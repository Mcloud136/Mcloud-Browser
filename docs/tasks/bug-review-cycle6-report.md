# Bug Review — 第 6 周期（2026-10-12）

全局视角审查：软件安装→更新→使用全链路，以及内存占用、内存安全、运行效率、CPU 占用、
多核调度、集显/独显渲染六个维度。

审查对象：MCloud Browser **M155（155.0.8059.40）**，构建树 `D:\wxmuma\chromium-src-155\src`，
安装实例 `C:\Program Files\Chromium\`（版本目录 `Application\155.0.8059.40`）。

硬件基线：Intel Core i9-14900HX（**8P + 16E = 24 逻辑核**，超线程关闭），
NVIDIA GeForce RTX 4070 Laptop（PCI `VEN_10DE&DEV_2860`，注册表 `DeviceDesc` 被改写成
"GTX 1050 Ti"）+ Intel Raptor Lake 核显（`DEV_A788`）。

> ⚠ **审查时的 GPU 环境不代表用户日常场景**：本次实测（WebGL / GPU 进程）落在
> **NVIDIA 独显**（`ANGLE (NVIDIA, …(0x00002860) Direct3D11 …)`），但用户**日常使用核显**
> 运行浏览器。凡涉及 GPU 能力、视频解码路径、光栅化策略的结论，都应按**核显**口径复核，
> 不要拿本报告里的独显实测值去推翻核显侧的既有定案（典型：`D3D12VideoDecoder` 禁用，见 §7.1）。

---

## 1. 结论摘要

| 编号 | 维度 | 缺陷 | 严重度 | 状态 |
|------|------|------|--------|------|
| D170 | CPU / 多核 | `BrowserProcessAboveNormalPriority` 单独启用无效，浏览器进程优先级提升**从未生效** | 高 | ✅ 已修复并实测 |
| D171 | 全维度（口径） | 51 项 feature 中 14 项上游默认已启用，净收益为零，其中 12 项未标注 | 中 | ✅ 已标注 |
| D59 | 全维度（静默失效） | 加载器不剥离行尾注释，一条行尾 `#` 注释会让**整份** flags 无声失效 | 高 | ✅ 已修复 + 加闸门 |
| D172 | 安装 / 更新 | `RegisterApplicationRestart` 命令行超 1024 字符失败，Windows 更新后浏览器不自动恢复 | 中 | ✅ 已修复（**待重新编译**） |
| — | 集显/独显 | `D3D12VideoDecoder` 全局禁用 | — | ✅ 定案：**保持禁用**（用户实际使用核显） |
| — | 渲染延迟 | `DXGIWaitableSwapChain` 未启用 | — | ✅ 定案：**保持现状** |
| — | 更新 | 无自动更新机制（Chromium 分支常态） | — | ✅ 定案：**保持现状** |

已核实**无需改动**的项（避免误改，见 §5）：PGO profdata 版本匹配、SIMD 基线、ThinLTO、
CFG / CET 影子栈 / BackupRefPtr / PartitionAlloc 硬化、安装布局与 flags 落地、字节一致性。

---

## 2. D170 — 浏览器进程优先级提升从未生效（CPU / 多核）

### 现象

`mcloud_flags.txt` 声明了 `--enable-features=BrowserProcessAboveNormalPriority`，
意图是让浏览器进程跑在 `ABOVE_NORMAL_PRIORITY_CLASS`。实测安装版浏览器进程：

```
BROWSER_PID=28744 AFFINITY=16777215 PRIORITY=Normal      # 修复前
```

### 根因：两项 feature 必须成对启用

`BrowserProcessAboveNormalPriority` 只是"允许给浏览器进程设 `kUserBlocking`"，
而 `kUserBlocking` **映射成哪个 Windows 优先级**由另一个 feature 决定：

```cpp
// components/performance_manager/graph/policies/process_priority_policy.cc:32-39
if (base::FeatureList::IsEnabled(features::kBrowserProcessAboveNormalPriority) &&
    process_node->GetProcessType() == content::PROCESS_TYPE_BROWSER) {
  CHECK_EQ(priority, base::Process::Priority::kUserBlocking);
  base::Process::Current().SetPriority(priority);
}

// base/process/process_win.cc:299-304
case Priority::kUserBlocking:
  os_priority = FeatureList::IsEnabled(features::kUserBlockingAboveNormalPriority)
                    ? ABOVE_NORMAL_PRIORITY_CLASS
                    : NORMAL_PRIORITY_CLASS;      // ← 缺这一项就落到这里
```

`kUserBlockingAboveNormalPriority`（`base/features.cc:205`，Windows 专属，默认禁用）**从未被启用**。
feature 自身的注释也写明了这一点：

> "// A feature to use ABOVE_NORMAL_PRIORITY_CLASS for Browser on Windows by setting
> base::Priority::kUserBlocking. **This should be used together with
> kUserBlockingAboveNormalPriority.**"

### 附带影响：Windows 11 EcoQoS 未被解除（多核维度）

同一段 `SetPriority()` 里（`process_win.cc:283-289`）：

```cpp
if (FeatureList::IsEnabled(kUseEcoQoSForBackgroundProcess)) {     // 默认 ENABLED
  win::SetProcessEcoQoSState(Handle(),
                             priority == Priority::kUserBlocking ? kUnset : kEnabled);
}
```

`kUseEcoQoSForBackgroundProcess` 默认启用，凡不是 `kUserBlocking` 的进程会被打上
**EcoQoS** → Windows 11 把其线程调度到**能效核（E-core）**并降频。本机 8P+16E，
浏览器进程一旦降级就跑在 E-core 上，UI 线程延迟明显变差。
所以 D170 同时是一条**混合架构多核调度**缺陷。

### 修复

