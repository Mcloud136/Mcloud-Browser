# MCloud Browser Changelog

## M155（内核升级 M151 → M155.0.8059.40）— 2026-10-10

### 升级本体
- 内核 `155.0.8059.40`（当期 stable）；V8 `15.5.35.20`；clang `llvmorg-24-init-7747`；PGO `chrome-win64-8059-…profdata`
- 定制重放面在升级中进一步缩小为 **6 个上游文件 / 206 行**：
  `apply_mcloud_source_defaults.py` 不再翻转 `kD3D12VideoDecoder` 默认（改为只校验 + 自愈回退历史覆盖），
  禁用意图统一由 `mcloud_flags.txt` 显式声明 —— 消除长期存在的「覆盖与运行时禁用互相抵消」自相矛盾（原 D24 遗留项收口）
- 首轮全量编译 58,416 步一次通过（`autoninja exit=0`）；`gn gen --check` 35,747 targets 无未知参数告警

### 性能 / 内存 / GPU 实测（同一台机器、同一时刻成对测量）
| 指标 | M151-r3 | M155 | 结论 |
|---|---|---|---|
| K1 冷启动中位数 | 46 ms（59,46,46,47,46） | **45 ms**（62,45,47,45,44） | 持平（差异在噪声内） |
| K2 50 标签驻留中位数 | 2590 MB（56 进程） | **2563.3 MB** | -1.0% 内存 |
| 标签开合泄漏探针（4 轮 × 25 标签，关标签后驻留） | 872.7→883.8 MB（+3.7 MB/轮） | **957.5→950.3 MB（-2.4 MB/轮）** | 155 无正漂移，回收更好 |
| GPU 渲染路径（窗口化探针） | GPU 进程在，D3D11+D3D12 ANGLE，无 SwiftShader | **同左，gpu-preferences 逐字一致** | 无回退 |
- A6 子进程命令行验证通过；`check_features.py` 在 155 源码树上 **53/53 存活**；
  `flag_stability.py` 以 [155,156] 为版本集合 **PASS**

### 升级期发现并修正的问题
- **D50（新）**：`SkiaGraphite` 在 151/155/156 均为**上游默认启用**，而拖拽冻结缓解只是注释掉启用行 —— 等于从未禁用。
  现改为显式 `--disable-features=SkiaGraphite`（`--enable-features=…` 列表不变），并把它列入 155 上的同方法 A/B 复核项
- `FlingSchedulingImprovements`：M155 起上游彻底移除，已按预评估约定从 flags 删除，接替候选见
  `docs/tasks/m155-perf-features.md`（`ResampleScrollEventsForFling`、`ApplyScrollRailingInRenderer`）
- 工具链坑（已写入 AGENTS.md 构建流程）：`gclient sync --jobs=16` 撞 googlesource 429 → 改 `jobs=4`；
  钩子按字面调用 `python3` 会命中 WindowsApps 占位程序 → 在真实 Python 目录内 `mklink /H python3.exe python.exe`；
  缺 `v8/tools/builtins-pgo/profiles/x64-rl.profile` 会让 `snapshot_blob.bin` 直接失败 → `download_profiles.py download`

### 第3周期全面 bug-review（2026-10-10 晚，D52–D67）
- 范围：运行时加载器与其注入器、`win_scripts/*.py`、`benchmark/*.ps1` 与 `benchmark/tools/*.py`、
  新入库的 `.bugreview` 验证脚本、以及 `git diff --stat` 实测的 6 文件 / 229 行编译面。
  详版报告：`docs/tasks/bug-review-cycle3-report.md`（含 5 轮深度 review 与全局效率评审）
- **测量有效性（High）**：`bench_memory.ps1` / `leak_probe.py` 原先按**进程名**汇总整机 chrome，
  K2 与被测实例无因果关系；测试工具还做机器级 `Stop-Process`，会杀掉用户自己的浏览器会话。
  现统一按本次 `--user-data-dir` 叶子名筛 PID、只清理本实例、采不到进程即判 FAIL。
  同构建同时刻对照：2586.8 MB / 58 进程（整机口径）→ **2512.85 MB / 57 进程**（实例口径）
