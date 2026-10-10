# M155 性能新特性挖掘与候选 flag 清单

- **日期**：2026-10-10（配合 `docs/tasks/m155-upgrade-preassessment.md`）
- **方法**：用声明位扫描分别建立 M151 与 M155 的 `base::Feature` 全集（`BASE_FEATURE` / `DEFINE_FEATURE` / `UNI_FEATURE` / `FEATURE` / `BASE_DECLARE_FEATURE`，含跨行声明与默认状态），做集合 diff：**M155 新增 809 个声明、移除 609 个**，其中含性能关键词的新增 **118 个**。再对每个候选回到源码读声明处注释与所在组件，判断是否属于"桌面 Windows x64 可用"（ADR-003 只发 Win x64，Android/WebView/CrOS 前缀项一律排除）。
- **原始材料**：`.bugreview/declared_features_151_155.json`（两版全集 + 默认状态）、`.bugreview/m155_added.txt`（118 条性能相关新增全列表）、`.bugreview/name_archaeology.py`（可重复执行）
- **纪律（重要）**：本清单里的条目**不得进 M151-r3**。它们在 M151 上不存在，写进 flags 文件只会变成又一批静默失效条目（正是 D48 的成因）。正确做法是升级到 M155 之后，按第 4 节的基准流程逐项启用并验证，同时把 `.bugreview/flag_stability.py` 的校验版本集合改成 `[当前基线, 目标版本]`。

## 1. Tier A：建议纳入并在升级后逐项 A/B 验证

