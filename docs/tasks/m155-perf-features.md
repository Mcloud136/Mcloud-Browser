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

## 5. 验证流程（2026-10-10 已按此实装，执行者 `.bugreview/ab_flags.py`）

原写的"加条目 → 重编 → 重启 → 人工看"流程在实测上不可行（一次全量重编只为改一行运行时 flags 是浪费），
已改为**同一二进制、只改构建目录运行时清单**的逐项 A/B。落地要点：

1. **单变量**：基线 = 仓库当前 `mcloud_flags.txt`；每个候选只写 `out/mcloud/mcloud_flags.txt`
   （仓库文件不动），测完在 `finally` 恢复并逐字节校验。
2. **变更算子必须是编辑而非追加**（`base/feature_list.cc:449-452`：disable 侧先注册且
   `RegisterOverride()` 用 emplace → 同名 feature 双写时**禁用胜出**）。所以
   `SkiaGraphite` 的"启用"臂用 `drop-line` 删掉 `--disable-features=SkiaGraphite`（回上游默认 ENABLED），
   追加 `--enable-features=SkiaGraphite` 是彻底无效的实验。
3. **静态前置校验**（任一不过就整轮拒绝开跑）：名字在 155 声明位存在、默认值与算子方向匹配、
   基线中没有反向覆盖、算子确实改变活动条目（注释行不计）。防的是 D48 那类"名字写错被静默忽略"。
4. **运行时生效证明**：启动一次 chrome，从 `Win32_Process.CommandLine` 解析子进程的
   `--enable-features=`（依据 `base/metrics/field_trial.cc:690` → `GetCommandLineFeatureOverrides()`）。
   没进回显的臂直接记为"未注册"并**跳过计时**——测一个不生效的臂只会产出"与基线无差异"的假数据。
   ⚠ 该回显是 command-line-only 集合，**不含带 params（走 trial 通道）的条目**，判读边界见 D51。
5. **采四项指标**（与升级验收口径一致：高性能 / 避免内存泄漏 / GPU 有效）：
   K1 冷启动中位数（5 轮，原始值留档算噪声带）、K2 50 标签工作集中位数（3 采样）、
   泄漏探针（3 轮 × 20 标签，看"关标签后驻留漂移"而非峰值）、GPU 探针（gpu-process 存活 +
   无 SwiftShader/Vulkan 回退）。配置之间留 25 s 冷却并清残留进程。
6. **判定标准（先看数据前定死，避免事后找理由）**：
   - 否决线：K1 比基线慢 > 3 ms，或 K2 涨 > 2%，或泄漏漂移比基线差 > 5 MB，或 GPU 探针回退/掉进程 → 撤回。
   - 采纳线：至少一项相对基线有超出噪声带的改善（K1 ≥ 3 ms、K2 ≥ 3%、泄漏 ≥ 5 MB 之一）。
   - 噪声带取自基线自身的 5 轮散布；全部落在带内 = 无收益 = 不采纳（不给"可能有用"留位置）。
   - 例外：`SkiaGraphite` 属窗口拖拽冻结缓解定案（4 项永久禁用之一），**即使测出收益也不自动撤销**，
     需要用户在同一构建上做拖拽+视频复现后才决定；本轮只出数据。
7. 胜出项写回 `mcloud_flags.txt` 后：`python .bugreview/flag_stability.py 155 156`（跨版本存活性）+
   `python .bugreview/flag_runtime_state.py`（运行时回显核对）都要过，再更新
   `docs/CMDLINE_FLAGS_LIST.md`、CHANGELOG 与升级报告。

### 5.1 A/B 结果（M155.0.8059.40，同一二进制，`out/mcloud` 运行时清单）

**Round 1**（11 配置 = 基线 + 10 臂；原始数据 `.bugreview/ab_results_round1.json` /
`ab_table_round1.md` / 执行日志 `ab_run_round1.log`；判定由 `.bugreview/ab_verdict.py`
按 §5.1 第 6 条预先登记的阈值机械得出，不是看完数据再定的）：

基线：K1 中位数 51 ms（5 轮原始值 `[69, 51, 45, 52, 51]`）/ K2 2586.8 MB（58 进程）/
关标签后驻留漂移 −2.7 MB / GPU 进程存活、无 SwiftShader 回退。

