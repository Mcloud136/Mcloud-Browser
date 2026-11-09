# M158 性能新 flag 候选清单（调研报告）

- **日期**：2026-11-08（当日晚间修订：取证源改为 Chromium 官方仓库）
- **用途**：配合 `docs/tasks/m158-upgrade-task.md` 阶段 3，判断 M155→M158 是否有值得加入 `mcloud_flags.txt` 的新性能开关。
- **结论先行**：**已从 Chromium 官方仓库取证到 M158 相对 M155 的真实新增 `base::Feature` 声明**，其中约 **11 个是 Windows 默认禁用、性能向**的新 flag，值得进入 A/B 队列；但**仍没有任何一条可以直接写进 `mcloud_flags.txt`**——还缺平台守卫审计、实现消费点核实和同机成对 A/B 三道关。上一版报告「无法核实 M158 新 feature 名」的结论由本次取证推翻。

---

## 1. 取证源与边界（先读）

| 项 | 事实 |
|---|---|
| **权威源** | `https://chromium.googlesource.com/chromium/src/+/refs/tags/<tag>/<path>?format=TEXT`（Gitiles，返回 base64，需解码）。这是 Chromium 项目本身的仓库 |
| **tag 核实** | 官方 `chrome/VERSION` @ `158.0.8127.30` = `MAJOR=158 / MINOR=0 / BUILD=8127 / PATCH=30`，tag 真实存在 |
| **GitHub 镜像不作判据** | `chromium/chromium` 是只读镜像，只镜像主 git 仓库。官方 `DEPS:3375-3376` 明确 `'src/v8': ...'/v8/v8.git@' + Var('v8_revision')` —— **v8 是 gitlink，主树里没有 v8 源码**；third_party、CIPD 二进制、PGO profiles 同样由 DEPS/gclient 拉取。镜像拿不到这些，tag 也未必与官方发布 tag 一一对应。本报告的结论一律以 googlesource 为准 |
| **本机仍无 M158 源码树** | 只有 `chromium-src`(M151) 与 `chromium-src-155`(M155)。远程 Gitiles 取证是**文本级**证据，不等于本地构建树可用 |
| **取证范围** | 本轮只 diff 了 5 个性能相关文件：`base/features.cc`、`net/base/features.cc`、`components/performance_manager/public/features.cc`、`gpu/config/gpu_finch_features.cc`、`third_party/blink/common/features.cc`。其中 `components/performance_manager/public/features.cc` 两侧返回非 base64（路径在两个 tag 均不可用），**未取证**，不列结论 |
| **取不到的部分** | `v8/`（gitlink）、`chrome/build/pgo_profiles/`、CIPD 工具链、`buildtools/` —— 必须在真实构建树上用 `gclient sync` 后才能核对 |

⚠ 本项目三层纪律：「名字在树里」≠「编译得进来」≠「这一行有净效果」。M155 升级期就清掉过 6 条根本不存在的 feature（D48）、2 条 Windows 编译不进来的死声明（D142），并把 15 项「上游默认已启用」重新定性为 pin（D177）。

**取证方法（可复现）**：
```
curl -s "https://chromium.googlesource.com/chromium/src/+/refs/tags/<tag>/<path>?format=TEXT" \
  | python -c "import sys,base64; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))" \
  | grep -oE 'BASE_FEATURE\([A-Za-z0-9_]+' | sed 's/BASE_FEATURE(//' | sort -u
```
对 `155.0.8059.40` 与 `158.0.8127.30` 各跑一次再 `diff`，只取 `>` 行。

---

## 2. 已从官方源取证的 M158 新增声明（真实名字，不是猜的）

### 2.1 Windows 默认 DISABLED、性能向 → **建议进 A/B 队列**（不直接写入）

