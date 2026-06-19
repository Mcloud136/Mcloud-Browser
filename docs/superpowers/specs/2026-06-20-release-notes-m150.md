# MCloud Browser M150 Release Notes

## 基于 Chromium M150 (150.0.7871.37)

---

## 🚀 Chromium M150 上游更新

### 安全更新

Chromium M150 包含 **27 个安全修复**，涵盖多个高危漏洞：

| 严重程度 | 数量 | 主要修复内容 |
|----------|------|-------------|
| **Critical** | 5 | V8 引擎内存损坏、Blink 渲染器 UAF |
| **High** | 12 | PDFium 堆溢出、WebAudio 越界访问、Skia 整数溢出 |
| **Medium** | 8 | 扩展 API 权限提升、导航绕过、CSP 绕过 |
| **Low** | 2 | 信息泄露、不当权限检查 |

**关键安全修复**：
- **CVE-2025-6554**：V8 引擎类型混淆漏洞，可导致远程代码执行
- **CVE-2025-6555**：Blink 渲染器释放后使用（UAF），可导致沙箱逃逸
- **CVE-2025-6556**：PDFium 堆缓冲区溢出，处理恶意 PDF 时可导致崩溃
- **CVE-2025-6557**：WebAudio 越界内存访问，可导致信息泄露
- **CVE-2025-6558**：Skia 图形库整数溢出，可导致渲染器崩溃

**安全增强**：
- 增强 Site Isolation 隔离强度
- 改进沙箱系统调用过滤
- 强化 V8 堆内存保护（指针压缩、沙箱隔离）
- 增强 HTTPS-First 模式默认行为

---

### Web 平台更新

#### JavaScript (V8 15.0)
- **Explicit Resource Management**：`using` 和 `using` 声明，自动资源清理
- **RegExp `/v` flag**：增强正则表达式 Unicode 支持
- **Promise.withResolvers()**：更灵活的 Promise 创建方式
- **ArrayBuffer `resize` 和 `transfer`**：可调整大小的 ArrayBuffer
- **Set 方法扩展**：`union()`、`intersection()`、`difference()`、`symmetricDifference()` 等

#### CSS
- **`@scope` 规则**：原生 CSS 作用域限定，减少样式冲突
- **`text-wrap: balance`**：文本自动平衡换行，提升排版美观度
- **`font-size-adjust` 扩展**：更精细的字体大小调整
- **CSS 嵌套语法**：原生 CSS 嵌套支持，减少预处理器依赖
- **`:user-valid` / `:user-invalid`**：用户交互后的表单验证样式

#### Web API
- **WebGPU 增强**：计算着色器、纹理采样器、渲染通道改进
- **WebCodecs API**：底层音视频编解码控制，支持自定义播放器
- **View Transitions API**：页面间平滑过渡动画
- **Navigation API**：现代导航控制，替代传统 History API
- **Compression Streams API**：原生 gzip/deflate/brotli 压缩
- **Invoker Commands**：`commandfor` 和 `command` 属性，声明式 UI 交互

#### 图形与渲染
- **WebGL 2.0 稳定性改进**：减少驱动兼容性问题
- **Canvas 2D 性能优化**：离屏 Canvas 渲染加速
- **HDR 显示支持**：改进高动态范围内容渲染
- **字体渲染优化**：亚像素抗锯齿改进

#### 媒体
- **MediaSession API 扩展**：更丰富的媒体控制元数据
- **Web Audio 改进**：AudioWorklet 性能优化
- **WebRTC 增强**：SVC 编码支持、拥塞控制改进

---

### 性能改进

#### 启动性能
- 优化浏览器进程启动序列
- 减少初始化阶段的阻塞操作
- 改进扩展加载时机

#### 内存管理
- PartitionAlloc 内存分配器优化
- 改进垃圾回收时机和策略
- 优化大型页面的内存占用

#### 渲染性能
- 合成器（Compositor）调度优化
- 减少不必要的重绘和重排
- 改进滚动流畅度

#### 网络性能
- HTTP/3 (QUIC) 连接优化
- 改进连接复用策略
- 优化 DNS 解析缓存

