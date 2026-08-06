# 一次性工具：在 chromium 树（上游基线）的 BUILDCONFIG.gn 上应用
# Polly/BOLT emit-relocs 接线（规范 2.5/2.6，Polly/BOLT 无效开关修复）。
# 背景：thorium 仓库内的 src/build/config/BUILDCONFIG.gn 基线过旧，
# 直接部署会与较新的 chromium 树冲突（enable_strict_deps 未定义），
# 故接线改为在树的上游文件上原位应用。
import io
import sys

p = r"D:\wxmuma\chromium-src\src\build\config\BUILDCONFIG.gn"
s = io.open(p, encoding="utf-8").read()

if "compiler:polly" in s:
    print("wiring already present, nothing to do")
    sys.exit(0)

wire_exe = (
    "# MCloud Browser: wire LLVM Polly / BOLT emit-relocs configs into linkable\n"
    "# targets. Internally gated by use_polly / use_bolt (compiler_opt.gni).\n"
    "if (!is_android && !is_apple) {\n"
    "  default_executable_configs += [\n"
    '    "//build/config/compiler:polly",\n'
    '    "//build/config/compiler:emit-relocs",\n'
    "  ]\n"
    "}\n"
    "\n"
    'set_defaults("executable") {'
)
wire_shl = (
    "# MCloud Browser: same Polly / BOLT emit-relocs wiring for shared libraries.\n"
    "if (!is_android && !is_apple) {\n"
    "  default_shared_library_configs += [\n"
    '    "//build/config/compiler:polly",\n'
    '    "//build/config/compiler:emit-relocs",\n'
    "  ]\n"
    "}\n"
    "\n"
    'set_defaults("shared_library") {'
)

assert s.count('set_defaults("executable") {') == 1, "executable anchor not unique"
assert s.count('set_defaults("shared_library") {') == 1, "shared_library anchor not unique"

s = s.replace('set_defaults("executable") {', wire_exe)
s = s.replace('set_defaults("shared_library") {', wire_shl)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("wiring applied")
