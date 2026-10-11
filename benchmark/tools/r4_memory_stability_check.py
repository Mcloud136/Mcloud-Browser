#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R4 内存 / 句柄 / 线程 / 退出残留实操（第4周期，2026-10-11）。

针对"长跑会不会涨、句柄会不会漏、关窗口会不会留尸"三件事，全部按**实例**取数
（D52/D55/D106：只认本次 --user-data-dir 的进程，绝不机器级统计或清理）：

  1. 每 10 秒采一次：本实例每个进程的 类型 / PrivateBytes / HandleCount / ThreadCount；
  2. 真做三轮标签开合（每轮 15 个标签，含 1440p 本地视频、chrome://gpu、真实站点）；
  3. 判据用**趋势**而不是单点：浏览器进程句柄数的"后半段最小值 − 前半段最大值"才是
     泄漏信号，单点峰值只反映当时开了多少标签；
  4. 关窗前后再探一次响应性（evaluate 必须还能返回，防"能计数但不能交互"）；
  5. `Browser.close` 之后必须**全部退出**：残留 PID 直接判 FAIL（孤儿进程会锁住
     out/mcloud 的 DLL，实测让链接失败，见 D71）。

阈值取自 memory: benchmark-noise-floors（泄漏判定的噪声带 ±8.9 MB），并留足余量：
本测试判的是"数量级上的失控"，不是 8 MB 级别的抖动。
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import cdp                                                        # noqa: E402

DEV_EXE = os.environ.get("MCHROME_EXE",
                         r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe")
OUT = os.path.join(THOR, ".cycle4")
PORT = 9431
LOCAL_VIDEO = r"C:\Users\Administrator\Videos\2026-10-07 14-27-54.mp4"


def proc_stats(fingerprint):
    """[(pid, ppid, handles, threads, cmdline)]，只含本实例。"""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "ForEach-Object { if ($_.CommandLine -like '*%s*') "
          "{ \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.HandleCount)"
          "`t$($_.ThreadCount)`t$($_.CommandLine)\" } }" % fingerprint)
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[0].strip().isdigit():
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]),
                         parts[4] if len(parts) > 4 else ""))
    return rows


def proc_types(rows):
    kinds = {}
    for pid, _pp, _h, _t, cl in rows:
        if "--type=" in cl:
            k = cl.split("--type=")[1].split()[0]
        elif "--plugin" in cl:
            k = "plugin"
        else:
            k = "browser"
        kinds.setdefault(k, []).append(pid)
    return kinds


def private_mb(pids):
    import ctypes
    import ctypes.wintypes
    k32 = ctypes.windll.kernel32
    ps = ctypes.windll.psapi

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.wintypes.DWORD), ("PageFaultCount", ctypes.wintypes.DWORD)] + \
                   [(n, ctypes.c_size_t) for n in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                        "PrivateUsage")]
    total = 0
    for pid in pids:
        h = k32.OpenProcess(0x1010, False, pid)
        if not h:
            continue
        c = PMC()
        c.cb = ctypes.sizeof(c)
        if ps.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            total += c.PrivateUsage
        k32.CloseHandle(h)
    return total // (1024 * 1024)