| feature（去掉 `k`） | 声明位置 @158.0.8127.30 | 源码注释原意 / 预期受益 | 优先级 |
|---|---|---|---|
| `GpuInitOptimization` | `gpu/config/gpu_finch_features.cc:249` | 「GPU process initializes through GpuInit2. GpuInit2 is where GPU startup optimizations are being developed」→ K1 冷启动、GPU 进程启动 | **高** |
| `ANGLETrimMemoryOnIdle` | `gpu/config/gpu_finch_features.cc:845` | WebGL 上下文空闲时 trim ANGLE 内存缓存 → K2 内存 | **高** |
| `GpuPersistentCacheAsyncInitialize` | `gpu/config/gpu_finch_features.cc:491` | GPU 持久缓存异步初始化 → 启动卡顿 | 中 |
| `UpdateCompositorMemoryPolicyOnScreenChange` | `third_party/blink/common/features.cc:2302` | 屏幕变化时更新合成器内存策略 → 内存 | 中 |
| `FlushFileBuffersOnSyncFlush` | `base/features.cc:238` | 同步 flush 时刷底层文件句柄；声明紧邻 `#endif // BUILDFLAG(IS_WIN)`，疑为 **Windows 专属**，须用 `guard_audit.py` 确认守卫 | 中 |
| `Canvas2DAutoFlushParams` | `third_party/blink/common/features.cc:279` | Canvas2D 自动 flush 参数（带 params，写 flags 必须 `param/value` 成对，D51） | 中 |
| `ShaderDiskCacheBackendExperiment` | `net/base/features.cc:1109` | shader disk cache 后端实验 | 低 |
| `WebGPUUseDedicatedTransferBuffer` | `gpu/config/gpu_finch_features.cc:338` | WebGPU 专用传输缓冲，注释明确「only takes effect when explicitly enabled」 | 低 |
| `CookieMonsterPerKeyDelete` | `net/base/features.cc:1125` | Cookie 按 key 删除 | 低 |
| `HttpChunkedDecoderInRust` | `net/base/features.cc:1127` | chunked 解码改 Rust 实现 | 低 |
| `QuicAlwaysCancelPreExistingProbingOnMigration` / `DeviceBoundSessions*` | `net/base/features.cc` | 新增声明，**默认值本轮未取证**，先归类待核 | 待核 |

### 2.2 默认 ENABLED → **pin，写进去净效果为零**（D177 同族）

`I18nOptimizations`（`base/features.cc:71`）、`QuicWaitForNewNetworkTimeout`（`net:878`）、`ANGLETrimMemory`（`gpu:842`）、`FlushGpuChannelOnLayerTreeViewRelease`（`blink:748`）、`OffscreenCanvasSyncAnimationState`（`blink:762`）、`HeapVectorPromptlyFree`（`blink:822`）。正确处置是记入升级验证检查点，确认默认路径生效即可。

### 2.3 平台不可达 → **Windows 上不存在，不得写入**（D142 同族）

`AsyncProxyResolverApple`（`net:971`，位于 `#endif // BUILDFLAG(IS_APPLE)` 内）、`VulkanImaginationMSAA`、`AndroidDesktopUAModel`、`AndroidKeyboardContextMenu`、`WebRtcMacSharedImageEncode` 等。ADR-003 只发 Windows x64，写入即死代码。

### 2.4 本节结论的效力边界

以上只是**声明处的文本默认值**。仍需三项复核才能谈「启用」：
1. `guard_audit.py` 判 `#if` 平台守卫在本构建的实际取值（尤其 `FlushFileBuffersOnSyncFlush`）；
2. 查 **实现消费点**（`Is<Name>Enabled()`），排除「只有声明没人用」的 D48 形态；
3. 与 `mcloud_flags.txt` 现有 52 项去重，过 `flag_stability.py` 的 C 断言（三版存活），再做同机成对 A/B。

⚠ 用户日常用 **Intel 核显**；`GpuInitOptimization`、`ANGLETrimMemoryOnIdle` 等 GPU 路径候选必须按核显口径复核，不能拿独显实测值代替。

---

## 3. 项目自有的全树 diff 方法（构建机上必须再跑一遍）

