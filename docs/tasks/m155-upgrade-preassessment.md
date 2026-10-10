# M151 → M155/M156 内核升级可行性预评估

- **评估日期**：2026-10-10
- **评估人**：Qoder Agent（用户授权范围内）
- **任务依据**：用户要求"检查 Chromium 最新内核版本并找到对应更新文档"，随后授权"按第 9 章清单出升级可行性预评估，先比对 flags 存活性，再定目标版本"
- **方法**：全程只读——用定向浅拉取把候选 tag 的**对象**取入 `D:\wxmuma\chromium-src\src\.git`（HEAD 与工作树未动，`out/mcloud` 不受影响），再用 `git grep <rev>` / `git show <rev>:<path>` 做锚点与声明位比对；V8 侧通过 googlesource `?format=TEXT` 取 DEPS 固定版本的两个文件
- **一句话结论**：**升级技术上低风险（定制面只有 7 个上游文件 / 207 行，全部注入锚点与 API 在 M155/M156 原样存在，PGO 与 V8 依赖均已就绪）；本次评估发现的高危可复现性缺陷 D47 已于 2026-10-10 修复（新增 `apply_installer_payload.py` 并接入 deploy），D48 flags 清理与 M155 新特性挖掘也已完成。**
- **执行状态（2026-10-10 续）**：目标版本按用户决定取 **M155**；D47/D48 已修复并验证（见下）；M155 源码 + 工具链预拉取在 `D:/wxmuma/chromium-src-155`（首轮因 googlesource 429 限流未完整，已用低并发重试脚本续跑）；M155 性能新特性候选清单见 `docs/tasks/m155-perf-features.md`。

---

## 1. 上游版本现状（两个独立来源交叉验证）

| 频道 | 最新版本 | 日期 | 验证 |
|---|---|---|---|
| Stable | **155.0.8059.40**（前值 .39） | 2026-10-06 | `refs/tags/155.0.8059.40` = `cfaadc5a…`，与 ChromiumDash `hashes.chromium` 一致 |
| Early Stable | 156.0.8078.12 / .13 | 2026-10-07 | tag `156.0.8078.12` = `634b046f…`，同样一致 |
| 156 全量稳定 | 计划 2026-10-20 | — | Chrome Status（156 条目） |
| Beta | 156.0.8078.17 | 2026-10-06 | ChromiumDash |
| Canary | 157.0.8095.0 | 2026-10-09 | ChromiumDash |
| Extended Stable | 154.0.8037.100 | 2026-10-06 | ChromiumDash + tag |
| **本仓库基线** | 151.0.7922.99 | 上游切 tag 2026-07-28 | 本地 `git describe` = `151.0.7922.99`，HEAD `fbb5d9fd`（grafted） |

差距：**4 个大版本 / 74 天**。

## 2. 发布节奏已改为双周，升级策略必须改

Google 于 2026-09-08 通过官方博客宣布 Chrome 从四周发布周期切换为**两周**（"Os recursos chegam ao canal Stable a cada duas semanas"），企业/extended 线保持约 8 周。对 MCloud 的直接影响：

- 技术规范 9.1 的"原则上每个大版本升级一次"从此等于**每两周一跳**，逐版跟随不可行；
- 单次升级的代码 delta 反而变小（官方称"发布范围更小，便于回归定位"），攒批的代价主要是 flags/feature 名漂移累积；
- 建议把 9.1 改成"**按季度攒批，目标锚定当期 stable；每两月评估一次；CVE 高危公告 7 天内评估**"，并把 M151→M156 这类跨 5 个里程碑的攒批作为常态处理。

更新文档入口（已逐个验证可达）：按里程碑的新特性/弃用/移除/企业策略正文现在在 **Chrome Status**（`chromestatus.com/release-notes`；`developer.chrome.com/release-notes/155` 已 404，该页只留跳转）；安全修复与 CVE 看 Chrome Releases 博客；策略与管理变更看 Chrome Enterprise release notes；版本/分支位置看 ChromiumDash 与 googlesource tag 列表。

## 3. 必须重放的定制面（实测，不是估计）

`git status --porcelain -uno` 在构建树上枚举出的**全部**上游改动：

