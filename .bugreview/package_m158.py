#!/usr/bin/env python3
"""package_m158.py - 发布 M158 安装包：门禁 → 复制 → sidecar → 发布说明 → 回填 SHA。

门禁复用 m155_verify.py 的判据子集（dll 加载器证据 / flags 一致 / chrome.release / chrome.7z 载荷），
不重复跑耗时的基准。
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys

THOR = r"d:\wxmuma\thorium"
SRC = r"D:\wxmuma\chromium-src-158\src"
OUT = os.path.join(SRC, "out", "mcloud")
VER = "158.0.8127.30"
RELEASE = os.path.join(THOR, "mcloud_%s_win64_mini_installer.exe" % VER)
NOTES = os.path.join(THOR, "docs", "superpowers", "specs",
                     "2026-11-08-release-notes-m158.md")
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
# 旧的根目录登记判据已删除：D105 证明"登记到 %(ChromeDir)s"既进不了安装结果，
# 那条判据只会给一个装不出文件的包打绿灯。现在的判据在下面（VersionDir + 暂存目录位置）。
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
# 载荷真身 = 打包暂存目录（create_installer_archive.py 把 chrome.release 列出的文件
# 复制到这里，再整体压成 7z）。用递归查找而不是写死路径：D105 之后文件落在
# Chrome-bin/<版本号>/ 而不是 Chrome-bin/。
staged_found = [os.path.join(r, f)
                for r, _d, fs in (os.walk(STAGING) if os.path.isdir(STAGING) else [])
                for f in fs if f == "mcloud_flags.txt"]
if not os.path.isdir(STAGING):
    problems.append("找不到打包暂存目录（说明 mini_installer 还没跑过，无法验证载荷）: %s" % STAGING)
elif not staged_found:
    problems.append("安装包载荷里没有 mcloud_flags.txt（暂存目录树里找不到该文件）"
                    "——create_installer_archive.py 对匹配不到的 chrome.release 条目**只在 --verbose 时**"
                    "打印一句，默认静默跳过，所以 autoninja 会 exit=0 而包里没这个文件（D47 同族）")
else:
    for x in staged_found:
        if sha(x) != sha(REPO_FLAGS):
            problems.append("暂存目录里的 mcloud_flags.txt 与仓库不一致（打包用的是旧内容）: %s" % x)
if os.path.exists(z7) and os.path.getmtime(z7) < os.path.getmtime(dll):
    problems.append("chrome.7z 早于 chrome.dll：载荷归档没跟上最后一次编译，需重打")

# D105（2026-10-11 干净系统安装实测）：光验"包里有文件"仍然不够——setup.exe 对
# Application 根目录只搬固定清单，根级条目**打包成功但不安装**。所以这里再加两条：
# ① chrome.release 必须把文件登记到 %(VersionDir)s；② 暂存目录里它必须落在版本子目录。
rel_txt = io.open(rel_list, encoding="utf-8", errors="replace").read()
if "mcloud_flags.txt: %(VersionDir)s\\" not in rel_txt:
    problems.append("chrome.release 没有把 mcloud_flags.txt 登记到 %(VersionDir)s —— "
                    "登记到 %(ChromeDir)s（根目录）的条目会被打包但**永不安装**（D105）")
for x in staged_found:
    rel = os.path.relpath(x, STAGING).replace("\\", "/")
    parts = rel.split("/")
    # 期望 Chrome-bin/<版本号>/mcloud_flags.txt；Chrome-bin/<文件> 是根级（不会被安装）。
    if len(parts) < 3:
        problems.append("暂存目录里的 mcloud_flags.txt 不在版本子目录下（%s）——"
                        "根级文件不会被 setup.exe 安装（D105）" % rel)

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

# ---- 外层安装包装器（缺陷 D119）----
# 直接双击 mini_installer 时，若浏览器正在运行，更新会**静默不生效**：根启动桩是被锁的
# 映像，上游把它暂存成 new_chrome.exe，并把收尾改名委托给 Google Update——而我们不发布
# Google Update（实测见 docs/tasks/bug-review-cycle4-report.md）。所以发布物必须带一个
# 内嵌 mini_installer 的包装器：优雅关闭 → 安装 → 复验 → 清理 → 重启。
SETUP = os.path.join(THOR, "mcloud_%s_win64_setup.exe" % VER)
_build = os.path.join(THOR, "win_scripts", "build_setup_exe.py")
_r = subprocess.run([sys.executable, _build, "--embed", RELEASE, "--version", VER,
                     "--out", SETUP],
                    capture_output=True, text=True, errors="replace", timeout=600)
# 缺陷 D130：旧写法只在失败时打印子进程输出，于是成功路径上"用的是哪个编译器、
# 产物是否可复现"整段被丢掉，随后照样写 .sha256 与发布说明。现在无条件转印。
print((_r.stdout or "").rstrip())
if _r.returncode != 0 or not os.path.isfile(SETUP):
    print("FAIL 包装器编译失败：\n" + (_r.stdout or "") + (_r.stderr or ""))
    sys.exit(1)
_setup_digest = sha(SETUP)
with open(SETUP + ".sha256", "w", newline="\n") as f:
    f.write("%s *%s\n" % (_setup_digest, os.path.basename(SETUP)))
print("发布物 -> %s  %d B\nSHA256 = %s" % (SETUP, os.path.getsize(SETUP), _setup_digest))

# 文件版本元数据必须实测核对，不能只声称"已带版本号"：第6轮那次试图用 csc /version:
# 实现，实际是"打印编译器版本并退出"，返回 0 却不产出文件（D164）；回退之后
# FileVersion/ProductVersion 长期是 0.0.0.0（D187），发布说明里没人发现。
_ver_ps = ('$v=(Get-Item "%s").VersionInfo; "" + $v.FileVersion + "|" + $v.ProductVersion'
          % os.path.join(THOR, os.path.basename(SETUP)).replace("\\", "/"))
_v = subprocess.run(["powershell.exe", "-NoProfile", "-Command", _ver_ps],
                    capture_output=True, text=True, errors="replace", timeout=180).stdout.strip().splitlines()
_fields = (_v[-1].split("|") if _v else ["", ""])
print("版本元数据：FileVersion=%s ProductVersion=%s（期望 %s）"
      % (_fields[0] or "?", _fields[1] if len(_fields) > 1 else "?", VER))
if _fields[0] != VER or (len(_fields) < 2 or _fields[1] != VER):
    print("FAIL 发布物文件版本元数据不是 %s —— build_setup_exe.py --version 没生效" % VER)
    sys.exit(1)

# 缺陷 D161：端到端验收 setup_wrapper_test.py 的**默认被测对象**是
# installer/out/MCloud-Setup-embedded.exe，但仓库里没有任何脚本生产它——实测重打包后
# 它的 mtime 仍停在上一日，于是"跑验收"实际跑的是**内嵌旧载荷**的那份包装器，
# 结论与被发布的那个不是同一个东西（D86/D72 同族：归属不能靠人记得）。
# 现在同批产一份，并且直接断言它内嵌的就是刚发布的 RELEASE。
TESTWRAP = os.path.join(THOR, "installer", "out", "MCloud-Setup-embedded.exe")
_r2 = subprocess.run([sys.executable, _build, "--console", "--embed", RELEASE,
                      "--version", VER, "--out", TESTWRAP],
                     capture_output=True, text=True, errors="replace", timeout=600)
print((_r2.stdout or "").rstrip())
if _r2.returncode != 0 or not os.path.isfile(TESTWRAP):
    print("FAIL 验收用包装器编译失败：\n" + (_r2.stdout or "") + (_r2.stderr or ""))
    sys.exit(1)
print("验收对象 -> %s  %d B  SHA256 = %s（非发布物，仅给 setup_wrapper_test.py 当默认目标）"
      % (TESTWRAP, os.path.getsize(TESTWRAP), sha(TESTWRAP)))

notes = f"""# MCloud Browser v{VER}