| 臂 | ΔK1(ms) | ΔK2(%) | Δ泄漏(MB) | GPU | 预登记判词 |
|---|---|---|---|---|---|
| `SkiaGraphite` 回上游默认（启用） | +1 | −0.3 | +1.9 | 正常 | 无差异｜定案项，不据此撤销 |
| `MojoDirectSharedMemoryAllocation` | −1 | +0.5 | **+6.6** | 正常 | **撤回**（泄漏否决线） |
| `VizDirectCompositorThreadIpcNonRoot` | −4 | −0.2 | +4.0 | 正常 | 无差异 |
| `DeferLayoutDuringBrowserStartup` | +1 | +0.7 | −3.4 | 正常 | 无差异 |
| `ImprovedStartupBestEffortDelay` | −1 | −0.2 | **+8.7** | 正常 | **撤回**（泄漏否决线） |
| `DeferSessionStorageScavengingOnStartup` | −5 | −0.8 | +3.9 | 正常 | 无差异 |
| `PartitionAllocAdaptiveMemoryReclaimInterval` | −4 | +0.0 | **−5.0** | 正常 | **采纳**（泄漏改善过线） |
| `PreconnectManagerDirectFastPath` | 0 | +0.2 | **+6.6** | 正常 | **撤回**（泄漏否决线） |
| `InitialWebUI` 纯名 | +1 | −0.3 | +2.3 | 正常 | 无差异 |
| `InitialWebUI` 修正 params 语法 | — | — | — | — | activation 门禁跳过（见下） |

必须先说的方法学结论（比单项结论更重要）：

- **K1 在本机 5 轮量测下不具备判别力**。基线自身散布 45–69 ms，按 `(max−min)/2` 得的噪声带就是
  ±12 ms，比所有候选的 ΔK1 都大。所以本轮及以后的 A/B **不采信任何 K1 结论**，判定只能靠
  K2（重复性明显更好）与泄漏驻留漂移；要用 K1 判别启动收益，至少需 15–20 轮并去掉首冷 outlier。
  这一条同时提醒：`docs/dev-logs/M151-r3-benchmark.md` 里单次 5 轮的 K1 差值同样不能当作收益证据。
- **泄漏探针的自身噪声量级 ≈ ±10 MB，比本轮所有差值都大**。依据不是猜测而是已归档的同机序列：
  `docs/dev-logs/M155-upgrade-report.md` 的 M155 泄漏探针（4 轮 × 25 标签）驻留序列为
  957.5 → 949.1 → 938.0 → 950.3 MB，相邻差 −8.4 / −11.1 / +12.3 MB。
  所以 round 1 里 −5.0（PartitionAlloc）与 +6.6 / +8.7（Mojo / Preconnect / Improved）
  **都落在噪声内**：既不能证明"有益"，也不能证明"有害"。这三条"撤回"的准确表述是
  "未见收益且存在负向倾向"，而不是"实测有内存回归"。阈值 ±5 MB 定得与噪声同量级，是本轮
  方法学上最主要的缺陷，已记录并要求后续轮次用"同配置重复测量"来先定噪声再定阈值（round 2 即如此）。
- `InitialWebUI` 两个臂是本轮的**方法学对照组**，不是性能候选：
  纯名臂无差异 ⇒ 支持"基线里 InitialWebUI 本就启用"（D51 的修正结论，见缺陷档案）；
  带 params 臂被 activation 门禁判为"未进回显"而跳过计时 ⇒ 直接演示了
  `GetFeatureOverridesImpl(command_line_only=true)` 会跳过带 trial 的 override，
  即"运行时回显集合"≠"已启用集合"。

本轮结论（**已被 §5.3 的重复测量推翻其判定强度，最终判定见 §5.3**）：**没有一项候选能给出超出噪声的收益**。
唯一触到"采纳线"的是 `PartitionAllocAdaptiveMemoryReclaimInterval`（关标签后驻留少 5.0 MB，
方向与内存取向一致），但该幅度小于探针自身噪声 → 只能靠同配置重复测量决定是否成立；
三项"泄漏否决"同样在噪声内，其准确读法是"未见收益"。基线自身在 round 1 里的
K2 与 K1 与升级报告一致（K2 2586.8 vs 报告 2563.3，约 +0.9%），说明构建与机器状态未漂移，
判据的短板在测量精度而不是被测对象。

### 5.2 本轮判据覆盖不到的收益面（有意不强行采纳）

`.bugreview/ab_flags.py` 的四项判据是 K1 冷启动 / K2 50 标签工作集 / 关标签驻留漂移 / GPU 进程与后端。
用这套判据去测"只有真实网页加载或交互才体现差异"的候选，产出的必然是"与基线无差异"的假数据，
所以以下候选**不在本轮判定范围内**，需要各自对应的测量面才能判定：

| 候选 | 为什么现有判据测不出 | 判定它需要的测量 |
|---|---|---|
| `DnsPlatformFailFastAndRetry`、`EnableIntermediateDnsResults`、`UseDnsHttpsSvcbAddressHints`、`AsyncDnsQuicJob` | 差异在解析/建连尾延迟，本地 `about:blank` 与固定标签数完全不涉及 | 真实站点的 K3 导航 + `net-log` 解析耗时分布（且依赖本机网络环境，噪声极大） |
| `QuicUseReadMultiple`、`QuicSlowTimerBasedOnRTT`、`AdjustQuicSlowTimerDelay` | 只在高带宽/弱网 QUIC 会话上有差异 | 定向 QUIC 站点吞吐与恢复时间测量 |
| `CacheControlImmutable` | 只有命中 `Cache-Control: immutable` 的站点才有效果 | 固定语料的二访 K3 导航（需自建含 immutable 响应的测试站） |
| `DecodeScriptsInBlink`、`FontDataManagerPrewarming` | 差异在脚本解析/首屏文字绘制，不在启动与驻留内存 | 需 K3/K6（页面级耗时） |
| `ResampleScrollEventsForFling`、`ApplyScrollRailingInRenderer` | 主观滚动质感与 jank 帧分布 | 需滚动帧时采集（frame timing），非本机现成工具 |
| `BindURLLoaderFactoryToHighPriorityTaskRunner`、`PrioritizeResizeTaskRunnerOnStartup` | 与"窗口拖拽/缩放冻结"历史问题直接相关，自动化 KPI 无差异不代表安全 | 必须先人工复现拖拽+视频场景，再决定是否值得测 |

