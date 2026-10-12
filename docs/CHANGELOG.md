# MCloud Browser Changelog

## M155（内核升级 M151 → M155.0.8059.40）— 2026-10-10

### r13（发布 v155.0.8059.40 到 GitHub Release）— 2026-10-12 深夜

M155 首次真正发布：**https://github.com/Mcloud136/Mcloud-Browser/releases/tag/v155.0.8059.40**
（tag 指向 `03c35e6`，正文取仓库里的 `2026-10-10-release-notes-m155.md`，非 draft / 非 prerelease）。

- 四个资产全部上传并经**服务端回读核对**：
  `..._win64_setup.exe` 127,586,304 B（`1302268f…`）、其 `.sha256` 103 B；
  `..._win64_mini_installer.exe` 127,559,168 B（`27c3236b…`）、其 `.sha256` 112 B。
  核对项 = 服务器报告字节 == 本地字节、`state=uploaded`、两个 sidecar 从 GitHub 拉回后与本地**逐字节相同**。
- 匿名（用户视角）验证可下载：releases/download 链接 200（1 次重定向到签名地址），
  sidecar 匿名取回内容即 `1302268f8a0101f1…`。
- ⚠ **D45 没有被这次发布解决**：tag 创建确实触发了 `release.yml` 且它跑成 success，
  但它一个资产都没传（仓库里没有 `mini_installer.exe`，被 `.gitignore` 排除，且 121.6 MiB
  超 git push 单文件上限）。发布是靠 Release asset 上传手工完成的。
  我的 release 之所以没被它清空，只因为资产已经先在了 —— 也就是说**这条流水线现在仍是"绿色但什么也没做"**，
  下一个人若照它发布就会得到一个空 release。D45 保持开放。
- 凭据：经用户明确授权使用 Git Credential Manager 里已有的 HTTPS 凭据，只在进程内存中使用、
  未写入任何文件或 git 配置，异常输出统一做 token 遮蔽处理。
### r12（D197：CI 绿灯不能代表 gcc 判据跑过）— 2026-10-12 深夜

- 推送 `20ab337` 后 CI 显示 `Source Verification: success`，但日志需要仓库管理员权限才能取
  （`403 Must have admin rights to Repository`），所以**无法证明**新加的
  `check_pak_roundtrip` / `check_pak_asan` 真跑过而不是 SKIPPED。而当时 `main()` 只把
  `failed` 计为失败 ⇒ "没测"与"通过"共用退出码 0。这条假绿是我自己上一轮引入的。
- 修法：`GITHUB_ACTIONS=true` 时 `compile+round-trip` 落到 SKIPPED **直接 FAIL**
  （ubuntu runner 必有 `cc`；真没有就修 runner，不放宽门禁）。ASan 检查只 WARN——
  runner 是否带 libasan 我在这台机器上证实不了，把未验证的前提写成硬失败只会造出没人敢信的红。
- 做红灯对照时又踩到一条同源坑：新失败文案里的 `U+21D2` 在 cp936 控制台抛
  `UnicodeEncodeError`，stdout 缓冲把已跑出的结论整段吞掉，`rc=1` 看似门禁在响，实为门禁被自己的输出打死。
  文案改 ASCII，并在入口加 `contextlib.suppress` 的 `stdout/stderr.reconfigure(errors="replace")`。
- **三向实测**：本机普通运行 `RESULT: PASS` rc=0；`GITHUB_ACTIONS=true` 且无编译器 ⇒ 真红且结论完整 rc=1；
  `GITHUB_ACTIONS=true` 且 MSVC 在 PATH ⇒ 恢复绿 + ASan WARN rc=0。ruff（`F,E9,B,SIM`）全绿。

### r11（D196 处置：用修好的源码重建 Windows 侧 pak 二进制）— 2026-10-12 深夜

用户定案：**本项目只发布 Windows x64（ADR-003），不编译其它平台**，所以只重建 Windows 那两份。

- 新入口：`pak_src/binaries/rebuild_win.bat`（只做转发）→ `.bugreview/pak_rebuild.py`（真正的实现）。
  **全部判据通过才落盘**，任一条红就保持原样退出 1：
  `/W4 /utf-8` 零警告 → `/MT` 静态 CRT（实测产物无 `VCRUNTIME140`/`api-ms-win-crt` 导入）→
  `/Brepro` 连编两次**逐字节相同** → 对 `out/mcloud` 的 4 个真实 v5 `.pak`（含 24 MB `resources.pak`）
  解包→再打包**与原文件逐字节相同** → 与仓库多文件版 `pak_src/*.c` 编出的参考实现**产物相同** →
  x86 与 x64 产物相同。
- 落盘：`pak_msvc64.exe` 193,536 B `sha256 7ab0ae23d2958c13…`；`pak_msvc32.exe` 160,768 B `b8007d96a79d5df5…`。
  清单 `pak_src/binaries/BUILDINFO.json` 记录源码/编译器/旗标/产物/语料哈希，
  **故意不写构建时间戳** ⇒ 同输入重建零 diff（与 `/Brepro` 同一理由：哈希要能当真依据）。
- 包装器改为**首选重建产物**：`pak_src/{pack,unpack}.bat`、`pak_src/binaries/pak-win/{pack,unpack}.bat`；
  在库的 MinGW 那对只在缺失时回退。实测包装器确实选中了 `pak_msvc64.exe`（解包产出 `39800.gz`/`39801.gz`）。
