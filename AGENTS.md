# AGENTS.md — MCloud Browser 仓库导航

本文件为 AI Agent 提供仓库导航：源码根职责、核心修改文件定位、构建流程和编码约定。
修改任何代码前先阅读本文件，避免无效探索。

## 项目简介

MCloud Browser 是基于 Chromium（当前 M155，155.0.8059.40，硬件基线 AVX2+FMA3）的高性能 Windows 浏览器分支，
通过 AVX2 原生编译 + 运行时优化标志（`mcloud_flags.txt`，启动时内置加载；
2026-10-12 (第6周期) 实测 55 条开关行 = 52 项 feature + 3 项普通开关（第6周期新增
`UserBlockingAboveNormalPriority`，缺陷 D170；2026-10-12 (第5周期) 时为 54 条 = 51 + 3）；
2026-10-10 (r3) 时为 56 条 = 53 + 3，差额是 D142 清理掉的 2 条**平台上根本编译不进来**的条目
（`BaseLockTrySpin` 在 `#if BUILDFLAG(IS_POSIX)` 内、`PartitionAllocUsePriorityInheritanceLocks`
在 `#if PA_BUILDFLAG(ENABLE_PARTITION_LOCK_PRIORITY_INHERITANCE)` 内，而该 buildflag 是
`is_android && (x64||arm64)`）；r2 时为 63 条 = 60 + 3，差额是 D48 清理掉的 7 条上游不存在的条目。
⚠ 52 项里有 **15 项**（`SpareRendererForSitePerProcess`、`BackForwardCache`、
`CacheControlNoStoreEnterBackForwardCache`、`PreloadTopChromeWebUI`、
`BookmarkTriggerForPreconnect`、`PartitionAllocMemoryReclaimer`、
`PruneOldTransferCacheEntries`、`ConsumeCodeCacheOffThread`、
`RevokeMediaSourceObjectURLOnAttach`、`GpuShaderDiskCache`、
`HighFramerateRequestFromClient`、`PlatformHEVCDecoderSupport`、
`DirectOpusAudioDecoding`、`EncryptedMediaOcclusionTracking`、**`AsyncDns`**）
**在 Windows 上上游默认就是 ENABLED**（第7周期用 `.bugreview/guard_audit.py` 按平台有效
默认值核定，缺陷 D171→D177；第6周期只数出 14 项，漏掉 AsyncDns 是因为它的默认值写在
`#if BUILDFLAG(IS_CHROMEOS)||IS_MAC||IS_ANDROID||IS_WIN||IS_LINUX` 里，旧抽取器读不到就
静默放过）。这些行是显式钉住（pin）而非"打开了默认关闭的优化"，不要算作已生效的定制收益
——**50 项启用里真正新增的只有 35 项**。
⚠ 同一把尺子也翻案了两条"禁用"：`D3D12VideoDecoder` 与 `SkiaGraphite` 在 Windows 上
**上游默认即 DISABLED**（后者声明是 `#if IS_APPLE ENABLED #else DISABLED`），所以这两行
当前净操作为零，作用是防 Finch 远程下发/防上游翻默认，**不是**"绿屏/冻结靠它们挡住的"
（缺陷 D178；拖拽冻结那组 4 项的归因另见 D182——其中 `ReduceHardwareVideoDecoderBuffers`
在 Windows 上是根本不存在的死声明）
⚠ `mcloud_flags.txt` **不支持行尾注释**：加载器只跳过整行注释，一行
`--enable-features=Foo   # note` 会让整串 feature 被拒、全部优化静默失效（**缺陷 D59**，
不是新缺陷；`flag_stability.py` 的 F 断言专拦此项）。
注释必须独占一行。已由 `.bugreview/flags_lint.py` + `verify_sources.py` 拦截）
+ 编译时优化栈提供极致流畅体验。
本仓库**不是完整 Chromium 源码树**，而是存放覆盖文件（override files）、补丁、构建脚本和打包配置。
完整构建需先将本仓库文件复制到外部 Chromium 源码树（`$CR_DIR`，默认 `D:\wxmuma\chromium-src\src`）再编译。

## 技术栈

| 组件 | 说明 |
|------|------|
| Chromium M155 | 浏览器内核（tag 155.0.8059.40） |
| GN + Ninja | Chromium 内置构建系统 |
| Clang (LLVM) | Chromium 内置编译器 |
| depot_tools | Google 构建工具链（仓库内 `depot_tools/` 固定修订版本） |
| Python 3.8+ | 构建脚本 |
| GitHub Actions | CI/CD（release.yml 发布 + verify.yml 源码验证） |

- **仓库**：https://github.com/Mcloud136/Mcloud-Browser（main 分支，MIT 许可）。
- **CI 触发**：`verify.yml` 在 push 到 main / PR / 手动时运行；`release.yml` **仅在推送 `v*` tag 时运行**
  （push 到 main 不会发布）。注意 release 作业不在 runner 上编译内核，它假定仓库根存在
  `mini_installer.exe` 才会算校验并上传资产——而该文件既被 `.gitignore` 排除、又超过 GitHub
  单次 push 的 100 MiB 上限，因此**打 tag 只会建出没有安装包的 release**；安装包资产需通过
  GitHub Release 资产上传（详见 `docs/tasks/bug-review-pak-src-defects.md` D45）。

## 源码根职责总览

| 目录 | 语言 | 职责 |
|------|------|------|
| `src/` | C++ | Chromium 覆盖文件：品牌、运行时 flags 加载、媒体/网络/UI 功能修改 |
| `win_scripts/` | Python | Windows 构建流水线：源码复制、flags 注入、编译、部署 |
| `pak_src/` + `pak_src_fixed/` | C | Chromium `.pak` 资源包工具；构建链只用 `pak_src/binaries/` 里的二进制（Windows 侧已从 `pak_src_fixed/pak.c` 重建，见下文） |
| `infra/` | C/Python/Shell | 发布打包：AppImage、Flatpak、Portable、DEB、品牌与构建脚本 |
| `arm/` | GN/Shell | ARM 平台构建支持（树莓派 / Windows on ARM） |
| `other/` | Patch | Chromium 补丁文件（`feature-name.patch` 命名格式） |
| `benchmark/` | PowerShell/Python | 性能基准测试脚本（启动、内存、导航、体积）与工具 |
| `depot_tools/` | - | 固定的 depot_tools 修订版本与 Windows 工具链配置 |

## src/ — 素材目录（**不是**「当前生效的修改集」）

**口径已更正（2026-10-10 第3周期扩展轮，缺陷 D77）**：`src/` 实测 **590** 个文件（不是旧文档写的
112；112 ≈ 当年的 `.cc/.h` 数，现为 106）。与 M155 构建树比对：**233** 个树内无对应路径（真正的
仓库独有资产）、**12** 个字节一致、**345** 个内容不同——而构建流水线只应用其中 **1** 个
（`build/config/compiler_opt.gni`，经 `copy_essentials.py` 白名单整份复制）。
也就是说：**改其余 344 个"与树内不同"的副本不会生效，也不会报错**；这些副本还新旧混杂
（`build/config/BUILDCONFIG.gn`、`compiler/BUILD.gn` 的副本带着上一代内核的 polly/avx2 注入痕迹，
`build/config/win/BUILD.gn` 的副本没有）——**拿仓库副本与树内文件比对会得出错误结论**。

权威清单：**`src/INVENTORY.md`**（自动生成的"哪些文件真的参与构建"），随内核升级后重生成：
`python .bugreview/src_inventory.py --write`。

