# 第7周期 bug-review 报告 —— 内存 / CPU 调度 / GPU 渲染（2026-10-12）

范围：以"稳定前提下最优效率"为目标，对**内存占用、内存性能、内存安全（含泄漏）**、
**CPU 调度效率与占用**、**核显与独显渲染路径**做全局审查。
审查对象按 D77 口径只取**真正参与构建的权威面**：`win_scripts/apply_*`、`inject_*`、
`mcloud_flags.txt`、构建树实际产物、量具脚本（`benchmark/`、`.bugreview/`）、
安装包装器 `installer/mcloud_setup.cs`、`pak_src/` C 工具。
被测二进制：安装版 r7（`8e59c458…`，与仓库/载荷三处一致）与 `out/mcloud` 开发树。

## 1. 结论摘要

| 维度 | 结论 | 证据强度 |
|---|---|---|
| 内存 | **未发现真实泄漏**：25 标签 × 4 轮开合，驻留 944.0 → 947.0 → 941.7 → 944.7 MB，轮间漂移 **+0.7 MB（0.2 MB/轮）** | 实测（旧版量具，其判据缺陷见 D179/D180，已修） |
| 内存口径 | 52 项 feature **全部编译得进来**（0 死声明，D142 那族已清零）；上游默认已启用的"pin"实为 **15 项**，真正新增启用的优化是 **35 项**（此前文档写 14/34/35 三个互相矛盾的数字） | 新增 `guard_audit.py` 逐项判定，含 3 条正例 |
| CPU | 50 标签驻留期 **K2-CPU 中位数 0.03% 整机 / 0.01 折合核** ⇒ D170 的 ABOVE_NORMAL + 解除 EcoQoS **没有产生可测的空转成本** | 实测（`bench_memory.ps1` K2-CPU） |
| GPU | 渲染实际走 **ANGLE D3D11 + 独显**（`GL_RENDERER = ANGLE (NVIDIA, … (0x00002860) Direct3D11 …)`，设备号 0x2860 = RTX 4070 Laptop；名称按 D143 不可信）；未回退 SwiftShader | 实测（修复后的 `gpu_probe.py` 读 chrome://gpu） |
| 量具 | **发现并修掉 5 个会造成假绿的判据缺陷**（D177/D179/D180/D181/D183/D184），全部带可失败的正例 | 每条都有 Red→Green 记录 |
| 发布链 | 本周期改注释后再次断裂（**第 4 次**），新增 `release_chain_check.py` 把它变成机器判定 | 实测 RED（见 §6） |

新缺陷编号 **D177–D184**，索引见 `docs/tasks/bug-review-pak-src-defects.md`。

## 2. 新增的两个永久工具（本周期最耐用的产出）

### 2.1 `.bugreview/guard_audit.py` —— 平台守卫与默认值可达性审计

`survival_check.py` 只回答"这个名字在树里声明了吗"，它既不看**预处理守卫**
（D142 那两条"`#if BUILDFLAG(IS_POSIX)` / Android-only buildflag"的死声明就是这么漏的），
也只看声明**同一行**的默认值。本脚本按我们的构建身份（Windows / x64 / official）逐项判定：

- 读取声明所在**整个文件**，按括号配平截出声明体（`-A2`/`-A8` 的上下文窗口都不可靠，见 §2.3）；
- 合并反斜杠续行后重建**外层 #if 条件链**；
- 区分两类 `#if`：包住整条声明 = **排除**（DEAD）；只包默认值的 `#if/#else` = **选分支**
  （按平台取实际那一支，不构成排除）；
- 非平台 buildflag：先读 `out/mcloud/gen/**/buildflags*.h` 里
  `PA_BUILDFLAG_INTERNAL_<X>() (0|1)` 的**本构建实际取值**（409 个宏），
  读不到再退回 `.gni` 表达式求值（自带一个只认 `&& || ! == 括号` 的安全求值器，
  **不用 eval**）；两者都判不了 ⇒ `UNRESOLVED_FLAG` 硬失败，绝不静默算通过。

四种正例（Red）实测：

