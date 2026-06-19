# Selective file copy - skip incompatible patches
import os, shutil, sys

cr_src = os.environ.get('CR_DIR', '.')
thor_src = os.environ.get('THOR_DIR', '.')

os.makedirs(f"{cr_src}/out/mcloud/", exist_ok=True)

# Copy essential source files only (no patches)
essential_files = [
    # Build optimization (SIMD, Polly, BOLT, O3)
    "src/build/config/compiler_opt.gni",
    "src/build/config/compiler/BUILD.gn",
    "src/build/config/BUILDCONFIG.gn",
    "src/build/config/win/BUILD.gn",
    # DNS fix (HTTP断流修复)
    "src/chrome/browser/net/default_dns_over_https_config_source.cc",
    # D3D12 video decoder (default enabled)
    "src/media/base/media_switches.cc",
    # Background mode (default disabled)
    "src/chrome/browser/background/extensions/background_mode_manager.cc",
]

for f in essential_files:
    src = os.path.join(thor_src, f)
    dst = os.path.join(cr_src, f)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Copied: {f}")
    else:
        print(f"SKIP (not found): {f}")

print("Done - essential files copied (patches skipped)")
