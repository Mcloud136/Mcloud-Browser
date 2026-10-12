# MCloud Browser v155.0.8059.40

基于 Chromium **M155（155.0.8059.40）**，Windows x64。本版是一次内核升级（M151 → M155），保持既有性能取向与
已定案的稳定性禁用项，并在升级过程中修正了两处口径问题。

## 变化

- **内核 M155**：V8 15.5.35.20、clang `llvmorg-24-init-7747`、PGO 使用 8059 系列 profile。
- **定制面更小**：需要重放的上游改动由 7 个文件降到 **6 个文件**——不再翻转 `kD3D12VideoDecoder`
  上游默认（该解码器仍由启动标志显式禁用，以规避 Intel 核显 D3D12 解码绿屏）。
- **冻结缓解真正生效**：`SkiaGraphite` 在上游本就是默认启用，此前仅注释掉启用行并不构成禁用；
  本版改为显式 `--disable-features=SkiaGraphite`（其余 3 项禁用状态不变）。
- **清单去虚**：删除 `FlingSchedulingImprovements`（M155 起上游已彻底移除该 feature）。
- **安装版才真正带上优化清单（r4）**：`mcloud_flags.txt` 改由 VersionDir 投递到 `Application/155.0.8059.40/`，加载器 v8 按 chrome.dll 所在目录（`base::DIR_MODULE`）优先查找，兼容开发树/便携包的扁平布局与安装版的版本子目录布局。此前登记在 Application 根目录的条目会被打包但**不被安装**（setup.exe 对根目录只搬固定三件套），所以 r3 及更早的安装包在干净机器上等于零内置优化（缺陷 D105）。
- **加载器路径优先级修正（r5）**：v7 以 exe 同目录为第一候选，会让一份残留的 `Application\mcloud_flags.txt` 永久静默压掉安装包投递的正式文件（缺陷 D109）。v8 改以 chrome.dll 所在目录为第一候选，与上游 `GetModulePath` 同口径。

## 安装（两个发布物，请用 setup 那个）

| 文件 | 用途 |
|---|---|
| `mcloud_155.0.8059.40_win64_setup.exe` | **推荐**。外层安装包装器：优雅关闭正在运行的本产品实例 → 安装 → **复验根 chrome.exe 确实升到本版本** → 清理临时文件与残留进程 → 自动重启浏览器。**默认就地更新机器上已存在的那一份**（不擅自换安装位置，避免旧路径的任务栏固定项失效）；两处都没装过时默认装到用户级目录（不弹 UAC），显式 `--system-level` 走系统级并自举提权。 |
| `mcloud_155.0.8059.40_win64_mini_installer.exe` | 上游原生安装器本体。**如果浏览器正在运行，更新会静默不生效**——根启动桩是被锁的映像，上游把它暂存成 `new_chrome.exe` 并把收尾改名委托给 Google Update，而本产品不发布 Google Update（缺陷 D119，已实测）。只在浏览器已完全退出、或你确认自己需要裸安装器时使用。 |

包装器另有 `--list-only`（只报告将关闭哪些实例、不关闭不安装）与 `--no-launch`（装完不重启）两个开关，退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。

## 自上次发布（v151.0.7922.99-r3）以来

**最重要的一条：以前的安装包在干净机器上根本不带运行时优化清单。**
`mcloud_flags.txt` 此前登记在安装包**不会安装**的位置——D47 修的是"打包侧没登记"，
而 D105 才查清真正丢件的环节在**安装侧**：`setup.exe` 对 Application 根目录只搬固定三件套。
所以 r3 及更早的每一个包，装到干净系统上时那 52 项 feature + 3 项普通开关**整体静默丢失且不报错**。
现在它随版本目录投递，并已用一次真实的 `--system-level` 干净安装复验：文件落地、与仓库逐字节一致、
对**安装后的二进制**回显 enable 50 / disable 2（第6周期 D170 补上 `UserBlockingAboveNormalPriority`
之后的口径；D142 之后曾为 49 / 2，再早是 51 / 2）。

## 本包相对上一份 r5 包的差异（第5周期 D121–D155）

