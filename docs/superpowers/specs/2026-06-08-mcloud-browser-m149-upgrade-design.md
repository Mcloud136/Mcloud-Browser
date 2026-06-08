# MCloud Browser — Thorium M144 → M149 升级设计规格

> 日期：2026-06-08
> 目标：将 Thorium 从 Chromium 144.0.7559.254 升级到 Chromium 149.0.7827.53
> 平台：Windows x64
> 仓库：Mcloud-Browser (GitHub)
> SIMD 策略：SSE3 基准 + AVX2 运行时分发（所有 SSE3+ CPU 均可运行，AVX2 CPU 自动获得额外性能）

---

## 1. 项目概述

MCloud Browser 基于 Thorium 项目（Chromium fork），通过运行时 SIMD 分发机制赋予浏览器使用 AVX2 指令集的能力来优化性能。

**核心设计理念**：不是将整个浏览器编译为只在 AVX2 CPU 上运行的二进制文件，而是在关键代码路径上实现运行时 CPU 特性检测，当检测到 AVX2 支持时自动切换到 AVX2 优化的代码路径。这样保证了最大兼容性（SSE3+ CPU 均可运行），同时让 AVX2 CPU 获得显著的性能提升。

当前版本基于 Chromium M144 LTS，需要升级到最新 Stable（M149）以获得：
- 最新的安全补丁和 Web 标准支持
- 更新的 V8/JavaScript 引擎（Maglev、TurboFan 优化）
- 更新的媒体编解码器支持
- 新的 WebGPU、WebCodecs 等 API

## 2. 升级策略：直接跳升 + 按子系统分阶段

### 2.1 阶段划分

| 阶段 | 内容 | 优先级 | 预计工作量 |
|------|------|--------|-----------|
| 1 | M149 基础构建 + GN 参数适配 | P0 | 高 |
| 2 | AVX2/SIMD 编译器优化迁移 | P0 | 中 |
| 3 | 媒体编解码器补丁迁移 (HEVC/Widevine/AC3/JXL) | P0 | 高 |
| 4 | UI/功能补丁迁移 (FTP/经典UI/下载栏/MV2) | P1 | 高 |
| 5 | 隐私/安全补丁迁移 (GPC/DNT/DoH) | P1 | 中 |
| 6 | 视频播放优化 + Bilibili 专项优化 | P1 | 中 |
| 7 | CI/CD + GitHub Actions | P2 | 中 |

### 2.2 已知可移除的补丁

来自 `setup.sh` 的注释：
- `fix_dangling_pointer_tooltip.patch` — M145 起可移除（上游已修复）
- `fix_deb_dependency_generation.patch` — M149 起可移除（上游已修复）
- M144 已移除的补丁无需恢复（partalloc, abseil, file_dialog, wayland 等）

## 3. 阶段一：M149 基础构建

### 3.1 Chromium 源码获取

从 Chromium 149.0.7827.53 tag 拉取源码：

```bash
mkdir ~/chromium && cd ~/chromium
fetch --nohooks chromium
cd src && git checkout tags/149.0.7827.53
gclient sync --with_branch_heads --with_tags --force --reset --nohooks
gclient runhooks
```

### 3.2 GN 参数适配（win_args.gn → M149 兼容版本）

核心变化点：
- 验证所有 SIMD 相关参数在 M149 中的有效性
- 更新 PGO profile 路径（M149 的 .profdata 文件名不同）
- 检查 `enable_iterator_debugging`、`win_enable_cfg_guards` 等 Windows 特定参数
- 验证 `v8_enable_maglev`、`v8_enable_turbofan` 在 M149 中的默认值
- 检查 Rust 相关配置（`enable_rust`）是否在 M149 中有变化

### 3.3 关键 GN 参数（M149 适配后）