| 条目 | 判定 | 依据 |
|---|---|---|
| `BaseLockTrySpin` | **DEAD** | 守卫排除本构建：`BUILDFLAG(IS_POSIX)` |
| `PartitionAllocUsePriorityInheritanceLocks` | **DEAD** | `ENABLE_PARTITION_LOCK_PRIORITY_INHERITANCE = False` @已生成 buildflags.h（`is_android && (x64‖arm64)`） |
| `DirectComposition` | **MISS** | 树里找不到定义式（D48 同族） |
| `AsyncDns` | ACTIVE + 有效默认 ENABLED | 默认值写在 `#if IS_CHROMEOS‖IS_MAC‖IS_ANDROID‖IS_WIN‖IS_LINUX` 里，走 #if 支 |

真实清单：**M155 与 M151 两棵树各 52/52 ACTIVE**（`--json` 证据在 `.cycle7/guard_155.json` /
`guard_151.json`）。

### 2.2 `.bugreview/feature_decl.py` —— 平台有效默认值的唯一实现

`PLATFORM_FACTS` / `join_continuations` / `eval_platform_cond` / `effective_default` /
`platform_excludes_us` 集中在这里，`guard_audit.py` 调用它。
**为什么不用 eval**：条件文本来自源码树，把字符串喂给 `eval` 就是执行面
（Qoder 安全提示也点了这一条），所以写成只认 `True/False/!/&&/||/()` 的递归下降解析器。

### 2.3 我试过并且**撤掉**的做法（写给下一个接手的人）

第一反应是给 `survival_check.py` 把 `git grep -A2` 放大成 `-A8` 去读跨行默认值。实测**更糟**：
40 条默认值发生变化，绝大多数是错的——`git grep` 的上下文会把**邻居声明**的行卷进同一个块，
于是 `kDefaultInterestAreaSizeInP…` 这类**参数默认值**被当成 feature 默认值，
`SkiaGraphite` 之外还有 `TransientKeepAlivePolicy`、`BoostClosingTabs` 等被串成 ENABLED。
⇒ 放大上下文窗口这条路不可行；要读声明体就只能读整个文件并按括号配平截取。
`survival_check.py` 已回退到 `-A2`（只报"声明行可读到的默认值"，读不到就留空 + `default_note`），
**有效默认值一律以 `guard_audit.py` 为准**。

## 3. 内存维度

### 3.1 实测：没有泄漏证据

`leak_probe.py`（安装版 r7，rounds=4，tabs=25）：

```
基线工作集 = 463.9 MB（本实例 9 个进程）
第 1/4 轮：开 25 关 25  峰值 1610.1 MB（34 进程）→ 驻留 944.0 MB（相对基线 +480.1）
第 2/4 轮：…            峰值 2074.9 MB（44 进程）→ 驻留 947.0 MB
第 3/4 轮：…            峰值 2055.8 MB（44 进程）→ 驻留 941.7 MB
第 4/4 轮：…            峰值 2077.7 MB（44 进程）→ 驻留 944.7 MB
轮间漂移合计 +0.7 MB（0.2 MB/轮） → PASS
```

- 判据是**轮间驻留不单调增长**，不是"关掉后必须回到基线"：+480 MB 的谷值抬升是
  Chromium 关闭标签后保留空闲渲染进程复用 + 缓存的正常行为（`r4_memory_stability_check.py`
  实测 11→4 进程约需 11 秒）。这条口径本身是对的，本周期没有动它。
- **但旧量具能在实例死掉时输出 PASS**（D179），所以这条结论的可信度要靠 §3.2 的修复支撑。

### 3.2 D179 / D180：泄漏探针的两个假绿形态（已修，Red 实测）

| 缺陷 | 位置 | 问题 | 修法与验证 |
|---|---|---|---|
| D179 | `benchmark/tools/leak_probe.py:61-77` | `workset_mb()` 取不到数据时 `return 0.0, 0`。基线处检查了 `nb == 0`，**逐轮采样没检查** ⇒ `residuals` 里混进 0.0，`drift = residuals[-1] - residuals[0]` 变负 ⇒ 实例死掉时探针宣布"无单调增长 = PASS" | 改为抛 `InstrumentError`，main 捕获后 **rc=2**（与"判据不成立"的 rc=1 区分）。Red→Green：拿不存在的 profile 指纹调用 → 实测抛出并给出原因 |
| D180 | 同文件 184-199 | `/json/new` 全部失败时 `opened=[]`，峰值≈基线、驻留≈基线 ⇒ **空转也 PASS**（缺席型判据作用在空数据上） | 每轮断言 `len(opened) == tabs`，且关闭后 page 数必须回落到基线以内，否则 rc=2；日志新增"剩余 page" |

