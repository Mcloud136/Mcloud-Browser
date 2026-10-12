# 第5周期 bug-review 报告（D121–D146）

**日期**：2026-10-12
**范围**：全局多维度评审——安装、更新、使用、内存占用、内存安全性、运行效率、CPU 占用、多核心优化、集成显卡/独立显卡渲染优化
**方法**：bug-review 技能五步流程（语言探测 → 复现规划 → 缺陷登记 → 最小修复 → 验证留证）
**上一轮基线**：第4周期止于 D120（`docs/tasks/bug-review-cycle4-report.md`）
**编号说明**：D98 / D101 是历史空洞，不复用

---

## 交接状态（接手请先读这一段）

**代码已改、已验证，但发布物还没跟上。** 三件事按顺序做：

1. **重新打包**（必做，否则本轮的安装器修复对用户完全无效）
   `installer/mcloud_setup.cs` 的 7 处修复只编译到 `.cycle5/MCloud-Setup-verify.exe` 做过验证，
   `installer/out/*.exe` 与仓库根的 `mcloud_155.0.8059.40_win64_setup.exe` **仍是旧版**。
   需重跑 `win_scripts/build_setup_exe.py` + `.bugreview/package_m155.py`（会重新内嵌
   mini_installer 并生成 `.sha256`）。
2. **给 `setup_wrapper_test.py` 补用户级用例**（必做，否则 D121 会再犯）
   现有测试第 84、102 行永远传 `--system-level`——**唯一被验收的分支恰好是硬编码碰对了的那个**。
   补一条不带该参数的用例，断言装到用户目录且 `Verify` 通过。
3. **干净安装复验**（AGENTS.md 步骤 8 的硬性要求，**需用户授权**：会动机器上的真实安装）
   注意回显判据的期望值已从 `51+2` 变为 **`49+2`**（D142 删了 2 条死声明）。
   当前真实安装在 `C:\Program Files\Chromium\Application`，版本 155.0.8059.40，
   版本目录内 flags 完好、根目录无遮蔽残留、SHA 与仓库一致——**这些本轮已核对通过**。

**已经生效、不需要重编的**：`mcloud_flags.txt` 的清理已部署到
`D:\wxmuma\chromium-src-155\src\out\mcloud\`（仓库外）并实测回显 49+2；
`win_args_mcloud.gn` 的 PGO 路径已与构建树对齐（预检 Green 用例报"逐项一致"）；
9 个 `.ps1` 的护栏正则、`bench_memory.ps1`、`run_baseline.ps1`、`gpu_probe.py` 均已生效。

**需要重编译才生效的**：只有 D146（加载器补日志）——LOADER 是注入到
`chrome_main_delegate.cc` 的 C++，下次 `deploy_mcloud.py` 会按"正文比对式升级器"约定
自动改写树内正文（D62/D64/D67），随后需重编。本轮只做了粗粒度自检
（`.bugreview/check_loader_syntax.py`：括号 32/32、104/104、5/5 平衡），**不等于编译通过**。

**需要用户决策的**（本轮**没有**擅自改，理由见 D147/D150）：
`symbol_level=0` 是否提升（崩溃可归因性 vs 构建时间）、BIOS 超线程是否开启
（24→32 逻辑处理器，但会改变所有 CPU 类 KPI 的可比性、必须重采基线）。

---

## 摘要

本轮共登记 **26 条缺陷**，其中 **14 条已修复并验证**，12 条记录在案待跟进。

最重要的四条：

1. **D121（Critical）**：发布物 `MCloud-Setup.exe` 的**用户级安装路径整体失效**——第 613 行把
   `--system-level` 写死了，而日志、`appDir`、复验、提权分支全都按 `systemLevel` 变量走。
   门禁抓不到它，因为 `setup_wrapper_test.py` 永远传 `--system-level`，**唯一被验收的分支
   恰好是硬编码碰对了的那个**。
2. **D123（High，安全）**：系统级安装后浏览器在**提权进程内**被 `Process.Start` 拉起，
   整个浏览会话（含全部 renderer/GPU/utility 子进程）继承管理员令牌——任何网页侧 RCE
   直接等于本机管理员，且 Explorer→浏览器拖放被 UIPI 拦死。
3. **D143（Medium，但推翻了一条既有结论）**：全仓库把独显记作 "GTX 1050 Ti（Pascal，无 AV1
   硬解）"，实测真机是 **RTX 4070 Laptop（Ada，8 GB，`DEV_2860`）**。D118 据此把**实测正确的**
   `av1 powerEfficient=true` 判为"只证明被选中"，属于**用错误前提推翻正确测量**。
4. **D137（High）**：D86 之后加到 9 个脚本、10 处的"你在测 M151 旧树"护栏，正则写成了
   `chromium-src(\|$)`（转义竖线，匹配字面量 `|`），**从未在任何地方触发过**。本机恰好有两棵树。

内存安全维度的结论是**正面的**：注入到 `chrome_main_delegate.cc` 的加载器 C++（本仓库唯一
进入浏览器进程的自有 C++）经逐行核验**无越界/UAF/泄漏/未初始化**；PartitionAlloc、BRP/raw_ptr、
CET 影子栈、libc++ extensive hardening 全部处于安全侧默认。

---

## 硬件事实基线（本轮全部结论的地基）

前四轮的所有 GPU 相关判断都建立在一个错误的硬件身份上，故先把事实钉死。

| 项目 | 值 | 取证口径 |
|---|---|---|
| CPU | Intel Core i9-14900HX，**24 核 / 24 逻辑处理器** | `$env:NUMBER_OF_PROCESSORS`、`[Environment]::ProcessorCount`、`Win32_Processor.ThreadCount` 三路一致 |
| 超线程 | **BIOS 中已关闭**（该型号规格为 24C/32T） | 上述三路均报 24 |
| 独显 | **NVIDIA GeForce RTX 4070 Laptop GPU**（Ada Lovelace） | `nvidia-smi` → `0x286010DE` / 8188 MiB / 驱动 610.62 |
| 独显 PCI ID | `VEN_10DE&DEV_2860&SUBSYS_1B931043&REV_A1` | `Win32_PnPEntity` |
| 核显 | Intel(R) UHD Graphics（Raptor Lake），`DEV_A788`，驱动 32.0.101.6790 | `Win32_PnPEntity` |
| 显示器 | AOC2703（DP 外接，2560x1440@170Hz）+ TMA2021（DP 内嵌） | `WmiMonitorConnectionParams` |
| 驱动显示的卡 | **独显**（只有 NVIDIA 适配器报告活动显示模式，核显为空） | `Win32_VideoController.CurrentHorizontalResolution` |
| 内存 | 32 GB | `Win32_ComputerSystem` |
| 虚拟显示适配器 | MuMu Virtual Display Adapter、GameViewer Virtual Display Adapter | `Win32_PnPEntity`（`ROOT\DISPLAY\*`，非 PCI） |

### 显卡名称为何是错的（根因已定位）

`Win32_VideoController.Name` 与 PnP `DeviceDesc` 都报 "NVIDIA GeForce GTX 1050 Ti"，根因在

```
HKLM\SYSTEM\CurrentControlSet\Enum\PCI\VEN_10DE&DEV_2860&SUBSYS_1B931043&REV_A1\4&3a9dcb36&0&0008
    DeviceDesc   = "NVIDIA GeForce GTX 1050 Ti"     ← 字面量
    FriendlyName = "NVIDIA GeForce GTX 1050 Ti"
    MFG          = "@oem9.inf,%nvidia_a%;NVIDIA"    ← 正常驱动安装是这种间接引用形式
```

同一台机器上音频设备的 `DeviceDesc` 就是 `@hdaudbus.inf,%hdaudio.devicedesc%;…` 间接形式，
说明显卡这条是**被人为改成了字面量**（这块卡被改过名）。

该错误名称经 `DXGI_ADAPTER_DESC.Description` 传进 Chromium，于是 chrome://gpu 与 WebGL 的
`UNMASKED_RENDERER_WEBGL` 都显示：

```
ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti (0x00002860) Direct3D11 vs_5_0 ps_5_0, D3D11)
```

**名字错、设备号对。** 好消息：Chromium 的 `software_rendering_list.json` /
`gpu_driver_bug_list.json` 按 PCI vendor+device ID 匹配而非按名字，所以规避规则命中的是 Ada
的正确条目——实测已应用 `Disable VP9 k-SVC video decoding on non-Intel GPUs`
（crbug.com/1508379，`disable_d3d11_vp9_ksvc_decoding`），这本身就证明它被正确识别为 non-Intel。

> **纪律**：不要再用显卡**名称**推断硬件能力。任何"某卡不支持 X"的判断必须以 PCI 设备号、
> `nvidia-smi` 或 chrome://gpu 的能力清单为准。

---

## 实测取得的渲染面证据

探针：`.bugreview/gpu_identity_probe.py`（本轮新增，四类证据交叉），被测
`D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe`（4,389,888 B，mtime 2026-10-11T20:01）。
证据：`.bugreview/gpu_identity_result.json`、`.bugreview/gpu_page_full.txt`（chrome://gpu 全文 79,428 B）。

**Graphics Feature Status**（chrome://gpu）：

```
Canvas: Hardware accelerated            Video Decode: Hardware accelerated
Compositing: Hardware accelerated       Video Encode: Hardware accelerated
Multiple Raster Threads: Enabled        WebGL: Hardware accelerated
OpenGL: Enabled                         WebGPU: Hardware accelerated
Rasterization: Hardware accelerated     WebNN: Disabled
  on all pages                          Direct Rendering Display Compositor: Disabled
