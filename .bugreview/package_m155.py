#!/usr/bin/env python3
"""package_m155.py - 发布 M155 安装包：门禁 → 复制 → sidecar → 发布说明 → 回填 SHA。

门禁复用 m155_verify.py 的判据子集（dll 加载器证据 / flags 一致 / chrome.release / chrome.7z 载荷），
不重复跑耗时的基准。
"""
import hashlib
import io
import os
import shutil
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
# ── 缺陷 D102（2026-10-11 实测）：下面这段"在 chrome.7z 里搜文件名"的判据是**无效量具**。
# 7z 的文件表是压缩的，原始字节扫描既看不到文件名也证不了伪：对照实验里 chrome.dll、
# resources.pak、icudtl.dat、chrome_100_percent.pak 这些**必然在包里的文件**在前 16 MB
# 内命中数全部为 0；唯一一次命中 "mcloud_flags.txt" 是 chrome.dll 里加载器自己的字符串
# （上下文是 "MCloud flags: --... skipped by command-line budget"）。也就是说：
# 这条判据既能被误报满足，也永远无法证明载荷里真的有那个文件。
# 真正的判据改成读**打包暂存目录**（create_installer_archive.py 把 chrome.release 列出的
# 文件复制到这里，再整体压成 7z —— 它就是载荷本身）。
STAGING = os.path.join(OUT, "gen", "chrome", "installer", "mini_installer",
                       "mini_installer", "temp_installer_archive")
staged_flags = os.path.join(STAGING, "Chrome-bin", "mcloud_flags.txt")
if not os.path.isdir(STAGING):
    problems.append("找不到打包暂存目录（说明 mini_installer 还没跑过，无法验证载荷）: %s" % STAGING)
elif not os.path.isfile(staged_flags):
    problems.append("安装包载荷里没有 mcloud_flags.txt（暂存目录缺 Chrome-bin/mcloud_flags.txt）"
                    "——create_installer_archive.py 对匹配不到的 chrome.release 条目**只在 --verbose 时**"
                    "打印一句，默认静默跳过，所以 autoninja 会 exit=0 而包里没这个文件（D47 同族）")
elif sha(staged_flags) != sha(REPO_FLAGS):
    problems.append("暂存目录里的 mcloud_flags.txt 与仓库不一致（打包用的是旧内容）")
if os.path.exists(z7) and os.path.getmtime(z7) < os.path.getmtime(dll):
    problems.append("chrome.7z 早于 chrome.dll：载荷归档没跟上最后一次编译，需重打")
if os.path.getmtime(inst) < os.path.getmtime(dll):
    problems.append("installer 早于 chrome.dll，需重打包")
# D72：门禁必须能识别"编译失败但产物还在"的情况。本轮实测踩过：
# 探针残留的 chrome 进程锁住 dxcompiler.dll → autoninja exit=1，
# 而旧门禁只看产物存在与内容证据，于是拿着上一轮的 installer 打印"门禁全绿"并回填了新哈希。
# 这里加两条"新鲜度链"：产物必须不早于它应当包含的源码/构建配置。
_loader_src = os.path.join(SRC, "chrome", "app", "chrome_main_delegate.cc")
_gn_srcs = [os.path.join(SRC, "build", "config", "BUILDCONFIG.gn"),
            os.path.join(SRC, "build", "config", "compiler", "BUILD.gn"),
            os.path.join(SRC, "build", "config", "win", "BUILD.gn"),
            os.path.join(SRC, "build", "config", "compiler_opt.gni")]
_t_dll = os.path.getmtime(dll)
if os.path.getmtime(_loader_src) > _t_dll:
    problems.append("chrome.dll 早于加载器源文件 chrome_main_delegate.cc："
                    "最后一次编译发生在源码改动之前（或在改动之后失败），产物不反映仓库正文")
_t_gn = max(os.path.getmtime(g) for g in _gn_srcs if os.path.exists(g))
if _t_gn > _t_dll:
    problems.append("chrome.dll 早于 GN 配置源文件：当前构建配置未反映在产物里，需重编后再打包")
if problems:
    print("FAIL 门禁：")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("门禁全绿（dll 加载器证据 / flags 一致 / chrome.release 登记 / **暂存目录=载荷真身** / mtime 链）")

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