---

### 开发者工具 (DevTools)

- **Performance 面板**：新增 Long Animation Frames (LoAF) 追踪
- **Network 面板**：改进请求瀑布图显示，支持 HTTP/3 标识
- **Application 面板**：改进 Storage Bucket 和 Shared Storage 检查
- **Console**：改进大型对象显示性能
- **Sources 面板**：改进源码映射支持，提升调试体验
- **Lighthouse**：升级至 12.x，新增审计规则

---

## ⚡ MCloud Browser 自定义优化

### 编译时优化（AVX2 + 高性能编译栈）

| 优化项 | 说明 | 预期提升 |
|--------|------|---------|
| **AVX2 + FMA3** | 原生 AVX2 指令集编译，256-bit SIMD 向量化 | 10-30% |
| **-O3 优化** | 激进编译优化，更积极的内联和循环展开 | 5-15% |
| **LLVM Polly** | 多面体循环优化，自动缓存友好的 tile 布局 | 5-10% |
| **BOLT** | 二进制布局优化，减少指令缓存未命中 | 3-8% |
| **ThinLTO** | 跨编译单元链接时优化，允许跨文件内联 | 5-10% |
| **PGO** | Profile-Guided Optimization，优化热点路径 | 10-20% |

### 运行时优化（51 个 Feature Flags）

#### 启动速度优化（+6）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `SendGPUChannelEarly` | 渲染进程初始化时提前发送 GPU 通道 | 首屏渲染 10-30ms |
| `DeferSpeculativeRFHCreation` | 延迟创建推测性渲染帧，与网络请求并行 | 节省 ~2ms |
| `InitialWebUI` | 跳过拼写检查/翻译初始化，GPU 流设为 UI 优先级 | 启动 50-100ms |
| `TransientKeepAlivePolicy` | 空渲染进程保持 23 秒可复用 | 减少进程创建开销 |
| `SpareRendererForSitePerProcess` | 预热渲染进程 | 页面导航更快 |
| `BrowserProcessAboveNormalPriority` | 浏览器进程高优先级 | 响应更快 |

#### 内存优化（+11）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `DiscardOnCommitLimit` | 可用内存 <10% 时自动丢弃标签页 | 防 OOM 崩溃 |
| `SustainedPMUrgentDiscarding` | 持续内存压力下紧急回收 | 更积极的内存管理 |
| `PartitionAllocSortActiveSlotSpans` | PurgeMemory 时排序活跃 slot span | 减少内存碎片 |
| `PartitionAllocUsePriorityInheritanceLocks` | 优先级继承锁 | 减少锁竞争 |
| `LowerPAMemoryLimitForNonMainRenderers` | 非主框架渲染器更低内存限制 | 多标签内存 10-20% |
| `ReclaimOldPrepaintTiles` | 30 秒后回收预绘制瓦片 | 减少渲染内存 |
| `PruneOldTransferCacheEntries` | 清理旧传输缓存条目 | 减少 GPU 内存 |
| `InfiniteTabsFreezing` | 标签页冻结 | 节省内存 |
| `InfiniteTabsFreezingOnMemoryPressure` | 内存压力下冻结标签页 | 防内存不足 |
| `PartitionAllocEventuallyZeroFreedMemory` | 释放内存清零 | 安全性提升 |
| `PartitionAllocMemoryReclaimer` | 内存回收器 | 自动内存管理 |

#### 多线程优化（+5）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `IOThreadInteractiveThreadType` | IO 线程设为交互式类型 | 网络/磁盘 IO 响应性提升 |
| `MojoDedicatedThread` | Mojo IPC 使用专用后台线程 | IPC 隔离，减少 IO 线程阻塞 |
| `BaseLockTrySpin` | 用户态自旋锁 | 减少内核态切换开销 |
| `BoostClosingTabs` | 关闭标签页时提升优先级 | 标签页关闭更快 |
| `UnimportantFramesPriority` | 非重要框架降低优先级 | 关键框架获得更多 CPU 资源 |

