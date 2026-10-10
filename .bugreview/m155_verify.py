#!/usr/bin/env python3
"""m155_verify.py - M155 构建后的一站式验收（性能 / 内存安全 / GPU 三条导向）。

依次跑：D47 门禁（155 树版）→ check_features(155) → flag_stability[155,156] →
A6 子进程命令行 → K1 → K2 → leak_probe(155 vs 151 A/B)。
每步都记录退出码与关键数值，最后给一张汇总表；任一硬门禁失败即整体 FAIL。

用法：python .bugreview/m155_verify.py [--skip-kpi]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

PY = sys.executable
THOR = r"D:\wxmuma\thorium"
SRC151 = r"D:\wxmuma\chromium-src\src"
SRC155 = r"D:\wxmuma\chromium-src-155\src"
OUT155 = os.path.join(SRC155, "out", "mcloud")
REPO_FLAGS = os.path.join(THOR, "mcloud_flags.txt")
R3_RECORD = os.path.join(THOR, "docs", "dev-logs", "M151-r3-benchmark.md")


def run(cmd, shell=False, timeout=3600):
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                       timeout=timeout, shell=shell)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, re.sub(r"[^\x20-\x7e\n]", "", out)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


def scan(path, needles):
    hit = {n: False for n in needles}
    if not os.path.isfile(path):
        return hit
    with open(path, "rb") as f:
        tail = b""
        while True:
            buf = f.read(1 << 22)
            if not buf:
                break
            data = tail + buf
            for n in needles:
                if n in data:
                    hit[n] = True
            tail = data[-256:]
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-kpi", action="store_true")
    args = ap.parse_args()
    results = []

    def rec(name, ok, detail=""):
        results.append((name, "PASS" if ok else "FAIL", detail))
        print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))

    # 0. 构建产物存在且新鲜
    dll = os.path.join(OUT155, "chrome.dll")
    exe = os.path.join(OUT155, "chrome.exe")
    inst = os.path.join(OUT155, "mini_installer.exe")
    z7 = os.path.join(OUT155, "chrome.7z")
    ok = all(os.path.isfile(p) for p in (dll, exe, inst, z7))
    rec("155 构建产物齐备", ok,
        "chrome.dll=%s mini_installer=%s" % (
            os.path.getmtime(dll) if ok else "-", os.path.getmtime(inst) if ok else "-"))
    if not ok:
        print("产物不全，后续步骤无意义")
        return 1

    # 1. 加载器确实在链接进去的 dll 里
    hits = scan(dll, [b"command-line budget", b"built-in features skipped",
                      b"mcloud_flags.txt", b"bug-review D40"])
    rec("dll 含加载器 v5 证据", all(hits.values()), str({k.decode()[:18]: v for k, v in hits.items()}))

    # 2. 打包输入一致性（flags 与 chrome.release）
    deployed = os.path.join(OUT155, "mcloud_flags.txt")
    same = os.path.isfile(deployed) and sha(deployed) == sha(REPO_FLAGS)
    rel = io_read(os.path.join(SRC155, "chrome", "installer", "mini_installer", "chrome.release"))
    rec("out/mcloud flags 与仓库一致", same)
    rec("155 树 chrome.release 已登记标志文件", "mcloud_flags.txt: %(ChromeDir)s\\" in rel)
    z7needles = [b"mcloud_flags.txt", "[r3 清理 2026-10-10".encode(),
                 b"SpareRendererForSitePerProcess", b"SkiaGraphite"]
    z7hits = scan(z7, z7needles)
    rec("chrome.7z 载荷含标志文件与 r3 清理标记",
        z7hits[b"mcloud_flags.txt"] and z7hits["[r3 清理 2026-10-10".encode()],
        " ".join(n.decode("utf-8", "replace")[:14] for n in z7needles if z7hits[n]))

    # 3. feature 存活性（155）
    rc, out = run([PY, os.path.join(THOR, "benchmark", "tools", "check_features.py"),
                   "--flags", REPO_FLAGS, "--src", SRC155], timeout=1800)
    m = re.search(r"\[OK\]\s+(\d+)\s*/\s*(\d+)", out)
    rec("check_features(155) 全部存活", rc == 0 and bool(m) and m.group(1) == m.group(2),
        "%s/%s" % (m.group(1), m.group(2)) if m else out[-160:])

    # 4. 跨版本稳定性（基线 155，目标 156）
    rc, out = run([PY, os.path.join(THOR, ".bugreview", "flag_stability.py"),
                   "155.0.8059.40", "156.0.8078.12", "156.0.8078.12"], timeout=1800)
    rec("flag_stability [155,156]", rc == 0, out.splitlines()[-1] if out else "")

    # 5. A6：内置 flags 进入子进程命令行
    rc, out = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", os.path.join(THOR, "benchmark", "tools", "verify_builtin_flags.ps1"),
                   "-ChromeExe", exe], timeout=900)
    nprobe = len(re.findall(r"\[OK\]", out))
    rec("A6 子进程命令行可见内置 feature", rc == 0, "探针命中 %d 项" % nprobe)

    # 6. K1 / K2（同方法与 r3 留痕对比）
    if not args.skip_kpi:
        rc, out = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                       "-File", os.path.join(THOR, "benchmark", "bench_startup.ps1"),
                       "-ChromeExe", exe, "-Runs", "5"], timeout=1800)
        k1 = re.findall(r"(\d+) ms", out)
        rec("K1 冷启动（155）", rc == 0 and bool(k1), out.strip().splitlines()[-2] if k1 else out[-160:])
        rc, out = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                       "-File", os.path.join(THOR, "benchmark", "bench_memory.ps1"),
                       "-ChromeExe", exe], timeout=1800)
        k2 = re.search(r"中位数）?:?\s*([\d.]+) MB", out) or re.search(r"([\d.]+) MB", out)
        proc = re.findall(r"进程数 (\d+)", out)
        rec("K2 内存（155，需与 r3 同进程数比较）", rc == 0 and bool(k2),
            "%s MB / 进程数 %s（r3 记录见 %s）" % (k2.group(1) if k2 else "?",
                                                 proc[-1] if proc else "?",
                                                 os.path.basename(R3_RECORD)))
        # 7. 泄漏探针：155 与 151 同参数 A/B
        for tag, e in (("M155", exe), ("M151", os.path.join(SRC151, "out", "mcloud", "chrome.exe"))):
            if not os.path.isfile(e):
                continue
            rc, out = run([PY, os.path.join(THOR, "benchmark", "tools", "leak_probe.py"),
                           "--chrome", e, "--rounds", "4", "--tabs", "25", "--label", tag],
                          timeout=2400)
            last = [l for l in out.splitlines() if "轮间漂移" in l]
            rec("leak_probe %s" % tag, rc == 0, last[-1].strip() if last else out[-200:])
    else:
        print("(--skip-kpi：K1/K2/leak_probe 未跑)")

    print("\n=== 汇总 ===")
    bad = [r for r in results if r[1] == "FAIL"]
    for name, st, detail in results:
        print("  %-46s %-5s %s" % (name[:46], st, detail[:90]))
    print("\n总判定:", "PASS" if not bad else "FAIL（%d 项）" % len(bad))
    return 0 if not bad else 1


def io_read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
