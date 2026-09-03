---
kind: configuration_system
name: MCloud Browser 配置体系：GN 构建参数、运行时启动标志与平台打包配置
category: configuration_system
scope:
    - '**'
source_files:
    - args.gn
    - win_args.gn
    - mcloud_flags.txt
    - docs/ABOUT_GN_ARGS.md
    - infra/args.list
    - win_scripts/apply_mcloud_source_defaults.py
    - win_scripts/inject_flags_loader.py
    - infra/DEBUG/debug_args.gn
    - infra/DEBUG/win_debug_args.gn
    - arm/android/arm64_args.gn
    - other/Mac/mac_args.gn
    - other/AVX2/AVX2_args.gn
    - infra/Flatpak/com.mcloud.browser/org.chromium.Chromium.yaml
    - infra/Flatpak/com.mcloud.browser/gtk-settings.ini
    - infra/Flatpak/com.mcloud.browser/libsecret.json
    - infra/Flatpak/com.mcloud.browser/examples/policies/google-safe-search/google-safe-search.json
    - infra/initial_preferences
---

## 1. 系统概览

MCloud Browser 的配置体系围绕 Chromium 的 GN 构建系统与浏览器运行时命令行/特性开关展开，分为三个层次：

- **构建期配置**：通过 `args.gn`（Linux）、`win_args.gn`（Windows）以及 `arm/`、`other/Mac/`、`infra/DEBUG/` 下的平台/变体 `.gn` 文件，以键值对形式声明 target_os/target_cpu/SIMD 指令集、是否官方构建、符号级别、LTO/PGO、媒体编解码器、Widevine、Rust 等。
- **源码级默认值注入**：通过 Python 脚本在 Chromium 源码树上做“定点单点替换”，把上游默认值改为 MCloud 期望值（如 `kD3D12VideoDecoder` 默认启用、`kBackgroundModeEnabled` 默认 false），并校验 DoH 默认已是 `kAutomatic`。
- **运行期配置**：通过内嵌到 `chrome_main_delegate.cc` 的 `LoadMcloudPerformanceFlags()` 在进程启动早期读取同目录 `mcloud_flags.txt`，将 `--enable-features` / `--disable-features` 与用户命令行合并（用户条目在后优先），其余开关若用户未指定则追加；同时通过 Flatpak YAML、GTK settings、libsecret JSON、Chrome 策略 JSON 等外部配置文件为 Linux 发行版提供沙箱、扩展、策略与密钥存储行为。

## 2. 关键文件与包

- 顶层 GN 参数：`args.gn`（Linux x64 发布）、`win_args.gn`（Windows x64 发布）
- 平台/变体 GN 参数：`arm/android/arm64_args.gn`、`other/Mac/mac_args.gn`、`other/AVX2/AVX2_args.gn`、`infra/DEBUG/debug_args.gn`、`infra/DEBUG/win_debug_args.gn`
- 运行时启动标志清单：`mcloud_flags.txt`（按冷启动、视频、渲染、内存、网络、V8、预加载、GPU、媒体、线程、Service Worker、存储等分组注释）
- 源码默认值注入脚本：`win_scripts/apply_mcloud_source_defaults.py`、`win_scripts/inject_flags_loader.py`
- 文档说明：`docs/ABOUT_GN_ARGS.md`（逐项解释 GN 参数的含义与 MCloud 选择原因）
- 参考清单：`infra/args.list`（Chromium 全部 GN 参数及其当前值来源）
- 运行时外部配置：`infra/Flatpak/com.mcloud.browser/org.chromium.Chromium.yaml`（沙箱权限、扩展/策略挂载）、`infra/Flatpak/com.mcloud.browser/gtk-settings.ini`、`infra/Flatpak/com.mcloud.browser/libsecret.json`、`infra/Flatpak/com.mcloud.browser/examples/policies/google-safe-search/google-safe-search.json`
- 初始偏好占位：`infra/initial_preferences`（空 JSON 对象）

## 3. 架构与设计约定