基于 Chromium **M158（{VER}，官方 tag `158.0.8127.30` / commit `cb5de443be`）**，Windows x64。
本版为 M155 → M158 内核升级（跨 3 个里程碑）。目标版本取 Chromium 官方 tag 列表中
`158.0.8127.*` 系列的最新补丁 tag；M158 当前仍为 Beta（计划 2026-11-17 转 Stable），
按 2026-11-08 的决策本次破例抢跑，下一次升级锚定 M159/M160 GA。

## 主要变化

- **安全**：一次性带入 Chrome 156 stable 的 354 项安全修复（6 Critical）与
  157 stable 的 213 项（7 Critical）。项目没有自动更新机制，存量用户需手动重装。
- **内核能力**：IndexedDB 后端改 SQLite（156）；HTML-in-Canvas 转正、
  Background Fetch 强制 CORS（157）；Web Install API 与 `<install>` 元素、
  媒体状态伪类、OfflineAudioContext 增量渲染、WebTransport 增强（158）。
- **兼容性回退**：自 Chrome 158 Stable 起 XSLT 停止工作（libxslt 攻击面），
  老 RSS / XML sitemap 页面会显示裸 XML；OT 与企业策略例外到 Chrome 176（2027-08-17）。
- **定制面复核**：8 处注入锚点在官方 `.30` 上逐项一致（加载器、-O3 链路、
  chrome.release、AVX2 基线、后台模式、DoH 校验等）；`-O3` 仍为
  `cflags += ["/clang:-O3"]`，M155 → M158 形态未变。