| 上游文件 | 变更量 | 由哪个脚本产生 | M155 锚点 | M156 锚点 |
|---|---|---|---|---|
| `build/config/BUILDCONFIG.gn` | +17 | `apply_polly_wiring.py` | ✅ 两个 `set_defaults()` 锚点均唯一 | ✅ |
| `build/config/compiler/BUILD.gn` | +39 | `append_polly_configs.py` | ✅ `common_optimize_on_ldflags` 存在 | ✅ |
| `build/config/win/BUILD.gn` | +5/−3 | `apply_avx2_baseline.py` | ✅ `-msse3` 原锚点块存在 | ✅ |
| `chrome/app/chrome_main_delegate.cc` | +144 | `inject_flags_loader.py` | ✅ `namespace {` + `std::optional<int> ChromeMainDelegate::BasicStartupComplete() {` + 5 个 include | ✅ |
| `chrome/browser/background/extensions/background_mode_manager.cc` | ±2 | `apply_mcloud_source_defaults.py` | ✅ 两处锚点原文一致（`RegisterBooleanPref(..., true)` / `SetBoolean(..., true)`） | ✅ |
| `media/base/media_switches.cc` | ±2 | 同上 | ✅ `BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_DISABLED_BY_DEFAULT);` | ✅ |
| **`chrome/installer/mini_installer/chrome.release`** | **+1** | **无脚本产生 → 缺陷 D47** | 文件存在，行缺失 | 文件存在，行缺失 |
| `build/config/compiler_opt.gni` | 新增文件 | `copy_essentials.py`（唯一白名单项） | ✅ 目标树无同名上游文件，可直接投放 | ✅ |

加载器正文依赖的 base API 在 M155/M156 全部保留：`base::SplitStringPiece`（签名不变，`std::string_view` 重载仍在 `base/strings/string_split.h`）、`base::ReadFileToStringWithMaxSize`、`base::StartsWith`、`base::PathService::Get` + `base::DIR_EXE`、`CommandLine::{HasSwitch,GetSwitchValueASCII,AppendSwitchASCII}`、`switches::{kEnableFeatures,kDisableFeatures}`（定义在 `base/base_switches.h`，注入脚本断言的是 `content_switches.h`，属断言指向不准但不影响编译，因目标文件本就 include 了 `base_switches.h`）、`FeatureList` 覆写路径仍为 `try_emplace`（D21 的用户优先合并语义不失效）。

`DoH 无需修改`这一条在 155/156 依然成立（`net::SecureDnsMode::kAutomatic` 在上游默认路径中）。

## 4. GN 参数与 V8 侧

- 主仓声明的参数（`use_thin_lto`/`chrome_pgo_phase`/`pgo_data_path`/`enable_rlz`/`win_enable_cfg_guards`/`proprietary_codecs`/`enable_platform_hevc` 等）在 155/156 均有声明或引用点；`use_sse3`/`use_avx2`/`is_full_optimization_build`/`use_polly`/`use_bolt` 属 MCloud 在 `compiler_opt.gni` 自行声明，不受上游影响。
- `v8_*` 参数声明在**独立的 v8 仓库**（主仓里 `v8/` 是 gitlink，`git grep` 看不到），因此按 DEPS 固定版本单独核对：M155 v8=`56832c16…`、M156 v8=`4b33f15d…`（本地 `src/v8` HEAD 恰为 M151 的 pin `2826b27d…`，控制组成立）。取 `v8/BUILD.gn` 后确认 `v8_symbol_level`、`v8_enable_fast_torque`、`v8_enable_builtins_optimization`、`v8_enable_maglev`、`v8_enable_turbofan`、`v8_enable_wasm_simd256_revec` 在 155/156 全部存在。
- `--js-flags` 里 4 个 V8 标志（`invocation_count_for_maglev`、`invocation_count_for_turbofan`、`osr_from_maglev`、`sparkplug_plus`）在 155/156 的 `src/flags/flag-definitions.h` 中均存在。

## 5. mcloud_flags.txt 逐项存活性（60 条 feature）

判定方法：构建目标版本的**已声明 feature 全集**（M151 7412 / M155 7576 / M156 7605 个 `kIdent`），再逐项要求 `k<Name>` 出现在声明位、或显式名字串出现在声明位。早期用"引号名串是否全树存在"的判法是错的——新版 `BASE_FEATURE(kFoo, <default>)` 不再写字符串名，运行时名由标识符去掉 `k` 推导。

| 判定 | 条数 | 说明 |
|---|---|---|
| 有效（上游默认与我们的意图不同，我们的覆盖真正起作用） | **37** | — |
| 冗余（上游默认已等同我们的意图，条目无副作用） | **15** | 含 `disable D3D12VideoDecoder`（正是仓库注释里"覆盖与运行时禁用互相抵消"那条） |
| 静默失效（M151 起就无此 feature，`--enable-features` 被 Chromium 忽略） | **7** | `CanvasOopRasterization`、`BestEffortTaskInhibitingPolicy`、`DirectComposition`、`EarlyData`、`AVIF`、`SpeculationRules`、`ServiceWorkerNavigationPreload` |
| 升级后新增失效 | **1** | `FlingSchedulingImprovements`（M151 存活，M152–M155 之间被上游移除） |

