# 第4周期 bug-review：五轮**实操**检测报告（2026-10-11）

## 0. 本轮口径与结论

用户要求：**"对测试内容使用实地测试，尽可能的实际操作而不是仅依赖脚本反馈"**。
因此本轮不以静态断言为主，而是每轮真启动一个独立 profile 的窗口化实例，真拖窗口、真杀
GPU/渲染进程、真下载文件、真放 1.18 GB 本地视频，判据一律取**浏览器自己的回答**：
真实 DOM 文本、磁盘上真实落地的字节、Win32 真实窗口位置、子进程真实命令行。

结论：

- **1 条产品缺陷（D109，High）已修复并证伪式验证**：加载器 v7 的路径优先级与上游口径相反，
  使一份残留的根级 `mcloud_flags.txt` 能永久、静默地压掉安装包投递的正式文件，
  而运行时 oracle 与加载器同序 ⇒ **门禁全绿而线上跑旧配置**。
- **11 条量具缺陷（D107、D108、D111–D118）**：本轮真正的风险分布是"量具 > 产品"。
  其中 4 条属于**假绿**（错误页冒充恢复、空页面上反向断言恒成立、截图/异常把判据带走、
  `/json/new` 丢参数被读成"页面没渲染"），3 条属于**假红**（`INPUT` 结构体尺寸、
  泄漏判据数学上永不成立、`decodingInfo` 必填参数）。
- **1 处量化过的取舍**：`TransientKeepAlivePolicy` 的内存代价首次有了数字。
- **4 个怀疑被证伪**，其中 1 个差点被我写成错误结论（"上游删掉了 chrome://media"）。
- 产物 r5：127,564,288 B / SHA256 `17b3151379dfc1091efe10a05825ce433c58895a27f6d925025dfbbd7517f3b7`。

## 1. 方法学（本轮沉淀的硬规则）

1. **文本存在性 ≠ 内容正确性**。所有"读到了内容"的判据必须先过 `cdp.is_error_page()`；
   正向标记只能来自**自己生成的本地页**。远端内容会变：example.com 正在改版，不同 CDN 节点
   分别返回 917 字符多语种版（含 `<h1>Example Domain</h1>`）与 156 字符纯段落版（连 h1 都没有，
   该串只活在 `<title>`）——拿正文当标记会永久误判。
2. **不存在型断言必须有可读性前置**。`X not in text` 在空页面上恒真。
3. **证据采集不得影响判据**。截图这类旁证一律 try/吞异常，主判据照常输出并照常定退出码。
4. **实验前提要由结果自证**。定位不到"被测标签的渲染进程"时，改成"杀到被测标签真的崩为止"。
5. **量具不得污染目标，也不得反噬被测树**。硬链接沙箱里**写之前必须先删链接**
   （否则 `open(w)` 会截断被测树里的真文件）；沙箱默认路径不得落在 `out/` 之下。
   两条都在本轮踩过并加了前门。
6. **取不到数据一律非 0 退出**（0=判据成立 / 1=有判据不成立 / 2=环境不满足），
   环境不满足不得记为通过。

## 2. 五轮结果

### R1 启动与运行时配置（真实 DOM）— ✅ 17/17

`benchmark/tools/r1_startup_check.py`。与 `flag_runtime_state.py` 的分工：后者读**子进程命令行**
（证明开关进了命令行），R1 要证明的是**浏览器真的把自己画成了那个样子**。

- chrome://version：`155.0.8059.40`、修订 `cfaadc5a132d…@{#936}`、V8 `15.5.35.20`；
  命令行含 `InitialWebUI:without_spellcheck/true/without_translate/true/high_stream_priority/true`
  （D51 修复后的合法 params 形式）、`--enable-gpu-rasterization`、
  `--disable-background-media-suspend`、`--disable-features=D3D12VideoDecoder,SkiaGraphite`、
  `--js-flags="--invocation_count_for_maglev=200 …"`；旧的坏形式 `without_spellcheck/without_translate`
  （无值）**不存在** ✓。
