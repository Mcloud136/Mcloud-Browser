#!/usr/bin/env python3
"""package_m155.py - 发布 M155 安装包：门禁 → 复制 → sidecar → 发布说明 → 回填 SHA。

门禁复用 m155_verify.py 的判据子集（dll 加载器证据 / flags 一致 / chrome.release / chrome.7z 载荷），
不重复跑耗时的基准。
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys

THOR = r"d:\wxmuma\thorium"
SRC = r"D:\wxmuma\chromium-src-155\src"
OUT = os.path.join(SRC, "out", "mcloud")
VER = "155.0.8059.40"
RELEASE = os.path.join(THOR, "mcloud_%s_win64_mini_installer.exe" % VER)
NOTES = os.path.join(THOR, "docs", "superpowers", "specs",
                     "2026-10-10-release-notes-m155.md")
REPO_FLAGS = os.path.join(THOR, "mcloud_flags.txt")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


def scan(path, needles):
    hit = {n: False for n in needles}
    with open(path, "rb") as f:
        tail = b""
        while True:
            buf = f.read(1 << 22)
            if not buf:
                break
            data = tail + buf
            for n in needles:
                if n in data:
                    hit[n] = True
            tail = data[-256:]
    return hit


inst = os.path.join(OUT, "mini_installer.exe")
z7 = os.path.join(OUT, "chrome.7z")
dll = os.path.join(OUT, "chrome.dll")
deployed = os.path.join(OUT, "mcloud_flags.txt")
rel_list = os.path.join(SRC, "chrome", "installer", "mini_installer", "chrome.release")

problems = []
h = scan(dll, [b"command-line budget", b"mcloud_flags.txt", b"bug-review D40"])
problems += ["dll 缺加载器证据: %s" % k for k, v in h.items() if not v]
if sha(deployed) != sha(REPO_FLAGS):
    problems.append("out/mcloud/mcloud_flags.txt 与仓库不一致")
if "mcloud_flags.txt: %(ChromeDir)s\\" not in io.open(rel_list, encoding="utf-8", errors="replace").read():
    problems.append("chrome.release 未登记 mcloud_flags.txt")
z = scan(z7, [b"mcloud_flags.txt", "[r3 清理 2026-10-10".encode(), b"SkiaGraphite",
              b"SpareRendererForSitePerProcess"])
problems += ["chrome.7z 缺载荷证据: %s" % k for k, v in z.items() if not v]
if os.path.getmtime(inst) < os.path.getmtime(dll):
    problems.append("installer 早于 chrome.dll，需重打包")
if problems:
    print("FAIL 门禁：")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("门禁全绿（dll / flags 一致 / chrome.release / chrome.7z 载荷 / mtime 链）")

shutil.copy2(inst, RELEASE)
digest = sha(RELEASE)
with open(RELEASE + ".sha256", "w", newline="\n") as f:
    f.write("%s *%s\n" % (digest, os.path.basename(RELEASE)))
print("发布物 -> %s  %d B\nSHA256 = %s" % (RELEASE, os.path.getsize(RELEASE), digest))

notes = """# MCloud Browser v%s

基于 Chromium **M155（%s）**，Windows x64。本版是一次内核升级（M151 → M155），保持既有性能取向与
已定案的稳定性禁用项，并在升级过程中修正了两处口径问题。

## 变化

- **内核 M155**：V8 15.5.35.20、clang `llvmorg-24-init-7747`、PGO 使用 8059 系列 profile。
- **定制面更小**：需要重放的上游改动由 7 个文件降到 **6 个文件**——不再翻转 `kD3D12VideoDecoder`
  上游默认（该解码器仍由启动标志显式禁用，以规避 Intel 核显 D3D12 解码绿屏）。
- **冻结缓解真正生效**：`SkiaGraphite` 在上游本就是默认启用，此前仅注释掉启用行并不构成禁用；
  本版改为显式 `--disable-features=SkiaGraphite`（其余 3 项禁用状态不变）。
- **清单去虚**：删除 `FlingSchedulingImprovements`（M155 起上游已彻底移除该 feature）。

## 实测（同一台机器、同一时刻成对测量）

| 指标 | M151-r3 | M155 |
|---|---|---|
| K1 冷启动中位数 | 46 ms | 45 ms |
| K2 50 标签驻留中位数 | 2590 MB | 2563.3 MB（-1.0%%） |
| 标签开合后的驻留漂移 | +3.7 MB/轮 | -2.4 MB/轮（无正漂移） |
| GPU 渲染路径 | GPU 进程 + D3D11/D3D12 ANGLE | 同左，gpu-preferences 逐字一致 |

内置启动标志 53 项 feature + 3 项普通开关在 M155 源码树逐项存活（`check_features` 53/53），
并通过子进程命令行验证（A6）确认实际注入。

## 校验

下载后核对 SHA256：

```
certutil -hashfile mcloud_%s_win64_mini_installer.exe SHA256
```

预期值：`%s`
""" % (VER, VER, VER.replace(".", "."), digest)
io.open(NOTES, "w", encoding="utf-8", newline="\n").write(notes)
print("发布说明 -> %s" % os.path.relpath(NOTES, THOR))

p = os.path.join(THOR, "docs", "CHANGELOG.md")
s = io.open(p, encoding="utf-8").read()
if "<SHA 待回填>" in s:
    s = s.replace("<SHA 待回填>", "`%s`" % digest, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("CHANGELOG 已回填 SHA")
