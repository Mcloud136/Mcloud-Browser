#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""r5_runtime_perf_check.py — 真机**运行时**性能探针（不含任何编译时长）。

三条确定性场景，全部本地自给，不依赖外网：
  S1 页面加载：本地 HTTP 服务（1 CSS + 2 JS + 30 图）+ Navigation/Paint Timing，5 次取中位
  S2 脚本执行：页内微基准（排序 30 万元素 / JSON 2 MB 往返 / 100 万次字符串拼接 / WebCrypto SHA-256 4 MB）
  S3 视频管线：canvas.captureStream → MediaRecorder 生成 3 s WebM → 播放，读
     getVideoPlaybackQuality()（总帧/丢帧）与 requestVideoFrameCallback 计数

第四条是**可选观测**：YouTube 是否能连、播放器自身发了多少并发分段请求
（从 Resource Timing 的 startTime/duration 算最大重叠并发）。连不上就报 env，
绝不用别的数字冒充它。

纪律：独立 profile（临时目录）+ 端口由系统分配；结束按 profile 指纹清理，不做机器级杀进程；
取不到数据一律非 0（0=判据成立 / 1=判据不成立 / 2=环境不满足）。
"""
import base64
import json
import os
import socket
import statistics
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import cdp  # noqa: E402

INSTALLED = os.environ.get("MCHROME_INSTALLED_EXE") or \
    r"C:\Program Files\Chromium\Application\chrome.exe"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
IMGS = 30

HTML = ("<!doctype html><meta charset=utf-8><title>r5</title>"
        "<link rel=stylesheet href=/app.css?r=%R%>"
        "<body><h1>r5 runtime probe</h1><div id=box></div>"
        + "".join(f"<img src=/img.png?i={i}&amp;r=%R% width=16 height=16>" for i in range(IMGS))
        + "<script src=/a.js?r=%R%></script><script src=/b.js?r=%R%></script>")
CSS = "".join(".c%d{color:#%03x;margin:%dpx}" % (i, i % 4096, i % 7) for i in range(200))
A_JS = ("var acc=0;for(var i=0;i<20000;i++){acc=(acc+i*31)%1000003;}"
        "window.__a=acc;document.getElementById('box').textContent='a='+acc;")
B_JS = "window.__b=Object.keys(window).length;"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/app.css":
            self._send(CSS.encode(), "text/css")
        elif p == "/a.js":
            self._send(A_JS.encode(), "application/javascript")
        elif p == "/b.js":
            self._send(B_JS.encode(), "application/javascript")
        elif p == "/img.png":
            self._send(PNG, "image/png")
        elif p in ("/", "/index.html"):
            r = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("run", ["0"])[0]
            self._send(HTML.replace("%R%", r).encode(), "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *a):
        pass


LOAD_JS = r"""
(async () => {
  const done = new Promise(r => {
    if (document.readyState === 'complete') r();
    else addEventListener('load', r, {once: true});
  });
  await done;
  await new Promise(r => setTimeout(r, 0));
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paint = {};
  for (const e of performance.getEntriesByType('paint')) paint[e.name] = Math.round(e.startTime * 10) / 10;
  const res = performance.getEntriesByType('resource');
  return {dcl: Math.round(nav.domContentLoadedEventEnd * 10) / 10,
          load: Math.round(nav.loadEventEnd * 10) / 10,
          ttfb: Math.round(nav.responseStart * 10) / 10,
          paint, resources: res.length,
          transferred: res.reduce((a, e) => a + (e.transferSize || 0), 0)};
})()
"""

JS_BENCH = r"""
(async () => {
  const med = a => { const s = [...a].sort((x, y) => x - y); return s[(s.length / 2) | 0]; };
  const out = {};
  // 1) 排序 30 万浮点
  const mk = () => Array.from({length: 300000}, () => Math.random() * 1e6);
  let t = [];
  for (let i = 0; i < 5; i++) {
    const a = mk(); const s = performance.now(); a.sort((x, y) => x - y); t.push(performance.now() - s);
  }
  out.sort300k_ms = Math.round(med(t) * 100) / 100;
  // 2) JSON 2 MB 往返
  const obj = {rows: Array.from({length: 20000}, (_, i) => ({id: i, name: 'row-' + i, v: i * 1.5}))};
  const text = JSON.stringify(obj);
  t = [];
  for (let i = 0; i < 5; i++) {
    const s = performance.now(); const r = JSON.stringify(JSON.parse(text)); t.push(performance.now() - s);
    if (r.length !== text.length) throw new Error('json roundtrip mismatch');
  }
  out.json2mb_ms = Math.round(med(t) * 100) / 100; out.json_bytes = text.length;
  // 3) 100 万次字符串拼接（数组 + join，主流正确写法）
  t = [];
  for (let i = 0; i < 5; i++) {
    const s = performance.now(); const a = new Array(1000000);
    for (let j = 0; j < a.length; j++) a[j] = (j & 1023).toString(16);
    const joined = a.join(''); t.push(performance.now() - s);
    if (joined.length < 1000000) throw new Error('join short');
  }
  out.join1m_ms = Math.round(med(t) * 100) / 100;
  // 4) WebCrypto SHA-256 over 4 MB
  const buf = new Uint8Array(4 * 1024 * 1024);
  for (let i = 0; i < buf.length; i += 4096) buf[i] = i & 255;
  t = [];
  for (let i = 0; i < 5; i++) {
    const s = performance.now();
    await crypto.subtle.digest('SHA-256', buf);
    t.push(performance.now() - s);
  }
  out.sha256_4mb_ms = Math.round(med(t) * 100) / 100;
  return out;
})()
"""

VIDEO_JS = r"""
(async () => {
  const c = document.createElement('canvas'); c.width = 640; c.height = 360;
  const ctx = c.getContext('2d');
  const types = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  const mime = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
  if (!mime) return {error: 'no supported MediaRecorder mime'};
  const stream = c.captureStream(30);
  const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond: 4000000});
  const chunks = []; rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
  const stopped = new Promise(r => { rec.onstop = r; });
  const t0 = performance.now();
  let raf; const draw = () => {
    const t = (performance.now() - t0) / 1000;
    ctx.fillStyle = 'hsl(' + ((t * 120) % 360) + ',70%,45%)'; ctx.fillRect(0, 0, 640, 360);
    ctx.fillStyle = '#fff'; ctx.fillRect((t * 160) % 600, (t * 90) % 320, 60, 60);
    raf = requestAnimationFrame(draw);
  };
  draw(); rec.start(100);
  await new Promise(r => setTimeout(r, 3000));
  cancelAnimationFrame(raf); rec.stop(); await stopped;
  stream.getTracks().forEach(t => t.stop());
  const blob = new Blob(chunks, {type: mime.split(';')[0]});
  const url = URL.createObjectURL(blob);
  const v = document.createElement('video');
  v.muted = true; v.playsInline = true; v.src = url; document.body.appendChild(v);
  await new Promise((res, rej) => {
    v.onloadedmetadata = res; v.onerror = () => rej(new Error('video element error'));
  });
  let rvfc = 0;
  if (v.requestVideoFrameCallback) {
    const cb = () => { rvfc++; v.requestVideoFrameCallback(cb); };
    v.requestVideoFrameCallback(cb);
  }
  const ps = performance.now();
  try { await v.play(); } catch (e) { return {error: 'play() rejected: ' + e.message, mime}; }
  await new Promise(res => { v.onended = res; setTimeout(res, 20000); });
  const wall = performance.now() - ps;
  const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {};
  URL.revokeObjectURL(url);
  return {mime, w: v.videoWidth, h: v.videoHeight,
          mediaDur: Math.round(v.duration * 1000) / 1000,
          encodeBytes: blob.size, encodedMs: Math.round((performance.now() - t0 - wall) * 10) / 10,
          wallMs: Math.round(wall * 10) / 10, rvfcFrames: rvfc,
          totalVideoFrames: q.totalVideoFrames, droppedVideoFrames: q.droppedVideoFrames,
          corruptedVideoFrames: q.corruptedVideoFrames};
})()
"""

YT_STATS_JS = r"""
(() => {
  const es = performance.getEntriesByType('resource')
      .filter(e => /googlevideo\.com/.test(e.name));
  const segs = es.map(e => ({s: e.startTime, d: e.duration}));
  const ev = [];
  for (const x of segs) { ev.push([x.s, 1]); ev.push([x.s + x.d, -1]); }
  ev.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let cur = 0, mx = 0;
  for (const [, v] of ev) { cur += v; if (cur > mx) mx = cur; }
  const durs = segs.map(x => x.d).sort((a, b) => a - b);
  const v = document.querySelector('video');
  const q = v && v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {};
  return {segments: segs.length, maxConcurrent: mx,
          medianSegMs: durs.length ? Math.round(durs[(durs.length / 2) | 0]) : 0,
          bytes: es.reduce((a, e) => a + (e.encodedBodySize || 0), 0),
          video: v ? {t: Math.round(v.currentTime * 100) / 100, w: v.videoWidth, h: v.videoHeight,
                      readyState: v.readyState, paused: v.paused,
                      frames: q.totalVideoFrames, dropped: q.droppedVideoFrames} : null};
})()
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main():
    if not os.path.isfile(INSTALLED):
        print(json.dumps({"env_fail": "找不到浏览器 %s" % INSTALLED}, ensure_ascii=False))
        return 2
    srv, web_port = start_server()
    # profile 叶子名必须唯一：kill_instance 按叶子名匹配命令行来清理进程，
    # 叫 "profile" 会误杀其它同名实例（D52/D55 纪律）。
    prof = os.path.join(tempfile.mkdtemp(prefix="r5-runtime-"),
                        "r5prof-%d-%d" % (os.getpid(), int(time.time())))
    port = free_port()
    res = {"browser": INSTALLED, "web_port": web_port, "cdp_port": port}
    fails = []
    env_fail = None
    try:
        cdp.launch(INSTALLED, prof, port,
                          extra=["--mute-audio", "--disable-features=Translate"])
        if not cdp.wait_for_port(port, timeout=40):
            print(json.dumps({"env_fail": "调试端口未起来", "port": port}, ensure_ascii=False))
            return 2
        tab = cdp.Tab(port=port, url="about:blank", timeout=40)

        # ---- S1 页面加载 ----
        loads = []
        for run in range(5):
            tab.navigate("http://127.0.0.1:%d/?run=%d" % (web_port, run), settle=0.3)
            for _ in range(50):
                st = tab.evaluate("document.readyState")
                if st == "complete":
                    break
                time.sleep(0.1)
            loads.append(tab.evaluate(LOAD_JS, timeout=40))
        ok_loads = [x for x in loads if x and x.get("load", 0) > 0]
        if not ok_loads:
            fails.append("S1 页面加载：5 次都没有 loadEventEnd")
        else:
            def med(k):
                return round(statistics.median([x[k] for x in ok_loads]), 2)
            res["S1_page_load"] = {"runs": len(ok_loads),
                                   "median_dcl_ms": med("dcl"), "median_load_ms": med("load"),
                                   "median_ttfb_ms": med("ttfb"),
                                   "median_fcp_ms": round(statistics.median(
                                       [x["paint"].get("first-contentful-paint", 0) for x in ok_loads]), 2),
                                   "resources": ok_loads[-1].get("resources"),
                                   "transferred": ok_loads[-1].get("transferred")}
            if (res["S1_page_load"]["resources"] or 0) < IMGS + 3:
                fails.append("S1 资源数不足：%s（期望 >= %d）"
                             % (res["S1_page_load"]["resources"], IMGS + 3))

        # ---- S2 脚本执行 ----
        bench = tab.evaluate(JS_BENCH, timeout=120)
        res["S2_script"] = bench
        if not bench or "sort300k_ms" not in bench:
            fails.append("S2 脚本基准没有返回数据")

        # ---- S3 视频管线 ----
        vid = tab.evaluate(VIDEO_JS, timeout=120)
        res["S3_video"] = vid
        if not vid or vid.get("error"):
            fails.append("S3 视频：%s" % (vid or {}).get("error", "无返回"))
        else:
            tot = vid.get("totalVideoFrames") or 0
            drop = vid.get("droppedVideoFrames") or 0
            if tot <= 0:
                fails.append("S3 视频：totalVideoFrames=0（没有真正解码）")
            elif tot and drop / tot > 0.25:
                fails.append("S3 视频：丢帧率 %.0f%% > 25%%" % (100.0 * drop / tot))

        # ---- S5 真实网页加载（网络相关，默认 bing；用 R5_NET_URL 覆盖）----
        net_url = os.environ.get("R5_NET_URL", "https://www.bing.com/")
        try:
            tab.navigate(net_url, settle=0.5)
            st = None
            for _ in range(60):
                st = tab.evaluate("document.readyState")
                if st == "complete":
                    break
                time.sleep(0.5)
            if st == "complete":
                res["S5_net_page"] = tab.evaluate(LOAD_JS, timeout=60)
                res["S5_net_page"]["url"] = net_url
            else:
                res["S5_net_page"] = {"env_fail": "页面在 30 s 内未 complete", "url": net_url}
                env_fail = env_fail or "S5 真实网页未加载完成（网络类）"
        except Exception as e:                       # noqa: BLE001
            res["S5_net_page"] = {"env_fail": "%s: %s" % (type(e).__name__, e), "url": net_url}
            env_fail = env_fail or "S5 真实网页观测异常（网络类）"

        # ---- S4 YouTube（可选观测）----
        try:
            tab.navigate("https://www.youtube.com/watch?v=dQw4w9WgXcQ", settle=1.0)
            playing = False
            for _ in range(30):
                st = tab.evaluate(
                    "(function(){var v=document.querySelector('video');"
                    "return v?{t:v.currentTime,r:v.readyState}:null})()")
                if st and st.get("t", 0) > 0.5:
                    playing = True
                    break
                # 有些环境需要显式 play()
                tab.evaluate("(function(){var v=document.querySelector('video');"
                             "if(v){v.muted=true;v.play&&v.play().catch(function(){});}})()")
                time.sleep(1.0)
            if not playing:
                res["S4_youtube"] = {"env_fail": "页面未进入播放（网络不可达/同意页/需要登录）",
                                     "url": tab.url(), "title": (tab.title() or "")[:80]}
                env_fail = "YouTube 未进入播放，S4 只报环境不报结论"
            else:
                time.sleep(8.0)
                res["S4_youtube"] = tab.evaluate(YT_STATS_JS, timeout=60)
        except Exception as e:                       # noqa: BLE001
            res["S4_youtube"] = {"env_fail": "%s: %s" % (type(e).__name__, e)}
            env_fail = "YouTube 观测异常（环境类）"

        tab.close()
    finally:
        left = cdp.kill_instance(prof, port=port)
        srv.shutdown()
        res["residue"] = left
        if left:
            fails.append("残留进程 %d 个" % left)

    res["FAILED_CHECKS"] = fails
    if env_fail:
        res["ENV_NOTE"] = env_fail
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