### 3.1 GN 构建参数分层
每个目标平台/变体都有一份完整的 `.gn` 文件，覆盖同一组键空间（SIMD 开关、target_os/target_cpu、is_official_build/is_debug、symbol_level、media_*、widevine、rtc_*、enable_platform_* 音频/HEVC/Dolby Vision、thin_lto、chrome_pgo_phase、pgo_data_path）。发布构建统一设置 `chrome_pgo_phase = 2` 并指向对应平台的 `.profdata` 路径；Debug 构建关闭 LTO/PGO、提高 symbol_level、开启 dcheck。该模式使不同 CPU 基线（SSE2/SSE3/SSE4/AVX2/AVX512）和 OS（linux/win/mac/android）可复用同一套语义化 GN 键。

### 3.2 源码级默认值“补丁”而非整体覆盖
`apply_mcloud_source_defaults.py` 使用 `patch_file(path, old, new, desc)` 对上游源码进行锚点匹配 + 字符串替换，并在目标已存在时跳过（幂等），找不到锚点时报 `[WARN]` 并退出，强制人工检查上游变更。这避免了跨版本整体复制导致的编译失败。

### 3.3 运行期标志加载器
`inject_flags_loader.py` 向当前上游基线的 `chrome/app/chrome_main_delegate.cc` 注入 `LoadMcloudPerformanceFlags()`，在 `BasicStartupComplete` 开头调用。加载规则：
- 从 exe 同目录读取 `mcloud_flags.txt`；
- 逐行解析 `--flag` / `--flag=value` / 引号值 / `#` 注释；
- `--enable-features` / `--disable-features` 采用“内置在前、用户追加在后”的合并策略，保证用户命令行覆盖；
- 其他开关若用户已指定则跳过。
这使得性能调优开关可以随二进制分发，无需修改启动脚本。

### 3.4 平台打包配置
- Flatpak：`org.chromium.Chromium.yaml` 定义 app-id、runtime/base、finish-args（文件系统、设备、IPC socket、system-talk-name）、add-extensions（Codecs/NativeMessagingHost/Extension/Policy）、modules（Python2、readelf-symlink、extensions、chromium 源及 patches/all.json）。
- GTK 打印后端由 `gtk-settings.ini` 限定为 file/cups。
- libsecret 通过 `libsecret.json` 以 Meson 方式作为 Flatpak module 构建。
- Chrome 策略通过 `examples/policies/google-safe-search/google-safe-search.json` 示例展示如何以 JSON 下发策略。

## 4. 约定与约束

- **GN 参数集中管理**：所有构建差异通过独立的 `.gn` 文件表达，不在源码中硬编码 target_os/target_cpu 或 SIMD 能力；新增平台/变体应仿照现有文件结构新增 `.gn`。
- **PGO 路径硬编码**：各发布 `.gn` 中的 `pgo_data_path` 指向本地绝对路径（如 `/home/alex/.../.profdata`），实际 CI 需替换为可共享位置。
- **源码默认值变更必须幂等**：`apply_mcloud_source_defaults.py` 要求新状态已在文件中则 skip，旧锚点不存在则 abort，避免静默漂移。
- **运行期标志优先级**：`mcloud_flags.txt` 中的 `enable/disable-features` 先于用户命令行注入，用户命令行追加在最后，因此用户可通过命令行覆盖内置 feature 列表；其他开关遵循“用户指定即跳过”的默认值语义。
- **调试/发布分离**：`infra/DEBUG/` 下 debug_args.gn / win_debug_args.gn 明确关闭 stripping/LTO/CFI、提高 symbol_level、关闭 PGO，与 `args.gn`/`win_args.gn` 形成对照；`docs/ABOUT_GN_ARGS.md` 是这些选择的权威说明。
- **Flatpak 沙箱最小化**：仅开放 home、cups、pulseaudio、x11/wayland、network、特定 D-Bus name 等必要权限，并通过 add-extensions 将 codecs/extensions/policies 以只读方式挂载。
- **初始偏好为空**：`infra/initial_preferences` 仅为 `{}`，表明项目不通过该文件下发默认偏好，而是依赖 GN 构建期开关与运行期 flags/loader。

## 5. 适用性结论

本仓库是一个基于 Chromium 的定制浏览器工程，其“配置系统”并非独立应用框架，而是由 GN 构建参数、源码默认值注入脚本、运行时启动标志加载器以及 Flatpak/GTK/策略 JSON 共同构成的多层配置体系，覆盖构建期、源码期与运行期三个阶段。