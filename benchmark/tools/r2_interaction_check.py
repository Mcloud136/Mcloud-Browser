#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2 交互与故障恢复实操（第4周期，2026-10-11）。

这一步要的是**真操作**，不是脚本自证：

  1. 真窗口拖拽：Win32 SendInput 从标题栏按下-移动-抬起。前置安全门：先
     SetForegroundWindow，再用 WindowFromPoint 确认那个像素上真的是**本实例的窗口**，
     否则拒绝拖拽（否则鼠标按下会拖到用户自己的窗口上——这是"量具不得污染目标"的
     物理版本）。核对窗口真的位移、拖拽期间 rAF 仍在出帧、拖完 IsHungAppWindow 为假。
     这是 SkiaGraphite 禁用决策（memory: mcloud-window-freeze-mitigation）的现场复验。
  2. 真杀 GPU 进程：只杀本实例的 --type=gpu-process（D52/D55/D106：禁止机器级
     Stop-Process chrome），验证浏览器把 GPU 进程拉回来、页面仍可执行 JS。
  3. 真杀某个标签的渲染进程：验证该标签 reload 后恢复。
  4. 标签开合回收：开 10 个标签再关掉，核对渲染进程数回落。

退出码：0=全部判据成立；1=有判据不成立；2=环境不满足（起不来 / 找不到窗口 / 拖不了）。
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes                                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import cdp                                                        # noqa: E402

DEV_EXE = os.environ.get("MCHROME_EXE",
                         r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe")
OUT = os.path.join(THOR, ".cycle4")
PORT = 9391

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# 64 位下 HWND 是指针：不设 argtypes 会被当 C int 截断，句柄直接错。
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
user32.IsHungAppWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class INPUT(ctypes.Structure):
    """Windows 的 INPUT：x64 上 sizeof 必须是 **40**（type 4 + 填充 4 + 联合体 32）。

    首版多写了一个 `pad: c_byte*40` 把联合体撑到 40，结构体变成 48，SendInput 一律返回
    0 / lasterr=87 (ERROR_INVALID_PARAMETER)，于是"拖拽没做成"被记成了产品判据不成立。
    对照实验：同一份结构体分别按 cbSize=40/48 发同一个事件 → 40 成功、48 报 87。
    """
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("ii",)
    _fields_ = [("type", wintypes.DWORD), ("ii", _U)]


assert ctypes.sizeof(INPUT) == 40, "INPUT 结构体尺寸错了（x64 应为 40），SendInput 会报 87"


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    # 字段顺序/宽度必须与 psapi.h 一致：cb 与 PageFaultCount 都是 DWORD，其后才是 SIZE_T。
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


class _EnvAbort(Exception):
    """环境不满足，后面的步骤没有意义——直接收尾并按退出码 2 报，绝不记成"通过"。"""


def send_mouse(x, y, flags):
    """按**绝对屏幕坐标**发一个鼠标事件（归一到 0..65535）。"""
    inp = INPUT()
    inp.type = 0                                                  # INPUT_MOUSE
    inp.mi = MOUSEINPUT(
        int(x * 65535 / max(1, user32.GetSystemMetrics(0) - 1)),
        int(y * 65535 / max(1, user32.GetSystemMetrics(1) - 1)),
        0, flags | MOUSEEVENTF_ABSOLUTE, 0, None)
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise RuntimeError("SendInput 返回 0（会话隔离或注入防护挡住了）")


def window_text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def find_browser_windows(pid):
    """该 PID 的可见顶层窗口。"""
    found = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, _lparam):
        pid_out = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if pid_out.value == pid and user32.IsWindowVisible(hwnd):
            text = window_text(hwnd)
            if text:
                found.append((hwnd, text))
        return True
    user32.EnumWindows(cb(enum_proc), 0)
    return found


def rect_of(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def window_at(x, y):
    pt = wintypes.POINT(x, y)
    return user32.WindowFromPoint(pt)


def private_bytes_mb(pids):
    total = 0
    for pid in pids:
        h = kernel32.OpenProcess(0x1010, False, pid)      # PROCESS_QUERY|VM_READ
        if not h:
            continue
        c = PROCESS_MEMORY_COUNTERS()
        c.cb = ctypes.sizeof(c)
        if psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            total += c.PrivateUsage
        kernel32.CloseHandle(h)
    return total // (1024 * 1024)


# -------------------------------------------------------- 本实例进程枚举 ----
def instance_procs(fingerprint):
    """[(pid, command_line)]，只含命令行带 fingerprint 的 chrome.exe。

    取不到进程一律返回空并由调用方判 FAIL——禁止"空列表当成功"。
    """
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "ForEach-Object { if ($_.CommandLine -like '*%s*') "
          "{ \"$($_.ProcessId)`t$($_.CommandLine)\" } }" % fingerprint)
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        pid, _, cl = line.partition("\t")
        if pid.strip().isdigit():
            rows.append((int(pid.strip()), cl))
    return rows