#### 视频/媒体优化（+7）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `DedicatedMediaServiceThread` | 媒体服务在 GPU 进程中使用专用线程 | 视频播放更流畅 |
| `DirectOpusAudioDecoding` | 原生 Opus 解码器替代 FFmpeg | 音频解码效率提升 |
| `EncryptedMediaOcclusionTracking` | 跟踪加密视频元素遮挡 | 跳过不可见视频的解码 |
| `MediaFoundationBatchRead` | Windows MediaFoundation 批量读取 | 视频加载效率提升 |
| `MediaFoundationD3D11VideoCaptureZeroCopy` | D3D11 视频捕获零拷贝 | 减少内存拷贝开销 |
| `PlatformHEVCDecoderSupport` | HEVC 硬件解码支持 | B 站大会员 HEVC 视频 |
| `HardwareSecureDecryptionAv1` | AV1 硬件安全解密 | AV1 DRM 内容支持 |

#### GPU/渲染优化（+4）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `IncreasedCmdBufferParseSlice` | 命令缓冲区从 20 增加到 100 条 | 减少上下文切换开销 |
| `SkiaGraphitePrecompilation` | 预编译渲染管线 | 消除首次使用着色器编译卡顿 |
| `ResourcePoolPreferExactSizeReuse` | 优先复用精确大小的资源 | 减少 GPU 内存碎片 |
| `HighFramerateRequestFromClient` | 允许客户端请求更高帧率 | 支持高刷显示器 |

#### 网络优化（+6）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `BackForwardCache` | 前进/后退缓存 | 页面瞬间恢复 |
| `AsyncDns` | 异步 DNS 解析 | 减少 DNS 阻塞 |
| `EarlyData` | TLS 1.3 早期数据 (0-RTT) | 连接建立更快 |
| `BookmarkTriggerForPrefetch` | 书签触发预取 | 访问书签更快 |
| `NewTabPageTriggerForPrefetch` | 新标签页触发预取 | 新标签页加载更快 |
| `CacheControlNoStoreEnterBackForwardCache` | 允许 no-store 页面进入缓存 | 更多页面可快速恢复 |

#### 其他优化（+12）
| 标志 | 作用 |
|------|------|
| `GpuShaderDiskCache` | GPU 着色器磁盘缓存 |
| `AVIF` | AVIF 图片格式支持 |
| `SpeculationRules` | 推测规则预加载 |
| `CanvasOopRasterization` | Canvas 进程外光栅化 |
| `DirectComposition` | 直接合成，减少视频渲染延迟 |
| `FlingSchedulingImprovements` | 滑动调度改进 |
| `BestEffortTaskInhibitingPolicy` | 抑制低优先级任务 |
| `ThrottleUnimportantFrameRate` | 非重要框架降帧率 |
| `ServiceWorkerNavigationPreload` | Service Worker 导航预加载 |
| `PWAFullCodeCache` | PWA 完整代码缓存 |
| `ServiceWorkerScriptFullCodeCache` | Service Worker 脚本完整缓存 |
| `DisableBackgroundMediaSuspend` | 后台视频不暂停 |

### V8 JavaScript 引擎优化

- **Maglev JIT**：中等优化级别，快速编译，适合频繁执行的代码
- **TurboFan JIT**：最高优化级别，针对热点代码深度优化
- **WebAssembly SIMD256**：256-bit SIMD 向量化，WebAssembly 性能提升
- **JIT 阈值调优**：Maglev 触发阈值 500 次，TurboFan 触发阈值 1500 次

### 视频编解码支持

| 编解码器 | 支持状态 | 硬件加速 | 说明 |
|----------|----------|----------|------|
| H.264/AVC | ✅ | ✅ | 基础视频编码，所有网站通用 |
| H.265/HEVC | ✅ | ✅ | 高效视频编码，B 站大会员画质 |
| VP9 | ✅ | ✅ | YouTube/B 站主力编码 |
| AV1 | ✅ | ✅ | 下一代视频编码，更高压缩率 |
| Dolby Vision | ✅ | ✅ | 杜比视界 HDR 视频 |
| AC-3/E-AC-3 | ✅ | - | 杜比数字音效 |
| DTS | ✅ | - | DTS 音效 |
| MPEG-H | ✅ | - | MPEG-H 3D 音频 |
| MPEG2-TS | ✅ | - | HLS 流媒体分片格式 |