```gn
# SIMD 编译基准：SSE3（保证兼容性，不编译为纯 AVX2 二进制）
use_sse3 = true
use_sse41 = true
use_sse42 = true
use_avx = false          # 编译基准保持 SSE3
use_avx2 = false         # 不全局编译为 AVX2，而是运行时分发
use_avx512 = false
use_fma = false

# 运行时 AVX2 分发：通过以下参数启用各模块的 AVX2 代码路径
v8_enable_wasm_simd256_revec = true   # V8 WASM SIMD256（运行时检测）
rtc_enable_avx2 = true               # WebRTC AVX2（运行时检测）

# 构建类型
target_os = "win"
target_cpu = "x64"
is_official_build = true
is_debug = false

# 编译器优化
is_clang = true
use_lld = true
use_thin_lto = true
thin_lto_enable_optimizations = true
use_text_section_splitting = true
enable_precompiled_headers = false

# V8 优化
v8_enable_fast_torque = true
v8_enable_builtins_optimization = true
v8_enable_maglev = true
v8_enable_turbofan = true
v8_enable_wasm_simd256_revec = true
use_v8_context_snapshot = true

# 媒体/编解码器
media_use_ffmpeg = true
media_use_libvpx = true
proprietary_codecs = true
ffmpeg_branding = "Chrome"
enable_ffmpeg_video_decoders = true
is_component_ffmpeg = false
enable_hls_demuxer = true
enable_mse_mpeg2ts_stream_parser = true

# Widevine DRM
enable_library_cdms = true
enable_widevine = true
bundle_widevine_cdm = true
enable_cdm_storage_id = true
enable_widevine_cdm_host_verification = true
ignore_missing_widevine_signing_cert = true
enable_media_drm_storage = true

# WebRTC
rtc_use_h264 = true
rtc_use_h265 = true
rtc_enable_avx2 = true

# HEVC/DV/DTS/AC3
enable_platform_hevc = true
enable_hevc_parser_and_hw_decoder = true
platform_has_optional_hevc_decode_support = true
platform_has_optional_hevc_encode_support = true
enable_platform_ac3_eac3_audio = true
enable_platform_dolby_vision = true
enable_platform_encrypted_dolby_vision = true
enable_platform_dts_audio = true
enable_platform_mpeg_h_audio = true

# Windows 特定
win_enable_cfg_guards = true
enable_rlz = true
chrome_pgo_phase = 2
```

## 4. 阶段二：AVX2 运行时 SIMD 分发优化

### 4.1 设计理念

**编译基准**：SSE3（保证 2005+ CPU 兼容性）
**运行时优化**：AVX2 代码路径通过 CPUID 检测自动启用

这意味着浏览器的二进制文件同时包含 SSE3 和 AVX2 两套代码路径，运行时根据 CPU 能力动态选择。

### 4.2 关键优化模块

| 模块 | 优化方式 | 运行时检测机制 |
|------|---------|---------------|
| **V8 JavaScript 引擎** | TurboFan/Maglev JIT 编译器中启用 AVX2 指令生成 | V8 内置 `cpu_features` 模块 |
| **FFmpeg 视频解码** | 多套解码内核（SSE3/AVX2），运行时选择 | Chromium 的 `CPUDetect` + FFmpeg 的 `cpuflags` |
| **Skia 渲染引擎** | 图形光栅化、图像缩放、模糊等操作的 AVX2 加速路径 | Skia 的 `CPUDetect` |
| **Opus 音频解码** | CELT/Silk 的 AVX2 优化路径（已有上游支持） | CMake `OPUS_X86_MAY_HAVE_AVX2` |
| **libjpeg-turbo** | JPEG 解码/缩放的 AVX2 加速 | `cpu_disp.c` 运行时分发 |
| **libpng** | PNG 解码的 AVX2 优化 | Intel IPP 或自定义 SIMD 路径 |
| **WebAssembly SIMD** | `v8_enable_wasm_simd256_revec = true` 启用 WASM SIMD256 | V8 运行时检测 |
| **Blink 布局引擎** | CSS 布局计算、选择器匹配的 SIMD 优化 | Chromium `base/cpu.h` |

### 4.3 实现策略

#### V8 引擎层
```gn
# 启用 V8 的运行时 SIMD 分发
v8_enable_wasm_simd256_revec = true   # WASM SIMD256 向量化
v8_enable_maglev = true               # Maglev JIT（内部使用 SIMD）
v8_enable_turbofan = true             # TurboFan JIT（内部使用 SIMD）
v8_enable_builtins_optimization = true # 内建函数优化
```

