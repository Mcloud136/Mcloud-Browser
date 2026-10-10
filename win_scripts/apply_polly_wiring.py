# 一次性工具：在 chromium 树（上游基线）的 BUILDCONFIG.gn 上应用
# Polly/BOLT emit-relocs 接线（规范 2.5/2.6，Polly/BOLT 无效开关修复）。
# 背景：thorium 仓库内的 src/build/config/BUILDCONFIG.gn 基线过旧，
# 直接部署会与较新的 chromium 树冲突（enable_strict_deps 未定义），
# 故接线改为在树的上游文件上原位应用。
import io
import os
import sys

SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "build", "config", "BUILDCONFIG.gn")
s = io.open(p, encoding="utf-8").read()

# D67（本周期修）：旧实现 `if "compiler:polly" in s: exit(0)` 只判"存在"，改了接线正文再跑，
# 树里仍是老版本 —— 与 D64/D67(AVX2) 同族的静默分叉。现按正文比对，不一致就整段替换。
BEGIN_EXE = "# MCloud Browser: wire LLVM Polly / BOLT emit-relocs configs into linkable"
BEGIN_SHL = "# MCloud Browser: same Polly / BOLT emit-relocs wiring for shared libraries."

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


def upgrade(text, begin, wire, anchor):
    """把 begin→anchor 之间我们写过的任何版本，统一升级为当前 wire 正文。"""
    if begin not in text:
        assert text.count(anchor) == 1, "anchor not unique: " + anchor
        return text.replace(anchor, wire, 1), "applied"
    i = text.index(begin)
    k = text.index(anchor, i)          # 我们那段一直延伸到 set_defaults 锚点
    cur = text[i:k]
    want = wire[:wire.index(anchor)]
    if cur == want:
        return text, "up-to-date"
    return text[:i] + want + text[k:], "replaced"


changed = []
for begin, wire, anchor in ((BEGIN_EXE, wire_exe, 'set_defaults("executable") {'),
                            (BEGIN_SHL, wire_shl, 'set_defaults("shared_library") {')):
    s, state = upgrade(s, begin, wire, anchor)
    changed.append(anchor.split('"')[1] + ":" + state)

if all(c.endswith(":up-to-date") for c in changed):
    print("polly wiring already up to date (content match), nothing to do")
    sys.exit(0)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("polly wiring: " + ", ".join(changed))