| 候选（`--enable-features=`） | 声明位置 | 上游默认 | 作用（源码注释原意） | 预期受益指标 | 风险 / 备注 |
|---|---|---|---|---|---|
| `DeferLayoutDuringBrowserStartup` | `chrome/browser/ui/ui_features.cc:591` | 禁用 | 启动期多个 WebUI/工具栏冗余布局经 Mojo 反复触发布局并阻塞 UI 线程，推迟并合并到窗口显示后执行，"saves significant CPU cycles" | K1 冷启动、启动 CPU 峰值 | 低；纯启动路径 |
| `ImprovedStartupBestEffortDelay` | `chrome/common/chrome_features.cc:111` | 禁用 | 标签加载/空闲且首屏之前延迟 BEST_EFFORT 任务 | K1 冷启动 | 低；与 `BoostClosingTabs` 等优先级项需一起看 |
| `DeferSessionStorageScavengingOnStartup` | `content/public/common/content_features.cc:266` | 禁用 | 推迟 Session Storage 清理，避免 LevelDB 初始化卡住启动关键路径 | K1 冷启动 | 低 |
| `MojoDirectSharedMemoryAllocation` | `mojo/core/embedder/features.cc:30` | 禁用 | Mojo 共享内存直接分配路径 | IPC 延迟 → 输入/合成 | 中；影响所有进程间通道，必须与崩溃率一起看 |
| `VizDirectCompositorThreadIpcNonRoot` | `components/viz/common/features.cc:376` | 禁用 | 非根 CompositorFrameSink 的 IPC 直达 viz 合成线程，不再先跳 IO 线程 | 滚动/合成延迟 | 中；注意其兄弟项 `…FrameSinkManager` 在 151 就已默认启用 |
| `PreconnectManagerDirectFastPath` | `content/browser/preloading/preconnect/preconnect_manager_impl.cc:30` | 禁用 | preconnect 管理器直连快路径 | 首屏资源建连耗时 | 低；与我们既有 `LCPPAutoPreconnectLcpOrigin`、`BookmarkTriggerForPreconnect` 同域 |
| `BindURLLoaderFactoryToHighPriorityTaskRunner` | `services/network/public/cpp/features.cc:572` | 禁用 | 把 URLLoaderFactory 的 Mojo receiver 绑到高优先级 task runner | 导航响应性 | 中；可能挤压后台任务，与窗口拖拽冻结历史相关，须实测 |
| `CacheControlImmutable` | `net/base/features.cc:163` | 禁用 | 允许 `Cache-Control: immutable` 覆盖 `Pragma: no-cache` | 二次访问命中率、K3 导航 | 低；语义标准化行为 |
| `DnsPlatformFailFastAndRetry` | `net/base/features.cc:79` | 禁用 | DNS_PLATFORM 查询 fail-fast + 重试 | DNS 解析尾延迟 | 低；与我们的 `AsyncDns` 叠加需实测 |
| `EnableIntermediateDnsResults` | `net/base/features.cc:128` | 禁用 | 向 ServiceEndpointRequest 交付中间结果（`HappyEyeballsV3` 开启时自动生效） | 建连耗时 | 低；若同时开 `HappyEyeballsV3` 则本项冗余 |
| `UseDnsHttpsSvcbAddressHints` | `net/base/features.cc:85` | 禁用 | 携带 HTTPS(SVCB) 记录的 ipv4hint/ipv6hint | 首包耗时 | 低；父特性 `kUseDnsHttpsSvcb` 已默认启用 |
| `AsyncDnsQuicJob` | `net/base/features.cc:354` | 禁用 | QUIC 会话池用 ServiceEndpointRequest 做异步解析 | QUIC 建连 | 中；依赖网络服务改动 |
| `QuicUseReadMultiple` | `net/base/features.cc:879` | 禁用 | `QuicChromiumPacketReader` 用 ReadMultiple 批量收包 | 高带宽吞吐 | 低 |
| `QuicSlowTimerBasedOnRTT` / `AdjustQuicSlowTimerDelay` | `net/base/features.cc`（155 新增） | 禁用 | 慢定时器按 RTT 自适应 / 调整慢定时器延迟 | 弱网 QUIC 恢复 | 中；两者语义相关，先单独测 |
| `PartitionAllocAdaptiveMemoryReclaimInterval` | `base/allocator/partition_alloc_features.cc:325` | 禁用 | 按可 decommit 量自适应内存回收间隔：空闲进程更少被唤醒，压力大时加快回收 | K2 内存、后台功耗 | 中；与我们已启用的 `PartitionAllocMemoryReclaimer` 直接交互，必须成对测量 |
| `DecodeScriptsInBlink` | `third_party/blink/common/features.cc:383` | 禁用 | 流式脚本由 blink 解码后再把解码数据交给 V8 | 脚本解析耗时 | 中；改动主线程/线程池分工 |
| `FontDataManagerPrewarming` | `content/common/features.cc:324` | 禁用 | 经 FontDataManager 投机预热字体族 | 首屏文字绘制 | 低；与我们已启用的 `PreloadSystemFonts` 互补而非重复 |
| `ResampleScrollEventsForFling` | `third_party/blink/common/features.cc:1960` | 禁用 | ScrollPredictor 预测 momentum 阶段事件（fling 重采样） | 滚动手感 | **优先级高**：用于接替 M155 已删除的 `FlingSchedulingImprovements` |
| `ApplyScrollRailingInRenderer` | `ui/base/ui_base_features.cc:228` | 禁用 | 在渲染端应用 scroll railing | 过滚回弹质感 | 低；同上属滚动接替项 |

谨慎项（进 Tier A 但需先确认与既有缺陷无冲突）：`PrioritizeResizeTaskRunnerOnStartup`（`content/common/features.cc:583`，155 新增，默认禁用）与"窗口拖拽/缩放冻结"这一历史问题（见 `docs/progress.md` 4.6 与已定案的 4 项永久禁用标志）直接相关，启用前必须复现拖拽场景再决定。

## 1.1 适用性核实（M155 真实引用点，实测于 `155.0.8059.40` 对象库）

方法：按**去 k 的名字**检索。消费者普遍调用 `Is<Name>Enabled()` 辅助函数，只搜 `k<Name>` 会漏报（本探针第一版就因此把 `VizDirectCompositorThreadIpcNonRoot` 误判成仅声明，已纠正）。剔除单测/浏览器测试文件后看剩余实现引用，并检查上游是否注册了 field trial。