- 顺带查清"重建改变了什么"：旧 MinGW 版对真实 pak **再打包同样能逐字节还原原文件**，
  唯一功能差距是解包时不给 gzip 资源加 `.gz` 后缀（`resources.pak` 里 3,199 个）——它早于仓库
  `pak_get_file_type.c` 的魔数表。即这次重建换来的是"二进制 == 源码" + 源码侧的安全加固
  （D1–D19、D190/D191/D193），不是修复一个"还原错文件"的问题。
- ⚠ 本轮踩到并记入 AGENTS.md 的两条 batch 坑：**`rem` 里写中文会按 OEM 代码页花屏**（.bat 保持 ASCII+CRLF）；
  **把局部变量命名为 `TMP`** 会覆盖 `%TMP%`，cmd 自身的临时文件逻辑被打乱，表现为 cl 返回 0 却不产出文件。
- ⛔ `binaries/pak`、`binaries/pak_arm64`（Linux ELF）**不重建**：不在发布范围（ADR-003），
  且本机没有 POSIX 编译器；`BUILDINFO.json` 里以 `out_of_scope_per_adr003` 明确标注，避免被当成遗漏。

### r10（复核另一位 C 工程师的 `pak_src_fixed/`：D190–D196）— 2026-10-12 深夜

- 他做对的保留：严格别名 UB（U1/U2）、`vsnprintf` off-by-one（U3）、`_snprintf`→`snprintf`（P1）、
  `strcpy`→`snprintf`（O1）、`header_size` 宽度（B1）、`ferror/fclose`（B3）—— 逐项核实成立。
- 修掉他留下的 4 条真实缺陷：
  **D190** v5 头部 3 个 padding 取自脏堆 ⇒ 产物不可复现（对他提交的 `pak.exe` 连打三次，
  偏移 5 为 `01/02/02`）；**D191** 他把 `read_file` 的 `size+1` NUL 当冗余删掉 ⇒ `sscanf`
  堆越界读（ASan `READ of size 77`）；**D192** 无 BOM UTF-8 + CP936 吞换行 ⇒ 警告行号 4/4 条
  指错代码，他的处理是 `/wd4819` 闭掉症状，现改 `/utf-8`；**D193** `version=4` 声明 `[Alias]`
  时静默丢别名表并返回 0（原工具直接 rc=8 拒绝）—— 现与原始工具一致地拒绝。
- 更正 `REVIEW.md` 的结论性表述：§六 承诺的 `Makefile`/`run_test.sh` 从未入库（已补并实测）、
  "本机无 C 编译器"与同 commit 提交的 `pak.exe/pak.obj/*.pak/t_out/` 矛盾（已 `git rm` + `.gitignore`）、
  "cl /W4 零警告"有掩蔽前提、"往返字节级兼容"当时不成立、B2 把承重的 `+1` 说成浪费。
- **D196（架构事实）**：`pak_src/` 与 `pak_src_fixed/` 的 C 源码**不参与任何构建** —— 全仓唯一
  复制 pak 的是遗留 `setup.sh:87-88` 与已按 D97 禁用的 `win_scripts/setup.py:144-149`，且复制的是
  `pak_src/binaries/` 里的**预编译旧版**；`deploy_mcloud.py` 无任何 pak 步骤。已写进 AGENTS.md。
- 判据入库并接进门禁：`win_scripts/verify_sources.py` 新增
  `check_pak_fixed_sources` / `check_pak_roundtrip` / `check_pak_asan`；
  `.bugreview/pak_fixed_verify.py`、`.bugreview/pak_fixed_diff.py`（19 组边界输入新旧差分：
  修前唯一分歧即 D193，修后 `行为不一致: 无`）、`.bugreview/pak_gate_red_control.py`
  （在临时副本上删修复证明门禁能红）、`pak_src_fixed/{Makefile,run_test.sh}`。
- ⚠ 平台边界（实测）：Windows 的 ASan **没有 LeakSanitizer**（`detect_leaks=1` 直接退出）
  ⇒ 本机 ASan clean 只证明无越界，不证明无泄漏；泄漏判据只在 POSIX/CI 侧成立。
- ⚠ D195（`snprintf` 截断 / OOM 下写出空索引却报成功）已修**未门禁化**：触发要 max-path 或 OOM，
  本机造不出真实输入，按纪律标注为"已修未测"。

### r9（第7周期五轮复审：D132 真正落地 + 两处文档虚指修正）— 2026-10-12 深夜

- **D132 单实例互斥**（第7周期才真正实现；档案里此前一直是「⬜ 待跟进」）：
  `Global\MCloudBrowserSetup`，第二个并发实例 `rc=2` 并给出原因。
  判据 `.bugreview/test_mutex_single_instance.py` 带**真 Red**：编译 HEAD 变体（走新加的
  `build_setup_exe.py --source`，不改工作树）证明改动前第二个实例不被挡住 ⇒ Green 的通过有意义。
  实测 Green `rc1=1 / rc2=2`，Red `rc2=1`，四条污染自检全过。
- **D189（我自己引入的自伤，已修）**：互斥体会把**提权自举的子进程**挡住（父持锁并 WaitForExit
  ⇒ 系统级安装直接 rc=2）。修法：子进程带 `--elevated-child` 跳过抢锁。
  实测：父在临界区内时带标记进程照常跑完（rc=1）、不带的被挡（rc=2）。
  ⚠ 本机 `EnableLUA=0` ⇒ 真实 UAC 分支从不执行，这一条仍需在开 UAC 的机器上复验（同 D158/D123 边界）。
