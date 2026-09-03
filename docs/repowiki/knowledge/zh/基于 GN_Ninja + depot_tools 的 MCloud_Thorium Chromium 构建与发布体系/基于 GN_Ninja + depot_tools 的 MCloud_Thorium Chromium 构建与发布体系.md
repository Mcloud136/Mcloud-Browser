---
kind: build_system
name: 基于 GN/Ninja + depot_tools 的 MCloud/Thorium Chromium 构建与发布体系
category: build_system
scope:
    - '**'
source_files:
    - gclient
    - args.gn
    - build.sh
    - build_win.py
    - build_mac.sh
    - build_android.sh
    - .github/workflows/release.yml
    - .github/workflows/verify.yml
    - infra/BUILDER
    - infra/DEBUG/debug_args.gn
    - arm/raspi/raspi_args.gn
    - arm/android/arm64_args.gn
    - other/AVX2/AVX2_args.gn
    - other/AVX512/AVX512_args.gn
    - win_scripts/build_win.py
    - win_scripts/apply_avx2_baseline.py
    - win_scripts/deploy_mcloud.py
    - infra/Arch_Linux/PKGBUILD
    - infra/Flatpak/com.mcloud.browser/build-aux/build.sh
    - infra/APPIMAGE/make_appimage.sh
---

## 1. 构建系统概览

本项目是 Chromium 定制分支（MCloud/Thorium），以 `gclient` + `depot_tools` 管理源码，使用 Chromium 原生 GN/Ninja 作为编译系统，并通过顶层 shell/Python 脚本统一编排不同平台（Linux、Windows、macOS、Android、ARM/Raspberry Pi）的构建流程。CI 仅负责轻量验证与打 Tag 后发布产物上传。

- **源码同步**：根目录 `gclient` 声明只拉取 `src`（chromium/src.git），并启用 `checkout_pgo_profiles`；`depot_tools/` 提供本地化的 `autoninja` 等工具。
- **编译入口**：各平台通过 `build.sh` / `build_win.py` / `build_mac.sh` / `build_android.sh` 调用 `autoninja -C out/mcloud mcloud_all ...`，输出统一位于 `out/mcloud`。
- **GN 参数**：默认优化配置集中在根级 `args.gn`（SSE4.2/AVX、LTO、V8 优化、Widevine、HEVC/H265、PGO 等），各平台变体在 `arm/`、`other/Mac/`、`other/AVX2/`、`other/AVX512/`、`infra/DEBUG/` 下以独立 `.gn`/`.gni` 文件覆盖。
- **打包**：Linux 直接调用 `chrome/installer/linux:stable_deb`、`stable_rpm`；Windows 调用 `setup mini_installer`；macOS 调用 `chrome/installer/mac minidump_stackwalk` 后再由 `create_dmg.sh` 生成 DMG；另有 Arch PKGBUILD、Flatpak、AppImage、便携包等发行版封装。
- **CI**：GitHub Actions 仅包含两个 workflow —— `verify.yml`（PR/push 时运行 `win_scripts/verify_sources.py` 校验源码完整性）、`release.yml`（push `v*` tag 时读取 `docs/superpowers/specs/*release-notes*.md` 作为 Release Notes，并将 `mini_installer.exe` 及 SHA256 附件上传到 GitHub Release）。

## 2. 关键文件与目录

| 类别 | 关键路径 | 作用 |
|---|---|---|
| 源码清单 | `gclient` | 定义只拉取 chromium/src 及目标 OS/CPU |
| 默认 GN 参数 | `args.gn` | Linux x64 默认优化开关（SIMD、LTO、V8、Widevine、HEVC、PGO） |
| 平台构建脚本 | `build.sh`、`build_win.py`、`build_mac.sh`、`build_android.sh` | 统一调用 autoninja 构建 mcloud_all 及对应 installer |
| ARM/AArch64 变体 | `arm/*.gn`、`arm/android/*.gn`、`arm/raspi/raspi_args.gn`、`arm/setup_arm.sh` | 为 Raspberry Pi、WoA、Android ARM 提供专用 GN 参数与补丁 |
| 其他 CPU 变体 | `other/AVX2/AVX2_args.gn`、`other/AVX512/AVX512_args.gn`、`other/SSE2/..` | 按指令集切分二进制分发 |
| Windows 构建编排 | `win_scripts/build_win.py`、`apply_avx2_baseline.py`、`apply_mcloud_source_defaults.py`、`deploy_mcloud.py` | 同步源码、应用补丁、设置基线、调用 autoninja、生成安装包 |
| 调试/开发构建 | `infra/DEBUG/debug_args.gn`、`build_debug_linux.sh`、`build_debug_win.sh` | 关闭 LTO/strip、开启 dcheck、符号级别提升 |
| 打包/发行 | `infra/BUILDER`、`infra/Arch_Linux/PKGBUILD`、`infra/Flatpak/com.mcloud.browser/`、`infra/APPIMAGE/`、`infra/portable/` | deb/rpm、Arch PKGBUILD、Flatpak、AppImage、便携包 |
| CI | `.github/workflows/release.yml`、`.github/workflows/verify.yml` | Tag 触发 Release 上传；PR 触发源码校验 |
| 版本/上游追踪 | `upstream_version.sh`、`version.sh`、`mcloud-libjxl/`、`mcloud_shell/` | 上游 Chromium 版本、自定义 libjxl、Shell 资源 |
| 基准测试 | `benchmark/` | 启动时间、内存、体积等 KPI 采集脚本 |