def renderers(key):
    return [p for p, c in instance_procs(key) if "--type=renderer" in c]


def safe_shot(tab, res, key, path):
    """截图只是证据，绝不能因为截不了图把整轮判据带走（崩溃页上 captureScreenshot
    会返回 -32603 Internal error，首版因此整轮崩掉）。"""
    try:
        res[key] = tab.screenshot(path)
    except Exception as exc:                                     # noqa: BLE001
        res[key] = "SKIPPED: %s" % repr(exc)[:120]


def kill_pid(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)


# 恢复实验的判据**不能依赖远端内容**。实测教训：example.com 正在改版，不同 CDN 节点
# 分别返回"多语种 917 字符版"和"只有 <p> 的 156 字符版"（旧版有 <h1>Example Domain</h1>，
# 新版连 h1 都没有、字符串只活在 <title> 里）——拿正文里的 "Example Domain" 当标记，
# 在改版后会永久判"页面没渲染"，而错误页同样有几十个字，反过来又可能把没恢复判成恢复。
# 所以：正向标记写在自己的本地文件里；网络可达性单独用 document.title 判。
PROBE_HTML = ("<!doctype html><meta charset=utf-8><title>mcloud-r2-probe</title>"
              "<h1>MCLOUD-R2-PROBE-OK</h1>"
              "<p>这个页面只用来确认渲染进程还活着、合成器还在出帧，内容必须完全可控。</p>"
              "<script>window.__n=0;setInterval(function(){window.__n++},100)</script>")
PROBE_MARKER = "MCLOUD-R2-PROBE-OK"
NET_URL = "https://www.example.com"
NET_TITLE = "Example Domain"          # 新旧两版都在 <title> 里，比正文稳
ERROR_PAGE_MARKERS = ("无法访问此网站", "该网页无法正常运作", "ERR_", "Aw, Snap",
                      "This site can’t be reached", "Problem loading page")


def page_is_real(text):
    """判"这是我们的探针页"，并且显式排除错误页文案。

    传**快照文本**而不是 tab 对象：wait_for 之后再单独 evaluate 会跨过导航提交点，
    读到新文档的空壳（R2 首版就是这么把一次正常加载读成 len=0 的）。
    """
    hit_err = [m for m in ERROR_PAGE_MARKERS if m in text]
    return (PROBE_MARKER in text and not hit_err), "len=%d err_markers=%s" % (len(text), hit_err)