- **DoH 可信列表**：DNSPod / 阿里云公共 DNS 随 `deploy_mcloud.py` 第 6 步重放；
  两个端点的 POST 与 GET 均实测返回 HTTP 200 / `application/dns-message` / DNS rcode=0。
- **优化清单**：沿用 52 项 feature + 3 项普通开关。M158 上的平台有效默认值、
  pin 集合与运行时回显期望值以 `docs/tasks/m158-upgrade-task.md` 和升级报告为准，
  本说明不写未经实测的数字。
- **新性能 flag**：M158 新增候选（如 `GpuInitOptimization`、
  `ANGLETrimMemoryOnIdle`、`QuicAlwaysCancelPreExistingProbingOnMigration`）仅进入
  A/B 队列，**未写入** `mcloud_flags.txt`。

## 安装（两个发布物，请用 setup 那个）

| 文件 | 用途 |
|---|---|
| `mcloud_{VER}_win64_setup.exe` | **推荐**。外层安装包装器：优雅关闭正在运行的本产品实例 → 安装 → 复验根 chrome.exe 确实升到本版本 → 清理临时文件与残留进程 → 自动重启浏览器。默认就地更新机器上已存在的那一份；两处都没装过时默认装到用户级目录，显式 `--system-level` 走系统级并自举提权。 |
| `mcloud_{VER}_win64_mini_installer.exe` | 上游原生安装器本体。浏览器正在运行时更新会静默不生效（缺陷 D119），只在浏览器已完全退出时使用。 |

包装器另有 `--list-only` 与 `--no-launch` 两个开关；退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。

## 已知限制

- **未做代码签名**：从 GitHub 下载后首次运行会有 SmartScreen 警告。
- **打 tag 不会自动带出安装包**：`release.yml` 不在 runner 上编译内核，安装包必须走
  GitHub Release 资产上传（缺陷档案 D45）。
- **M158 为 Beta 抢跑**：11-17 GA 后上游仍会出补丁 tag，本包会随之落后；
  下一次升级锚定 M159/M160 GA。

## 校验

下载后核对 SHA256（两个发布物都要核）：

```
certutil -hashfile mcloud_{VER}_win64_setup.exe SHA256
certutil -hashfile mcloud_{VER}_win64_mini_installer.exe SHA256
```

- setup（推荐）预期值：`{_setup_digest}`
- mini_installer 预期值：`{digest}`

两者都是同一个内核构建（{VER}）的产物；setup 只是把 mini_installer 内嵌进外层安装程序。
"""
io.open(NOTES, "w", encoding="utf-8", newline="\n").write(notes)
print("发布说明 -> %s" % os.path.relpath(NOTES, THOR))

p = os.path.join(THOR, "docs", "CHANGELOG.md")
s = io.open(p, encoding="utf-8").read()
if "<SHA 待回填>" in s:
    s = s.replace("<SHA 待回填>", "`%s`" % digest, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("CHANGELOG 已回填 SHA")
