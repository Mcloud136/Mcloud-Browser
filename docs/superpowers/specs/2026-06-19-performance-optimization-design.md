# MCloud Browser 性能优化设计文档 v2.0

> 日期：2026-06-19
> 版本：2.0（基于 M150 实际验证重写）
> 状态：已批准

## 概述

MCloud Browser 基于 Chromium M150 (150.0.7871.37) 的全面性能优化方案。

**构建环境**：
- 平台：Windows x64
- 编译器：VS2026 BuildTools + Clang (Chromium 内置)
- 依赖：gclient sync 完成，所有 hook 成功

**优化目标**：
1. 启动速度
2. 内存占用
3. 多线程性能
4. 视频解码
5. 视频网站优化（B站/YouTube）

---

## 第一部分：编译时参数（args.gn）

所有参数已通过 `gn args --list` 验证有效（1196 个有效参数中使用 72 个）。

### 已有参数（保持不变）

| 类别 | 参数 | 值 | 作用 |
|------|------|-----|------|
| SIMD | `use_avx2` | `true` | AVX2 指令集 |
| SIMD | `use_fma` | `true` | FMA3 指令集 |
| 编译优化 | `is_official_build` | `true` | 官方构建模式 |
| 编译优化 | `is_full_optimization_build` | `true` | -O3 优化 |
| 编译优化 | `use_polly` | `true` | LLVM Polly 循环优化 |
| 编译优化 | `use_bolt` | `true` | BOLT 二进制布局优化 |
| 编译优化 | `use_thin_lto` | `true` | ThinLTO 链接时优化 |
| 编译优化 | `chrome_pgo_phase` | `2` | PGO 优化 |
| V8 | `v8_enable_maglev` | `true` | Maglev JIT |
| V8 | `v8_enable_turbofan` | `true` | TurboFan JIT |
| V8 | `v8_enable_wasm_simd256_revec` | `true` | WebAssembly SIMD256 |
| 视频 | `enable_platform_hevc` | `true` | HEVC 支持 |
| 视频 | `enable_hevc_parser_and_hw_decoder` | `true` | HEVC 硬解 |
| 视频 | `platform_has_optional_hevc_decode_support` | `true` | HEVC 可选支持 |
| 视频 | `proprietary_codecs` | `true` | 商业编解码器 |
| 视频 | `ffmpeg_branding` | `"Chrome"` | FFmpeg 品牌 |
| WebRTC | `rtc_use_h264` | `true` | H.264 支持 |
| WebRTC | `rtc_use_h265` | `true` | H.265 支持 |
| WebRTC | `rtc_enable_avx2` | `true` | WebRTC AVX2 |
| DRM | `enable_widevine` | `false` | Widevine（暂时禁用） |
| GPU | `enable_vulkan` | `false` | Vulkan（Windows 用 D3D12） |

### 新增参数

| 参数 | 值 | 作用 | 验证状态 |
|------|-----|------|---------|
| `enable_vulkan = false` | 新增 | 禁用 Vulkan，Windows 使用 D3D12 | ✅ 已验证 |

> 注：之前尝试添加的 `enable_nacl`、`enable_platform_av1_decoder`、`use_prefer_intrusive_backing_list`、`v8_enable_short_builtins`、`v8_enable_lazy_source_positions` 在 M150 中已不存在（功能已内置或移除），已从 args.gn 中移除。

---

## 第二部分：运行时标志（mcloud_flags.txt）

通过 `--enable-features=` 启用 Chromium feature flags，无需重编译。

### 2.1 启动速度（4 个新标志）

| 标志 | 作用 | 来源文件 |
|------|------|---------|
| `SendGPUChannelEarly` | 渲染进程初始化时提前发送 GPU 通道 | `gpu/config/gpu_finch_features.cc` |
| `DeferSpeculativeRFHCreation` | 延迟创建推测性渲染帧，节省 ~2ms | `content/public/common/content_features.cc` |
| `InitialWebUI:without_spellcheck/without_translate/high_stream_priority` | 跳过拼写/翻译初始化，GPU 流 UI 优先 | `content/public/common/content_features.cc` |
| `TransientKeepAlivePolicy` | 空渲染进程保持 23 秒可复用 | `components/performance_manager/features.cc` |

### 2.2 内存优化（7 个新标志）

| 标志 | 作用 | 来源文件 |
|------|------|---------|
| `DiscardOnCommitLimit` | 可用内存 <10% 时丢弃标签页 | `components/performance_manager/features.cc` |
| `SustainedPMUrgentDiscarding` | 持续内存压力下紧急丢弃 | `components/performance_manager/features.cc` |
| `PartitionAllocSortActiveSlotSpans` | PurgeMemory 时排序活跃 slot span | `base/allocator/partition_alloc_features.cc` |
| `PartitionAllocUsePriorityInheritanceLocks` | 优先级继承锁 | `base/allocator/partition_alloc_features.cc` |
| `LowerPAMemoryLimitForNonMainRenderers` | 非主框架渲染器更低内存限制 | `base/allocator/partition_alloc_features.cc` |
| `ReclaimOldPrepaintTiles` | 30 秒后回收预绘制瓦片 | `cc/base/features.cc` |
| `PruneOldTransferCacheEntries` | 清理旧传输缓存条目 | `gpu/config/gpu_finch_features.cc` |

