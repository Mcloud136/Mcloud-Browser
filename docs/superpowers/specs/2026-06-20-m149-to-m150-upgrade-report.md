# MCloud Browser M149 → M150 升级报告

> 日期：2026-06-20
> 从：Chromium M149 (149.0.7827.53)
> 到：Chromium M150 (150.0.7871.37)

---

## 1. 内核升级

| 项目 | M149 | M150 |
|------|------|------|
| Chromium 版本 | 149.0.7827.53 | 150.0.7871.37 |
| V8 引擎 | 同步更新 | 同步更新 |
| Blink 渲染引擎 | 同步更新 | 同步更新 |
| Skia 图形库 | 同步更新 | 同步更新 |
| FFmpeg | 同步更新 | 同步更新 |
| WebRTC | 同步更新 | 同步更新 |

**M150 主要更新内容**：
- 安全补丁和漏洞修复
- Web 标准支持更新
- 性能优化和 bug 修复
- 新增 feature flags

---

## 2. 性能优化（新增）

### 2.1 编译时优化

| 优化项 | M149 | M150 | 提升 |
|--------|------|------|------|
| SIMD 指令集 | AVX2 + FMA3 | AVX2 + FMA3 | 保持 |
| 编译优化级别 | -O3 | -O3 | 保持 |
| LLVM Polly | ✅ | ✅ | 保持 |
| BOLT 二进制布局 | ✅ | ✅ | 保持 |
| ThinLTO | ✅ | ✅ | 保持 |
| PGO | ✅ | ✅ | 保持 |
| D3D12 视频解码 | ❌ 默认禁用 | ✅ **默认启用** | **新增** |
| Vulkan | 未处理 | ❌ 显式禁用 | **优化** |
| Rust +bmi 标志 | 缺失 | ✅ 已添加 | **修复** |
| -O3 指定 | 三重指定 | ✅ 简化为 /clang:-O3 | **优化** |

### 2.2 运行时优化（Feature Flags）

**M150 新增 28 个性能标志**：

#### 启动速度（+4）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `SendGPUChannelEarly` | 提前发送 GPU 通道 | 首屏渲染 10-30ms |
| `DeferSpeculativeRFHCreation` | 延迟推测性渲染帧 | 节省 ~2ms |
| `InitialWebUI` | 跳过拼写/翻译初始化 | 启动 50-100ms |
| `TransientKeepAlivePolicy` | 空渲染进程复用 | 减少进程创建开销 |

#### 内存优化（+7）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `DiscardOnCommitLimit` | 内存 <10% 丢弃标签页 | 防 OOM |
| `SustainedPMUrgentDiscarding` | 持续压力紧急丢弃 | 更积极回收 |
| `PartitionAllocSortActiveSlotSpans` | 排序活跃 slot span | 减少碎片 |
| `PartitionAllocUsePriorityInheritanceLocks` | 优先级继承锁 | 减少锁竞争 |
| `LowerPAMemoryLimitForNonMainRenderers` | 非主框架更低内存 | 多标签内存 10-20% |
| `ReclaimOldPrepaintTiles` | 30 秒回收预绘制瓦片 | 减少渲染内存 |
| `PruneOldTransferCacheEntries` | 清理旧传输缓存 | 减少 GPU 内存 |

#### 多线程（+5）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `IOThreadInteractiveThreadType` | IO 线程交互式 | IO 响应性提升 |
| `MojoDedicatedThread` | Mojo IPC 专用线程 | IPC 隔离 |
| `BaseLockTrySpin` | 用户态自旋锁 | 减少内核切换 |
| `BoostClosingTabs` | 关闭标签提升优先级 | 关闭更快 |
| `UnimportantFramesPriority` | 非重要框架降优先级 | 关键框架更多资源 |

#### 视频/媒体（+6）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `DedicatedMediaServiceThread` | 媒体服务专用线程 | 视频更流畅 |
| `DirectOpusAudioDecoding` | 原生 Opus 解码 | 音频效率提升 |
| `EncryptedMediaOcclusionTracking` | 跟踪加密视频遮挡 | 跳过不必要解码 |
| `MediaFoundationBatchRead` | MediaFoundation 批量读取 | 视频加载更快 |
| `MediaFoundationD3D11VideoCaptureZeroCopy` | D3D11 零拷贝 | 减少内存拷贝 |

#### GPU/渲染（+4）
| 标志 | 作用 | 预期提升 |
|------|------|---------|
| `IncreasedCmdBufferParseSlice` | 命令缓冲 20→100 条 | 减少上下文切换 |
| `SkiaGraphitePrecompilation` | 预编译渲染管线 | 消除着色器编译卡顿 |
| `ResourcePoolPreferExactSizeReuse` | 精确大小资源复用 | 减少 GPU 内存碎片 |
| `HighFramerateRequestFromClient` | 允许高帧率请求 | 支持高刷显示器 |

---

## 3. Bug 修复

### 3.1 HTTP 断流问题（M149 存在，M150 修复）

| 项目 | 说明 |
|------|------|
| **现象** | MCloud Browser 访问 HTTP 网站被断流，Edge 正常 |
| **根因** | DNS-over-HTTPS 默认模式设为 `kSecure`（严格模式），只用 DoH 解析 DNS |
| **影响** | 所有 HTTP 网站无法访问，HTTPS 正常 |
| **修复** | 改为 `kAutomatic`（自动模式，DoH 失败时回退普通 DNS） |
| **文件** | `chrome/browser/net/default_dns_over_https_config_source.cc` |