要改上游 Chromium 文件，正确路径只有一个：在 `win_scripts/` 写**定点幂等脚本**
（`apply_*` / `inject_*`），由 `deploy_mcloud.py` 编排。不要往 `copy_essentials.py` 的整份复制清单
里加有上游对应物的文件——那里的 `ALLOWED_COPY` 白名单会直接拒绝（缺陷 D41）。

下面按子目录定位**素材**（读它们可以了解历史意图，但不能据此判断"当前构建里是什么样"）：

### src/chrome/（素材 60 文件；历史改动集中区，但除注入目标外均为惰性副本）
- **启动标志加载：唯一来源是 `win_scripts/inject_flags_loader.py` 的 `LOADER` 常量**（向树内
  `chrome/app/chrome_main_delegate.cc` 幂等注入 `LoadMcloudPerformanceFlags()`）。
  ⚠ 仓库内的 `src/chrome/app/chrome_main_delegate.cc` 是 2026-08-05 的**旧基线副本，不参与构建、
  已从 copy_essentials 清单移除**（与 M151 存在 8 处 API 漂移，整份覆盖会编译失败，见
  `docs/dev-logs/phase2-dev-log.md` §8 与缺陷 D41）。改加载器行为请改注入脚本，不要改这份副本。
- `src/chrome/browser/about_flags.cc` — chrome://flags 界面注册。
- `src/chrome/browser/chrome_content_browser_client.cc` — 浏览器内容客户端配置。
- `src/chrome/browser/ui/browser.cc`、`browser_commands.cc`、`tabs/tab_strip_model.cc` — 浏览器窗口与标签页 UI。
- `src/chrome/browser/background/extensions/background_mode_manager.cc` — 后台模式。
- `src/chrome/browser/net/default_dns_over_https_config_source.cc` — DoH 默认配置。

### src/components/（19 文件）
- `src/components/webui/flags/flags_state.cc` — flags 状态管理。
- `src/components/history/core/browser/history_backend.cc` — 历史记录后端。
- `src/components/neterror/resources/dino_game/offline.ts` — 离线恐龙游戏。

### src/media/（5 文件）
- **`src/media/base/media_switches.cc`** — 媒体特性开关（HEVC、硬件解码等），churn 最高的 C++ 文件之一。
- `src/media/ffmpeg/ffmpeg_common.cc` — FFmpeg 集成（AC3/EAC3 等编解码支持）。

### src/net/（4 文件）
- `src/net/dns/dns_transaction.cc`、`src/net/dns/dns_client.cc` — DNS 客户端优化。
- `src/net/url_request/url_request_http_job.cc` — HTTP 请求作业。
- `src/net/base/load_flags_list.h` — 加载标志定义。

### src/content/、src/sandbox/、src/extensions/、src/third_party/、src/ui/
- `src/content/common/gpu_pre_sandbox_hook_linux.cc` — Linux GPU 沙箱钩子。
- `src/sandbox/win/src/sandbox_policy_base.cc` — Windows 沙箱策略。
- `src/extensions/` — Manifest V2 扩展兼容。
- `src/third_party/blink/common/features.cc` — Blink 特性开关。
- `src/build/config/compiler_opt.gni` — 编译器优化配置（修改前必须备份）。

## win_scripts/ — Windows 构建流水线（15 文件）

构建流程主入口。`deploy_mcloud.py` 是统一部署编排器（编译前执行，内核升级后唯一部署步骤），
按序调用以下定点注入脚本（全部幂等，可重复运行）：

