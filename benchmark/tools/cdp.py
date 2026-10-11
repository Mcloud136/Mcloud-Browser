#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cdp.py - 最小 Chrome DevTools Protocol 客户端（仅标准库，无第三方依赖）。

为什么需要它（第4周期 bug-review，2026-10-11）：本周期要求"实地操作优先于脚本反馈"。
仓库里既有的探针都只读进程命令行（Win32_Process.CommandLine），那属于"间接证据"——
它能证明开关进了命令行，但证明不了页面真的渲染成什么样、按钮真的能点、下载真的落盘。
这个客户端让我可以直接对真实浏览器：导航、执行 JS、读 DOM 文本、截图、点按钮、
触发下载并核对文件。

用法（作为库）：
    import cdp
    with cdp.Tab(port=9333, url="chrome://version") as tab:
        text = tab.evaluate("document.body.innerText")
        tab.screenshot(r"D:\\...\\version.png")

依赖：Python 3.8+，Windows/Linux 皆可（只用 socket/base64/json/urllib）。
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

__all__ = ["CDPError", "available_targets", "Tab", "launch", "wait_for_port", "kill_instance"]


class CDPError(RuntimeError):
    pass


# ---------------------------------------------------------------- HTTP 端点 ----
def _get_json(url, timeout=5.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def available_targets(port=9222, timeout=5.0):
    """/json/list：返回可调试目标列表。空列表是合法结果，但调用方必须自己判空。"""
    return _get_json("http://127.0.0.1:%d/json/list" % port, timeout=timeout)


def version_info(port=9222, timeout=5.0):
    return _get_json("http://127.0.0.1:%d/json/version" % port, timeout=timeout)


def browser_endpoint(port=9222):
    """浏览器级 WebSocket：Target.* 这类跨目标命令只能走它（附着到 page 会被拒）。"""
    return version_info(port)["webSocketDebuggerUrl"]


def activate_tab(port, target_id, timeout=10.0):
    """把标签切到前台。

    全屏、PiP、`document.hasFocus()` 相关的 API 都要求文档处于**激活**状态：
    CDP 新建的标签默认在后台，直接 requestFullscreen() 会抛
    `TypeError: not granted`（R3 实测），那是量具的问题，不是浏览器坏了。
    """
    ws = WSClient(browser_endpoint(port), timeout=timeout)
    try:
        ws.call("Target.activateTarget", {"targetId": target_id}, timeout=timeout)
    finally:
        try:
            ws.sock.close()
        except Exception:                                       # noqa: BLE001
            pass


# ------------------------------------------------------------ WebSocket 实现 ----
class WSClient:
    """够用的 WebSocket 客户端：文本帧、无分片续传、无扩展（CDP 正是这种用法）。"""

    def __init__(self, ws_url, timeout=30.0):
        # ws://127.0.0.1:9222/devtools/page/<id>
        rest = ws_url.split("://", 1)[1]
        hostport, _, path = rest.partition("/")
        path = "/" + path
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = [
            "GET %s HTTP/1.1" % path,
            "Host: %s:%s" % (host, port or 80),
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: %s" % key,
            "Sec-WebSocket-Version: 13",
            "", "",
        ]
        self.sock.sendall("\r\n".join(req).encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("handshake closed")
            buf += chunk
        head, _, self._pending = buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise CDPError("handshake rejected: %r" % head[:120])
        self._id = 0

    def _send_frame(self, payload):
        data = payload.encode("utf-8")
        header = bytearray([0x81])                      # FIN + text
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv_exact(self, n):
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise CDPError("socket closed")
            out += chunk
        return out

    def _read_frame(self):
        b0, b1 = self._recv_exact(2)
        ln = b1 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self._recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self._recv_exact(8))[0]
        payload = self._recv_exact(ln)
        if b0 & 0x0F == 0x8:                            # close
            raise CDPError("peer closed websocket")
        return payload.decode("utf-8", "replace")

    def call(self, method, params=None, timeout=30.0):
        """发一个命令并等它的响应（按 id 匹配，忽略中间的事件）。"""
        self.sock.settimeout(timeout)
        self._id += 1
        mine = self._id
        self._send_frame(json.dumps({"id": mine, "method": method,
                                     "params": params or {}}))
        while True:
            msg = json.loads(self._read_frame())
            if msg.get("id") == mine:
                if "error" in msg:
                    raise CDPError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})


# ------------------------------------------------------------------ Tab ----
# 穿透 shadow root 的整页文本表达式。
# Document 分支必须走 `body.innerText`：DOM 规范里 `document.textContent` 恒为空串
# （Document/DocumentType 的 textContent 特判返回 ""），写成 root.textContent 会让
# 无 shadow root 的普通页面读出 0 长度（本轮实测踩过，chrome://version 与 example.com
# 同时变空，而 chrome://gpu 因为恰好走 shadow 分支"看起来是好的"）。
DEEP_TEXT_JS = r"""(function(){
  var parts = [];
  function visit(root){
    if (!root) return;
    var t;
    if (root.body) { t = root.body.innerText; }              // Document
    else if (typeof root.innerText === 'string') { t = root.innerText; }
    else { t = root.textContent; }                           // ShadowRoot：只有 textContent
    if (t) parts.push(t);
    var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (var i = 0; i < all.length; i++) { if (all[i].shadowRoot) visit(all[i].shadowRoot); }
  }
  visit(document);
  return parts.join('\n');
})()"""