- **D188**：第7周期报告把 `.bugreview/gpu_degradation_probe.py` 当现成门禁引用，而它当时只在
  gitignore 的 `.cycle6/cycle6-reverted/` 里。已按本仓纪律重写并入库（不写死端口、临时目录
  finally 删除、页面判据不依赖外网、chrome://gpu 必须读到 GL_RENDERER），实测三场全绿：
  禁用 GPU→WARP(`0x0000008C`) 软件渲染、`--use-angle=swiftshader`→SwiftShader/Vulkan、
  默认对照→合成/Canvas/Video Decode 全硬件加速。首版判据把 WebGL 只认 SwiftShader，
  把 WARP 这条合法软件路径判成红 —— 已改为与默认场景对照 + 按硬件设备号排除。
- **门禁回归**：`installer_arg_test.py` 12/12（含此前跳过的系统级分支，互斥体未破坏两分支）；
  修后量具首次完整跑通：`leak_probe` 4×25 标签漂移 +4.7 MB 且每轮「剩余 page=1」；
  `r4` `instrument_valid: true` + 6 项全绿；K1 中位数 50 ms（噪声带内）。
- 发布物：mini_installer 不变（`27c3236b…`），外层 setup 随包装器改动重打为
  `1302268f8a0101f11e86fda5e98172022a084b67bfba2c69ef2af0d2fa9c7af3`；
  `release_chain_check.py` 三处一致。

### r8（第7周期收口：遗留清零 + 重打包 + 干净安装复验）— 2026-10-12 深夜

- **D186 源码树身份断言**（新 `win_scripts/tree_check.py`）：`CR_DIR` 默认值历史上指向
  **M151 回滚参考树**，而两棵树都有同名注入目标 ⇒ 忘设变量时注入在旧树上"成功"、编译用新树，
  定制静默丢失。现在 `deploy_mcloud.py` 开工第一件事就是比对 `<CR_DIR>/chrome/VERSION` 与
  `KERNEL_MAJOR`，不符 exit 114 并点名原因与修法。Red：指向 M151 树 → rc=114；
  Green：指向发布树 → 打印 `源码树：M155（155.0.8059.40）`。
- **D187 setup 文件版本元数据**：此前实测 `FileVersion/ProductVersion = 0.0.0.0`。
  用临时 `AssemblyInfo.cs` 同批编译实现（**不是** `csc /version:` —— 那是"打印编译器版本并退出"，
  返回 0 却不产出文件，见 D164）。`package_m155.py` 现在会**实测核对** VersionInfo，
  不符即 FAIL；复现性未受影响（同名不同目录两次 SHA 一致）。
- **D185**：安装器两处 `Process.Start` 未 Dispose；我修 D184 时新写的 `gpu_identity()`
  漏关 WebSocket（审计别人泄漏时自己造了一个）——均已修。
- **重打包**：增量只有 3 步（`mini_installer_archive` → `packed_files.res` → `LINK`），
  `chrome` 本体未过期 ⇒ 本轮不涉及 crubit，不会撞 D173 的管道竞态。
  新发布物：setup `a61655ddba2cbadd27522cbc970232c3b2997c8112d846a059624e5356b13019`（127,585,792 B）、
  mini_installer `27c3236b82454d6dba4a0df53584d37185b835f8748fe517c86ec6c418faef68`（127,559,168 B）。
- **干净安装复验**（真实改动本机安装实例）：卸载 rc=19 → 安装 rc=0；清单落版本目录且与仓库
  逐字节一致（`a071260c8c2c374f`）；根目录无残留、无 `new_chrome.exe` 暂存件；
  安装版 `chrome.dll`(`e7679fb5…`) 与根 `chrome.exe`(`86b588a4…`) **与本轮构建同哈希**（判新旧只认哈希，
  安装目录 mtime 来自 7z 归档）；对安装后的二进制回显 **`enable 50 / disable 2`**。
  `release_chain_check.py` 三处一致 ⇒ 第 4 次发布链断裂闭合。
- ⚠ 卸载器再次删掉任务栏固定项，仍需人工重钉（无 API 可恢复）。
- 本轮**没有重新编译内核代码**（源码侧改动全在脚本/文档/清单注释），
  所以 `chrome.dll` 与 r7 同一份；D172 的"实测消失 + 正向对照"结论继续有效。

### 第7周期（源码侧，未重打包）— 2026-10-12 晚

- **内存/CPU/GPU 全局审查**（D177–D184，详版 `docs/tasks/bug-review-cycle7-report.md`）。
- 口径更正：52 项 feature 中上游默认已启用的是 **15 项**（不是 14），真正新增生效 **35 项**（不是 34）。
  漏掉的是 `AsyncDns`（默认值写在 `#if BUILDFLAG(...)` 里，旧抽取器读不到就静默放过）。
- 翻案两条"禁用"：`D3D12VideoDecoder`、`SkiaGraphite` 在 Windows 上上游默认即 DISABLED
  ⇒ 它们是防 Finch 远程下发/防上游翻默认的 **pin**，不是当前生效的禁用手段（D178）。
  拖拽冻结缓解的"4 项禁用"归因不成立：其中 `ReduceHardwareVideoDecoderBuffers`
  在本构建**根本不存在**（`#if IS_CHROMEOS||IS_LINUX`），另 3 项默认即禁用（D182，定案不变）。
