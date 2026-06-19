# MCloud Browser 性能优化实施计划 v2.0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 优化 MCloud Browser 的启动速度、内存占用、多线程性能、视频解码和视频网站体验。

**Architecture:** 修改运行时标志（mcloud_flags.txt）和编译时参数（args.gn），启用 Chromium M150 中已有的性能优化特性。所有参数已通过 `gn args --list` 验证有效。

**Tech Stack:** GN, Chromium Feature Flags, D3D12 视频解码, VS2026 BuildTools + Clang

## Global Constraints

- 平台：Windows x64
- Chromium 版本：150.0.7871.37
- SIMD：AVX2 + FMA3
- VS：VS2026 BuildTools
- 环境变量：`DEPOT_TOOLS_WIN_TOOLCHAIN=0`, `vs2026_install=C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools`
- 品牌名称：Mcloud Browser

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `mcloud_flags.txt` | 修改 | 添加 28 个运行时标志 |
| `win_args_mcloud.gn` | 修改 | 添加 1 个编译时参数（enable_vulkan=false） |
| `win_scripts/copy_essentials.py` | 已完成 | 包含 media_switches.cc |
| `src/media/base/media_switches.cc` | 已完成 | D3D12 默认启用 |
| `src/chrome/browser/net/default_dns_over_https_config_source.cc` | 已完成 | DNS 修复 |

---

### Task 1: 更新 mcloud_flags.txt

**Files:**
- Modify: `mcloud_flags.txt`

- [ ] **Step 1: 写入完整的 mcloud_flags.txt**

```txt
# =============================================================================
# MCloud Browser — Performance Startup Flags
# =============================================================================
# This file contains command-line flags and feature flags for MCloud Browser
# performance optimizations. These are applied at browser startup.
# =============================================================================

# --- Cold Startup Optimization ---
--enable-features=SpareRendererForSitePerProcess
--enable-features=BrowserProcessAboveNormalPriority
--enable-features=SendGPUChannelEarly
--enable-features=DeferSpeculativeRFHCreation
--enable-features=InitialWebUI:without_spellcheck/without_translate/high_stream_priority
--enable-features=TransientKeepAlivePolicy

# --- Video Playback Optimization ---
--disable-background-media-suspend
--enable-gpu-rasterization
--enable-features=CanvasOopRasterization

# --- Rendering Optimization ---
--enable-features=FlingSchedulingImprovements
--enable-features=BestEffortTaskInhibitingPolicy
--enable-features=ThrottleUnimportantFrameRate
--enable-features=DirectComposition

# --- Memory Optimization ---
--enable-features=InfiniteTabsFreezing
--enable-features=InfiniteTabsFreezingOnMemoryPressure
--enable-features=PartitionAllocEventuallyZeroFreedMemory
--enable-features=PartitionAllocMemoryReclaimer
--enable-features=EnableAdpfEfficiencyMode
--enable-features=DiscardOnCommitLimit
--enable-features=SustainedPMUrgentDiscarding
--enable-features=PartitionAllocSortActiveSlotSpans
--enable-features=PartitionAllocUsePriorityInheritanceLocks
--enable-features=LowerPAMemoryLimitForNonMainRenderers
--enable-features=ReclaimOldPrepaintTiles
--enable-features=PruneOldTransferCacheEntries

# --- Network Optimization ---
--enable-features=BookmarkTriggerForPrefetch
--enable-features=NewTabPageTriggerForPrefetch
--enable-features=BackForwardCache
--enable-features=CacheControlNoStoreEnterBackForwardCache
--enable-features=AsyncDns
--enable-features=EarlyData

# --- Image Optimization ---
--enable-features=AVIF

# --- Speculation Rules ---
--enable-features=SpeculationRules

# --- V8 JavaScript Optimization ---
--js-flags="--invocation-count-for-maglev=500 --invocation-count-for-turbofan=1500"

# --- GPU Optimization ---
--enable-features=GpuShaderDiskCache
--enable-features=SyncPointGraphValidation
--enable-features=IncreasedCmdBufferParseSlice
--enable-features=AggressiveShaderCacheLimits
--enable-features=SkiaGraphitePrecompilation
--enable-features=ResourcePoolPreferExactSizeReuse
--enable-features=HighFramerateRequestFromClient

# --- Media Optimization ---
--enable-features=PlatformHEVCDecoderSupport
--enable-features=HardwareSecureDecryptionAv1
--enable-features=DedicatedMediaServiceThread
--enable-features=DirectOpusAudioDecoding
--enable-features=PauseMutedBackgroundAudio
--enable-features=EncryptedMediaOcclusionTracking
--enable-features=MediaFoundationBatchRead
--enable-features=MediaFoundationD3D11VideoCaptureZeroCopy

# --- Threading Optimization ---
--enable-features=IOThreadInteractiveThreadType
--enable-features=MojoDedicatedThread
--enable-features=BaseLockTrySpin
--enable-features=BoostClosingTabs
--enable-features=UnimportantFramesPriority

# --- Service Worker Optimization ---
--enable-features=ServiceWorkerNavigationPreload

# --- Storage Optimization ---
--enable-features=PWAFullCodeCache
--enable-features=ServiceWorkerScriptFullCodeCache
```

