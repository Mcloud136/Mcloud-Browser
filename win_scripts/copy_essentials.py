# Selective file copy - skip incompatible patches
import os, shutil, sys

cr_src = os.environ.get('CR_DIR', '.')
thor_src = os.environ.get('THOR_DIR', '.')

os.makedirs(f"{cr_src}/out/mcloud/", exist_ok=True)

# Copy essential source files only (no patches)
essential_files = [
    "src/chrome/app/chromium_strings.grd",
    "src/chrome/app/settings_chromium_strings.grdp", 
    "src/chrome/app/shared_settings_strings.grdp",
    "src/chrome/app/app_management_strings.grdp",
    "src/chrome/app/generated_resources.grd",
    "src/chrome/browser/about_flags.cc",
    "src/chrome/browser/thorium_flag_entries.h",
    "src/chrome/browser/thorium_flag_choices.h",
    "src/chrome/common/thorium_2024.h",
    "src/build/config/compiler_opt.gni",
]

for f in essential_files:
    src = os.path.join(thor_src, f)
    dst = os.path.join(cr_src, f)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Copied: {f}")

print("Done - essential files copied (patches skipped)")