### 3.3 D181：`r4_memory_stability_check.py` 的内存量具同样能"坏了也算绿"

`private_mb()` 对 `OpenProcess` 失败的进程 `continue`，`GetProcessMemoryInfo` 失败静默计 0，
返回**单个 int**。判据 `last.trough_private_mb <= first + 120` 在两边都是 0 时**必然成立**
⇒ 量具坏了伪装成"没有累积泄漏"（正是第5周期 K2 侧 D138 修掉的形态，Python 侧漏了）。
现返回 `(MB, 实际读到数据的进程数)`，汇总处新增 `instrument_valid` 硬判据
（任一次采样 `procs==0` 或 `private_measured==0` 即 FAIL）。

⚠ 我第一版顺手把访问掩码从 `0x1010` 改成 `0x0410` 并写下"GetProcessMemoryInfo 要求 0x0410"——
**实测两种掩码都取到 `PrivateUsage`**，那句话没有依据，已撤销改动并在注释里记录撤销理由。
（纪律：改判据要带证据，不许"看起来更正确"。）

### 3.4 内存向 flags 的实际状态（净收益口径修正）

`-enable-features` 里内存相关的 9 项：`InfiniteTabsFreezing`、
`InfiniteTabsFreezingOnMemoryPressure`、`PartitionAllocEventuallyZeroFreedMemory`、
`PartitionAllocMemoryReclaimer`(pin)、`DiscardOnCommitLimit`、`SustainedPMUrgentDiscarding`、
`PartitionAllocSortActiveSlotSpans`、`LowerPAMemoryLimitForNonMainRenderers`、
`ReclaimOldPrepaintTiles`、`PruneOldTransferCacheEntries`(pin)。
按 `guard_audit` 逐项：**全部 ACTIVE（本构建编译得进来）**，其中只有
`PartitionAllocMemoryReclaimer` 与 `PruneOldTransferCacheEntries` 是 pin，其余 8 项是真新增。

需要点名的两条取舍（不是缺陷，是**代价**，写在报告里以免下一个人误读）：
- `PartitionAllocEventuallyZeroFreedMemory`（内存安全：释放的内存最终清零）在本构建
  `USE_PARTITION_ALLOC_AS_MALLOC = 1` 下确实编译进来，它买的是 UAF 类问题的可利用性下降，
  代价是清零开销 —— 属于"内存安全优先"的有意选择，与 ADR-002 的性能取向并存时应在基准里盯住。
- `LowerPAMemoryLimitForNonMainRenderers` 压低非主渲染器的 PA 上限，重页面场景更容易触发
  分配失败→丢弃；它和 `DiscardOnCommitLimit`/`SustainedPMUrgentDiscarding` 同向，
  组合的净效果偏"省内存优先"，与"极致流畅"存在张力，目前实测（§3.1）未见副作用。

## 4. CPU 调度维度

- **K2 驻留期 CPU**：50 标签静置 90 s，5 次采样 **0.0% / 0.03% / 0.03% / 0.01% / 0.04% 整机**，
  折合 **0.01 核**（本机 24 逻辑处理器）。⇒ D170 打开 `UserBlockingAboveNormalPriority`
  （连带 `process_win.cc:283-289` 解除 EcoQoS）**没有带来可测的空转 CPU**，
  "提权换流畅"的代价目前只在**争用场景**下才会显形（Windows 调度层面 ABOVE_NORMAL
  会压过普通前台应用），这条应作为已知取舍记录，而不是当作免费收益。
- 单位自洽断言与"取不到即 throw"仍在（D145/D166③ 的成果本周期未回退）。
- 遗留：`UnimportantFramesPriority`（降优先级）开着而 `ThrottleUnimportantFrameRate`（限帧率）
  关着 —— 第5周期已定案为有意为之，本周期复核其在 Windows 上的默认值确为 DISABLED，
  定案不变。

## 5. GPU 渲染维度

### 5.1 D184：`gpu_probe.py` 报的 ANGLE 后端一直是假的（已修）

旧判据：`"d3d11" in GPU进程命令行` / `"d3d12" in GPU进程命令行` → 两者**同时为 True**。
实测原因：GPU 进程命令行里根本没有 `--use-angle`，命中的是**我们自己的 feature 名**：

