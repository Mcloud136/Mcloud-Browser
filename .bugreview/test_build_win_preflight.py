#!/usr/bin/env python3
"""test_build_win_preflight.py - 验证 build_win.py 的 PGO 预检与漂移比对（缺陷 D144）。

Red  → 用指向不存在文件的 pgo_data_path 造一份 args.gn，预检必须以 111 退出并说清根因；
Green→ 用真实构建树的 args.gn，预检必须通过并报告"逐项一致"。
不触碰任何发布产物目录：全部在临时目录里造样本。
"""
import os
import subprocess
import sys
import tempfile

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_WIN = os.path.join(THOR, "win_scripts", "build_win.py")
TEMPLATE = os.path.join(THOR, "win_args_mcloud.gn")
REAL_ARGS = r"D:\wxmuma\chromium-src-155\src\out\mcloud\args.gn"

# 只跑预检、不跑 autoninja 的桩：把 build_win.py 的源码在 preflight 之后截断
STUB_TAIL = "\nprint('PREFLIGHT_DONE')\n"


def run_preflight(args_dir, label):
    """在隔离目录里 import build_win 的预检逻辑并执行，返回 (rc, stdout+stderr)。"""
    with open(BUILD_WIN, "r", encoding="utf-8") as fh:
        src = fh.read()
    marker = "# Change directory and run build commands"
    if marker not in src:
        print("FAIL: build_win.py 里找不到预检挂载点标记，测试自身失效")
        return 99, ""
    head = src.split(marker)[0]
    stub = head + (
        "import sys as _s\n"
        "preflight_args(_s.argv[1], template=_s.argv[2])\n" + STUB_TAIL
    )
    stub_path = os.path.join(args_dir, "_preflight_stub.py")
    with open(stub_path, "w", encoding="utf-8") as fh:
        fh.write(stub)
    p = subprocess.run([sys.executable, stub_path, args_dir, TEMPLATE],
                       capture_output=True, text=True, errors="replace", timeout=120)
    out = (p.stdout or "") + (p.stderr or "")
    print("--- %s (rc=%d) ---" % (label, p.returncode))
    print(out.strip()[:1200])
    return p.returncode, out


def main():
    if not os.path.isfile(REAL_ARGS):
        print("ENV FAIL: 找不到真实构建树 args.gn: %s" % REAL_ARGS)
        return 2

    failures = []

    # ---- Green：真实配置（pgo_data_path 已修回 155 树）----
    tmp_ok = tempfile.mkdtemp(prefix="pfoK_")
    with open(REAL_ARGS, "r", encoding="utf-8", errors="replace") as fh:
        real = fh.read()
    with open(os.path.join(tmp_ok, "args.gn"), "w", encoding="utf-8") as fh:
        fh.write(real)
    # 模板在仓库根，stub 通过 __file__ 推不出来，这里显式复制一份到 tmp 上层不需要——
    # 漂移比对读的是 win_scripts/../win_args_mcloud.gn，即仓库真实模板，正是我们要比的。
    rc, out = run_preflight(tmp_ok, "Green: 真实 args.gn")
    if rc != 0:
        failures.append("Green 用例预检未通过（rc=%d）" % rc)
    if "PGO 预检 OK" not in out:
        failures.append("Green 用例没有打印 'PGO 预检 OK'")

    # ---- Red：pgo_data_path 指向不存在的文件（复现 D144 的漂移后果）----
    tmp_bad = tempfile.mkdtemp(prefix="pfBAD_")
    broken = real.replace("chromium-src-155/src/chrome/build/pgo_profiles",
                          "chromium-src/src/chrome/build/pgo_profiles")
    if broken == real:
        print("FAIL: 没能造出坏样本（真实 args.gn 里找不到可替换的 155 树路径）")
        return 1
    with open(os.path.join(tmp_bad, "args.gn"), "w", encoding="utf-8") as fh:
        fh.write(broken)
    rc, out = run_preflight(tmp_bad, "Red: pgo_data_path 指向 M151 树（文件不存在）")
    if rc != 111:
        failures.append("Red 用例应以 111 退出（实际 rc=%d）——预检没拦住坏配置" % rc)
    if "PGO 剖面不存在" not in out:
        failures.append("Red 用例的报错没有指出根因（缺 '剖面不存在'）")
    if "PREFLIGHT_DONE" in out:
        failures.append("Red 用例竟然继续往下走了（出现 PREFLIGHT_DONE）")

    # ---- Red2：漂移比对必须能发现取值不同 ----
    tmp_drift = tempfile.mkdtemp(prefix="pfDRIFT_")
    drifted = real.replace("chrome_pgo_phase = 2", "chrome_pgo_phase = 0")
    with open(os.path.join(tmp_drift, "args.gn"), "w", encoding="utf-8") as fh:
        fh.write(drifted)
    rc, out = run_preflight(tmp_drift, "Red2: 构建树关了 PGO 而模板开着（漂移）")
    if "漂移" not in out:
        failures.append("Red2 用例没有报告模板/构建树漂移")

    print("")
    if failures:
        print("VERDICT: FAIL")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("VERDICT: PASS（Green 通过、Red 拦住并给出根因、漂移可被发现）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
