# 一次性工具：向 chromium 树的 compiler/BUILD.gn 追加 polly / emit-relocs
# config 定义（供 BUILDCONFIG.gn 接线引用）。树文件为上游基线，
# thorium 仓库内的同名文件基线过旧不可整体部署（2026-08-05 实证）。
import io
import sys

p = r"D:\wxmuma\chromium-src\src\build\config\compiler\BUILD.gn"
s = io.open(p, encoding="utf-8").read()

if 'config("polly")' in s:
    # 已追加过：确保 config 块前有 compiler_opt.gni 的 import
    # （use_polly/use_bolt 声明在该 gni，作用域不会跨文件传递）。
    marker = "# MCloud Browser: Emit relocations for BOLT post-link optimization."
    assert marker in s, "polly block marker not found"
    before = s.split(marker)[0]
    if 'import("//build/config/compiler_opt.gni")' not in before[-600:]:
        s = s.replace(marker, 'import("//build/config/compiler_opt.gni")\n\n' + marker, 1)
        io.open(p, "w", encoding="utf-8", newline="\n").write(s)
        print("import added before polly/emit-relocs configs")
    else:
        print("polly/emit-relocs configs and import already present, nothing to do")
    sys.exit(0)

assert "common_optimize_on_ldflags" in s, "common_optimize_on_ldflags not found"

block = '''

import("//build/config/compiler_opt.gni")

# MCloud Browser: Emit relocations for BOLT post-link optimization.
# Gated by use_bolt (declared in //build/config/compiler_opt.gni).
config("emit-relocs") {
  if (!using_sanitizer && use_bolt) {
    if (is_win) {
      ldflags = [ "-mllvm:--emit-relocs" ]
    } else {
      ldflags = [ "-Wl,--emit-relocs" ]
    }
  }
}

# MCloud Browser: Use LLVM's Polly optimizer.
# Gated by use_polly (declared in //build/config/compiler_opt.gni).
# Requires a self-built clang with Polly support (infra/build_polly.sh).
config("polly") {
  if (use_polly == true) {
    ldflags = common_optimize_on_ldflags
    if (is_win) {
      ldflags += [
        "-mllvm:-polly",
        "-mllvm:-polly-detect-profitability-min-per-loop-insts=40",
        "-mllvm:-polly-run-dce",
        "-mllvm:-polly-vectorizer=stripmine",
      ]
    } else {
      ldflags += [
        "-Wl,-mllvm,-polly",
        "-Wl,-mllvm,-polly-detect-profitability-min-per-loop-insts=40",
        "-Wl,-mllvm,-polly-run-dce",
        "-Wl,-mllvm,-polly-vectorizer=stripmine",
      ]
    }
  }
}
'''

if not s.endswith("\n"):
    s += "\n"
s += block
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("polly/emit-relocs configs appended")