```
…MediaFoundationBatchRead,MediaFoundationD3D11VideoCaptureZeroCopy,…   ← "d3d11"
--disable-features=D3D12VideoDecoder,SkiaGraphite                      ← "d3d12"
```

同族问题在文件末尾还有一句"两版均走同一 ANGLE 后端 → 一致"，而它比较的其实是
两个 `gpu-process 存在` 布尔值 —— **结论超出测量**。

修法：经 CDP 打开 `chrome://gpu`，等 `GL_RENDERER` 真出现（正文开头只有内联 CSS，
`wait_for_text(min_len=400)` 会被它骗过），解析后端与适配器；读不到就 rc=2 判量具失效。
过程中还踩到标签格式：chrome://gpu 写的是 `GL_RENDERER<空格>:值`（冒号不是等号），
首版正则用 `=` ⇒ 永远取不到（这条已写进代码注释）。

### 5.2 实测结论（修复后的探针，安装版 r7）

```
ANGLE 后端（chrome://gpu）= D3D11
GL_RENDERER = ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti (0x00002860) Direct3D11 vs_5_0 ps_5_0,
                     D3D11-32.0.16.1062)
渲染适配器 = NVIDIA / 设备号 0x00002860      ← = RTX 4070 Laptop（名称按 D143 不可信）
gpu-process 存在 = True；本实例进程数 = 8；未回退 SwiftShader
```

⇒ **本机的合成与光栅化在独显上跑**，核显（Intel UHD，DEV_A788）不参与渲染。

### 5.3 D178 / D182：两条 `--disable-features` 与"4 项冻结缓解"的事实依据被推翻

`guard_audit` + `chrome://gpu` 给出三条硬事实：

1. **`SkiaGraphite` 在 Windows 上上游默认就是 DISABLED**。声明是
   `#if BUILDFLAG(IS_APPLE) FEATURE_ENABLED_BY_DEFAULT #else FEATURE_DISABLED_BY_DEFAULT`，
   151 与 155 结构相同。第6周期"实测三版默认启用、故必须显式禁用"的说法来自
   `survival_check` 取了 Apple 那一支（D177）。⇒ `--disable-features=SkiaGraphite`
   当前**净操作为零**，它的价值只剩"防上游翻默认值 / 防 Finch 远程下发启用"。
2. **`D3D12VideoDecoder` 上游基线也是 DISABLED**（`media_switches.cc:1704`），
   所以"绿屏靠这一行挡住"的叙述不成立；同理它是 pin，不是手段。
   而本周期实测渲染在独显上 ⇒ Intel 核显 D3D12 绿屏这条路径在本机根本没被走到。
   **定案不变**（只有核显的机器 / Windows 电源策略切到核显时仍会撞上），但表述已更正。
3. 冻结缓解"4 项禁用清单"经逐项核对：**`ReduceHardwareVideoDecoderBuffers` 的声明整体在
   `#if BUILDFLAG(IS_CHROMEOS) || BUILDFLAG(IS_LINUX)` 内，Windows 构建里没有这个 feature**
   （D142 同族死声明，只因它写在注释/文档里而不是清单里，此前从未被门禁扫到）；
   另三项在 Windows 上默认即 DISABLED。
   ⇒ **这四项没有一项是"我们关掉的"**；保持不启用是对的，但把"拖拽不再冻结"归因给它没有证据
   （当时是整组观察、未二分归因）。任务 **#27 的人工复现因此从"可选"升为必须**。

### 5.4 后续可做（需要基准/编译，未在本周期动手）

- `--enable-gpu-rasterization` 与 ANGLE D3D11 + Ganesh（Graphite 关闭）的组合是当前实测状态；
  想用 Graphite 必须在**核显与独显两种路由下**各自做拖拽复现（#27），否则定案不动。
- 独显/核显的**确定性选择**目前仓库不做（依赖 Windows 图形设置与电源策略）。若要产品化，
  必须同时给出：默认取向、被 Windows 覆盖时的可观测证据（`gpu_probe` 已能输出设备号）、
  以及核显路径的绿屏回归验证（`.bugreview/gpu_degradation_probe.py` 只测降级，不测路由）。

## 6. 发布链：第 4 次断裂，已变成机器判定

