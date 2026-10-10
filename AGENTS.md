# AGENTS.md — MCloud Browser 仓库导航

本文件为 AI Agent 提供仓库导航：源码根职责、核心修改文件定位、构建流程和编码约定。
修改任何代码前先阅读本文件，避免无效探索。

## 项目简介

MCloud Browser 是基于 Chromium（当前 M155，155.0.8059.40，硬件基线 AVX2+FMA3）的高性能 Windows 浏览器分支，
通过 AVX2 原生编译 + 运行时优化标志（`mcloud_flags.txt`，启动时内置加载；
2026-10-10 (r3) 实测 56 条开关行 = 53 项 feature + 3 项普通开关；r2 时为 63 条 = 60 + 3，差额是 D48 清理掉的 7 条上游不存在的条目）+ 编译时优化栈提供极致流畅体验。
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
| `pak_src/` | C | Chromium `.pak` 资源包打包/解包命令行工具源码 |
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
   相应地加载器 v7 在 exe 同目录读不到时会回退到 `exe_dir\<版本号>\mcloud_flags.txt`。
   **发布前必须做一次干净安装复验**（`mini_installer.exe --system-level` 装到 Program Files，
   断言文件落地 + 与仓库字节一致 + 对安装后的二进制跑 `flag_runtime_state.py` 得到 51+2 回显，
   然后卸载）。只看门禁绿灯不足以证明安装包正确。
8. **`build_win.py`** — 执行 gn/autoninja 编译。
9. 辅助：`version.py`（版本管理）、`clean.py`、`reset_depot_tools.py`、`tot.py`/`trunk.py`（ToT 同步）。
10. **`verify_sources.py`** — 最小源码验证：win_scripts/ 全部 Python 脚本语法检查 + 关键脚本存在性 + pak_src/ C 源码检查。修改构建脚本后运行 `python3 win_scripts/verify_sources.py`（退出码 0=PASS / 1=FAIL）；已接入 CI（`.github/workflows/verify.yml`，push/PR 自动运行）。

注意：`setup.py` 为遗留全量覆盖脚本，已被定点注入取代，勿在新 Chromium 树上运行（会污染源码树）。
该约定现已**机器化**（缺陷 D97，2026-10-11）：脚本在没有上游对应动作的位置直接拒绝执行，
默认 `REFUSED` + 退出码 112 并指向 `deploy_mcloud.py`；只有显式设 `MCLOUD_ALLOW_LEGACY_SETUP=1` 才会继续。
`--help` 仍正常返回 0。

前置文档：**本文件下面「构建快速参考」一节 + `docs/progress.md` §5.1**（两者一致，是权威步骤）。
⚠ `docs/BUILDING_WIN.md` 是**上游 Thorium 遗留文档**（假设 `C:\src\chromium\src`、要 VS 2022、
无 `deploy_mcloud.py` 步骤），照它做会得到不含本仓库定制的构建 —— 已在文件头加了警示（缺陷 D91）。

## pak_src/ — .pak 资源工具（14 文件）

C 语言编写的 Chromium 资源包工具：
- `main.c` / `main.h` — CLI 入口。
- `pak_pack.c` / `pak_header.c` / `pak_file.c` — 打包、头部解析、文件操作。
- `pack.bat` / `unpack.bat` — Windows 快捷脚本。

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
- `run_baseline.ps1` — 基线采集。
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
- **PowerShell 三条语言坑（第3周期扩展轮实测，D81/D82/D83/D89）**：
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
- **测试不得写入发布产物目录（缺陷 D99 纪律）**：会改写被测文件的测试（`loader_edge_test2/3` 要重写 `mcloud_flags.txt`）必须在**硬链接沙箱**里跑，不能把 `LOADER_TEST_OUT` 指到 `out/mcloud`。`final_gate_matrix.ps1` 会自动建 `out/mcloud_loader_test`（链运行时文件、跳过 args.gn/.ninja_log/build.ninja 与文件数>1000 的构建中间目录）。中断的测试曾在发布目录留下 106 KB/300 KB 的假 flags 文件，让后续门禁拿测试语料当生产配置测量。测试脚本里有「发现构建特征文件即 REFUSED/exit 2」的前门；确需在生产目录上跑，显式设 `MCLOUD_ALLOW_LOADER_TEST_ON_BUILD_DIR=1`。
- **基准/工具脚本不得写死被测树**：`benchmark/*.ps1` 与 `benchmark/tools/*` 的默认对象改为
  `$env:MCHROME_EXE` / `$env:MCHROME_OUT`（再退回 `D:\wxmuma\chromium-src-155\src\out\mcloud`），
  并在开头打印**被测身份**（exe/dll 绝对路径、字节数、mtime、同目录 `mcloud_flags.txt` 是否存在），
  路径命中 M151 回滚树特征时 `Write-Warning`。多棵源码树并存时，"结果归属到哪棵树的产物"
  必须写在日志里，不能靠调用者记得自己传了什么（缺陷 D86/D72 同族）。
- **补丁位置**：`other/` 目录，命名 `feature-name.patch`。
- **文档位置**：`docs/architecture/`（架构）、`docs/dev-logs/phase{N}-dev-log.md`（开发日志）、`docs/decisions/ADR-{NNN}-{title}.md`（决策记录）、`docs/tasks/`（任务文档）。
- **修改 build/ 目录前**：必须备份 `compiler_opt.gni` 等自定义文件。
- **禁止**：不要用 `git checkout -- build/` 批量回退（会删除自定义文件）；修改 GN 参数后必须重新 `gn gen out/mcloud --check`。
- **已知坑（口径已更正 2026-10-10）**：`--js-flags` 内的 V8 标志**统一写下划线形式**（`--invocation_count_for_maglev=...`）。旧断言「连字符写法在 M151 静默失效」与源码不符：`v8/src/flags/flags-impl.h:19` 的 `NormalizeChar` 把 `_` 归一为 `-` 并用于标志名比较，两种写法应等价；Chromium 侧对未知 js-flags 静默忽略，故该点无法用 stderr 反证（缺陷 D49，定论需 `autoninja d8`）。沿用下划线写法是安全的默认，不要再以「连字符会失效」为依据做判断；Polly/BOLT 需先接线再启用（见 `win_args_mcloud.gn` 注释；注意 BOLT 官方仅支持 ELF/Mach-O，Windows PE 路线待核实，见规范 10.1 与缺陷档案）。
