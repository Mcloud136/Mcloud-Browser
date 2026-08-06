# Selective file copy + targeted in-place patches (no wholesale overlays)
#
# 2026-08-06 重构：除 compiler_opt.gni（thorium 专有声明文件，无上游对应物）外，
# 不再整体复制任何源码/构建文件——仓库内副本基于旧内核基线，整体覆盖会与
# 新上游树产生漂移并破坏构建（多次实证）。全部定制改为定点幂等脚本：
#   apply_polly_wiring.py          BUILDCONFIG.gn polly/emit-relocs 接线
#   append_polly_configs.py        compiler/BUILD.gn polly/emit-relocs 定义+import
#   apply_avx2_baseline.py         win/BUILD.gn AVX2+FMA3 基线（替换 -msse3）
#   inject_flags_loader.py         chrome_main_delegate.cc 内置 flags 加载器
#   apply_mcloud_source_defaults.py D3D12 默认启用/后台模式默认关/DoH 校验
import os, shutil, sys

cr_src = os.environ.get('CR_DIR', '.')
thor_src = os.environ.get('THOR_DIR', '.')

os.makedirs(f"{cr_src}/out/mcloud/", exist_ok=True)

# Copy essential source files only (no patches)
essential_files = [
    # Build optimization arg declarations (SIMD, Polly, BOLT, O3 switches).
    # thorium-specific file with no upstream counterpart; safe to copy.
    "src/build/config/compiler_opt.gni",
]

for f in essential_files:
    src = os.path.join(thor_src, f)
    # CR_DIR 已指向 chromium/src，条目中的前缀 "src/" 必须剥离，
    # 否则会复制到 <cr_src>/src/... 嵌套死目录（2026-08-05 修复）。
    rel = f.replace("\\", "/")
    if rel.startswith("src/"):
        rel = rel[len("src/"):]
    dst = os.path.join(cr_src, rel)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Copied: {f} -> {dst}")
    else:
        print(f"SKIP (not found): {f}")

# Copy mcloud_flags.txt next to the build output (chrome.exe reads it at startup)
flags_src = os.path.join(thor_src, "mcloud_flags.txt")
flags_dst = os.path.join(cr_src, "out", "mcloud", "mcloud_flags.txt")
if os.path.exists(flags_src):
    shutil.copy2(flags_src, flags_dst)
    print("Copied: mcloud_flags.txt -> out/mcloud/")
else:
    print("SKIP (not found): mcloud_flags.txt")

print("Done - essential files copied (patches skipped)")
