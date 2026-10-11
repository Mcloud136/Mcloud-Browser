#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D109 真实安装复验：往**真安装**的根目录放一份带探针的残留文件，
看已安装的 chrome.exe（v8）到底读哪一份。

与 `.bugreview/loader_precedence_test.py` 的分工：那个用硬链接沙箱，能在任意时刻廉价重跑；
这一条跑在**真安装、真产品二进制**上，是发布前的最后一道确认。用完即删，且只碰
Program Files 下这次测试安装（用户自己的用户级安装不受影响）。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "benchmark", "tools"))
import cdp                                                        # noqa: E402

APP = r"C:\Program Files\Chromium\Application"
EXE = os.path.join(APP, "chrome.exe")
VER = os.path.join(APP, "155.0.8059.40")
ROOT_FLAGS = os.path.join(APP, "mcloud_flags.txt")
VER_FLAGS = os.path.join(VER, "mcloud_flags.txt")
MARKER = "--mcloud-installed-shadow-probe=ROOT"
PORT = 9451
prof = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shadow-prof")

repo = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                         "mcloud_flags.txt"), encoding="utf-8-sig").read()
if os.path.exists(ROOT_FLAGS):
    raise SystemExit("REFUSED: 根目录已有 mcloud_flags.txt，先确认这不是别人留下的现场再跑")

try:
    with open(ROOT_FLAGS, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(repo + "\n%s\n" % MARKER)
    print("planted stray root file: %s (%d B)" % (ROOT_FLAGS, os.path.getsize(ROOT_FLAGS)))
    os.makedirs(prof, exist_ok=True)
    subprocess.Popen([EXE, "--user-data-dir=" + prof, "--remote-debugging-port=%d" % PORT,
                      "--no-first-run", "--no-default-browser-check"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not cdp.wait_for_port(PORT, timeout=40):
        raise SystemExit("FAIL: 端口没起来")
    time.sleep(3)
    tab = cdp.Tab(port=PORT, url="about:blank")
    tab.navigate("chrome://version")
    txt = tab.wait_for_text(1000, timeout=30)
    tab.close()
finally:
    cdp.kill_instance(prof)
    if os.path.exists(ROOT_FLAGS):
        os.remove(ROOT_FLAGS)
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    "Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % prof],
                   capture_output=True)

shadowed = MARKER in txt
loaded_real = "enable-gpu-rasterization" in txt
print("root file planted            : yes")
print("version-dir file present     : %s" % os.path.isfile(VER_FLAGS))
print("installed binary read ROOT   : %s" % shadowed)
print("installed binary read VERSION: %s (enable-gpu-rasterization in cmdline)" % loaded_real)
print("root file cleaned up         : %s" % (not os.path.exists(ROOT_FLAGS)))
if not loaded_real:
    print("VERDICT: FAIL-ENV —— 连正式文件都没读到，说明加载器根本没跑")
    sys.exit(2)
print("VERDICT: %s" % ("D109 STILL PRESENT (root shadowed the payload file)"
                       if shadowed else "FIXED (stray root file ignored; version-dir file used)"))
sys.exit(1 if shadowed else 0)