- 实测：无泄漏（25 标签×4 轮开合，轮间驻留漂移 +0.7 MB）；50 标签静置 CPU **0.01 折合核**
  （D170 的 ABOVE_NORMAL 无可见空转代价）；渲染走 **ANGLE D3D11 + 独显 0x00002860**。
- 新工具：`.bugreview/guard_audit.py` + `.bugreview/feature_decl.py`（平台有效默认值与守卫可达性，
  三条正例可失败）、`.bugreview/release_chain_check.py`（发布链三处指纹一致性；本周期改注释
  触发第 4 次断裂，脚本现为 RED，需重打包闭合）、`benchmark/tools/mcloud_flags_lookup.ps1`
  （按加载器口径查清单，`.ps1` 计数 44→45）。
- 修掉的假绿判据：`leak_probe` 实例死掉仍 PASS（D179）、标签没开成也 PASS（D180）、
  `r4` 内存量具坏了仍 PASS（D181）、三个 bench 对安装版误报"内置优化不生效"（D183）、
  `gpu_probe` 把 feature 名当 ANGLE 后端（D184）。

### r7（第6周期收口：D170/D171/D172 落地 + 重编重打包 + 干净安装复验）— 2026-10-12 下午

- **D170（High，CPU/多核）**：`BrowserProcessAboveNormalPriority` 单独启用**完全无效**——它只把根进程
  标成 `kUserBlocking`，而 `kUserBlocking → ABOVE_NORMAL_PRIORITY_CLASS` 由
  `UserBlockingAboveNormalPriority` 决定（`base/features.cc:205` 默认禁用、
  `base/process/process_win.cc:299-304`，上游注释要求两者成对）。补齐后实测
  **安装版与开发树根进程 `PriorityClass` 均为 `AboveNormal`**（gpu-process 同升、renderer 仍 `Idle`）。
  副作用是同时解除 Windows 11 的 EcoQoS（`process_win.cc:283-289` 以"是否为 kUserBlocking"为判据），
  本机 8P+16E ⇒ 浏览器不再被调度到能效核；代价是功耗/发热上升，与 ADR-002 一致。
- **D171（口径）→ 第7周期 D177 修正**：52 项 feature 中 **15 项在 Windows 上上游默认即 ENABLED**（净效果为零，属显式钉住；第6周期数成 14 项是漏了默认值写在 `#if` 里的 `AsyncDns`），
  此前只标注 2 项 ⇒ 真正新增生效的启用项是 **35**，别按 50 理解收益（第6周期的 14/34 由 D177 更正）。
- **D172（中，安装/更新）**：`RegisterApplicationRestart` 命令行上限 1024 字符，我们的
  `--enable-features` 单项约 1.4 KB ⇒ `E_INVALIDARG`，上游只 `LOG(WARNING)` 后继续 ⇒
  **构建/安装/门禁全绿而浏览器不被 Windows 更新恢复**。新增 `win_scripts/apply_restart_cmdline.py`
  在 `GetRestartCommandLine()` 剔除三项直传开关（加载器每次启动重注入，无需接力）。
  Red 硬证据：r6 旧二进制 `chrome_debug.log` 1998 B 内含
  `chrome_browser_main_win.cc:832] Command line too long for RegisterApplicationRestart: …`
  （该条命令行实测 **1911 字符** > 1024）。
  **Green + 正向对照（16:33–16:55）**：① 对安装后的新版二进制用同一采集方法
  （`--enable-logging --log-file --v=1` + 一次性 profile）启动，日志 **135,082 B**（证明日志通道开着）
  而该 WARNING **0 次**；② 同一份二进制只多加一个 1300 字符的未知开关，WARNING **复现（hits=1，
  日志 86,166 B）** ⇒ 判据可失败，"0 次"不是量具坏了的结果；③ 算术核对：按现剔除规则重算
  修剪后命令行 **≈284 字符** < 1024。⚠ 我第一版用 `--v=0` 采到的是 **0 B 空日志**，
  "空日志 + 0 hits"属空数据上的缺席判据，不能当证据——已改为"非空日志里 0 次 + 正向对照"。
- **构建环境（D173）**：`autoninja` 满并行时 `cc_bindings_from_rs.exe` spawn `clang-format.exe`
  撞 `os error 231 = ERROR_PIPE_BUSY`，三次尝试同一目标同一错误；`clang-format` 本体正常、
  同一目标 `-j 1/-j 2` 一次通过 ⇒ 判定为 spawn 竞态而非代码问题。
  **两段式修法**：先 `ninja -j 2` 做掉 12 个 `*_crubit_action`，再全速 `autoninja`（6830 步，60 分钟，
  其中 `chrome.dll` ThinLTO 链接约 10 分钟、24 核打满、RSS 13.4 GB）。
- **发布物（新）**：setup **127,589,888 B / `8e59c4580e95bef278bef517da210c6b104598ad5ba2152bfda70bfef3d5d746`**；
  mini_installer 同步重打。载荷 `mcloud_flags.txt` = `b737605e6d9806d3…`（LF, 17,194 B），
  与仓库/构建树/暂存目录四处一致 ⇒ 上一轮"手工 copy 进安装目录"造成的断链（D175）由本次真装闭合。