- **用户级安装此前整体失效（D121，Critical）**：包装器把 `--system-level` 写死传给 mini_installer。
  后果是选"用户级"时既不提权（提权分支按 systemLevel=false 判断，不触发），又**真的装进
  Program Files**，而复验查的是用户目录 ⇒ 必然报"复验未通过"。现已按 `systemLevel` 条件传参
  （上游 mini_installer 只认 `--system-level`，用户级就是"不传该开关"）。
  判据：`.bugreview/installer_arg_test.py` —— 用假安装包把收到的 argv 录进文件，
  **不触碰任何真实安装位置**；同一条用例跑在修复前的源码上会录到 `--system-level`，
  Red 与 Green 双向都成立，所以这条判据有区分力，不是"两边都恰好通过"。
- **系统级安装后浏览器不再继承管理员令牌（D123，安全）**：此前在提权进程内直接
  `Process.Start` 拉起浏览器，整个浏览会话（含全部 renderer / GPU / utility 子进程）以
  admin 运行——任何网页侧 RCE 直接等于本机管理员，且 Explorer→浏览器拖放被 UIPI 拦死。
  现改经 `explorer.exe` 启动，落回交互用户的中等完整性级别。
- **两处"假绿"的复验判据改正**：默认浏览器注册**整条丢失**此前不算回归（D124——丢失比
  "指向死文件"更严重，用户彻底失去默认浏览器，却静默放过）；进程状态查不到此前按
  "已退出"处理（D125——跨完整性级别访问被拒时进程活得好好的还锁着根启动桩，于是对着
  仍在运行的浏览器执行安装，精确复现 D119 的静默无效更新）。现两者都按失败处理。
- **判定与定位细节**：安装器自身退出码参与最终判定（D129，否则"装失败 + 目录残留"会被
  判成"已确认更新"）；提权实例的退出码原样透传而不再一律报 0（D122）；两处都装着不同
  版本时按 `System.Version` 逐段比较，不再用序数字符串（D127：`"155.0.8059.40"` 按字符比
  会小于 `"155.0.8059.9"`，于是选中更低的那份）；快捷方式快照补上全机器开始菜单
  （D128，系统级安装的 .lnk 恰在那里，此前"指向死路径"根本 WARN 不到）。
- **优化清单去虚（D142）**：删掉 2 条在本平台**根本编译不进来**的声明——`BaseLockTrySpin`
  整体在 `#if BUILDFLAG(IS_POSIX)` 内，`PartitionAllocUsePriorityInheritanceLocks` 的门是
  `is_android && (x64 || arm64)`；另有 2 条上游默认已启用的条目
  （`PartitionAllocMemoryReclaimer`、`PruneOldTransferCacheEntries`）**保留但加注**，
  它们是显式钉住（pin）以防上游翻默认值，不应算作定制收益。删除的 2 条净行为为 0。

## 本包相对 r6 包的差异（第6周期 D170–D172）

- **浏览器进程优先级提升此前从未生效（D170，性能）**：清单里只有 `BrowserProcessAboveNormalPriority`，
  而它只负责把浏览器进程标成 `kUserBlocking`；`kUserBlocking` 映射到哪个 Windows 优先级由
  `UserBlockingAboveNormalPriority` 决定（`base/features.cc:205` 默认禁用，
  `base/process/process_win.cc:299-304`）。两项必须成对，缺后者等于什么都没提。
  现已补齐，安装版实测根进程 `PriorityClass` 由 `Normal` 变 `AboveNormal`（gpu-process 同升，
  renderer 仍 `Idle`，符合上游语义）。
- **EcoQoS 与优先级是同一处判定（多核 / 混合架构）**：`process_win.cc:283-289` 只在优先级为
  `kUserBlocking` 时解除 EcoQoS。本机的 14900HX 是 8P+16E，未解除时浏览器线程会被 Windows 11
  调度到能效核并降频。代价是功耗与发热上升——这与本产品"极致流畅"的定位一致（性能优先，见 ADR-002）。
- **Windows 更新重启后不再自动恢复（D172）**：上游用 `RegisterApplicationRestart` 注册恢复，
  命令行上限 1024 字符，而我们的 `--enable-features` 单项就约 1.4 KB ⇒ 返回 `E_INVALIDARG`，
  上游只打一条 `LOG(WARNING)` 后继续，**完全静默**。现由 `win_scripts/apply_restart_cmdline.py`
  在重启命令行里剔除 `enable-features` / `disable-features` / `js-flags`（三项都由加载器每次启动
  从 `mcloud_flags.txt` 重新注入，无需命令行接力），修剪后**实测 ≈284 字符**
  （Red 时同一条命令行 1911 字符）。r7 已把该改动**编进二进制并实测**：对安装后的二进制用与
  Red 同一采集方法启动日志复测，该 WARNING 不再出现。