在 `mcloud_flags.txt` 的 Threading 段新增（含完整理由注释）：

```
--enable-features=UserBlockingAboveNormalPriority
```

### 验证（对**已安装**二进制）

```
BROWSER_PID=30044 PriorityClass=AboveNormal     # 修复后
  PID=28296 TYPE=renderer   PRIO=AboveNormal
  PID=20820 TYPE=gpu-process PRIO=AboveNormal
```

运行时回显同步由 `enable 49 / disable 2` 变为 `enable 50 / disable 2`。

### 代价（有意取舍）

`ABOVE_NORMAL` 会在 CPU 争用时优先于其他应用，解除 EcoQoS 会抬升功耗与发热。
这与本项目"极致流畅"定位一致；若改为续航优先，需**同时**移除这两行
（只留其一等于无效配置，这正是本缺陷的成因）。

---

## 3. D171 — 净收益口径：14 项"启用"实为钉住

用 `.bugreview/stab_155.json`（M155 全量声明核对结果）交叉比对 51 项 feature：

- 全部 **51 项在 M155 真实声明存在**（D48 清理已到位，无"上游不存在"的死条目）
- 其中 **14 项上游默认即 `FEATURE_ENABLED_BY_DEFAULT`** → 净效果为零
- 真正生效的启用项：**34 项**（另有 2 项显式禁用）

此前只有 2 项（`PartitionAllocMemoryReclaimer`、`PruneOldTransferCacheEntries`）被注释标注，
其余 12 项未标注，读清单时会把 49 项启用**高估为 49 项优化**。

已在文件头新增"净收益口径"说明块，并给 14 项逐条加 `# pin:` 标记行。

> ⚠ 注意：加标记时踩到 D59——行尾注释会让整份 flags 失效，最终改为**独立注释行**。

---

## 4. D59 重复触发 — 行尾注释导致整份 flags 静默失效（**不是新缺陷**）

> ⚠ **本节为过程记录，不是新缺陷登记。**
> 档案 **D59**（`docs/tasks/bug-review-cycle3-report.md`）早已确立"flags 行尾 `# 注释` 会让
> 该条整条失效"，`flag_stability.py` 的 **F 断言**就是专为此项加的静态拦截
> （注释原文"（D59）"）。本周期我给 14 行加行尾注释又踩了一次，**既有闸门本来会拦住它**——
> 没能拦住的原因是：**我改完 flags 没跑 `flag_stability.py`**，靠运行期回显才发现。
> 教训不是"缺少 lint"，而是"改 flags 后必须先跑既有闸门"（已写入 §10 流程约定）。

### 现象

为 D171 给 14 行加了行尾 `# pin: ...` 注释后，运行时回显从 50 项掉到：

```
运行时 override：enable 1 项 / disable 2 项
    - BackForwardCache   # pin  params= BackForwardCache 上游默认已启用，本行为显式钉住
```

### 根因

加载器（`inject_flags_loader.py`，LOADER v8）逐行解析时**只跳过整行注释**（行首 `#`），
不剥离行尾注释：

```cpp
if (line.empty() || line[0] == '#') continue;      // 只判行首
...
value = std::string(line.substr(equals + 1));      // 行尾注释进了 value
```

于是 feature 名变成 `BackForwardCache   # pin`（含空格与中文），`FeatureList` 无法匹配，
**整串 `--enable-features` 被拒**。后果：全部性能优化无声失效，而构建、安装、门禁全绿。

与 D48（上游不存在的 feature）、D57（UTF-8 BOM 吃掉首行）同族：**失效不可见**。

### 处置

1. 14 处行尾注释改为**独立注释行**（已在 D171 中完成）
2. 新增 `.bugreview/flags_lint.py`：查行尾注释（致命）、feature 名合法性、重复声明，
   可选对照 stab 查存在性
3. 接入 `win_scripts/verify_sources.py`，做了负向测试：

```
[PASS] mcloud_flags.txt lint: no trailing comments, switch names well-formed
[FAIL] mcloud_flags.txt lint: [FATAL] 行尾注释 / 不可解析行（1）——…   ← 注入后按预期失败
```

### 公允定位：这是**闸门位置**的改进，不是缺陷发现

| | `flag_stability.py` F 断言 | `flags_lint.py` |
|---|---|---|
| 拦行尾注释 | ✅ 早已能拦 | ✅ 能拦 |
| 在 CI 里跑 | ❌ **不在 CI** | ✅ 已接 `verify_sources.py`（CI 跑） |

增量价值只有一条：**把同类的静态拦截放进 CI**。缺陷本身（D59）是旧账，不是本周期发现。
若已有 F 断言覆盖，正确做法应是"先跑它，再把它的覆盖范围接入 CI"，而不是另起一套
lint 并登记为新缺陷编号——本周期做反了，编号 D165 已撤销。

> 待办（需重新编译）：让加载器支持剥离行尾注释，从根上消除这类失效。
> 另：`flags_lint.py` 的 `--stab` 读的是 `survival_check.py` **生成**的 `stab_155.json`
> （非入库资产），缺失时应先跑 `flag_stability.py` 生成。

---

## 5. D172 — RegisterApplicationRestart 失败（Windows 更新后不自动恢复）

### 现象（安装版启动日志，稳定复现）

```
WARNING:chrome\browser\chrome_browser_main_win.cc:832] Command line too long for
RegisterApplicationRestart:  --disable-background-media-suspend --disable-features=…
--enable-features=SpareRendererForSitePerProcess,…,UnimportantFramesPriority …
```

### 根因

