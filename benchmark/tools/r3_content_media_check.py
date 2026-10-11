#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R3 内容与媒体实操（第4周期，2026-10-11）。

覆盖"用户真的会做的事"，判据全部来自浏览器自己的回答，不看脚本脸色：

  1. 本地 1080p H.264 真播放（1.18 GB 录屏文件）：currentTime 必须推进，
     `getVideoPlaybackQuality()` 的丢帧率必须低于阈值；
  2. `chrome://media` 读回解码器归属（这是比 chrome://gpu 更权威的证据：它按**流**
     报告用的是 MojoVideoDecoder 还是 SwiftShader，且内容在 shadow root 里，必须走
     deep_text）；
  3. 真 PiP / 真全屏：`requestPictureInPicture()`/`requestFullscreen()` 只在**可信手势**
     里被允许，所以 evaluate 必须带 userGesture，否则会把"浏览器不让"当成"我们坏了"；
  4. 真下载：本地起一个 stdlib HTTP 服务（http 源，避免 file:// 的下载策略噪声），
     CDP 点 `<a download>`，核对字节真的落到磁盘；
  5. 真打印：`Page.printToPDF` 出 PDF，核对文件头与体积；
  6. HEVC/AV1：只有当测试源可达时才测，不可达记 NOT-TESTED——**不许拿"没测"当"通过"**。

