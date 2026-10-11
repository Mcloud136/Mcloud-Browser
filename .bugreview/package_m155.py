#!/usr/bin/env python3
"""package_m155.py - 发布 M155 安装包：门禁 → 复制 → sidecar → 发布说明 → 回填 SHA。

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
_r = subprocess.run([sys.executable, _build, "--embed", RELEASE, "--out", SETUP],
                    capture_output=True, text=True, errors="replace")
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

# 缺陷 D161：端到端验收 setup_wrapper_test.py 的**默认被测对象**是
# installer/out/MCloud-Setup-embedded.exe，但仓库里没有任何脚本生产它——实测重打包后
# 它的 mtime 仍停在上一日，于是"跑验收"实际跑的是**内嵌旧载荷**的那份包装器，
# 结论与被发布的那个不是同一个东西（D86/D72 同族：归属不能靠人记得）。
# 现在同批产一份，并且直接断言它内嵌的就是刚发布的 RELEASE。
TESTWRAP = os.path.join(THOR, "installer", "out", "MCloud-Setup-embedded.exe")
_r2 = subprocess.run([sys.executable, _build, "--console", "--embed", RELEASE, "--out", TESTWRAP],
                     capture_output=True, text=True, errors="replace")
print((_r2.stdout or "").rstrip())
if _r2.returncode != 0 or not os.path.isfile(TESTWRAP):
    print("FAIL 验收用包装器编译失败：\n" + (_r2.stdout or "") + (_r2.stderr or ""))
    sys.exit(1)
print("验收对象 -> %s  %d B  SHA256 = %s（非发布物，仅给 setup_wrapper_test.py 当默认目标）"
      % (TESTWRAP, os.path.getsize(TESTWRAP), sha(TESTWRAP)))

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
- **安装版才真正带上优化清单（r4）**：`mcloud_flags.txt` 改由 VersionDir 投递到 `Application/155.0.8059.40/`，加载器 v8 按 chrome.dll 所在目录（`base::DIR_MODULE`）优先查找，兼容开发树/便携包的扁平布局与安装版的版本子目录布局。此前登记在 Application 根目录的条目会被打包但**不被安装**（setup.exe 对根目录只搬固定三件套），所以 r3 及更早的安装包在干净机器上等于零内置优化（缺陷 D105）。
- **加载器路径优先级修正（r5）**：v7 以 exe 同目录为第一候选，会让一份残留的 `Application\\mcloud_flags.txt` 永久静默压掉安装包投递的正式文件（缺陷 D109）。v8 改以 chrome.dll 所在目录为第一候选，与上游 `GetModulePath` 同口径。

## 安装（两个发布物，请用 setup 那个）

| 文件 | 用途 |
|---|---|
| `mcloud_155.0.8059.40_win64_setup.exe` | **推荐**。外层安装包装器：优雅关闭正在运行的本产品实例 → 安装 → **复验根 chrome.exe 确实升到本版本** → 清理临时文件与残留进程 → 自动重启浏览器。**默认就地更新机器上已存在的那一份**（不擅自换安装位置，避免旧路径的任务栏固定项失效）；两处都没装过时默认装到用户级目录（不弹 UAC），显式 `--system-level` 走系统级并自举提权。 |
| `mcloud_155.0.8059.40_win64_mini_installer.exe` | 上游原生安装器本体。**如果浏览器正在运行，更新会静默不生效**——根启动桩是被锁的映像，上游把它暂存成 `new_chrome.exe` 并把收尾改名委托给 Google Update，而本产品不发布 Google Update（缺陷 D119，已实测）。只在浏览器已完全退出、或你确认自己需要裸安装器时使用。 |

包装器另有 `--list-only`（只报告将关闭哪些实例、不关闭不安装）与 `--no-launch`（装完不重启）两个开关，退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。

## 自上次发布（v151.0.7922.99-r3）以来

**最重要的一条：以前的安装包在干净机器上根本不带运行时优化清单。**
`mcloud_flags.txt` 此前登记在安装包**不会安装**的位置——D47 修的是"打包侧没登记"，
而 D105 才查清真正丢件的环节在**安装侧**：`setup.exe` 对 Application 根目录只搬固定三件套。
所以 r3 及更早的每一个包，装到干净系统上时那 51 项 feature + 3 项普通开关**整体静默丢失且不报错**。
现在它随版本目录投递，并已用一次真实的 `--system-level` 干净安装复验：文件落地、与仓库逐字节一致、
对**安装后的二进制**回显 enable 49 / disable 2（第5周期 D142 清理掉 2 条平台上根本编译不进来的
死声明之后的新口径；此前是 51 / 2）。

## 本包相对上一份 r5 包的差异（第5周期 D121–D155）

- **用户级安装此前整体失效（D121，Critical）**：包装器把 `--system-level` 写死传给 mini_installer。
  后果是选"用户级"时既不提权（提权分支按 systemLevel=false 判断，不触发），又**真的装进
  Program Files**，而复验查的是用户目录 ⇒ 必然报"复验未通过"。现已按 `systemLevel` 条件传参
  （上游 mini_installer 只认 `--system-level`，用户级就是"不传该开关"）。
  判据：`.bugreview/installer_arg_test.py` —— 用假安装包把收到的 argv 录进文件，
  **不触碰任何真实安装位置**；同一条用例跑在修复前的源码上会录到 `--system-level`，
  Red 与 Green 双向都成立，所以这条判据有区分力，不是"两边都恰好通过"。
- **系统级安装后浏览器不再继承管理员令牌（D123，安全）**：此前在提权进程内直接
  `Process.Start` 拉起浏览器，整个浏览会话（含全部 renderer / GPU / utility 子进程）以
  admin 运行——任何网页侧 RCE 直接等于本机管理员，且 Explorer→浏览器拖放被 UIPI 拦死。
  现改经 `explorer.exe` 启动，落回交互用户的中等完整性级别。
- **两处"假绿"的复验判据改正**：默认浏览器注册**整条丢失**此前不算回归（D124——丢失比
  "指向死文件"更严重，用户彻底失去默认浏览器，却静默放过）；进程状态查不到此前按
  "已退出"处理（D125——跨完整性级别访问被拒时进程活得好好的还锁着根启动桩，于是对着
  仍在运行的浏览器执行安装，精确复现 D119 的静默无效更新）。现两者都按失败处理。
- **判定与定位细节**：安装器自身退出码参与最终判定（D129，否则"装失败 + 目录残留"会被
  判成"已确认更新"）；提权实例的退出码原样透传而不再一律报 0（D122）；两处都装着不同
  版本时按 `System.Version` 逐段比较，不再用序数字符串（D127：`"155.0.8059.40"` 按字符比
  会小于 `"155.0.8059.9"`，于是选中更低的那份）；快捷方式快照补上全机器开始菜单
  （D128，系统级安装的 .lnk 恰在那里，此前"指向死路径"根本 WARN 不到）。
- **优化清单去虚（D142）**：删掉 2 条在本平台**根本编译不进来**的声明——`BaseLockTrySpin`
  整体在 `#if BUILDFLAG(IS_POSIX)` 内，`PartitionAllocUsePriorityInheritanceLocks` 的门是
  `is_android && (x64 || arm64)`；另有 2 条上游默认已启用的条目
  （`PartitionAllocMemoryReclaimer`、`PruneOldTransferCacheEntries`）**保留但加注**，
  它们是显式钉住（pin）以防上游翻默认值，不应算作定制收益。删除的 2 条净行为为 0。

**新增外层安装程序 `mcloud_%s_win64_setup.exe`（请用这个）**：

- 浏览器正在运行时双击裸 `mini_installer`，会出现"安装返回成功、下次启动仍是旧版"：根启动桩是被锁的
  映像，上游把它的替换推迟并委托给 Google Update，而本产品不发布 Google Update（D119）。
  setup 会先优雅关闭正在运行的本产品实例（只发关闭消息、超时才强制结束），装完**复验根 chrome.exe
  确实升到本版本**，再清理临时文件与残留进程并自动重启浏览器。
- 默认**就地更新已存在的那一份**，不擅自换安装位置——换位置会让指向旧路径的任务栏固定项失效（D120）。
- 只发裸 mini_installer 等于把"装了但没更新"交给用户，所以两个发布物都要给，但指引一律指向 setup。

**清单可信度**：删掉 7 条上游根本不存在的开关（D48）；修正一处 feature 参数写法——
`Feature:without_spellcheck/without_translate/high_stream_priority` 这种裸名会**静默丢弃全部参数**
并退回上游默认值，已改为合法的 `参数/值` 成对形式（D51）；`SkiaGraphite` 的禁用改为显式声明（D50：
上游在 M155 本就默认启用，"注释掉启用行"等于从未禁用）。

**质量与测量体系**：三轮系统性 bug-review（D52–D120，共 69 条）。把"按进程名统计整机 chrome"
这类与被测实例无因果关系的测量改成按实例取数；把会**假绿**的门禁逐条换成能失败的正例
（聚合表为空却输出 ALL PASS、在压缩归档里搜文件名字节串、"包里有这个文件"当成"装得出来"）；
新增实操五轮探针（真拖窗口、真杀 GPU/渲染进程看恢复、真下载/打印/PiP/全屏、真 1440p 播放、
跨轮句柄与内存累积）与 9 门收口矩阵。测试工具不再做机器级进程清理，也不会污染发布产物目录。

## 实测（同一台机器、同一时刻成对测量）

| 指标 | M151-r3 | M155 |
|---|---|---|
| K1 冷启动中位数 | 46 ms | 45 ms |
| K2 50 标签驻留中位数 | 2590 MB | 2563.3 MB（-1.0%%） |
| 标签开合后的驻留漂移 | +3.7 MB/轮 | -2.4 MB/轮（无正漂移） |
| GPU 渲染路径 | GPU 进程 + D3D11/D3D12 ANGLE | 同左，gpu-preferences 逐字一致 |

内置启动标志 51 项 feature + 3 项普通开关在 M155 源码树逐项存活（`.bugreview/flag_stability.py`
51/51，并确认第5周期删除的 2 条在 M151 上同样是无效声明，净行为为 0），
并通过子进程命令行验证（`flag_runtime_state.py`，回显 enable 49 / disable 2）确认实际注入。

## 已知限制

- **未做代码签名**：从 GitHub 下载后首次运行会有 SmartScreen 警告（需要"仍要运行"）。
- **打 tag 不会自动带出安装包**：`release.yml` 不在 runner 上编译内核，而 127 MB 的包体既被
  `.gitignore` 排除、又超过单次 push 的 100 MiB 上限，所以推 `v*` tag 只会建出一个没有资产的
  release；安装包必须走 GitHub Release 资产上传（缺陷档案 D45）。

## 校验

下载后核对 SHA256（两个发布物都要核）：

```
certutil -hashfile mcloud_%s_win64_setup.exe SHA256
certutil -hashfile mcloud_%s_win64_mini_installer.exe SHA256
```

- setup（推荐）预期值：`%s`
- mini_installer 预期值：`%s`

两者都是同一个内核构建（%s）的产物；setup 只是把 mini_installer 内嵌进外层安装程序，
所以体积略大。
""" % (VER, VER, VER, VER, VER, _setup_digest, digest, VER)
io.open(NOTES, "w", encoding="utf-8", newline="\n").write(notes)
print("发布说明 -> %s" % os.path.relpath(NOTES, THOR))

p = os.path.join(THOR, "docs", "CHANGELOG.md")
s = io.open(p, encoding="utf-8").read()
if "<SHA 待回填>" in s:
    s = s.replace("<SHA 待回填>", "`%s`" % digest, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("CHANGELOG 已回填 SHA")