<code>BestEffortTaskInhibitingPolicy</code> 的真名是 <code>EnableBestEffortTaskInhibitingPolicy</code>（`components/performance_manager/public/features.h:104`），属改名未跟随；其余 6 条在目标树里连标识符都只出现在注释/枚举（`RequestHeaderType::kEarlyData`、`ImageType::kAVIF`、`WebFeature::kServiceWorkerNavigationPreload`）里，从未作为 feature 声明。

### 5.1 逐项明细

| feature（mcloud_flags.txt 条目） | 方向 | M151 | M155 | M156 | 上游默认（M156） | 判定 |
|---|---|---|---|---|---|---|
| `SpareRendererForSitePerProcess` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `BrowserProcessAboveNormalPriority` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `SendGPUChannelEarly` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `DeferSpeculativeRFHCreation` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `InitialWebUI` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `TransientKeepAlivePolicy` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `CanvasOopRasterization` | enable | 静默失效 | 静默失效 | 静默失效 | — | 失效条目（M151 起即无效） |
| `FlingSchedulingImprovements` | enable | 存活 | 已移除/无此名 | 已移除/无此名 | — | 升级后失效（M152–M155 被上游移除） |
| `BestEffortTaskInhibitingPolicy` | enable | 已移除/无此名 | 已移除/无此名 | 已移除/无此名 | — | 失效条目（M151 起即无效） |
| `DirectComposition` | enable | 已移除/无此名 | 已移除/无此名 | 已移除/无此名 | — | 失效条目（M151 起即无效） |
| `InfiniteTabsFreezing` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `InfiniteTabsFreezingOnMemoryPressure` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PartitionAllocEventuallyZeroFreedMemory` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PartitionAllocMemoryReclaimer` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `DiscardOnCommitLimit` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `SustainedPMUrgentDiscarding` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PartitionAllocSortActiveSlotSpans` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PartitionAllocUsePriorityInheritanceLocks` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `LowerPAMemoryLimitForNonMainRenderers` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `ReclaimOldPrepaintTiles` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PruneOldTransferCacheEntries` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `BookmarkTriggerForPrefetch` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `NewTabPageTriggerForPrefetch` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `BackForwardCache` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `CacheControlNoStoreEnterBackForwardCache` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `AsyncDns` | enable | 存活 | 存活 | 存活 | — | 有效 |
| `EarlyData` | enable | 静默失效 | 静默失效 | 静默失效 | — | 失效条目（M151 起即无效） |
| `AVIF` | enable | 静默失效 | 静默失效 | 静默失效 | — | 失效条目（M151 起即无效） |
| `SpeculationRules` | enable | 静默失效 | 静默失效 | 静默失效 | — | 失效条目（M151 起即无效） |
| `Prerender2WarmUpCompositorForNewTabPage` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `Prerender2WarmUpCompositorForBookmarkBar` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `LoadingPreconnectToRedirectTarget` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PreloadTopChromeWebUI` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `BookmarkTriggerForPreconnect` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `ThreadedPreloadScanner` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `ConsumeCodeCacheOffThread` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `InlineScriptCache` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `PreloadSystemFonts` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `HttpDiskCachePrewarming` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `LCPPAutoPreconnectLcpOrigin` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `RevokeMediaSourceObjectURLOnAttach` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `BackForwardCacheDWCOnJavaScriptExecution` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `GpuShaderDiskCache` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `IncreasedCmdBufferParseSlice` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `ResourcePoolPreferExactSizeReuse` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `HighFramerateRequestFromClient` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `PlatformHEVCDecoderSupport` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `HardwareSecureDecryptionAv1` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `DedicatedMediaServiceThread` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `DirectOpusAudioDecoding` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `EncryptedMediaOcclusionTracking` | enable | 存活 | 存活 | 存活 | 上游已默认启用 | 冗余（上游已默认启用） |
| `MediaFoundationBatchRead` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `MediaFoundationD3D11VideoCaptureZeroCopy` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `IOThreadInteractiveThreadType` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `MojoDedicatedThread` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `BaseLockTrySpin` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `BoostClosingTabs` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `UnimportantFramesPriority` | enable | 存活 | 存活 | 存活 | 上游已默认禁用 | 有效 |
| `ServiceWorkerNavigationPreload` | enable | 静默失效 | 静默失效 | 静默失效 | — | 失效条目（M151 起即无效） |
| `D3D12VideoDecoder` | disable | 存活 | 存活 | 存活 | 上游已默认禁用 | 冗余（上游已默认禁用） |

