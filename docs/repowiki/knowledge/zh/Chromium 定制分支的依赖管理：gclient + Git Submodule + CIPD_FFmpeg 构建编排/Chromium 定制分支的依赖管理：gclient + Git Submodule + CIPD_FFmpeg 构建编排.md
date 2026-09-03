---
kind: dependency_management
name: Chromium 定制分支的依赖管理：gclient + Git Submodule + CIPD/FFmpeg 构建编排
category: dependency_management
scope:
    - '**'
source_files:
    - gclient
    - depot_tools/DEPOT_TOOLS_REVISION
    - .gitmodules
    - infra/Flatpak/com.mcloud.browser/.gitmodules
    - other/build_ffmpeg.py
    - arm/third_party/libaom/BUILD.gn
    - infra/VERSIONS_LIST.txt
    - infra/Flatpak/com.mcloud.browser/patches/all.json
---

## 1. 使用的系统与工具

本项目是 MCloud Browser（基于 Chromium M151 的 Thorium 定制分支），其依赖管理完全围绕 Chromium 工程体系展开，没有使用 npm/yarn/pip/go 等语言级包管理器。

- **源码与第三方库同步**：通过根目录的 `gclient` 清单指定单一 solution `src`，指向 `https://chromium.googlesource.com/chromium/src.git`，并启用 `checkout_pgo_profiles`。目标 OS/CPU 覆盖 linux/win/android/chromeos 及 x64/x86/arm64/arm。
- **depot_tools 版本锁定**：仓库自带 `depot_tools/` 子模块，并通过 `depot_tools/DEPOT_TOOLS_REVISION` 固定到提交 `34256ef66abb14e04ac4c0ba2a2042f65db6b6bde0`，保证 fetch/gclient/git-cl 行为一致。
- **Git Submodule**：`gitmodules` 声明两个外部依赖：
  - `mcloud-libjxl` → `https://github.com/Mcloud136/mcloud-libjxl.git`（branch: main）
  - `infra/upgrader` → `https://github.com/Mcloud136/mcloud-win-upgrade`
- **Flatpak 发行版**：`infra/Flatpak/com.mcloud.browser/.gitmodules` 引入 Flathub 共享模块 `shared-modules`（`https://github.com/flathub/shared-modules`）。
- **CIPD / DEPS**：当前检出中未找到 `src/DEPS`、`CIPD_MANIFEST` 或 `.cipd_version` 文件；说明该工作树可能为精简检出或未包含完整的 Chromium 元数据。

## 2. 关键文件与位置

| 文件 | 作用 |
|---|---|
| `gclient` | 顶层 gclient 清单，定义 Chromium src 仓库 URL、目标平台 |
| `depot_tools/DEPOT_TOOLS_REVISION` | 锁定 depot_tools 精确提交 |
| `.gitmodules` | 声明 mcloud-libjxl、mcloud-win-upgrade 两个 submodule |
| `infra/Flatpak/com.mcloud.browser/.gitmodules` | Flatpak 构建时拉取 flathub/shared-modules |
| `other/build_ffmpeg.py` | 按 Chromium 约定在 `third_party/android_toolchain/ndk` 等路径下构建 FFmpeg，输出多架构二进制 |
| `arm/third_party/libaom/BUILD.gn` | ARM 专用 libaom 构建配置，按 current_cpu 选择 SSE/AVX/NEON 汇编实现 |
| `infra/VERSIONS_LIST.txt` | 历史 Chromium Stable 版本清单（从 49 到 103+），用于版本回溯参考 |
| `infra/Flatpak/com.mcloud.browser/patches/all.json` | 声明 Flatpak 打包阶段对 chromium/ffmpeg 的补丁列表 |
| `src/third_party/widevine/` | Widevine CDM 相关资源目录（具体 manifest 未检出） |

## 3. 架构与约定

- **单仓库 + 多解决方案**：整个项目以 Chromium 源码树为根，所有第三方依赖通过 Chromium 自身的 `gclient`/`DEPS`/`CIPD` 机制拉取，本仓库不维护独立的 `package.json`/`go.mod`/`requirements.txt`。
- **平台差异化依赖**：ARM/Raspberry Pi 构建在 `arm/third_party/` 下提供 libaom、libvpx、libyuv、widevine、xnnpack 等平台的独立 BUILD.gn 与补丁；Windows on ARM 通过 `win_ARM_args.gn` 等 GN 参数区分。
- **FFmpeg 自构建**：`other/build_ffmpeg.py` 根据宿主 OS/Arch 调用 Chromium 内建脚本，针对 android/linux/mac/win 分别产出对应 ABI 的二进制，NDK 路径硬编码为 `third_party/android_toolchain/ndk`。
- **Widevine 与 DRM**：`arm/raspi/widevine-other-locations.patch`、`arm/raspi/widevine_fixup.py`、`infra/widevine_versions.txt` 表明 Widevine 通过补丁与脚本适配非标准安装路径。
- **Flatpak 沙箱补丁**：`infra/Flatpak/com.mcloud.browser/patches/` 集中存放对 Chromium 和 FFmpeg 的 Flatpak 兼容补丁，由 `all.json` 统一索引。

## 4. 约定与约束

- **depot_tools 必须用仓库自带的副本**：通过 `DEPOT_TOOLS_REVISION` 固定提交，避免系统全局 depot_tools 版本漂移导致 fetch 失败。
- **Chromium src 只通过 gclient 拉取**：`gclient` 中 `managed: False` 表示不托管子仓库，仅作为单一 solution 同步。
- **第三方库以 Chromium third_party 约定为准**：如 FFmpeg NDK 路径、Android API level 读取逻辑均依赖 Chromium 内部 gn_helpers，不得随意修改。
- **平台变体通过 GN args 而非新仓库管理**：ARM、Raspberry Pi、AVX2/AVX512/SSE* 等 CPU 基线差异集中在 `arm/`、`other/` 下的 `*.gn`、`*.list` 文件中，不拆分独立依赖源。
- **Flatpak 依赖通过 shared-modules 子模块管理**：Flathub 公共依赖由 `shared-modules` submodule 提供，不在本仓库直接声明。
- **无语言级包管理器锁文件**：仓库中未发现 `go.sum`、`package-lock.json`、`poetry.lock`、`Pipfile.lock` 等；依赖版本由 Chromium 上游版本与本地补丁共同决定。

### 约束来源
- `gclient` 清单显式声明 Chromium src URL 与目标平台集合。
- `depot_tools/DEPOT_TOOLS_REVISION` 将工具链锁定到唯一 SHA。
- `.gitmodules` 强制 submodule 路径与远端 URL 必须匹配。
- `other/build_ffmpeg.py` 中 `ROBO_CONFIGURATION.ffmpeg_home()` 与 `android_toolchain/ndk` 路径为硬性约定。
- `infra/Flatpak/com.mcloud.browser/patches/all.json` 作为 Flatpak 构建期补丁的唯一清单。

## 总结

MCloud Browser 的依赖管理本质上是 **Chromium 工程体系的定制层**：通过 `gclient` 锁定 Chromium 源码、`depot_tools` 固定开发工具、Git Submodule 引入自有组件（libjxl、upgrader）、并在 `arm/`、`other/`、`infra/` 中以 GN 参数与补丁形式管理平台相关第三方库（FFmpeg、libaom、Widevine）。它不使用语言级包管理器，也不维护独立的 lockfile；可复现性依赖于 Chromium 上游版本、depot_tools 提交、以及本仓库内的补丁与 GN 参数组合。