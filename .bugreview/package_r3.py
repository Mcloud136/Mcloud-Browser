#!/usr/bin/env python3
"""package_r3.py - r3 收尾：确认构建完成 → 复用 refresh_release 门禁 → r3 专属门禁
→ 回填 SHA256 到发布说明 / CHANGELOG / progress。

用法：
  python .bugreview/package_r3.py            # 构建未完成时直接退出并提示
前置：.bugreview/build_r3.ps1 已结束且 autoninja exit=0。
"""
import hashlib
import io
import os
import re
import subprocess
import sys

REPO = r"d:\wxmuma\thorium"
SRC = r"D:\wxmuma\chromium-src\src"
OUT = os.path.join(SRC, "out", "mcloud")
BUILD_LOG = os.path.join(REPO, ".bugreview", "build_r3.log")
RELEASE = os.path.join(REPO, "mcloud_151.0.7922.99_win64_mini_installer.exe")
NOTES = os.path.join(REPO, "docs", "superpowers", "specs",
                     "2026-10-10-release-notes-m151-r3.md")
CHANGELOG = os.path.join(REPO, "docs", "CHANGELOG.md")
PROGRESS = os.path.join(REPO, "docs", "progress.md")
R3_MARKER = "# [r3 清理 2026-10-10，缺陷 D48]".encode("utf-8")
CHUNK = 1 << 22


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(CHUNK), b""):
            h.update(blk)
    return h.hexdigest()


# --- 1. 构建完成校验 -----------------------------------------------------
log = io.open(BUILD_LOG, encoding="utf-8", errors="replace").read() if os.path.isfile(BUILD_LOG) else ""
if "=== r3 打包结束 ===" not in log:
    print("构建仍在进行（未见结束标记）。等 .bugreview/build_r3.log 出现 '=== r3 打包结束 ===' 后重跑。")
    tail = [ln for ln in log.splitlines() if ln.startswith("[2")]
    print("最后日志：", tail[-1] if tail else "(无)")
    sys.exit(2)
m = re.search(r"autoninja exit=(-?\d+)", log)
if not m or m.group(1) != "0":
    print("FAIL: autoninja 退出码非 0：%s" % (m.group(1) if m else "未记录"))
    sys.exit(1)
print("autoninja exit=0 已确认")

# --- 2. 复用既有发布门禁（含 dll/flags 一致性/chrome.release/mtime 链） ---
r = subprocess.run([sys.executable, os.path.join(REPO, ".bugreview", "refresh_release.py")],
                   capture_output=True, text=True, errors="replace")
print(r.stdout[-2600:])
if r.returncode != 0:
    print(r.stderr[-800:])
    print("FAIL: refresh_release 门禁未过，r3 不发布")
    sys.exit(1)

# --- 3. r3 专属门禁：安装载荷里的 flags 文件必须已是清理后的版本 ----------
z7 = os.path.join(OUT, "chrome.7z")
with open(z7, "rb") as f:
    blob = f.read()
if R3_MARKER not in blob:
    print("FAIL: chrome.7z 内的 mcloud_flags.txt 不含 r3 清理标记 → 载荷仍是旧版 flags")
    sys.exit(1)
print("chrome.7z 载荷已含 r3 清理标记（等价证明：失效条目已随载荷一起更新）")

# --- 4. 回填 SHA256 ------------------------------------------------------
digest = sha256(RELEASE)
size = os.path.getsize(RELEASE)
print("published -> %s  %d bytes  SHA256=%s" % (RELEASE, size, digest))

for path, token in ((NOTES, "<待打包完成后回填>"), (CHANGELOG, "<SHA256 待回填>")):
    if not os.path.isfile(path):
        print("WARN: 文件不存在，跳过回填：%s" % path)
        continue
    s = io.open(path, encoding="utf-8").read()
    if token in s:
        s = s.replace(token, "`%s`" % digest)
        io.open(path, "w", encoding="utf-8", newline="\n").write(s)
        print("已回填 SHA256 -> %s" % os.path.relpath(path, REPO))
    elif digest in s:
        print("已包含该 SHA256（无需重复回填）-> %s" % os.path.relpath(path, REPO))
    else:
        print("WARN: %s 内既无占位符也无该哈希，请人工核对" % os.path.relpath(path, REPO))
sys.exit(0)