- **静默失效族收口**：D62 注入器只在正文不一致时才看调用点（调用行丢失会报 already up to date 而加载器永不运行，
  已改为无条件校验 + 负例 exit 1）；D64/D67 polly 接线与 AVX2 基线注入器从"标志串存在即完成"
  改为正文比对式升级器；D57 加载器不剥 UTF-8 BOM（首行整条被丢）；D59 flags 行尾 ` # 注释` 会让该条失效
  （新增 `flag_stability.py` 的 F 断言静态拦住，不改运行期语义）
- **卡死风险**：12+ 处 WMI/PowerShell/git grep 调用无 timeout → 统一补 180/600/900 s；
  bench_*.ps1 的清理移入 try/finally（异常路径不再留孤儿 chrome 与临时目录）；
  leak_probe 不再写死 CDP 端口 9333（每轮取空闲端口，避免驱动到别人的实例）
- **D63（潜伏）**：Polly 是编译期 pass 却被写进 `ldflags`（打开也基本空转）、Windows 分支给 lld 发
  BOLT 不支持的 `--emit-relocs` → 改 `cflags` 并加 `!is_win`；`use_polly/use_bolt` 仍保持 false
- 新增 `benchmark/tools/`… 之外，加载器边界测试扩充为 `loader_edge_test2`（11 例）+
  `loader_edge_test3`（7 例，含 BOM/空文件/缺文件/垃圾行/双写/行内注释/子进程限定），
  并在 M151(v5) 上做 Red 对照：**T1 BOM 用例 v5 失败、v6 通过**，证明用例有鉴别力
- 本轮自身引入又被回归测试抓出的 3 个次生缺陷记为 D66（含 PowerShell
  `double + '|'` 抛类型转换异常被宽 except 吞成 0 MB 这一条）
- 流程缺口修复：此前**仓库没有任何 Python 静态检查**，现引入 ruff + pyflakes 并逐条判真伪处置真阳性
- **验收链自身的缺陷（D68–D72，其中 High×3）**：只有真把 A6 脚本与构建链跑一遍才会现形——
  A6 主路径 `--dump-dom chrome://version` 在 M155 已无 DOM（D68）；清理语句撞 lockfile 抛异常
  使脚本**在探测之前**终止并留下 9 个孤儿 chrome（D70）；探针一次性 kill 留下 crashpad 尾巴，
  残余进程锁住 `dxcompiler.dll` 把 51,296 步重编打断（D71，`autoninja exit=1`）；
  构建失败后打包门禁仍拿上一轮遗留 installer 报「门禁全绿」并回填新哈希（D72）。
  修复：A6 改以子进程回显为主路径 + GUID 实例指纹 + finally 清理 + 残留即失败；
  三处清理改为循环杀到干净；`package_m155.py` 加新鲜度链（dll 不得早于加载器源与 GN 源），
  收尾链在构建失败时中止不打包。纪律已写进规范 4.1.1：**门禁与量具必须当作被测代码来测**
- 产物：加载器升到 v6 需重编 `chrome.dll`；`gn gen --check` 后出现整树重编计划（51,296 步，
  确切成因待查，已列待办），为保持"仓库正文 == 二进制源码"本轮接受该重编

### 第3周期·扩展轮（同日晚，D77–D104：导航基准 / 门禁聚合 / src 参与度 / 步骤文档 / 临时文件）

- **D89（Critical，本轮最重要）**：`benchmark/tools/final_gate_matrix.ps1` 的汇总用函数体内
  `$results +=`，PowerShell 作用域规则使其永不写回脚本级变量 → **无论各门禁成败都输出
  `RESULT: ALL PASS` 且 exit 0**。决定性证据：对不存在的构建树实跑，日志同屏出现
  `leak_probe => exit=1` 与 `ALL PASS`。修复后聚合用 `$script:`、**自检采集条数**、
  `ExitCode` 取不到判 `NOEXIT`、逐项表打到 stdout；对假树如实报 `FAIL x5`/exit 1，
  对真树 `ALL PASS (8/8)`。口径修正：**"ALL PASS 摘要行"不再作为证据，结论只认逐项退出码。**
