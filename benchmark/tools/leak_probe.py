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
import os
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.request

DEV_PORT = 9333


def ps(cmd, timeout=120):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace",
                       timeout=timeout)
    return p.stdout.strip()


# ── 实例界定（缺陷 D52）────────────────────────────────────────────
# 旧实现按进程名汇总 `Get-Process chrome`，会把**机器上所有 chrome 进程**算进来：
# 用户自己开着的浏览器、上一轮没清干净的实例、以及并行运行的另一个探针，全部计入 K2/驻留，
# 产出的内存数字与被测实例无关——这正是 A/B 跨轮散布 ±27 MB 的主要来源之一。
# 现改为：以本次启动使用的 --user-data-dir 为指纹，用子进程命令行筛选出**属于本实例**的 PID 集合。
def _key_of(udd):
    """实例指纹 = profile 目录的叶子名（每次 mkdtemp 唯一）。

    绝不用完整路径匹配：Python 的 TEMP 变量可能以 8.3 短名形式出现，
    而 chrome 命令行里是长名（或反之），子串匹配会整批落空 —— 结果是
    采到 0 进程 0 MB 却照样打印 PASS。本轮修 D52 时就是这样引入、
    又当场被回归测试抓到，所以把这个坑写死在函数里。
    """
    return os.path.basename(udd.rstrip("/\\"))


def _filter_cmd(udd):
    return ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Where-Object { $_.CommandLine -like '*%s*' } | "
            "ForEach-Object { $_.ProcessId }" % _key_of(udd))


def instance_pids(udd):
    out = ps(_filter_cmd(udd))
    pids = [int(x) for x in out.split() if x.strip().isdigit()]
    return pids


def workset_mb(udd):
    pids = instance_pids(udd)
    if not pids:
        return 0.0, 0
    # PowerShell 里 `double + '|'+…` 会抛"无法将值 '|' 转换为 System.Double"
    # （+ 的左操作数是数字时右操作数会被强制转数字），必须用 -f 格式化。
    # 本函数第一版踩了这个坑：表达式静默失败 → stdout 为空 → 解析成 0.0 MB / 0 进程。
    out = ps("$ids=%s; $p=@(Get-Process -Id $ids -ErrorAction SilentlyContinue); "
             "if($p.Count -eq 0){"
             "'0|0'}else{"
             "('{0}|{1}' -f [math]::Round((($p|Measure-Object WorkingSet64 -Sum).Sum)/1MB,1), "
             "$p.Count)}" % ",".join(str(x) for x in pids))
    try:
        mb, n = out.split("|")
        return float(mb), int(n)
    except ValueError:
        return 0.0, 0


def stop_instance(udd, proc):
    """只终止本实例的进程；绝不使用机器级的 `Get-Process chrome | Stop-Process`。

    必须**循环杀到干净**（缺陷 D71）：一次性杀 PID 会留下尾巴——浏览器被杀时
    crashpad-handler 可能正在重启，残余进程会继续持有 out 目录里的 DLL 句柄，
    下一轮链接就以 `lld-link: failed to write output './dxcompiler.dll': permission denied`
    失败（本轮实测：9 个孤儿进程直接把 51,296 步的重编打断）。
    """
    key = _key_of(udd)
    for _attempt in range(5):
        pids = instance_pids(udd)
        if not pids:
            break
        ps("Get-Process -Id %s -ErrorAction SilentlyContinue | "
           "Stop-Process -Force -ErrorAction SilentlyContinue" % ",".join(str(x) for x in pids))
        time.sleep(2)
    if proc is not None and proc.poll() is None:
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
    left = instance_pids(udd)
    if left:
        # 不许静默：残留进程会锁文件、也会污染下一次测量的指纹
        print("WARN: 本实例仍有 %d 个进程未退出（PID %s）——后续编译可能被文件锁打断"
              % (len(left), left[:8]))
    return not left



def cdp(path, method="GET"):
    url = "http://127.0.0.1:%d%s" % (DEV_PORT, path)
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode().strip()
            if not body:
                return {}                             # /json/close 可能返回空体
            try:
                return json.loads(body)
            except ValueError:
                return {"raw": body}                  # M155 的 /json/close 回纯文本，
                #  旧实现把它当异常刷屏，真正的失败信号反而被淹没了
    except Exception as e:                        # noqa: BLE001 - 探针要容错继续
        print("   CDP %s 失败: %s" % (path, type(e).__name__))
        return None


def free_port():
    """为本次实例挑一个空闲调试端口（缺陷 D53：旧实现写死 9333，
    与另一个实例/上一轮残留实例争抢时会连到**别人的浏览器**，采到的数字与被测对象无关）。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", required=True)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--tabs", type=int, default=30)
    ap.add_argument("--label", default="build")
    args = ap.parse_args()
    if args.rounds < 2:
        print("rounds 至少 2（漂移需要首末两点），实际 %d" % args.rounds)
        return 2

    global DEV_PORT
    DEV_PORT = free_port()
    chrome = args.chrome
    profile = tempfile.mkdtemp(prefix="leakprobe_" + args.label + "_")
    residuals = []
    code = 1
    proc = None
    try:
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
            stop_instance(profile, proc)
            return 2

        baseline, nb = workset_mb(profile)
        print("%s  基线工作集 = %.1f MB（本实例 %d 个进程，调试端口 %d）"
              % (args.label, baseline, nb, DEV_PORT))
        if nb == 0:
            # 采不到任何本实例进程 = 指纹/查询失效，绝不能继续输出 0.0 MB 的"PASS"
            print("FAIL: 实例进程筛选为 0（指纹或 WMI 查询失效），本次结果不可信")
            stop_instance(profile, proc)
            return 2
        for r in range(1, args.rounds + 1):
            opened = []
            for _i in range(args.tabs):
                j = cdp("/json/new?about:blank", "PUT")
                if j and j.get("id"):
                    opened.append(j["id"])
            peak, np_ = workset_mb(profile)
            for tid in opened:
                cdp("/json/close/" + tid)
            time.sleep(6)                              # 等回收/延迟释放稳定
            resid, nr = workset_mb(profile)
            residuals.append(resid)
            print("  第 %d/%d 轮：开 %d 关 %d  峰值 %.1f MB（%d 进程）→ 驻留 %.1f MB"
                  "（相对基线 %+.1f MB，当前 %d 进程）"
                  % (r, args.rounds, len(opened), len(opened), peak, np_, resid,
                     resid - baseline, nr))
            time.sleep(3)

        drift = residuals[-1] - residuals[0]
        per_round = drift / max(1, args.rounds - 1)
        limit = max(25.0, baseline * 0.01)
        verdict = "PASS — 关闭标签后驻留无单调增长" if per_round <= limit \
            else "WARN — 每轮驻留上升 %.1f MB，需要查泄漏" % per_round
        print("\n%s 轮间漂移合计 %+.1f MB（%.1f MB/轮） → %s"
              % (args.label, drift, per_round, verdict))
        print("采样序列:", " → ".join("%.1f" % x for x in residuals), "MB")
        code = 0 if per_round <= limit else 1
    finally:
        stop_instance(profile, proc)
        shutil.rmtree(profile, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