# ------------------------------------------------------------------ 步骤 ----
def step_drag(tab, hwnd, res):
    l, t, r, b = rect_of(hwnd)
    before = (l, t)
    cx, cy = (l + r) // 2, t + 12                          # 标题栏中线
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    l, t, r, b = rect_of(hwnd)
    cx, cy = (l + r) // 2, t + 12
    under = window_at(cx, cy)
    if under != hwnd:
        # 那个像素不是本实例的窗口（被遮挡/被别的程序占着）——绝不发鼠标按下。
        res["drag_refused_reason"] = "WindowFromPoint=%s 不是本实例窗口 %s" % (under, hwnd)
        return False
    cur = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(cur))
    tab.evaluate("window.__f=0;(function loop(){window.__f++;requestAnimationFrame(loop)})()")
    try:
        send_mouse(cx, cy, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.15)
        for i in range(1, 13):
            send_mouse(cx + i * 12, cy + i * 6, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN)
            time.sleep(0.04)
        res["raf_frames_during_drag"] = tab.evaluate("window.__f")
        send_mouse(cx + 144, cy + 72, MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTUP)
    finally:
        user32.SetCursorPos(cur.x, cur.y)                  # 把指针还给用户
    time.sleep(0.6)
    after = rect_of(hwnd)[:2]
    res["drag_before"] = list(before)
    res["drag_after"] = list(after)
    res["drag_moved_px"] = [after[0] - before[0], after[1] - before[1]]
    res["drag_moved"] = abs(after[0] - before[0]) >= 40 and abs(after[1] - before[1]) >= 20
    res["raf_alive_during_drag"] = bool(res.get("raf_frames_during_drag", 0) > 5)
    res["window_hung_after_drag"] = bool(user32.IsHungAppWindow(hwnd))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEV_EXE)
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    res = {}
    if not os.path.isfile(args.exe):
        print("FAIL: 找不到 %s" % args.exe)
        return 2
    os.makedirs(OUT, exist_ok=True)
    probe_html = os.path.join(OUT, "r2_probe.html")
    with open(probe_html, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PROBE_HTML)
    probe_url = "file:///" + probe_html.replace("\\", "/")
    prof = os.path.join(OUT, "r2-prof")
    key = os.path.basename(prof)
    proc = cdp.launch(args.exe, prof, args.port)
    env_fail = None
    try:
        if not cdp.wait_for_port(args.port, timeout=40):
            env_fail = "调试端口没起来"
        time.sleep(3)
        procs = instance_procs(key)
        res["instance_proc_count"] = len(procs)
        if env_fail is None and not procs:
            env_fail = "按 profile 指纹 %r 取不到本实例进程" % key
        wins = []
        if env_fail is None:
            wins = find_browser_windows(proc.pid)
            res["windows"] = [[h, t] for h, t in wins]
            if not wins:
                env_fail = "找不到本实例的可见顶层窗口（chrome.exe 桩进程可能不持有窗口）"
        if env_fail is not None:
            raise _EnvAbort(env_fail)

        hwnd = wins[0][0]
        tab = cdp.Tab(port=args.port, url="about:blank")
        tab.navigate(probe_url)
        ok_probe, probe_diag = page_is_real(tab.wait_for_text(len(PROBE_MARKER), timeout=15))
        res["probe_page"] = probe_diag
        if not ok_probe:
            raise _EnvAbort("探针页没渲染出来，拖拽/rAF 判据无从谈起（%s）" % probe_diag)

        # --- 1. 真拖拽 ---
        try:
            res["drag_attempted"] = step_drag(tab, hwnd, res)
        except Exception as exc:                                 # noqa: BLE001
            res["drag_error"] = repr(exc)
            res["drag_attempted"] = False
        safe_shot(tab, res, "screenshot_after_drag", os.path.join(OUT, "r2_after_drag.png"))

        # --- 2. 杀 GPU 进程 ---
        gpu = [(p, c) for p, c in instance_procs(key) if "--type=gpu-process" in c]
        res["gpu_procs_before_kill"] = len(gpu)
        if not gpu:
            res["gpu_recovered"] = False
            res["gpu_note"] = "本实例没有 gpu-process，恢复实验无法进行（判 FAIL，不给绿）"
        else:
            kill_pid(gpu[0][0])
            deadline, back = time.time() + 20, 0
            while time.time() < deadline:
                time.sleep(1.0)
                back = len([1 for p, c in instance_procs(key) if "--type=gpu-process" in c])
                if back:
                    break
            res["gpu_procs_after_recovery"] = back
            res["gpu_recovered"] = back > 0
            try:
                tab.navigate(probe_url)
                ok_page, diag = page_is_real(tab.wait_for_text(len(PROBE_MARKER), timeout=20))
                res["page_alive_after_gpu_kill"] = ok_page
                res["page_alive_diag"] = diag
            except Exception as exc:                             # noqa: BLE001
                res["page_alive_after_gpu_kill"] = False
                res["page_alive_error"] = repr(exc)
            # 网络栈在 GPU 进程被杀之后仍要能用：这条只看 title（新旧版都稳定）
            try:
                tab.navigate(NET_URL)
                tab.wait_for("document.title === %r" % NET_TITLE, timeout=25)
                res["network_alive_after_gpu_kill"] = tab.title() == NET_TITLE
            except Exception as exc:                             # noqa: BLE001
                res["network_alive_after_gpu_kill"] = False
                res["network_diag"] = repr(exc)
            safe_shot(tab, res, "screenshot_after_gpu_kill", os.path.join(OUT, "r2_after_gpu_kill.png"))

        # --- 3. 杀"承载被测标签的那个"渲染进程 ---
        # M155 的 CDP 不再给 processId（实测 Target.getTargetInfo 的 targetInfo 里
        # 根本没有这个字段），所以不能"先定位再杀"。改成**闭环自证**：逐个杀本实例的
        # 渲染进程，每杀一个就看被测标签有没有真的进崩溃态——只有它真的崩了，
        # 才说明"被杀的就是它的渲染进程"，实验前提由结果证明而不是由猜测声明。
        t3 = cdp.Tab(port=args.port, url=probe_url)
        pre_ok, pre_diag = page_is_real(t3.wait_for_text(len(PROBE_MARKER), timeout=25))
        res["probe_before_kill"] = pre_diag
        if not pre_ok:
            raise _EnvAbort("探针页未真正渲染（%s）" % pre_diag)
        victims = []
        crashed = ""
        for pid in renderers(key):
            kill_pid(pid)
            victims.append(pid)
            time.sleep(2.5)
            try:
                crashed = t3.deep_text()
            except Exception as exc:                             # noqa: BLE001
                crashed = ""
                res["kill_probe_error"] = repr(exc)
            if len(crashed) == 0 or any(m in crashed for m in ERROR_PAGE_MARKERS):
                break
        res["renderer_victim_pids"] = victims
        res["after_renderer_kill_len"] = len(crashed)
        res["crash_ui_shown"] = (len(crashed) == 0
                                 or any(m in crashed for m in ERROR_PAGE_MARKERS))
        if not res["crash_ui_shown"]:
            res["env_fail"] = "杀遍了本实例 %d 个渲染进程，被测标签都没崩——它其实没有自己的进程" % len(victims)
            raise _EnvAbort(res["env_fail"])
        safe_shot(t3, res, "screenshot_after_renderer_kill", os.path.join(OUT, "r2_after_renderer_kill.png"))
        try:
            t3.navigate(probe_url)
            res["renderer_recovered"], res["renderer_reload_diag"] = page_is_real(
                t3.wait_for_text(len(PROBE_MARKER), timeout=25))
        except Exception as exc:                                 # noqa: BLE001
            res["renderer_recovered"] = False
            res["renderer_reload_error"] = repr(exc)
        t3.close()

        # --- 4. 标签开合回收 ---
        # Chrome 关标签后不会立刻退渲染进程（keep-alive/可复用空闲进程），10 秒窗口下
        # "没回落"是常态，不能据此判泄漏；这里量**衰减曲线**，最长等 150 秒。
        base = len(renderers(key))
        tabs = []
        for i in range(10):
            try:
                tabs.append(cdp.Tab(port=args.port, url=probe_url + "&i=%d" % i))
            except Exception as exc:                             # noqa: BLE001
                res["tab_open_error_%d" % i] = repr(exc)
        time.sleep(6)
        res["renderers_base"] = base
        res["renderers_peak"] = len(renderers(key))
        res["private_mb_peak"] = private_bytes_mb([p for p, _c in instance_procs(key)])
        for t in tabs:
            t.close()
        curve = []
        deadline = time.time() + 150
        while True:
            n = len(renderers(key))
            curve.append([int(time.time() - (deadline - 150)), n])
            if n <= base + 2 or time.time() >= deadline:
                break
            time.sleep(10)
        res["renderer_decay_curve_sec_n"] = curve
        res["renderers_after_close"] = curve[-1][1]
        res["reclaim_waited_sec"] = curve[-1][0]
        res["private_mb_after_close"] = private_bytes_mb([p for p, _c in instance_procs(key)])
        # 允许 +2：SpareRendererForSitePerProcess 会留一个备用渲染进程，属预期驻留
        res["tab_churn_reclaimed"] = curve[-1][1] <= base + 2
        res["window_hung_final"] = bool(user32.IsHungAppWindow(hwnd))
        tab.close()
    except _EnvAbort as exc:
        res["env_fail"] = str(exc)
    except Exception as exc:                                     # noqa: BLE001
        # 任何一步的意外异常都不许吞掉整轮的判据输出：记成环境失败，照常打印。
        import traceback
        res["env_fail"] = "unexpected: %r" % exc
        res["traceback"] = traceback.format_exc()[-900:]
    finally:
        left = cdp.kill_instance(prof, port=args.port)
        res["leftover_procs"] = left
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % prof],
                       capture_output=True)
        try:
            proc.wait(timeout=20)
        except Exception:                                        # noqa: BLE001
            proc.kill()

    print(json.dumps(res, ensure_ascii=False, indent=2))
    if "env_fail" in res:
        return 2
    hard = []
    for k in ("drag_attempted", "drag_moved", "raf_alive_during_drag", "gpu_recovered",
              "page_alive_after_gpu_kill", "network_alive_after_gpu_kill",
              "renderer_recovered", "tab_churn_reclaimed"):
        if not res.get(k):
            hard.append(k)
    if res.get("window_hung_after_drag") or res.get("window_hung_final"):
        hard.append("window_hung(IsHungAppWindow=True)")
    if res.get("leftover_procs"):
        hard.append("leftover_procs=%s" % res["leftover_procs"])
    print("\nFAILED-CHECKS: %s" % (hard or "none"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