## 6. PGO 与工具链依赖

- `win_args_mcloud.gn:53` 为 `chrome_pgo_phase = 2`，`pgo_data_path` 现指向 `chrome-win64-7922-…profdata`。查 GCS 桶 `chromium-optimization-profiles/pgo_profiles`：win64 侧 **8037（M154）、8059（M155）、8078（M156）三个系列均已存在**（如 `chrome-win64-8059-1789468853-…`、`chrome-win64-8078-1790677744-…`），升级清单第 4 项不会卡。
- V8 builtins profiles 由 gclient hook 按目标 DEPS 拉取；M151 那次曾因版本不符被 `mksnapshot` 拒绝（升级报告偏差 3），155/156 需按同一路径复核版本。
- 本机到 `chromium.googlesource.com` 直连可用（本次两次浅拉取各约 1.5 分钟），代理不在线也能取。

## 7. 本次新发现的缺陷

### 本轮新增（编号沿用缺陷档案 `bug-review-pak-src-defects.md`，此前最大号为 D46）

> **处置状态**：D47 已修复（`win_scripts/apply_installer_payload.py` + 接入 `deploy_mcloud.py` 第 7 步 + `verify_sources.py` 关键脚本清单，探针 `d47_probe.py` 五例全过）；D48 已清理（删 6 条 + 改名转注释 1 条 + 升级期标记 1 条，稳定性断言 `flag_stability.py` PASS）；D49 待运行时歧义实验。

**D47 — 安装包清单文件的定制无脚本产生（High，发布链路可复现性）**
- 事实：构建树里 `chrome/installer/mini_installer/chrome.release` 多出的那一行 `mcloud_flags.txt: %(ChromeDir)s\` 只存在于**工作树的未提交修改**中。`win_scripts/deploy_mcloud.py` 的 6 个步骤（copy_essentials / apply_polly_wiring / append_polly_configs / apply_avx2_baseline / apply_mcloud_source_defaults / inject_flags_loader）**没有任何一个**写这个文件；全仓检索显示除了 `win_scripts/setup.py`（遗留禁跑脚本）通过 `other/mini_installer.patch` 间接涉及它之外，活跃流水线里无人产生；`docs/BUILDING_WIN.md`、`AGENTS.md`、技术规范均无记载，而 `README.md:259` 却写"flags 文件已随 chrome.release 清单打入安装包"，把它当作既有事实。
- 后果：在全新树（正是升级场景）按文档跑 `deploy_mcloud.py → gn gen → autoninja chrome mini_installer`，**编译与打包全部成功，但安装包里不带 `mcloud_flags.txt`**，63 行运行时标志整体丢失且没有任何报错。当前 r2 安装包之所以正确，只是因为这棵树恰好还留着那次手工改动。
- 建议处置：新增第 7 个幂等注入脚本（如 `apply_installer_payload.py`，锚点用 `chrome.exe: %(ChromeDir)s\` 行后插入，重复运行安全），挂进 `deploy_mcloud.py` 清单，`win_scripts/verify_sources.py` 增加存在性检查，并在 `docs/BUILDING_WIN.md`/`AGENTS.md` 记一步。发布侧的 `.bugreview/refresh_release.py` 已把"chrome.release 列出该文件"作为门禁，可作为回归哨兵保留。

**D48 — 7 条 flags 静默失效（Medium，性能面）**
- 事实与证据见第 5 节；影响是"以为开了、其实没开"，属于优化清单虚高，不是崩溃类风险。
- 建议处置：`BestEffortTaskInhibitingPolicy` 改为真名 `EnableBestEffortTaskInhibitingPolicy`（或直接删除并记录）；其余 6 条删除；`FlingSchedulingImprovements` 在升级到 155+ 时一并删除；把 `benchmark/tools/check_features.py` 的存活性校验纳入 `verify_sources.py`/CI，避免清单继续漂移。15 条冗余项可保留（用户显式覆盖时仍有语义），但在文件注释里标注"上游已默认，无需本行"。

**D49 — 文档"V8 连字符写法静默失效"的口径与源码不符（Low，文档）**
- 源码证据：`v8/src/flags/flags-impl.h:19` `static constexpr char NormalizeChar(char ch) { return ch == '_' ? '-' : ch; }`，标志名比较一律经 `FlagHelpers::EqualNameWithSuffix`/`flags.cc` 的下标比较归一化；因此 `--js-flags` 内 `--osr-from-maglev` 与 `--osr_from_maglev` **等价**，`--sparkplug-plus` 同理。
- 现状态：`AGENTS.md` 与 `mcloud_flags.txt` 注释都断言"连字符旧格式在 M151 静默失效（实证）"。本次未能复现该实证（结论来自更早会话，未附可复核产物）。
- 建议处置：把口径更正为"两种写法等价，V8 归一化 `_`/`-`"，并把原来的"实测失效"记录标为待复核；如需硬结论，做一次运行时验证（同一 flag 两种写法分别注入，读子进程命令行或 `chrome://system`/v8 统计区分歧）。**在核实前不要按旧口径改动 flags 文件。**