- chrome://gpu（内容在 `<info-view>` 的 shadow root 里，78,108 字符）：
  Canvas / WebGL / Video Decode / Video Encode / Compositing / Rasterization / WebGPU 全
  **Hardware accelerated**；`Skia Graphite: Disabled`、`TreesInViz: Disabled`、`Raw Draw: Disabled`；
  Skia Backend `GaneshGL`、`In-process GPU false`、`Passthrough Command Decoder true`、
  `Direct composition true`、`Supports overlays true`；无 "Software only" 回退。
- 真实站点：`https://www.example.com` 渲染出 917 字符多语种正文，CJK/阿拉伯/西里尔字形正常。
- 证据：`.cycle4/r1_version.png`、`r1_gpu.png`、`r1_site.png`（由人读图，不靠脚本自证）。

### R2 交互与故障恢复 — ✅ 8/8

`benchmark/tools/r2_interaction_check.py`。

- **真窗口拖拽**（Win32 `SendInput` 绝对坐标，按下前先 `WindowFromPoint` 确认那个像素上
  确实是本实例的窗口，否则拒绝发鼠标按下——否则会拖到用户自己的窗口上）：
  位移 132×66 px、拖拽期间 rAF 计数 159 帧、拖完 `IsHungAppWindow = False`。
  这是 SkiaGraphite 禁用决策（memory: mcloud-window-freeze-mitigation）的**现场复验**。
- **真杀 GPU 进程**：杀本实例的 `--type=gpu-process` → 1 秒内被重建（1→1），
  页面仍可执行 JS、网络栈仍可用（`document.title` 命中）。
- **真杀渲染进程**：M155 的 CDP `Target.getTargetInfo` 已不返回 `processId`（实测字段不存在），
  因此改为闭环自证——逐个杀本实例渲染进程直到被测标签真的进崩溃态（第 6 个才命中，
  前 5 个是备用/其他标签的进程），随后 reload 恢复 ✓。
- **标签开合回收**：10 标签开→关，渲染进程 11 → 4（约 11 秒），私有内存随之回落。
- 全程只按 profile 指纹清理，`leftover_procs = 0`，用户自己的浏览器未受影响。

### R3 内容与媒体 — ✅ 11/11

`benchmark/tools/r3_content_media_check.py`。

- **本地 1.18 GB、2560×1440 H.264 录屏真播放 8 秒**：`currentTime` 推进到 7.95、
  `readyState 4`、`error 0`、`totalVideoFrames 483` / **`droppedVideoFrames 0`**。
- **chrome://media-internals**（注意真名，见 §3.3）列出该 player 与 `kPlay` 事件。
- **真 PiP 进入 ✓、真全屏进入并退出 ✓**（全屏截图 4.1 MB，须先 `Target.activateTarget`：
  非激活文档上 `requestFullscreen()` 抛 `TypeError: not granted`）。
- **真下载**：本地 stdlib HTTP 服务 + CDP 点击 `<a download>` → `r3-payload.txt` 落盘。
- **真打印**：`Page.printToPDF` → 8,459 B 且文件头 `%PDF-`。
- **解码能力**：`MediaCapabilities.decodingInfo` 对 h264 / hevc / av1 / vp9 全部
  `supported + smooth + powerEfficient`。
  ⚠ 该字段只证明"被选中"，不证明"硬件单元存在"（GTX 1050 Ti 为 Pascal，无 AV1 硬解单元）；
  HEVC 硬解的可靠证据仍是 K6 下用户 4K HEVC 播放时浏览器 CPU 2.3% + chrome://gpu 的
  `Video Decode: Hardware accelerated`。
- 远端 HEVC 源本机不可达（`test-videos.co.uk` 三个 URL 全部失败），故记
  `SOURCE-UNREACHABLE`，**不计入判据也不记为通过**。

### R4 内存 / 句柄 / 线程 / 退出残留 — ✅ 6/6 + A/B

`benchmark/tools/r4_memory_stability_check.py`，三轮 × 15 标签开合，每 4–10 秒采样：