- **干净安装复验**（非交互口径）：卸载 rc=19 → 全新安装 rc=0（13 s）→ 根 exe 155.0.8059.40、
  flags 落版本目录且与仓库逐字节一致、根目录无残留、无 `.new.exe` 暂存件、无 setup/mini_installer 驻留、
  默认浏览器链自愈（`TargetExists: n/a → yes`）、快捷方式 1 → 3；对**安装后的二进制**回显
  **`enable 50 / disable 2`**、`D3D12VideoDecoder` 与 `SkiaGraphite` 禁用完好。
  ⚠ 任务栏固定项仍被卸载器删除且无 API 恢复，需手工重钉。
- 门禁：`verify_sources` PASS（`.ps1` 44）、`flag_stability` PASS、`flags_lint`（第6周期新增闸门）PASS、
  `test_build_win_preflight` PASS、`installer_arg_test` 12/12 PASS。
  ⚠ `installer_arg_test` 出现过一次 `污染.用户级安装目录` 红（空目录指纹瞬态变化，事后 mtime 仍是旧值、
  无法复现也未归因）；已把明细改成打印**变化的字段**，复跑 5 次全绿。
- 我自己本轮的两处操作失误已登记：**D174**（按进程名机器级清理，误杀用户其它软件的
  `crashpad_handler`，无数据损失）、以及 `Start-Process -PassThru` + 重定向取不到 `ExitCode`
  的采集缺陷（两次复现，改为 `cmd /c` 读 errorlevel 的路上又因 GUI 程序等待而挂住 —— 见 D158 备注）。


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

### r4（修 D105/D106：安装版根本不携带 mcloud_flags.txt）— 2026-10-11

- **D105（Critical，发布阻断）**：`chrome.release` 把 `mcloud_flags.txt` 登记在
  `%(ChromeDir)s`（Application 根），而 `setup.exe` 对根目录只搬固定三件套
  （chrome.exe / chrome_proxy.exe / chrome.VisualElementsManifest.xml）——
  文件被打包进 `chrome.7z`（`-mx0` 未压缩，包尾能直接看到它的正文）却**永不安装**。
  用 `--system-level` 干净安装 + `--verbose-logging` 取证：`C:\Program Files\Chromium\Application\`
  下只有那三个文件，整棵树搜不到 `mcloud_flags.txt`。
  ⇒ **r3 及更早的每一个安装包，在干净机器上都不带运行时优化清单**（53 项 feature + 3 项开关全丢），
  而且不报错。此前所有"包里有没有这个文件"的判据都没能发现：搜 chrome.7z 字节串是无效量具（D102），
  验打包暂存目录也只证明"进了包"，不证明"装得出来"。
- 修复三处：① `apply_installer_payload.py` 改为登记 **`%(VersionDir)s`**（版本目录整目录搬迁，必然落地），
  并做成正文比对式升级器（树上旧的 ChromeDir 条目就地改写）；② 加载器升 **v7**：exe 同目录读不到时
  回退 `exe_dir\<版本号>\mcloud_flags.txt`（目录须含 chrome.dll，多版本取最新），开发树行为不变；
  ③ `package_m155.py` 门禁新增"必须登记到 VersionDir + 暂存目录里必须在版本子目录 + 递归 sha256 比对"。
  第一次编译失败在 API 假设上：M155 的 `base::Version` 没有 `NewFromString()`/`GreaterThan()`。
- **D106（Critical，工具）**：`flag_runtime_state.py` 收尾是
  `Get-Process chrome | Stop-Process -Force`——机器级杀进程，门禁每跑一次就把用户正在用的浏览器
  （含未保存表单）一起干掉；它是 D52/D55 那批探针里唯一漏改的一个。改为按 profile 叶子名筛 PID、
  6 轮杀到干净、残留即 SystemExit；用**诱饵实例**验证修复后其存活（修复前必被杀）。
- 端到端复验（干净系统安装）：`Applicationm.0.8059.40\mcloud_flags.txt` 8,186 B 且
  sha256 与仓库一致；对**安装后的二进制**跑运行时探针得 `enable 51 / disable 2`；测试安装已卸载、
  用户级安装未受影响。
- 产物：**127,549,952 B**，SHA256 `54fc59b5ccd3afc43c27f113206ededb8fc0db6c04825f88c53493afd1b228d1`
  （沿革：`0602cafa…` = r3，带 D105 已知缺陷；`54fc59b5…` = r4 修复后）。
- 新增纪律（AGENTS.md）：**发布前必须做一次干净安装复验**，只看门禁绿灯不足以证明安装包正确。

### r5c（D120：包装器改为就地更新，并校验默认浏览器与快捷方式）— 2026-10-11 深夜

- 用户反馈"安装程序先卸载会清掉默认浏览器设置和任务栏快捷方式"。逐链实测**更正了前提**：
  默认浏览器**没丢**——`HKLM\SOFTWARE\Classes\ChromiumHTM\shell\open\command` 与
  `StartMenuInternet\Chromium\shell\open\command` 都已被系统级安装重登记到新路径，
  `UserChoice(http/https)=ChromiumHTM` 仍解析到存在的 exe；真正丢的只有任务栏固定项
  （`User Pinned\TaskBar` 只剩 File Explorer）与开始菜单 lnk。
- 真因是**换了安装位置**（先卸用户级、再装系统级），而包装器首版按命令行参数决定装到哪、
  不检测已有副本 ⇒ 误用一次就会留下两份安装、并把 pin 指向死路径（缺陷 D120）。
- 改为 **Google Update 式就地更新**：`DetectInstall()` 以"根 chrome.exe 是否存在"判定
  （注册表有卸载空壳，不可靠），两处都在时以**默认浏览器当前解析到的那份**为准，再退而取版本更高者；
  只有显式 `--system-level` / `--user-level` 才允许换位置，且换之前打印后果警告。
- 新增**更新前快照 / 更新后复算**：默认浏览器解析目标与各 .lnk 指向；链"从好变坏"判 FAIL，
  pin 指向死路径只 WARN 并逐条列出。**不做任务栏 pin 自动恢复**——Windows 7 之后没有公开 API
  （`ITaskbarList::AddTab` 只是活动按钮），写 `User Pinned\TaskBar` 属非公开做法，按用户决定不采用。
- 健壮性：`CheckAssociations` 的键访问加守卫、Main 的兜底 catch 补上栈信息（未预期异常不得
  让 GUI 连失败原因都显示不出来）。
- 实测：无参数时输出"检测到已安装副本 C:\Program Files\Chromium\Application → 就地更新这一份"；
  只有系统级却传 `--user-level` 时输出 WARN 并说明后果。上游 setup.exe **不支持自定义安装目录**，
  所以"完整安装路径"的新增代码段尚未在真机上跑过（见待办）。

### r5b（安装面：修 D119 运行中升级静默不生效 + 新增外层安装器）— 2026-10-11 深夜

- **D119（High，发布相关）**：**浏览器正在运行时双击 mini_installer，安装器返回 0 但更新完全不生效**。
  实测（151→155 系统级）：装完根 `chrome.exe` 仍是 `151.0.7922.99`，`new_chrome.exe` 被暂存后无人消化，
  重启后 `chrome://version` 仍是 151。机理：载荷走旁路新版本目录不需要覆盖，但根启动桩是被锁的映像，
  上游因此暂存为 `new_chrome.exe` 并写一条 `rename-chrome-exe` AppCommand，而**系统级安装的收尾改名
  整个委托给 Google Update**（`upgrade_util_win.cc:505-506`）——我们不发布它，所以这一步永远没人执行。
