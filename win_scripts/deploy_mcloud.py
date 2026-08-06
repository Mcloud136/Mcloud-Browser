# MCloud Browser 统一部署入口（内核升级后唯一部署步骤）
#
# 用法（设置 THOR_DIR / CR_DIR 环境变量后）：
#   python win_scripts/deploy_mcloud.py
#
# 按序执行全部定点部署步骤（均幂等，可重复运行）：
#   1. copy_essentials.py           复制 compiler_opt.gni + mcloud_flags.txt
#   2. apply_polly_wiring.py        BUILDCONFIG.gn polly/emit-relocs 接线
#   3. append_polly_configs.py      compiler/BUILD.gn polly/emit-relocs 定义+import
#   4. apply_avx2_baseline.py       win/BUILD.gn AVX2+FMA3 基线
#   5. apply_mcloud_source_defaults.py  D3D12/后台模式/DoH 校验
#   6. inject_flags_loader.py       chrome_main_delegate.cc flags 加载器
#   7. 复制 mcloud_flags.txt 到 out/mcloud（加载器运行时读取位置）
#
# 部署完成后执行：gn gen out/mcloud --check
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
cr_src = os.environ.get('CR_DIR', r'D:\wxmuma\chromium-src\src')
os.environ['CR_DIR'] = cr_src
os.environ.setdefault('THOR_DIR', os.path.dirname(here))

STEPS = [
    ("copy_essentials.py", None),
    ("apply_polly_wiring.py", None),
    ("append_polly_configs.py", None),
    ("apply_avx2_baseline.py", None),
    ("apply_mcloud_source_defaults.py", None),
    ("inject_flags_loader.py", None),
]

print("=== MCloud deploy: %s -> %s ===" % (os.environ['THOR_DIR'], cr_src))
for name, _ in STEPS:
    print("\n>>> %s" % name)
    r = subprocess.run([sys.executable, os.path.join(here, name)])
    if r.returncode != 0:
        print("FAILED at %s (exit %d)" % (name, r.returncode))
        sys.exit(r.returncode)

print("\n>>> copy mcloud_flags.txt -> out/mcloud/")
import shutil
os.makedirs(os.path.join(cr_src, "out", "mcloud"), exist_ok=True)
shutil.copy2(os.path.join(os.environ['THOR_DIR'], "mcloud_flags.txt"),
             os.path.join(cr_src, "out", "mcloud", "mcloud_flags.txt"))
print("done")

print("\n=== deploy complete ===")
print("next: gn gen out/mcloud --check")