```
   6.6s  procs=10  handles=1756  threads=56  private=310  MB
  36.9s  procs=33  handles=2753  threads=60  private=1927 MB   <- 开 15 标签
  56.1s  procs=22  handles=2273  threads=60  private=1046 MB   <- 关完
  84.5s  procs=33  handles=2770  threads=59  private=1846 MB
 103.5s  procs=22  handles=2281  threads=58  private=1027 MB
 132.1s  procs=33  handles=2779  threads=60  private=1840 MB
 151.2s  procs=22  handles=2286  threads=59  private=1064 MB
```

- 峰 33/33/33、谷 22/22/22、谷句柄 2273/2281/2286、谷私有内存 1046/1027/1064 MB ——
  **跨轮零累积**（这才是泄漏判据；"关掉后立刻回基线"会把正常的空闲进程复用误判成泄漏，见 D115）。
- 关窗前页面仍可执行 JS；`Browser.close` 后残留进程 **0**（孤儿进程会锁住 out/mcloud 的 DLL
  并让链接失败，见 D71）。
- **A/B：`TransientKeepAlivePolicy` 的代价**（同机同探针，唯一差别是命令行加
  `--disable-features=TransientKeepAlivePolicy`）：

  | | 基线 | 峰值 | 谷值（关完 8 秒） |
  |---|---|---|---|
  | 启用（当前发布配置） | 10 进程 / 309 MB | 33 / 1.93 GB | **22 进程 / 1.05 GB** |
  | 禁用 | 10 进程 / 310 MB | 27 / 1.80 GB | **12 进程 / 0.68 GB** |

  即约 **+10 个进程、+360 MB 的关标签后驻留**，换重开同站点零冷启动。上游在浏览器测试里
  默认禁用它，理由写得很直白：*"delays renderer process cleanup, breaking tests checking
  process counts or expecting immediate process exit"*
  （`chrome/test/base/in_process_browser_test.cc:381-385`）。
  按 ADR-002（性能优先）暂**维持启用**，数字留档；面向小内存机型时这一项应第一个重议。
  附带收益：这次 A/B 同时证明命令行 `--disable-features=X` 确实压得住内置 enable（D21 的
  user-first 合并在真实场景成立）。

### R5 发布与升级面 — ✅ 修复并三重验证

**D109（High，产品）：加载器 v7 的路径优先级与上游口径相反。**

- 上游判定"程序目录"的依据是 **chrome.dll 在哪**：`chrome/app/main_dll_loader_win.cc:175-191`
  的 `GetModulePath()` 先试 `exe_dir\<chrome::kChromeVersion>\chrome.dll`，找不到才退回
  `exe_dir\chrome.dll`。安装版根目录因此只是一个 4 MB 启动桩。