- **净收益口径（D171）**：52 项 feature 中 14 项上游默认即启用，属显式钉住，已在清单内逐条标注。

**新增外层安装程序 `mcloud_155.0.8059.40_win64_setup.exe`（请用这个）**：

- 浏览器正在运行时双击裸 `mini_installer`，会出现"安装返回成功、下次启动仍是旧版"：根启动桩是被锁的
  映像，上游把它的替换推迟并委托给 Google Update，而本产品不发布 Google Update（D119）。
  setup 会先优雅关闭正在运行的本产品实例（只发关闭消息、超时才强制结束），装完**复验根 chrome.exe
  确实升到本版本**，再清理临时文件与残留进程并自动重启浏览器。
- 默认**就地更新已存在的那一份**，不擅自换安装位置——换位置会让指向旧路径的任务栏固定项失效（D120）。
- 只发裸 mini_installer 等于把"装了但没更新"交给用户，所以两个发布物都要给，但指引一律指向 setup。

**清单可信度**：删掉 7 条上游根本不存在的开关（D48）；修正一处 feature 参数写法——
`Feature:without_spellcheck/without_translate/high_stream_priority` 这种裸名会**静默丢弃全部参数**
并退回上游默认值，已改为合法的 `参数/值` 成对形式（D51）；`SkiaGraphite` 的禁用改为显式声明（D50：
上游在 M155 本就默认启用，"注释掉启用行"等于从未禁用）。

**质量与测量体系**：三轮系统性 bug-review（D52–D120，共 69 条）。把"按进程名统计整机 chrome"
这类与被测实例无因果关系的测量改成按实例取数；把会**假绿**的门禁逐条换成能失败的正例
（聚合表为空却输出 ALL PASS、在压缩归档里搜文件名字节串、"包里有这个文件"当成"装得出来"）；
新增实操五轮探针（真拖窗口、真杀 GPU/渲染进程看恢复、真下载/打印/PiP/全屏、真 1440p 播放、
跨轮句柄与内存累积）与 9 门收口矩阵。测试工具不再做机器级进程清理，也不会污染发布产物目录。

## 实测（同一台机器、同一时刻成对测量）

| 指标 | M151-r3 | M155 |
|---|---|---|
| K1 冷启动中位数 | 46 ms | 45 ms |
| K2 50 标签驻留中位数 | 2590 MB | 2563.3 MB（-1.0%） |
| 标签开合后的驻留漂移 | +3.7 MB/轮 | -2.4 MB/轮（无正漂移） |
| GPU 渲染路径 | GPU 进程 + D3D11/D3D12 ANGLE | 同左，gpu-preferences 逐字一致 |

内置启动标志 52 项 feature + 3 项普通开关在 M155 源码树逐项存活（`.bugreview/flag_stability.py`
52/52，并确认第5周期删除的 2 条在 M151 上同样是无效声明，净行为为 0），
并通过子进程命令行验证（`flag_runtime_state.py`，回显 enable 50 / disable 2）确认实际注入。
⚠ 52 项里有 14 项上游默认即 ENABLED（D171），那 14 行是**显式钉住（pin）**而非"打开了默认
关闭的优化"，真正的定制启用项是 34 项——别按 50 去理解收益。

## 已知限制

- **未做代码签名**：从 GitHub 下载后首次运行会有 SmartScreen 警告（需要"仍要运行"）。
- **打 tag 不会自动带出安装包**：`release.yml` 不在 runner 上编译内核，而 127 MB 的包体既被
  `.gitignore` 排除、又超过单次 push 的 100 MiB 上限，所以推 `v*` tag 只会建出一个没有资产的
  release；安装包必须走 GitHub Release 资产上传（缺陷档案 D45）。

## 校验

下载后核对 SHA256（两个发布物都要核）：

```
certutil -hashfile mcloud_155.0.8059.40_win64_setup.exe SHA256
certutil -hashfile mcloud_155.0.8059.40_win64_mini_installer.exe SHA256
```

- setup（推荐）预期值：`8e59c4580e95bef278bef517da210c6b104598ad5ba2152bfda70bfef3d5d746`
- mini_installer 预期值：`dd85313bdd8366730aa2b62418729eeb72d4af54ec146fef8e1eb19003704295`

两者都是同一个内核构建（155.0.8059.40）的产物；setup 只是把 mini_installer 内嵌进外层安装程序，
所以体积略大。