本周期只改了 `mcloud_flags.txt` 的**注释**（有效开关集合实测与 HEAD 完全一致：55 行 / 52 feature / 3 普通），
但字节指纹变了 ⇒ 仓库 `a071260c8c2c374f` vs 打包暂存载荷与已安装实例 `b737605e6d9806d3`。
这条链在 D102、D175、第6周期 §8.2 已经断过三次，每次靠人记得。新增
`.bugreview/release_chain_check.py`：三处指纹各自比对，不一致即 **rc=1**，
并区分"只差注释"与"开关集合也不同"两种处置，末尾直接给出"重打包 → 干净安装复验 → 复跑"的路径，
同时明确**不要手工 copy**（D175 的形态）。当前实测输出即上面那组（RED，符合预期）。

⚠ 我没有重打包，也没有手工同步载荷 —— 按纪律，重打包 + 复验属于发布动作，需要授权。

## 7. 门禁与量具回归（本周期结束时的状态）

| 判据 | 结果 |
|---|---|
| `python win_scripts/verify_sources.py` | **PASS**（`.ps1` 44 → **45**，新增 `benchmark/tools/mcloud_flags_lookup.ps1`） |
| `python .bugreview/flag_stability.py` | 待复跑（清单内容变了：新增 3 条 pin 注释 + 更正块；A 断言基线是 HEAD，提交后应绿） |
| `python .bugreview/flags_lint.py --stab … --guard …` | **PASS，pin=15**；不带 `--guard` 时 **rc=1**（D177 的牙齿，设计如此） |
| `python .bugreview/guard_audit.py`（M155 / M151） | **52/52 ACTIVE**，rc=0 |
| `python .bugreview/release_chain_check.py` | **rc=1（预期）**，见 §6 |
| `ruff --select F,E9,B,SIM`（改动的 5 个文件） | 全绿 |
| `benchmark/tools/gpu_probe.py --chrome <安装版>` | rc=0，输出真实后端/适配器 |
| `benchmark/tools/leak_probe.py`（修后代码） | Red 实测：坏指纹抛 `InstrumentError`；Green 待下一次跑完整轮次 |
| `benchmark/tools/r4_memory_stability_check.py` | 新 `instrument_valid` 判据已接入，未跑完整轮次 |

## 8. 残留风险与责任人

| # | 事项 | 严重度 | 需要谁 |
|---|---|---|---|
| 1 | 拖拽冻结的归因未成立（§5.3），"4 项禁用"不是手段 | 高（可能压着真实性能取向） | 人工复现（任务 #27），核显与独显各一次 |
| 2 | 发布链需重打包 + 干净安装复验（当前 RED 是本周期注释改动导致） | 高（发布阻断项） | 授权后执行 |
| 3 | `guard_audit` 只覆盖"声明可达性"，不覆盖 feature 的 **params 是否被读**（D51 族）与"两个 feature 相互抵消" | 中 | 下一个接手者：可加一条 `flag_runtime_state` 与清单的交叉断言 |
| 4 | `ABOVE_NORMAL` 的实际代价只在 CPU 争用下显形，本机静置测不出 | 中 | 需要"浏览器 + 重负载第三方进程"对照基准 |
| 5 | 独显/核显路由由 Windows 决定，仓库不控制；产品取向未写进文档 | 中 | 需要产品决策（续航 vs 流畅），再决定要不要下发 GPU 偏好 |
| 6 | `mcloud_flags.txt` 有效集合未变但字节变了 ⇒ 已安装实例与仓库不同源 | 低（行为等价） | 随下一次发布闭合 |
| 7 | `feature_decl` 的平台事实表写死 win/x64（ADR-003 允许），若将来出 ARM/其它平台需扩展 | 低 | 平台扩展时 |
| 8 | 我改的 `private_mb` 未跑完整 r4 轮次验证（只做了单元级 Red/Green） | 低 | 下一次跑 r4 时确认 |

## 9. 深度复查轮次（本周期做了 2 轮实测量 + 1 轮代码自检，余 2 轮待运行时条件）

按前几轮周期的规矩，收尾前要独立重查若干遍。这里是实际做到的与做不到的，不写成"已完成五轮"。