## 3. 架构与约定

- **单一源码树**：所有平台共享同一份 `src/chromium` 源码，差异通过 GN args 和少量 patch 实现，避免多分支维护成本。
- **out 目录隔离**：每个平台/变体使用独立的 `out/<name>`（如 `out/mcloud`、`out/thorium`），通过 `autoninja -C out/<name>` 切换，互不干扰。
- **GN 参数分层**：`args.gn` 提供全局默认值；平台特定参数放在 `arm/`、`other/*/`、`infra/DEBUG/` 下的同名或带前缀的 `.gn` 文件中，由上层脚本按需 include。
- **SIMD 指令集切分**：通过 `use_sse3/use_sse41/use_sse42/use_avx/use_avx2/use_avx512` 等 GN 变量控制编译产物，配合 `other/thor_ver_linux/wrapper-*` 包装器在运行时选择合适二进制。
- **PGO 优化**：`args.gn` 中 `is_official_build=true`、`chrome_pgo_phase=2` 并指向外部 `.profdata` 文件，表明 PGO 数据由外部流程生成后注入。
- **Widevine/DRM**：默认启用 `enable_widevine=true`、`bundle_widevine_cdm=true`，并在 `arm/raspi/` 下提供 widevine 补丁与 `widevine_fixup.py`。
- **媒体能力**：默认启用 FFmpeg、libvpx、HLS、HEVC/H265、AC3/E-AC3、Dolby Vision、DTS、MPEG-H 等解码器，`media_use_ffmpeg=true`、`proprietary_codecs=true`。
- **安全/沙箱**：`infra/BUILDER` 中记录将 `chrome-sandbox` 设为 setuid root（4755）的权限要求。

## 4. 约定与约束

- **构建命令约定**：所有平台构建脚本统一导出 `NINJA_SUMMARIZE_BUILD=1` 与 `NINJA_STATUS` 环境变量，便于并行构建日志可读。
- **源码目录约定**：通过 `CR_DIR` 环境变量指定 Chromium 源码根（默认 `$HOME/chromium/src` 或 Windows 下 `C:/src/chromium/src`），所有脚本据此 `cd` 进入源码目录执行 `autoninja`。
- **目标产物约定**：主浏览器产物统一为 `mcloud_all`，配套产物包括 `chrome_sandbox`、`chromedriver`、`clear_key_cdm`、`policy_templates`、`mcloud_shell`（content_shell）。
- **Windows 安装器约定**：Windows 构建完成后必须再执行 `setup mini_installer`，产物位于 `out/mcloud/mini_installer.exe`，由 release workflow 直接上传。
- **Release 命名约定**：GitHub Release 名称格式为 `MCloud Browser v<版本号>`，版本号取自 git tag `refs/tags/v*`；Release Notes 优先读取 `docs/superpowers/specs/*release-notes*.md`，否则回退为默认模板。
- **源码完整性校验**：`verify.yml` 强制在 PR/push main 时运行 `python3 win_scripts/verify_sources.py`，用于校验源码未被篡改（具体校验逻辑在该脚本内）。
- **禁用 AVX-512 的保守策略**：`infra/BUILDER` 显式列出 `-mno-avx512f` 等全部 AVX-512 子指令禁用标志，作为通用优化注释保留，防止编译器误用不稳定指令。
- **调试构建隔离**：`infra/DEBUG/` 下提供独立 `debug_args.gn`、`test_build_args.gn`、`win_debug_args.gn` 以及对应的 `build_debug_*.sh`，与 release 构建完全分离。
- **Android 多 ABI 构建**：`build_android.sh` 通过 `--arm32/--arm64/--x86/--x64` 参数分别构建 `chrome_public_apk`、`content_shell_apk`、`system_webview_*_apk`，产物统一位于 `out/mcloud/apks/`。
- **依赖第三方工具**：构建依赖 `depot_tools`（fetch/gclient/git-cl）、`autoninja`、LLVM/Clang、lld、V8 context snapshot、Widevine CDM 等，均通过 Chromium 标准机制获取。
