# AGENTS.md — MCloud Browser 仓库导航

本文件为 AI Agent 提供仓库导航：源码根职责、核心修改文件定位、构建流程和编码约定。
修改任何代码前先阅读本文件，避免无效探索。

## 项目简介

MCloud Browser 是基于 Chromium（当前 M151，151.0.7922.x，硬件基线 AVX2+FMA3）的高性能 Windows 浏览器分支，
通过 AVX2 原生编译 + 运行时优化标志（`mcloud_flags.txt`，启动时内置加载；
2026-10-09 实测 63 条开关行 = 60 项 feature + 3 项普通开关）+ 编译时优化栈提供极致流畅体验。
本仓库**不是完整 Chromium 源码树**，而是存放覆盖文件（override files）、补丁、构建脚本和打包配置。
完整构建需先将本仓库文件复制到外部 Chromium 源码树（`$CR_DIR`，默认 `D:\wxmuma\chromium-src\src`）再编译。

## 技术栈

| 组件 | 说明 |
|------|------|
| Chromium M151 | 浏览器内核（tag 151.0.7922.x） |
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

## src/ — Chromium 覆盖文件（核心）

112 个文件，修改浏览器行为的主战场。按子目录定位：

### src/chrome/（60 文件，最高频修改区）
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
8. **`build_win.py`** — 执行 gn/autoninja 编译。
9. 辅助：`version.py`（版本管理）、`clean.py`、`reset_depot_tools.py`、`tot.py`/`trunk.py`（ToT 同步）。
10. **`verify_sources.py`** — 最小源码验证：win_scripts/ 全部 Python 脚本语法检查 + 关键脚本存在性 + pak_src/ C 源码检查。修改构建脚本后运行 `python3 win_scripts/verify_sources.py`（退出码 0=PASS / 1=FAIL）；已接入 CI（`.github/workflows/verify.yml`，push/PR 自动运行）。

注意：`setup.py` 为遗留全量覆盖脚本，已被定点注入取代，勿在新 Chromium 树上运行（会污染源码树）。

前置文档：`docs/BUILDING_WIN.md`。

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

- `*.patch` 文件：按 `feature-name.patch` 命名，修改 Chromium 源码的补丁集合。
- `other/build_ffmpeg.py` — FFmpeg 构建工具。
- 关键补丁：`mini_installer.patch`（安装包打包 mcloud_flags.txt）、`allow_manifest_v2_extensions.patch`、`add-hevc-ffmpeg-decoder-parser.patch`。

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
# 0. 首次：拉取 Chromium M151 源码（已拉取可跳过）
fetch --nohooks chromium
cd src && git checkout tags/151.0.7922.99
# ⚠ 禁止给 sync 添加 --force --reset --delete_unversioned_trees（实证会清除
#   全部定制与 buildtools/win CIPD 二进制，见 M151 升级报告故障处置 2）
gclient sync --shallow --jobs=16 --with_branch_heads --with_tags
gclient runhooks

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
- **补丁位置**：`other/` 目录，命名 `feature-name.patch`。
- **文档位置**：`docs/architecture/`（架构）、`docs/dev-logs/phase{N}-dev-log.md`（开发日志）、`docs/decisions/ADR-{NNN}-{title}.md`（决策记录）、`docs/tasks/`（任务文档）。
- **修改 build/ 目录前**：必须备份 `compiler_opt.gni` 等自定义文件。
- **禁止**：不要用 `git checkout -- build/` 批量回退（会删除自定义文件）；修改 GN 参数后必须重新 `gn gen out/mcloud --check`。
- **已知坑**：V8 flags（--js-flags 内）须用 M151 **下划线**命名格式（`--invocation_count_for_maglev=...` 等），连字符旧格式在 M151 静默失效（mcloud_flags.txt 55-57 行实证注释）；Polly/BOLT 需先接线再启用（见 `win_args_mcloud.gn` 注释；注意 BOLT 官方仅支持 ELF/Mach-O，Windows PE 路线待核实，见规范 10.1 与缺陷档案）。