def sample(key, log):
    rows = proc_stats(key)
    kinds = proc_types(rows)
    br = [p for p in kinds.get("browser", [])]
    entry = {"t": round(log["elapsed"](), 1),
             "procs": len(rows),
             "browser_handles": max([h for p, _pp, h, _t, _c in rows if p in br], default=0),
             "browser_threads": max([t for p, _pp, _h, t, _c in rows if p in br], default=0),
             "private_mb": private_mb([p for p, _a, _b, _c, _d in rows]),
             "kinds": {k: len(v) for k, v in sorted(kinds.items())}}
    log["samples"].append(entry)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEV_EXE)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--tabs", type=int, default=15)
    ap.add_argument("--extra", default="",
                    help="附加给启动命令行的开关（A/B 用）。注意：用户条目在合并时排在"
                         "内置之前，所以 --disable-features=X 能真的压过内置的 enable（D21）")
    args = ap.parse_args()
    res = {}
    if not os.path.isfile(args.exe):
        print("FAIL: 找不到 %s" % args.exe)
        return 2
    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(OUT, "r4-prof")
    key = os.path.basename(prof)
    t0 = time.time()
    log = {"samples": [], "elapsed": lambda: time.time() - t0}
    urls = ["https://www.example.com", "chrome://gpu", "chrome://version",
            "chrome://settings"]
    if os.path.isfile(LOCAL_VIDEO):
        urls.append("file:///" + LOCAL_VIDEO.replace("\\", "/").replace(" ", "%20"))
    extra = [x for x in args.extra.split() if x]
    res["extra_flags"] = extra
    proc = cdp.launch(args.exe, prof, args.port, extra=extra)
    try:
        if not cdp.wait_for_port(args.port, timeout=40):
            print(json.dumps({"env_fail": "端口没起来"}, ensure_ascii=False))
            return 2
        time.sleep(4)
        if not proc_stats(key):
            print(json.dumps({"env_fail": "按指纹取不到本实例进程"}, ensure_ascii=False))
            return 2
        sample(key, log)
        res["baseline"] = log["samples"][0]
        # 先开一个可交互标签，作为"还活着"的探针
        probe = cdp.Tab(port=args.port, url="about:blank")
        probe.navigate("chrome://version")
        probe.wait_for_text(500, timeout=25)

        rounds = []
        for r in range(args.rounds):
            tabs = []
            for i in range(args.tabs):
                try:
                    tabs.append(cdp.Tab(port=args.port, url="%s#%d-%d" % (urls[i % len(urls)], r, i)))
                except Exception as exc:                         # noqa: BLE001
                    res.setdefault("tab_open_errors", []).append(repr(exc)[:80])
            for _ in range(3):
                time.sleep(4)
                sample(key, log)
            peak = log["samples"][-3:]          # 开着 15 个标签时的三次采样
            for t in tabs:
                t.close()
            time.sleep(8)
            sample(key, log)
            trough = log["samples"][-1]
            rounds.append({"peak_procs": max(x["procs"] for x in peak),
                           "peak_handles": max(x["browser_handles"] for x in peak),
                           "peak_private_mb": max(x["private_mb"] for x in peak),
                           "trough_procs": trough["procs"],
                           "trough_handles": trough["browser_handles"],
                           "trough_private_mb": trough["private_mb"]})
        res["rounds"] = rounds

        # 关窗前响应性
        try:
            probe.navigate("chrome://version")
            alive_txt = probe.wait_for_text(500, timeout=20)
            res["responsive_before_close"] = (len(alive_txt) > 500
                                              and not cdp.is_error_page(alive_txt))
        except Exception as exc:                                 # noqa: BLE001
            res["responsive_before_close"] = False
            res["responsive_error"] = repr(exc)[:150]
        probe.close()
        bws = cdp.WSClient(cdp.browser_endpoint(args.port))
        try:
            bws.call("Browser.close", timeout=15)
        except Exception as exc:                                 # noqa: BLE001
            res["browser_close_call"] = repr(exc)[:120]   # 正常：进程会立刻断链
        bws.sock.close()
        deadline = time.time() + 25
        left = proc_stats(key)
        while left and time.time() < deadline:
            time.sleep(2)
            left = proc_stats(key)
        res["residue_procs_after_close"] = len(left)
        res["exit_clean"] = len(left) == 0
        try:
            proc.wait(timeout=20)
        except Exception:                                        # noqa: BLE001
            pass
    finally:
        res["leftover_procs"] = cdp.kill_instance(prof, port=args.port)
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % prof],
                       capture_output=True)
        try:
            proc.wait(timeout=20)
        except Exception:                                        # noqa: BLE001
            proc.kill()

    samples = log["samples"]
    res["samples"] = samples
    rounds = res.get("rounds") or []
    if rounds:
        # 泄漏的判据是**跨轮不累积**，不是"关掉之后立刻回到基线"：Chrome 关标签后会把
        # 空闲渲染进程留一小段时间复用（R2 实测 11→4 约 11 秒），所以只看单点回落会
        # 把正常复用误判成泄漏；反过来，如果每轮的峰/谷都在往上爬，那才是真漏。
        # 首版判据写的是"后半段最大值 <= 基线+6"，拿"开着 15 个标签时的峰值"去比
        # "基线 9 个进程"，数学上永远不可能成立（假红）。
        first, last = rounds[0], rounds[-1]
        res["accumulation"] = {
            "peak_procs": [x["peak_procs"] for x in rounds],
            "trough_procs": [x["trough_procs"] for x in rounds],
            "peak_handles": [x["peak_handles"] for x in rounds],
            "trough_handles": [x["trough_handles"] for x in rounds],
            "trough_private_mb": [x["trough_private_mb"] for x in rounds],
        }
        res["no_proc_accumulation"] = last["peak_procs"] <= first["peak_procs"] + 2
        res["no_handle_accumulation"] = last["trough_handles"] <= first["trough_handles"] + 150
        # ±8.9 MB 是本机泄漏判定的噪声带（memory: benchmark-noise-floors），阈值放到 120 MB
        res["no_memory_accumulation"] = (last["trough_private_mb"]
                                         <= first["trough_private_mb"] + 120)
        res["trough_returns_near_baseline"] = last["trough_procs"] <= res["baseline"]["procs"] + 12
    hard = [k for k in ("no_proc_accumulation", "no_handle_accumulation",
                        "no_memory_accumulation", "trough_returns_near_baseline",
                        "responsive_before_close", "exit_clean") if not res.get(k)]
    if res.get("leftover_procs"):
        hard.append("leftover_procs")
    res.pop("handle_trend", None)
    print(json.dumps({k: v for k, v in res.items() if k != "samples"}, ensure_ascii=False, indent=2))
    print("\nsamples (t/procs/handles/threads/privateMB):")
    for s in samples:
        print("  %6.1fs  procs=%-3s handles=%-5s threads=%-4s private=%-5sMB  %s"
              % (s["t"], s["procs"], s["browser_handles"], s["browser_threads"],
                 s["private_mb"], s["kinds"]))
    print("\nFAILED-CHECKS: %s" % (hard or "none"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