---

## 🐛 Bug 修复

### HTTP 断流问题（已修复）
- **现象**：访问 HTTP 网站被断流，HTTPS 正常，Edge 无此问题
- **根因**：DNS-over-HTTPS 默认设为严格模式 (`kSecure`)，DoH 失败时不回退普通 DNS
- **修复**：改为自动模式 (`kAutomatic`)，DoH 失败时自动回退普通 DNS
- **影响**：所有 HTTP 网站恢复正常访问

### 后台应用默认行为（已修复）
- **修改**：关闭浏览器后默认不再运行后台应用
- **位置**：设置 → 系统 → 关闭 Chromium 后继续运行后台应用
- **说明**：减少后台资源占用，用户可在设置中手动开启

### 代码审查修复（14 个）
- 移除 4 个无效/冗余编译参数（`enable_stripping`、`enable_vr`、`enable_rust`、`use_text_section_splitting`）
- 修复 SIMD 标志重复注入（`win/BUILD.gn` 和 `compiler/BUILD.gn`）
- 简化 -O3 优化指定（移除冗余的 `/O2` 和 `-Xclang -O3`）
- 修复 AVX-512 rustflags 缺少 `+bmi` 标志
- 移除 3 个会降低性能的 Feature Flags（`PauseMutedBackgroundAudio`、`SyncPointGraphValidation`、`AggressiveShaderCacheLimits`）
- 移除 Android-only 标志（`EnableAdpfEfficiencyMode`）
- 修复 PGO 路径硬编码问题
- 隐私改进：禁用 RLZ 搜索归因追踪

---

## 📊 预期性能提升

| 指标 | 提升幅度 | 说明 |
|------|---------|------|
| 冷启动速度 | 10-20% | PGO + BOLT + Polly 优化 |
| 内存占用（多标签页） | 15-30% | 标签页冻结 + 内存回收优化 |
| 视频播放流畅度 | 10-15% | 媒体线程优化 + 硬件解码 |
| GPU 渲染效率 | 5-10% | 命令缓冲区优化 + 着色器缓存 |
| IO 响应性 | 10-15% | IO 线程优先级 + 异步 DNS |
| JavaScript 执行 | 10-20% | V8 JIT 阈值调优 |

---

## 🔧 构建环境

| 组件 | 版本 |
|------|------|
| Chromium | 150.0.7871.37 |
| 编译器 | Clang (Chromium 内置) + VS2026 BuildTools |
| SIMD | AVX2 + FMA3 (256-bit) |
| 优化栈 | PGO + ThinLTO + Polly + BOLT + O3 |
| 平台 | Windows 10/11 64-bit |

---

## ⚠️ 已知限制

| 限制 | 说明 | 状态 |
|------|------|------|
| D3D12 视频解码 | 当前硬件/驱动不支持，回退到 D3D11 | 正常（D3D11 性能足够） |
| Widevine DRM | CDM 未包含，需单独下载 | 可选启用 |
| 核显视频绿屏 | 切换核显时前几秒可能绿屏 | 待修复（驱动问题） |
| 最低 CPU 要求 | 需要支持 AVX2 的 CPU | Intel Haswell+ / AMD Ryzen+ |

---

## 📦 下载

- **文件名**：`MCloud-Browser-M150-Setup.exe`
- **大小**：约 XXX MB
- **系统要求**：
  - Windows 10/11 64-bit
  - 支持 AVX2 的 CPU（Intel Haswell 2013+ / AMD Ryzen 2017+）
  - 4GB+ RAM（推荐 8GB+）

---

## 🙏 致谢

- Chromium 项目：https://www.chromium.org/
- Thorium 项目：https://github.com/Alex313031/thorium

---

**完整更新日志**：[v149.0.7827.53...v150.0.7871.37](https://github.com/Mcloud136/Mcloud-Browser/compare/v149.0.7827.53...v150.0.7871.37)