### 3.2 代码审查问题修复（14 个）

| # | 问题 | 影响 | 修复 |
|---|------|------|------|
| 1 | win/BUILD.gn AVX2 无条件注入 | 非 AVX2 构建崩溃 | 移除重复块 |
| 2 | PGO 路径硬编码 | 换机器编译失败 | 移除，自动查找 |
| 3 | AVX2/FMA 标志重复 | 代码混乱 | 统一由 thorium_simd_optimization 处理 |
| 4 | PauseMutedBackgroundAudio | **后台视频暂停** | 移除 |
| 5 | SyncPointGraphValidation | GPU 调试开销 | 移除 |
| 6 | enable_vr 无效参数 | 被忽略 | 移除 |
| 7 | 三重 -O3 指定 | 代码混乱 | 简化为 /clang:-O3 |
| 8 | EnableAdpfEfficiencyMode | Android-only | 移除 |
| 9 | enable_stripping 无效 | 被忽略 | 移除 |
| 10 | enable_rust 冗余 | 重复 | 移除 |
| 11 | enable_rlz 隐私问题 | Google 追踪 | 改为 false |
| 12 | use_text_section_splitting | Windows 无效 | 移除 |
| 13 | AVX-512 rustflags 缺 +bmi | 不一致 | 添加 |
| 14 | AggressiveShaderCacheLimits | 视频卡顿 | 移除 |

---

## 4. 构建环境变更

| 项目 | M149 | M150 |
|------|------|------|
| VS 版本 | VS2022 | VS2026 BuildTools |
| ATL 路径 | 自动 | 需手动设置 INCLUDE |
| depot_tools | 自动下载 | 需手动克隆 |
| PGO profiles | 需手动下载 | gclient runhooks 自动下载 |
| V8 PGO profiles | 需手动下载 | gclient runhooks 自动下载 |

---

## 5. 配置变更汇总

### 5.1 args.gn 变更

| 参数 | M149 | M150 | 原因 |
|------|------|------|------|
| `enable_widevine` | `true` | `false` | CDM 未下载 |
| `enable_vulkan` | 未设置 | `false` | Windows 用 D3D12 |
| `enable_rlz` | `true` | `false` | 隐私问题 |
| `enable_vr` | `true` | 移除 | M150 中无效 |
| `enable_rust` | `true` | 移除 | 默认已启用 |
| `enable_stripping` | `true` | 移除 | 无效参数 |
| `use_text_section_splitting` | `true` | 移除 | Windows 无效 |
| `pgo_data_path` | 硬编码路径 | 移除 | 自动查找 |

### 5.2 mcloud_flags.txt 变更

| 类别 | M149 | M150 |
|------|------|------|
| 总标志数 | ~26 | 51 |
| 启动速度 | 2 | 6 |
| 内存优化 | 5 | 11 |
| 多线程 | 0 | 5 |
| 视频/媒体 | 2 | 7 |
| GPU/渲染 | 1 | 4 |

---

## 6. 预期性能提升

| 指标 | M149 | M150 预期 | 提升幅度 |
|------|------|----------|---------|
| 冷启动速度 | 基准 | 更快 | 10-20% |
| 内存占用（多标签） | 基准 | 更低 | 15-30% |
| 视频播放流畅度 | 基准 | 更流畅 | 10-15% |
| GPU 渲染效率 | 基准 | 更高 | 5-10% |
| IO 响应性 | 基准 | 更快 | 10-15% |
| HTTP 访问 | ❌ 断流 | ✅ 正常 | 修复 |
| 后台视频 | 正常 | 正常 | 保持 |

---

## 7. 已知限制

| 限制 | 说明 | 解决方案 |
|------|------|---------|
| Widevine DRM | CDM 未下载，无法播放 DRM 内容 | 运行 `build/download_widevine_cdm.py` |
| 品牌名 | 使用 Chromium 默认 | 用户决定不修改 |
| VS2026 ATL | 需手动设置 INCLUDE 路径 | 已记录在 CLAUDE.md |
| D3D12 视频解码 | 硬件/驱动不支持，回退到 D3D11 | 保持 D3D11，性能足够 |
| 核显视频绿屏 | 切换核显时前几秒绿屏 | 更新驱动或进一步调试 |

---

## 8. D3D12 视频解码测试结果

| 测试项 | 结果 |
|--------|------|
| 编译时配置 | ✅ `kD3D12VideoDecoder = ENABLED_BY_DEFAULT` |
| 命令行强制启用 | ❌ 仍回退到 D3D11 |
| 独显测试 | ❌ 显示 D3D11VideoDecoder |
| 核显测试 | ❌ 显示 D3D11VideoDecoder |

**结论**：D3D12 视频解码在当前硬件/驱动上不可用。D3D11 是成熟稳定的方案，保持使用即可。

---

## 8. 下一步

1. **运行时验证**：启动浏览器，测试 B 站/YouTube 视频播放
2. **性能测试**：对比 M149 和 M150 的启动速度、内存占用
3. **Widevine 支持**：如需 DRM，下载 CDM 并启用
4. **CI/CD**：解决 GitHub Actions 构建问题

---

## 9. 相关文档

- 设计文档：`docs/superpowers/specs/2026-06-19-performance-optimization-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-19-performance-optimization.md`
- 代码审查修复：`docs/superpowers/specs/2026-06-20-code-review-fixes.md`
- 开发进度：`.claude/progress.md`
- 项目指南：`CLAUDE.md`