- v7 却以 `DIR_EXE` 为第一候选 ⇒ 任何一份**残留的** `Application\mcloud_flags.txt`
  都会永久、静默地压掉安装包投递到版本目录的正式文件。本机就是这种状态：
  `AppData\Local\Chromium\Application\` 下同时有根文件（D104 期间手工 copy 留下）与版本目录文件，
  旁边还躺着 9 月排障留下的 `.bak-20260922` / `.stale-20260922`。
- **验证链同构地错**：`.bugreview/flag_runtime_state.py` 的 `resolve_flags_path()` 照抄 v7 顺序，
  于是"读被压制的那份、断言那份"→ 门禁全绿而线上跑旧配置（D47/D62 同族的静默失效）。
- 修复：加载器 **v8** 改以 `base::DIR_MODULE` 为第一候选（`base/base_paths.cc:68` 由
  `FILE_MODULE` 推导，而 `base_paths_win.cc:43-51` 用 `GetModuleFileName(CURRENT_MODULE())`，
  `CURRENT_MODULE()` = `&__ImageBase`，即"这段代码所在的镜像"= chrome.dll），
  exe 目录次之（便携/开发树扁平布局），最新载荷目录兜底；oracle 同步改序，
  并**打印整条候选链 + 各自 sha256 + 谁压住谁**。

三重验证（每一重都能失败）：

| 层次 | 手段 | 修复前 | 修复后 |
|---|---|---|---|
| 判据（可重跑） | `.bugreview/loader_precedence_test.py`：硬链接拼出安装同形沙箱（根目录**无** chrome.dll），两份文件各带不同探针开关，真启动一次从 chrome://version 读回生效的那枚 | `verdict: ROOT` | `verdict: VERSION` |
| 真安装落地 | `mini_installer.exe --system-level` 干净装到 `C:\Program Files\Chromium\` | — | `Application\155.0.8059.40\mcloud_flags.txt` 8,186 B、sha256 `61b7670856ed…` 与仓库一致；根目录**没有**该文件（正是 D105 的投递路径生效） |
| 真产品二进制 | `.cycle4/verify_installed_shadowing.py`：往这次测试安装的**根目录**植入一份带 `--mcloud-installed-shadow-probe=ROOT` 的残留文件，启动已安装的 chrome.exe，读 chrome://version | （v7 会读 ROOT） | `installed binary read ROOT: False`、`read VERSION: True` → `VERDICT: FIXED`；探针文件用完即删 |

对安装后二进制的运行时回显：`enable 51 / disable 2`，与开发树一致；解析到的路径就是版本目录那份。
卸载：`Installer\setup.exe --uninstall --system-level` 返回 **19 = `UNINSTALL_SUCCESSFUL`**
（`chrome/installer/util/util_constants.h:45`），`C:\Program Files\Chromium` 整树消失、
HKLM 卸载项无残留，用户自己的用户级安装未受影响（其版本目录文件 sha 仍为 `61B7670856ED`）。

⚠ 一条需要用户知道的事实：**用户当前这台机器上的用户级安装是 r3 二进制（加载器 v6，只读 exe 同目录），
它之所以有优化，靠的正是那份手工留在根目录的文件**。装 r5 之后 v8 会改读版本目录那份，
根文件与两个 `.bak/.stale` 变成纯垃圾，可以删；但在升级之前**不要**单独删掉根文件，
否则那个旧安装会立刻退回"零内置优化"。

## 4. 收口验证

- `final_gate_matrix.ps1` — **RESULT: ALL PASS (9/9)**，本轮把 D109 的回归判据接成了第 9 门：

  | 门 | exit | 结果 |
  |---|---|---|
  | verify_sources | 0 | PASS |
  | flag_stability(A-F) | 0 | PASS |
  | loader_edge_test2 | 0 | PASS |
  | loader_edge_test3 | 0 | PASS |
  | A6 builtin flags | 0 | PASS |
  | flag_runtime_state | 0 | PASS |
  | **loader_precedence（本轮新增）** | 0 | PASS（verdict=VERSION） |
  | leak_probe(2x15) | 0 | PASS |
  | package_m155(门禁) | 0 | PASS |

  汇总条数自检（`$results.Count -ne $EXPECTED_GATES` 即 FAIL，D89 的教训）同步升到 9。
- `win_scripts/verify_sources.py`：PASS（44 个 .ps1 的 BOM/param 规则 + AST 解析全通过）。
- `ruff check --select F,E9,B win_scripts benchmark .bugreview`：本轮新增/改动的文件 0 命中
  （仓库仍有 20 条历史命中，18 条集中在遗留 `win_scripts/setup.py`，属既有待办）。
- 发布目录未被量具污染：跑完全部量具后 `out/mcloud/mcloud_flags.txt` 仍与仓库
  逐字节一致（`61b7670856ed…`）。
- ⚠ 已知**注释级**漂移（有意保留）：`win_scripts/inject_flags_loader.py` 里 D109 那段注释的
  措辞已更正为"根文件来自 D104 期间的手工 copy"（最初写成"由诊断脚本写入"，逐行核对
  `.diag/verify_flags_edit.ps1` 后确认它只读，见 D110 的更正）。**r5 二进制里仍是更正前的
  旧措辞**——纯注释、不影响任何行为；不为它单独花一次"1 TU 编译 + chrome.dll 重链 + 重打包 +
  换 SHA"（D74 的口径：零收益改动必须与真实改动同批落地）。下次任何实质改动重编时自动对齐。

## 6. 延伸：安装体验与"运行中升级"（D119，同日晚）

用户提出两件事：不要静默安装、旧版要能升到包内版本、装完不驻留更新进程。
探索后发现上游 M155 的 setup.exe **根本没有进度 UI**（`ProgressCalculator::Calculate()`
除单元测试外无消费者，也没有静默/非静默开关），所以界面只能由外层提供；进度条一项经确认**暂时搁置**。

真问题在第二件上，而且实测成立（过程与数据见缺陷档案 D119 详细段）：
**浏览器开着时装新版，安装器返回 0 但更新完全不生效**，`new_chrome.exe` 被暂存后无人消化。

落地内容：

- 新增外层包装器 `installer/mcloud_setup.cs` → `mcloud_<ver>_win64_setup.exe`
  （构建脚本 `win_scripts/build_setup_exe.py`，已接入 `package_m155.py`）：
  按可执行文件路径识别本产品实例 → `WM_CLOSE` 优雅退出（超时才强制）→ 安装 →
  **复验根 chrome.exe 版本 == 包内版本且无 `new_chrome.exe`** → 清理临时目录与进程 → 重启浏览器。
  UI 只有阶段状态文字（无百分比）。开关：`--system-level` / `--no-launch` / `--list-only` / `--quiet`。
- 验收（`.bugreview/setup_wrapper_test.py`，151→155 真实现场）：包装器退出码 0，
  **1 个 WM_CLOSE 关掉 8 个实例且未动用强制结束**，根 chrome.exe = 155.0.8059.40，
  `new_chrome.exe` 无残留，151 目录被正常删除，重启后 `chrome://version` 实测
  **actually_running = 155.0.8059.40**（对照组是 151），零进程驻留，用户自己的安装 sha 未变。
