# 向 chromium 树的 build/config/compiler/BUILD.gn 注入 polly / emit-relocs config 定义
# （供 BUILDCONFIG.gn 接线引用）。树内文件以上游基线为准，仓库内的同名副本基线过旧，
# 不可整体部署（2026-08-05 实证）。
#
# 本脚本是**可重复运行的升级器**，不是"一次性追加"（缺陷 D64）：
# 旧实现一旦看到 `config("polly")` 存在就只补 import 然后 exit(0)，
# 于是"改了 config 正文再跑脚本"时树里仍是旧块——脚本自称已生效、内容其实没换，
# 与 D47/D50 同族（静默不一致）。现在按正文比对，不一致就整体替换。
#
# 同时修正 config 自身的正确性（缺陷 D63）：
#   · Polly 是**编译期**优化（SCoP 检测 + 多面体变换），必须走 cflags。旧写法把
#     `-mllvm:-polly` 放进 ldflags，只有 link-time codegen 看得见，逐 TU 编译根本不过
#     这条路 → 即便打开 use_polly 也基本空转（"看起来开了，其实没开"）。
#   · 旧写法还在 polly config 里写 `ldflags = common_optimize_on_ldflags`，与 Polly 无关。
#   · emit-relocs 服务于 BOLT 后链接，而 BOLT 官方只支持 ELF/Mach-O；Windows COFF 路线
#     未证实可行，故 Windows 下不再发这个 flag，避免 use_bolt 一开就把不支持的参数喂给 lld
#     （表现为链接失败，而不是静默无效——至少不会给出假信号）。
#   当前 use_polly / use_bolt 均为 false（见 compiler_opt.gni / win_args_mcloud.gn），
#   这些 config 展开为空，对本轮构建产物无影响；本轮修的是"将来打开时的正确性"。
import io
import os
import sys

SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "build", "config", "compiler", "BUILD.gn")
s = io.open(p, encoding="utf-8").read()

BEGIN = "# MCloud Browser: Emit relocations for BOLT post-link optimization."
POLLY = 'config("polly") {'
IMPORT_LINE = 'import("//build/config/compiler_opt.gni")'

BLOCK = '''# MCloud Browser: Emit relocations for BOLT post-link optimization.
# Gated by use_bolt. BOLT 只支持 ELF/Mach-O，Windows 下不发该 flag（D63）。
config("emit-relocs") {
  if (!using_sanitizer && use_bolt && !is_win) {
    ldflags = [ "-Wl,--emit-relocs" ]
  }
}

# MCloud Browser: Use LLVM's Polly optimizer.
# Gated by use_polly. Requires a self-built clang with Polly (infra/build_polly.sh).
# Polly 是编译期 pass，必须走 cflags（旧写法放 ldflags 里基本空转，见 D63）。
config("polly") {
  if (use_polly == true) {
    if (is_win) {
      cflags = [
        "-mllvm:-polly",
        "-mllvm:-polly-detect-profitability-min-per-loop-insts=40",
        "-mllvm:-polly-run-dce",
        "-mllvm:-polly-vectorizer=stripmine",
      ]
    } else {
      cflags = [
        "-mllvm",
        "-polly",
        "-mllvm",
        "-polly-detect-profitability-min-per-loop-insts=40",
        "-mllvm",
        "-polly-run-dce",
        "-mllvm",
        "-polly-vectorizer=stripmine",
      ]
    }
  }
}
'''


def ensure_import(text, before_idx):
    """保证 use_polly/use_bolt 的声明文件被 import（作用域不跨文件传递）。"""
    if IMPORT_LINE in text:
        return text
    # 插到我们块的开头，最贴近使用处且仍在顶层作用域
    return text[:before_idx] + IMPORT_LINE + "\n\n" + text[before_idx:]


if BEGIN in s:
    i = s.index(BEGIN)
    j = s.index(POLLY, i)
    k = s.find("\n}\n", j)
    assert k != -1, 'polly config 块的收尾 "}" 未找到，文件形状与脚本假设不符'
    k += len("\n}\n")
    cur = s[i:k]
    if cur == BLOCK:
        s2 = ensure_import(s, i)
        if s2 != s:
            io.open(p, "w", encoding="utf-8", newline="\n").write(s2)
            print("polly block up to date; import added")
        else:
            print("polly/emit-relocs configs already up to date (content match), nothing to do")
        sys.exit(0)
    s = s[:i] + BLOCK + s[k:]
    s = ensure_import(s, i)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("polly/emit-relocs block replaced in place (content differed from repo version)")
    sys.exit(0)

assert "common_optimize_on_ldflags" in s, "common_optimize_on_ldflags not found"

block = "\n\n" + IMPORT_LINE + "\n\n" + BLOCK
if not s.endswith("\n"):
    s += "\n"
s += block
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("polly/emit-relocs configs appended")
