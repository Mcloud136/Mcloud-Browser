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
# ⚠ 目标目录必须是 %(VersionDir)s（= Application\<版本号>\），不能是 %(ChromeDir)s
# （= Application\ 根）。2026-10-11 用 --system-level 干净安装 + --verbose-logging 实测：
# setup.exe 对根目录只搬固定清单（chrome.exe / chrome_proxy.exe /
# chrome.VisualElementsManifest.xml），根级 chrome.release 条目会被打包进 chrome.7z
# 却**永远不被安装**——于是干净机器上 53 项 feature + 3 项开关整体丢失且无任何报错
# （缺陷 D105；D47 的原始修复方式在这里被证明无效）。版本目录是整目录搬迁，必然落地。
ENTRY = 'mcloud_flags.txt: %(VersionDir)s\\\n'
# 历史形态（D105 之前的错误登记），检测到就地改写，不留下重复条目。
LEGACY_ENTRY = 'mcloud_flags.txt: %(ChromeDir)s\\\n'

if not os.path.isfile(p):
    print("ERROR: %s not found (CR_DIR 指向的树不对？)" % p)
    sys.exit(1)

s = io.open(p, encoding="utf-8").read()

if ENTRY in s and LEGACY_ENTRY not in s:
    print("installer payload entry already present (%(VersionDir)s), nothing to do")
    sys.exit(0)

if LEGACY_ENTRY in s:
    # 正文比对式升级器（D62/D64/D67 纪律）：旧条目存在就原位换成正确目标，
    # 而不是看到"有 mcloud_flags.txt 字样"就宣布已应用。
    s = s.replace(LEGACY_ENTRY, ENTRY, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("chrome.release fixed: mcloud_flags.txt moved from %(ChromeDir)s to "
          "%(VersionDir)s (root-level entries are never installed, D105)")
    sys.exit(0)

if ANCHOR not in s:
    print("ERROR: anchor 'chrome.exe: %(ChromeDir)s\\' not found in chrome.release; "
          "上游清单格式可能已变更，请人工核对后调整本脚本锚点")
    sys.exit(1)

s = s.replace(ANCHOR, ANCHOR + ENTRY, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("chrome.release updated: mcloud_flags.txt registered under %(VersionDir)s")
