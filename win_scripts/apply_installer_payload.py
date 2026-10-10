# 一次性/幂等工具：把 mcloud_flags.txt 登记进 mini_installer 的打包清单
# （chrome/installer/mini_installer/chrome.release），缺陷 D47 的产生侧修复。
#
# 背景（2026-10-10 升级预评估实证）：此前该行只存在于构建树的一次未提交手工改动里，
# deploy_mcloud.py 的六个注入步骤无一写这个文件，文档亦无记载。后果是全新源码树
# （=任何一次内核升级）按文档构建时编译与打包全部成功，但安装包里不带
# mcloud_flags.txt，63 行运行时标志整体静默丢失。
#
# 位置选择：紧跟 `chrome.exe: %(ChromeDir)s\` 之后，与已发布 r2 安装包的清单
# 字节级一致（文件头注释称按字母序排列，此处优先保证与既有已验证产物一致）。
import io
import os
import sys

SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "chrome", "installer", "mini_installer", "chrome.release")

ANCHOR = 'chrome.exe: %(ChromeDir)s\\\n'
ENTRY = 'mcloud_flags.txt: %(ChromeDir)s\\\n'

if not os.path.isfile(p):
    print("ERROR: %s not found (CR_DIR 指向的树不对？)" % p)
    sys.exit(1)

s = io.open(p, encoding="utf-8").read()

if ENTRY in s:
    print("installer payload entry already present, nothing to do")
    sys.exit(0)

if ANCHOR not in s:
    print("ERROR: anchor 'chrome.exe: %(ChromeDir)s\\' not found in chrome.release; "
          "上游清单格式可能已变更，请人工核对后调整本脚本锚点")
    sys.exit(1)

s = s.replace(ANCHOR, ANCHOR + ENTRY, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("chrome.release updated: mcloud_flags.txt registered under %(ChromeDir)s")