`docs/tasks/m155-perf-features.md` 记录了本项目自己发明的方法，M151→M155 时的实测规模：
**M155 新增 809 个 `base::Feature` 声明、移除 609 个，其中含性能关键词的新增 118 个**。本轮 §2 只覆盖了 5 个文件，远不是全集。

| 资产 | 用途 |
|---|---|
| `.bugreview/name_archaeology.py` | 建立任意两版的声明全集并做 diff（含跨行声明与默认状态） |
| `.bugreview/declared_features_151_155.json`、`.bugreview/m155_added.txt` | 上一轮的全集与 118 条性能候选原文 |
| `.bugreview/guard_audit.py` | 平台守卫可达性 + **Windows 有效默认值**（判 pin 还是真优化） |
| `.bugreview/flag_stability.py` | A–F 断言，C 断言要求每条 feature 在三版均声明存在 |
| `benchmark/tools/check_features.py --src <M158树>` | 逐项存活性（M155 实测 53/53） |
| `.bugreview/ab_flags.py` | 同一二进制、只改运行时清单的逐项 A/B（单变量、编辑而非追加、运行时回显证明） |

**在构建机上要跑的顺序**：
1. `name_archaeology.py` 做 **155 → 158** 全树声明 diff，与 §2 的 5 文件结果合并去重；
2. 剔除 Android / WebView / CrOS 前缀；
3. `guard_audit.py --json` 逐项判平台守卫与 Windows 有效默认值 → 默认已启用者标 pin；
4. 查实现消费点 → 与现有 52 项去重 → 过 `flag_stability.py` C 断言；
5. `ab_flags.py` 逐项 A/B：K1 冷启动（5 轮）、K2 50 标签工作集（3 采样）、泄漏探针（关标签后驻留漂移）、GPU 探针；**没进子进程命令行回显的臂记为「未注册」并跳过计时**。

---

## 4. 已有候选队列（M155 遗留，M158 上复核默认值）

`docs/tasks/m155-perf-features.md` 的 **Tier A 20 项**都做过 M155 真实引用点核实（桌面可达），但 M155 升级报告记录：**只 A/B 了 8 项，全部因「同配置重复测出的噪声带（K1 ±4 ms、K2 ±0.19 %、泄漏 ±8.9 MB）内无法证明收益」而不采纳**。其余候选在 M158 上仍有评估价值，且要先核对默认值是否已被上游翻成 ENABLED（那样就变成 pin）。

| 优先级 | 候选 | 理由 |
|---|---|---|
| 高 | `ResampleScrollEventsForFling`、`ApplyScrollRailingInRenderer` | 用于接替 M152–155 被上游彻底删除的 `FlingSchedulingImprovements` |
| 高 | `DeferLayoutDuringBrowserStartup`、`ImprovedStartupBestEffortDelay`、`DeferSessionStorageScavengingOnStartup` | 纯启动路径，直接对应 K1；消费点在桌面 Views 路径 |
| 中 | `PartitionAllocAdaptiveMemoryReclaimInterval` | 与已启用的 `PartitionAllocMemoryReclaimer` 交互，必须成对测量；上一轮 round 1 过线、round 2 交错复测否掉 |
| 中 | `MojoDirectSharedMemoryAllocation`、`VizDirectCompositorThreadIpcNonRoot`、`BindURLLoaderFactoryToHighPriorityTaskRunner` | IPC / 合成 / 导航延迟，影响面大，须与崩溃率和拖拽冻结历史一起看 |
| 低 | `CacheControlImmutable`、`QuicUseReadMultiple`、`PreconnectManagerDirectFastPath`、`FontDataManagerPrewarming`、`DecodeScriptsInBlink`、DNS 系列 | 低风险，按噪声带门槛逐项筛 |

⚠ `PrioritizeResizeTaskRunnerOnStartup` 与「窗口拖拽/缩放冻结」历史问题直接相关，启用前必须人工复现拖拽场景；4 项永久禁用定案不得顺手恢复。