Windows `RegisterApplicationRestart` 命令行上限 1024 字符。仅 `--enable-features` 一项
就约 1.4 KB，必然超限 → 返回 `E_INVALIDARG`。上游只打 `LOG(WARNING)` 后继续，
**不影响启动**，所以完全静默：构建、安装、门禁全绿，只是浏览器从此**不再被 Windows
重启管理器恢复**（其他已注册应用会在 Windows 更新重启后自动恢复，本浏览器不会）。

`GetRestartCommandLine()` 只调了 `about_flags::RemoveFlagsSwitches()`，那只移除
chrome://flags 产生的开关；本项目的 flags 是**命令行直传**的，不在其集合内，原样保留。

### 修复

新增 `win_scripts/apply_restart_cmdline.py`（幂等注入，已接入 `deploy_mcloud.py`），
在 `GetRestartCommandLine()` 中移除三项：

```cpp
switches.erase("enable-features");
switches.erase("disable-features");
switches.erase("js-flags");
```

安全性：加载器每次启动都从 `mcloud_flags.txt` 重新注入，无需命令行接力。
去掉后重启命令行约 260 字符，远低于 1024。

已在 M155 树实跑，幂等验证通过（run1 注入 / run2、run3 "already present"），
上游 `switches.erase(switches::kFromInstaller);` 完整保留。

> ⚠ **需 `gn gen` + 重新编译才生效**（仅重新编译 `chrome_browser_main_win.cc` 一个 TU）。
>
> 修复过程中该脚本的第一版自身有缺陷：块结束锚点取到了下一个上游语句，复跑会误删
> `kFromInstaller` 那行；同时 `BLOCK.strip()` 吃掉首行缩进。两处均已修正并复测。

---

## 6. 已核实无需改动的项（避免误改）

| 项 | 结论 | 依据 |
|----|------|------|
| PGO profdata | ✅ 正确指向 M155 的 8059 剖面 | `out/mcloud/args.gn` 与 `chrome/build/pgo_profiles/` 核对；`build_win.py` 有存在性预检（D144） |
| 仓库模板 vs 构建树 args.gn | ✅ 仅注释差异，语义一致 | `diff win_args_mcloud.gn <树>/out/mcloud/args.gn` |
| SIMD 基线 | ✅ AVX2+FMA3 正确，AVX-512 关闭（14900HX 无） | `compiler_opt.gni` |
| `compiler_opt.gni` | ✅ **本仓自带定制，复制步骤必须保留** | 树内 `git status` 为 `??`（未跟踪）⇒ 上游根本没有此文件 |

> ⚠ **更正一处前版误判**：本表曾写"`compiler_opt.gni` 与上游字节一致 ⇒ 复制是 no-op"。这是**错的**。
> 判据取错了：两份哈希相同只能证明 `copy_essentials.py` **复制成功**，不能证明"上游有同名文件"。
> 树内 `git status --short build/config/compiler_opt.gni` 返回 `??`（未跟踪）⇒ 该文件**不在上游
> Chromium/Thorium 的版本控制里**，它就是从本仓库 `src/build/config/compiler_opt.gni` 复制过去的
> 定制件（AGENTS.md 明确写"修改前必须备份"的那个）。
> 误判的危害：若被采信，有人会去删 `copy_essentials.py` 里的复制步骤，或以为改仓库里的
> `compiler_opt.gni` 不起作用——两者都会静默丢掉 AVX2/SIMD 定制。
| CET 影子栈 | ✅ 默认启用 | `compiler.gni:230` `= target_cpu == "x64"` → `/CETCOMPAT` |
| BackupRefPtr (MiraclePtr) | ✅ 默认启用 | `build_overrides/partition_alloc.gni:106` 随 PA-E 开启 |
| CFG、`init_stack_vars_zero` | ✅ 均已开 | args.gn |
| flags 落地与布局 | ✅ 版本目录内，根目录无残留，与仓库字节一致（12662 B） | 安装实例核对 |
| 单实例运行态内存 | 19 进程 / 约 1.3 GB WS（含一个**额外**的残留实例，非单实例真实值） | 实测 |

---

## 7. 待决项定案（2026-10-12 用户决定：三项全部保持现状）

### 7.1 `D3D12VideoDecoder` — 保持禁用 ✅

**定案理由：用户实际使用核显（Intel）运行浏览器**，核显正是 D3D12 视频解码绿屏缺陷的
受影响设备，因此这条全局禁用不是"过度规避"而是**主路径上的正确定案**。
本报告 §6 的实测结论（WebGL 走 NVIDIA 独显）是审查时的临时环境，**不代表用户日常场景**——
后续复查 GPU 相关问题时应以核显为准，不要再按独显口径推翻这条结论。

### 7.2 `DXGIWaitableSwapChain` — 保持现状 ✅

`ui/gl/gl_switches.cc:457`，默认禁用，注释："Use waitable swap chain on Windows to
reduce display latency"。它默认关闭通常意味着有驱动兼容性前科，且核显场景下"降延迟"
的收益弱于其风险。维持不启用。

> 同文件的 `DirectCompositionUnlimitedOverlays` 同样**不启用**——上游注释明确写
> "If there are more videos than hardware overlay planes, there may be a performance hit"。

### 7.3 自动更新 — 保持现状 ✅

Chromium 分支不含 Omaha/更新器，用户手动下载新版本重装。维持现状。

### 7.4 `symbol_level = 0`（D147 遗留）

崩溃无法归因。提升 symbol level 会增大体积。未在本周期改动。

---

## 7.5 ⚠ 由此暴露的一个张力：D170 与"核显/续航"意图相反

D170 新增的 `UserBlockingAboveNormalPriority` 有两个效果：

1. 浏览器进程升到 `ABOVE_NORMAL_PRIORITY_CLASS`
2. **解除 Windows 11 EcoQoS**（`process_win.cc:283-289`），即不再被调度到 E-core、不再降频