### 2.3 多线程（5 个新标志）

| 标志 | 作用 | 来源文件 |
|------|------|---------|
| `IOThreadInteractiveThreadType` | IO 线程设为交互式类型 | `content/public/common/content_features.cc` |
| `MojoDedicatedThread` | Mojo IPC 使用专用线程 | `content/public/common/content_features.cc` |
| `BaseLockTrySpin` | 用户态自旋锁 | `base/features.cc` |
| `BoostClosingTabs` | 关闭标签页时提升优先级 | `components/performance_manager/features.cc` |
| `UnimportantFramesPriority` | 非重要框架降低优先级 | `components/performance_manager/features.cc` |

### 2.4 视频/媒体（6 个新标志）

| 标志 | 作用 | 来源文件 |
|------|------|---------|
| `DedicatedMediaServiceThread` | 媒体服务专用线程 | `media/base/media_switches.cc` |
| `DirectOpusAudioDecoding` | 原生 Opus 解码器 | `media/base/media_switches.cc` |
| `PauseMutedBackgroundAudio` | 暂停静音后台音频 | `media/base/media_switches.cc` |
| `EncryptedMediaOcclusionTracking` | 跟踪加密视频遮挡 | `media/base/media_switches.cc` |
| `MediaFoundationBatchRead` | MediaFoundation 批量读取 | `media/base/media_switches.cc` |
| `MediaFoundationD3D11VideoCaptureZeroCopy` | D3D11 视频捕获零拷贝 | `media/base/media_switches.cc` |

### 2.5 GPU/渲染（6 个新标志）

| 标志 | 作用 | 来源文件 |
|------|------|---------|
| `SyncPointGraphValidation` | 图形化同步点验证 | `gpu/config/gpu_finch_features.cc` |
| `IncreasedCmdBufferParseSlice` | 命令缓冲区 20→100 条 | `gpu/config/gpu_finch_features.cc` |
| `AggressiveShaderCacheLimits` | 更大着色器缓存 | `gpu/config/gpu_finch_features.cc` |
| `SkiaGraphitePrecompilation` | 预编译渲染管线 | `gpu/config/gpu_finch_features.cc` |
| `ResourcePoolPreferExactSizeReuse` | 精确大小资源复用 | `cc/base/features.cc` |
| `HighFramerateRequestFromClient` | 允许高帧率请求 | `cc/base/features.cc` |

---

## 第三部分：D3D12 视频解码

已在 `media/base/media_switches.cc` 中将 `kD3D12VideoDecoder` 改为 `FEATURE_ENABLED_BY_DEFAULT`。

**工作流程**：
```
B站/YouTube 视频 → Chromium 解码器选择
    ↓
D3D11VideoDecoder::CreateD3DVideoDecoderWrapper()
    ↓
检测 kD3D12VideoDecoder = ENABLED
    ↓ 尝试创建 D3D12 设备
成功 → D3D12VideoDecoderWrapper（D3D12 后端）
失败 → D3D11VideoDecoderWrapper（D3D11 回退）
```

**支持的编解码器**：H.264、VP9、AV1、HEVC

---

## 第四部分：DNS 修复

已在 `chrome/browser/net/default_dns_over_https_config_source.cc` 中将 DoH 默认模式从 `kSecure` 改为 `kAutomatic`。

**修复效果**：HTTP 网站不再断流，DoH 失败时自动回退普通 DNS。

---

## 第五部分：构建环境

| 组件 | 状态 | 路径 |
|------|------|------|
| Chromium 源码 | ✅ 完整 | `D:\wxmuma\chromium-src\src` |
| V8 PGO profiles | ✅ 4 个文件 | `v8/tools/builtins-pgo/profiles/` |
| Chrome PGO profile | ✅ 445MB | `chrome/build/pgo_profiles/` |
| 第三方库 | ✅ 10/10 | angle, icu, ffmpeg, pdfium, boringssl, libvpx, libaom, dav1d, libyuv, opus |
| SwiftShader | ✅ 2.5GB | `third_party/swiftshader/` |
| Rust 工具链 | ✅ 413MB | `third_party/rust-toolchain/` |
| Node.js | ✅ | `third_party/node/` |
| depot_tools | ✅ | `third_party/depot_tools/` |
| VS2026 BuildTools | ✅ | `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools` |

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 运行时标志组合不稳定 | 低 | Chromium 官方测试覆盖 |
| D3D12 解码器不稳定 | 低 | 自动回退到 D3D11 |
| Widevine DRM 不可用 | 中 | `enable_widevine = false`，需要时单独下载 CDM |
| 编译时参数不兼容 | 低 | 已通过 `gn args --list` 验证 |

---

## 预期收益

| 指标 | 预期提升 |
|------|---------|
| 冷启动速度 | 10-20% |
| 内存占用（多标签页） | 15-30% |
| 视频播放流畅度 | 10-15% |
| GPU 渲染效率 | 5-10% |
| IO 响应性 | 10-15% |