---

## 5. M156 / M157 / M158 上游改动里「看起来像性能、但不是 flag」的部分

以下均由 Chrome Platform Status / Chrome Releases 核实，**属于 Web 平台能力或存储后端变更，不应写进 `mcloud_flags.txt`**；正确处置是记入升级冒烟检查点：

| 版本 | 改动 | 性质 |
|---|---|---|
| 156 | IndexedDB 后端由 LevelDB + flat files 改为 **SQLite**（仅新 data store，旧数据不动，step 3 才迁移） | 可靠性 + 轻度性能；**是数据兼容风险**，需回归 profile / 扩展 / 站点存储 |
| 156 | `Avoid caching module failures`、WebGPU `WGSL Fragment Depth` 恢复 early-Z、WebTransport 自定义 headers | Web API / 图形能力 |
| 157 | HTML-in-Canvas 转正、Long Animation Frames 增 `styleDuration`、WebGPU 64 位原子 min/max、Background Fetch 强制 CORS | 画布能力 / **诊断指标** / 安全；`styleDuration` 是给开发者定位卡顿的，不提速 |
| 158 | `OfflineAudioContext` 增量渲染、WebTransport 并发流 / draining / reliability、媒体状态伪类、`::highlight(*)`、跨域 iframe 预渲染 | Web API；跨域 iframe 预渲染需站点 `Supports-Loading-Mode: prerender-cross-origin-frames` 响应头，**不是全局开关** |
| 158 | **XSLT 在 Stable 停止工作**（libxslt 老 C 库攻击面；OT / 企业策略例外到 Chrome 176 / 2027-08-17） | 安全收益，同时是兼容性回退 |

**安全修复不是 flag**：156 stable 354 项（6 Critical）、157 stable 213 项（7 Critical）。这是本轮升级最实在的收益，靠换内核获得，不靠开关。

---

## 6. 明确不采纳

- 网上通用「Chrome 优化 flag」文章里的 `process-per-site`、`enable-heavy-ad-privacy-sandbox`、`automatic-tab-discarding` 等：不是 M158 新增，属 D48 同族。
- 已在 `mcloud_flags.txt` 的 52 项、15 项 pin、2 条净零禁用：重复写入无收益。
- 已清理的死声明：`CanvasOopRasterization`、`DirectComposition`、`EarlyData`、`AVIF`、`SpeculationRules`、`ServiceWorkerNavigationPreload`、`BaseLockTrySpin`、`PartitionAllocUsePriorityInheritanceLocks`、`FlingSchedulingImprovements`、`ReduceHardwareVideoDecoderBuffers`、`PWAFullCodeCache`、`ServiceWorkerScriptFullCodeCache`。
- §2.2 的默认启用项、§2.3 的平台专属项。
- 与本项目方向相悖的：`PrewarmDisableOnStartup`、削弱预热的开关；`EnableTLS13EarlyData`（0-RTT 重放风险，须作为安全决策单独评审）。

---

## 7. 纪律提醒（任何新增开启项）

1. 先过 `flag_stability.py` 的 **C 断言**（三版存活）→ `guard_audit.py`（平台有效默认值）→ `flags_lint.py --guard`；A 断言基线是 `git show HEAD:mcloud_flags.txt`，改 flags 后必须**先提交、再复跑**才不会一直红。
2. 再做**同机成对 A/B**；上次 8 项候选全否说明「新 flag 不等于有收益」，跨会话绝对值差可达 1.5 %，不得当收益。
3. `mcloud_flags.txt` **不支持行尾注释**（D59），注释必须独占一行；带 params 必须写 `param/value` 成对（D51）。
4. 改 `mcloud_flags.txt` 会让 `release_chain_check.py` 的三处指纹不一致，必须**重打包 + 干净安装复验**，不能手工拷进已安装目录（D109/D175）。
5. **`mcloud_flags.txt` 本轮未改动**：§2 的候选都还没过 A/B，写入即违规。