- [ ] **Step 2: 同步到 Chromium 源码树**

```bash
cp /d/wxmuma/thorium/mcloud_flags.txt /d/wxmuma/chromium-src/src/mcloud_flags.txt
```

---

### Task 2: 更新 args.gn

**Files:**
- Modify: `win_args_mcloud.gn`

- [ ] **Step 1: 确认 Widevine 已禁用**

检查 `win_args_mcloud.gn` 中：
```gn
enable_widevine = false
bundle_widevine_cdm = false
```

- [ ] **Step 2: 确认 Vulkan 已禁用**

检查 `win_args_mcloud.gn` 中：
```gn
enable_vulkan = false
```

- [ ] **Step 3: 同步到 Chromium 源码树**

```bash
cp /d/wxmuma/thorium/win_args_mcloud.gn /d/wxmuma/chromium-src/src/out/mcloud/args.gn
```

---

### Task 3: 同步覆盖文件

**Files:**
- Run: `win_scripts/copy_essentials.py`

- [ ] **Step 1: 运行复制脚本**

```bash
export THOR_DIR="/d/wxmuma/thorium"
export CR_DIR="/d/wxmuma/chromium-src/src"
python3 $THOR_DIR/win_scripts/copy_essentials.py
```

预期输出：14 个文件全部 "Copied:"

- [ ] **Step 2: 验证关键文件**

```bash
# DNS 修复
grep "kAutomatic" /d/wxmuma/chromium-src/src/chrome/browser/net/default_dns_over_https_config_source.cc

# D3D12 默认启用
grep "ENABLED_BY_DEFAULT" /d/wxmuma/chromium-src/src/media/base/media_switches.cc | grep "D3D12"

# SIMD 配置
grep "thorium_simd_optimization" /d/wxmuma/chromium-src/src/build/config/BUILDCONFIG.gn
```

---

### Task 4: 编译

**Files:**
- None (编译验证)

- [ ] **Step 1: 生成构建文件**

```bash
cd /d/wxmuma/chromium-src/src
export PATH="/d/wxmuma/depot_tools:$PATH"
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
gn gen out/mcloud --check
```

预期输出：`Done. Made 31060 targets from 4768 files`

- [ ] **Step 2: 编译浏览器**

```bash
cd /d/wxmuma/chromium-src/src
export PATH="/d/wxmuma/depot_tools:$PATH"
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
autoninja -C out/mcloud chrome
```

预期输出：编译成功，生成 `chrome.exe`

---

### Task 5: 运行时验证

- [ ] **Step 1: 启动浏览器**

```bash
cd /d/wxmuma/chromium-src/src/out/mcloud
./chrome.exe
```

- [ ] **Step 2: 检查 chrome://flags**

访问 `chrome://flags`，搜索确认：
- `D3D12VideoDecoder` — Enabled
- `PlatformHEVCDecoderSupport` — Enabled

- [ ] **Step 3: 检查 chrome://media-internals**

播放 B 站视频，检查：
- 视频解码器类型
- 是否使用硬件解码

- [ ] **Step 4: 视频播放测试**

访问以下网站测试：
- B 站 (bilibili.com) — HEVC/AV1 视频
- YouTube — VP9/AV1 视频

- [ ] **Step 5: 内存测试**

打开 10+ 标签页，访问 `chrome://system/` 查看内存

---

## 验收标准

| 指标 | 目标 |
|------|------|
| gn gen | 无错误 |
| 编译成功 | 生成 chrome.exe |
| D3D12 解码 | chrome://media-internals 显示 D3D12 |
| B 站视频 | 流畅播放 |
| YouTube 视频 | 流畅播放 |
| HTTP 访问 | 不断流（DNS 修复） |