| 候选（去掉 k 前缀） | 引用文件数 | 主要实现引用 | 上游 field trial | 桌面可达性判定 |
|---|---|---|---|---|
| `DeferLayoutDuringBrowserStartup` | 6 | `chrome/browser/ui/views/frame/browser_view.cc`, `chrome/browser/ui/views/frame/browser_view.h` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `ImprovedStartupBestEffortDelay` | 9 | `chrome/browser/after_startup_task_utils.cc`, `chrome/browser/chrome_browser_main.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `DeferSessionStorageScavengingOnStartup` | 4 | `content/browser/storage_partition_impl.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `MojoDirectSharedMemoryAllocation` | 5 | `content/app/initialize_mojo_core.cc` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `VizDirectCompositorThreadIpcNonRoot` | 5 | `components/viz/service/frame_sinks/compositor_frame_sink_impl.cc`, `components/viz/service/main/viz_compositor_thread_runner_impl.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `PreconnectManagerDirectFastPath` | 4 | `content/browser/preloading/preconnect/preconnect_manager_impl.cc`, `content/browser/preloading/preconnect/preconnect_manager_impl.h` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `BindURLLoaderFactoryToHighPriorityTaskRunner` | 4 | `services/network/prefetch_matching_url_loader_factory.cc` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `CacheControlImmutable` | 4 | `net/http/http_response_headers.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `DnsPlatformFailFastAndRetry` | 9 | `net/dns/dns_platform_android_attempt.cc`, `net/dns/dns_transaction.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `EnableIntermediateDnsResults` | 5 | `net/dns/host_resolver_manager_job.cc` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `UseDnsHttpsSvcbAddressHints` | 5 | `net/dns/dns_response_result_extractor.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `AsyncDnsQuicJob` | 10 | `net/dns/host_resolver_manager_job.cc`, `net/http/http_stream_factory_job_controller.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `QuicUseReadMultiple` | 13 | `net/quic/quic_chromium_packet_reader.cc`, `net/quic/quic_proxy_datagram_client_socket.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `PartitionAllocAdaptiveMemoryReclaimInterval` | 3 | `base/allocator/partition_alloc_support.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `DecodeScriptsInBlink` | 6 | `third_party/blink/renderer/bindings/core/v8/script_streamer.cc`, `third_party/blink/renderer/bindings/core/v8/script_streamer.h` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `FontDataManagerPrewarming` | 4 | `content/child/font_data/font_data_manager.cc` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `ResampleScrollEventsForFling` | 7 | `components/input/fling_controller.cc`, `third_party/blink/renderer/platform/widget/input/scroll_predictor.cc` | 有 | ✅ 有跨平台实现引用，桌面可达 |
| `ApplyScrollRailingInRenderer` | 5 | `ui/events/gesture_detection/gesture_provider.cc`, `ui/events/gesture_event_details.h` | 无 | ✅ 有跨平台实现引用，桌面可达 |
| `PrioritizeResizeTaskRunnerOnStartup` | 6 | `content/browser/browser_main_loop.cc`, `content/browser/scheduler/browser_task_queues.cc` | 有 | ✅ 有跨平台实现引用，桌面可达 |

补充观察：

- 多数候选已在 `testing/variations/fieldtrial_testing_config.json` 注册实验，即上游把它们当作待验证特性灰度发布，这与本项目「启用前必须逐项 A/B」的纪律一致。
- `VizDirectCompositorThreadIpcNonRoot` 的真实消费点在 `components/viz/service/frame_sinks/compositor_frame_sink_impl.cc`、`components/viz/service/main/viz_compositor_thread_runner_impl.cc`、`content/gpu/gpu_main.cc`，属 GPU 进程路径，Windows 可达。
- `MojoDirectSharedMemoryAllocation` 虽出现在 Android flag list 里，但实现引用位于 `content/app/initialize_mojo_core.cc`（所有进程的 Mojo 初始化），不是 Android 专属。
- `DeferLayoutDuringBrowserStartup` 的消费点在 `chrome/browser/ui/views/frame/browser_view.cc`（Views 桌面窗口路径），对本产品直接相关。
## 2. Tier B：M155 已默认启用，只需在升级后确认行为（不必写进 flags）

`DefaultDisableGpuLaunchTimeout`、`QueuedCompositorWebContentsUpdates`、`ReuseScanoutRenderPassBacking`、`SpeculationRulesRendererSideHeuristics`、`PrerenderUntilScriptProcessReuse`、`PrefetchRevampAcceptHeader`、`AncestorThrottleEvaluateRedirectSource`、`SearchPrefetchPreloadServingMetrics`、`ExtensionServiceWorkerPriorityVoter`。
写进 flags 只会制造 D48 式冗余条目，正确处置是把它们记入升级验证检查点（确认默认路径生效即可）。

## 3. Tier C：明确不建议

- **Android / WebView / CrOS 专属**：`WebViewWarmupNetworkService`、`WebViewBoostRendererPriorityOnNavigation`、`WebViewPurgeMemoryInBackground`、`TweakApplicationPreload*`（位于 `chrome/browser/flags/android/chrome_feature_list.cc`）等——ADR-003 只发 Windows x64，引入即死代码。
- **安全权衡未评估**：`EnableTLS13EarlyData`（0-RTT，重放风险）。注意这正是我们原先写错的 `EarlyData` 的上游真名——原条目在 151/155 都无操作，因此**从未真正开启过 0-RTT**；若将来要开，需作为安全决策单独评审，不能混在性能清理里。
- **与既有策略相悖**：`PrewarmDisableOnStartup`、`TweakApplicationPreloadSkipWarmUp`（削弱预热，与我们的启动预热方向相反）。
- **UI/功能向而非性能向**：`ThemeChangeOptimization`、`OnDemandBackgroundTabContextCaptureOptimization` 等。

## 4. 失效条目后继归因（D48 的收口）

| r3 已删除条目 | 归因 | 证据 |
|---|---|---|
| `CanvasOopRasterization` | 上游已无该 feature，151/155 声明位均无（仅存一处历史注释） | 关键词扫描 0 命中 |
| `AVIF` / `ServiceWorkerNavigationPreload` | 同名 feature 不存在；命中的是 `ImageType::kAVIF`、`WebFeature::kServiceWorkerNavigationPreload` 等枚举/计数，与 feature 无关 | 声明位扫描 0 命中 |
| `SpeculationRules` | 基线能力已默认化；155 的后继增强是 `SpeculationRulesRendererSideHeuristics`（默认启用）与 `AutoSpeculationRules`（默认禁用） | 见 §1/§2 |
| `EarlyData` | 真名为 `EnableTLS13EarlyData`（151/155 均默认禁用）→ 属"从未生效"，不是"生效后被删" | `net/base/features.cc` |
| `DirectComposition` | 无同名 feature；上游是同族多个开关（`…ResizeFixes`/`…SoftwareOverlays`/`…UnlimitedOverlays`/`…LetterboxVideoOptimization`，前三个默认已启用） | `components/viz`/`ui` 声明位 |
| `BestEffortTaskInhibitingPolicy`（改为注释保留） | 真名 `EnableBestEffortTaskInhibitingPolicy`（151/155 默认禁用）。启用会改变行为，需按第 7 章基准单独验证 | `components/performance_manager/public/features.h:104` |
| `FlingSchedulingImprovements`（r3 保留 + 标记） | 151 存在且我们启用（真实生效）；155 起标识符彻底消失且无同名后继 → 升级时必须删除，并用 §1 的两个滚动接替项重做评估 | 两版全集 diff |

## 5. 验证流程（升级后逐项执行）

1. 每次只加入 1 个 Tier A 条目 → `deploy_mcloud.py` → 重启浏览器 → 用 `benchmark/tools/verify_builtin_flags.ps1` 确认它进入子进程命令行。
2. 采 K1（冷启动）/K2（50 标签内存）/K3-K6（导航、滚动）各 ≥5 轮，与"同一构建去掉该条目"的 A/B 基线对比；无收益或有回退即撤回。
3. 内存类候选（`PartitionAllocAdaptiveMemoryReclaimInterval`）额外确认 K2 不劣化（我们已有 ADR-002：性能优先，但内存回归仍有否决权）。
4. 全部候选测完后，把胜出项写进 `mcloud_flags.txt` 并跑 `python .bugreview/flag_stability.py`（此时版本集合应为 `[155, 156]`），再更新 `docs/CMDLINE_FLAGS_LIST.md` 与 CHANGELOG。