- D83：同一文件的 `param()` 写在四条语句之后 → `-OutDir` 被静默丢弃、恒测默认树且仍 exit 0
  （最小复现：副作用先执行、`param` 被当命令名、参数丢失）。已归位并证明参数确被消费。
- D78/D79/D80/D81：`bench_navigation.ps1` 曾 `2>$null | Out-Null` 吞掉输出、拿不到 DOM 也报
  "加载耗时"，且 `& $exe` 无超时（页面卡住即基准挂死）。改为 `--headless=new` + DOM 字节判成功 +
  `WaitForExit(超时)` + 实例级清理 + 自动变量改名；无效样本一律抛"导航基准不可信"。
  文件头同时声明量具边界：headless 不含 GPU 合成路径，只看相对趋势。
- D84/D85：`PSParser::Tokenize` 对语句顺序类错误全盲（同一坏文件三次 PARSE OK）。
  `win_scripts/verify_sources.py` 新增 PowerShell 三层检查：BOM 规则（D38 机器化）、
  `param` 位置、AST 解析，且**空输入即 FAIL**；三个负例文件验证可证伪，并当场抓到
  4 个在用的 `.ps1` 缺 BOM。
- D86/D87/D88：9 个基准/工具脚本的默认被测对象硬编码在 M151 回滚树且不打印身份 → 改为
  `$env:MCHROME_EXE`/`MCHROME_OUT` + 155 兜底 + 打印 exe/dll 路径·大小·mtime·标志文件状态 +
  回滚树告警；`flag_stability.py` 增 `_require_revs()` 前置校验并打印三个修订解析到的 commit。
- D77：实测仓库 `src/` 590 文件中 **344 个**与 M155 树内容不同却无任何脚本读取（其中
  `BUILDCONFIG.gn`/`compiler/BUILD.gn` 副本还带着上一代注入痕迹），而 AGENTS.md 称其为
  "覆盖文件/主战场"。生成权威清单 `src/INVENTORY.md`（工具 `.bugreview/src_inventory.py`）
  并更正口径：`src/` 是素材目录，改上游文件只能走 `win_scripts/apply_*|inject_*`。
- D90（High，步骤文档缺步骤）：`docs/progress.md` §5.1"下次编译更新内核时的操作"只让跑
  `copy_essentials.py`，**跳过全部定点注入**（加载器 / AVX2 / Polly 接线 / `chrome.release` 登记），
  照做会得到"能编译能打包、但 53 项 feature + 3 项开关整体静默丢失"的构建 —— 与 D47 同一失败
  模式，出现在升级时真正会被执行的清单上。已重写为 `deploy_mcloud.py` 唯一入口 + 显式 `CR_DIR`
  + 编译前 `verify_sources.py` + rebase 后三项收尾（重生成 INVENTORY、flag_stability、门禁矩阵）。
- D91（Medium）：`docs/BUILDING_WIN.md` 是上游 Thorium 流程（`C:\src\chromium\src`、VS 2022、
  `git clone Alex313031/mcloud`、构建 `mcloud_shell/setup` 等本项目不存在的目标、"密钥在私有仓库"
  与 ADR-001 冲突），全文没有 `deploy_mcloud.py`，却被 AGENTS.md 指为 Windows 前置文档。
  已在文件头加"上游遗留、非本仓库步骤"警示，并把 AGENTS.md 的指针改到权威步骤。
- D92（Medium，泄漏）：D78 新加的临时文件清理用 `-ErrorAction SilentlyContinue` 把"子进程仍持有重定向句柄"导致的删除失败吞掉，两次实跑在 `%TEMP%` 遗留 42 个文件（最大 409 KB）。改为 `pendingCleanup` 登记 + 按实例杀进程后 5 轮重试 + 残留即告警；重跑后 `navdom=0 naverr=0 navprof=0`，且样本仍有效。
- D93（R9 复核自查）：我给 `param` 位置写的新检查用 `strip()` 判顶层，会把函数体内**合法的**
  `param(...)` 误判为违规；当前仓库恰好没这种写法所以未暴露。改为只认顶格 param，并用
  「合法函数级 param 不报 / 顶层错位仍报」两路对照实测。教训：新增判据要同时问「它对哪些合法代码会误判」，假阳性会把人训练成忽略门禁。