- 新增**外层安装包装器** `installer/mcloud_setup.cs` → `mcloud_155.0.8059.40_win64_setup.exe`
  （构建脚本 `win_scripts/build_setup_exe.py`，已接入 `package_m155.py`）：
  按可执行文件路径识别本产品实例（读不到路径就不算目标）→ `WM_CLOSE` 优雅退出、30 秒超时才强制结束 →
  运行内嵌 mini_installer → **复验根 chrome.exe 版本 == 包内版本且无 `new_chrome.exe` 残留** →
  删临时目录并断言无 setup/mini_installer 驻留 → 自动重启浏览器。
  开关：`--system-level`（自举提权）/ `--no-launch` / `--list-only` / `--quiet`；
  退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。**给用户的一律是 setup 那个**。
- 上游 setup.exe **没有任何进度 UI**（`ProgressCalculator::Calculate()` 除单元测试外无消费者），
  也没有静默开关，所以"要安装界面"只能由外层提供；本轮按用户决定**只做阶段状态文字，不做进度条**。
- 验收与对照：`.bugreview/setup_wrapper_test.py` 在同一 151→155 现场下，包装器路径
  **1 个 WM_CLOSE 关掉 8 个实例（未动用强制结束）**、根 chrome.exe = 155、`new_chrome.exe` 无、
  151 目录被正常删除、重启后 `actually_running = 155.0.8059.40`、零进程驻留、用户自己的安装未受影响；
  `--list-only` 只报告不关闭，且系统级模式下用户级实例完全不在集合内（首版会误并进来，已收窄）。
- 发布可复现性：旧 csc 不支持 `/deterministic` 导致同一源码两次编译 SHA 不同
  （`b0bc7652…` → `96376b3c…`），改为优先 VS Roslyn csc + `/deterministic+` 后连跑两次打包
  SHA 稳定。setup 发布物：127,583,232 B / `106a245452539057685e5fe336c06aae360699933c117b38c1feaa7e0d575e4e`。
- 浏览器本体未变：`mcloud_155.0.8059.40_win64_mini_installer.exe` 仍是
  `17b3151379dfc1091efe10a05825ce433c58895a27f6d925025dfbbd7517f3b7`（r5），不需要重测浏览器行为。

### r6（第5周期收口：让发布物重新跟上源码 + D121 首次可执行验收）— 2026-10-12 凌晨

本轮不找新 bug，只做两件事：把第5周期改在源码里的东西**打进发布物**，以及给
"改了但从未执行过"的安装器分支补一条**能失败**的验收。

- **触发原因**：第5周期把 D121–D129（安装器）、D142（flags 清理）、D144（PGO 路径）改在源码里，
  但产物停在 r5 —— 实测时间差可钉死：源码 mtime `00:19 / 00:27 / 00:29`，提交 `00:58`，
  而 `installer/out/*.exe` 是前一日 `22:42–22:46`、根 setup 是 `23:04`。
  **用户拿到的包不含这些修复**，且已安装浏览器里的 flags 仍是旧的 `61b7670856ed`
  （仓库与构建树都已是 `d71d988ca2d2`）。
- **载荷重打**：清理后的 `mcloud_flags.txt` 此前只复制到 `out/mcloud/`，**没进 `chrome.7z`**。
  `autoninja -C out/mcloud mini_installer` 实测只有 3 步（archive → RC `packed_files.res` → LINK），
  **不触发任何重编译**（先跑 `ninja -n` 数过步数再动手，避免误开全树重编，见 D74）。
  重打后打包暂存目录（= 载荷真身）里的 `mcloud_flags.txt` 与仓库逐项一致。
