#!/usr/bin/env python3
"""leak_probe.py - 标签页开合循环的工作集漂移探针（内存泄漏导向验证）。

原理：通过 Chrome DevTools 协议 HTTP 端点反复开/关标签页（每轮 open N 个、全部关掉），
逐轮采样整个 chrome 进程树的工作集合。真正的泄漏表现为"关闭后回落不到基线"，
所以判定看的是**每轮结束后的驻留值单调上升幅度**，不是峰值。

用法：
  python leak_probe.py --chrome <chrome.exe 路径> [--rounds 5] [--tabs 30] [--label M155]

依赖：仅标准库 + Windows 的 Get-Process（PowerShell）。
"""
import argparse
import json
import subprocess
import sys
import time
import tempfile
import urllib.request

DEV_PORT = 9333


def ps(cmd):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace")
    return p.stdout.strip()


def workset_mb():
    out = ps("$p=@(Get-Process chrome -ErrorAction SilentlyContinue); "
             "if($p.Count -eq 0){'0'}else{[math]::Round((($p|Measure-Object WorkingSet64 -Sum).Sum)/1MB,1)}")
    try:
        return float(out)
    except ValueError:
        return 0.0


def cdp(path, method="GET"):
    url = "http://127.0.0.1:%d%s" % (DEV_PORT, path)
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode().strip()
            return json.loads(body) if body else {}     # /json/close 返回空体，属正常
    except Exception as e:                        # noqa: BLE001 - 探针要容错继续
        print("   CDP %s 失败: %s" % (path, type(e).__name__))
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", required=True)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--tabs", type=int, default=30)
    ap.add_argument("--label", default="build")
    args = ap.parse_args()

    chrome = args.chrome
    profile = tempfile.mkdtemp(prefix="leakprobe_" + args.label + "_")
    proc = subprocess.Popen(
        [chrome, "--user-data-dir=" + profile,
         "--remote-debugging-port=%d" % DEV_PORT, "--no-first-run",
         "--no-default-browser-check", "--disable-background-timer-throttling",
         "--new-window", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if cdp("/json/version"):
            break
        time.sleep(1)
    else:
        print("FAIL: chrome 未响应调试端口")
        proc.kill()
        return 2

    baseline = workset_mb()
    print("%s  基线工作集 = %.1f MB（调试端口就绪）" % (args.label, baseline))
    residuals = []
    for r in range(1, args.rounds + 1):
        opened = []
        for i in range(args.tabs):
            j = cdp("/json/new?about:blank", "PUT")
            if j and j.get("id"):
                opened.append(j["id"])
        peak = workset_mb()
        for tid in opened:
            cdp("/json/close/" + tid)
        time.sleep(6)                              # 等回收/延迟释放稳定
        resid = workset_mb()
        residuals.append(resid)
        print("  第 %d/%d 轮：开 %d 关 %d  峰值 %.1f MB → 驻留 %.1f MB（相对基线 %+.1f MB）"
              % (r, args.rounds, len(opened), len(opened), peak, resid, resid - baseline))
        time.sleep(3)

    ps("Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force")
    import shutil as _sh
    _sh.rmtree(profile, ignore_errors=True)
    try:
        proc.wait(timeout=30)
    except Exception:                              # noqa: BLE001
        proc.kill()

    drift = residuals[-1] - residuals[0]
    per_round = drift / max(1, args.rounds - 1)
    verdict = "PASS — 关闭标签后驻留无单调增长" if per_round <= max(25.0, baseline * 0.01) \
        else "WARN — 每轮驻留上升 %.1f MB，需要查泄漏" % per_round
    print("\n%s 轮间漂移合计 %+.1f MB（%.1f MB/轮） → %s"
          % (args.label, drift, per_round, verdict))
    print("采样序列:", " → ".join("%.1f" % x for x in residuals), "MB")
    return 0 if per_round <= max(25.0, baseline * 0.01) else 1


if __name__ == "__main__":
    sys.exit(main())