- D94（High，假绿家族）：`benchmark/run_baseline.ps1`（K1/K2/K7 一键采集器）用 `& 子脚本 | Tee-Object -Variable x` 抓输出，但 PS 5.1 里 `Write-Host` 走 information stream(6)，实测**捕获 0 行**（加 `6>&1` 才有 6 行）→ 生成的基线报告「原始数据」为空、KPI 表恒写「见原始数据」，末尾仍绿色打印「报告已写入」且 exit 0。同文件另有两处口径错：`-Version` 默认写死 `M150`（同时决定报告标题与**文件名**）、`$env:COMPUTER_NAME` 拼错（应为 `COMPUTERNAME`）使「构建机」字段恒空。修复：`6>&1` 捕获 + 正则把 K1/K2/K7 数值填进表 + 版本从被测二进制文件版本推导 + 抽不到数即写入异常记录并 exit 1（报告仍留作取证）+ 捕获后回显保住了控制台进度可见性。全仓 `Tee-Object` 扫描确认该模式只此一处。
- D97：`win_scripts/setup.py`（遗留全量覆盖脚本）此前只靠文档口头禁令，误跑一次就污染源码树。现加拒绝闸：默认打印 `REFUSED` 并 exit 112、指向 `deploy_mcloud.py`，需显式 `MCLOUD_ALLOW_LEGACY_SETUP=1` 才继续；`--help` 保持可用（三条路径实测）。
- D99（Critical）+ D100：门禁把 `LOADER_TEST_OUT` 指向**真实构建目录**，而 loader 边界测试会改写 `out/mcloud/mcloud_flags.txt` 做 BOM/空文件/垃圾字节/3000 条语料，只在 finally 恢复。实测打断后发布目录留下 106,890 B / 300,063 B 的假 flags 文件（一首字节 0xD6 非 UTF-8），下游 A6/leak_probe/runtime_state 于是拿测试垃圾当生产配置测量，`flag_runtime_state.py` 直接崩在裸 `UnicodeDecodeError`。修复：门禁改建**硬链接沙箱** `out/mcloud_loader_test`（链运行时文件、跳过构建元数据与文件数>1000 的中间目录）；两个测试加「发现 args.gn/.ninja_log 即 REFUSED/exit 2」前门；`flag_runtime_state.py` 改 utf-8-sig 读 + 解码失败给恢复指引 + 与仓库不一致即 exit（`--allow-drift` 才继续）。隔离验证：沙箱里跑完测试，真实文件 sha256 前后不变。
- D102/D103（打包门禁的载荷判据是无效量具）：`package_m155.py` 原来靠「在 chrome.7z 里搜 `mcloud_flags.txt` 文件名」证明包里有它，但 7z 文件表是压缩的——对照实验里 `chrome.dll`/`resources.pak`/`icudtl.dat` 命中数全为 0，唯一命中是 chrome.dll 内加载器自己的字符串。上游 `create_installer_archive.py` 对匹配不到的 chrome.release 条目默认**静默跳过**（只有 --verbose 才打印），所以缺文件也能 exit=0。改为断言**打包暂存目录** `temp_installer_archive/Chrome-bin/mcloud_flags.txt` 存在且与仓库字节一致，并用「改名→FAIL、恢复→全绿」证明这条判据能失败。
- D104（用户机器实测）：装完 155 后 `Application\mcloud_flags.txt` 仍是 9-22 的旧文件，chrome://version 里因此出现 D51 修复前的坏 params 形式；`chrome.exe`/`chrome.dll` 与本次构建逐字节相同（说明装对了、只有额外文件没被覆盖）。已隔离旧文件并放入正文，待重启复核。
- 本轮**未改动任何浏览器 C++ 源码与 `mcloud_flags.txt`**，故不需重编；产物仍是
  `chrome.dll` 303,440,384 B / installer `0602cafa…7090`。

### Tier A 候选 A/B（升级后同日完成，结论：全部不采纳）