- **D130 修**：`build_setup_exe.py` 找不到支持 `/deterministic` 的 Roslyn csc 时不再静默退回旧 csc，
  而是 exit 113 并给出两种修法；新增 `--allow-nondeterministic`（仅供本机排错，发布路径禁用）。
  `package_m155.py` 改为**无条件转印**子编译器日志——"用了哪个编译器 / 产物是否可复现"
  旧写法只在失败时打印，成功路径整段丢掉，随后照样写 `.sha256` 与发布说明。
- **D121 / D129 第一次有可执行验收**：新增 `.bugreview/installer_arg_test.py`。
  它**没有**采用交接文档建议的"给 `setup_wrapper_test.py` 加一条不带 `--system-level` 的用例"：
  那会真的往 `%LOCALAPPDATA%\Chromium\Application` 装一份浏览器，而注册表里恰好有一条指向该路径的
  `GpuPreference=1`（= 省电 = 优先**核显**，缺陷 D154，本轮实测该条目仍在、目标 exe 已不存在），
  于是测试会把这台机器上的用户级安装钉在 Intel 核显上——而核显正是 D3D12 绿屏那一侧，
  与所有既有 GPU 基准不可比；收尾卸载本身又是一次真实安装变更（D99 纪律）。
  改为**假安装包录参数**：stub 把收到的 argv 写进文件，不碰任何安装位置。实跑结果（Red→Green 双向）：
  - A（HEAD 源码 + `--user-level`）→ stub 收到**空参数**；包装器 rc=1（用户目录本来没装东西，
    复验必须判不过，而不是被"目录里文件还在"蒙过去）；
  - A'（`68838c1` 硬编码那一版跑同一条用例）→ stub 收到 `--system-level`。
    **没有 A' 这条，A 的通过毫无意义**——它证明判据有区分力，不是"两边都恰好绿"；
  - B（stub 以 rc=3 退出）→ 日志出现"安装器自身返回 3"、包装器 rc=1（D129 分支被真实触发）；
  - C（系统级分支）本轮**按设计跳过**：`C:\Program Files\Chromium\Application` 下有 13 个
    正在运行的本产品实例，执行会先 `WM_CLOSE` 掉用户正在用的浏览器（D52/D55 禁止）。
    判据整体因此判 **PARTIAL / exit 2**——不允许用"两半通过"冒充全绿；
  - 四条污染自检全部成立：用户级 / 系统级目录指纹前后逐项一致、实例数不变、无残留 `MCloudSetup-*` 目录。
- **新发布物**：
  - `mcloud_155.0.8059.40_win64_setup.exe` 127,545,856 B / SHA256 `9600c425cfd632541110ad600adecc06137adae15bfdbe3700fc347224437d43`
  - `mcloud_155.0.8059.40_win64_mini_installer.exe` 127,519,744 B / SHA256 `488e604be2f4ab8f54f74649124858c1f5117606e23eebf69bde3fd5bc87ebc6`
  - sidecar 用 `sha256sum -c` 双双 OK；**装配校验做到底**：从发布出的 setup.exe 里把内嵌的清单资源
    取出来算哈希，与 `mcloud_..._mini_installer.exe` 逐字节一致（`MATCH=True`）。
    这比"setup 体积略大，应该是内嵌了"强得多（同族教训见 D102"在压缩归档里搜文件名字节串"）。
  - 发布形态实跑 `--list-only`：rc=0，两个安装目录零改动。
    ⚠ 顺带**收窄 D133 的口径**：winexe 形态在 stdout 被重定向时**是有输出的**（本轮实测 149 B 正文），
    所以 `--list-only` 对脚本/CI 并不哑，只有**双击**的用户看不到——D133 的严重度应按此下调。
- **仍未做（需授权）**：干净安装复验。要把新版装进 Program Files、对**安装后的二进制**跑
  `flag_runtime_state.py` 断言回显 **`enable 50 / disable 2`**（口径已随 D170 变更：D142 后为
  49+2、更早为 51+2；**不要再按 49+2 判新包**）
  再卸载；且必须先关掉正在运行的浏览器 ⇒ 同时这也是补齐 D121 系统级分支（用例 C）的唯一路径。
- ⚠ **r6 的"干净安装复验"对新 flags 已不再成立（2026-10-12 第6周期补充）**：r6 之后
  `mcloud_flags.txt` 又变了（D170 新增 `UserBlockingAboveNormalPriority`、D171 pin 标注），
  但**打包暂存目录里的载荷仍是旧内容**（`d71d988ca2d2ab`，仓库侧已是 `b737605e6d9806`）。
  ⇒ 机器上安装实例的 flags 现在**无法从任何发布物复现**（同 D109 遮蔽形态）。
  修复顺序：`deploy` → 重跑 mini_installer 打包（刷新载荷）→ 重新做干净安装复验。
  期间**不要**手工把新 flags 拷进 `Program Files` 下已安装的版本目录——那会造出
  "跑着的 flags 装不出来"的偏差，正是 D109 当年被遮蔽的原因。
- 历史哈希不回改：r3 / r4 / r5 的记录保持原样。mini_installer 沿革：
  `0602cafa…`=r3（带 D105 缺陷）→ `54fc59b5…`=r4（修 D105）→ `17b31513…`=r5（修 D109）→
  `488e604b…`=r6（载荷跟上 D142 清理 + 安装器修复进入发布物）。