1. **`deploy_mcloud.py`** — 统一部署编排入口，按序执行下列 2-6 步并复制 `mcloud_flags.txt` 到 `out/mcloud`。
2. `copy_essentials.py` — 复制 `compiler_opt.gni` + `mcloud_flags.txt` 到 `$CR_DIR`（最高频修改的构建脚本）。
3. `apply_polly_wiring.py` — BUILDCONFIG.gn polly/emit-relocs 接线。
4. `append_polly_configs.py` — compiler/BUILD.gn polly/emit-relocs 定义+import。
5. `apply_avx2_baseline.py` — win/BUILD.gn AVX2+FMA3 基线。
6. `apply_mcloud_source_defaults.py` — D3D12/后台模式/DoH 源码级默认修改。
7. **`inject_flags_loader.py`** — 将 flags 加载器注入 `chrome_main_delegate.cc`。
8. **`apply_installer_payload.py`** — 向 `chrome/installer/mini_installer/chrome.release` 登记
   **`mcloud_flags.txt: %(VersionDir)s\`**（缺陷 D47 修复；目标目录于 2026-10-11 由 D105 更正）。
   **这一步不可省略**：少了它，编译与打包全部成功但安装不包含标志文件，运行时优化整体静默丢失。
   ⚠ **不要改成 `%(ChromeDir)s`（= Application 根目录）**：`setup.exe` 对根目录只搬固定清单
   （chrome.exe / chrome_proxy.exe / chrome.VisualElementsManifest.xml），根级条目会被打包进
   `chrome.7z` 却**永不安装**——实测干净系统安装后 `Application\` 下没有该文件，
   而版本目录 `Application\<版本号>\` 是整目录搬迁、必然落地（D105）。
   相应地加载器 **v8** 以 `base::DIR_MODULE`（**chrome.dll 所在目录**，与上游
   `main_dll_loader_win.cc:175-191 GetModulePath` 同口径）为第一候选，exe 同目录次之，
   最新载荷目录兜底。⚠ 不要退回"先读 exe 同目录"：安装版根目录只有一个 4 MB 启动桩，
   任何一份残留的 `Application\mcloud_flags.txt` 都会永久、静默地压掉安装包投递的那份
   （缺陷 D109 已用硬链接沙箱实测复现，回归判据见 `.bugreview/loader_precedence_test.py`）。
   **发布前必须做一次干净安装复验**，非交互口径已实测确定（照下面的命令做，否则会卡在弹窗上，
   缺陷 D162）：
   ```
   # 装（外层包装器；必须 --quiet，否则 GUI 形态会停在"完成"按钮等人点 = D131）
   mcloud_<ver>_win64_setup.exe --quiet --system-level        # 期望 rc=0
   # 卸（必须 --force-uninstall：不带它时上游会启动 chrome.exe --uninstall 弹确认框并死等）
   "C:\Program Files\Chromium\Application\<ver>\Installer\setup.exe" --uninstall --system-level --force-uninstall
   #                                                             期望退出码 19 = UNINSTALL_SUCCESSFUL
   ```
   断言四件事：版本目录里文件落地 + 与仓库字节一致 + 对**安装后的二进制**跑
   `flag_runtime_state.py` 得到回显 + 根目录无残留 `mcloud_flags.txt`。只看门禁绿灯不足以证明安装包正确。
   ⚠ **不要用安装目录的 mtime 判断"装的是不是本轮产物"**（第6周期收口轮实测）：7z 归档保留原始
   时间戳，版本目录 `chrome.dll` 显示 Oct 6 08:16 而 SHA1 与 15:50 的构建产物完全一致。
   判据只能是哈希，且 `chrome.dll` 与根 `chrome.exe` **各比一次**。
   ⚠ 另：`chrome.release` 把 `chrome.exe` 登记为 `%(ChromeDir)s\`，所以**版本目录里本来就没有
   `chrome.exe`**，根目录那个 4,389,888 B 的 exe 就是产物本体（不是"启动桩"）——别据此判"安装不完整"。
   ⚠ 卸载会**连带删掉** `User Pinned\TaskBar` 里指向自己的 .lnk（实测：任务栏固定项消失）；
   `UserChoice` 的 `ProgId` 保持 `ChromiumHTM` 不变，所以重装后默认浏览器会**自行恢复**
   （实测 `TargetExists: n/a -> yes`），但任务栏固定项没有 API 可恢复，需手工重新固定。
   ⚠ **回显条数口径（第6周期 D170，2026-10-12）**：新增 UserBlockingAboveNormalPriority 后，
   期望值为 **`enable 50 / disable 2`**。
   历史：第5周期 D142 清理掉 2 条平台上根本编译不进来的死声明后为 `enable 49 / disable 2`；
   再早是 `enable 51 / disable 2`。发布说明与本文件里所有旧口径对新包都要改。
   ⚠ **安装版启动日志里曾稳定出现 `Command line too long for RegisterApplicationRestart`**
   （缺陷 D172）：命令行超 Windows 的 1024 字符上限，导致浏览器不被 Windows 重启管理器恢复。
   修复脚本 `win_scripts/apply_restart_cmdline.py` **需要重新编译才生效**；发布前应在启动日志中
   确认该 WARNING 已消失。
   ✅ **r7（2026-10-12）已编入并实测消失，且有正向对照**：对安装后的二进制用
   `--enable-logging --log-file=<路径> --v=1` + 一次性 `--user-data-dir` 采集，
   日志 **135,082 B**（证明日志通道开着）而该 WARNING **0 次**；再在同一份二进制上
   多加一个 **1300 字符的未知开关**，WARNING **复现** ⇒ 这条判据**能红**，"0 次"才是测量结果。
   ⚠ 用 `--v=0` 会采到 **0 B 空日志**——"空日志 + 0 hits"是空数据上的缺席判据，**不作证据**；
   缺席型判据必须同时给出"日志非空"和"同类输入能让它失败"两条旁证。
   命令行长度算术：Red 时 **1911 字符** → 修剪后 **≈284 字符** < 1024。
9. **`build_win.py`** — 执行 gn/autoninja 编译。**编译前有 `preflight_args()` 预检**（第5周期 D144 新增）：
   ① `chrome_pgo_phase=2` 时硬校验 `pgo_data_path` 指向的 profdata **确实存在**，不存在即以 111 退出
   并给出根因与两种修法（GN 只 `assert(pgo_data_path != "")`、**不校验存在**，见
   `build/config/compiler/pgo/BUILD.gn:149`，所以 `gn gen --check` 会过、ninja 才在第 156 行
   `inputs +=` 上报一句完全不指向根因的 `missing and no known rule to make it`）；
   ② **仓库模板 `win_args_mcloud.gn` 与构建树 `out/mcloud/args.gn` 逐项漂移比对**，不一致即 WARN
   并逐条列出——D144 就是两边静默漂移，导致"仓库里 committed 的配置根本构建不出已发布的二进制"。
10. 辅助：`version.py`（版本管理）、`clean.py`、`reset_depot_tools.py`、`tot.py`/`trunk.py`（ToT 同步）。
11. **`verify_sources.py`** — 最小源码验证：win_scripts/ 全部 Python 脚本语法检查 + 关键脚本存在性 + pak_src/ C 源码检查。修改构建脚本后运行 `python3 win_scripts/verify_sources.py`（退出码 0=PASS / 1=FAIL）；已接入 CI（`.github/workflows/verify.yml`，push/PR 自动运行）。
12. **`build_setup_exe.py`** — 编译外层安装包装器 `MCloud-Setup.exe`（源文件 `installer/mcloud_setup.cs`），
    由 `package_m155.py` 在打包时自动调用并内嵌 mini_installer。**必须用 VS 的 Roslyn csc**：
    .NET Framework 自带的旧 csc 不支持 `/deterministic`，同一份源码两次编译 SHA 会不同，
    发布哈希失去意义。**现已硬失败**（缺陷 D130，2026-10-12 r6）：找不到 Roslyn 时不再静默退回旧 csc，
    而是 exit 113 并给出两种修法——旧写法随后照样写 `.sha256` 与发布说明，等于把"核对哈希"这条验收作废。
    确需本机排错才用 `--allow-nondeterministic`，发布路径禁用。
    `package_m155.py` 侧同步改为**无条件转印**子编译器日志（旧写法 `capture_output=True` 且只在失败时打印，
    成功路径把"用了哪个编译器/是否可复现"整段丢掉）。
    注意复现性验证要**同名不同目录**对比——输出文件名会进元数据。

注意：`setup.py` 为遗留全量覆盖脚本，已被定点注入取代，勿在新 Chromium 树上运行（会污染源码树）。
该约定现已**机器化**（缺陷 D97，2026-10-11）：脚本在没有上游对应动作的位置直接拒绝执行，
默认 `REFUSED` + 退出码 112 并指向 `deploy_mcloud.py`；只有显式设 `MCLOUD_ALLOW_LEGACY_SETUP=1` 才会继续。
`--help` 仍正常返回 0。

### 发布物有两个（缺陷 D119，必读）

| 文件 | 说明 |
|---|---|
| `mcloud_<ver>_win64_setup.exe` | **给用户的那个**。外层包装器：优雅关闭正在运行的本产品实例 → 安装 → **复验根 chrome.exe 确实升到本版本** → 清理临时文件与残留进程 → 自动重启浏览器。**默认就地更新已存在的那一份**（Google Update 式）：先用「根 chrome.exe 是否存在」+「默认浏览器当前解析到哪份」判定位置，两处都在就更新用户真正在用的那份，**不擅自换位置**（换位置会让旧路径的任务栏固定项失效并留下两份安装，缺陷 D120）。只有显式 `--system-level` / `--user-level` 才允许换，且换前打印后果；系统级会自举提权。更新前/后对「默认浏览器解析目标 + 指向本产品的 .lnk」做快照比对：默认浏览器链从好变坏 = 判 FAIL；pin 指向死路径只 WARN——任务栏固定项自 Win7 起没有公开 API 可创建，唯一可靠做法就是别换位置。`--list-only` 只报告不关闭。 |
| `mcloud_<ver>_win64_mini_installer.exe` | 上游裸安装器。**浏览器正在运行时双击它，更新会静默不生效**：根启动桩是被锁的映像，上游把它暂存成 `new_chrome.exe` 并把收尾改名委托给 Google Update，而我们不发布 Google Update（实测见 `docs/tasks/bug-review-cycle4-report.md`）。只用于浏览器已完全退出的场景或自动化复验。 |

⚠ 只发裸 mini_installer 等于把"装了但没更新"交给用户；发布说明与任何安装指引都必须指向 setup 那个。
验收/回归（两条，覆盖面不同，**都要跑**）：
- `.bugreview/setup_wrapper_test.py` — 端到端：造 151 运行中现场 → 用包装器升 155 → 断言真的升到 155。
  ⚠ 它第 84/102/144 行**永远传 `--system-level`**，所以它验的恰好是"硬编码也能碰对"的那一支（缺陷 D121
  就是从这里漏掉的），而且它会真的装到 Program Files 并在收尾卸载 ⇒ 属"改动真实安装"的操作，需授权。
- `.bugreview/installer_arg_test.py` — **参数级**（r6 新增，不需要授权）：用一个假安装包（stub）把
  包装器实际传给 mini_installer 的 argv 录进文件，因此 `--user-level` 这一支能被**真正执行**：
  A（HEAD + `--user-level` → 收到空参数）/ A'（`68838c1` 那版跑同一条 → 收到 `--system-level`，
  这条不成立就说明 A 的通过毫无意义）/ B（stub 返回 3 → 日志出现"安装器自身返回 3"且 rc=1，D129）/
  C（`--system-level` → 收到 `--system-level`；目标目录下有正在运行的实例时**按设计跳过**并整体判
  PARTIAL/exit 2，不允许两半通过冒充全绿）。四条污染自检（两个安装目录指纹、实例数、残留临时目录）
  每次都跑——这是 D99 那族"测试自己污染被测目标"的对策。
  ⚠ **不要**把它简化成"给 setup_wrapper_test.py 加一条 `--user-level`"：那会真的往
  `%LOCALAPPDATA%\Chromium\Application` 装一份，而注册表 `UserGpuPreferences` 里有一条指向该路径的
  `GpuPreference=1`（= 优先核显，缺陷 D154），测试会把用户级安装钉在 Intel 核显上，而核显正是
  D3D12 绿屏那一侧，与所有既有 GPU 基准不可比。

⚠ `--list-only` 在**发布形态（`/target:winexe`）下并非完全哑**：stdout 被重定向时能读到正文
（r6 实测 149 B），只有双击打开的用户看不到。D133 原记为"用户手上是哑的"，严重度按此收窄。

前置文档：**本文件下面「构建快速参考」一节 + `docs/progress.md` §5.1**（两者一致，是权威步骤）。
⚠ `docs/BUILDING_WIN.md` 是**上游 Thorium 遗留文档**（假设 `C:\src\chromium\src`、要 VS 2022、
无 `deploy_mcloud.py` 步骤），照它做会得到不含本仓库定制的构建 —— 已在文件头加了警示（缺陷 D91）。

## pak_src/ — .pak 资源工具（14 文件）

C 语言编写的 Chromium 资源包工具：
- `main.c` / `main.h` — CLI 入口。
- `pak_pack.c` / `pak_header.c` / `pak_file.c` — 打包、头部解析、文件操作。
- `pack.bat` / `unpack.bat` — Windows 快捷脚本。
- `binaries/` — **构建链真正会用的那几份**（上游 myfreeer 发布物 + Thorium 作者自编译的
  Linux/Windows/arm64 二进制）。

**构建链不编译 `pak_src/` 的 C 源码**（第7周期 D196 实测）：全仓唯一复制 `pak` 的动作在
`setup.sh:87-88` 与遗留 `win_scripts/setup.py:144-149`（后者按 D97 直接 REFUSED/exit 112），
两者复制的都是 `binaries/` 里的预编译二进制；`deploy_mcloud.py` 里没有任何 pak 步骤。
⇒ "源码已加固"只有在**重建过 `binaries/`** 之后才等于"工具已加固"。

- ✅ **Windows 侧已重建并验证**（2026-10-12 r11）：入口 `pak_src/binaries/rebuild_win.bat`
  只做转发，真正的实现是 `.bugreview/pak_rebuild.py`。它从 `pak_src_fixed/pak.c` 编
  `pak_msvc64.exe` / `pak_msvc32.exe`，**全部判据通过才落盘**：`/W4` 零警告、`/MT` 静态 CRT
  （产物不依赖 vcruntime140，实测无该导入）、`/Brepro` 连编两次逐字节相同、对 `out/mcloud`
  里 4 个真实 `.pak`（含 24 MB 的 `resources.pak`）解包→再打包**与原文件逐字节相同**、
  与仓库多文件版 `pak_src/*.c` 的参考实现**产物相同**、x86 与 x64 产物相同。
  清单 `pak_src/binaries/BUILDINFO.json` **故意不含构建时间戳** ⇒ 同输入重建零 diff。
  包装器 `pak_src/{pack,unpack}.bat` 与 `binaries/pak-win/{pack,unpack}.bat` 已改为
  **首选 `pak_msvc*.exe`**，在库的 MinGW 那对（早于仓库源码，不解 `.gz` 魔数）只在缺失时回退。
- ⛔ **Linux/ARM 那两份 ELF 不重建**：本项目只发布 Windows x64（ADR-003），它们属上游遗留材料。
  本机也确实没有 POSIX 编译器（gcc/clang/WSL 都不存在），所以 `Makefile`/`run_test.sh` 侧判据
  只能在 ubuntu CI 上真跑，本机一律报 SKIPPED 而不是假通过。
- ⚠ 写 `.bat` 的两条实测坑：**必须 CRLF + ASCII**（cmd 按 OEM 代码页读，中文 `rem` 会花屏，
  行尾 LF 会让解析错乱）；**不要把局部变量叫 `TMP`**——覆盖 `%TMP%` 会打乱 cmd 自身的临时文件
  逻辑，表现为 cl "返回 0 却不产出文件"。另：batch 里 `cmd | findstr` 抓编译输出在本机实测会让
  整个脚本静默中止（rc=255 且无报错），改成"重定向到文件再读"。

### pak_src_fixed/ — 现代 C11 单文件重写（另一位 C 工程师 `0bbabca` 引入，第7周期复核）

- `pak.c` — 消除严格别名 UB / `_snprintf` / `PATH_MAX` 等问题的等价重写版；`build_and_test.bat`
  是 MSVC 入口，`Makefile` + `run_test.sh` 是 POSIX 入口。
- **MSVC 必须带 `/utf-8` 编译**（缺陷 D192）：无 BOM 的 UTF-8 中文注释在 CP936 下会吞掉换行，
  警告行号整体错位（实测 4/4 条 C4996 指错代码）。**禁止用 `/wd4819` 闭掉**——那只掩掉症状。
  同理 `/D_CRT_SECURE_NO_WARNINGS` 会把 C4996 全部掩掉，"零警告"不代表干净。
- 本轮修掉的真实缺陷：D190（v5 头部 3 个 padding 取自脏堆 ⇒ 产物不可复现）、
  D191（`read_file` 少 1 字节 NUL ⇒ `sscanf` 堆越界读，ASan 实测）、
  D193（version=4 声明别名时**静默丢弃别名表还返回 0**，原工具是直接拒绝）。
- 门禁：`win_scripts/verify_sources.py` 现含 `check_pak_fixed_sources` /
  `check_pak_roundtrip`（真编译 + 确定性 + 与原始工具字节一致 + v4 别名拒绝 + 畸形输入）/
  `check_pak_asan`（POSIX 侧 ASan+LSan）。判据可红性由
  `.bugreview/pak_gate_red_control.py` 在**临时副本**上证明（不改工作树）。
  另有 `.bugreview/pak_fixed_verify.py`（MSVC + ASan + Red 对照）与
  `.bugreview/pak_fixed_diff.py`（19 组边界索引的新旧行为差分）。
- ⚠ **Windows 的 ASan 没有 LeakSanitizer**（实测 `ASAN_OPTIONS=detect_leaks=1` 直接以
  `detect_leaks is not supported on this platform` 退出）⇒ 本机"ASan clean"只证明**无越界**，
  不得写成"无泄漏"；泄漏判据只能在 POSIX 侧下。

## infra/ — 发布打包

- `infra/APPIMAGE/`、`infra/Flatpak/`、`infra/Arch_Linux/` — Linux 发行格式。
- `infra/portable/` — Portable 版（含 C 自解压包装器 `C/THORIUM-PORTABLE.sh.x.c`）。
- `infra/BRANDING`、`infra/mcloud_strings.grd` — 品牌资源。
- `infra/build_ffmpeg.sh`、`infra/build_polly.sh` — 依赖构建。
- `infra/google_api_keys-inc.cc` — Google API 密钥（公开密钥，维持入库）。

## arm/ — ARM 平台

- `arm/win_ARM_args.gn`、`arm/woa_arm.gni` — Windows on ARM 构建参数。
- `arm/mac_arm.gni`、`arm/setup_arm.sh` — 树莓派 / macOS ARM。
- 仅用于 Raspi 和 WoA；常规 Linux/macOS ARM 用仓库根文件即可。

## other/ — 补丁与工具

- `*.patch` 文件：按 `feature-name.patch` 命名，共 32 个。**当前构建链不应用任何 .patch**
  （`deploy_mcloud.py` 只跑定点注入脚本）；唯一引用者是遗留的 `win_scripts/setup.py`，而该脚本按约定禁止运行。
  因此这些补丁是**上游历史/参考材料**，不是构建输入。
- ⚠ 不要"顺手应用"这些补丁（缺陷 D75）：`mini_installer.patch` 与 D47 的修复同源重复——
  `mcloud_flags.txt` 进 `chrome.release` 现在由 `win_scripts/apply_installer_payload.py` 幂等写入，
  再打这个补丁会造成重复条目或冲突；`allow_manifest_v2_extensions.patch` /
  `add-hevc-ffmpeg-decoder-parser.patch` 同理，对应能力已由覆盖文件或上游默认提供。
  要改上游文件一律写 `apply_*` / `inject_*` 幂等脚本（见 D41 约定）。

## benchmark/ — 性能基准

- `bench_startup.ps1`、`bench_memory.ps1`、`bench_navigation.ps1`、`bench_size.ps1` — 四维基准。
  **`bench_memory.ps1` 除 K2 内存外，第5周期起同时输出 K2-CPU 驻留占用**（D145 填补了
  "仓库此前完全没有任何 CPU 占用率量具"的空白；`-NoCpu` 可关）。实现要点，改它之前先读：
  复用同一批 PID 与同一次 `Get-Process` 快照（**不引入第二套进程枚举**，避免重犯 D52/D55）；
  `TotalProcessorTime` 是累计值且本实例 PID 会在采样间变动，故用 Hashtable **按 PID 分别做差**；
  同时输出"占整机%"与"折合核数"两个口径，**跨机器比较必须看折合核数**（否则 24 核机器上的
  同一负载会显得比 8 核机器"轻"三倍）；计数器取不到即 `throw`——
  ⚠ 上游 Chromium 自己在这类地方用 `.value_or(0.0)` 把失败吞成 0
  （`chrome/browser/task_manager/sampling/task_group_sampler.cc:125`），**本仓不得照抄**；
  并有一道**单位自洽断言**（`|折合核数/逻辑核*100 − 占整机%| > 0.5` 即 FAIL），
  它拦住过首版把核数错存成"单核百分比"的 100 倍错误。
  K2 侧另有三处硬失败 + 采样条数自检（D138/D89）：取不到进程时旧实现会因 `$null/1MB == 0`
  输出"内存峰值 0 MB"并 `exit 0`，看起来像巨大改善。
- `run_baseline.ps1` — 基线采集。环境块的 GPU 字段**只认 PCI 适配器**并记 `VEN:DEV`（D139：
  旧实现 `Select-Object -First 1` 取到的是 MuMu 虚拟显示器，导致每份归档基线的 GPU 都是错的）。
- `tools/cdp.py` — **零依赖 CDP 客户端**（stdlib 手搓 WebSocket）。实操轮次的公共底座：
  `Tab.deep_text()`（穿透 shadow root，WebUI 必需）、`Tab.try_screenshot()`（证据不掀判据）、
  `activate_tab()`（全屏/PiP 要可信前台）、`kill_instance()`（按 profile 指纹，禁机器级清理）。
- `tools/r1_startup_check.py` / `r2_interaction_check.py` / `r3_content_media_check.py` /
  `r4_memory_stability_check.py` — 第4周期的**实操**五轮探针（真 DOM 核对、真拖拽、
  杀 GPU/渲染进程看恢复、真下载/打印/PiP/全屏、跨轮句柄与内存累积）。退出码统一
  0=判据成立 / 1=有判据不成立 / 2=环境不满足；**取不到数据一律非 0**（不得空值算绿）。
- `tools/check_features.py` — 构建产物特性校验；`tools/verify_builtin_flags.ps1` — flags 注入验证；`tools/bolt_pipeline.ps1`、`tools/pgo_collect.ps1` — 编译优化流水线。

## 构建快速参考

### 环境变量（必须设置）

```bash
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
# VS2026 ATL 头文件路径（必须添加）
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"
```

### Google API 密钥（运行时需要）

启动浏览器前必须设置 `GOOGLE_API_KEY`、`GOOGLE_DEFAULT_CLIENT_ID`、`GOOGLE_DEFAULT_CLIENT_SECRET`，否则会提示缺少密钥。
使用仓库根 `launch_browser.bat` 启动可自动设置。公开密钥亦入库于 `infra/google_api_keys-inc.cc`。

### 完整构建流程

```bash
# 0. 首次：拉取 Chromium M155 源码（已拉取可跳过）
fetch --nohooks chromium
cd src && git checkout tags/155.0.8059.40
# ⚠ 禁止给 sync 添加 --force --reset --delete_unversioned_trees（实证会清除
#   全部定制与 buildtools/win CIPD 二进制，见 M151 升级报告故障处置 2）
# ⚠ jobs 用 4：--jobs=16 实测会撞 googlesource HTTP 429 限流导致 sync 中断
gclient sync --shallow --jobs=4 --with_branch_heads --with_tags
gclient runhooks
# ⚠ runhooks 会按字面调用 python3：若解析到 WindowsApps 占位程序会全线失败，
#   需在真实 Python 目录内 mklink /H python3.exe python.exe 并置于 PATH 前
# ⚠ 首轮编译前必须拉 V8 builtins PGO profile，否则报 x64-rl.profile missing：
#   python v8/tools/builtins-pgo/download_profiles.py download --depot-tools <depot_tools>

# 1. 定点部署（deploy_mcloud.py 编排全部注入步骤，幂等）+ 生成构建 + 编译 + 安装包
cd $CR_DIR
python3 $THOR_DIR/win_scripts/deploy_mcloud.py
cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn   # 首次或配置变更时
gn gen out/mcloud --check
autoninja -C out/mcloud chrome mini_installer
```

### 增量与重配

- 修改源码后：`autoninja -C out/mcloud chrome`。
- 修改 args.gn 后：必须重新 `gn gen out/mcloud --check` 再编译。

### 关键构建参数（win_args_mcloud.gn）

| 参数 | 值 | 说明 |
|------|-----|------|
| `use_avx2` / `use_fma` | true | SIMD 基线（AVX2+FMA3） |
| `is_full_optimization_build` | true | -O3 优化 |
| `use_polly` / `use_bolt` | false | 接线已修复但依赖未落地（见规范 2.6 / 10.1） |
| `use_thin_lto` | true | ThinLTO |
| `v8_enable_maglev` / `v8_enable_turbofan` | true | V8 优化编译器 |
| `v8_enable_wasm_simd256_revec` | true | WASM SIMD256 向量化 |
| `proprietary_codecs` / `ffmpeg_branding` | true / "Chrome" | 专有编解码 |
| `enable_platform_hevc` | true | HEVC 硬件解码 |
| `enable_widevine` | false | CDM 未下载时禁用 |
| `enable_vulkan` | false | Windows 使用 D3D12 |
| `win_enable_cfg_guards` | true | Windows CFG 保护 |
| `enable_rlz` | true | 与 win_args_mcloud.gn 口径一致，决策见 `docs/decisions/ADR-001` |

### 其他要点

- 构建目录固定为 `out/mcloud`；构建配置 `win_args_mcloud.gn`。
- 启动标志 `mcloud_flags.txt`（仓库根）由 `chrome_main_delegate.cc` 内置加载。
- **feature params 语法**：`Feature:param/value/param/value`，value 必需。写成裸名（`Feature:a/b/c`）不报错，
  参数会被整段丢掉并退回上游默认值（缺陷 D51）。`.bugreview/flag_stability.py` 的 E 断言已按成对语法校验。
- **运行时是否真生效**：静态"声明位存在"只能证明名字存在。要核对实际生效集合，用
  `python .bugreview/flag_runtime_state.py`——浏览器经 `field_trial.cc:690` → `GetCommandLineFeatureOverrides()`
  把命令行 override 序列化进**子进程**命令行，从 `Win32_Process.CommandLine` 解析即可。注意该集合
  不含带 params（走 field trial 通道）的条目，"看不到"≠"没生效"。
- **同名 feature 双写时禁用侧胜出**（`base/feature_list.cc:449-452`，disable 先注册 + emplace 首条生效）。
  要把某项从禁用改为启用，必须**删掉** `--disable-features=` 行，追加 enable 行是无效实验（A/B 曾因此差点误判）。
- **基准与探针一律按"实例"而非"进程名"取数**（缺陷 D52/D55）。`Get-Process chrome` 会把用户自己开着的
  浏览器一起算进 K2，`Get-Process chrome | Stop-Process` 会杀掉它的会话。现统一以本次启动的
  `--user-data-dir` **叶子名**为指纹筛 PID（比完整路径稳——不依赖短名/长名是否一致；该路径差异本身
  尚未复现，见 D66-③）。硬规则：**取不到进程必须判 FAIL**，禁止返回 0 值式的"成功"。
- **PowerShell 数字与字符串不能用 `+` 拼接**：`[math]::Round(...)+'|'+$n` 抛
  "无法将值 '|' 转换为 System.Double"，而宽 `except` 会把它吞成"0 MB"（D66-① 已独立复现）。格式化一律用 `-f`。
- **注入器一律"正文比对式升级器"**（缺陷 D62/D64/D67）：禁止用"某标志串是否存在"判定已应用——
  那会让树内正文永远停在旧版，输出却自称 already up to date。加载器还必须在正文一致时**继续校验调用点**。
- Python 静态检查已引入 `ruff`（`python -m ruff check --select F,E9,B,SIM win_scripts benchmark .bugreview`）；
  仓库此前没有任何 Python linter 在跑。真阳性（B023/B905 等）逐条判真伪后再修。
- **源码树身份现在是机器判定**（第7周期收口，缺陷 D186）：`win_scripts/tree_check.py::require_tree()`
  读 `<CR_DIR>/chrome/VERSION` 与仓库声明的 `KERNEL_MAJOR` 比对，不符即 exit 114 并点名是不是
  M151 回滚参考树；`deploy_mcloud.py` 开工第一件事就是它，`apply_restart_cmdline.py` 单跑也拦。
  内核升级 rebase 时**必须同步改 `KERNEL_MAJOR`**（这是新的单点真相）。
  历史约定仍然有效：
- **多棵源码树时 `deploy_mcloud.py` 必须显式设 `CR_DIR`**：其默认值是 `D:\wxmuma\chromium-src\src`（M151 树），
  在 155 树下不设变量就会把定制部署到旧树（2026-10-10 实际踩到；因全部步骤幂等未致损）。
- **GN 里 config 的正文改动 = 全树重编**（缺陷档案 D74 实测）：只换 `config("polly")` 的写法
  （`use_polly=false` 下展开为空）也让 `gn gen` 后 ninja 给出 51,296 步计划（约 3 小时）。
  因此"把注释/写法改正确"这类零收益改动必须与真实改动同批落地，不要为它单开一次全树重编。
- **跑基准/探针前先清残留实例**：孤儿 chrome 会锁住 `out/mcloud` 里的 DLL，
  实测让链接以 `lld-link: failed to write ./dxcompiler.dll: permission denied` 失败（D71）。
- CI：`.github/workflows/release.yml`（发布，push `v*` tag 触发）+ `.github/workflows/verify.yml`（源码验证，push/PR 触发）。

## 性能优化参考

- 设计文档：`docs/superpowers/specs/2026-06-19-performance-optimization-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-19-performance-optimization.md`
- 代码审查修复：`docs/superpowers/specs/2026-06-20-code-review-fixes.md`
- 架构规范：`docs/architecture/performance-build-technical-spec.md`
- 开发进度：`docs/progress.md`

## 编码约定

- **品牌名称**：使用 Chromium 默认品牌名（不修改）。
- **文件命名**：小写加下划线（如 `mcloud_flag_entries.h`）。
- **PowerShell 编码**：含中文的 `.ps1` 必须存为 **UTF-8 with BOM**（PowerShell 5.1 对无 BOM 文件按 GBK 解析会直接语法失败；benchmark/ 与 tools/ 已批量修复，见 `docs/tasks/bug-review-pak-src-defects.md` D38）。
  该约定现已机器化：`python3 win_scripts/verify_sources.py` 会检查全部 `.ps1` 的 BOM、`param` 位置并用
  PowerShell 的 AST 解析器实跑一遍（非 Windows 平台自动 SKIP，空输入一律判 FAIL）。
- **PowerShell 五条语言坑（第3周期扩展轮 D81/D82/D83/D89；第4条第5周期 D145；第5条第6周期收口轮实测）**：
  ① **`param(...)` 必须是脚本第一条语句**（前面只能有注释/空行）。写在赋值语句之后不会报语法错，
  而是把 `param` 当命令名抛非终止错误 → **参数块整体作废、传入的 `-OutDir/-ChromeExe` 被静默丢弃，
  脚本仍退出 0**。
  ② **函数内 `$x += …` 不会累加到脚本级变量**（PowerShell 作用域：读父级、写即建本地副本）。
  聚合结果必须 `$script:results += …`，或让函数返回对象由调用方收集。
  累加完必须**自检条数**：`$results.Count -ne <预期门禁数>` 直接判 FAIL——否则"汇总为空"会表现成
  `ALL PASS`（这是缺陷 D89，本仓库最严重的一次假绿，位置在"门禁的门禁"）。
  ③ **`[System.Diagnostics.Process]` 没有 `Wait(int)`**，只有 `WaitForExit(int)`；
  中文输出被管道/文件捕获时需显式
  `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false`，且要排在**首条中文输出之前**。
  ④ **`-f` 的优先级高于 `+`**：`"A{0}" + "B{1}" -f $x, $y` 只会格式化 `B` 那一段，
  **`A` 里的占位符原样印出来**（不报错）。必须写成 `(("A" + "B") -f $x, $y)`。
  这是 D66-① 的同族变体，第5周期给 K2-CPU 的报错文案做 Red 验证时靠"占位符没被替换"发现。
  另：正则里 `\|` 是**转义竖线**（匹配字面量 `|`），要匹配"反斜杠或串尾"必须写 `(\\|$)`——
  D137 就是这个错，导致"你在测 M151 旧树"的护栏在 9 个脚本 10 处**从未触发过**。
  ⑤ **变量名大小写不敏感 ⇒ typed `param` 会被自己的局部变量反噬**：
  `param([int]$Pad)` 之后再写 `$pad = "a" * $Pad`，`$pad` 与 `$Pad` 是**同一个变量**，
  于是把 1300 个字符往 `[int]` 上强转，报 `无法将值"aaaa…"转换为类型 System.Int32`
  （`$ErrorActionPreference='Stop'` 下整个脚本停在第 11 行）。第6周期收口轮的取证脚本实测；
  同族：D83（函数内 `+=` 不写回脚本作用域）。写取证脚本时局部名与参数名不要只差大小写。
- **安装包装器现在有单实例互斥**（D132，第7周期收口真正实现；此前档案里一直是「待跟进」，
  而回退轮交来的"判据"验证的是一个不存在的功能）：命名互斥体
  `Global\MCloudBrowserSetup`（受限环境退回 `Local\`，建不起只 WARN 不阻断），
  拿不到即 `rc=2`。**提权自举带 `--elevated-child` 跳过抢锁**，否则父进程持有锁等待子进程时
  会把系统级安装自己挡死（D189，本机 EnableLUA=0 跑不到真实 UAC 分支，仍待有 UAC 的机器复验）。
  判据：`.bugreview/test_mutex_single_instance.py`（Green=工作树、Red=HEAD 变体，
  编译变体走 `build_setup_exe.py --source`，**不改工作树里被跟踪的源文件**）。
  GPU 降级验证：`.bugreview/gpu_degradation_probe.py`（三场：禁用 GPU→WARP 软件渲染、
  `--use-angle=swiftshader`→SwiftShader、默认对照→硬件加速；页面判据用 `chrome://version`
  与 `data:` URL，不依赖外网内容）。
- **判据必须命中它声称的那个东西**（第7周期 D179/D180/D181/D183/D184，五条同族）：
  ① 子串匹配 feature 名当成 GPU 后端（`gpu_probe` 的 `d3d11 in 命令行` 命中的是
  `MediaFoundationD3D11VideoCaptureZeroCopy` 和 `--disable-features=D3D12VideoDecoder`，
  与 ANGLE 后端无关，且两者同时为 True）；② 量具取不到数据时 `return 0`，
  于是"实例死了/查不到内存"表现为 `0 ≤ 0 + 120` ⇒ 泄漏判据必然成立；
  ③ 工作负载没跑起来（一个标签都没开成）时峰值≈基线 ⇒ 空转也 PASS；
  ④ 身份检查按 `exe 同目录` 找清单，而安装版在版本目录 ⇒ KPI 日志里长期写着
  "内置优化不生效，结果无意义"（实测照样 exit 0）；⑤ 结论句子比较的两个布尔值
  跟句子说的不是一回事。⇒ 写判据时先问：**它在什么输入下会红？**
  答不出并给出一次实测的红，就还没有判据。
- **"名字在树里"≠"编译得进来"≠"这一行有净效果"**（第7周期，缺陷 D177/D178/D182）：
  三层分别由 `survival_check.py`（存在性）、`guard_audit.py`（预处理守卫 + 已生成
  buildflags 实际取值 + **平台有效默认值**）、`flags_lint.py --stab --guard`（pin 还是真优化）判定。
  内核升级后三条都要跑；`guard_audit` 需要源码树与 `out/mcloud`（或 `.gni` 回退路径）。
  ⚠ 不要用"放大 `git grep` 上下文"来读跨行默认值：`-A8` 实测把邻居声明的
  `kDefault*Param` 卷进同一个块，制造 40 条错值 —— 只能读整文件按括号配平截取。
- **发布链一致性现在是机器判定**（第7周期，`python .bugreview/release_chain_check.py`）：
  仓库 `mcloud_flags.txt` / 打包暂存载荷 / 已安装实例三处指纹任一不一致即 rc=1，
  并区分"只差注释"与"开关集合不同"。这条链断过 3 次（D102/D175/第6周期 §8.2），
  第 4 次就是本周期改注释触发的。**修法只有重打包 + 干净安装复验，手工 copy 是 D175 的形态。**
- **测试不得写入发布产物目录（缺陷 D99 纪律）**：会改写被测文件的测试（`loader_edge_test2/3` 要重写 `mcloud_flags.txt`）必须在**硬链接沙箱**里跑，不能把 `LOADER_TEST_OUT` 指到 `out/mcloud`。`final_gate_matrix.ps1` 会自动建 `out/mcloud_loader_test`（链运行时文件、跳过 args.gn/.ninja_log/build.ninja 与文件数>1000 的构建中间目录）。中断的测试曾在发布目录留下 106 KB/300 KB 的假 flags 文件，让后续门禁拿测试语料当生产配置测量。测试脚本里有「发现构建特征文件即 REFUSED/exit 2」的前门；确需在生产目录上跑，显式设 `MCLOUD_ALLOW_LOADER_TEST_ON_BUILD_DIR=1`。
- **基准/工具脚本不得写死被测树**：`benchmark/*.ps1` 与 `benchmark/tools/*` 的默认对象改为
  `$env:MCHROME_EXE` / `$env:MCHROME_OUT`（再退回 `D:\wxmuma\chromium-src-155\src\out\mcloud`），
  并在开头打印**被测身份**（exe/dll 绝对路径、字节数、mtime、同目录 `mcloud_flags.txt` 是否存在），
  路径命中 M151 回滚树特征时 `Write-Warning`。多棵源码树并存时，"结果归属到哪棵树的产物"
  必须写在日志里，不能靠调用者记得自己传了什么（缺陷 D86/D72 同族）。
  ⚠ 该护栏的正则曾写成 `chromium-src(\|$)`（`\|` 是转义竖线，匹配字面量 `|`）而**从未触发过**，
  第5周期 D137 已在 9 个脚本 10 处改为 `(\\|$)`；`benchmark/tools/*.py` 侧的 `MCHROME_EXE`
  纪律仍只部分落实（D141）。
- **Python 判据脚本三条语言坑（r6，2026-10-12 实测）**：
  ① **`subprocess.run(..., errors="replace")` 会隐式打开文本模式**——CPython 里
  `encoding`/`errors`/`text`/`universal_newlines` 任一给定即 `text_mode=True`，于是 `stdout` 变成
  `str`，后面那句 `.decode()` 直接 `AttributeError`。想要字节就**什么都别传**；
  这也是 `build_setup_exe.py` 里"用 `errors="replace"` 兜住奇数字节"那段注释的真实前提（它确实在文本模式下工作）。
  ② **打印超出代码页的字符会抛 `UnicodeEncodeError` 并把已缓冲的日志整段吞掉**：本机默认 stdout 是 cp936，
  `⇒`（U+21D2）不在其中 → 脚本崩在 print，而 stdout 有缓冲，**崩溃前跑出来的结论一行都看不到**。
  判据脚本要么开头 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，要么把断言用的
  needle 与展示文字分开——**判据本身不依赖控制台编码**（`installer_arg_test.py` 对同一句中文
  同时试 utf-8 / gbk 两种字节，所以它在任何代码页下都不会假红，这族问题的源头见 D66-①）。
  ③ **`Where-Object` 只匹配到一条时返回标量字符串**，`$names[0]` 取到的是**第一个字符**而不是元素，
  于是 `GetManifestResourceStream("m")` 返回 null，看起来像"资源不存在"。PowerShell 里凡是
  "管道结果按下标取"的位置都要 `@(...)` 强制成数组（同族：D83 函数内 `+=` 不写回、D140 首检复检指纹不一致）。
- **第6轮回退登记（2026-10-12，D164–D169，勿重犯）**：另一模型 r6 之后的改动经复核后**整体回退**
  （详录 `docs/tasks/bug-review-cycle5-report.md`「续 2」；其完整改动留在 `.cycle6/cycle6_full_work.patch`）。
  可复用的五条：
  ① **`csc` 的 `/version` 是"打印编译器版本并退出"**，没有 `/version:x.y.z` 设程序集版本的用法——
     要写文件版本必须生成 `Assembly*Version` 特性文件同批编译（否则 csc 返回 0 却**不产出文件**）。
  ② **判据的污染自检必须可满足**：不能要求一个被它自己前提排除的状态
     （它把进程检查写成 `after[系统级] > 0`，而用例 C 的前提就是 `before[系统级] == 0`）。
  ③ **量具不得在被测窗口内采样**：全进程树 CIM 枚举 50–200 ms/次，插进 `WaitForInputIdle`
     轮询间隙会把 K1 从 45 ms 撑到实测 607 ms，并在启动快于轮询间隔时让基准自杀。
     某指标给不出来就不要用恒等式假装给出来了（它那条"单位自洽"是 `x − x`，永不触发；
     可用的是 `cpuSec ≤ 逻辑核 × 墙钟秒` 这类有物理意义、可能失败的界）。
  ④ **`gn gen` 必须用与成功构建一致的环境**（`DEPOT_TOOLS_WIN_TOOLCHAIN=0` + `vs2026_install` +
     `GYP_MSVS_OVERRIDE_PATH` + atlmfc `INCLUDE`）。`-imsvc` 包含路径会被烘进 `build.ninja`，
     环境不对 ⇒ 每个编译命令行都变 ⇒ **全树失效**（实测 `ninja -n` 51,361 步 + libc++
     `'new.h' file not found`）。动手前先 `ninja -n` 数步数（D74）。
  ⑤ **门禁的输入集合必须能从干净检出复现**：`.bugreview/` 下只入库 `*.py`，
     放一份 `.ps1` 进那里会让 `verify_sources.py` 的 `.ps1` 计数凭空 +1，
     接手方一条判据都复现不了（同 `a291812`/`bf4e63f` 的"悬空引用"族）。
     ⚠ 反过来，**入库的**共享脚本让计数变化是正常且必须写进文档的：第7周期新增
     `benchmark/tools/mcloud_flags_lookup.ps1`（缺陷 D183 的修法），计数 44→45。
     另：判据日志必须自己落盘——我批量跑时那次 rc=1 因为把输出丢进 `/dev/null` 而至今无法归因。
- **本机硬件身份（第5周期 D143 实测钉死，勿再按名称推断）**：
  | 项目 | 值 |
  |---|---|
  | CPU | Intel i9-14900HX，**24 核 / 24 逻辑处理器**（规格 24C/32T ⇒ **超线程在 BIOS 中关闭**，D150） |
  | 独显 | **NVIDIA GeForce RTX 4070 Laptop GPU**（Ada，PCI `VEN_10DE&DEV_2860`，8 GB，驱动 610.62） |
  | 核显 | Intel UHD Graphics（Raptor Lake，`DEV_A788`，驱动 32.0.101.6790） |
  | 显示器 | 由**独显**驱动（只有 NVIDIA 适配器报告活动显示模式）；AOC2703 外接 2560x1440@170Hz + TMA2021 内嵌 |
  | 另有 | MuMu / GameViewer 两个**虚拟显示适配器**（`ROOT\DISPLAY\*`，非 PCI），排在真实显卡之前 |

  ⚠ **本机 WMI `Win32_VideoController.Name` 与 PnP `DeviceDesc` 都错报 "NVIDIA GeForce GTX 1050 Ti"**，
  根因是注册表 `Enum\PCI\VEN_10DE&DEV_2860&…\4&3a9dcb36&0&0008` 的 `DeviceDesc` 被写成**字面量**
  （正常驱动安装是 `@inf,%key%;名称` 间接形式），即这块卡被人为改过名。该错误名称经
  `DXGI_ADAPTER_DESC.Description` 传进 Chromium，所以 chrome://gpu 与 WebGL 的
  `UNMASKED_RENDERER_WEBGL` 都显示 `NVIDIA GeForce GTX 1050 Ti (0x00002860)`——**名字错、设备号对**。
  Chromium 的 `software_rendering_list.json` / `gpu_driver_bug_list.json` 按 **PCI vendor+device ID**
  匹配而非按名字，故规避规则命中的是 Ada 的正确条目（实测已应用
  `Disable VP9 k-SVC video decoding on non-Intel GPUs`，crbug.com/1508379）。
  > **纪律：不要用显卡名称推断硬件能力。** 任何"某卡不支持 X"的判断必须以 PCI 设备号 /
  > `nvidia-smi` / chrome://gpu 的能力清单为准。D118 曾据错误名称把**实测正确的**
  > `av1 powerEfficient=true` 判为"不足以采信"，而 chrome://gpu 硬解清单里明确有
  > `Decode av1 profile main: 128x128 to 8192x8192`——Pascal 不可能有这条。
  > 同理，`Get-CimInstance Win32_VideoController | Select-Object -First 1` 取到的是
  > **MuMu 虚拟显示器**，D139 之前每份 KPI 基线的 GPU 字段都是错的。
- **补丁位置**：`other/` 目录，命名 `feature-name.patch`。
- **文档位置**：`docs/architecture/`（架构）、`docs/dev-logs/phase{N}-dev-log.md`（开发日志）、`docs/decisions/ADR-{NNN}-{title}.md`（决策记录）、`docs/tasks/`（任务文档）。
  缺陷档案：`docs/tasks/bug-review-pak-src-defects.md`（D1–D196 索引）+ 各周期详版
  `bug-review-cycle{3,4,5,6}-report.md`。**第5周期（D121–D155，2026-10-12）详版见
  `docs/tasks/bug-review-cycle5-report.md`**，含硬件取证、chrome://gpu 实测、Red→Green 验证记录
  与 12 条待跟进项；该文件末尾的 **「续：r6 收口轮执行记录」** 登记 D156–D163，
  是对第5周期交接件的复核（哪些成立、哪些要打折）、**重打包后的新发布物哈希**、
  "7 条安装器修复当时一条都没执行过"的处置（`installer_arg_test.py`），以及
  **干净安装复验的实测结果**（D162 卸载必卡、D163 本机 `EnableLUA=0` 的结论边界）。
  **第7周期（D177–D184，2026-10-12）详版见 `docs/tasks/bug-review-cycle7-report.md`**：
  内存/CPU/GPU 三个方向的全局审查。要点 —— 52 项 feature 全部编译得进来（0 死声明）、
  pin 实为 15 项 / 真正新增 35 项（D177 更正 D171 的 14/34）；未发现泄漏
  （25 标签×4 轮，轮间 +0.7 MB）；50 标签驻留 CPU 0.01 折合核；渲染实测走
  **ANGLE D3D11 + 独显（设备号 0x00002860）**；修掉 5 个会造成假绿的判据缺陷
  （D179/D180/D181/D183/D184）；新增 `guard_audit.py`（平台守卫与有效默认值）、
  `release_chain_check.py`（发布链一致性，当前因只改注释而红，属预期）。
  再往后的 **「续 2：第 6 轮改动的处置与整体回退」** 登记 D164–D169：另一模型的 12 文件改动
  里哪些我核过是对的、哪 3 条是阻断级缺陷（含实测复现）、以及为什么整体回退到 `96267cd`
  与回退后的全套测试结果。
- **修改 build/ 目录前**：必须备份 `compiler_opt.gni` 等自定义文件。
- **禁止**：不要用 `git checkout -- build/` 批量回退（会删除自定义文件）；修改 GN 参数后必须重新 `gn gen out/mcloud --check`。
- **已知坑（口径已更正 2026-10-10）**：`--js-flags` 内的 V8 标志**统一写下划线形式**（`--invocation_count_for_maglev=...`）。旧断言「连字符写法在 M151 静默失效」与源码不符：`v8/src/flags/flags-impl.h:19` 的 `NormalizeChar` 把 `_` 归一为 `-` 并用于标志名比较，两种写法应等价；Chromium 侧对未知 js-flags 静默忽略，故该点无法用 stderr 反证（缺陷 D49，定论需 `autoninja d8`）。沿用下划线写法是安全的默认，不要再以「连字符会失效」为依据做判断；Polly/BOLT 需先接线再启用（见 `win_args_mcloud.gn` 注释；注意 BOLT 官方仅支持 ELF/Mach-O，Windows PE 路线待核实，见规范 10.1 与缺陷档案）。