- 方法：同一 M155 二进制，只改 `out/mcloud/mcloud_flags.txt`，基线 + 10 臂逐项测 K1/K2/泄漏漂移/GPU；
  判定阈值在看数据前登记（`docs/tasks/m155-perf-features.md` §5.1），结论由 `.bugreview/ab_verdict.py` 机械产出
- **每一项都先过运行时生效校验**（子进程命令行回显，依据 `field_trial.cc:690` →
  `FeatureList::GetCommandLineFeatureOverrides()`）——没注册的臂直接跳过计时，避免产出"与基线无差异"的假数据
- 关键修正：变更算子必须是**编辑**而非追加。`base/feature_list.cc:449-452` 证明同名 feature 双写时
  **禁用侧胜出**，所以 `SkiaGraphite` 的"启用"臂用删行（回上游默认），追加 enable 是无效实验
- **重复测量给出的噪声带**（同配置两遍）：K1 ±4 ms、K2 ±0.19 %、泄漏 ±8.9 MB。round 1 按 ±5 MB 阈值
  判 `PartitionAllocAdaptiveMemoryReclaimInterval` 过采纳线，交错复测后被否（三次取值跨零）→
  最终 **8 项候选一律不采纳**，flags 不新增条目（无重复收益就加条目 = D48 的成因）
- `SkiaGraphite` 保持显式禁用：四项判据看不出差别，撤销定案需要拖拽+视频的人工复现证据而非 KPI
- **D51（新，Low）**：`InitialWebUI` 的 params 写成 `Feature:a/b/c`（缺 value）→ 参数关联失败退回默认值；
  因三个参数上游默认恰为 `true` 故净行为不变。已改为 `param/true` 显式写法，并给 `flag_stability.py`
  的 E 断言加"奇数 token 即 FAIL"的语法校验（负向对照已验证）。M151/M155 回显一致，非升级引入
- **发布物已知偏差**：已发布的 r3 包不含 `--disable-features=SkiaGraphite`（D50 修于升级期，晚于 r3 打包），
  即 r3 用户实际跑在 Graphite 启用状态；M155 包修正这一点。证据与说明见 `docs/dev-logs/M155-upgrade-report.md`

### 发布（未发布，仅本地产物）
- 安装包：`mcloud_155.0.8059.40_win64_mini_installer.exe`（127,523,328 B）
- SHA256：`0602cafabb94f221e7a6ec5bfd59605fceaceb0b2fa8c4d7e88339ea50717090`（sidecar 已同步；第3周期 bug-review 后的 loader v6 + D51 修正版全量重编产物）
- 哈希沿革（三个值都有原因，不是抄错）：`2afdfbdc…02` A/B 前首版 → `195f9349…2dd81` D51 flags 修正后 →
  `cd6f5172…3527` **作废**（D72：构建因孤儿进程锁文件失败，打包链却仍给上一轮遗留产物算出的哈希）→
  当前 `0602cafa…7090`（00:22 全量重编成功后，8 项收口门禁 ALL PASS）
- 发布状态：**未发布**（用户 2026-10-10 决定先做候选 A/B，暂缓 push/tag/资产上传）


## M151-r3（发布链路完整性 + 优化清单真实性）— 2026-10-10