在本轮之内但收益测不出的：`PreconnectManagerDirectFastPath` —— 本轮只能给出"能注册 + 四项 KPI 不劣化"
的下界结论，它真正的收益（首屏建连耗时）要等 K3/net-log 通道；结论口径会按此写，不会把"无差异"当成"无用"。

`SkiaGraphite` 虽在本轮，但属窗口拖拽冻结缓解定案项，按第 6 条例外规则处理（数据出结果也不自动撤销）。

### 5.3 Round 2 交错复测与最终判定（定稿）

目的不是"多测几遍取平均"，而是**先量出判据自身的可重复性**，再回头看 round 1 的结论还剩下什么。
做法：基线与两个边界项（`PartitionAllocAdaptiveMemoryReclaimInterval` = round 1 唯一过采纳线、
`ImprovedStartupBestEffortDelay` = round 1 最大负向 +8.7 MB）各测 **2 遍并交错排列**
（基线→A→B→基线#2→A#2→B#2），泄漏轮数提到 5。数据 `.bugreview/ab_confirm.json`，
表 `.bugreview/ab_confirm_table.md`，日志 `ab_confirm.log`。

| 配置 | K1(ms) | K2(MB) | 泄漏漂移(MB) |
|---|---|---|---|
| (基线) | 47 | 2593.0 | +9.4 |
| ImprovedStartupBestEffortDelay | 46 | 2601.1 | +8.6 |
| PartitionAllocAdaptiveMemoryReclaimInterval | 47 | 2572.5 | −0.9 |
| (基线)#2 | 51 | 2588.0 | +0.5 |
| ImprovedStartupBestEffortDelay#2 | 52 | 2611.8 | −1.0 |
| PartitionAllocAdaptiveMemoryReclaimInterval#2 | 47 | 2598.1 | −0.9 |

同配置重复（基线两次）给出的**真实重复噪声**：K1 ±4 ms、K2 ±5.0 MB（0.19%）、泄漏 ±8.9 MB。
据此重判 round 1：

- **泄漏指标完全无区分力**：基线自己两次就差 8.9 MB，而 round 2 里候选与**同轮**基线只差 ≤1.5 MB。
  所以 round 1 的 −5.0（PartitionAlloc 采纳依据）与 +6.6 / +8.7（三条否决依据）**全部作废**，
  既非收益也非回归。附带发现：round 2 的泄漏值随"在同一轮里的先后位置"系统性下降
  （首配置 +9.4，之后 −0.9～−1.0），说明该指标被冷缓存/预热状态主导，不是 flags 的函数。
- **K2 也不足以支撑 ±1% 的判定**：三次独立取值为 Improved −3.9 / +8.1 / +23.8 MB、
  PartitionAlloc +0.8 / −20.5 / +10.1 MB，都跨零且散布 ~27 MB（>1%）。
- K1 与 round 1 同结论：无判别力（噪声带 12 ms，round 2 基线重复差 4 ms）。

**最终判定：本轮 8 项候选一律不采纳，`mcloud_flags.txt` 不新增任何条目**（只含 D51 的语法修正）。
理由不是"它们有害"，而是**现有判据无法证明它们有益**；在没有可重复收益的情况下往清单里加条目，
正是 D48 那批静默失效条目的成因。`SkiaGraphite` 保持显式禁用（定案项，四项判据本轮也看不出差别，
撤销它需要的是拖拽+视频场景的人工复现证据，不是 KPI）。

方法学改进（下轮 A/B 必须满足，否则不产出"结论"）：
1. **同轮配对**：候选必须与同一轮内的基线相减，禁止跨轮比绝对值。
2. **先定噪声再定阈值**：阈值取 2× 同配置重复散布；重复散布未知时先跑一遍只做重复测量。
3. K1 需 ≥15 轮且剔除首轮 cold outlier（本机首轮常年 59–69 ms，其余 44–52 ms），否则不参与判定。
4. 泄漏探针改为**每轮重置 profile** 或丢弃每轮首个样本，消除预热趋势；轮数 ≥5。
5. 预期收益小于上述噪声带的候选（本轮 8 项全部如此）不应进入 A/B，
   应先做成本更低的定向测量（如 K3/net-log）再决定是否值得测。