### r5（第4周期五轮实操收口：修 D109 加载器路径优先级 + 量具假绿族）— 2026-10-11 晚

本轮口径是**实地操作**而非脚本反馈：每轮真启动独立 profile 实例，真拖窗口、真杀 GPU/渲染进程、
真下载、真放 1.18 GB 本地视频。产物：`docs/tasks/bug-review-cycle4-report.md`，
缺陷详版 `docs/tasks/bug-review-pak-src-defects.md` 第4周期段（D107–D118）。

- **D109（High，产品）**：加载器 v7 以 **exe 同目录**为第一候选，而上游判定"程序目录"的依据是
  **chrome.dll 在哪**（`main_dll_loader_win.cc:175-191`）——安装版根目录只有 4 MB 启动桩。
  于是一份残留的 `Application\mcloud_flags.txt`（本机确有，D104 期间手工 copy 留下）会**永久、
  静默地**压掉安装包投递的正式文件；而 `flag_runtime_state.resolve_flags_path()` 照抄同一顺序，
  门禁读被压制的那份、断言那份 ⇒ **全绿而线上跑旧配置**。
  修复：加载器 **v8** 改以 `base::DIR_MODULE` 为第一候选（exe 目录次之、最新载荷目录兜底），
  oracle 同步改序并打印**整条候选链 + 各自 sha256 + 谁压住谁**。
  判据可证伪：`.bugreview/loader_precedence_test.py` 用硬链接拼出安装同形沙箱（根目录无 chrome.dll）、
  两份文件各带不同探针开关真启动一次 —— **v8 前判 `ROOT`，v8 后判 `VERSION`**。
- **量具假绿/假红族（D107、D111–D118）**：本轮 12 条里只有 1 条是产品缺陷，其余全在量具自身，
  且两类都出现过：① 空页面上"不存在型"断言恒成立（D107，chrome://gpu 的正文在 shadow root 里，
  `body.innerText` 实测 0 长度）；② "reload 后有文本即算恢复"被**错误页**满足（D112，
  同条还包含把 `chrome://media` 拼错读成"上游删了这个页"——真名 `chrome://media-internals`）；
  ③ `INPUT` 结构体多一个 pad 字段 → x64 上 48≠40 → `SendInput` 恒 `lasterr=87`，
  拖拽三项判据被记成产品失败（D111，对照实验 cbSize 40 成功 / 48 报 87）；
  ④ `/json/new?url=X` 丢参数使标签停在 about:blank（D113）；⑤ 截图失败掀翻整轮已跑完的判据（D114）；
  ⑥ 泄漏判据拿"开 15 标签时的峰值"比"基线 9 进程"，数学上永不成立（D115）；
  ⑦ 探针页用 `body.innerText=` 打标记，赋值会替换全部子节点、把要点的 `<a download>` 自己删掉（D117）。
- **五轮结果**：R1 真实 DOM 17/17（chrome://version 命令行含 D51 形式 params；chrome://gpu
  Canvas/WebGL/Video Decode/Compositing/Rasterization 全 Hardware accelerated、Graphite Disabled）；
  R2 8/8（真拖拽位移 132×66 px、期间 rAF 159 帧、`IsHungAppWindow=False`；杀 GPU 进程 1 秒内重建
  且页面与网络栈存活；杀被测标签渲染进程后 reload 恢复）；R3 11/11（**2560×1440 H.264 播 8 秒
  483 帧 0 丢帧**、真 PiP/全屏、真实下载落盘、printToPDF 8,459 B、四 codec 能力查询全 supported）；
  R4 6/6（三轮 15 标签开合：峰 33/33/33 进程、谷 22/22/22、谷句柄 2273/2281/2286、
  谷私有内存 1046/1027/1064 MB —— **跨轮零累积**；关窗残留 0）。
- **一处量化过的取舍（不是缺陷，但留数）**：`TransientKeepAlivePolicy` 关掉后同一探针下
  关标签后的驻留从 **22 进程 / 1.05 GB 降到 12 进程 / 0.68 GB**（约 +10 进程、+360 MB 的代价换重开零冷启动）。
  上游在浏览器测试里默认禁用它，理由正是 *"delays renderer process cleanup"*
  （`chrome/test/base/in_process_browser_test.cc:381-385`）。按 ADR-002 暂维持启用。
- 被证伪的四个怀疑（避免重复走）：冻结开关挡后台标签加载 ✗（6/6 正常加载）、
  GPU 崩溃后缺 `<h1>` 是渲染缺陷 ✗（该站改版后正文本就没有 h1）、
  上游删除 chrome://media ✗（URL 写错）、命令行 chrome:// 启动页被顶掉是本分支缺陷 ✗
  （`url_util.cc:85-89` 有意只放行 web-safe/`file:`/`about:blank`）。
- 产物：**127,564,288 B**，SHA256 `17b3151379dfc1091efe10a05825ce433c58895a27f6d925025dfbbd7517f3b7`
  （沿革：`0602cafa…` = r3 带 D105 缺陷；`54fc59b5…` = r4 修 D105；`17b31513…` = r5 修 D109）。
- 文档口径更新：AGENTS.md（v8 路径规则 + 实操量具清单）、规范 §4.1.1（新增两条【必须】：
  DIR_MODULE 优先、文本存在性≠内容正确性）。

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