V8 内部通过 `src/base/cpu.h` 检测 CPU 特性，在 JIT 编译时选择最优指令集。

#### FFmpeg 层
FFmpeg trunk 版本已内置多套解码器内核：
- `libavcodec/x86/h264dsp_init.c` — H.264 去块滤波的 AVX2 路径
- `libavcodec/x86/hevc*` — HEVC 解码的 AVX2 路径
- `libavcodec/x86/vp9*` — VP9 解码的 AVX2 路径
- `libavcodec/x86/av1*` — AV1 解码的 AVX2 路径

FFmpeg 在初始化时通过 `av_get_cpu_flags()` 检测 CPU 能力，自动选择最快的代码路径。

#### Skia 渲染层
Skia 通过 `src/core/SkCpu.cpp` 检测 CPU 特性，在以下操作中使用 AVX2：
- 图像缩放（`SkSampler`）
- 模糊效果（`SkGaussianBlur`）
- 颜色空间转换
- 矩阵运算

#### Opus 音频层
Chromium 的 Opus 库已有完整的 AVX2 支持（来自 Context7 文档）：
- `OPUS_X86_MAY_HAVE_AVX2`：编译 AVX2 代码路径
- `OPUS_X86_PRESUME_AVX2`：如果目标平台确定支持 AVX2
- 运行时通过 `OPUS_X86_CPUID` 检测，选择最优路径

### 4.4 编译配置

```gn
# 基准编译目标：SSE3（兼容性）
# 不设置 /arch:AVX2，保证基线兼容

# 启用各模块的 AVX2 运行时代码路径编译
v8_enable_wasm_simd256_revec = true
rtc_enable_avx2 = true               # WebRTC AVX2 优化

# LTO + PGO 用于全局优化（不改变 SIMD 兼容性）
use_thin_lto = true
thin_lto_enable_optimizations = true
use_text_section_splitting =true
```

### 4.5 CPU 特性检测链路

```
浏览器启动
  └─ Chromium base::CPU::Detect()
       ├─ CPUID 指令检测
       ├─ 检查 AVX2 位 (EBX bit 5)
       ├─ 检查 OSXSAVE + XSAVE 支持
       └─ 设置 internal::g_cpu_features
            ├─ V8::InitializeOncePerProcess() → 选择 JIT 策略
            ├─ av_get_cpu_flags() → FFmpeg 选择解码器内核
            ├─ SkCpu::Detect() → Skia 选择渲染路径
            └─ opus_select_arch() → Opus 选择音频处理路径
```

### 4.6 性能预期

| 场景 | SSE3 基准 | AVX2 加速 | 提升幅度 |
|------|----------|----------|---------|
| JavaScript 执行 | 基准 | +15-25% | V8 JIT 优化 |
| 视频解码（4K HEVC） | 基准 | +30-50% | FFmpeg AVX2 内核 |
| 图形渲染 | 基准 | +10-20% | Skia SIMD 路径 |
| 音频处理 | 基准 | +10-15% | Opus AVX2 路径 |
| 图片解码 | 基准 | +15-25% | libjpeg-turbo AVX2 |
| WASM 应用 | 基准 | +20-40% | SIMD256 向量化 |

## 5. 阶段三：媒体编解码器

### 5.1 FFmpeg HEVC 补丁

M149 的 FFmpeg 版本可能已更新，需要：
1. 检查 M149 的 `third_party/ffmpeg/` 中 HEVC 解码器状态
2. 如未原生支持，适配 `add-hevc-ffmpeg-decoder-parser.patch`
3. 适配 `change-libavcodec-header.patch`

FFmpeg trunk 已原生支持多种硬件加速解码：
- `ff_hevc_d3d11va_hwaccel` / `ff_hevc_d3d11va2_hwaccel`
- `ff_hevc_dxva2_hwaccel`
- `ff_av1_d3d11va_hwaccel`
- VP9 DXVA2/D3D11VA 支持

### 5.2 JPEG XL

- 更新 `thorium-libjxl` 子模块到兼容 M149 的版本
- 更新 DEPS 文件中的 libjxl 依赖版本

### 5.3 Widevine CDM