- 负向对照：`--list-only` 只报告不关闭；系统级模式下用户级实例**完全不在关闭集合内**
  （首版把另一个安装位置也并进集合，那会让系统级安装无故关掉用户正在用的浏览器，已收窄）。
- 发布可复现性：首版用 .NET Framework 自带旧 csc，**不支持 `/deterministic`**，同一份源码
  两次编译 SHA 不同（`b0bc7652…` → `96376b3c…`）⇒ 发布哈希失去意义。改为优先 VS Roslyn csc
  + `/deterministic+`，连跑两次打包 SHA 稳定为 `106a245452539057685e5fe336c06aae360699933c117b38c1feaa7e0d575e4e`。
  另一个坑：复现性对比必须**同名不同目录**——输出文件名会进元数据，首版用 `rep-a/rep-b` 对比
  得出"仍不可复现"的错误结论（差异只有 24 字节，且含 `A`/`B` 字符差）。
- 上游安装/卸载器**不杀浏览器进程**（`setup_main.cc:1773` 终止的是它自己，
  `setup_util.cc:186` 终止的是它自己 CreateProcess 出来的子进程）——这条排查是为了回答
  "测试期间用户浏览器为何退出"，结论：本轮所有工具调用要么是 `--list-only`，
  要么只针对 Program Files，所有 kill 都按 `.cycle4` profile 指纹过滤，无命中用户实例的路径。


## 5. 遗留与后续

- [ ] 把"干净安装复验"接进 CI 或收口矩阵（目前仍是手工一次 + `package_m155.py` 的静态断言）。
- [ ] `r1..r4_*_check.py` 四条实操探针尚未接入收口矩阵（`loader_precedence` 已接入）
- [ ] 包装器的 GUI 版只在 headless 自动化里验过（窗口出现/阻塞/关窗退出码），
      真人双击的观感与 UAC 流程尚未由用户确认；进度条按用户决定搁置。
- [ ] K3 窗口化 + CDP 导航通道（本轮的 CDP 基建已可直接复用）。
- [ ] D49：V8 连字符/下划线口径的 `autoninja d8` 歧义实验。
- [ ] 面向小内存机型时重议 `TransientKeepAlivePolicy`（代价已量化：+10 进程 / +360 MB 驻留）。