## 8. 目标版本建议与工作量

| 方案 | 说明 | 评价 |
|---|---|---|
| **A（推荐）** | 等 M156 于 2026-10-20 转全量稳定后直接升 **156** | 与升 155 工作量相同，锚点/依赖已同样验证通过；升完即为当期 stable，避免"刚升完就差一个里程碑" |
| B | 立即升 **155.0.8059.40** | 更快拿到 4 个里程碑的安全修复；但 10 天后即落后一个版本 |
| C | 暂不升级，先修 D47 + D48 并重发 M151-r3 | 若近期有对外发布计划，这是必须先做的一步——D47 使"任何一次干净重建树"都可能产出无 flags 的安装包 |

推荐顺序：**先 C 的两个修复（半天内可完成，且不改内核版本、无需全量重编译，仅需重打安装包并复跑发布门禁），再按 A 做升级**。

升级执行期工作量分级（按第 9 章 14 项清单映射）：

- 低：浅拉取 + checkout + `gclient sync`/`runhooks`（已实证 1.5 分钟级）、`compiler_opt.gni` 投放、6 个注入脚本重放（锚点全存活）、GN 参数重配（`gn gen --check`）。
- 中：profdata 换 8078 系列并改 `pgo_data_path`；V8 builtins profile 版本核对；全量重编译（M151 实测 54824 步）+ `mini_installer`；K1/K2/K7 基准回归。
- 需人工：flags 清单清理（D48，7+1 条删除 + 1 条改名，删前建议按"是否有实测收益"逐项判断，勿只按存在性一刀切）；`other/` 遗留补丁登记表的清理（31 个补丁中仅 `setup.py` 时代引用，活跃流水线一个都不跑，建议明确标注"Windows 路线不应用"）。

## 9. 本次评估的边界（未验证项）

1. 没有真正编译 155/156，所有"锚点存在"是**声明位/文本级**证据，不等于零编译错误（尤其 `chrome_main_delegate.cc` 的 +144 行注入体周边上下文若被上游改写，仍需现场合并）。
2. M156 以 `156.0.8078.12`（Early Stable）为样；10-20 转全量时的补丁号会更高，届时需按新 tag 复核一次存活性表。
3. D49 的结论来自 V8 源码阅读，未做运行时反证实验。
4. `--enable-features` 的 15 条冗余判定基于声明处默认值，若某 feature 还受 field trial 参数影响（如 `InitialWebUI:without_spellcheck/...`），"冗余"不等于"可删"。
5. 未评估 WebUI/扩展面（`src/` 内 108 个不参与构建的旧基线副本仍按 D41 结论忽略）。

## 10. 证据文件

- `.bugreview/flag_inventory.py`（清单解析：63 行 = 60 feature + 3 普通开关，程序化复核）
- `.bugreview/survival_check.py` + `.bugreview/survival_{151,155,156}.json`（逐项存活判定与上游默认值）
- `.bugreview/api_drift.py` + `.bugreview/api_drift.log`（注入锚点 / base API / GN 参数三版对比）
- `.bugreview/fetch_m155_m156.log`（浅拉取记录，HEAD 保持 `fbb5d9fd`）
- `.bugreview/flags_table.md`（60 条明细表）
- `.bugreview/v8_{151,155,156}_{BUILD.gn,flag-definitions.h}.txt`（V8 侧核对原始材料）
- 上游文档：`chromestatus.com/release-notes`、`chromereleases.googleblog.com/2026/10/`、`developer.chrome.com/blog/chrome-two-week-start`、`chromeenterprise.google/resources/release-notes/`
