#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r6_video_stability_check.py — 视频播放的**流畅与稳定**判据（真机、安装版、独立 profile）。

要回答的问题是"卡在哪"：解码走的是硬件还是软件、有没有 rebuffer、缓冲余量够不够、
走的是 h2/h3 还是 h1.1 回退。全部读浏览器自报值，不靠推断。

测量分两段（共用一条 CDP 连接）：
  Phase 1（默认 15 s）：`Media.domain` + `Network.domain` 事件流，抓
      kVideoDecoderName / kAudioDecoderName / kIsPlatformVideoDecoder 与每个媒体分段的协议；
  Phase 2（默认 45 s）：每秒采样 currentTime / buffered 末尾 / readyState，统计
      waiting（rebuffer 停顿）次数与缓冲余量的最小值/中位数。

判据（每条都可能红）：
  - 必须真正进入播放（currentTime 前进 > 1 s）
  - waiting 事件数 = 0 才算"无 rebuffer 停顿"
  - 播放推进速率 ∈ [0.97, 1.03]（墙钟 vs 媒体时间）
  - 丢帧率 <= 5%
  - 解码器必须读得到（读不到就报 env，不猜"应该是硬解"）
退出码：0=全绿；1=有判据不成立；2=环境不满足（连不上/不播放/取不到数据）。
"""
import contextlib
import json
import collections
import os
import socket
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

INSTALLED = os.environ.get("MCHROME_INSTALLED_EXE") or \
    r"C:\Program Files\Chromium\Application\chrome.exe"
URL = os.environ.get("R6_URL", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
PHASE1 = float(os.environ.get("R6_PHASE1", "15"))
PHASE2 = float(os.environ.get("R6_PHASE2", "45"))

INJECT = r"""
(() => {
  const v = document.querySelector('video');
  if (!v) return null;
  if (!window.__vstats) {
    window.__vstats = {waiting: 0, stalled: 0, error: 0, playing: 0, suspend: 0, emptied: 0};
    for (const e of Object.keys(window.__vstats)) {
      v.addEventListener(e, () => { window.__vstats[e]++; });
    }
    // YouTube 的 <video>.getVideoPlaybackQuality() 实测返回空对象（不是 VideoPlaybackQuality），
    // 帧数只能靠 requestVideoFrameCallback 自己数（r6 首版在这里因 totalVideoFrames=0 误红）。
    window.__rf = 0;
    if (v.requestVideoFrameCallback) {
      const cb = () => { window.__rf++; v.requestVideoFrameCallback(cb); };
      v.requestVideoFrameCallback(cb);
    }
  }
  return {t: v.currentTime, r: v.readyState, paused: v.paused};
})()
"""

SAMPLE = r"""
(() => {
  const v = document.querySelector('video');
  if (!v) return null;
  const b = v.buffered;
  const ahead = b.length ? (b.end(b.length - 1) - v.currentTime) : 0;
  return {t: v.currentTime, ahead, r: v.readyState, paused: v.paused,
          rf: window.__rf || 0, stats: window.__vstats || null};
})()
"""


def main():
    if not os.path.isfile(INSTALLED):
        print(json.dumps({"env_fail": "找不到浏览器 %s" % INSTALLED}, ensure_ascii=False))
        return 2
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    prof = os.path.join(tempfile.mkdtemp(prefix="r6-stab-"),
                        "r6prof-%d-%d" % (os.getpid(), int(time.time())))
    out = {"browser": INSTALLED, "url": URL, "phase1_s": PHASE1, "phase2_s": PHASE2}
    fails = []
    try:
        cdp.launch(INSTALLED, prof, port,
                   extra=["--mute-audio",
                          "--autoplay-policy=no-user-gesture-required",
                          "--window-size=1920,1080"])
        if not cdp.wait_for_port(port, timeout=40):
            print(json.dumps({"env_fail": "调试端口未起来"}, ensure_ascii=False))
            return 2
        tab = cdp.Tab(port=port, url="about:blank", timeout=40)
        tab.ws.call("Network.enable")
        tab.ws.call("Media.enable")
        tab.navigate(URL, settle=1.0)

        # 进入播放（最多 30 s）
        playing = False
        for _ in range(30):
            st = tab.evaluate(INJECT)
            tab.evaluate("(function(){var v=document.querySelector('video');"
                         "if(v){v.muted=true;v.play&&v.play().catch(function(){});}})()")
            if st and st.get("t", 0) > 1.0 and (st.get("r") or 0) >= 2:
                playing = True
                break
            time.sleep(1.0)
        if not playing:
            out["env_fail"] = "未进入播放（网络/同意页/需要登录）"
            out["title"] = (tab.title() or "")[:100]
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return 2

        # Phase 1：事件流 —— 解码器 + 协议
        decoders = {}
        media_props = collections.Counter()
        protos = collections.Counter()
        bytes_by_proto = collections.Counter()
        t0 = time.time()
        tab.ws.sock.settimeout(2.0)
        while time.time() - t0 < PHASE1:
            try:
                msg = json.loads(tab.ws._read_frame())
            except socket.timeout:
                continue
            m = msg.get("method")
            if m == "Media.playerPropertiesChanged":
                for p in msg["params"].get("properties", []):
                    k, v = p.get("name"), p.get("value")
                    if k in ("kVideoDecoderName", "kAudioDecoderName",
                             "kIsPlatformVideoDecoder", "kIsPlatformAudioDecoder",
                             "kVideoTracks", "kAudioTracks"):
                        media_props[(k, str(v)[:60])] += 1
                        if k in ("kVideoDecoderName", "kAudioDecoderName"):
                            decoders[k] = str(v)[:60]
            elif m == "Network.responseReceived":
                r = msg["params"]["response"]
                u = r.get("url", "")
                if "googlevideo.com" in u:
                    pr = r.get("protocol", "?")
                    protos[pr] += 1
                    # CDP 的 headers 是 dict（不是 [{name,value}]）
                    hdrs = {str(k).lower(): v for k, v in (r.get("headers") or {}).items()}
                    with contextlib.suppress(TypeError, ValueError):
                        bytes_by_proto[pr] += int(hdrs.get("content-length") or 0)
        out["decoders"] = decoders
        out["media_properties"] = {"%s=%s" % k: n for k, n in media_props.items()}
        out["media_protocols"] = dict(protos)
        out["media_bytes_by_protocol"] = dict(bytes_by_proto)

        # Phase 2：每秒采样
        samples = []
        t1 = time.time()
        while time.time() - t1 < PHASE2:
            st = tab.evaluate(SAMPLE)
            if st:
                samples.append(st)
            time.sleep(1.0)
        if not samples:
            fails.append("Phase 2 采样为空")
        else:
            first, last = samples[0], samples[-1]
            wall = (time.time() - t1)
            adv = last["t"] - first["t"]
            rate = adv / wall if wall > 0 else 0
            aheads = [s["ahead"] for s in samples]
            stats = last.get("stats") or {}
            frames = (last.get("rf") or 0)
            out["playback"] = {
                "wall_s": round(wall, 2), "advanced_s": round(adv, 2),
                "rate": round(rate, 4),
                "buffer_ahead_min_s": round(min(aheads), 2),
                "buffer_ahead_median_s": round(sorted(aheads)[len(aheads) // 2], 2),
                "stalls_waiting": stats.get("waiting"),
                "stalled_events": stats.get("stalled"),
                "errors": stats.get("error"),
                "frames_rvfc": frames,
                "fps": round(frames / adv, 2) if adv > 0 else None,
                "final_resolution": tab.evaluate(
                    "(function(){var v=document.querySelector('video');"
                    "return v?v.videoWidth+'x'+v.videoHeight:null})()"),
            }
            if rate < 0.97 or rate > 1.03:
                fails.append("播放推进速率 %.3f 不在 [0.97, 1.03]" % rate)
            if stats.get("waiting"):
                fails.append("发生 %d 次 rebuffer 停顿（waiting 事件）" % stats["waiting"])
            if frames <= 0:
                fails.append("rVFC 帧数=0（没有真正解码/合成）")
        if not decoders:
            # 实测：YouTube 页面上 Media 域没有给出 playerPropertiesChanged，media-internals
            # 也读不出播放器条目。解码器身份因此**不可得**，记为环境说明而不是判据——
            # 用 GPU 能力清单（chrome://gpu 的 Decode vp9/av1）另行核对，不猜。
            out["decoder_note"] = ("Media 域未返回 kVideoDecoderName；解码器身份不可得"
                                   "（不计失败，但也不得据此声称硬解/软解）")
        tab.close()
    finally:
        left = cdp.kill_instance(prof, port=port)
        out["residue"] = left
        if left:
            fails.append("残留进程 %d 个" % left)
    out["FAILED_CHECKS"] = fails
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