退出码：0=硬判据全部成立；1=有硬判据不成立；2=环境不满足（视频文件缺失等）。
"""
import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import cdp                                                        # noqa: E402

DEV_EXE = os.environ.get("MCHROME_EXE",
                         r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe")
OUT = os.path.join(THOR, ".cycle4")
PORT = 9421
WEB_VIDEO = "https://test-videos.co.uk/media/Big_Buck_Bunny_1080_10s_1MB.mp4"
HEVC_CANDIDATES = ("https://test-videos.co.uk/media/Big_Buck_Bunny_1080_10s_1MB_HEVC.mp4",
                   "https://test-videos.co.uk/vids/hevc/mp4/1080/10s_1MB.mp4")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_a):
        pass


def start_http(root, port):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "payload.txt"), "w", encoding="utf-8") as fh:
        fh.write("MCloud R3 download probe payload\n" * 200)
    # 不能用 `document.body.innerText=...` 打标记：赋值 innerText 会**替换掉全部子节点**，
    # 于是刚写的 <a download> 自己把自己删了，后面 getElementById('d') 得到 null
    # （首版的下载步骤就是这么断的）。标记改成一个静态元素。
    page = ("<!doctype html><meta charset=utf-8><title>r3dl</title>"
            "<a id=d href=payload.txt download=r3-payload.txt>down</a>"
            "<p id=m>R3-DL-READY</p>")
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    # SimpleHTTPRequestHandler.__init__ 会用 `self.directory = directory or "."` 覆盖
    # 类属性，所以不能用 type() 塞 directory（首版因此 404，下载判据全空）。
    handler = functools.partial(QuietHandler, directory=root)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def video_page(src):
    return ("<!doctype html><meta charset=utf-8><title>r3media</title>"
            "<video id=v width=640 controls autoplay playsinline src='%s'></video>" % src)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEV_EXE)
    ap.add_argument("--video", default=r"C:\Users\Administrator\Videos\2026-10-07 14-27-54.mp4")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--http-port", type=int, default=8765)
    args = ap.parse_args()
    res = {}
    if not os.path.isfile(args.exe):
        print("FAIL: 找不到 %s" % args.exe)
        return 2
    if not os.path.isfile(args.video):
        print("FAIL: 找不到本地视频 %s（播放判据依赖它，不许退化成「没视频也算过」）" % args.video)
        return 2
    os.makedirs(OUT, exist_ok=True)
    dl_dir = os.path.join(OUT, "dl")
    shutil.rmtree(dl_dir, ignore_errors=True)
    os.makedirs(dl_dir)
    web_root = os.path.join(OUT, "webroot")
    srv = start_http(web_root, args.http_port)
    prof = os.path.join(OUT, "r3-prof")
    page_dir = os.path.join(OUT, "r3pages")
    os.makedirs(page_dir, exist_ok=True)
    local_page = os.path.join(page_dir, "local_video.html")
    with open(local_page, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(video_page("file:///" + args.video.replace("\\", "/").replace(" ", "%20")))
    proc = cdp.launch(args.exe, prof, args.port)
    try:
        if not cdp.wait_for_port(args.port, timeout=40):
            print(json.dumps({"env_fail": "端口没起来"}, ensure_ascii=False))
            return 2
        time.sleep(3)
        bws = cdp.WSClient(cdp.browser_endpoint(args.port))
        bws.call("Browser.setDownloadBehavior",
                 {"behavior": "allow", "downloadPath": dl_dir})

        # --- 1. 本地 1080p H.264 真播放 ---
        tab = cdp.Tab(port=args.port, url="about:blank")
        tab.navigate("file:///" + local_page.replace("\\", "/"))
        tab.wait_for("!!document.getElementById('v')", timeout=20)
        tab.evaluate("var v=document.getElementById('v'); v.play().catch(function(){})",
                     user_gesture=True)
        time.sleep(8)
        q = tab.evaluate("""(function(){var v=document.getElementById('v');
            var a=v.getVideoPlaybackQuality();
            return JSON.stringify({t:v.currentTime, w:v.videoWidth, h:v.videoHeight,
              rs:v.readyState, err:v.error?v.error.code:0,
              total:a.totalVideoFrames, dropped:a.droppedVideoFrames});})()""")
        q = json.loads(q or "{}")
        res["playback"] = q
        res["playback_advances"] = bool(q.get("t", 0) > 2.0)
        # 不写死分辨率：这台机上的录屏就是这台机上的录屏，判"至少 1080 行、尺寸确实被
        # 探测到了"，具体数值进日志由人读。
        res["playback_resolution_ok"] = q.get("w", 0) > 0 and q.get("h", 0) >= 1080
        tot, drop = q.get("total", 0), q.get("dropped", 0)
        res["playback_no_media_error"] = q.get("err", 0) == 0 and q.get("rs", 0) >= 3
        # 丢帧率：8 秒 1080p 硬解，阈值取 5%（远高于噪声，真掉速才会超）
        res["playback_drop_ok"] = tot > 30 and (drop / tot) < 0.05
        res["screenshot_playback"] = tab.try_screenshot(os.path.join(OUT, "r3_playback.png"))

        # --- 2. chrome://media：解码器归属（必须在播放器**正在跑**的时候读）---
        # 上一版是先读完再切走，chrome://media 只剩 74 字符的空壳；这里让视频 loop 起来
        # 再开第二个标签读，并把原文留在结果里由人判。
        loop_page = os.path.join(page_dir, "loop_video.html")
        with open(loop_page, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(video_page("file:///" + args.video.replace("\\", "/").replace(" ", "%20"))
                     .replace("<video ", "<video loop "))
        tab.navigate("file:///" + loop_page.replace("\\", "/"))
        tab.wait_for("!!document.getElementById('v')", timeout=20)
        tab.evaluate("document.getElementById('v').play().catch(function(){})",
                     user_gesture=True)
        time.sleep(5)
        mtab = cdp.Tab(port=args.port, url="about:blank")
        mtab.navigate("chrome://media-internals")
        mtxt = mtab.wait_for_text(20, timeout=25)
        res["media_page_len"] = len(mtxt)
        res["media_page_raw_head"] = mtxt[:400]
        res["media_decoder_lines"] = [l.strip()[:160] for l in mtxt.splitlines()
                                      if any(k in l for k in
                                             ("Decoder", "hev", "avc", "Mojo", "hardware",
                                              "GPU", "Video"))][:14]
        # 长度只证明"有字"，不证明"是我们要的页"：错误页同样有几十个字（本轮就被
        # chrome://media 这个错 URL 骗过一次，真名 chrome://media-internals）。
        res["media_page_readable"] = len(mtxt) > 20 and not cdp.is_error_page(mtxt)

        # --- 3. 真 PiP + 真全屏（都必须先把标签切到前台）---
        # requestFullscreen 在非激活文档上抛 `TypeError: not granted`——那是 CDP 新建
        # 标签默认在后台造成的，不是产品坏了；所以这里显式 activateTarget。
        tab.navigate("file:///" + local_page.replace("\\", "/"))
        tab.wait_for("!!document.getElementById('v')", timeout=20)
        cdp.activate_tab(args.port, tab.target_id)
        time.sleep(2)
        res["tab_active"] = bool(tab.evaluate("document.hasFocus()"))
        try:
            tab.evaluate("document.getElementById('v').requestPictureInPicture()",
                         user_gesture=True)
            time.sleep(2)
            res["pip_entered"] = bool(tab.evaluate("!!document.pictureInPictureElement"))
        except Exception as exc:                                 # noqa: BLE001
            res["pip_entered"] = False
            res["pip_error"] = repr(exc)[:200]
        try:
            tab.evaluate("document.getElementById('v').requestFullscreen()", user_gesture=True)
            time.sleep(2)
            res["fullscreen_entered"] = bool(tab.evaluate("!!document.fullscreenElement"))
        except Exception as exc:                                 # noqa: BLE001
            res["fullscreen_entered"] = False
            res["fullscreen_error"] = repr(exc)[:200]
        res["screenshot_fullscreen"] = tab.try_screenshot(os.path.join(OUT, "r3_fullscreen.png"))
        try:
            tab.evaluate("document.exitFullscreen()", user_gesture=True)
            time.sleep(1.5)
            res["fullscreen_exited"] = not tab.evaluate("!!document.fullscreenElement")
        except Exception as exc:                                 # noqa: BLE001
            res["fullscreen_exited"] = False
            res["fullscreen_exit_error"] = repr(exc)[:160]

        # --- 4. 真下载 ---
        dtab = cdp.Tab(port=args.port, url="about:blank")
        dtab.navigate("http://127.0.0.1:%d/index.html" % args.http_port)
        dtxt = dtab.wait_for_text(10, timeout=20)
        res["dl_page_text"] = dtxt[:40]
        box = json.loads(dtab.evaluate(
            "JSON.stringify(document.getElementById('d').getBoundingClientRect())"))
        dtab.click(int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2))
        landed = None
        for _ in range(20):
            time.sleep(0.5)
            for f in os.listdir(dl_dir):
                if f.startswith("r3-payload") and not f.endswith(".crdownload"):
                    landed = os.path.join(dl_dir, f)
                    break
            if landed:
                break
        res["download_file"] = landed
        res["download_ok"] = bool(landed) and os.path.getsize(landed) > 1000

        # --- 5. 真打印 ---
        pdf = os.path.join(OUT, "r3_print.pdf")
        try:
            r = dtab.ws.call("Page.printToPDF", {"printBackground": True}, timeout=60)
            import base64
            with open(pdf, "wb") as fh:
                fh.write(base64.b64decode(r["data"]))
            res["pdf_bytes"] = os.path.getsize(pdf)
            res["pdf_ok"] = res["pdf_bytes"] > 2000 and open(pdf, "rb").read(5) == b"%PDF-"
        except Exception as exc:                                 # noqa: BLE001
            res["pdf_ok"] = False
            res["pdf_error"] = repr(exc)[:200]

        # --- 6. HEVC/AV1：可达才测，不可达记 NOT-TESTED ---
        hevc_state = "NOT-TESTED"
        for url in HEVC_CANDIDATES:
            # 先问服务器有没有这个文件，再问浏览器能不能解——否则 404 会被读成
            # `MEDIA_ERR_SRC_NOT_SUPPORTED(err=4)`，而 4 既可能是"源不存在"也可能是
            # "解码器不支持"，两种归因完全不同。
            try:
                head = urllib.request.urlopen(
                    urllib.request.Request(url, method="HEAD"), timeout=15)
                if head.status != 200:
                    hevc_state = "SOURCE-UNREACHABLE http %s" % head.status
                    continue
            except Exception as exc:                             # noqa: BLE001
                hevc_state = "SOURCE-UNREACHABLE %s" % type(exc).__name__
                continue
            try:
                href = "data:text/html;charset=utf-8," + urllib.parse.quote(video_page(url))
                dtab.navigate(href)
                dtab.wait_for("var v=document.getElementById('v');"
                              "v && (v.readyState > 0 || v.error)", timeout=25)
                info = json.loads(dtab.evaluate("""(function(){var v=document.getElementById('v');
                    return JSON.stringify({w:v.videoWidth,rs:v.readyState,
                      err:v.error?v.error.code:0});})()""") or "{}")
                if info.get("w", 0) > 0:
                    hevc_state = "PLAYING %sx%s" % (info.get("w"), info.get("h"))
                    break
                hevc_state = "SOURCE-OK-BUT-NO-VIDEO %s" % info
            except Exception as exc:                             # noqa: BLE001
                hevc_state = "LOAD-FAIL %s" % repr(exc)[:60]
        res["hevc"] = hevc_state
        # --- 6b. MediaCapabilities：不需要媒体文件的解码能力权威问询 ---
        # 远端 HEVC 源在这台机器上不可达（test-videos.co.uk 三个 URL 全部失败），
        # 但"这个构建到底能不能硬解 HEVC/AV1"不必靠下载文件来猜：
        # navigator.mediaCapabilities.decodingInfo() 会走真实的解码器能力查询，
        # powerEfficient=true 即硬件路径。这是可离线复现的判据。
        try:
            caps = json.loads(tab.evaluate("""(async function(){
              var out = {};
              var list = {h264:'video/mp4; codecs="avc1.640028"',
                          hevc:'video/mp4; codecs="hvc1.1.6.L93.B0"',
                          av1 :'video/mp4; codecs="av01.0.05M.08"',
                          vp9 :'video/webm; codecs="vp09.00.10.08"'};
              for (const k in list) {
                try {
                  var r = await navigator.mediaCapabilities.decodingInfo({
                    type: 'file',
                    video: {contentType: list[k], width: 1920, height: 1080,
                            // M155 起 framerate 是**必填**（缺了整次调用抛 TypeError，
                            // 四个 codec 全变 err，看着像"能力查询失败"其实是参数不全）
                            bitrate: 4000000, framerate: 30}});
                  out[k] = {supported: r.supported, smooth: r.smooth,
                            powerEfficient: r.powerEfficient};
                } catch (e) { out[k] = {err: String(e)}; }
              }
              return JSON.stringify(out);
            })()""", timeout=40))
            res["decoding_info"] = caps
            # HEVC 是我们花力气开 PlatformHEVCDecoderSupport 的理由：必须 supported
            res["hevc_supported"] = bool(caps.get("hevc", {}).get("supported"))
            res["av1_supported"] = bool(caps.get("av1", {}).get("supported"))
        except Exception as exc:                                 # noqa: BLE001
            res["decoding_info_error"] = repr(exc)[:200]
            res["hevc_supported"] = False
            res["av1_supported"] = False

        res["doh_pref"] = None
        pref = os.path.join(prof, "Default", "Preferences")
        if os.path.isfile(pref):
            try:
                j = json.load(open(pref, encoding="utf-8"))
                res["doh_pref"] = j.get("dns_over_https")
            except Exception as exc:                             # noqa: BLE001
                res["doh_pref_error"] = repr(exc)[:120]
        bws.sock.close()
        for t in (tab, mtab, dtab):
            t.close()
    except Exception as exc:                                     # noqa: BLE001
        import traceback
        res["env_fail"] = "unexpected: %r" % exc
        res["traceback"] = traceback.format_exc()[-900:]
    finally:
        srv.shutdown()
        res["leftover_procs"] = cdp.kill_instance(prof, port=args.port)
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % prof],
                       capture_output=True)
        try:
            proc.wait(timeout=20)
        except Exception:                                        # noqa: BLE001
            proc.kill()

    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("env_fail"):
        print("ENV-FAIL: %s" % res["env_fail"])
        return 2
    hard = [k for k in ("playback_advances", "playback_resolution_ok", "playback_no_media_error",
                        "playback_drop_ok", "media_page_readable", "pip_entered",
                        "fullscreen_entered", "fullscreen_exited", "download_ok", "pdf_ok", "hevc_supported")
            if not res.get(k)]
    if res.get("leftover_procs"):
        hard.append("leftover_procs")
    print("\nFAILED-CHECKS: %s" % (hard or "none"))
    # 两条 HEVC 判据要分清：`hevc_supported` 是浏览器自己的能力查询（MediaCapabilities），
    # 不需要媒体文件，所以它**是**硬判据；`hevc` 是远端真播放，源不可达时只报状态不判失败。
    print("NOTE: hevc 远端播放=%s（不计入硬判据：源不可达只报状态）；"
          "hevc_supported 走 MediaCapabilities 能力查询，是硬判据"
          % res.get("hevc"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