ERROR_PAGE_MARKERS = ("无法访问此网站", "无法访问该网站", "该网页无法正常运作", "ERR_",
                      "Aw, Snap", "This site can’t be reached", "Problem loading page")


def is_error_page(text):
    """错误页也是**有文本的页**：任何"读到了内容"的判据都必须先排除它。

    R3 实测：把 URL 写成 chrome://media（真名是 chrome://media-internals）时读出 74 字符
    的"无法访问此网站…ERR_INVALID_URL"，而当时的可读性门是 `len > 20`——于是错误页被判成
    "页面可读"，我差点据此写下"上游删掉了这个页"的错误结论。长度只能证明"有字"，
    不能证明"是我们想要的那个页"。
    """
    return any(m in (text or "") for m in ERROR_PAGE_MARKERS)


class Tab:
    """一个可调试页面目标；支持 evaluate / navigate / 截图 / 等待。"""
    def __init__(self, port=9222, url="about:blank", timeout=30.0, target_id=None):
        # 建标签一律先 about:blank，再在**会话就绪后**用 Page.navigate 打开目标 URL。
        # 原因（R2 实测）：`/json/new?url=X` 建的标签会把 X 丢掉——target 停在
        # about:blank 上，deep_text 永远读出 0，看起来像"页面没渲染"，其实是根本没导航。
        # 走 about:blank + navigate 这条路与手工操作一致，且能被 wait_for_text 正常观测。
        if target_id is None:
            try:
                info = _get_json("http://127.0.0.1:%d/json/new?about:blank" % port, timeout)
            except Exception:                       # noqa: BLE001  新版 Chrome 要求 PUT
                import urllib.request as u
                req = u.Request("http://127.0.0.1:%d/json/new?url=about%%3Ablank" % port,
                                method="PUT")
                with u.urlopen(req, timeout=timeout) as r:
                    info = json.loads(r.read().decode("utf-8"))
            target_id = info["id"]
        self.target_id = target_id
        tgt = [t for t in available_targets(port) if t.get("id") == target_id]
        if not tgt:
            raise CDPError("target %s 不在 /json/list 里（chrome:// 某些页可能被禁用调试）"
                           % target_id)
        self.ws = WSClient(tgt[0]["webSocketDebuggerUrl"], timeout=timeout)
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.port = port
        if url and url != "about:blank":
            self.navigate(url)

    # -- 读 -----------------------------------------------------------
    def evaluate(self, expr, timeout=30.0, user_gesture=False):
        """user_gesture=True 让 Chromium 把这次求值当成"用户手势"。

        requestPictureInPicture()/requestFullscreen() 这类 API 只在可信手势里才允许，
        普通 evaluate 会被静默拒绝——不加这个开关就会把"浏览器不让进 PiP"误判成
        "我们的 PiP 坏了"。
        """
        params = {"expression": expr, "returnByValue": True, "awaitPromise": True}
        if user_gesture:
            params["userGesture"] = True
        res = self.ws.call("Runtime.evaluate", params, timeout=timeout)
        detail = res.get("exceptionDetails")
        if detail:
            raise CDPError("JS 异常: %s" % json.dumps(detail)[:300])
        return res.get("result", {}).get("value")

    def text(self, selector="document.body", timeout=30.0):
        return self.evaluate("(function(){var e=document.querySelector(%r);"
                             "return e?e.innerText:null})()" % _unquote(selector),
                             timeout=timeout)

    def deep_text(self, timeout=30.0):
        """穿透 shadow DOM 取整页文本。

        Chrome WebUI 大量把内容渲染进自定义元素的 shadow root：实测 chrome://gpu 的
        `document.body.innerText` 长度为 **0**，而 `<info-view>` 的 shadowRoot 里有
        78,108 字符（.cycle4/diag_gpu_dom.py 的原始输出）。用 innerText 判读这类页面
        会把"渲染正常"误判成"页面空白"，所以核对 WebUI 一律走这个方法。
        """
        return self.evaluate(DEEP_TEXT_JS, timeout=timeout) or ""

    def url(self):
        return self.evaluate("location.href")

    def title(self):
        return self.evaluate("document.title")

    # -- 动 -----------------------------------------------------------
    def navigate(self, url, settle=1.5):
        self.ws.call("Page.navigate", {"url": url})
        time.sleep(settle)
        return self.url()

    def click(self, x, y):
        for typ in ("mousePressed", "mouseReleased"):
            self.ws.call("Input.dispatchMouseEvent",
                         {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1})

    def type_text(self, s):
        for ch in s:
            self.ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch})
            self.ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "text": ch})

    def press(self, key):
        code = {"Enter": "Enter", "Escape": "Escape", "Tab": "Tab",
                "Backspace": "Backspace"}.get(key, key)
        self.ws.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": code,
                                                "code": code, "windowsVirtualKeyCode": 0})
        self.ws.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": code,
                                                "code": code, "windowsVirtualKeyCode": 0})

    def wait_for(self, js_predicate, timeout=20.0, poll=0.4):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.evaluate(js_predicate):
                    return True
            except CDPError:
                pass
            time.sleep(poll)
        return False

    def wait_for_text(self, min_len=40, timeout=20.0, poll=0.4):
        """等到穿透后的整页文本达到 min_len，返回该文本（超时返回最后一次结果）。

        返回文本而不是布尔，调用方必须自己判长度——取不到内容一律按不成立处理，
        不允许"空字符串 + 绿灯"。
        """
        end = time.time() + timeout
        txt = ""
        self.last_wait_error = None
        while True:
            try:
                txt = self.deep_text()
            except Exception as exc:                              # noqa: BLE001
                # 不只 CDPError：崩溃页/切文档的瞬间 socket 读超时（R2 实测 TimeoutError）
                # 也是**暂时**的，等待循环应当重试而不是把整轮判据炸掉（D114 同口径）。
                txt = ""
                self.last_wait_error = repr(exc)[:120]
            if len(txt) >= min_len:
                return txt
            if time.time() >= end:
                return txt   # 拿不到就返回最后一次（可能为空），调用方必须判长度
            time.sleep(poll)

    # -- 证据 ---------------------------------------------------------
    def screenshot(self, path, full=False, timeout=30.0):
        res = self.ws.call("Page.captureScreenshot",
                           {"format": "png", "captureBeyondViewport": bool(full)},
                           timeout=timeout)
        data = base64.b64decode(res["data"])
        with open(path, "wb") as f:
            f.write(data)
        return len(data)

    def try_screenshot(self, path, timeout=12.0):
        """截图是**证据**不是判据：拿不到就记一行原因，绝不能把整轮判据带走。

        实测两类页面会卡住 captureScreenshot：全屏中的标签（30 秒不返回，直接把
        socket 读到超时）和刚崩掉的渲染进程（-32603 Internal error）。
        """
        try:
            return self.screenshot(path, timeout=timeout)
        except Exception as exc:                                  # noqa: BLE001
            return "SKIPPED: %s" % repr(exc)[:120]

    def close(self):
        try:
            _get_json("http://127.0.0.1:%d/json/close/%s" % (self.port, self.target_id), 5)
        except Exception:                       # noqa: BLE001
            pass
        try:
            self.ws.sock.close()
        except Exception:                       # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _unquote(s):
    # text() 里传的是 CSS 选择器字符串；允许直接写 document/body 简写
    if s in ("document.body", "body", "html"):
        return s if s != "document.body" else "body"
    return s


