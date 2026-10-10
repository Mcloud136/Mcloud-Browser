# 一次性工具：向 M155 上游版 build/config/win/BUILD.gn 应用 AVX2+FMA3 基线
# （替换上游的 -msse3）。依据：技术规范 1.5 硬件基线。
#
# D67（本周期修）：旧实现用 `if "-mavx2" in s: exit(0)` 判"已应用"，于是**改了标志列表再跑，
# 树里仍是老列表**——与 D64（polly 无升级路径）同族。现按正文比对：
# 内容一致才算完成；发现我们自己写过的旧版本就整段替换；上游形状变了则明确报错。
import io
import os
import re
import sys

# D27: 与 deploy_mcloud.py 的 CR_DIR 机制保持一致（默认构建机标准树）
SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "build", "config", "win", "BUILD.gn")
s = io.open(p, encoding="utf-8").read()

BEGIN = "# MCloud Browser: AVX2 + FMA3 baseline for Windows x64 builds"
new = '''    # MCloud Browser: AVX2 + FMA3 baseline for Windows x64 builds
    # (spec 1.5 hardware baseline; Clang supports targeting any Intel
    # microarchitecture. MSVC only supports a subset of architectures.)
    if (current_cpu == "x86" || current_cpu == "x64") {
      cflags += [ "-mavx2", "-mfma", "-mf16c", "-mlzcnt", "-mbmi", "-mbmi2" ]
    }'''

old = '''    if (current_cpu == "x86" || current_cpu == "x64") {
      cflags += [ "-msse3" ]
    }'''

if BEGIN in s:
    # 我们应用过了：取出这一段（到该 if 块的收尾 }）与目标正文比对
    i = s.index(BEGIN)
    k = s.find("\n    }", i)
    assert k != -1, "AVX2 块的收尾未找到，文件形状与脚本假设不符"
    k += len("\n    }")
    cur = s[i:k]
    want = new.lstrip("    ").strip("\n")
    if cur.rstrip() == new.strip():
        print("AVX2 baseline already present (content match), nothing to do")
        sys.exit(0)
    s = s[:i] + new.strip() + s[k:]
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("AVX2 baseline block replaced in place (content differed from repo version)")
    sys.exit(0)

assert old in s, ("AVX2 anchor not found：上游该段文本已改变（既没有我们的注释块，也没有预期的 "
                  "`cflags += [ \"-msse3\" ]`），请人工核对后再改锚点，不要盲目追加")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("AVX2 baseline applied")