### 🔧 发布链路（缺陷 D47，High）
- 新增幂等注入脚本 `win_scripts/apply_installer_payload.py`，把 `mcloud_flags.txt: %(ChromeDir)s\`
  登记进 `chrome/installer/mini_installer/chrome.release`，并接入 `deploy_mcloud.py`（现 7 步）
  与 `verify_sources.py` 关键脚本清单
- 修复前该行只存在于某台构建机的未提交改动里：干净源码树按文档构建会**编译打包全绿但安装包装不到标志文件**，
  63 行运行时优化整体静默丢失（内核升级必然踩到）
- 探针 `.bugreview/d47_probe.py` 五例全过：M155 上游文件首次注入 / 重复运行幂等 / 与当前 151 树状态判定 /
  缺锚点报错不写文件 / **干净上游 151 文件 + 注入器 == 当前树文件（逐字节）**

### 🧹 优化清单（缺陷 D48）
- 按上游 feature **声明位**核对 151/155/156 后删除 6 条根本不存在、一直被静默忽略的条目：
  `CanvasOopRasterization`、`DirectComposition`、`EarlyData`、`AVIF`、`SpeculationRules`、
  `ServiceWorkerNavigationPreload`（这 6 条在 r2 上也无操作，**删除不改变现有行为**）
- `BestEffortTaskInhibitingPolicy` 上游真名为 `EnableBestEffortTaskInhibitingPolicy`（默认禁用）：
  改名后转注释保留，待基准验证再启用；`FlingSchedulingImprovements` 保留并标注"M155 起上游已移除，升级期删除"
- 新增跨版本稳定性断言 `.bugreview/flag_stability.py`（PASS）- 标志文件形态由 63 行（60 feature + 3 普通开关）变为 **56 行 = 53 feature + 3 普通开关**；
  加载器追加成本 ≈1,753 B，占 24 KiB 命令行预算的 **7.1%**（原 8 项冗余条目带来的开销一并消除）
- 用项目自带 `benchmark/tools/check_features.py` 对两棵真实源码树交叉验证：M151 **53/53 OK**；
  M155 **52/53 OK**，唯一 NOT_FOUND 正是已标注升级期处置的 `FlingSchedulingImprovements`
：无新增开启项、被移除项在 151 上曾生效数 = 0、
  53 条中 52 条三版全存活、普通开关三版均在
- 方法论更正：新版 `BASE_FEATURE(kFoo, <default>)` 不写名字串，运行时名由标识符去 `k` 推导，
  因此"全树搜引号名串"的旧判法既漏报又误报

### 🚀 M155 升级准备（目标版本由用户定案为 M155）
- 预拉取：`155.0.8059.40` 源码树（本地对象库浅克隆，10.2 GB）+ `chrome-win64-8059-…profdata`（104 MiB）；
  DEPS 首轮被 googlesource 429 限流，已改 `--jobs=4` 多轮重试续跑（坑位已写入升级任务单）
- 性能新特性挖掘：`.bugreview/declared_features_151_155.json` 全集合 diff（155 新增 809 / 移除 609，
  性能关键词 118）→ `docs/tasks/m155-perf-features.md`（Tier A 19 项含源码出处与默认状态，Tier B/C 分档）
- 执行任务单 `docs/tasks/m155-upgrade-task.md`（阶段 0–5 + 验收标准）

### 📦 发布状态

- 发布页：https://github.com/Mcloud136/Mcloud-Browser/releases/tag/v151.0.7922.99-r3
- L3 深度安全审查：findings=0；`main` 与 tag `v151.0.7922.99-r3` 均已推送
- 安装包已作为 Release 资产上传（HTTP 201），GitHub 计算摘要与本地一致；
  公开下载经 302→206 校验，首字节 4D 5A，总长 123,466,752 B

### 📦 构建产物

- 本版为全量重编译产物（50,795 步，`autoninja exit=0`）；实测留痕见
  `docs/dev-logs/M151-r3-benchmark.md`（K1 中位数 39 ms；K2 2927.5 MB/64 进程，
  与档案值 2646.2 MB/57 进程**进程数不同不可直接比较**）；A6 子进程命令行验证通过
- `mcloud_151.0.7922.99_win64_mini_installer.exe`（123,448,320 B 量级，本版全量重编译后重打）
- SHA256：``393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049``


## M151-r2（稳定性/内存安全修复）— 2026-10-09

### 🛡️ 运行时内存安全（本版重点，缺陷 D39/D40）
- 加载器新增**命令行字节预算**：总 24KiB、普通开关子预算 12KiB，超预算条目跳过并 `LOG(WARNING)` 降级
- 堵住两条同型崩溃路径：超大 `--enable-features` 合并值撑破子进程 `CreateProcessW` 32767 字符上限
  （GPU 进程无法创建 → `FATAL GPU process isn't usable. Goodbye.`），以及单条超长值（如异常大的 `--js-flags`）
- 实测：106,890B / 3000 条 feature 语料下浏览器存活且内置列表不入子进程命令行；修复前约 12s FATAL
- 标志文件强制 1MiB 上限 + 逐行有界解析；解析改用 `string_view::substr`，`-Wunsafe-buffer-usage` 告警清零
- 注入器"是否需要替换"判定由版本号标记改为正文比对（真幂等，避免正文与标记不同步的假升级）
- 真实标志文件仅占预算 ~8%（1.9KB/24KB），60 项 feature + 3 项普通开关全部照常生效