- 验证 CDM bundle 在 M149 中的集成方式
- 确保 `enable_cdm_host_verification` 和 `enable_widevine_cdm_host_verification` 配置正确

### 5.4 AC3/E-AC3/DTS

- `enable_platform_ac3_eac3_audio = true` 已在 GN 参数中
- 验证 M149 的 media pipeline 中这些编解解码器的注册

## 6. 阶段四：UI/功能补丁

### 6.1 Thorium 2024 UI

`thorium-2024-ui.patch` 是最大的补丁之一。M145-M149 中 CR23 UI 持续演进：
- Tab strip 布局变化
- Omnibox 样式变化
- Side panel 变化

策略：
1. 先在 M149 上应用补丁，分析所有 reject
2. 对每个 reject 定位 M149 中对应代码的新位置
3. 逐个适配修改

### 6.2 FTP 支持

M149 中 FTP 代码可能已被进一步清理：
- 检查 `net/ftp/` 目录是否仍存在
- 如已移除，需要从 M144 提取完整的 FTP 模块代码

### 6.3 Manifest V2 扩展

M149 可能已移除 MV2 代码路径：
- 检查 `extensions/browser/manifest_v2/` 是否存在
- 如已移除，需要重写 `allow_manifest_v2_extensions.patch`

### 6.4 其他功能

- 下载栏（`restore_download_shelf.patch`）
- 搜索引擎配置（DuckDuckGo, Brave, Ecosia 等）
- 自定义 NTP
- 标签页自定义（矩形标签、宽度、滚动切换）
- 键盘快捷键

## 7. 阶段五：隐私/安全补丁

- GPC（Global Privacy Control）
- Privacy Sandbox 禁用
- DNT 默认启用
- DoH（DNS over HTTPS）
- 显示完整 URL
- 禁用 API Key 警告
- Prefetch 隐私配置
- Captive Portal 检测禁用

## 8. 阶段六：视频播放优化

### 8.1 硬件解码加速（Windows）

| 编解码器 | 硬件加速 API | GN 参数 |
|---------|-------------|---------|
| H.264/AVC | DXVA2/D3D11VA | 内置支持 |
| H.265/HEVC | DXVA2/D3D11VA | `enable_platform_hevc = true` |
| VP9 | DXVA2/D3D11VA | 内置支持 |
| AV1 | D3D11VA | 内置支持（需 GPU 支持） |

FFmpeg 层面，trunk 版本已支持：
- `ff_hevc_d3d11va_hwaccel` / `ff_hevc_d3d11va2_hwaccel`
- `ff_hevc_dxva2_hwaccel`
- `ff_av1_d3d11va_hwaccel`

### 8.2 MSE 缓冲优化

通过 Chromium feature flags 和参数调整：
- 增大 MediaSource 默认缓冲区
- 优化 buffer eviction 策略
- 减少缓冲中断

### 8.3 HDR 支持

- DXGI HDR 输出路径
- HDR10 元数据传递
- 色彩空间正确映射

### 8.4 帧调度优化

- Viz compositor 帧调度策略调优
- 减少视频播放掉帧
- 优化 GPU 合成路径

### 8.5 YouTube 特定优化

- VP9/AV1 codec 选择策略
- 减少 codec 切换抖动
- 预加载/buffer 策略优化

### 8.6 Bilibili 特定优化

Bilibili 使用的技术栈：
- **视频编码**：H.264/AVC 为主，部分 HEVC（HEVC 需要大会员）
- **流媒体协议**：HTTP-FLV 和 DASH
- **播放器**：自研 HTML5 播放器（基于 MSE）
- **弹幕系统**：Canvas/WebGL 渲染的高密度弹幕

优化方案：
1. **MSE 缓冲策略**：针对 Bilibili 的 DASH 流优化 buffer 大小和预加载时机
2. **弹幕渲染性能**：优化 Canvas 2D 和 WebGL 的合成路径，利用 Skia AVX2 路径加速弹幕渲染，确保高密度弹幕不掉帧
3. **HEVC 硬解优先**：对 Bilibili 的 HEVC 流优先走 D3D11VA 硬解路径，软解时自动使用 FFmpeg AVX2 解码内核
4. **内存管理**：Bilibili 长视频场景下的内存占用优化
5. **页面加载**：优化 Bilibili 首页和视频页的资源加载优先级
6. **弹幕解码**：利用 AVX2 加速弹幕 JSON/XML 解析和文本渲染