Skia Graphite: Disabled（定案禁用）      TreesInViz: Disabled
Raw Draw: Disabled
```

**Video Decode Accelerator Supported Profile**（决定性）：

```
Decode h264 baseline/main/high : 64x64 to 4096x4096
Decode vp9 profile0/profile2   : 128x128 to 8192x8192
Decode hevc main / main 10 / main still-picture / range extensions : 144x144 to 8192x8192
Decode av1 profile main        : 128x128 to 8192x8192      ← Pascal 不可能有这一条
```

**MediaCapabilities**（4K@30 / 20 Mbps）：h264 / hevc / vp9 / av1 全部
`supported=True smooth=True powerEfficient=True`。

**渲染适配器归属**：WebGL 走独显（NVIDIA，`0x00002860`，D3D11）。显示器也由独显驱动，
故**不存在跨适配器拷贝开销，当前归属是最优的**，无需调整。

**清理**：残留进程 0（否则锁住 `out/mcloud` 里的 DLL，见 D71）。

---

## 缺陷清单

### 安装 / 更新（`installer/mcloud_setup.cs`、`win_scripts/build_setup_exe.py`）

#### [D121] mcloud_setup.cs:613 — 硬编码 `--system-level`，用户级安装路径整体失效
- **严重度**：Critical
- **根因**：逻辑错误（参数未接线）
- **证据**：第 612 行 `SetStage("安装 …（" + (systemLevel ? "系统级" : "用户级") + "）")`
  按变量显示；第 613 行 `int irect = RunAndWait(pkg, "--system-level");` 写死。
  `appDir` 由第 531/539 行按 `systemLevel` 计算，`Verify(appDir, …)` 因此查错目录。
  上游只认 `--system-level`，用户级 = 不传该开关
  （`chrome/installer/mini_installer/configuration.cc:77-97`，**没有 `--user-level` 这种开关**）。
- **影响**：
  - 非管理员双击（文件头宣称的默认"用户级安装，不弹 UAC"）：第 552 行
    `if (systemLevel && !IsAdmin())` 因 `systemLevel=false` **不触发提权**，于是以非提权身份
    跑系统级安装；上游系统级分支含 `AddElevationServiceWorkItems` →
    `CHECK(::IsUserAnAdmin())`（`install_worker.cc:115-122,317-322`）→ 构建工作项阶段就崩，
    什么都没装，`Verify` 随之失败 rc=1。
  - 管理员双击：真的装进 `C:\Program Files\Chromium\Application`，而 `appDir` 仍指向用户目录
    → `Verify` 必然失败 rc=1，同时机器上多出一份用户从未要求的系统级安装——**正是 D120 要
    禁止的"擅自换位置"**。
- **门禁为何没抓到**：`.bugreview/setup_wrapper_test.py:102` 永远传 `--system-level`，
  第 84 行同样。**唯一被验收的分支恰好是硬编码碰对了的分支。**
- **修复**：`RunAndWait(pkg, systemLevel ? "--system-level" : "")`。

#### [D129] mcloud_setup.cs:613-624 — 安装器自身退出码不参与判定
- **严重度**：Medium　**根因**：校验缺失
- `irect` 只被打日志，`rc` 全由 `Verify` 决定；而 `Verify` 只查"版本目录 / chrome.dll /
  mcloud_flags.txt 是否存在"，**同版本重跑时它们本来就在**，于是"安装失败 + 目录残留"被判
  rc=0"完成：已确认更新到 X"。`Verify` 也从不读 `chrome.dll` 的版本，只读存在性（461-463）。
- **修复**：`irect != 0` 直接 `ok = false` 并写明原因（与 D121 同批落地）。

#### [D122] mcloud_setup.cs:488-500,552-561 — 提权自举"发射后不管"，父进程恒返回 0
- **严重度**：High　**根因**：校验缺失 + 退出码假绿
- `RelaunchElevated` 只 `Process.Start` 不等待，随后第 560 行 `return 0;`。提权子进程的
  rc=1（复验不通过）/ rc=2（异常）**全部丢失**。任何脚本、CI 或 AGENTS.md 要求的"干净安装
  复验"在 `--system-level` 下都只能看到 0。父进程还在子进程安装中途就退出，用户看到 UAC
  之后原窗口消失、无进度。
- **修复**：改为返回 `int`，`WaitForExit()` 后透传子进程退出码；新增两个哨兵值
  `ELEV_LAUNCH_FAILED(-1)`（UAC 被拒）与 `ELEV_RC_UNAVAILABLE(-2)`（非提权父进程拿到的
  提权子进程句柄通常只有 `SYNCHRONIZE`、没有 `PROCESS_QUERY_INFORMATION`，`ExitCode` 会抛
  Access Denied）。**取不到退出码同样按失败上报**，不空值算绿（D100/D115 纪律）。

#### [D123] mcloud_setup.cs:626-633 — 系统级安装后以管理员令牌重启浏览器
- **严重度**：High（安全）　**根因**：API 误用（未降权）
- 提权重启后，接管的是**已提权**的那个实例，其中 `Process.Start(chrome.exe)` 配
  `UseShellExecute=true` ⇒ 子进程继承完整管理员令牌。此后整个浏览会话以 admin 运行：
  所有 renderer/GPU/utility 子进程继承 admin，下载文件属主为 admin，Explorer→浏览器拖放被
  UIPI 拦截，**任何网页侧 RCE 直接等于本机管理员**。上游安装器从不这么做。
- 这一条与本仓关心的"内存安全性"直接相关：它不制造内存错误，但把任何一个内存错误的
  **后果**从"沙箱内"抬到"本机管理员"。
- **修复**：提权上下文内改由 `explorer.exe "<path>"` 启动，落回交互用户的中等完整性级别；
  非提权路径保持原样。并记日志说明为何绕道。

#### [D124] mcloud_setup.cs:255-257 — 默认浏览器"整条注册丢失"被判为通过
- **严重度**：High　**根因**：校验缺失（假绿）
- 旧判据 `regressed = before=="yes" && after=="NO"`。若更新把 `UserChoice` 整条抹掉，
  `DefaultBrowserTarget()` 返回 null → `UserTarget="(unresolved)"` → `TargetExists="n/a"`
  （188-190）→ **不算回归**。丢注册比指向死文件更严重（用户彻底失去默认浏览器），却静默放过。
  这是本文件里**唯一一处 FAIL 判据**上的假绿。
- 附带：`after["TargetExists"]` 直接索引，若 `SnapshotAssociations` 在第 188 行之前抛异常
  会 `KeyNotFoundException`（`before` 侧有 `Has()` 守卫，`after` 侧没有）。
- **修复**：`wasGood && (afterExists=="NO" || afterExists=="n/a")` 均判回归，两种情形分别给出
  不同文案；两侧都走 `Has()` 守卫。

#### [D125] mcloud_setup.cs:382-390 — "查不到就算已退出"
- **严重度**：Medium　**根因**：异常吞没导致校验假绿
- `Alive()` 的 `catch { /* 已退出 */ }` 把 `Refresh()`/`HasExited` 的**任何**异常都当成进程已
  退出。最常见原因是跨完整性级别访问被拒（安装器未提权而浏览器进程提权），此时进程活得好好的、
  还锁着根启动桩。`WaitForExit` 于是立刻返回 true，安装器随即对着**仍在运行的浏览器**执行
  setup.exe ⇒ **精确复现 D119**（上游走 in-use 分支暂存 `new_chrome.exe`，收尾改名委托给
  Google Update，而本产品不发布 Google Update）⇒ 静默无效更新。
- **意义**：D119 的修复（外层包装器）可以被 D125 抵消。
- **修复**：异常一律按"仍存活"处理并记 WARN（含 pid 与原因），宁可超时中止也不假绿；
  用静态 `HashSet<int>` 去重，避免 500 ms 轮询把同一条 WARN 刷满日志。

#### [D127] mcloud_setup.cs:170-173 — 用序数字符串比版本号
- **严重度**：Medium　**根因**：API 误用
- `string.Compare("155.0.8059.40", "155.0.8059.9")` < 0（第 4 段首字符 `'4' < '9'`），
  于是两处都装且默认浏览器不归属任一处时，**选中版本更低的那份**去更新。第 170 行原注释
  "字符串比较对 a.b.c.d 够用"是错的。
- **修复**：`Version.TryParse` 逐段整数比较；解析不出来时退回字符串比较**并打 WARN**（不静默）。

#### [D128] mcloud_setup.cs:206-213 — 快捷方式快照漏掉全机器开始菜单
- **严重度**：Low　**根因**：校验缺失
- `dirs` 只有 `DesktopDirectory` / `CommonDesktopDirectory` / `StartMenu\Programs` / Quick Launch，
  没有 `CommonStartMenu`（`C:\ProgramData\Microsoft\Windows\Start Menu\Programs`）。
  系统级安装的快捷方式恰在那里 ⇒ D120 关心的"快捷方式指向死路径"在系统级路径上**根本不会
  被 WARN 到**。
- **修复**：补 `SpecialFolder.CommonStartMenu + @"\Programs"`。

#### 记录在案、本轮未修（D126 / D130–D136）

| ID | 级别 | 位置 | 问题 | 为何未修 |
|---|---|---|---|---|
| D126 | Med | `mcloud_setup.cs:287,479,584` | 关闭集合只枚举进程名 `chrome`，漏 `chrome_proxy.exe` / `chrome_crashpad_handler.exe` / `elevation_service.exe`（`install_worker.cc:115-135` 注册为 Windows 服务）；`allowForce` 写死使 343-346 的"不强杀就中止"分支成死代码；GUI 按钮全程禁用无倒计时，30 s 后无条件 TerminateProcess | 需要把关闭集合改为按 `appDir` 路径前缀匹配 + GUI 交互重设计，改动面大，宜单独一轮 |
| D130 | Med | `build_setup_exe.py:59-64`、`package_m155.py:143-151` | 找不到 Roslyn 时无声退回旧 csc（**实测旧 csc 两次编译 SHA 不同**：`c4c5da27…` vs `2025fcdd…`；Roslyn `/deterministic+` 跨目录同名两次一致 `2e25c93e…`）；`package_m155.py` 用 `capture_output=True` 且只在失败时打印，成功路径把"用了哪个编译器/是否可复现"整段丢弃，随后照样写 `.sha256` 与发布说明 | 建议改为 `deterministic=False` 即 `fail()`（或加 `--allow-nondeterministic`），并无条件转印子进程 stdout |
| D131 | Med | `mcloud_setup.cs:692-705,752` | `BuildUi` 只等 2 s（40×50 ms）让句柄建好；句柄没建成时 `_done.WaitOne()` **无超时永久阻塞**。且发布物是 GUI 版（`/target:winexe`），而 `setup_wrapper_test.py:34,102` 只测 `MCloud-Setup-console.exe --quiet` ⇒ `BuildUi`/`Finish`/`Log` 的 UI 分支**从未被任何门禁执行过** | 需补 GUI 形态用例 + `WaitOne(TimeSpan)` 降级 |
| D132 | Med | 全文件无 `Mutex` | 并发双击两个包装器 → 两边同时关浏览器、同时对同一棵树跑 mini_installer，工作项列表互相踩 | 修法明确（命名 Mutex + 已存在则退出 2），本轮未动 |
| D133 | Low | `mcloud_setup.cs:76,82,576-582` | 发布形态是 `winexe`，无控制台时 `Console.WriteLine` 落到虚空 ⇒ AGENTS.md 与发布说明都宣传的 `--list-only` **在用户手上是哑的** | 需改为写日志文件或强制 `--quiet` 语义 |
| D134 | Low | `build_setup_exe.py:69-81` | 不传 `/version` 或 `/win32res`；实测发布物 `mcloud_155.0.8059.40_win64_setup.exe` 的 ProductVersion/FileVersion 均为 `0.0.0.0`，无法从文件属性辨别包装器版本，SmartScreen/AV 情报也更弱 | 一行编译参数即可，宜与 D130 同批 |
| D135 | Low | `mcloud_setup.cs:471-476,658-665` | `Verify`（校验函数）里 `File.Delete` 删根目录 `mcloud_flags.txt`，校验带副作用且失败时也已删过；残留扫描按机器级进程名 `setup`/`mini_installer` 匹配，会撞上用户同时在跑的任意 `setup.exe` 并打假 WARN（好在只 WARN 不杀） | 副作用与校验应分离 |
| D136 | Low | `mcloud_setup.cs:130,143` | `DefaultBrowserTarget` 先查 HKLM 再查 HKCU，两处都注册同一 ProgId 时系统级胜出，可能把"用户在用的用户级那份"误判成系统级，进而绕开 D120 的就地更新；143 的 `cmd.Split(' ')[0]` 对无引号且含空格的路径会截断 | 与 D124 同族，需一并设计 |

**复核确认无回归**：D105 的 `%(VersionDir)s` 登记在 M155 树内实际生效；`OurBrowserProcesses`
（284-311）按 `MainModule.FileName` 路径前缀匹配、读不到路径时明确**不**计入目标，符合
D52/D55/D106 纪律；临时目录 `%TEMP%\MCloudSetup-<12位GUID>`，`DeleteTree` 只递归该目录。

---

### 量具 / 门禁（`benchmark/`、`.bugreview/`）

#### [D137] 9 个文件 10 处 — "你在测 M151 旧树"护栏的正则从未生效
- **严重度**：High　**根因**：正则转义错误（逻辑错误）
- 全部写成 `-match 'chromium-src(\|$)'`。`\|` 是**转义竖线**，匹配字面量 `|`；`$` 紧随其后。
  任何真实路径都不含 `chromium-src|`，所以**永不匹配**。正确写法是 `'chromium-src(\\|$)'`
  （反斜杠或串尾）。
- **实测**（`.bugreview/test_d137_guard.py`，本轮新增并已入库；一次性版本曾为 `.cycle5/regex_test.ps1`）：

  | 写法 | M151 树 | M155 树 |
  |---|---|---|
  | 旧 `chromium-src(\|$)` | False | False |
  | 新 `chromium-src(\\|$)` | **True** | False |

- **影响面**（10 处）：`bench_memory.ps1:41`、`bench_navigation.ps1:49`、`bench_size.ps1:28`、
  `bench_startup.ps1:35`、`run_baseline.ps1:28,41`、`tools/bolt_pipeline.ps1:31`、
  `tools/diag_igpu_green_screen.ps1:32`、`tools/pgo_collect.ps1:33`、
  `tools/verify_builtin_flags.ps1:35`。
- **为何严重**：本机同时存在 `chromium-src`（M151 回滚参考树）与 `chromium-src-155`（发布树），
  这正是 D86/D72 当初要防的场景。护栏全线失效意味着"把结果归属到错误的产物树"这件事
  **完全静默**。
- **修复**：10 处全部改为 `(\\|$)`；在 `bench_memory.ps1` 留注释说明 `\|` 与 `\\|` 的区别，
  防止将来被"简化"回去。BOM 全部保留（D38），`verify_sources.py` 45 个 `.ps1` AST 解析全绿。
- **已机器化**（同 D38/D83/D97 的做法）：`win_scripts/verify_sources.py` 的
  `check_powershell_static()` 新增一条闸——非注释行里出现 `chromium-src(\|$)` 即判 FAIL 并
  给出正确写法。回归判据 `.bugreview/test_d137_guard.py`（Green：无探针时门禁 PASS；
  Red：放入一个含坏写法的临时 `.ps1` 后门禁 FAIL 且指名该文件；收尾断言探针已删、
  `benchmark/` 零改动）。
  ⚠ 该闸第一版把 `.cycle5/regex_test.ps1` 也扫进来了——那是一次性取证脚本，**故意**同时
  含坏写法与正确写法以证明差异，于是门禁在自己的取证语料上失败。已让
  `collect_powershell_files()` 跳过 `.cycle*` 目录（AGENTS.md 约定：那是一次性脚本与证据、
  整目录 gitignore）。`.diag/`（D110 定性为历史材料）与 `.qoder/` 的既有扫描范围未动。

#### [D138] bench_memory.ps1:88-96 — K2 取不到进程时输出"0 MB"并以 0 退出
- **严重度**：High　**根因**：校验缺失（假绿）
- `$ids.Count -eq 0` → `$procs=@()` → `Measure-Object … -Sum` 得 `$null` →
  PowerShell 里 `$null / 1MB == 0` → 照样 `$measured += 0`、打印"0 MB（进程数 0）"、
  最终 `exit 0`。**浏览器根本没起来却被记成"内存峰值 0 MB"**，读起来像巨大改善。
- 直接违反 AGENTS.md 硬规则"取不到进程必须判 FAIL，禁止返回 0 值式的'成功'"（D52/D55 家族）。
- K2 是 `run_baseline.ps1` 的三大 KPI 之一，所以这条污染的是 headline 指标。
- **修复**（四处）：
  1. 匹配到 0 个进程 → `throw`（`finally` 仍负责清理实例与临时目录）；
  2. 拿到 PID 但 `Get-Process` 取不到 → `throw`；
  3. `WorkingSet64` 求和为 `$null`（计数器不可用）→ `throw`；
  4. 循环后自检 `$measured.Count -ne $Samples` → `throw`（D89 教训：聚合完必须自检条数，
     否则"汇总不完整"会表现成一个看起来完全正常的中位数），并补 `exit 0`。
- 附带：指纹由完整路径改为 profile **叶子名**，与 `cdp.kill_instance` 同口径
  （`$env:TEMP` 可能是 8.3 短名形式而命令行里是长名，整批子串匹配会落空）。

#### [D145] 全仓库没有任何 CPU 占用率量具
- **严重度**：Medium　**根因**：量具缺口
- K1–K7 里**没有 CPU 指标**。`benchmark/` + `.bugreview/` 全量搜索只有 3 处文本命中：
  `benchmark/README.md:15,59-62`（K6 是手工流程，写着"用任务管理器/Get-Counter 采样"，
  未自动化）、`run_baseline.ps1:90-96`（只记 `Win32_Processor` 的**型号名**）。
  用户本轮明确问到"CPU 占用"，而仓库无法回答。
- **修复**：在 `bench_memory.ps1` 既有的 K2 采样循环上增加 CPU 采集（新增 `-NoCpu` 开关可关），
  作为独立指标 **K2-CPU** 输出，不改动 K2 内存数值本身的语义。实现要点：
  - 复用同一批 PID 与同一次 `Get-Process` 快照 ⇒ 不额外扰动被测实例，也**不引入第二套进程
    枚举**（避免重犯 D52/D55 按进程名统计）；
  - `TotalProcessorTime` 是累计值，且本实例 PID 集合会在采样间变动（renderer 起停），
    故用 `Hashtable` **按 PID 分别做差再求和**；新出现的 PID 其累计值就是它自诞生以来真实
    消耗的 CPU，消失的 PID 停止贡献，负增量按 0 计；
  - 墙钟增量用 `[DateTime]::UtcNow` 实测而非 `SampleInterval` 名义值（WMI 查询本身耗时）；
  - 同时输出**占整机百分比**与**折合核数**两个口径，并注明跨机器比较必须看折合核数
    （否则 24 核机器上的同一负载会显得比 8 核机器"轻"三倍）；
  - 计数器取不到 → `throw`。**上游 Chromium 自己在这类地方用 `.value_or(0.0)` 把失败吞成 0**
    （`chrome/browser/task_manager/sampling/task_group_sampler.cc:125`），本仓库不得照抄；
  - 格式化一律用 `-f`（D66-①）。
- **验证（Red→Green 双向）**：
  - Green 实跑：`中位数 0.06% 整机 / 峰值 0.11%`，`折合核数中位数 0.02 核`，`exit 0`；
  - 首版把 `$cores * 100` 存进"核数"数组，实跑立刻自相矛盾（`0.11% 整机` 旁边印 `2.70 核`）；
    据此新增**单位自洽断言** `|cores/逻辑核*100 − pct| > 0.5 → throw`；
  - Red：把 100 倍错误重新注入副本 → 断言触发、`exit 1`、报"差 7.84"。
- **顺带发现的 PowerShell 陷阱（已修，全仓已扫）**：`"A{0}" + "B{1}" -f $x,$y` 中
  **`-f` 的优先级高于 `+`**，格式化只作用在 `B` 那一段，`A` 里的占位符原样印出来。
  Red 验证时正是靠这个现象发现了它（报错里 `{0:N3}`/`{1:N2}` 未被替换）。修法是
  `(("A" + "B") -f …)`。已用多行正则全仓扫描 `.ps1`，**无既存同类问题**（D66 家族的新变体）。

#### [D139] run_baseline.ps1:92 — 每份 KPI 基线的 GPU 都被记成虚拟显示器
- **严重度**：Medium　**根因**：取值错误（`Select-Object -First 1`）
- `$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1` 取的是 WMI 枚举顺序
  里的第一个适配器。本机 MuMu / GameViewer 两个虚拟显示器排在真实显卡前面 ⇒
  实测 `-First 1` 返回 **MuMu Virtual Display Adapter**（无 GPU）。
- **已归档基线的实际受损情况**：

  | 文件 | 记录的 GPU | 有无警示 |
  |---|---|---|
  | `docs/dev-logs/M150-benchmark.md:15` | GameViewer Virtual Display Adapter / 15.6.5.199 | 有（人工加注"不代表本机独显"） |
  | `docs/dev-logs/M151-benchmark.md:15` | 同上 | 有 |
  | `docs/dev-logs/M151-opt-benchmark.md:15` | 同上 | 有 |
  | `docs/dev-logs/M155-benchmark.md:17` | **MuMu Virtual Display Adapter / 20.36.41.498** | **无** |

  即当前权威的 M155 基线，其环境块声称的显卡**在本机上不是一个 GPU**，且无任何提示。
- **修复**：只认 `PNPDeviceID -like 'PCI\*'` 的适配器；逐个输出名称 + **PCI VEN:DEV** +
  驱动版本 + 是否驱动显示（有活动显示模式者）；把被排除的虚拟适配器单列一行说明；
  一个真实显卡都识别不到时 `throw`（拒绝写出基线，不编造环境）；
  另增"逻辑处理器 / 物理核"一行并注明两者相等意味着超线程关闭，因为它直接影响 CPU 类 KPI
  的可比性（本机 24/24）。
- **为何用 PCI 设备号**：本机 WMI `Name` 被注册表改名污染（见 D143），设备号才可信。

#### [D140] gpu_probe.py:68 vs 80 — 清理复检用了比首检更弱的指纹，失败即静默
- **严重度**：Medium　**根因**：逻辑不一致导致假绿
- 第 68 行首次查 PID 用 `key`（profile **叶子名**），第 80 行循环内**复检**却用 `prof`
  （**完整路径**）。而该文件第 33-34 行的注释恰恰在解释为什么必须用叶子名：
  "Python 的 TEMP 可能是 8.3 短名形式，而 chrome 命令行里是长名（或反之），整批子串匹配会
  落空——同 leak_probe 里刚被回归测试抓到的那个坑"。
- 后果：短名/长名不一致时复检匹配为空 → `pids` 变空 → 循环 `break` → **不打印任何 WARN**，
  而进程其实还活着。不只是报告失真：残留 chrome 会锁住 `out` 目录里的 DLL，让下一次链接以
  `lld-link: failed to write ./dxcompiler.dll: permission denied` 失败（D71 实测）。
- 对照：`cdp.kill_instance`（`benchmark/tools/cdp.py:392-410`）首检与复检都用
  `os.path.basename(os.path.abspath(profile))`，是正确范式；`gpu_probe.py` 没复用公共底座。
- **修复**：复检改回 `key`，并注明为何两处必须同指纹。

#### [D141] Python 工具未落实 `MCHROME_EXE` / `MCHROME_OUT` 纪律
- **严重度**：Low　**根因**：约定只落实了一半
- AGENTS.md 明写"`benchmark/*.ps1` 与 `benchmark/tools/*` 的默认对象改为 `$env:MCHROME_EXE` /
  `$env:MCHROME_OUT`（再退回 155 树）"。实测：`.ps1` 全部合规（env 引用 ≥2），
  **`.py` 基本没落实**——`gpu_probe.py` env=0/硬编码=3、`check_features.py` env=0/硬编码=1、
  `r1_startup_check.py` env=0/硬编码=1（`r2/r3/r4` 各 1 处，`cdp.py`/`leak_probe.py` 无硬编码）。
- **修复（部分）**：`gpu_probe.py` 的 `--chrome` 默认值与无参双树对比分支均改为
  `os.environ.get("MCHROME_EXE") or <155 树>`，并对不存在的产物打 `SKIP` 而非崩溃。
  `check_features.py` / `r1_startup_check.py` 仍待跟进。

#### [D142] mcloud_flags.txt — 2 条平台上根本编译不进来的声明 + 2 条上游默认已启用的声明
- **严重度**：Medium　**根因**：校验缺失（声明位存在 ≠ 本平台生效）
- 逐条源码核实（M155 树）：

  | 条目 | 声明位置 | 判定 |
  |---|---|---|
  | `BaseLockTrySpin` | `base/features.h:82-83`、`base/features.cc:219-230`，整体在 `#if BUILDFLAG(IS_POSIX)` 内；唯一消费者 `base/synchronization/lock.cc:176-180` 同样在守卫内 | **Windows 构建里该 feature 不存在**，静默忽略。第二重无效：即便 POSIX，参数默认 `spin_count_x86 = 0`（`base/features.cc:226`），裸名启用 = 自旋 0 次（D51 家族） |
  | `PartitionAllocUsePriorityInheritanceLocks` | `base/allocator/partition_alloc_features.cc:430-431`，在 `#if PA_BUILDFLAG(ENABLE_PARTITION_LOCK_PRIORITY_INHERITANCE)` 内；该 buildflag = `is_android && (current_cpu=="x64"\|\|"arm64")`（`base/allocator/partition_allocator/partition_alloc.gni:588-589`，注释原文 "Enabled only on 64-bit Android"） | `target_os="win"` ⇒ buildflag 假 ⇒ **符号未编译进 chrome.dll** |
  | `PartitionAllocMemoryReclaimer` | `base/allocator/partition_alloc_features.cc:312` `FEATURE_ENABLED_BY_DEFAULT` | 上游默认已启用，`--enable-features=` **净效果为零** |
  | `PruneOldTransferCacheEntries` | `gpu/config/gpu_finch_features.cc:497` `base::FEATURE_ENABLED_BY_DEFAULT` | 同上 |

- **门禁为何漏掉（系统性盲区，D89 同族"门禁的门禁"）**：
  - `.bugreview/flag_stability.py` 的不变式是"每条 feature 在 151/155/156 三版**声明存在**"，
    这四条都满足 ⇒ 全绿；
  - `.bugreview/survival_check.py` **已采集**声明默认值（`:18`、`:108` 的 `default` 字段），
    但 `flag_stability.py` 的 C 断言只判 `state=="OK"`（`:158-168`），**从不读 `default`**；
  - `benchmark/tools/check_features.py:70-78` 是全树**纯文本**正则扫描，不评估 `BUILDFLAG`
    守卫，结构上无法发现条件编译这一类。
- **修复（区别处置，不是一刀切删除）**：
  - 2 条**平台不可能生效**的 → **删除**（同 D48 处置；删了净行为为 0），并在原位留下
    源码级依据，注明"Windows 上想调锁自旋没有对应 feature，不要按名字猜"；
  - 2 条**上游默认已启用**的 → **保留但加注**。理由：它们是**显式钉住（pin）**，防止上游将来
    翻默认值时本产品行为跟着变——与本仓对 `SkiaGraphite` 的处置思路一致
    （"实测在 151/155/156 均为上游默认启用，仅注释掉启用行并不等于禁用"）。
    加注明确写出"读清单时不要把这两项算作已生效的定制收益"。
- **验证**：`flag_stability.py` **PASS / exit 0**，且门禁**独立确认**了删除是零净行为：
  `B 移除 2 项：BaseLockTrySpin, PartitionAllocUsePriorityInheritanceLocks`、
  `这两项在 M151 上也是无效的（净行为为 0）: 0`；`C r3 项目全部存活 51/51`；
  `E InitialWebUI params 成对校验通过`；`F 冻结注释检查未触发`。
  部署到构建树后对二进制重跑 `flag_runtime_state.py`：回显由 **enable 51 / disable 2** 变为
  **enable 49 / disable 2**，恰为删掉的 2 条，其余逐项不变，`SkiaGraphite`/`D3D12VideoDecoder`
  的禁用（拖拽冻结缓解定案）完好，`exit 0`。
- **口径更新**：清单现为 **184 行 / 54 条活动开关行 / 51 项 feature / 3 项普通开关**
  （原 142 行 / 56 / 53 / 3）。AGENTS.md 第 10 行已同步。
- **未动**：`InfiniteTabsFreezingOnMemoryPressure`(:47) 在 `InfiniteTabsFreezing`(:46) 启用时
  是 else-if 链的不可达分支（`components/performance_manager/freezing/freezing_policy.cc:485-497`），
  只剩 Windows 专属的 `memory_check_timer_`(:263-271) 周期性开销。这是**冗余而非无效声明**，
  删除属行为变更，宜先 A/B，本轮只记录。

#### [D144] win_args_mcloud.gn:57 — `pgo_data_path` 指向 M151 树，仓库模板与真实构建配置漂移
- **严重度**：High　**根因**：配置漂移（发布不可复现）
- 仓库模板写 `D:/wxmuma/chromium-src/src/…/chrome-win64-8059-….profdata`（**M151 树**），
  实测该目录只有 `chrome-win64-7871.profdata` 与 `chrome-win64-7922-….profdata`，
  **没有 8059 这份**；而真正构建出 r5 的
  `D:/wxmuma/chromium-src-155/src/out/mcloud/args.gn:57` 早已手工改成 155 树路径（文件存在，
  507,095,496 B）。
- **两份配置的完整 diff 只有 2 行**（PGO 注释 + `pgo_data_path`），也就是说
  **仓库里committed 的 `win_args_mcloud.gn` 根本构建不出已发布的 r5 二进制**。
- **失败模式**（源码级）：`build/config/compiler/pgo/BUILD.gn:149` 只 `assert(pgo_data_path != "")`
  ——**不校验存在**，所以 `gn gen --check` 能过；第 156 行 `inputs += [ pgo_data_path ]` 让 ninja
  把该文件登记为隐式依赖，于是 `autoninja` 立刻报
  `missing and no known rule to make it`。失败信息完全不指向根因。
- 按 AGENTS.md 的 `cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn`（"首次或配置变更时"）
  走一遍即触发；这也与"多棵树时 `deploy_mcloud.py` 必须显式设 `CR_DIR`"是同一族陷阱。
- 附带：`win_scripts/build_win.py:35` 的 `CR_DIR` 默认值是**第三个口径**
  （`C:/src/chromium/src`，本机不存在），与 `deploy_mcloud.py` 的默认值（M151 树）不一致。
- **修复（两部分）**：
  1. 路径改回 155 树，并在原位写下 GN 不校验存在这一源码级依据；
  2. `win_scripts/build_win.py` 新增 `preflight_args()`，在 `autoninja` 之前：
     - `chrome_pgo_phase=2` 时校验 profdata **确实存在**，不存在则以 111 退出并给出根因与两种修法；
     - **模板 vs 构建树 args.gn 逐项漂移比对**，不一致则 WARN 并逐条列出（注释行不参与比对），
       把"仓库里的配置 ≠ 构建出发布物的配置"这件事变成编译前就能看见的信号。
- **验证（Red→Green，`.bugreview/test_build_win_preflight.py`）**：
  - Green：真实 args.gn → `PGO 预检 OK：phase=2 剖面 484 MB`，且
    **`漂移比对 OK：仓库模板与构建树 args.gn 逐项一致`**（直接证明 D144 已对齐、发布重新可复现）；
  - Red：把路径替换回 M151 树 → **rc=111**，报"chrome_pgo_phase=2 但 PGO 剖面不存在"并列出
    来源、常见原因、两种修法，且**未继续执行**（无 `PREFLIGHT_DONE`）；
  - Red2：构建树 `chrome_pgo_phase=0` 而模板为 2 → 精确报出漂移项。

#### [D146] inject_flags_loader.py LOADER — flags 三处候选全失败时裸 `return`，无任何日志
- **严重度**：Low（可诊断性）　**根因**：静默失败
- LOADER 的 `module_dir → exe_dir → 已安装载荷目录` 三级候选全部失败时直接 `return`，
  而**只有预算溢出**才 `LOG(WARNING)`。整套运行时优化丢失时无进程内信号——正是 D105 那个
  发布阻断的形态（编译与打包全部成功，安装版就是不带 flags，静默丢失）。
- **修复**：补 `LOG(WARNING)`，列出三个已尝试的位置，并明说"所有内置性能标志处于未生效状态"。
- **必须记录的局限（已写进代码注释）**：该函数由
  `ChromeMainDelegate::BasicStartupComplete()`（树内 `chrome/app/chrome_main_delegate.cc:1368-1372`）
  调用，而 `InitLogging()` 要到 `PreSandboxStartup()`（同文件 `:1756`）才执行。
  所以此刻 logging **尚未初始化**，这条 WARNING 只能到 OutputDebugString / 附加的调试器，
  **即使用户加了 `--enable-logging=stderr` 也看不到**。既有的 284/317 行 `LOG(WARNING)` 同理。
  ⇒ **权威检测手段仍是外部探针** `.bugreview/flag_runtime_state.py`；本轮已核实它在 flags
  文件缺失时确实 `raise SystemExit`（`:201-207`，退出码非 0），D105 类回归门禁能拦住。
- **生效条件**：LOADER 是注入到 `chrome_main_delegate.cc` 的 C++，本条改动**需要重新
  `deploy_mcloud.py` + 重编译**才进入二进制；按 D62/D64/D67 的"正文比对式升级器"约定，
  下次 deploy 会自动把树内正文改写为新版。

#### [D143] 全仓库把独显记作 GTX 1050 Ti，并据此推翻了正确的 AV1 实测值
- **严重度**：Medium　**根因**：错误事实前提 → 错误结论
- 受影响位置（均已更正）：
  - `mcloud_flags.txt:99-108`（D3D12VideoDecoder 禁用理由段）；
  - `docs/tasks/bug-review-cycle4-report.md:94`；
  - `docs/tasks/bug-review-pak-src-defects.md:722`（D118 行）；
  - `.cycle4/d107_rows.md:12`（历史取证材料，未改）；
  - `.qoder/repowiki/zh/content/性能优化/性能优化.md:299`（生成物，未改）。
- **实质危害**：D118 的处置写着"h264/hevc/av1/vp9 全部 `supported+smooth+powerEfficient=true`
  （注意：该字段只证明'被选中'，GTX 1050 Ti 无 AV1 硬解单元…）"。
  测量是**对的**，却被错误的硬件前提降级为"不足以采信"。
  本轮 chrome://gpu 硬解清单实测含 `Decode av1 profile main: 128x128 to 8192x8192`
  ——Pascal 不可能有这一条。**结论应翻转为：AV1 硬件解码在本机真实可用。**
- **修复**：在 `mcloud_flags.txt` 与两份缺陷档案里写入完整取证链（nvidia-smi / 注册表
  DriverDesc / chrome://gpu 能力清单 / 注册表字面量 DeviceDesc 根因 / DXGI 传播路径 /
  Chromium 按 ID 匹配故未受影响），并立下纪律：**不要用显卡名称推断硬件能力**。
  D118 的历史结论用删除线保留、不抹除，符合本仓"更正而非重写历史"的做法。
- **未受影响的部分**：`--disable-features=D3D12VideoDecoder` 的**决定本身不变**——
  绿屏是 Intel 核显侧实测到的（T3 对照实验），与独显型号无关。

---

### 构建配置（`win_args_mcloud.gn`）—— 记录在案，需用户决策

#### [D147] `symbol_level = 0`（:28）使发布产物的崩溃无法归因
- **严重度**：Medium-High（可诊断性 / 内存安全）　**状态**：**未改，建议决策**
- 上游 official build 的默认是 `default_symbol_level = 2`，注释原文
  *"We want the best debug info we can get for in-the-wild crashes."*
  （`build/config/compiler/compiler.gni:130-132`）。
- **关键事实**：Windows 上符号是**分离的 PDB**（同文件 `:144-147`："Mac and Windows have them
  separate"）。所以 `symbol_level=2` **不增加发布体积、不影响运行时性能**，只增加构建时间与
  磁盘。官方 Chrome 正是"全符号构建 + 只发二进制 + PDB 上传崩溃服务器"。
- 设 0 的后果：`config("no_symbols")`（`build/config/compiler/BUILD.gn:3137-3146`）的 Windows
  分支只留 ldflags `/DEBUG`（`:3139`），编译器**不加 `/Z7`**（对比 `config("symbols")`
  `:2892-2896`）⇒ .obj 无 CodeView 信息 ⇒ PDB 无行号/类型；且 `HAS_SYMBOLS=false`
  （`:3257-3261`）。外部崩溃 minidump 只能到 `module+offset`，
  **注入的 LOADER 若在用户机出问题完全无法归因**。旁证：`base/BUILD.gn:3008-3011` 有
  `assert(symbol_level > 0)` 绑定"栈行号"。
- **为何不擅自改**：全符号会显著增加构建时间与磁盘（chrome.dll 的 PDB 可达数 GB），
  而本仓已多次记录"全树重编约 3 小时"之痛（D74）。这是成本/收益取舍，属用户决策。
- **建议**：折中用 `symbol_level = 1`（函数级符号，足够定位到函数名，成本远低于 2），
  或维持 0 但**另建一份 `symbol_level=2` 的符号构建**只用于崩溃归因、不发布。

#### [D148] `exclude_unwind_tables = true`（:31）在 Windows 上双重无效
- **严重度**：Low（误导性配置）　**状态**：未改
- ① 它本来就已默认为 true：`build/config/compiler/compiler.gni:219-220` =
  `(is_official_build && !is_android) || is_cronet_for_aosp_build`；
  ② 其唯一 cflags 使用点 `BUILD.gn:505-510` 位于 `if ((is_posix && !is_apple) || is_fuchsia)`
  （`:476`）内，**Windows 走不到**。
- Win x64 的 `.pdata`/`RUNTIME_FUNCTION` 是 ABI 强制项，不受这两个 flag 影响 ⇒
  栈回溯机制本身没被削弱；让栈"没用"的只有 `symbol_level=0`（见 D147）。
- 建议：删除该行或加注说明其在 Windows 上无作用，避免读者以为它在省体积/提速。

#### [D149] 24 核机器上 raster 线程被钳到 4 —— 多核心利用最明显的浪费点
- **严重度**：Medium（性能机会，非缺陷）　**状态**：未改，需源码注入
- `content/browser/gpu/compositor_util.cc:405-438 NumberOfRendererRasterThreads()` =
  `clamp(cores/2, kMinRasterThreads=1, kMaxRasterThreads=4)`（常量在 `:49-50`）
  ⇒ 本机 24/2=12 **被钳到 4**。browser 经 `render_process_host_impl.cc:3728-3731` 下发给每个
  renderer，消费者 `cc/raster/categorized_worker_pool.cc:426-438`（缺 switch 会 CHECK）。
- **命令行 `--num-raster-threads`（`cc/base/switches.cc:55`）写大于 4 无效**，因为钳制发生在
  browser 侧下发之前。要突破只能改源码常量——本仓的既定机制是写
  `win_scripts/apply_*.py` 幂等注入脚本（D41 约定），不是加覆盖文件。
- 属"有收益但需重编译 + 需 A/B"的改动，且与 ADR-002（性能优先）方向一致，建议排期。

#### 正面确认（无需动作）
- `init_stack_vars_zero = true`(:42)：**no-op 但方向正确**。声明
  `build/config/compiler/BUILD.gn:153` = `is_official_build && !dcheck_always_on` ⇒ 本配置已 true；
  实际 `-ftrivial-auto-var-init=zero` 已在 `out/mcloud/toolchain.ninja` 中实测到。
  注意上游 `:145-151` 明说权衡：zero 消除可利用性但丢掉 `pattern` 的毒值信号。
- `win_enable_cfg_guards = true`(:71)：**同为 no-op，且已实测生效**。声明
  `build/config/win/control_flow_guard.gni:10` = `!is_debug && !is_asan` ⇒ 已 true；
  链接侧 `win/BUILD.gn:381-393` 只看 `!is_debug && !is_asan`、**不看这个参数**。
  实测 `toolchain.ninja` 有 `/guard$:cf`、`disable_guards_cfg_compiler` 命中 **0**。
- **PartitionAlloc 全套处于安全侧默认**（未显式设置即为最优）：
  `use_partition_alloc_as_malloc=true`（PA-E 开，`build_overrides/partition_alloc.gni:103-104`）、
  `enable_backup_ref_ptr_support=true`（BRP/raw_ptr 开，`:106`）、
  `_disable_partition_alloc_everywhere=false`（`:71-72`）。
  `enable_dangling_raw_ptr_checks` 含 `!is_official_build` ⇒ 本配置 false，
  与上游 `partition_alloc.gni:113` 的建议一致，**不建议改**。
- `enable_site_isolation` 在 M155 **已不存在**（全树 `*.gn/*.gni` 0 命中），运行时由
  `switches::kSitePerProcess`（`content/public/common/content_switches.cc:681`）控制。仓库不设是对的。
- **硬件级抗 ROP 已开启**：`enable_cet_shadow_stack = target_cpu=="x64"`
  （`compiler.gni:230`，使用点 `BUILD.gn:3264-3265`）⇒ true。
- **libc++ 加固为 EXTENSIVE 档**：`use_safe_libcxx = use_custom_libcxx && enable_safe_libcxx`
  （`build/config/c++.gni:116`，两个前置均 true）⇒
  `_LIBCPP_HARDENING_MODE_EXTENSIVE`（`BUILD.gn:1757-1758`），已在 toolchain.ninja 实测到该 define。

---

### 加载器 C++ 内存安全审查（`win_scripts/inject_flags_loader.py` 的 LOADER 常量）

**结论：未发现越界 / UAF / 泄漏 / 未初始化 / 竞态。** 这是本仓库唯一进入浏览器进程的自有 C++，
逐行核验结果如下（行号按 `inject_flags_loader.py`）：

| 核验点 | 证据 |
|---|---|
| 无固定长度缓冲区、无裸 `new`/`delete` | 全程 `std::string` / `string_view` / `vector` |
| 无悬垂 `string_view` | `:237-239` range-for 的 range-initializer 临时 vector 生命周期延长至循环末；`contents` 循环内未被修改 |
| `substr` 无越界 | `:244` `StartsWith("--")` 保证 size≥2；`:250` 前 2 字节是 `-`，故 `find('=')` 只可能 ≥2 ⇒ `equals-2≥0`、`equals+1≤size()`；`:259` 引号剥离有 size≥2 前置 |
| 超大文件 / 部分读 | `base/files/file_util.cc:375-389` 先 clear；`:328-346` 超 1 MiB 时**仍 swap 入已读字节并返回 false** ⇒ LOADER 在 `:203/:208` 显式 `contents.clear()`、`:212` 直接 return，**不消费截断内容**（正确但不显然：删掉那两个 clear 就会解析半个文件） |
| BOM / CRLF | `:219-224` 有 size≥3 前置；`TRIM_WHITESPACE` 剥 `\r`，CRLF 正常 |
| 时序 / 线程 | 调用点 `chrome_main_delegate.cc:1368-1372`（函数首行），由 `content_main_runner_impl.cc:963-964` 在**主线程**调用；`BrowserTaskExecutor::Create()` 在同文件约 1299 行之后 ⇒ 此刻仅主线程，**无竞态**。D58 守卫（`:166-168`）令子进程早退。浏览器进程无沙箱 |
| 开关追加顺序 | `BasicStartupComplete`(964) → `PreSandboxStartup`(1062) → `chrome_main_delegate.cc:1138 CreateFeatureList` ⇒ 追加的 `--enable-features` 必被 FeatureList 读到。`AppendSwitchNative`（`base/command_line.cc:454`）对已存在 key 是**覆盖**，故 merge 不会产生重复开关 |
| sequence checker | `base/command_line.cc:438-440` 的 `sequence_checker_` 由 `enable_commandline_sequence_checks` 控制，`base/BUILD.gn:3005-3006` = `(is_debug\|\|dcheck_always_on)&&!is_android` ⇒ 本配置 **false**，已编译掉 |
| M155 API 漂移 | 全部对得上，**无 D41 类风险**：`ReadFileToStringWithMaxSize`(`file_util.h:276`)、`SplitStringPiece`(`string_split.h:118`)、`StartsWith`(`string_util.h:375`)、`AppendSwitchASCII`/`HasSwitch`/`GetSwitchValueASCII`(`command_line.h:217/198/204`)、`FileEnumerator`(`file_enumerator.h:186`)、`explicit Version(string_view)`(`version.h:36`)+free `operator>`(`:74`)、`DIR_MODULE=DirName(FILE_MODULE)`(`base_paths.cc:68-73`)、`FILE_MODULE=GetModuleFileName(CURRENT_MODULE())`(`base_paths_win.cc:43-50`) |
| 树内已注入块 vs 仓库 LOADER | 本轮改动前**仅 4 行注释文字不同、代码逐字节一致**（下次 deploy 自动改写，非缺陷） |

**记录在案的低severity项**：
- **A1** CR-only 文件（无 `\n`）→ 整份成一行且不以 `--` 开头 ⇒ **全文静默丢弃**（`:237`）。
- **A2** 内嵌 NUL 字节未过滤，会造出畸形开关名/值追加到命令行。
- **A3** `builtin_enable/disable` 在循环内**无预算**累积（`:269-278`），预算只在 merge 时检查
  （`:316`）⇒ 最坏瞬时约 3 MiB 后释放，属"先建后拒"，**非泄漏**。
- **A5** 注入器断言 `content/public/common/content_switches.h` 并注释
  "kEnableFeatures/kDisableFeatures 来自 content_switches"（`:381-383`）。实测 M155：二者在
  **`base/base_switches.h:18,30`**（`inline constexpr char[]`），`content_switches.h` 只有
  `kProcessType`(`:167`)。真正被依赖的 `base_switches.h`（树内 `chrome_main_delegate.cc:108`）
  **未被断言** ⇒ 上游若删它，注入会"成功"而编译失败。

---

### 环境 / 使用面观察（非仓库代码缺陷，但影响用户维度）

#### [D150] 本机超线程在 BIOS 中关闭（24 核 / 24 线程）
i9-14900HX 规格为 24C/32T，三路 API 一致报 24 ⇒ HT 关闭。这是**用户可操作的"多核心优化"
最大单点**：开启后可多出 8 个逻辑处理器（+33%）。注意它会同时改变
`base::ThreadPool` 的前台 worker 上限（见下）与所有 CPU 类 KPI 的可比性，
故**开启后必须重采基线**，不能与既有数据直接比较。已在 `run_baseline.ps1` 的环境块新增
"逻辑处理器 / 物理核"一行并注明此影响。

#### [D151] ThreadPool 前台 worker 上限 = 23/进程，聚合远超 24 核
`base/task/thread_pool/thread_pool_instance.cc:93-95` =
`max(3, SysInfo::NumberOfProcessors()-1)` ⇒ 本机 **23**，且 browser / GPU / 每个 renderer
**各一份**。无命令行开关、无 feature 可调该上限
（`base/task/thread_pool/initialization_util.cc:15-23` 的
`RecommendedMaxNumberOfThreadsInThreadGroup` 不被 ThreadPool 路径使用）。
它是**上限而非目标**（worker 惰性创建），不会静态超额订阅，但聚合上限远超物理核数 ⇒
高负载下为抢占型超额订阅。renderer 侧另有 `content/common/thread_pool_util.cc:13-17` =
`max(1, cores-1)` = 23（**最小**前台线程）。
可试的 feature（名字已在 `base/task/task_features.cc` 核实）：
`UseHighPriorityThreadGroup`(:27 DISABLED)、`ThreadPoolForegroundBlockingTimeouts`(:53 DISABLED，
参数 `:56-65` MayBlockThreshold=1000 ms / BlockedWorkersPoll=1200 ms)、
`UseUtilityThreadGroup`(:25)、`InheritTaskImportanceByDefault`(:67)、`AlignWakeUps`(:42)。
**已默认启用故声明无效**：`RunTasksByBatches`(:46，Win/Mac/CrOS 已 ENABLED)、
`AddTaskLeewayFeature`(:29)、`JobPriorityBoosting`
（`base/task/thread_pool/job_task_source.cc:32`）。

#### [D152] renderer 进程数上限 = 82，与本机 32 GB 内存无关
`content/public/common/content_switches.cc:629 kRendererProcessLimit`，读取点
`content/browser/browser_main_loop.cc:607-613`。默认算法 `render_process_host_impl.cc:1504-1578`：
`AmountOfTotalPhysicalMemory().InMiB()/2 / 85`（`kEstimatedWebContentsMemoryUsage=85`，64 位，
`:1558-1563`）后 `clamp(_, 3, GetPlatformMaxRendererProcessCount())`；而
`GetPlatformProcessLimit()` 在 **Windows 直接返回 0**（`:1202-1215`，仅 Linux/ChromeOS 实现），
故落到 fallback 常量 **82**（`:1485-1495`）。本机 32 GB → 16384/85≈192 → 钳到 82。

#### [D153] CPU 性能分档：本机命中最高档
`content/browser/cpu_performance/cpu_performance.cc:225-236 GetTierFromCores()`：
**≥13 核 = `Tier::kUltra`**，经 `render_process_host_impl.cc:2020-2029` 下发 renderer。
其余按核数缩放处：`compositor_util.cc:514`（`cores<4` 分支）、
`indexed_db_context_impl.cc:1220`、`media/base/video_decoder.cc:51` /
`video_encoder.cc:73`（`min(desired, cores)`）、`gpu/ipc/service/gpu_watchdog_thread.cc:69,681`。
**未找到**任何以"大核数"为条件的锁竞争 / work-stealing / 调度调优开关
（Windows 侧唯一的锁自旋就是 D142 里那条 POSIX-only 的）。

#### [D154] 悬空的 GPU 首选项条目指向已删除的安装
`HKCU\Software\Microsoft\DirectX\UserGpuPreferences` 中
`C:\Users\Administrator\AppData\Local\Chromium\Application\chrome.exe = GpuPreference=1`
（**1 = 省电 = 优先集显**），而该路径的 chrome.exe **已不存在**
（`Application\` 下只剩一个空的 `155.0.8059.40\` 目录，是测试残留）。
同键下还有 `QQ.exe`/`wegame.exe`/`QQLive*` 等一批 `GpuPreference=1`，以及
`yysls.exe = GpuPreference=2`（高性能）、全局 `SwapEffectUpgradeEnable=1`。
- **风险**：若将来把浏览器装回该用户级路径，它会**被 Windows 钉在 Intel 核显**上——
  而核显正是 D3D12 绿屏缺陷那一侧；同时所有既有 GPU 基准都是在**无该条目的开发树产物**上
  测的（实测走独显），两者不可比。
- 当前真实安装在 `C:\Program Files\Chromium\Application`（**无**该条目），实测走独显，无影响。
- 建议：清掉这条悬空条目；若将来做用户级安装，装完顺手核对/设置该键为 `GpuPreference=2`。

#### [D155] `enable_vulkan=false` 但 Vulkan 校验层 DLL 仍被构建
`out/mcloud/` 下有 `VkICD_mock_icd.dll`(673,792 B) 与
`VkLayer_khronos_validation.dll`(20,305,408 B)。按 ADR-002 体积不作约束，故仅为观察项；
但需确认它们**没有被打进安装包**（约 21 MB 死重）。

#### 安装面实测状态（本轮核对，全部通过）
| 检查项 | 结果 |
|---|---|
| 真实安装位置 | `C:\Program Files\Chromium\Application`，`chrome.exe` FileVersion = **155.0.8059.40** |
| flags 投递位置 | `Application\155.0.8059.40\mcloud_flags.txt` **存在**（D105 修复生效） |
| 根目录遮蔽残留 | `Application\mcloud_flags.txt` **不存在**，`.bak-*`/`.stale-*` 也无（D109 遮蔽源已清） |
| 与仓库字节一致 | SHA256 `61b7670856ed581ca26b669aea1c804ac6412fe658592dfc8b07aaa03920e742` 双方一致（改动前口径） |
| 安装后二进制运行期回显 | `enable 51 / disable 2`，`InitialWebUI` 走 trial 通道，`SingleAxisScrollContainers` 为上游默认 trial，普通开关 0 缺失，**exit 0** |
| 用户级安装残留 | `AppData\Local\Chromium\Application\155.0.8059.40\` 为**空目录**（测试残留，非产品缺陷） |

---

## 本轮已执行的验证（证据）

| 验证 | 命令 | 结果 |
|---|---|---|
| 源码门禁 | `python win_scripts/verify_sources.py` | **PASS / exit 0**：Python 18 文件、关键脚本 11/11、pak_src 14/14、PowerShell 静态 lint **45** 个 `.ps1`（BOM + param 位置）、AST 解析 **45** 个全绿 |
| flags 跨版本稳定性 | `python .bugreview/flag_stability.py` | **PASS / exit 0**：A 基线53→当前51、B 移除 2 项且确认净行为为 0、C r3 项目 51/51 存活、D 普通开关三版都在、E params 成对校验通过、F 冻结注释未触发 |
| 运行期回显（安装后二进制） | `flag_runtime_state.py --chrome "C:\Program Files\Chromium\Application\chrome.exe"` | **exit 0**，`enable 51 / disable 2`（改动前） |
| 运行期回显（部署新 flags 后） | `flag_runtime_state.py --chrome …chromium-src-155…\chrome.exe` | **exit 0**，`enable 49 / disable 2`，SHA 与仓库一致 |
| C# 编译 | `python win_scripts/build_setup_exe.py --console --out .cycle5/MCloud-Setup-verify.exe` | **OK**，Roslyn `/deterministic+`，26,112 B，无警告 |
| 安装器 `--list-only` 实跑 | `.cycle5/MCloud-Setup-verify.exe --list-only --quiet` | **exit 0**，正确识别 `C:\Program Files\Chromium\Application（only-system-level）`、声明"就地更新不换位置"、"没有本产品实例" |
| PGO 预检 Red→Green | `python .bugreview/test_build_win_preflight.py` | **PASS / exit 0**：Green `PGO 预检 OK 484 MB` + `漂移比对 OK 逐项一致`；Red rc=111 且未继续；Red2 精确报出漂移项 |
| K2/K2-CPU Red→Green | `powershell -File benchmark/bench_memory.ps1 -Tabs 6 -SettleSeconds 10 -Samples 3 -SampleInterval 4` | Green **exit 0**，内存 679.4 MB / CPU 中位 0.06% 整机、0.02 核；Red（注入 100 倍错误）**exit 1**，自洽断言报"差 7.84" |
| 正则护栏 Red→Green | `python .bugreview/test_d137_guard.py` | **PASS / exit 0**：Green（无探针）门禁 PASS；Red（放入含坏写法的临时 `.ps1`）门禁 FAIL 且指名该文件与 D137；探针已删、`benchmark/` 零改动。另用一次性 `.cycle5/regex_test.ps1` 直接对比过两种正则：旧写法两树皆 False，新写法 M151=True / M155=False |
| LOADER C++ 粗检 | `python .bugreview/check_loader_syntax.py` | **PASS / exit 0**：`{}` 32/32、`()` 104/104、`[]` 5/5 平衡；D146 新增行存在且未用 `.value()`（Windows 上 `FilePath::StringType` 是 `std::wstring`，改为直接流 `FilePath`，依据 `base/files/file_path.h:553-554` 的 `operator<<`，经 `base/files/file_util.h:25` 可达）。**注意这只是粗检，不等于编译通过**；另已核实该 TU 内既有 4 处 `LOG(WARNING)` 且 r5 编译成功，故宏可用 |
| GPU 四路取证 | `python .bugreview/gpu_identity_probe.py` | 独显渲染确认、AV1/HEVC/VP9/H264 硬解确认、清理残留 0；两处 FAIL 是探针段落名需按 M155 校准（量具问题，非产品问题） |
| ruff（AGENTS.md 选择器） | `python -m ruff check --select F,E9,B,SIM win_scripts benchmark .bugreview` | 全仓 127 项均为**既存**风格问题（100 SIM115、18 F541、7 SIM105、1 SIM102、1 SIM212），**无 B 类真阳性**；本轮改过的 `build_win.py`/`gpu_probe.py` **零错误**（`inject_flags_loader.py` 的 3 项 SIM115 经与 HEAD 版本对比确认为既存 backlog） |

**本轮新增并已入库的判据脚本**（放 `.bugreview/`，因为 `.gitignore` 的规则是
`.bugreview/*` + `!.bugreview/*.py`——**脚本入库、数据与日志不入库**。这与 `a291812`
"把取证脚本从 gitignore 的证据目录提到 .bugreview，消除悬空引用"是同一条纪律：
本报告大量按路径引用它们，若只存在于本机工作树，接手方干净检出后一条判据都复现不了）：
`gpu_identity_probe.py`（GPU 身份与硬解能力四路取证）、
`test_build_win_preflight.py`（D144 的 Red→Green）、
`check_loader_syntax.py`（LOADER C++ 粗检）、
`test_d137_guard.py`（D137 回归闸的 Red→Green）。

**留在 `.cycle5/`（整目录 gitignore，同 `.cycle4/` 约定）的一次性材料与证据**：
`regex_test.ps1`（两种正则的直接对比，结论已抄进上表）、`MCloud-Setup-verify.exe`
（仅用于验证编译的产物，发布物需另行重打包）、`gpu_identity_result.json`、
`gpu_page_full.txt`（chrome://gpu 全文 79,428 B）、`gpu_probe_launch.log`。
其中 json/txt/log 重跑 `.bugreview/gpu_identity_probe.py` 即可再生（会写到 `.bugreview/` 下，
同样不入库）。

---

## 残余风险与待跟进

### 需要重新编译才能生效的改动
| 改动 | 生效条件 |
|---|---|
| D146 加载器补日志 | `deploy_mcloud.py` + 重编译（注入器为"正文比对式升级器"，下次 deploy 自动改写树内正文，D62/D64/D67） |
| D149 raster 线程钳制 | 需新增 `win_scripts/apply_*.py` 幂等注入脚本改 `compositor_util.cc` 常量 + 重编译 + A/B |
| D147/D148 symbol_level | 改 args.gn 后 `gn gen --check` + **全树重编**（注意 D74：config 正文改动即 51,296 步 ≈3 h） |

### 需要重新打包/安装才能生效
| 改动 | 生效条件 |
|---|---|
| D121–D129 安装器修复 | 已编译验证通过，但**发布物 `installer/out/*.exe` 与 `mcloud_155.0.8059.40_win64_setup.exe` 仍是旧版**，需重跑 `build_setup_exe.py` + `package_m155.py` 重新内嵌并生成 `.sha256` |
| D142 flags 清理 | 已部署到 `out/mcloud` 并验证回显；要进安装包需重新打包 |

### 本轮未做（明确列出，避免"看起来已完成"）
1. **未做干净安装复验**。AGENTS.md 要求发布前用 `mini_installer.exe --system-level` 装到
   Program Files、断言文件落地 + 字节一致 + 跑 `flag_runtime_state.py` 得 51+2（本轮改动后应为
   **49+2**）再卸载。该操作会改动用户机器上的真实安装，**需用户授权**。
   同时 `setup_wrapper_test.py` 应补一条**不带 `--system-level`** 的用户级用例——否则 D121
   这一类"唯一被验收的分支恰好是碰对的那个"会再次发生。
2. **未跑 `final_gate_matrix.ps1` 九门收口矩阵**。本轮只跑了其中受影响的
   `verify_sources` / `flag_stability` / `flag_runtime_state` 三门。
3. **未跑 `r1..r4` 四条实操探针**（它们本就尚未接入 `final_gate_matrix.ps1`，第4周期遗留项）。
4. **集显侧未做渲染实测**。本轮确认了独显渲染路径与硬解能力，但 Intel 核显侧只跑了
   静态识别；`benchmark/tools/diag_igpu_green_screen.ps1` 的 T1–T4 二分**至今无缺陷编号、
   无本轮复验记录**（第4周期已记为空白）。由于显示器由独显驱动、核显不驱动显示，
   要测核显需显式切换（Windows 图形首选项或 `--use-angle`/GPU 偏好），属独立一轮。
5. **`SkiaGraphite` 的 A/B 仍未做**。`mcloud_flags.txt:117-119` 自己写着"该项与 GPU 效率存在
   张力，升级后须做一次同方法 A/B"。它属 2026-10-08 窗口拖拽冻结缓解的 4 项**永久禁用**组，
   **即使测出收益也不得自动恢复**（见项目记忆 `mcloud-window-freeze-mitigation.md`）。
6. **`check_features.py` / `flag_stability.py` 的平台守卫盲区未修**（D142 的系统性根因）。
   建议：让 `survival_check.py` 采集声明点时**向上扫描最近的 `#if` 守卫**并记录
   `BUILDFLAG(IS_*)` / `PA_BUILDFLAG(*)` 条件，再由 `flag_stability.py` 对
   `target_os="win"` 判可行性；同时把已采集但从未被读取的 `default` 字段接进 C 断言，
   让"上游默认已启用"的 pin 被显式标注而不是算作收益。
7. **CPU 量具只覆盖驻留态**（挂在 K2 上）。冷启动峰值 CPU、导航期 CPU 仍无采集；
   若要回答"运行效率/CPU 占用"的完整问题，需把同一套按-PID-做差的采集挂到
   `bench_startup.ps1` 与 `r4_memory_stability_check.py:38-52 proc_stats()`（后者已每 10 s
   采本实例每进程指标，WMI 同一行即可带出 `KernelModeTime`/`UserModeTime`）。
8. **`.qoder/repowiki/` 与 `docs/repowiki/` 里的错误 GPU 型号未改**（生成物，
   `性能优化.md:299` 仍写"独显（GTX 1050 Ti）"）。宜随下次 wiki 重生成修正，不手改。
9. **`docs/dev-logs/M155-benchmark.md:17` 的错误 GPU 行未改**——它是**已归档的历史基线**，
   本轮选择保留原样并在本报告 D139 表格中列明，而不是回改历史数据。
   下次重采基线时会自动带上正确的 PCI 设备号。

### 上游事实（供后续判断，非本仓缺陷）
- M155 `setup.exe` **无进度 UI**（`ProgressCalculator::Calculate()` 除单测无消费者）、无静默开关；
  上游安装/卸载器**不杀浏览器进程**（`setup_main.cc:1773`、`setup_util.cc:186` 只终止自己）。
- `task_group_sampler.cc:125` 用 `.value_or(0.0)` 把 CPU 采集失败吞成 0 ——
  **本仓自制量具不得照抄这个模式**（已写进 `bench_memory.ps1` 的注释）。
- `content_features.cc:1544` 的注释写 "kInteractive" 与代码（`:1545` 实际是
  `kPresentation→kAudioProcessing`）不符，属上游注释陈旧。

---

## 修复文件清单

| 文件 | 改动 | 对应缺陷 |
|---|---|---|
| `installer/mcloud_setup.cs` | 7 处：条件传 level、`irect` 参与判定、提权等待并透传 rc、降权重启浏览器、默认浏览器整条丢失判回归、`Alive()` 异常按存活、`Version` 比较、补 CommonStartMenu | D121 D122 D123 D124 D125 D127 D128 D129 |
| `win_args_mcloud.gn` | `pgo_data_path` 指回 155 树 + 源码级依据注释 | D144 |
| `win_scripts/build_win.py` | 新增 `read_args_gn()` / `preflight_args()`：PGO 剖面存在性硬校验 + 模板/构建树漂移比对 | D144 |
| `win_scripts/inject_flags_loader.py` | LOADER 三级候选全失败处补 `LOG(WARNING)` 并记录"logging 此时尚未初始化"的局限 | D146 |
| `win_scripts/verify_sources.py` | `check_powershell_static()` 新增 D137 回归闸（非注释行出现坏正则即 FAIL）；`collect_powershell_files()` 跳过 `.cycle*` 一次性取证目录 | D137 |
| `.bugreview/test_d137_guard.py`（新） | D137 回归闸的 Red→Green 判据；只增删临时探针，**不改写任何已跟踪文件** | D137 |
| `.bugreview/test_build_win_preflight.py`（新） | PGO 预检与漂移比对的 Red→Green 判据 | D144 |
| `.bugreview/gpu_identity_probe.py`（新） | GPU 身份与硬解能力四路取证（主机 PCI/nvidia-smi + chrome://gpu + MediaCapabilities + WebGL + 子进程命令行） | D143 D154 |
| `.bugreview/check_loader_syntax.py`（新） | LOADER C++ 正文粗检（括号平衡 / LOG 收尾 / 未用 `.value()`） | D146 |
| `mcloud_flags.txt` | 删 2 条平台不可能生效的声明、为 2 条默认已启用的 pin 加注、更正独显身份与 D118 结论 | D142 D143 |
| `benchmark/bench_memory.ps1` | 三处硬失败 + 采样条数自检 + `exit 0`、指纹改叶子名、新增 K2-CPU 采集与单位自洽断言、修正 `-f`/`+` 优先级、修正 M151 护栏正则 | D137 D138 D145 |
| `benchmark/run_baseline.ps1` | GPU 只认 PCI 适配器并输出 VEN:DEV/是否驱动显示、排除虚拟适配器、新增逻辑处理器行、识别不到真实显卡即 `throw`、修正护栏正则 ×2 | D137 D139 |
| `benchmark/bench_startup.ps1`、`bench_navigation.ps1`、`bench_size.ps1`、`tools/bolt_pipeline.ps1`、`tools/diag_igpu_green_screen.ps1`、`tools/pgo_collect.ps1`、`tools/verify_builtin_flags.ps1` | 修正 M151 护栏正则 | D137 |
| `benchmark/tools/gpu_probe.py` | 清理复检指纹统一为叶子名、`--chrome` 与双树对比改走 `MCHROME_EXE`、产物缺失打 SKIP | D140 D141 |
| `AGENTS.md` | flags 口径 54/51/3 + D142 缘由 + pin 提示 | D142 |
| `docs/tasks/bug-review-cycle4-report.md` | D118 的 AV1 结论更正（保留删除线，不抹历史） | D143 |
| `docs/tasks/bug-review-pak-src-defects.md` | D118 行更正 | D143 |
| `.gitignore` | 新增 `.cycle5/` | — |

---

## 续：r6 收口轮执行记录（接手方 Qoder 侧，2026-10-12 01:30–02:30）

上面那份报告是交接件。本节只写**我实际执行过、且有输出可查**的动作（含 §7 的破坏性复验）；复核意见与新增编号在前，
便于回审时逐条对表。所有实测都是在真机上跑的命令，不是对报告的转述。

### 0. 对上面报告的复核

独立确认（重跑或重读源码，不采信文字）：

| 条目 | 我的复核方式 | 结果 |
|---|---|---|
| D121 | `git show 68838c1:installer/mcloud_setup.cs` 第 613 行 vs HEAD 第 693 行 | 成立，且是**我上一轮写下的**缺陷 |
| D123 / D124 / D125 / D127 / D128 / D122 / D129 | 逐条读 `git diff 68838c1..HEAD -- installer/mcloud_setup.cs` | 修法成立。D127 那句"字符串比较对 a.b.c.d 够用"的原注释是我的，判错无误 |
| D137 | 实跑 `.bugreview/test_d137_guard.py` | VERDICT: PASS（Green rc=0 / Red rc=1 指名探针 / 探针自删、`benchmark/` 零改动） |
| D138 / D145 | 读 `bench_memory.ps1` diff | 三处 `throw` + 条数自检 + 单位自洽断言齐备 |
| D139 | 读 `run_baseline.ps1` diff，并**特意核 `throw` 的位置** | 第 107 行的硬失败发生在第 143 行起浏览器**之前** ⇒ 中止不会留下锁 DLL 的实例（D71 类风险，报告未提，我确认安全） |
| D140 / D141 | 读 `gpu_probe.py` diff | 复检指纹统一为叶子名、`MCHROME_EXE` 落实（`check_features.py`/`r1` 他自己标了待跟进） |
| D142 | 自己重数仓库 flags | 54 活动行 = 51 feature 项 + 3 普通开关；enable **49** / disable **2**，逐项吻合 |
| D143 | `nvidia-smi` + PCI 枚举 | 成立，且**推翻的是我今天对你说的话**（我曾说 AV1 `powerEfficient` 只证明被选中） |
| D144 | 比对 `win_args_mcloud.gn:65` 与 `out/mcloud/args.gn:57`；实跑预检测试 | 已对齐，PASS（我先前报它失败是**我自己加了 `-X utf8`**） |
| D146 | 额外验了他没验的可编译性：`base/files/file_path.h:553` 的 `operator<<` 是**非模板** `std::ostream&`，该头文件只 include `<iosfwd>`，但 `base/logging.h` include `<sstream>` 带进完整 `<ostream>`；`module_dir`/`exe_dir` 在插入点确在作用域内 | 编译安全（仍不等于已重编，见 §5） |
| 安装器 GUI 形态 | 实编 `/target:winexe`（他只编了 console 形态） | Roslyn `/deterministic+`，26,112 B，无警告；临时产物已删 |
| 正面确认（LOADER 内存安全、PartitionAlloc/CET/libcxx 档位、A5） | 抽读源码依据 | 同意，未动作 |

需要打折的四处，登记为新编号（见 §1）。

### 1. 本轮登记的缺陷（D156–D161）

| ID | 级别 | 位置 | 问题 | 状态 |
|---|---|---|---|---|
| D156 | Low | 本报告「本轮已执行的验证」表 | 表中"PowerShell 静态 lint **45** 个 `.ps1`"与现状差一个：现实跑是 **44**，差的就是 `.cycle5/regex_test.ps1`。那一栏是**加了 `.cycle` 跳过之前**那一次运行的计数——即失败的那次被记成了结论。结论没错，数字来自旧一次运行 | 已在此节更正 |
| D157 | **High** | 本报告「摘要」的"14 条已修复并验证" | D121–D129 这 7 条安装器修复**一条都没有被真实执行过**：验证表里与安装器有关的只有两行——编译（还只是 console 形态）和 `--list-only` 实跑。用户级安装、提权 rc 透传、降权重启、`Alive()` 异常路径全部零执行。**这与 D121 本身的病因同构**（改了分支却没配可执行验收），报告批评了前者却没自查后者 | **已修**：`installer_arg_test.py` 的 A / A' / B / C 四条 12/12 PASS（见 §3）。仍剩 `RelaunchElevated`（需非提权父进程）与 D123 的降权重启（需真实安装成功）两支，属 §5 第 1 项 |
| D158 | Medium | `mcloud_setup.cs:539-565`（D122 的修法） | 非提权父进程读**提权子进程**的 `ExitCode`，跨完整性级别时常常取不到；他的实现取不到就 `return ELEV_RC_UNAVAILABLE` → 主流程 `return 2` 并打印"按失败上报"。方向符合本仓"宁假红不假绿"，但**后果是系统级安装即使成功也可能对用户报失败、返回 2**，脚本/CI 会据此判红。必须真机跑一次系统级安装确认到底走哪一支，并把 rc 语义写进指引（2 = 未能判定 ≠ 没装上） | 未修，属 §5 那一步的输出 |
| D159 | Medium | `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` × D121 | D154 被记为"环境观察"，但它与 D121 是**同一件事的前后两半**：D121 修好后，用户级安装路径**第一次真正可用**，而该路径正对着一条 `GpuPreference=1`（= 优先**核显**）。本轮实测：条目仍在，目标 `C:\Users\Administrator\AppData\Local\Chromium\Application\chrome.exe` **不存在**，`Application\155.0.8059.40\` 是个空壳残留。⇒ 清掉悬空条目（或用户级装完核对为 `GpuPreference=2`）应作为 **D121 的收尾步骤**，而不是独立观察项 | 已据此改判据设计（见 §2 步骤 3） |
| D160 | Low | D133 的定性 | 发布形态 `/target:winexe` 的 `--list-only` **并非完全哑**：stdout 被重定向时能读到正文（本轮实测 149 B："检测到已安装副本：C:\Program Files\Chromium\Application（only-system-level）… 就地更新这一份，不换位置"）。所以它对脚本/CI 可用，**只有双击的用户看不到** ⇒ 严重度下调，修法应聚焦"双击时把日志写文件"，而不是"输出丢了" | 已在 AGENTS.md 更正口径 |
| D161 | Medium | `setup_wrapper_test.py:63` 默认 `WRAPPER` × `package_m155.py` | 端到端验收的**默认被测对象** `installer/out/MCloud-Setup-embedded.exe` 在全仓库**没有任何脚本生产它**（唯一的引用就是那条 help 文本）。实测第5周期重打包后它的 mtime 仍停在上一日 22:42 ⇒ "跑验收"实际跑的是**内嵌旧载荷**的包装器，结论与发布物不是同一个东西。属 D86/D72 同族：产物归属不能靠人记得手动重建 | 已修：并入 `package_m155.py` 同批产出并打印其 SHA |

另有一条只在 AGENTS.md 立约定、不占缺陷编号（因为仓库里没有对应既存代码，是我这轮写临时脚本时踩的）：
`subprocess.run(..., errors="replace")` 会**隐式打开文本模式**（CPython 中 `encoding`/`errors`/`text`
任一给定即 `text_mode=True`），想要字节就不能传；打印超出 cp936 的字符（如 `⇒`）会抛
`UnicodeEncodeError` 且**缓冲中的日志整段丢失**；PowerShell 的 `Where-Object` 只命中一条时返回标量，
`$names[0]` 取到的是第一个字符 —— 这三条已写进 AGENTS.md「Python 判据脚本三条语言坑」。

### 2. 已执行的操作（按序，含实测输出）

1. **对齐状态取证**（不采信"发布物可能是旧的"这种推测）：
   源码 mtime `mcloud_setup.cs 00:19` / `mcloud_flags.txt 00:27` / `win_args_mcloud.gn 00:29`，
   提交 `e08ba06 00:58`、`bf4e63f 01:05`；产物 `installer/out/*.exe 10-11 22:42–22:46`、
   根 setup `10-11 23:04`。flags 三处哈希：仓库 `d71d988ca2d2`、构建树 `d71d988ca2d2`、
   **已安装 `61b7670856ed`** ⇒ 落后确证。
2. **重打载荷**：先 `ninja -n -C out/mcloud mini_installer` 数过步数（**3 步**：
   `mini_installer_archive` → RC `packed_files.res` → `LINK mini_installer.exe`，
   不触发任何重编译，按 D74 纪律确认后才动手）；跑前实测 `out/mcloud` 下实例数 0（避免 D71 锁 DLL）。
   `autoninja` exit=0 → `chrome.7z` 445,012,281 B @01:43、`mini_installer.exe` 127,519,744 B @01:44，
   打包暂存目录（= 载荷真身）里的 `mcloud_flags.txt` 哈希 **`d71d988ca2d2`，与仓库一致**。
3. **补 D121/D129 的可执行验收**（新判据 `.bugreview/installer_arg_test.py`，见 §3）。
4. **修 D130**：`build_setup_exe.py` 找不到支持 `/deterministic` 的 Roslyn 时改为 exit 113
   并给出两种修法（新增 `--allow-nondeterministic` 仅供本机排错）；
   `package_m155.py` 改为无条件转印子编译器日志。
5. **修 D161**：`package_m155.py` 同批产出 `installer/out/MCloud-Setup-embedded.exe`（console + `--embed`）
   并打印其 SHA，让端到端验收的默认目标不可能再落在旧载荷上。
6. **发布说明模板更新**：`package_m155.py` 里的 notes 模板原写死"53 项 feature"、"回显 enable 51 / disable 2"
   —— 那是 D142 之前的口径，重新打包会把旧口径原样印回去。已改为 **51 项 feature + 3 项普通开关 /
   回显 49+2**，并新增「本包相对上一份 r5 包的差异（D121–D155）」整节（D121/D123/D124/D125/D122/D127/
   D128/D129/D142 逐条），历史哈希（r3/r4/r5）不回改。
7. **重打包**：`python .bugreview/package_m155.py` → 门禁全绿，产出见 §4。
8. **发布物装配校验**：从**发布出的 setup.exe** 里把内嵌清单资源取出来单独算哈希——
   `EMBED_SIZE=127519744 == RELEASE_SIZE`、`EMBED_SHA=488e604b… == RELEASE_SHA`、`MATCH=True`。
   （这是 D102 的正例做法：不看体积差、不在压缩归档里搜字节串，而是把载荷**还原出来称重**。）
9. **发布形态实跑** `mcloud_155.0.8059.40_win64_setup.exe --list-only`：rc=0、stdout 149 B、
   两个安装目录指纹前后逐项一致（系统级 262 条目、用户级 1 条目）⇒ 零副作用（D160 由此得出）。
10. **复现性实测**：连跑两次打包，两个发布物 SHA **逐字节不变**
    （`9600c425…` / `488e604b…`）⇒ Roslyn `/deterministic+` 这条链在真实发布管线上成立，
    不只是 `build_setup_exe.py` 的孤立实验。
11. **回归门禁重跑**：`verify_sources.py` PASS / exit 0（Python 18 文件、关键脚本 11/11、
    pak_src 14/14、`.ps1` 静态 lint **44** + AST 44 全绿）；`flag_stability.py` PASS / exit 0
    （A 基线 51、B 移除 0、C 51/51 存活、D/E/F 通过）。

### 3. 新判据 `installer_arg_test.py`：设计与实跑

**为什么不做成交接文档建议的那样**：给 `setup_wrapper_test.py` 补一条不带 `--system-level` 的用例，
会真的往 `%LOCALAPPDATA%\Chromium\Application` 装一份浏览器——而 D159 实测那条
`GpuPreference=1` 正埋伏在这个路径上，测试会把机器上的用户级安装钉在 Intel 核显上（核显 = D3D12 绿屏那一侧，
且与所有既有 GPU 基准不可比），收尾卸载又是一次真实安装变更。按 D99 纪律（测试不得污染被测目标）
改成**录参数**：D121 的缺陷面只是"传给 mini_installer 的参数"，所以用一个假安装包 stub 把收到的 argv
落到文件里，就能不碰任何安装位置而**真正执行到**那条分支。

实跑输出（本机，提权 = 是）：

| 用例 | 断言 | 结果 |
|---|---|---|
| A（HEAD + `--user-level`） | stub 收到**空参数**；包装器 rc≠0（用户目录本来没装东西，复验必须判不过） | PASS / PASS |
| A'（`68838c1` 那一版跑同一条） | stub 收到 `--system-level` | PASS —— **这条不成立，A 的通过就毫无意义** |
| B（stub 以 rc=3 退出） | 参数仍为空；日志出现"安装器自身返回 3"；包装器 rc=1 | PASS / PASS / PASS（D129 分支被真实触发） |
| C（`--system-level`） | stub 收到 `--system-level`；跑完 rc=0（stub 返回 0，且真实系统级目录的复验逐项通过） | 第一次跑 **SKIP**（`C:\Program Files\Chromium\Application` 下有 13 个正在运行的本产品实例，执行会先 `WM_CLOSE` 掉用户正在用的浏览器，D52/D55 禁止）；用户关闭浏览器后重跑 → **PASS / PASS** |
| 污染自检 ×4 | 用户级目录指纹、系统级目录指纹、实例数、残留 `MCloudSetup-*` 目录 | 4 项全 PASS |

两次运行的判据总览（完整日志：`.cycle5/r6_installer_arg_test.log`，gitignore 目录）：

| 运行 | 环境 | 断言 | 跳过 | 结论 |
|---|---|---|---|---|
| 第 1 次（01:50） | 提权=是，系统级实例=**13** | 10 / 10 成立 | 1（C） | **`VERDICT: PARTIAL` / exit 2** —— 系统级那一半没跑就不报全绿，不允许"两半通过"冒充结论 |
| 第 2 次（02:0x） | 提权=是，系统级实例=**0** | **12 / 12 成立** | 0 | **`VERDICT: PASS` / exit 0** —— D121 的用户级与系统级两条参数分支、D129 的判定分支**都被真实执行**，且未污染任何安装位置 |

⇒ **D157 的"7 条安装器修复一条都没执行过"就此收口**（A/A'/B/C 四条覆盖到用户级参数、Red 参照、
安装器返回码参与判定、系统级参数）。仍**没被覆盖**的只剩两支，都不是本判据能达到的：
① `RelaunchElevated` 这支需要**非提权父进程**（本机 shell 已提权，走的是内联路径）——
也正是 **D158 的假红风险所在**；② D123 的 `explorer.exe` 降权重启需要真实安装成功才触发。
两者都要靠 §5 第 1 项那一步来判定。

### 4. 新的发布物

| 文件 | 体积 | SHA256 |
|---|---|---|
| `mcloud_155.0.8059.40_win64_setup.exe` | 127,545,856 B | `9600c425cfd632541110ad600adecc06137adae15bfdbe3700fc347224437d43` |
| `mcloud_155.0.8059.40_win64_mini_installer.exe` | 127,519,744 B | `488e604be2f4ab8f54f74649124858c1f5117606e23eebf69bde3fd5bc87ebc6` |
| `installer/out/MCloud-Setup-embedded.exe`（非发布物，验收默认目标，D161） | 127,545,856 B | `e7de33d5df7a7397820784376be7e41741913955a067e1fd40778f05027fc05b` |

两个 sidecar 用 `sha256sum -c` 双双 OK。mini_installer 沿革：
`0602cafa…`(r3, 带 D105) → `54fc59b5…`(r4, 修 D105) → `17b31513…`(r5, 修 D109) → **`488e604b…`(r6, 载荷跟上 D142 + 安装器修复进入发布物)**。

### 5. 本轮仍未做（不要读成"已完成"）

1. ~~**干净安装复验未做**~~ ⇒ **已做，见 §7**（用户选 B：卸载 → 全新安装 → 复验 → 保留安装）。
   结果：安装 rc=0、flags 与仓库**逐字节一致**、对安装后的二进制回显 **`enable 49 / disable 2` / exit 0**、
   根目录无残留、无暂存件、默认浏览器自愈。过程中登记 **D162**（卸载缺 `--force-uninstall` 必卡）
   与 **D163**（本机 `EnableLUA=0` ⇒ D123 降权与 `RelaunchElevated` 在此**不可验证也不生效**）。
   ⇒ 原本列在这里的"两条够不着的分支"结论要**改写**：`RelaunchElevated` 与 D123 的降权实效
   在本机**不是"等这一步"，而是"这台机器测不了"**——需要一台 UAC 开启的机器。
2. **D146 未进二进制**：需要 `deploy_mcloud.py` + 重编译。本轮**没有**为它单开一次全树重编
   （D74：config/正文改动即 51,296 步 ≈3 h，而它零行为收益），建议与 D149 raster 线程 A/B
   或 D147 `symbol_level` 绑在同一批重编里。
3. **未跑 `final_gate_matrix.ps1` 九门收口矩阵**，也没把 `installer_arg_test.py` 接进去——
   它 exit 2 是合法结论（PARTIAL），直接进矩阵会让"环境不满足"与"门禁失败"混成一种颜色，
   接线时需先定矩阵对 rc=2 的语义。
4. **未跑 r1–r4 四条实操探针**（第4周期遗留，本就尚未接入矩阵）。
5. **`installer/out/*.exe` 与 `out/mcloud` 之外的中间态未纳入版本控制**，本节表格外的产物
   （如 `.cycle5/MCloud-Setup-verify.exe`）仍是上一轮的旧件，只作取证用，不要当发布物比对。

### 6. 本轮改动的文件

| 文件 | 改动 | 对应 |
|---|---|---|
| `.bugreview/installer_arg_test.py`（新） | 参数级 Red→Green 判据：假安装包录 argv + rc 参与判定 + 四条污染自检；SKIP 记 PARTIAL/exit 2 | D121 D129（D157 的修复） |
| `win_scripts/build_setup_exe.py` | 找不到 Roslyn 即 exit 113 + 两种修法；新增 `--allow-nondeterministic` | D130 |
| `.bugreview/package_m155.py` | 无条件转印子编译器日志；同批产出验收用包装器（D161）；notes 模板改 49+2 口径并新增「相对 r5 差异」整节 | D130 D142 D157 |
| `mcloud_155.0.8059.40_win64_{setup,mini_installer}.exe` + `.sha256` | 重打包 | D121–D129 D142 进入发布物 |
| `installer/out/MCloud-Setup{,-console,-embedded}.exe` | 全部重建到当前源码（gitignore，不入库） | D161 |
| `docs/superpowers/specs/2026-10-10-release-notes-m155.md` | 由模板重生成：新口径 + 新哈希 + 差异节 | D142 D157 |
| `docs/CHANGELOG.md` | 新增 **r6** 段（历史 r3/r4/r5 哈希不回改） | — |
| `AGENTS.md` | D130 现状、两条验收判据分工与"不要简化成 `--user-level` 用例"的原因、D160 口径、Python/PowerShell 三条语言坑 | D130 D157 D159 D160 D161 |
| `docs/tasks/bug-review-pak-src-defects.md` | r6 段（D156–D161）+ 勾掉两条第5周期待办 | — |

### 7. 干净安装复验（用户选 B：卸载→全新安装→复验→保留）执行记录

用户授权后按 B 走完。**过程中撞到两条新缺陷 D162 / D163，都在下面。**

前置只读快照（`b_pre.ps1`）：`RUNNING_INSTANCES=0`、根 exe `155.0.8059.40`、
已安装 flags `61b7670856ed`（旧）、根目录无残留 flags、暂存件 0、目录 262 条目、
`UserChoice=ChromiumHTM`（→ `C:\Program Files\Chromium\Application\chrome.exe`，即**默认浏览器就是本产品**）、
4 个 .lnk 指向它（含 `User Pinned\TaskBar`）。

| 步骤 | 命令 | 实测 |
|---|---|---|
| 卸载（第一次，**错**） | `setup.exe --uninstall --system-level` | `WaitForExit(240000)` **超时判 FAIL**。现场零删除（目录仍 262 条目），残留 2 个 setup.exe + 1 个带 `--uninstall` 的 chrome.exe（就是确认框宿主）⇒ 按 pid 清掉自己启动的这三个 |
| 卸载（第二次，**对**） | `setup.exe --uninstall --system-level --force-uninstall` | **0 s 返回 19 = UNINSTALL_SUCCESSFUL**；`APP_DIR_EXISTS=False`、`HKCR\ChromiumHTM` 已删、**任务栏固定项被连带删除**、`UserChoice` 仍写 `ChromiumHTM`（悬空）、chrome 进程 0、setup 残留 0 |
| 全新安装 | `mcloud_155.0.8059.40_win64_setup.exe --quiet --system-level`（stdout 重定向） | **8 s 走完，rc=0**，全程无一次需要人点按钮。日志关键行：`已从自身解出安装包…127,519,744 字节` / `启动：mcloud_mini_installer.exe --system-level` / `mini_installer 退出码 = 0` / 四项复验 True / `关联 UserTarget: (unresolved) -> …chrome.exe`、`TargetExists: n/a -> yes` / `快捷方式数量 前=1 后=3` / `完成：已确认更新到 155.0.8059.40` / `确认：无 setup.exe / mini_installer.exe 驻留` |
| 安装面断言 | 目录与注册表实测 | `ROOT_EXE=155.0.8059.40`、`FLAGS_IN_VERDIR=True`、**根目录无残留 `mcloud_flags.txt`**（D109 遮蔽源为零）、`STAGING_LEFTOVERS=0`、`HKCR\ChromiumHTM=True`、桌面/开始菜单 .lnk 由安装器重建、**任务栏固定项未恢复**（无 API，需手工重新固定） |
| **flags 字节一致性** | `sha256sum` | 安装后 `Application\155.0.8059.40\mcloud_flags.txt` = **`d71d988ca2d2ab`** == 仓库那份，逐字节一致 |
| **运行期回显（headline）** | `flag_runtime_state.py --chrome "C:\Program Files\Chromium\Application\chrome.exe"` | **exit 0**，`运行时 override：enable 49 项 / disable 2 项；子进程命令行 18 条`，并打印 `[与仓库一致]`；`[C]` 确认 `D3D12VideoDecoder`、`SkiaGraphite` **已禁用**（拖拽冻结缓解定案完好）；`[D]` 普通开关缺失 0 |
| 默认浏览器 | 注册表复查 | `DEFAULT_PROGID=ChromiumHTM` → `C:\Program Files\Chromium\Application\chrome.exe`，**`DEFAULT_TARGET_EXISTS=True`** ⇒ 悬空状态被重装自愈，无需用户重新设默 |

⇒ **AGENTS.md 步骤 8 的"干净安装复验"这一条，r6 包首次满足**，且回显口径确认为 **49+2**。

#### [D162] 复验/验收里的"卸载"步骤缺 `--force-uninstall`，无人值守必卡　**High（流程阻断）**
- `AGENTS.md` 原文只写"…然后卸载"，`setup_wrapper_test.py:142-144` 更是把
  `--uninstall --system-level` 直接写死。**上游源码**：`chrome/installer/setup/uninstall.cc:884-890`
  —— 不带 `--force-uninstall` 时走 `IsChromeActiveOrUserCancelled()`，它
  `LaunchChromeAndWait(target_path, --uninstall)` **启动 chrome.exe 弹确认框并等用户点**；
  带 `--force-uninstall` 才走静默分支（注释原文"Try to close all running Chrome instances"）。
- 本轮实测代价：第一次卸载 240 s 超时判 FAIL（现场零删除，但残留 3 个进程要手工清）；
  旧 `setup_wrapper_test.py` 若走到那一行会挂满 `timeout=600` 再从 `finally` 里抛
  `TimeoutExpired`，把整个测试炸掉——而它在 `finally`，所以**清理和结论一起丢**。
- `.cycle4/inuse_utf8.json` 里 `uninstall_rc: "19"` 说明那次确实走通了，但**无法据此判断走的是哪条分支**
  （`LaunchChromeAndWait` 失败时 PLOG 分支也会直接 `UNINSTALL_CONFIRMED`）——
  也就是说"卸载成功"取决于确认框弹不弹得出来，是个**不确定判据**。
- **修复**：`setup_wrapper_test.py` 加 `--force-uninstall`（含源码依据注释）；
  AGENTS.md 复验条目改为可直接粘贴的两条命令 + 期望退出码 19。

#### [D163] 本机 `EnableLUA=0` ⇒ D123 的降权修法与 `RelaunchElevated` 分支**在此机器上不可验证、也不生效**　**Medium（结论边界）**
- 实测：`HKLM\...\Policies\System\EnableLUA = 0`、`ConsentPromptBehaviorAdmin = 0`，
  账户是内置 `Administrator`（`whoami /user` → SID 尾号 **-500**）。
  ⇒ 全机没有 UAC 分令牌，**所有进程都在 High Mandatory Level**（`whoami /groups` 对照实验：
  直接从本 shell 启动 = `S-1-16-12288`；**经 `explorer.exe` 启动仍是 `S-1-16-12288`**）。
- 三条后果：
  1. 包装器日志那句"当前处于提权上下文，改由 explorer.exe 启动浏览器，避免继承管理员令牌"
     在本机是**空头承诺**——Explorer 自己就是 High，绕过去拿到的还是完整管理员令牌。
     ⚠ 所以**不能**把本轮写成"D123 已验证降权"：D123 的代码修法在正常 UAC 机器上是对的
     （那里 Explorer 是 Medium），但在本机上无法证伪也无法证实。
  2. `if (systemLevel && !IsAdmin())` 恒为假 ⇒ **`RelaunchElevated` 这条分支在本机不可达**，
     因此 **D158（跨 IL 取不到 ExitCode 会把成功报成失败）在本机测不了**，需要一台 UAC 开启的机器。
  3. "浏览器以管理员运行"的真因是这台机器的 UAC 配置（与 D150 的 BIOS 超线程同类：环境事实，
     不是仓库代码缺陷）。真正的缓解是把 `EnableLUA` 打开，而不是改安装器。
- 建议：任何"提权/降权/完整性级别"类结论都要标注取证机器的 `EnableLUA`；
  本仓现有结论里 D123、D158、`installer_arg_test.py` 的 C 用例都属"仅在本机取证，需 UAC 机器复验"。

#### r6 复验后新增的待办
- [ ] 需要**一台 UAC 开启（`EnableLUA=1`）的机器**才能收口：D158（提权子进程 `ExitCode` 是否取得到）、
      D123 的降权实效、`RelaunchElevated` 分支。
- [ ] 任务栏固定项被卸载器删除且无 API 可恢复 ⇒ 发布说明里应写"升级走 setup 就地更新可保留固定项，
      **先卸载再装**会丢"（D120 的"别换位置"结论在这里再加一条"别卸载"）。
- [ ] 用户需手工把 `Chromium.lnk` 重新固定到任务栏（本机现状：桌面与开始菜单快捷方式已由安装器重建，
      默认浏览器已自愈，任务栏无固定项）。

### 8. 复验后改动的文件（在 §6 之外）

| 文件 | 改动 | 对应 |
|---|---|---|
| `AGENTS.md` | 干净安装复验改成**可直接粘贴的非交互命令**（装 `--quiet`、卸 `--force-uninstall`、期望退出码 19）+ 断言四件事 + 卸载会删任务栏固定项的实测后果 | D162 D131 |
| `.bugreview/setup_wrapper_test.py` | 收尾卸载加 `--force-uninstall` 并写下源码依据（旧写法会挂满 600 s 再从 `finally` 抛 `TimeoutExpired`，把清理和结论一起丢） | D162 |
| `docs/tasks/bug-review-cycle5-report.md` | 本节（§7–§8） | D156–D163 |
| `docs/tasks/bug-review-pak-src-defects.md` | D162 / D163 入索引 + 勾掉"干净安装复验"待办 | D162 D163 |
| 机器上的真实安装 | 已全新装到 `C:\Program Files\Chromium\Application`，flags 与仓库字节一致，**保留不卸载** | — |

---

## 续 2：第 6 轮（另一模型）改动的处置与整体回退（2026-10-12 04:00–04:40）

用户随后让**另一个模型**基于 `96267cd` 审查并"优化"了我 r6 的成果。经逐条复核，
它的改动里**正确的部分不少，但它引入了 3 个阻断级缺陷并弄脏了构建树**，
用户决定：**抛弃它本轮的全部操作，代码回到 `96267cd`**。本节是这次回退的事实记录。

### 它改了什么（范围）

12 个已跟踪文件 +515/−83：`installer/mcloud_setup.cs`(229)、`benchmark/bench_startup.ps1`(132)、
`win_scripts/inject_flags_loader.py`(34)、`benchmark/tools/r4_memory_stability_check.py`(88)、
`AGENTS.md`(35)、`.bugreview/installer_arg_test.py`(30)、`benchmark/tools/{r1,check_features}`、
`win_args_mcloud.gn`(8 行注释)、`win_scripts/{build_setup_exe,deploy_mcloud}.py`、`.bugreview/package_m155.py`；
另有 4 个未入库新文件：`win_scripts/apply_raster_threads.py`(91)、
`.bugreview/{test_mutex_single_instance(102),gpu_degradation_probe(135),build_cycle6}(39)`。

### 复核：它做对的（我逐条去源码/树里核过，可惜最终随回退一起撤掉）

| 项 | 我的核验 |
|---|---|
| D126 关闭集合补 `chrome_proxy` | 依据 `install_worker.cc` 成立——根目录两份被锁映像只关 chrome.exe 会走 in-use 静默分支 |
| D132 命名互斥体 | `SetStage` 用 `BeginInvoke`+`IsHandleCreated`+try/catch ⇒ 它的倒计时线程**不会**跨线程炸；`RebuildArgs` 是"除 drop 项全透传"⇒ `--no-force` 在提权路径**不丢**（我原本两条怀疑都被证伪） |
| D135 校验去副作用 | `HygieneCleanup` 从 `Verify()` 拆出且只在判定后执行，正确 |
| D136 ProgId 解析顺序 | HKCU 覆盖 HKLM 的判断正确；`.exe` 截断还加了"后随空白或串尾"守卫，能挡住 `chrome.exe.bak\` 这类陷阱 |
| A1/A2/A5 加载器 | 树内 `<algorithm>`(106 行)、`base_switches.h`(108 行) 确实已存在；CR→LF、剔 NUL 逻辑正确 |
| D149 raster | 锚点我去了树里核：`compositor_util.cc:50` 确为顶格 `const int kMaxRasterThreads = 4;`；`:437` 的 `std::clamp` 确在读开关**之后** ⇒ "命令行给 >4 无效"成立。默认不改值 + 断言锚点 + 回退路径的设计是对的 |
| D141 | 三个 tools 走 `MCHROME_EXE`/`MCHROME_SRC`/`MCHROME_INSTALLED_EXE` 方向正确（旧 `INSTALLED_EXE` 确实指向不存在的路径） |

### 它引入的阻断级缺陷（三条，全部实测复现）

| ID | 级别 | 现象与复现 |
|---|---|---|
| **D164** | **High** | `build_setup_exe.py` 给 csc 传 `/version:<ver>`。Roslyn csc 的 `/version` 含义是**"打印编译器版本并退出"**，没有"设程序集版本"的用法。实测：`--version` ⇒ csc 只输出 `5.9.0-1.26357.3 (…)`、**不产出文件**、脚本 exit 111；而它同时把 `package_m155.py` 改成**无条件传 `--version`** ⇒ **整条重打包流水线被打断**。（我一度改成生成临时 `AssemblyInfo` 特性文件来修，实测 `FileVersion/ProductVersion` 正常——但按"全部回退"的决定该修复也一并撤掉，`9600c425…` 发布物回到无版本资源状态，与 `96267cd` 一致。） |
| **D165** | **High** | 把 `installer_arg_test.py` 的污染自检改成 `after[系统级] > 0`，而用例 C 的执行前提是 `before[系统级] == 0` 且 `run_case` 全程 `--no-launch` ⇒ **不可满足**。实测 `前=(0,0) 后=(0,0)`、零进程被改动，判据报 **FAIL/exit 1**，把我 r6 的 12/12 PASS 打回假红。**教训：污染自检必须可满足**，否则它只是在随机报错（D89 同族）。 |
| **D166** | **High** | K1-CPU 把全进程树 CIM 枚举（单次 50–200 ms）插进 `WaitForInputIdle` 的轮询间隙 ⇒ **在被测窗口内扰动被测对象**：实测 K1 从基线 45 ms 撑到 **607 ms**；且冷启动快于首个 200 ms 间隔时 `$samples=0`，它把"0 个采样点"当量具失效直接 `throw` ⇒ **正常情形（本机日常 45–60 ms）下整个基准自杀 exit 1、有效结果被丢**。 |
| D167 | Medium | 它的"单位自洽断言"写成 `\|meanCores/核数*100 − $pct\| > 0.5`，而 `$pct` 就是同一表达式算出来的 ⇒ **差值恒为 0 的假检查**。真正可用的是 `cpuSec ≤ 逻辑核 × 墙钟秒` 这类有物理意义、可能失败的界。（`bench_memory.ps1` 里 D145 那条是真断言——两侧来自独立数组；它抄成了自减自。） |
| D168 | **High** | 它的 `build_cycle6.ps1` 在**不等价于成功构建的环境**里跑 `gn gen`（日志证据：`'new.h' file not found`、`'corecrt_terminate.h' file not found`、`__libcpp_timespec_t` 未知 ⇒ libc++ 编不过，`autoninja exit=1`，2 分钟即挂，`chrome.dll` 仍是 10-11 20:01）。因为 `-imsvc` 包含路径会被烘进 `build.ninja`，**每个编译目标的命令行都变了 ⇒ 全树失效**（`ninja -n` 报 51,361 步）。我用补全环境（`DEPOT_TOOLS_WIN_TOOLCHAIN=0` + `vs2026_install` + `GYP_MSVS_OVERRIDE_PATH` + atlmfc `INCLUDE`）重跑 `gn gen`（35747 targets，exit 0）后步数降到 **14,042**，且 `ninja any.obj` 单目标**编译通过** ⇒ 构建树已恢复可用，只是脏。**按"回退"方针我没有开这 14k 步重建**（它会把发布物推进到含 D146 日志的新二进制、换 SHA、要重做干净安装复验，而"回到本轮之前"并不需要它）。 |
| D169 | Low（取证） | 它对使用者机器做过**注册表写入**：删掉 `HKCU\...\UserGpuPreferences` 里两条指向已不存在路径的 MCloud 值（其余 QQ/WeGame/ArmouryCrate/yysls 条目我核过仍在）。但它 AGENTS.md 里写的"清理前已备份"**站不住**：`.cycle6/UserGpuPreferences-backup.txt` 里**不含被删的那两条**（只有其余 10 条），删前现场在未命名的 `.cycle6_gpupref.txt`。而且它的 6 个 `.cycle6_*.txt` 落在**仓库根且未被 gitignore**，一次 `git add -A` 就会提交。 |

### 回退做了什么

- 已跟踪 11 个文件 `git checkout --` 回 `96267cd`；`benchmark/bench_startup.ps1` 先前已单独回退；
  **完整改动留档**：`.cycle6/cycle6_full_work.patch`（968 行）与 `.cycle6/bench_startup_k1cpu_work.patch`（170 行）。
- 4 个未入库新脚本**移出仓库**但没销毁：`.cycle6/cycle6-reverted/`（`apply_raster_threads.py`、
  `test_mutex_single_instance.py`、`gpu_degradation_probe.py`、`build_cycle6.ps1`）。
  注：`deploy_mcloud.py` 回到 HEAD 后不含 6b 接线，所以那份 raster 脚本即便留在树里也不会被 deploy 调用。
- `.gitignore` **保留我加的两条**（`.cycle6/`、`.cycle6_*`）——HEAD 里没有，这是防上面那类散件进仓库的必要规则，
  属于我的改动而非它的改动。
- 树内正文：用 HEAD 的 `inject_flags_loader.py` 重跑，输出 `loader block replaced in place (content differed)`，
  树里 A1/A2 痕迹归零、D146 那行 `LOG(WARNING)` 保留（它是 HEAD 内容）。
  ⚠ 由此产生的已知状态：**`chrome.dll`(10-11 20:01) 不含 D146 日志行**，即"源码领先二进制一行（纯日志）"，
  这正是第5周期报告自己登记的待办；打包门禁会因 mtime 拦住重打包，属预期行为。
- 它的注册表删除**不回滚**（被删的两条指向不存在的路径，留着就是 D154 那颗雷）；删前原文在 `.cycle6_gpupref.txt`。

### 回退后的测试（全部实跑）

| 项 | 结果 |
|---|---|
| `verify_sources.py` | PASS / exit 0，`.ps1` 计数回到 **44**（它那个不入库的 `build_cycle6.ps1` 曾把门禁输入集变成 45 —— 干净检出复现不了，正是 D137 修过的"门禁在自己的取证语料上失败"那一族） |
| `ruff --select F,E9,B,SIM win_scripts benchmark .bugreview` | **127 项**，与第5周期记录的既存 backlog 计数一致 ⇒ 无新增 |
| `flag_stability.py` | PASS / exit 0（51/51 存活，删除项净行为为 0） |
| `installer_arg_test.py` | **12/12 PASS / exit 0**，用户级+系统级两条参数分支都被真实执行、污染自检四项全过 |
| `test_d137_guard.py` / `test_build_win_preflight.py` / `check_loader_syntax.py` | 各 PASS / exit 0 |
| `bench_startup.ps1 -Runs 5`（HEAD 版） | K1 中位数 **61 ms**（76/56/61/50/75），exit 0 |
| `bench_memory.ps1 -Tabs 6 -Samples 2` | K2 正常、K2-CPU 中位 0.05% 整机 / 0.01 核，exit 0 |
| `flag_runtime_state.py`（安装后二进制） | exit 0，回显 **enable 49 / disable 2**，标注 `[与仓库一致]` |
| 发布物 | `sha256sum -c` 两个 sidecar 均 OK：`9600c425…` / `488e604b…`（与 `96267cd` 一致，**未被它重打包污染**） |

### 一条没归因完的开放项（诚实记录）

批量跑四个判据时 `installer_arg_test` 报过一次 **rc=1**，而我随后单独跑 + 连跑三次都是 rc=0。
那次我把输出重定向到了 `/dev/null`，**所以无法说出是哪条断言红的** —— 这本身是流程缺陷：
判据的日志必须自己落盘，否则偶发失败永远无法归因（与 D114"证据不得掀翻判据"是同族的反面：
证据不得被丢弃）。已改为 `> .cycle6/arg_rep_N.log` 的跑法。**当前状态：5 次里 4 次全绿，1 次红且未归因。**