| 轮 | 对象 | 做了什么 | 结论 |
|---|---|---|---|
| 1 | flags 语义层（52 项） | `guard_audit` 全量 + M151 交叉；pin/净新增重算；两条 disable 行翻案 | D177/D178/D182 成立；0 死声明 |
| 2 | 量具自身 | leak_probe / r4 / gpu_probe / bench_* 身份块逐个读代码 + 正例复现（D184 的命中位置用真实命令行取证） | D179/D180/D181/D183/D184 全部修复并带可失败证据 |
| 3 | 我自己这轮新写的代码（自检轮） | 逐条找"我的量具在什么输入下会静默放行" | 抓到并当场修掉 4 处：① `git grep -F` 前缀匹配串到 `kBackForwardCacheSize` ⇒ 改为标识符全等；② 反斜杠续行未合并 ⇒ `IS_WIN` 被截断，`AsyncDns` 误判 DEAD；③ 内层 `#if` 与外层守卫混为一谈 ⇒ `SkiaGraphite` 误判 DEAD；④ `#ifdef/#ifndef` 形态的守卫**不判定**⇒ 会静默 ACTIVE，现改为在结论里显式 WARN（当前 52 项无此形态，升级后若出现不会悄悄放过）。另撤掉一处无依据改动（D181 的访问掩码） |
| 4 | 句柄与连接泄漏（代码面） | 复查 `mcloud_setup.cs` 全部 `Process.Start`/`RegistryKey`/`FileStream`、`cdp.py` 的 WebSocket 生命周期、`gpu_probe`/`leak_probe` 的子进程与临时目录收尾 | **D185**：安装器两处 Process 未 Dispose（已修，Roslyn 编译验证）；我自己新写的 `gpu_identity()` 漏关 WebSocket（已修，连跑两次结果一致）。顺带确认 `pak_src/*.c` 的分配/释放配对与边界检查无可疑路径（`calloc` 求和带 4 GiB 上限、写 payload 前有 `bufferEnd` 检查） |
| 5 | 长时间驻留 / CPU 争用 | **未做**：需要数十分钟到数小时的驻留浸泡，以及"浏览器 + 重负载第三方进程"的对照条件（本机跑着会干扰，且用户其它软件不应被我拿来压测） | 留给下一轮；判据已就绪（K2-CPU / r4 instrument_valid） |
| 6 | 核显路由下的渲染与冻结复现 | **未做**：需要把路由切到 Intel UHD（Optimus 电源策略或禁用独显）或换只有核显的机器；且窗口拖拽是人工动作 | 任务 #27，已由"可选"升为"必须"（因为 D182 推翻了原来的归因） |

⇒ 第 1–4 轮的结论可以直接采信；第 5–6 轮（驻留浸泡/CPU 争用、核显路由复现）是本周期**没有**覆盖的面，报告里不把它们算作已通过。第 5 轮已立项为任务 #50，第 6 轮仍是任务 #27。

## 10. 下一次发布前必须做的事（在第6周期 §9 基础上增补）

1. `python .bugreview/release_chain_check.py` —— 现在是红的（本周期只改注释），必须走完整重打包闭合
2. `python .bugreview/guard_audit.py --json .cycle7/guard_<ver>.json`（升级内核后必跑，两棵树各一次）
3. `python .bugreview/flag_stability.py` → `flags_lint.py --stab … --guard …`（不带 `--guard` 会因
   `AsyncDns` 默认值未知而红，这是设计行为，不是噪声）
4. `python win_scripts/verify_sources.py`（`.ps1` 现为 45 个）
5. `python benchmark/tools/gpu_probe.py --chrome <安装版>` —— 记录**实测**后端与适配器设备号
6. 干净安装复验（AGENTS.md 非交互口径）+ `flag_runtime_state.py` 回显 `enable 50 / disable 2`
7. `python benchmark/tools/leak_probe.py --chrome <安装版>` —— 修后版本要能给出非空 residuals 与
   "剩余 page" 回落证据
8. 任务 #27：核显路由下的拖拽人工复现（D182 之后这是唯一能确认冻结缓解是否真实的手段）

## 11. 收口轮（应用户要求：已知问题清零后再进五轮）

### 11.1 清零的三项遗留