### 🧰 pak_src 工具（缺陷 D1-D24 收口）
- 头部/表范围/偏移单调性校验、64 位尺寸累加并拒绝 >4GB、错误路径补齐 fclose/free、
  有界索引写入与 `%255s` 宽度限制、argv 与路径拷贝越界防护
- 判据：ASan 畸形语料优雅报错 + 450 例变异模糊 + 23 例结构化溢出探针（两向均带可成功正例），
  零 ASan 报告/零访问违例/零挂起；v4/v5 真实 pak 往返字节一致

### 🖥️ 体验修复配置固化
- 窗口拖拽缩小播放视频冻结的缓解 4 项标志固化为禁用（§4.6 用户实测确认有效）
- 核显视频开头绿屏（Intel D3D12 解码首帧缺陷）修复包内携带：`mcloud_flags.txt` 已确认打进 installer

### 🏗️ 工程修正
- 含 `gclient sync --force --reset --delete_unversioned_trees` 的 legacy 升级入口改为拒绝执行（D28/D37）
- 8 个含中文的 `.ps1` 补 UTF-8 BOM，修复 PowerShell 5.1 解析失败（D38）
- `copy_essentials.py` 白名单断言防旧基线副本再入（D41）；`build_win.py` 目标修正（D29）；脚本统一 `CR_DIR`（D30）
- 发布链路缺陷登记并修复：installer 明文字节搜索无效（D43，应扫 `chrome.7z` 载荷）、
  发行包与 `.sha256` sidecar 不同步（D44，发布脚本改为同批重算写盘）
- `verify_sources.py` 接入 CI（`.github/workflows/verify.yml`）
- 文档口径校正：标志数量统一为实测 63 条生效行 = 60 feature + 3 开关（D42）

### 📊 验证与产物
- 连续五轮 8 门回归全绿（零新缺陷）；K1 冷启动中位数 54ms 无性能回归
- 发行包 `mcloud_151.0.7922.99_win64_mini_installer.exe`（123,448,320B）
  SHA256 `054efb37c8018feda5ba06842e39269908e438f27ae873b0bb670bfc05ab389f`
  （强制全量重做：重编加载器 TU → 重链 chrome.dll → 重建 chrome.7z → 重打 installer）

---

## M151-opt（运行时优化增量）— 2026-08-06

### 🔧 V8 脚本执行修正（确定性 bug）
- 修正 `--js-flags` 命名：连字符→下划线（旧写法在 M151 不生效）
- `invocation_count_for_maglev=200`（默认 400，更快进入 Maglev）
- `invocation_count_for_turbofan=1500`（默认 3000）
- 新增 `--osr-from-maglev`、`--sparkplug-plus`

### ⚡ 新增 17 项运行时 feature（均经 check_features.py 核实存活，66/66）
- 启动预载/预热（7）：Prerender2WarmUpCompositor*、LoadingPreconnectToRedirectTarget、PreloadTopChromeWebUI、BookmarkTriggerForPreconnect、NewTabPageTriggerForPrerender2、MultipleSpareRPHs
- 脚本/加载加速（7）：ThreadedPreloadScanner、ConsumeCodeCacheOffThread、InlineScriptCache、PreloadSystemFonts、HttpDiskCachePrewarming、LCPPAutoPreconnectLcpOrigin、LoadingPredictorPrefetch
- MSE/视频缓冲（3）：RevokeMediaSourceObjectURLOnAttach、ReduceHardwareVideoDecoderBuffers、BackForwardCacheDWCOnJavaScriptExecution

### 📊 基准（vs M151 基线，同机同方法）
- K1 冷启动：79ms vs 73ms（+8%，首跑噪声偏大，待更多样本）
- K2 内存 50 标签：**2696.4MB vs 2646.2MB（+50MB，+1.9%）** —— 预载类 feature 的内存代价
- 详见 docs/dev-logs/M151-opt-benchmark.md