第 2 点的代价是**功耗与发热上升**。而用户选择核显运行浏览器，通常正是为了省电/续航/
低温。也就是说 D170 是"性能优先"取舍，与核显场景的意图存在张力。

三个可选处置（**尚未执行，等你选**）：

| 选项 | 做法 | 效果 |
|------|------|------|
| A（当前状态） | 保留两行 | 最流畅；浏览器进程不被降频，功耗上升 |
| B（推荐试） | 保留 `BrowserProcessAboveNormalPriority`，移除 `UserBlockingAboveNormalPriority` | 浏览器进程仍标 kUserBlocking（**EcoQoS 仍被解除**），但不抢 ABOVE_NORMAL |
| C | 两行都移除 | 完全回到上游：允许 EcoQoS 生效，最省电，但浏览器进程可能被降到 E-core |

注：B 与 C 的区别在于——EcoQoS 的开关取决于优先级是否为 `kUserBlocking`，
只有 C 才会让 EcoQoS 重新生效。若目标是续航，应走 C。

### 核显场景下另一个可 A/B 项（未执行）

`--enable-gpu-rasterization`（当前启用）在较弱的核显上未必划算：GPU 光栅化会把合成/栅格
负载压到核显，而核显共享系统内存带宽。若在核显上感到滚动掉帧，可试**移除该行**改用
CPU 光栅化做对照。此项需按规范第 7 章跑基准后再定，本周期不动。

---

## 8. 本周期改动清单

| 文件 | 改动 |
|------|------|
| `mcloud_flags.txt` | +`UserBlockingAboveNormalPriority`；新增净收益口径说明块；14 项 pin 标注 |
| `win_scripts/apply_restart_cmdline.py` | **新增**，D172 幂等注入 |
| `win_scripts/deploy_mcloud.py` | 编排新增 `apply_restart_cmdline.py` |
| `win_scripts/verify_sources.py` | 新增 flags lint 闸门（把 D59 的静态拦截放进 CI） |
| `.bugreview/flags_lint.py` | **新增**，D59 静态闸门 |
| `chromium-src-155/src/chrome/browser/chrome_browser_main_win.cc` | D172 注入（**待编译**） |
| `docs/CHANGELOG.md` | 回显口径 49+2 → **50+2**；补"r6 干净安装复验对新 flags 失效"声明 |

> **已撤销的错误改动**：`.bugreview/stab_155.json` 的人工补录已删除。该文件是
> `survival_check.py` 的**生成产物**（`flag_stability.py` 每次运行重新生成），不是入库资产
> （`.gitignore` 只放行 `.bugreview/*.py`），改它既无效也不可复现。

## 8.1 ⚠ 本周期对**本机**的改动（必须记录）

审查过程中我改过本机的已安装实例，这里如实登记，否则接手方会以为机器状态可复现：