| 项 | 缺陷号 | 做法 | 验证 |
|---|---|---|---|
| `CR_DIR` 默认指向 M151 回滚树，注入会静默改错树 | **D186** | 新增 `win_scripts/tree_check.py::require_tree()`：读 `<CR_DIR>/chrome/VERSION` 比对 `KERNEL_MAJOR`，不符 exit 114；接入 `deploy_mcloud.py`（开工第一件事）与 `apply_restart_cmdline.py`（单跑也拦） | Red：`CR_DIR=D:/wxmuma/chromium-src/src` → **rc=114**，错误信息点名"M151 回滚参考树"并给修法；Green：指向发布树 → 打印 `源码树：M155（155.0.8059.40）` 后照常执行 |
| setup 的 `FileVersion/ProductVersion` 是 `0.0.0.0` | **D187** | `build_setup_exe.py --version <4段>`：生成固定路径临时 `AssemblyInfo.cs` 同批编译（**不用** `csc /version:`，见 D164）；`package_m155.py` 传 `--version` 并**实测核对 VersionInfo**，不符即 FAIL | 实测 `FileVersion=155.0.8059.40 ProductVersion=155.0.8059.40`；非法形态 `155.0` → exit 111；**同名不同目录两次编译 SHA 相同**（`8a2e159d…`）⇒ 未破坏 D130 的复现性 |
| 安装器 `Process.Start` 未 Dispose + 我自己 `gpu_identity()` 漏关 WebSocket | **D185** | C# 两处 `using (…)`；`try/finally + contextlib.suppress` 关 tab | Roslyn `/deterministic+` 编译通过；`gpu_probe` 连跑两次读数一致（D3D11 / 0x00002860） |

顺带：清掉 `leak_probe.py` 一条 ruff SIM105，过程中暴露出我改了 `contextlib.suppress`
却**没加 import**（F821 NameError）——由 lint 抓到，已补。
这正说明"改完就跑 lint"不是仪式。

### 11.2 重打包与干净安装复验（闭合第 4 次发布链断裂）

- 部署：`CR_DIR=<155树> python win_scripts/deploy_mcloud.py` → 身份断言通过，清单同步 `out/mcloud`。
- 增量：**3 步**（`mini_installer_archive` → `packed_files.res` → `LINK mini_installer.exe`），
  `chrome` 未过期 ⇒ 本轮不涉及 crubit/Rust，**不会**触发 D173 的管道竞态；exit 0。
- 发布物：setup `a61655dd…`（127,585,792 B）、mini_installer `27c3236b…`（127,559,168 B）；
  `.sha256` 与发布说明由 `package_m155.py` 刷新，`sha256sum -c` 两个都 OK。
- 干净安装复验（`.cycle7/clean_install_reverify_r8.ps1`，**真实改动本机安装实例**）：
  卸载 **rc=19** → 安装 **rc=0**；清单落版本目录并与仓库**逐字节一致**（`a071260c8c2c374f`）；
  根目录无残留、无 `new_chrome.exe` 暂存件；安装版 `chrome.dll`(`e7679fb5…`)、
  根 `chrome.exe`(`86b588a4…`) **与本轮构建同哈希**；版本目录内没有 chrome.exe
  （再次印证 `chrome.release` 的 `%(ChromeDir)s` 登记）；
  对**安装后的二进制**回显 **`enable 50 / disable 2`**。
- `release_chain_check.py`：仓库 / 打包暂存载荷 / 已安装实例 **三处一致，RC=0**。
- ⚠ 卸载器又删掉任务栏固定项（无 API 可恢复），仍需人工重钉。
- 本轮未重编内核代码（改动都在脚本/文档/清单注释），`chrome.dll` 与 r7 同一份
  ⇒ D172 的"实测消失 + 正向对照"结论继续成立。

### 11.3 一个环境级陷阱（写给自己也写给下一个接手的人）

在本机 Git Bash 里用 `env -u CR_DIR python …` 这种前缀**会静默吞掉子进程的 stdout，
而 rc 仍是 0**（我用它测"未设 CR_DIR"时表现为"脚本没输出也没报错"，看起来像通过）。
测默认值路径请改用显式赋值（`CR_DIR=<旧树> python …`），或在脚本内 `os.environ.pop`。
这是"工具自己谎报成功"的又一族，与 D158（`Start-Process -PassThru` + 重定向取不到 ExitCode）同属
**采集通道本身不可信**这一类，判据设计时要按通道单独验证。

## 12. 五轮复审（应用户要求：已知问题清零后再做）

清完 §11 的遗留之后，重新按轮次过一遍，每轮换一个视角而不是把同一遍抄五次。

