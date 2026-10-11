#!/usr/bin/env python3
"""test_d137_guard.py - 验证 verify_sources.py 里的 D137 回归闸真的会拦下坏正则。

⚠ 纪律（D99 / "测试工具不得改变或污染被测目标"）：会改写被测文件的测试不得直接改真身。
首版把 benchmark/bench_size.ps1 里正确的写法临时替换成坏写法再还原，结果文本模式读写触发
universal newlines，把 CRLF 变成了 LF —— 还原后 sha256 与原文不一致（被本测试自己的
断言抓到）。现改为**只增删一个临时探针文件**，全程不触碰任何已跟踪文件。

判据：
  Green —— 临时探针不存在时门禁 PASS；
  Red   —— 放入一个含坏写法的 .ps1 后门禁 FAIL 且报出 D137，并指名该探针文件；
  收尾  —— 探针必须被删掉，且 `git status` 对本测试涉及的已跟踪文件无改动。
退出码：0=三项都成立 / 1=有判据不成立 / 2=环境不满足。
"""
import os
import subprocess
import sys

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(THOR, "win_scripts", "verify_sources.py")
# 放在 benchmark/ 下才会被门禁扫到；名字带前导下划线与 REDPROBE 便于识别与兜底清理
PROBE = os.path.join(THOR, "benchmark", "_d137_redprobe.ps1")

# 坏写法：\| 是转义竖线，匹配字面量 "|"，任何真实路径都不含它（缺陷 D137）
PROBE_BODY = (
    "# D137 regression probe - intentionally contains the DEAD guard regex.\n"
    "# This file is created and deleted by .bugreview/test_d137_guard.py only.\n"
    "if ($p -match 'chromium-src(\\|$)') { Write-Warning 'never fires' }\n"
)


def run_gate():
    p = subprocess.run([sys.executable, GATE], capture_output=True, text=True,
                       errors="replace", timeout=900, cwd=THOR)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cleanup():
    try:
        if os.path.exists(PROBE):
            os.remove(PROBE)
    except OSError as exc:
        print("WARN: 探针文件删除失败：%s（请手工删掉 %s）" % (exc, PROBE))


def git_clean_for_tracked():
    """本测试只往 benchmark/ 里放探针，所以只需自证该目录零改动。
    ⚠ 不要把 win_scripts/ 也算进来：verify_sources.py 正是被测对象、本轮**故意**改过它，
    首版把两个目录一起查，结果把合法修改误报成"测试污染"。"""
    p = subprocess.run(["git", "status", "--porcelain", "--", "benchmark/"],
                       capture_output=True, text=True, errors="replace", timeout=120,
                       cwd=THOR)
    return [l for l in (p.stdout or "").splitlines()
            if not l.strip().endswith("_d137_redprobe.ps1")]


def main():
    if not os.path.isfile(GATE):
        print("ENV FAIL: 找不到门禁脚本 %s" % GATE)
        return 2
    cleanup()   # 兜底：清掉上一轮可能残留的探针

    failures = []

    print("== Green: 无探针时门禁应 PASS ==")
    rc, out = run_gate()
    result = [l for l in out.splitlines() if l.startswith("RESULT")]
    print("   rc=%d  %s" % (rc, result))
    if rc != 0:
        failures.append("Green 未通过（rc=%d），说明树里本来就有问题，Red 判据无意义" % rc)

    print("== Red: 放入含坏写法的探针 .ps1 ==")
    try:
        # 纯 ASCII 内容 + 无 BOM：这样只会触发 D137 这一条，不牵动 BOM/param 规则
        with open(PROBE, "w", encoding="ascii", newline="\r\n") as fh:
            fh.write(PROBE_BODY)
        rc, out = run_gate()
        hits = [l.strip() for l in out.splitlines()
                if "D137" in l and "_d137_redprobe" in l]
        print("   rc=%d" % rc)
        for h in hits[:2]:
            print("   %s" % h[:200])
        print("   %s" % [l for l in out.splitlines() if l.startswith("RESULT")])
        if rc == 0:
            failures.append("Red 未生效：放入坏写法后门禁仍 PASS —— D137 闸是空的")
        if not hits:
            failures.append("Red 生效了但没指名探针文件/没提 D137，报错不可用")
    finally:
        cleanup()
        print("== 收尾 ==  探针已删除: %s" % (not os.path.exists(PROBE)))
        if os.path.exists(PROBE):
            failures.append("探针文件未被删除，会污染后续门禁")

    dirty = git_clean_for_tracked()
    if dirty:
        failures.append("本测试改动了已跟踪文件：%s" % dirty[:5])

    print("")
    if failures:
        print("VERDICT: FAIL")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("VERDICT: PASS（Green 通过、Red 被 D137 闸拦住并指名探针、探针已清理、"
          "已跟踪文件零改动）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