### ⚠️ 权衡与后续
- 预载/预热类 feature 以内存换预载速度；若内存敏感，建议评估移除 MultipleSpareRPHs、LoadingPredictorPrefetch、NewTabPageTriggerForPrerender2 后重测
- V8 修正与脚本加速收益待 K4（Speedometer/JetStream）实测确认
- B 站弹幕 GPU 加速在源码未找到专属 feature，标注待验证

### 🔬 预载收益验证（数据驱动决策，2026-08-06）
- 导航响应实测：bilibili 预载 -5.6%（1434 vs 1519ms），example/qq 无差异——收益依赖预测命中率
- 内存隔离实测（真实站点 50 标签）：全配置 7676.2MB → 移除高内存三项后 **7472.8MB（-203MB）**
- **已移除**：MultipleSpareRPHs、LoadingPredictorPrefetch、NewTabPageTriggerForPrerender2（代价大收益不稳定）；flags 69→66 条
- 新增 bench_navigation.ps1 导航基准；bench_memory.ps1 增加 -ExtraFlags/-UrlsFile 支持

---

## M151 (151.0.7922.99) — 2026-08-06

### 🚀 Chromium 内核升级
- 升级到 Chromium M151 (151.0.7922.99)，同步上游安全修复与新特性（V8 15.1、`<usermedia>` 元素、声明式 Shadow DOM slot 分配等）

### 🔧 工程体系升级（本次新增）
- 部署体系重构：`win_scripts/deploy_mcloud.py` 统一入口 + 6 个定点幂等脚本，取代易漂移的整体覆盖方案
- 内置启动标志加载器（chrome_main_delegate.cc）：52 条启动标志/49 个 feature 首次真实生效（A6 验证 3/3 通过）
- 移除 M150 失效 feature 2 个（PWAFullCodeCache、ServiceWorkerScriptFullCodeCache）
- DoH kAutomatic 定制移除（M151 上游已吸收）
- Polly/BOLT GN 接线修复（开关自此真实生效，前置条件就绪前维持关闭）
- 基准测试体系：benchmark/ 全套脚本 + M150/M151 双基线归档

### 📊 性能基线（vs M150，同机同方法）
- K1 冷启动：73ms vs 71ms（+2.8%，测量噪声内，持平）
- K2 内存（50 标签驻留 90s）：2646.2 MB vs 2669.1 MB（**-0.86%**）
- 详见 docs/dev-logs/M151-benchmark.md 与 docs/dev-logs/M151-upgrade-report.md

### ⚠️ 已知限制（沿用 M150）
- Widevine DRM 未包含（需单独下载 CDM）
- 核显视频绿屏问题待修复

---

## M150 (150.0.7871.37) — 2026-06-20

### 🚀 Chromium 内核升级
- 升级到 Chromium M150 (150.0.7871.37)
- 安全更新：27 个安全修复（5 Critical, 12 High, 8 Medium, 2 Low）
- Web 平台更新：JavaScript V8 15.0、CSS 新特性、Web API 改进

### ⚡ 性能优化
- **51 项运行时性能标志**：启动、内存、多线程、视频、GPU 全链路优化
- **编译时优化栈**：AVX2 + FMA3 + O3 + Polly + BOLT + ThinLTO + PGO
- **预期提升**：启动 10-20%、内存 15-30%、视频 10-15%

### 🐛 Bug 修复
- 修复 HTTP 断流问题（DNS-over-HTTPS 模式改为 kAutomatic）
- 修复后台应用默认行为（默认关闭）
- 修复 Google API 密钥配置
- 代码审查修复（14 个问题）

### 📦 CI/CD
- 简化 GitHub Actions 工作流（只做打包上传）
- 移除 build.yml（不再需要 CI 编译）

### ⚠️ 已知限制
- D3D12 视频解码不可用（回退到 D3D11）
- Widevine DRM 未包含（需单独下载 CDM）
- 核显视频绿屏问题（待修复）

---

## M149 (149.0.7827.53) — 2026-06-19

### 🚀 Chromium 内核升级
- 升级到 Chromium M149

### ⚡ 性能优化
- 初始性能优化实现
- AVX2 + FMA3 编译支持

---

## M130 — 初始版本

- 基于 Chromium M130 的初始版本