| 轮 | 视角 | 跑了什么 | 结果 |
|---|---|---|---|
| A | 安装链端到端 | `installer_arg_test.py`（首次因"安装包装完自动重启浏览器"留下 11 个实例而被判 PARTIAL——把实例收掉后重跑） | **12/12 PASS**：用户级与系统级两条参数分支都真实执行、D129 分支触发、四条污染自检全过 |
| B | 内存 | 修后 `leak_probe.py`（4×25 标签，带 D179/D180 硬失败）+ 修后 `r4_memory_stability_check.py`（3 轮×15 标签） | leak：**+4.7 MB / 1.6 MB 每轮 → PASS**，且每轮记录「剩余 page=1」证明标签确实关掉（不再是空转判据）；r4：`instrument_valid: true`，6 项判据全绿，残留 0 |
| C | CPU | `bench_startup.ps1 -Runs 5` | K1 中位数 **50 ms**（61/50/53/50/42），落在本机 ±12 ms 噪声带内；无异常尖峰 |
| D | GPU / 媒体 | `gpu_probe.py`（复跑两次）+ 新入库的 `gpu_degradation_probe.py` 三场 | 两次读数一致（**ANGLE D3D11 / 0x00002860**）；降级三场全绿：禁用 GPU → WARP(`0x0000008C`) 软件渲染 + 本地页面可读；`--use-angle=swiftshader` → SwiftShader/Vulkan；默认对照 → 合成/Canvas/Video Decode 全硬件加速 |
| E | 门禁自身与文档 | 路径引用扫描（423 处）、数字口径逐处对齐、`git log -S` 追门禁真伪 | 抓到 §12.1 三件事；AGENTS/发布说明/清单头的 15/35 口径统一；`.ps1` 计数 45 与文档一致 |

### 12.1 五轮里真正挖出来的东西（这才是复审的价值，不是"再看一遍没问题"）

1. **D132 从来没有被实现过**，而档案里躺着一条"D132 的 Red→Green 判据"。
   `git log -S"Mutex" -- installer/mcloud_setup.cs` **零命中** ⇒ 那份判据验证的是一个不存在的功能。
   已实现（命名互斥体 + `rc=2`），并补一份**带真 Red** 的判据：编译 HEAD 变体证明改动前
   第二个实例不被挡住。实测 Green `rc1=1 / rc2=2`、Red `rc2=1`、污染自检全过。
2. **我自己加的那把锁会锁死系统级安装**（D189）：提权自举时父进程持有互斥体并等待子进程，
   子进程抢不到锁 ⇒ 直接 `rc=2`。用户级判据覆盖不到这条分支，是"新护栏没顺着既有分支想一遍"。
   修法：子进程带 `--elevated-child` 跳过抢锁；实测父持锁期间带标记进程照常跑完、不带的被挡。
   ⚠ 本机 `EnableLUA=0` ⇒ 真实 UAC 分支从不执行，"提权路径整体通过"仍待有 UAC 的机器复验。
3. **我上一节的引用是虚指**（D188）：报告把 `.bugreview/gpu_degradation_probe.py` 当作现成门禁
   来对比"它不测什么"，而它当时只在被 gitignore 的 `.cycle6/cycle6-reverted/` 里。
   已按本仓纪律重写入库；重写过程中还纠正了它首版判据的一个假红：
   禁用 GPU 后 WebGL 拿到的是 `Microsoft Basic Render Driver`（WARP，也是软件渲染器），
   只认 SwiftShader 会把好结果判成失败 ⇒ 改成"与默认场景对照 + 按硬件设备号排除"。

### 12.2 本轮收尾后的门禁清单（都实测过）

`verify_sources`(45 `.ps1`) / `flag_stability` A–F / `flags_lint --stab --guard` /
`guard_audit`(M155、M151 各 52/52) / `release_chain_check` 三处一致 /
`installer_arg_test` 12/12 / `test_mutex_single_instance` PASS(含 Red) /
`gpu_probe` / `gpu_degradation_probe` / `leak_probe` / `r4` / `bench_startup`。

**仍没覆盖**：真实 UAC 提权路径、长时间浸泡与 CPU 争用对照（任务 #50）、
核显路由下的窗口拖拽复现（任务 #27）、`workset_mb` "实例中途死掉"的实机注入验证（只有单元级 Red）。
外层 setup 随包装器改动重打为 `1302268f…`；mini_installer 未变（`27c3236b…`）。