通过 Chromium command line flags 实现：
```cpp
// Bilibili 优化 flags
--enable-features=PlatformHEVCDecoder,MediaFoundationH265Encoding
--disable-features=HardwareMediaKeyHandling
--force-video-overlays  // 减少视频层合成开销
```

### 8.7 WebCodecs API 增强

确保 WebCodecs API 在 M149 中的完整支持：
- `VideoEncoder` / `VideoDecoder` 的 `hardwareAcceleration: "prefer-hardware"` 配置
- HEVC codec string 支持（`hvc1.*`, `hev1.*`）
- AV1 codec string 支持

## 9. CI/CD：GitHub Actions

### 9.1 工作流设计

由于采用 SSE3 基准 + AVX2 运行时分发的策略，只需要一个构建配置（而非多个 SIMD 矩阵）。
AVX2 优化代码路径在编译时就已包含在二进制文件中，运行时自动选择。

```yaml
name: MCloud Browser Build

on:
  push:
    branches: [main, M149]
    tags: ['v*']
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v6

      - name: Cache depot_tools
        uses: actions/cache@v4
        with:
          path: depot_tools
          key: depot-tools-${{ runner.os }}-${{ hashFiles('**/version.sh') }}
          restore-keys: depot-tools-${{ runner.os }}-

      - name: Setup depot_tools
        run: |
          git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
          echo "$PWD/depot_tools" >> $GITHUB_PATH

      - name: Fetch Chromium M149
        run: |
          fetch --nohooks chromium
          cd src && git checkout tags/149.0.7827.53
          gclient sync --with_branch_heads --with_tags --force --reset --nohooks
          gclient runhooks

      - name: Apply MCloud Browser patches
        run: python win_scripts/setup.py

      - name: Build (SSE3 baseline + AVX2 runtime dispatch)
        run: |
          gn gen out/mcloud --args="$(cat win_args.gn)"
          autoninja -C out/mcloud chrome

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: mcloud-browser-win64
          path: out/mcloud/mini_installer.exe
```

### 9.2 构建产物

由于采用运行时 SIMD 分发，只需要一个构建配置：

| 产物 | 说明 |
|------|------|
| `MCloud-Browser-win64-installer.exe` | 标准安装包（SSE3 基准，AVX2 运行时加速） |
| `MCloud-Browser-win64-portable.zip` | 便携版 |

AVX2 CPU 用户无需下载特殊版本，标准版本已内置 AVX2 优化路径。

## 10. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 补丁冲突 | 按子系统分阶段处理，逐个 reject 分析 |
| GN 参数废弃 | 逐参数验证，参考 M149 的 `build/config/` |
| FFmpeg 版本变更 | 对比 M144 和 M149 的 ffmpeg 版本差异 |
| MV2 代码移除 | 预留重写方案，从 M144 提取关键代码 |
| PGO profile 过期 | 更新到 M149 的最新 profile |
| GitHub Actions 超时 | 使用 self-hosted runner 或优化缓存策略 |

### 9.3 发布流程

当 tag 推送（如 `v149.0.0`）时自动触发 Release：
- 构建 installer 和 portable 版本
- 自动创建 GitHub Release 并上传产物
- Release notes 自动生成（包含版本号、变更日志、下载链接）

## 10. 成功标准

1. M149 Windows x64 构建成功（SSE3 基准）
2. AVX2 运行时分发正常工作（在 AVX2 CPU 上自动启用优化路径）
3. 所有现有 Thorium 功能正常工作
4. HEVC/AC3/Dolby Vision 编解码器正常
5. Widevine DRM 正常
6. FTP 协议支持正常
7. 经典 UI/下载栏正常
8. 隐私增强功能正常
9. Bilibili 视频播放流畅，弹幕不掉帧
10. GitHub Actions CI 自动构建成功
11. 构建产物可在 SSE3+ 的 Windows 10/11 上正常安装运行
12. 在 AVX2 CPU 上可观察到明显的性能提升