| 时间 | 动作 | 后果 |
|------|------|------|
| 05:09 | 把新 `mcloud_flags.txt` 手工拷进 `C:\Program Files\Chromium\Application\155.0.8059.40\` | 安装实例的 flags 变成**任何发布物都装不出来的**内容（同 D109 遮蔽形态） |
| — | 期间曾试图用 `.bak` 备份原版，但备份时机错误（备份的是新内容） | 原版一度丢失，只能从打包暂存目录找回 |
| 已修复 | 从打包暂存目录（载荷真身）拷回，恢复为 `d71d988ca2d2ab` | 安装实例回到**可从发布物复现**的状态 |

另：审查中为抓进程/GPU 数据多次启停浏览器实例，其中一次 `Stop-Process -Name chrome -Force`
会连带结束当时正在运行的其他 Chromium 实例。后续实测应先记录既有 PID 集合，
只结束本次启动的进程。

## 8.2 发布物当前落后于源码（第三次）

| 侧 | 哈希 | 说明 |
|----|------|------|
| 仓库 / 构建树 ×3 | `b737605e6d9806` | 含 D170 + D171 |
| **打包暂存目录（载荷真身）** | `d71d988ca2d2ab` | **旧**，落后 |
| 已安装实例 | `d71d988ca2d2ab` | 与载荷一致（已恢复） |

载荷路径：
`out/mcloud/gen/chrome/installer/mini_installer/mini_installer/temp_installer_archive/Chrome-bin/155.0.8059.40/mcloud_flags.txt`

> ⚠ **不要**直接把新 flags 拷进暂存目录而不重新压缩打包：那会让 `package_m155.py`
> 的"载荷与仓库一致"判据变绿，但真正的 `chrome.7z` / `mini_installer.exe` 仍是旧的——
> 这正是 D102"无效量具"的同族陷阱。必须走完整打包流程。

## 8.3 构建树中间产物已大量缺失（本次编译前实测）

执行增量编译前的预检发现，`out/mcloud` 并不是"改一个 .cc 就能增量"的状态：

| 检查项 | 实测 | 说明 |
|--------|------|------|
| `obj/` 总大小 | **8.0 GB** | 完整 Chromium 构建（含 ThinLTO）通常 30–60 GB |
| `obj/chrome/browser/chrome_browser_main_win.obj` | **不存在** | 本次要改的 TU 自身就没有中间产物 |
| `ninja -n chrome` 步数 | **14,044** | 远超"一个 TU + 链接"应有的量级 |
| `ninja -d explain` | `output …/libc++/*.obj doesn't exist` | 是**产物缺失**，不是命令行变化 |

判据区分很重要：教训④ 的"全树失效"是 `command line changed`（环境不一致，实测 51,361 步 +
`libc++ 'new.h' file not found`）；本次是 `doesn't exist`（产物不在磁盘上），
**不是环境不对**，因此不需要重新 `gn gen`，直接增量即可（但仍接近半量重编）。

环境（与 `build_m155.ps1` 一致，必须原样使用）：

```
DEPOT_TOOLS_WIN_TOOLCHAIN=0  DEPOT_TOOLS_UPDATE=0
vs2026_install=C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools
INCLUDE=<...>/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE
PATH=D:/wxmuma/depot_tools;$PATH
```

> 后续若有人看到"步数突然变多"，先跑 `ninja -n -d explain` 区分
> `command line changed`（环境错，赶紧停）与 `doesn't exist`（产物被清，可以编）。

### 8.3.1 首轮编译失败：Windows 命名管道耗尽（os error 231）

`autoninja`（自动高并行）跑到 `[1325/13986]` 时失败：

```
FAILED: gen/components/cbor/rust/cbor_rust.h …
thread 'rustc' panicked at …token_stream_printer.rs:541:29:
Failed to spawn clang-format at "../../buildtools/win-format/clang-format.exe":
  所有的管道范例都在使用中。(os error 231)
ERROR: `cc_bindings_from_rust.exe` exited with a non-zero exit code: 101
ninja: build stopped: subcommand failed.
```

`os error 231` = **ERROR_PIPE_BUSY**：并发过高，Windows 命名管道实例被耗尽。
发生在 Rust↔C++ 绑定生成（crubit）这类**派生大量子进程**的动作上，**与代码改动无关**。

#### 根因定位（不是并行度，也不是重定向方式）

逐一排除后的结论：

| 假设 | 验证 | 结论 |
|------|------|------|
| 并行度过高 | `-j 16`、甚至 `-j 1` 同样失败 | ❌ 否 |
| clang-format 缺失/损坏 | 手动 `clang-format.exe --version` → RC=0，连续 spawn 20 次全过 | ❌ 否 |
| `RAYON_NUM_THREADS` 内部并行 | 设为 1 仍失败 | ❌ 否 |
| 工具沙箱限制 | Bash 通道直跑同样失败 | ❌ 否 |
| 输出接管道导致 | 改用纯文件重定向（`> file 2>&1`）仍失败 | ❌ 否 |
| ninja 传参差异 | 从 `out/mcloud` 手工复现整条命令，同样失败 | ❌ 否 |

开 `RUST_BACKTRACE=full` 后拿到真正的调用点：

```
3: std::sys::backtrace::__rust_begin_short_backtrace::<
     std::sys::process::windows::child_pipe::spawn_pipe_relay::{closure#0}, ()>
```

即 Rust std 在 Windows 上的 **管道中继线程**（`spawn_pipe_relay`）创建**命名管道**时拿到
`ERROR_PIPE_BUSY`。这是 Rust std 的实现细节，不是 Chromium 或本仓库的问题，
也与本周期的改动无关（本次只改一个 `.cc`）。

另注：`gen/components/cbor/rust/cbor_rust.h` **已存在**（Oct 10 21:25 生成，223 KB），
只是因为 `obj/components/cbor/rust/libcbor.rlib` 被重编而需要重新生成
（`ninja -d explain`：recorded mtime older than most recent input）。

#### 进一步排除的项

| 假设 | 验证 | 结论 |
|------|------|------|
| 相对路径 / CWD 解析 | 改成绝对路径 `D:/wxmuma/.../clang-format.exe` 仍失败 | ❌ 否 |
| 命名管道资源真的耗尽 | PowerShell `NamedPipeServerStream` 创建测试 → **PIPE_CREATE_OK** | ❌ 否（资源充足） |
| 残留进程持有管道 | 查询 `cc_bindings/rustc/cargo/python/clang` → **无残留** | ❌ 否 |

即：**系统管道资源充足、无残留进程，但 Rust std 的这条路径就是拿不到 231 之外的结果。**
错误码具有误导性，实际不是"管道实例耗尽"。

#### 处理与当前状态

用 `ninja -k 0` 跳过失败项，编到 **[3215/12383]** 后 `cannot make progress due to previous errors`
——因为 `chrome.dll` 依赖链上的 cbor / signed_web_bundles 绑定，失败项阻塞了全部后续目标。

**当前状态：编译未完成，D172 尚未进入二进制。** 源码改动已就绪且已验证（见 §8 deploy 复核），
只差一次成功的编译。

复跑命令（环境必须原样）：

```
cd D:\wxmuma\chromium-src-155\src
set DEPOT_TOOLS_WIN_TOOLCHAIN=0 & set DEPOT_TOOLS_UPDATE=0
set vs2026_install=C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools
set INCLUDE=C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;%INCLUDE%
third_party\ninja\ninja.exe -C out/mcloud -j 16 chrome mini_installer
```

> 记住：Chromium 构建里出现 `os error 231` / `pipe busy`，**不要去改源码**；
> 先 `-k 0` 跑完其余部分，再单独重试失败项。若仍失败，通常要在**重启机器后**跑
> （本次在同一会话内重试 5+ 次均失败；注意重启会中断自动化会话，故需人工触发后续步骤）。

## 8.4 ⚠ 本周期未完成的部分（诚实登记）

| 步骤 | 状态 |
|------|------|
| deploy 编排 | ✅ 完成并复核 |
| 增量编译（D172 进入二进制） | ❌ **未完成**，被 crubit / Rust std 管道问题阻塞（§8.3.1） |
| 重跑 mini_installer 刷新载荷 | ⏸ 未做（依赖上一步） |
| 干净安装复验 | ⏸ 未做（依赖上一步） |

⇒ 发布物载荷**仍是 `d71d988ca2d2ab`（旧）**，仓库侧 `b737605e6d9806`。
D170 的优先级修复**在本机当前不生效**（安装实例已回滚到载荷状态，见 §8.1）。

## 9. 下次发布前必须做的事

1. `CR_DIR=D:\wxmuma\chromium-src-155\src python win_scripts/deploy_mcloud.py`
2. `gn gen out/mcloud --check` + `autoninja chrome`（D172 需编译生效）
3. **重跑 mini_installer 打包**，刷新暂存目录载荷，并核对载荷 == 仓库 `mcloud_flags.txt`
4. 干净安装复验：版本目录内 flags 落地 + 字节一致 + 运行时回显 `enable 50 / disable 2`
5. 确认启动日志中 **不再出现** "Command line too long for RegisterApplicationRestart"
6. `python .bugreview/flag_stability.py`（A–F 全绿）
7. `python .bugreview/flags_lint.py --stab .bugreview/stab_155.json`
8. `python win_scripts/verify_sources.py`

## 10. 流程约定（本周期教训，写给下一个接手的人）

1. **改 `mcloud_flags.txt` 后必须先跑 `flag_stability.py`，再跑运行期回显。**
   本周期顺序反了：靠 `flag_runtime_state.py` 才发现行尾注释把整份 flags 打回 1 项，
   而 F 断言（D59）本来第一秒就能拦住。
2. **A 断言的基线是 `git show HEAD:mcloud_flags.txt`**，所以"新增开启项"必然先红一次：
   正确顺序是 C 断言证明三版存活（本项 52/52）→ 提交 → 基线跟上 → 复跑确认 A–F 全绿。
   只改工作树不提交，闸门就一直红着给下一个人看。
3. **不要在 `.bugreview/` 放 `.ps1`**（AGENTS.md 教训⑤）：会被 `verify_sources.py`
   计入 `.ps1` 总数（44→45），干净检出复现不了。本周期又犯了一次，已删除。
4. **不要手工改已安装实例的 flags**，也不要只改暂存目录而不重压包。
5. `.bugreview/stab_*.json` 是生成产物，不要手工编辑。
   ⚠ 但它同时也**未入库**（`git ls-files` 无匹配、`.gitignore` 也没有条目）。
   本节第 7 步在**干净检出**上必然找不到文件——收口轮复核时这就是 D176 的触发路径
   （缺文件被当成"全部声明存在"并返回 0）。现在 `flags_lint.py` 已改为缺文件即 rc=1，
   所以接手方必须**先跑本节第 6 步**（`flag_stability.py` 会写出 stab），再跑第 7 步，
   别把这次的红当噪声。

## 11. 收口轮执行记录（第5周期接手方，2026-10-12 14:30–16:40）

我按 §9 的清单把你留下的四件事（§8.4）做完，并对你的三条改动（D170/D171/D172）与新代码
做了复核。**你的三条结论我全部独立核过源码，成立**；下面只写差异与补强。

### 11.1 §8.4 四项状态：全部完成

| 步骤 | 你的状态 | 收口轮实测 |
|---|---|---|
| 增量编译（D172 进二进制） | ❌ 被 crubit 管道问题阻塞 | ✅ **6830/6830，exit 0**（`.bugreview/build_r8_full.log`，15:52 完成；`out/mcloud/chrome.dll` 15:50，303,442,944 B） |
| 重跑 mini_installer 刷新载荷 | ⏸ | ✅ 暂存目录载荷 → `b737605e6d9806d3`（与仓库同哈希）；`mcloud_155.0.8059.40_win64_mini_installer.exe` 15:52 |
| 重新打外层 setup | ⏸ | ✅ `mcloud_155.0.8059.40_win64_setup.exe` = **127,589,888 B / SHA256 `8e59c4580e95bef278bef517da210c6b104598ad5ba2152bfda70bfef3d5d746`**（16:04） |
| 干净安装复验 | ⏸ | ✅ 16:09 真实 `--quiet --system-level` 装 → 版本目录 flags 落地且与仓库字节一致 → 对**安装后的二进制**回显 **`enable 50 / disable 2`**（`.cycle6/r11_runtime.log`）→ 根进程 `PriorityClass=AboveNormal`（D170 端到端）→ 卸载 rc=19 |

⇒ **§8.2 的"发布物第三次落后于源码"与 D175 一并闭合**：现在
仓库 / 打包暂存载荷 / 已安装版本目录三处 `mcloud_flags.txt` 全是 `b737605e6d9806d3`。

门禁复跑：`verify_sources.py` **PASS**（44 个 `.ps1`，与 §10.3 口径一致）、
`flag_stability.py` A–F 全绿、`flags_lint.py`（不带 `--stab` 的 CI 形态）PASS、
`test_build_win_preflight.py` PASS、`installer_arg_test.py` PASS。

### 11.2 D172 的 Green 现在有**真正的正向对照**（你的 §9 第 5 步）

你写的是"发布前应在启动日志中确认该 WARNING 已消失"——但缺席型判据在没有旁证时不成立
（日志里"没有"既可能是修好了，也可能是那段代码没跑到、或日志根本没写进去）。收口轮做了三条：

1. **算术**：把你 §8.1 之前抓到的那条 WARNING（`.bugreview/gpu_startup.log:87`，05:04:17，
   旧二进制）里的命令行原样取出来，**实测 1911 字符**；按 `GetRestartCommandLine()` 现在的
   剔除规则（`enable-features`/`disable-features`/`js-flags`）重算 → **≈284 字符** < 1024。
2. **同法复测（Green）**：对**安装后的二进制**用**与 Red 相同的采集方法**
   （`--enable-logging --log-file=… --v=1` + 一次性 `--user-data-dir` 叶子）启动：
   日志 **135,082 B**（证明日志通道确实开着），其中 `RegisterApplicationRestart` **0 次**。
   证据：`.cycle6/r14_d172_mcd172v3.log`。
3. **正向对照（Red，可失败性证明）**：同一份二进制、同一次采集，只额外加一个
   **1300 字符的未知开关** `--mcloud-probe-padding=aaaa…`，WARNING **回来了（hits=1）**，
   日志 86,166 B。⇒ 这条判据**能红**，"0 次"是真测出来的而不是量具坏了；
   同时也确认修剪只去掉我们注入的三项、没有把注册逻辑本身关掉。
   证据：`.cycle6/r15_d172_positive_control.log`（脚本 `.cycle6/r15_d172_positive_control.ps1`）。

实例一律按 profile 指纹收尾：三次取证实测 `instance procs=8~9 → remaining=0`、
临时目录 `tempdir-removed=True`，**没有**触碰你 §8.1 提到的其它在跑的浏览器。

⚠ 顺带纠正我自己一处：`--v=0` 时日志是 **0 B**——"0 B + 0 hits"看着像通过，其实是
空数据上的缺席判据（D176 同族、也是我批评你的那一点）。判据必须是"**非空日志里 0 次**"，
所以我改用了 `--v=1` 并补了第 3 条正向对照。

### 11.3 对你 §8.3.1 的一处事实更正（会影响下一个人的判断）

你写"`-j 16`、甚至 `-j 1` 同样失败 ⇒ 不是并行度"。我在这台机器上对**同一个目标**
`gen/components/cbor/rust/cbor_rust.h` 跑 `ninja -j 1` / `-j 2` 是**一次通过**的
（记录见缺陷档案 D173）。差别在于**是否在整棵并行构建的中途跑**：

- 高并行构建**进行中**时单独重试 → 失败（与 `-j` 无关）；
- 先把 12 个 `*_crubit_action` 用 `ninja -j 2` **单独**跑完 → 之后整棵树 `autoninja -j 16`
  一路到 6830/6830 无一次 231。

⇒ 结论从"错误码误导、同一会话内重试 5+ 次均失败、要重启机器"改为
**"两段式可解，不需要重启"**。请以此为准，否则下一个人会去做不必要的全树重编或重启。
（我把这条写进 D173 的"已定策"，措辞比我上面第一版更谨慎：我没有复现你的
"会话内反复重试"全过程，只否证了"`-j 1` 也失败"这一条判别依据。）

### 11.4 复核你的新代码：两条建议 + 一条已修缺陷

| 位置 | 情况 | 处置 |
|---|---|---|
| `.bugreview/flags_lint.py:91-95,150-161` | **D176（假绿）**：`--stab` 文件不存在时返回一条 note，而 `main()` 用 `"未声明" in m` 挑致命项 ⇒ note 不匹配 ⇒ 打印"存在性核对（…）：**全部声明存在**"并 **rc=0**。触发条件真实存在（stab 未入库）。同族：D89/D138 | **已修**：调用前 `isfile` 否则 `[FAIL] … 存在性核对未执行，不得判为通过` + rc=1，并删掉函数内现在不可达的跳过分支。Red→Green 复跑：缺文件 rc=1、真实 `stab_155.json` rc=0 且 **pin=14**（与你 D171 的 14 项对上）、正向对照（塞一个不存在的 feature 名）rc=1 ⇒ 判据可失败。顺手消掉该文件两条 ruff 真阳性（`json.load(io.open(...))` 未用 `with` ⇒ SIM115、循环变量 `raw` 未用 ⇒ B007），`ruff --select F,E9,B,SIM` 现全绿；不带 `--stab` 的 CI 路径（`verify_sources.py`）不受影响，仍 PASS |
| `flags_lint.py` 的判据分派 | 致命/提示靠**自己打印的中文字符串**匹配（`"未声明" in m`、`" note " in m`），改文案即静默失效 | 未改（记录为待办）：建议返回 `(kind, msg)` 元组或抛类型化异常 |
| `win_scripts/apply_restart_cmdline.py:30` | `SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")` = **M151 树**，而 M151 **也有** `chrome/browser/chrome_browser_main_win.cc`（42,657 B）⇒ 忘了设 `CR_DIR` 会把 D172 打进旧树并自称成功 | 本机实测**未受害**（M151 树该文件里没有 MCloud 标记）。待办：脚本里读 `chrome/VERSION` 主版本号，不等于 155 就 REFUSED（同 D137"护栏要能真的触发"一族） |
| 注入正文 `chrome_browser_main_win.cc:952-956` | 三条 `erase` 后有两个连续空行 | 纯风格，`clang-format` 会收；不值得单独触发重编（D74），留待下次同批改动 |
| `win_scripts/deploy_mcloud.py:34` | 接线注释写的是 **"D166"** —— 那是你自己 `.workbuddy` 记忆里承认撞过、已改号为 D170–D172 的旧编号，而档案里 **D166 是 K1-CPU 在被测窗口内采样**那条（与重启命令行无关）。正文注释（树内 944 行）写的是 D172，只有这处漏改 | **已改回 D172**；全仓再扫 `D16[3-6]` 只剩档案里合法的 D156–D169 记录。ID 是本项目的可追溯性主干，改号后要**连注释一起扫** |

另外两点口径，我认为你写对了、这里只是复述给下一个人：
`flags_lint` 与 `flag_stability.py` 的 F 断言**故意重叠**（前者在 CI、后者不在）；
`stab_155.json` 是生成产物不入库——但配合 D176 的修复后，"没生成 stab 就跑第 7 步"
现在会红，不会再静默通过。

### 11.5 两条"文案 vs 实测"的坑（我踩了，写下来省你时间）

1. **安装目录的 mtime 不能判断新旧**：版本目录 `chrome.dll` 时间戳是 **Oct 6 08:16**
   （7z 保留归档时间戳），而 SHA1 `a0e06d99…` == 15:50 构建产物。我按 mtime 差点判成
   "装了旧包"（正是你 §8.2 警惕的形态）。⇒ 判据只能是哈希，且 dll 与根 exe 各比一次。
2. **根 `chrome.exe` 就是产物本体**，4,389,888 B、SHA1 `14e82f36…` == `out/mcloud/chrome.exe`；
   `chrome.release` 登记的是 `chrome.exe: %(ChromeDir)s\`，**版本目录里本来就没有 chrome.exe**。
   我按 §8.1/D109 的"根目录只有 4 MB 启动桩"这句话去找版本目录里的 exe，误判过一次"安装不完整"。
   D109 的**结论**不变（加载器先 `DIR_MODULE`，因为根级 flags 是跨版本残留物），措辞需要更正。

### 11.6 本轮我对本机做的事（接着你的 §8.1 记）

| 时间 | 动作 | 状态 |
|---|---|---|
| 16:09 | 真实 `mcloud_155…_setup.exe --quiet --system-level` 安装（本轮第 2 次改动已安装实例） | 已复验，装的就是本轮产物（哈希核对） |
| 16:33 | 启停一次实例（`--user-data-dir=…\mcd172after`，10 个进程按 profile 指纹收尾） | `REMAINING=0`，临时 profile 已删 |
| — | 卸载/重装过程中 Windows 再次删掉任务栏固定项 | **仍需人工重新固定**（无 API 可恢复，AGENTS.md 已记） |

我自己制造过但已修的一次判据噪声：`installer_arg_test.py` 在本轮早些时候出现过
**一次** `污染.用户级安装目录` 红（目录 `155.0.8059.40` 在 XOR 里出现两次，因空目录 mtime
被计入），其后 5 次连续绿、且我用"目录只记 (路径, 大小)"复现不出来 ⇒ 记为**未归因的一次性差异**，
已把诊断信息加进判据（差分逐项打印"前=/后="）而**没有**放宽断言。下一个人若再撞见，请留着日志别重跑。

### 11.7 还剩什么（分工写清，别让人以为收口=全部完成）

1. **`chrome/VERSION` 身份断言**（防 §11.4 的 M151 静默错树）——脚本级，不需重编。
2. **stab 的生成入口要写进 §9**：第 7 步依赖的 `stab_15x.json` 由
   **第 6 步 `python .bugreview/flag_stability.py`** 写出（它 `subprocess` 调
   `survival_check.py <rev> --json` 落盘，`flag_stability.py:101-104,145,153-154`），
   所以顺序必须是 6→7；而 `survival_check.py` 需要 **151/155/156 三棵源码树/引用在位**，
   干净检出 alone 跑不出来。配合 D176 修复后，跳过第 6 步直接跑第 7 步现在是**红**（以前是假绿）。
3. **需要开 UAC 的机器**才能做的：D158（提权自举）、D123（`--user-level` 真实安装）、
   以及 `setup_wrapper_test.py` 的端到端复验。
4. **外层 setup 的 `FileVersion`/`ProductVersion` 仍是 `0.0.0.0`**：
   第6轮那版想用 `csc /version:` 写版本号（D164，`/version` 是"打印版本并退出"，不产出文件），
   整体回退后这个能力**没有**保留下来——我实测当前发布物 `Get-Item .VersionInfo` 两个字段都是
   `0.0.0.0`。要补的话正确做法是临时 `AssemblyInfo.cs` 与源码同批编译（我验证过能把
   三处版本字段写成 `155.0.8059.40`）；不补也行，但**发布说明别声称带版本号**。
5. 老遗留：`installer_arg_test.py` 接进 `final_gate_matrix.ps1`（要处理 rc=2=PARTIAL）、
   r1–r4 实操探针未进矩阵、D49 `autoninja d8`、D147/D149/D150 三个待决策项、
   #27 SkiaGraphite 拖拽人工复现。

### 11.8 顺手做掉的两个"我怀疑过但经查不成立"的点（省你复查）

1. **K1 的测量对象没搞错**：我一度怀疑 `bench_startup.ps1` 的
   `Start-Process -PassThru` 拿到的是"启动器 PID"、`WaitForInputIdle` 量的是交接而非浏览器就绪
   （K1≈45–70 ms 这个数字本身就值得怀疑）。实测**不成立**：`out/mcloud/chrome.exe` 与
   安装版根 `Application\chrome.exe` 两种情况下，**被 Start-Process 返回的那个 PID 就是持有
   主窗口的浏览器进程**（`winhandle!=0`、`title=[about:blank - Chromium]`、是另外 7 个进程的父进程），
   `WaitForInputIdle` 在 +62/+69 ms 返回 True 且此刻 `HasExited=False`。
   ⇒ K1 的口径仍然成立（"输入空闲"≠"首帧"是另一回事，但那不是本轮引入的问题）。
   取证脚本：`.cycle6/r13_k1_validity_probe.ps1`（可复跑，按 profile 指纹收尾）。
2. **"日志 0 B"不是二进制的问题，是同 profile 第二个实例的交接**：我第一次（16:31）用
   `--enable-logging=stderr` 起跑、只结束了 `Start-Process` 返回的 PID，真实浏览器进程活到了下一轮；
   16:33 再启动时命中**单实例互斥**（D132），新进程把请求转交后自行退出 ⇒ `$p.Kill()` 抛
   "进程已退出"，而我 `--log-file` 指向的文件被交接方**截断**成 0/110 B。
   ⇒ 纪律：**取证脚本收尾必须按 profile 指纹枚举并结束全部实例，而不是只结束 `-PassThru` 那个 PID**；
   而且启动前必须断言"该 leaf 既有实例数 = 0"（我在 `r14` 里补了这个前置打印）。
   这条同时解释了 §11.6 那 10 个进程的来源——不是用户自己开的浏览器。