# --------------------------------------------------------------- 实例管理 ----
def launch(exe, profile, port, extra=None, log_path=None):
    """启动一个**独立 profile** 的窗口化实例（绝不复用用户日常 Profile，也不做机器级清理）。"""
    os.makedirs(profile, exist_ok=True)
    argv = [exe, "--user-data-dir=" + profile, "--remote-debugging-port=%d" % port,
            "--no-first-run", "--no-default-browser-check"]
    if extra:
        argv += list(extra)
    fh = open(log_path or os.devnull, "ab")
    proc = subprocess.Popen(argv, stdout=fh, stderr=fh)
    return proc


def wait_for_port(port, timeout=25.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            version_info(port, timeout=2.0)
            return True
        except Exception:                       # noqa: BLE001
            time.sleep(0.5)
    return False


def kill_instance(profile, port=None, rounds=6, wait=1.5):
    """只清理 profile 路径匹配的实例进程（D52/D55/D106 纪律：禁止机器级 Stop-Process）。"""
    key = os.path.basename(os.path.abspath(profile))
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "ForEach-Object { if ($_.CommandLine -like '*%s*') { $_.ProcessId } }" % key)
    for _ in range(rounds):
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True).stdout.split()
        pids = [x for x in out if x.isdigit()]
        if not pids:
            return 0
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "Get-Process -Id @(%s) -ErrorAction SilentlyContinue | "
                        "Stop-Process -Force" % ",".join(pids)], capture_output=True)
        time.sleep(wait)
    return len(pids)


if __name__ == "__main__":
    # 自检：能连上就说明客户端可用（量具自身也要能被证伪）
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    if not wait_for_port(port, timeout=5):
        print("SELFTEST FAIL: 端口 %d 上没有可调试实例" % port)
        sys.exit(1)
    vi = version_info(port)
    print("SELFTEST OK:", vi.get("Browser"), "|", vi.get("Protocol-Version"))
