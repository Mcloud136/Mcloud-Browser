# bug-review 缺陷档案 — pak_src（2026-10-08，第一轮深度审计）

审计对象：`pak_src/`（独立 C 工具，Windows 可执行）。方法：逐行审查 + MSVC /fsanitize=address 运行时 + 畸形输入语料 + 真实 pak 往返基线。
环境：VS2026 BuildTools MSVC 14.51.36231，/fsanitize=address 构建；测试输入 `out/mcloud/chrome_100_percent.pak`（v5，往返基线字节一致 ✅）。

## 运行时已证实（Red 证据，ASan/退出码）

### D1 pak_header.c:3-23 pakParseHeader — 无最小长度校验的堆越界读
- 严重度: **High**（崩溃）
- 根因: 读取头部字段前不校验缓冲实际大小；4 字节畸形文件触发
- 证据: `F1-tiny-header-oob exit=86, SUMMARY: heap-buffer-overflow READ of size 2 @ pak_header.c:8 in pakParseHeader`
- 修复: pakParseHeader/pakUnpack/pakGetFiles/pakGetFile 传入并校验 `size`（≥头+表），调用链同步更新。

### D2 pak_pack.c:144 sscanf("%u=%s") — 无界写栈溢出
- 严重度: **Critical**（可利用的栈溢出）
- 根因: `%s` 不限宽写入 `fileNameBuf[260]`；恶意/损坏 index 行 → 溢出
- 证据: `F4-index-longname exit=0xC0000409 (FAST_FAIL_STACK_BUFFER_OVERRUN, /GS 哨兵捕获)`
- 修复: `"%255s"` 限宽 + 校验 sscanf 返回值==3；返回码缺失的 count 复位。

### D3 pak_file.c:32-35 pakPackFiles — rc==0 时 `(pakResFile-1)->size` 越界读；alias memcpy(dst,NULL,0) UB
- 严重度: **High**
- 证据: `F5-zero-resources exit=86, heap-buffer-overflow READ of size 4 @ pak_file.c:33`
- 修复: resource_count==0 直接返回错误；aliasSize==0 时跳过 memcpy。

### D4 pak_pack.c:115-127 — strstr 未判 NULL + 指针序未校验 → 空基址 OOB 读
- 严重度: **High**
- 证据: `F6-missing-res exit=86, access-violation @ 0x0b in countChar（[Resources] 缺失 → NULL+13）`
- 修复: 判空返回 BROKEN_INDEX；`pakAliasIndex >= pakEntryIndex` 校验；countChar 长度改为带符号检查后转无界。

### D5 pak_header.c:51 与 pakCheckFormat — 32 位算术回绕 + 无单调性校验
- 严重度: **High**（越界写/4GB 假 size 写文件；构造 F3b 重验）
- 证据: F2 中 `(rc+1)*6` 回绕致大小检查被绕过（本次侥幸被 offset 检查拒绝）；非单调 offset 目前被静默接受（F3a 无效用例但代码路径确认）
- 修复: 检查改 64 位算术；entry offset 单调递增校验；`size<offset`→`size<=offset` 语义保留 + `offset[i]>=offset[i-1]`。

### D6 pak_file_io.c:3-31 readFile — calloc 失败路径 **句柄泄漏**；fread 返回值未检查；ftello 未检查；>4GB 截断
- 严重度: **High**（资源泄漏 + 静默数据损坏）
- 根因: 错误路径缺 fclose；短读未处理
- 修复: 失败路径 fclose；校验 fseeko/ftello≥0、fread==size；size>UINT32_MAX 拒绝。

### D7 main.c:282-283 strcpy 无界拷贝入 path1/path2[PATH_MAX]
- 严重度: **Medium**（需超长命令行参数；本地利用面小，仍为溢出）
- 修复: `_snprintf_s(..._TRUNCATE)` 或 strncpy+终止。

### D8 main.c:158-165 pakUnpackPath — 头/格式检查失败路径 **不释放 pakFile.buffer**（整文件缓冲泄漏）
- 严重度: Medium（进程即退，影响小，但属明确泄漏）
- 修复: return 前 freeFile(pakFile)。

### D9 main.c:235 pakPackIndexFile — 失败仍打印绿色 "Packed"（错误报告逻辑缺陷）
- 严重度: Low。修复: 仅 returnCode==0 时打印成功。

### D10 pak_pack.c:43/66 sprintf 无界写 pathBuf[PATH_MAX+2]（outputPath+文件名拼接溢出）
- 严重度: Medium-High（深路径即触发）。修复: snprintf 限宽并校验。

### D11 pak_get_file_type.c:22 `file.size > identifer.size` 应为 `>=`（等长内容误判类型）
- 严重度: Low（正确性）。修复: `>=` + `file.buffer==NULL` 防护。

### D12 main.h:24-27 mainCRTStartup — CommandLineToArgv* 返回 NULL 未判空 → NULL argv 传 main
- 严重度: Medium（分配失败即空指针解引用）。修复: 判空返回错误码。

### D13 main.c:172 ANSI 转义串拼写错误 `\033[1;32\nm`（输出乱码，证据：F3 运行输出显示 "mUnpacked"）
- 严重度: Low。修复: `\033[1;32m`。

### D14 main.c:99-100 等 printHelp/Version/Chromium：`strcpy(selfName, ptr+1)` 重叠拷贝 UB；printf 传多余参数
- 严重度: Low。修复: memmove；去掉多余参数。

## 代码面确认无问题项
- 结构体布局实测与 pak v5/v4 规范一致（V5=12/V4=9/Entry=6/Alias=4）
- 真实 v5 pak 往返字节一致（正向功能基线健康）
- pakParseHeader 的 v4/v5 分支、writeFile 返回值检查正确

### D15 pak_file.c:53-60 pakGetFile — 别名查找循环 aliasPtr 永不前进（功能性缺陷）
- 严重度: Medium（latent：该 API 目前无调用方，但语义错误——永远只比较第一条别名）
- 修复: 循环末尾 `aliasPtr++`

### D16 pak_defs.h:7-8 MSVC ftello/fseeko 映射到 32 位 ftell/fseek — >2GB 文件截断
- 严重度: Medium。修复: 映射 `_ftelli64/_fseeki64`，readFile 校验返回值并拒绝 >4GB。

### D17 pak_pack.c pakUnpack — 每个资源 writeFile 返回值被忽略（静默失败）
- 严重度: Medium。修复: 失败即中止返回 false。

### D18 pak_pack.c pakPack — 极短 index 文件（<10 字节）读越界候选
- 严重度: Medium。修复: 入口校验 `pakIndex.size >= sizeof("[Global]")`。

### D19 main.h mainCRTStartup — CommandLineToArgv* 失败未判空
- 严重度: Medium。修复: 判空返回 34。

### D21 chrome_main_delegate.cc 注入加载器（v1）— 合并顺序与 FeatureList 首条生效语义冲突
- 严重度: **High**（正确性：用户带参覆盖被内置项静默压制，与注入器注释声称的"用户优先"相反）
- 根因: v1 将内置项拼在用户条目前；`base::FeatureList::RegisterOverride` 用 try_emplace（首条生效，feature_list.cc:1261-1264 注释明确）
- 修复: 注入器 v2 — 用户列表置前；已升级树内加载器并重编译验证

### D22 加载器 v1 — 每行累积 AppendSwitchASCII：O(n²) 字符串累积 + ~60 个重复开关
- 严重度: Medium（性能/命令行膨胀）。修复: v2 单趟聚合，enable/disable 各追加一次

### D23 加载器 v1 — ReadFileToString 无上限
- 严重度: Medium（健壮性：异常大文件在每进程启动时全量读入）。修复: v2 改用 ReadFileToStringWithMaxSize(1MiB)

### D24（修复开发过程记录）pak_pack.c v2 reserve 指针回写遗漏 — 自查测试捕获
- 现象: 真实 v5 pak 解包 UAF（realloc 后旧指针）；修复后 8 组畸形语料 + 3 组往返全绿
- 意义: 证明回归测试体系（ASan + 真实 pak 往返 + 畸形语料）能捕获修复自引入的回归

### D33 inject_flags_loader.py（v2 首版）— 自动补 include 使用过期头路径
- 严重度: High（自引入回归，构建 1/7 步即 fatal error 终止）
- 根因: 假定 base/file_util.h 存在；M151 树已迁至 base/files/file_util.h（上游文件本就
  已包含该头，无需注入）。修复（2026-10-08）：注入器改为"两路径任一存在即跳过，
  否则补新路径"，并移除树内错误 include 行。教训：include 注入必须以目标树为准。

### D34（过程记录）loader v2 语义前提复核
- AppendSwitchASCII 的 CommandLine 开关 map 为"后写覆盖"语义（A6 实证 + v1 累积
  合并正常工作反证），v2 单次合并 append 在该语义下 enable/disable 各自生效；
  FeatureList 解析端 try_emplace 首条生效 → 用户置前 = 用户优先。链路自洽。

### D28 legacy 升级入口族 — 永久禁用的破坏性参数组合散布 8 处（架构安全）
- 严重度: **Critical**（误运行即摧毁源码树定制与工具链）
- 位置与处置（2026-10-08）:
  - `win_scripts/version.py`：✅ 运行禁用（保留历史说明）
  - `win_scripts/upstream_version.py`、`trunk.py`、`tot.py`：✅ 运行禁用
  - `aliases.txt` origin/gsync：✅ 注释禁用并给安全替代
  - `AGENTS.md` L148 构建流程（与 README L235 禁令矛盾）：✅ 更正为安全组合并加注
  - 遗留（低危，ADR-003 判定不维护的 Linux 面）：root `version.sh`/`trunk.sh`/`tot.sh`/`upstream_version.sh`、`win_scripts/old/*.bat`、`docs/WIN_INSTRUCTIONS.txt` —— 保留但已在缺陷档案登记，Windows 流程不引用
- 根因: 项目从 Thorium 继承的升级脚本与 2026-08-06 固化的禁令未同步清理

### D29 win_scripts/build_win.py — 引用不存在目标（mcloud_all/setup），永远失败
- 严重度: Medium。✅ 修复: 改为 `chrome` + `mini_installer`（与 AGENTS.md 一致）

### D30 win_scripts 定点脚本硬编码树路径，与 deploy_mcloud.py 的 CR_DIR 机制脱节
- 严重度: Medium（架构一致性：换树/多树环境会打错目标）。✅ 修复: 6 个脚本统一 `CR_DIR` 环境变量 + 标准默认值

### D31 AGENTS.md 已知坑条目与实证相反（V8 flag 格式描述错误）
- 严重度: Low（文档误导）。✅ 修复: 更正为下划线格式要求（与 mcloud_flags.txt 55-57 行一致）

### D32 src/media/base/media_switches.cc 覆盖注释失实（D3D12 上游默认 DISABLED）
- 严重度: Low。✅ 修复: mcloud_flags.txt 注释更正；覆盖+运行时禁用互相抵消的事实入档，
  下次升级清理（移除覆盖后该行禁用可删）

### D35 benchmark/tools/verify_builtin_flags.ps1 — 兜底路径计数器重复累加（验证门可被绕过）
- 严重度: **High**（A6 验证脚本自身缺陷：headless 部分命中 + fallback 全量重计 →
  found 可超过 probe.Count，把缺失标志的构建误判为 PASS）
- ✅ 修复: fallback 分支进入时 `found = 0` 重新计数（2026-10-08）

### Round-1 模糊测试证据（2026-10-08）
- 工具：`pak_fixed.exe`（/fsanitize=address 构建）+ 随机变异（位翻 1-6 + 30% 截断）
- 规模：解包侧 400 例（真实 v5 pak 变异）+ 打包侧 200 例（pak_index.ini 变异）
- 结果：**crashes=0**（全部落入优雅退出码集合 unpack{0-4}/pack{0,5-9}）
- 环境注记：首轮 4 例"崩溃"为 ASan 运行库 DLL 不在子进程 PATH 的伪影（0xC0000135），
  补 PATH 后复跑归零——记录以防误读。

### D36（观察，不改行为）win_scripts/clean.py — 会整体删除 pgo_profiles（459MB 重建成本）
- 与上游 clean.sh 语义一致（升级前清理用途），破坏性有界；登记为已知行为。

### D37 win_scripts/reset_depot_tools.py — 删除固定修订 depot_tools 并重克隆 master
- 严重度: **High**（破坏版本锁定策略；DEPOT_TOOLS_DIR 配为盘根带尾斜杠时 `del /S /Q`
  可清空整盘的边界风险）。✅ 修复: 运行禁用（2026-10-08）

### D38 benchmark/*.ps1 批量不可解析 — 无 BOM UTF-8 + 中文注释破坏 PS 5.1 解析
- 严重度: **High**（K1-K7 基准工具全部实际不可运行：bench_startup 实测
  MissingEndCurlyBrace 解析错误；8 月 K1=73ms 数值与该脚本实际状态矛盾）
- 根因: PowerShell 5.1 对无 BOM 文件按 ANSI(GBK) 解码，UTF-8 多字节序列破坏词法分析
- ✅ 修复: 为含非 ASCII 的 8 个 .ps1 添加 UTF-8 BOM（fix_ps1_bom.py 可重复执行）
- ✅ 验证: bench_startup.ps1 恢复运行，K1 中位数 68ms（基线 73ms，无回归）
- 防再犯: 后续新 .ps1 含中文必须带 BOM（写入编码约定，Round 5 前入 AGENTS.md）

## Round 结果记录
| 轮次 | 日期 | 门（每轮） | 新缺陷 | 结果 |
|------|------|-----------|--------|------|
| 1 | 2026-10-08 | 静态门/pak套件(ASan)/fuzz450(种子7)/deploy幂等/A6/features + 补 K1=68ms 与包内容验证（D38 修复后重计） | — | 全绿 |
| 2 | 2026-10-08 | 六门（fuzz 种子 14） | 无 | 全绿 |
| 3 | 2026-10-08 | 六门（fuzz 种子 21） | 无 | 全绿 |
| 4 | 2026-10-08 | 六门（fuzz 种子 28）+ 包内容复核 | 无 | 全绿 |
| 5 | 2026-10-08 | 六门（fuzz 种子 35） | 无 | 全绿 |

**结论**：D1-D38 修复/登记完毕后，连续五轮"深度 bug + 全功能"回归零新缺陷。
证据目录：`D:\wxmuma\thorium\.bugreview\`（round_1..5_summary.txt、fuzz_result2.txt、
verify_fixes 输出、tree_diff.txt）。已知验证局限：MSVC ASan 不含泄漏检测器（
detect_leaks 不支持），内存泄漏结论以逐行分配/释放配对审查（12 个分配点全配对）
+ D3/D6/D8 实证修复为准，登记为残余风险（owner：项目方；可用 Dr.Mem/WinAppVerifier
后续加强）。

### 第2周期回归（内存溢出专项修复后，轮次接续编号 6-10，2026-10-09）
| 轮次 | 门（每轮 8 项） | 新缺陷 | 结果 |
|------|----------------|--------|------|
| 6 | 静态门 / pak ASan 套件 / fuzz 450（种子 42）/ **结构化溢出探针 23 例（新增门 3b）** / deploy 幂等 / A6 / features / **加载器边界 11 例（新增门 7）** | — | 24 PASS / 0 FAIL |
| 7 | 同上（fuzz 种子 49） | 无 | 24 PASS / 0 FAIL |
| 8 | 同上（fuzz 种子 56） | 无 | 24 PASS / 0 FAIL |
| 9 | 同上（fuzz 种子 63） | 无 | 24 PASS / 0 FAIL |
| 10 | 同上（fuzz 种子 70） | 无 | 24 PASS / 0 FAIL |

- 性能门：K1 冷启动中位数 **51ms**（原始 70/48/51/51/45，5 次有效），
  对比第 1 周期 68ms 无回归（首样本为冷页缓存噪声）。
- 发布门：`refresh_release.py` 全 8 项判据通过后重打发行包并同步写 sidecar，
  SHA256 `054efb37…05ab389f`（123,448,320B，构建于 16:55，加载器 v5）。
     该包为**强制全量重做**产物：touch 加载器源文件 → 重编该 TU → 重链 chrome.dll →
     重建 chrome.7z → 重打 mini_installer，随后 A6 3/3、K1=54ms、发布 11 项判据全部复验通过。
     （此前 15:58 的 `d558d755…` 为同一份源码的早期构建，代码一致，仅压缩包时间戳/体积不同。）
- 顺序约束（实测踩到并已在脚本内加 5×60s 重试）：发布脚本的"标志文件与仓库同哈希"
  判据不能与门 7（会临时替换 `out/mcloud/mcloud_flags.txt`）并行执行。
- 安装版核对：`%LOCALAPPDATA%\Chromium\Application\mcloud_flags.txt` 与仓库版本
  **生效行完全一致**（各 63 行，差集为空），差异仅为仓库新增的说明注释；
  功能无缺口，故未改动用户正在使用的安装目录，下次用新包重装即自动同步。

**第2周期结论**：D39/D40/D41/D42/D43/D44 全部修复并有实测证据；
连续五轮 8 门回归零新缺陷；运行时内存安全面（加载器 + pak 工具）在畸形/超大输入下
均为优雅降级，无 AV、无 ASan 报告、无挂起。

### D39 加载器 v2 — 超大合并值毒化子进程创建，浏览器 FATAL 自杀（第2周期端到端发现）
- 严重度: **High**（可用性：一份畸形/超大的 mcloud_flags.txt 使整个浏览器无法启动）
- 根因链（stderr 实证）：合并后 --enable-features ≈101KB →
  `WARNING chrome_browser_main_win.cc:795 Command line too long for RegisterApplicationRestart` →
  GPU 子进程 CreateProcessW（32767 字符上限）创建失败 →
  `FATAL gpu_data_manager_impl_private.cc:417 GPU process isn't usable. Goodbye.`
- 阈值实测：~50KB（n=1500）存活、~101KB（n=3000）FATAL；1MiB 文件上限拦不住"合法大文件"
- ✅ 修复（loader v3）：合并值 >24KiB 时跳过内置合并并 LOG(WARNING)，浏览器优雅降级
- ✅ 验证（2026-10-09，`.bugreview/probe_huge.py`）：3000 条 feature（文件 106,890B）
  场景下 chrome.dll(v3) 启动 → 18s 存活、2 个 renderer、全部子进程命令行中
  `EdgeProbeFeat` 出现 **0** 次（内置合并确被跳过，非"塞进去但没崩"）；
  对照 v2 同语料 ~12s FATAL。边界套件 `L-huge-merge-3000` 断言已改为
  "FeatureProbe 不出现 + renderer 存在"，纳入每轮门 7。
- 证据渠道说明：`LOG(WARNING)` 在 BasicStartupComplete 阶段（logging 尚未 InitLogging）
  不落 stderr，实测 `%TEMP%\probe_huge_err.log` 为空——降级行为以子进程命令行
  为权威证据，日志文本不作为通过条件。

### D40 加载器 v3 — 单个超长普通开关值仍可毒化子进程（预算覆盖不全）
- 严重度: **Medium**（与 D39 同一失效模式，触发面不同：非 feature 开关）
- 根因：v3 只对 --enable/--disable-features 的合并值限长；循环内的普通开关
  （`command_line->AppendSwitchASCII(switch_name, value)`）无长度约束。
  标志文件上限 1MiB，故单条 `--js-flags=<250KB>` 合法读入并追加；
  `--js-flags` 在传给 renderer 的开关白名单内 → renderer CreateProcessW 溢出，
  页面进程起不来，症状与 D39 同类（GPU/renderer 不可用）。
- 审计依据：`git diff` 显示树内 MCloud 定制 C++ 仅 4 个文件
  （chrome_main_delegate.cc +108 行为唯一自写代码，其余 3 处为单行默认值/打包清单），
  仓库 src/ 112 个覆盖文件中自定义 C 字符串危险调用为 0（唯一 memcpy 属上游
  `ui/base/x/x11_util.cc`）→ 运行时内存安全面集中在加载器，D40 是其最后一处未 bound 的写入。
- ✅ 修复（loader v4）：加载器追加的**全部**开关共用字节预算
  `kMaxAppendedBytes = 24KiB`，普通开关另有 `kMaxPlainSwitchBytes = 12KiB` 子预算，
  超预算条目跳过并 LOG(WARNING)；feature 合并排在循环之后，故始终保有 ≥12KiB
  余量，不会被畸形普通开关挤掉（真实 6.1KB 文件实测追加 ~3.4KB，余量充足）。
- 设计要点（为什么预算必须按"合并后总长"而非"本次新增长度"计算）：加载器在
  **每个进程**的 `BasicStartupComplete` 里都会执行，子进程读到同一份标志文件后会把
  内置项再追加一次，于是内存中的 `--enable-features` 随进程代际线性增长
  （浏览器 → 子进程 → 孙进程各 +内置列表）。按总量设限才能给这条增长链封顶；
  按增量设限的话，代际叠加仍会逼近 CreateProcessW 的 32767 字符上限。
- ✅ 验证：边界套件新增 `L-jsflags-oversized(budget)`（250KB --js-flags：
  renderer 存活且 `--expose-gc` 不入子进程命令行、feature 仍生效）与
  `L-many-plain-sw(budget)`（4000 个不同普通开关：`sw3999` 不出现、feature 仍生效）。

### loader v5（同批整理，非缺陷）
- v4 构建日志逐行报 `-Wunsafe-buffer-usage`（`line.data() + equals + 1` 等裸指针运算，
  虽经边界推导可证安全，但 Chromium 现行标准将此类告警计为技术债）→ v5 改用
  `string_view::substr`，该文件定制部分告警清零。
- 注入器"是否需替换"的判定由版本号标记改为**正文比对**：正文与标记可能不同步
  （旧逻辑在正文已更新而标记未改时会跳过升级）。实测二次运行输出
  "loader already up to date (content match)"，幂等性保持。

### D41 仓库内 `src/chrome/app/chrome_main_delegate.cc` 为陈旧副本，文档却指向它
- 严重度: **Medium**（架构安全：按文档改这份文件不会影响构建，白做且误导）
- 事实：该副本 2026-08-05 基线，与 M151 有 8 处 API 漂移，早已从
  `copy_essentials.py` 清单移除（phase2-dev-log §8），加载器实际唯一来源是
  `win_scripts/inject_flags_loader.py`；而 `AGENTS.md` 仍写"修改启动行为/flags
  加载从这里入手"。审计同时确认：树内 MCloud 定制 C++ 只有 4 个文件
  （`git diff` 111 行），仓库 src/ 112 个覆盖文件中自定义危险 C 调用 0 处
  （唯一 `memcpy` 属上游 `ui/base/x/x11_util.cc`），无任何脚本再复制该副本。
- ✅ 修复（三处，全部防御性）：
  1. `AGENTS.md` 改为"启动标志加载唯一来源 = 注入脚本 LOADER 常量"，并标注副本陈旧；
  2. 副本文件头加显著注释（不参与构建 / 勿加回复制清单 / 改行为请改注入脚本）；
  3. `copy_essentials.py` 增加 `ALLOWED_COPY` 白名单断言：清单只允许无上游对应物的
     文件（当前仅 `compiler_opt.gni`），一旦被加入上游同名文件即拒绝执行并退出 1。
- 验证：`py_compile` 通过；`copy_essentials.py` 现有清单仍在白名单内（不改变行为）。

### D42 文档中的标志数量口径互相矛盾且与实测不符
- 严重度: **Low**（文档准确性；与 D31 同类，会误导评审与回归判断）
- 事实：`AGENTS.md` 写"66 项运行时优化标志"，`docs/progress.md` 三处写"51 个"，
  实测 `mcloud_flags.txt` 为 **63 条生效开关行 = 60 项 feature + 3 项普通开关**
  （注释行与因卡顿固化禁用的 4 项不计）。
- ✅ 修复：AGENTS.md 与 progress.md §1/§2.2/§7 三处统一改为实测口径并标注测量日期，
  §2.2 保留"历史 51 个/9 类"表述作为分类来源说明。
- 计数方法（可复算，避免再次漂移）：统计非注释且以 `--` 开头的行；
  feature 行按 `=` 后逗号分割计数。

### D43（自身验证方法缺陷）mini_installer 打包内容用明文字节搜索验证——永远不可能命中
- 严重度: **Medium**（验证方法失效：门 3 无论打包对不对都会判 FAIL，反之若判 PASS 才可疑）
- 现象：`refresh_release.py` 首版在 `mini_installer.exe` 内搜 `mcloud_flags.txt` 明文，
  结果 MISS；补测发现连 `chrome.dll`、`resources.pak` 这些必然在包内的文件名也全为 MISS
  → 说明安装包负载是压缩的，明文字节搜索**不是**可用的打包内容验证通道
  （此前"无 7-Zip 时字节搜索"的做法只对未压缩落盘的 `out/mcloud/` 目录有效，
  不能推广到 installer）。
- ✅ 修复：改为验证**打包输入**这一可判定面——
  1. `out/mcloud/chrome.dll` 含加载器 v4/v5 字符串（证明链接的不是旧 obj）；
  2. `out/mcloud/mcloud_flags.txt` 与仓库 `mcloud_flags.txt` **SHA256 相同**
     （installer 打的就是 chrome.dll 旁边那份文件）；
  3. `chrome/installer/mini_installer/chrome.release` 列出
     `mcloud_flags.txt: %(ChromeDir)s\`（这才是打包器会带上它的原因）；
  4. installer mtime ≥ chrome.dll mtime（防止用旧 installer 冒充新包）。
- 顺序约束（实测踩到）：门 2 会在测试期间临时替换
  `out/mcloud/mcloud_flags.txt`，因此发布脚本不能与加载器边界套件并行运行；
  并发时门 2 会因探针内容判 FAIL（属预期失败保护，非包体缺陷）。

### D44 发行包与其 `.sha256` 校验文件不同步（发布脚本只打印不写盘）
- 严重度: **Medium**（发布完整性：用户按 sidecar 校验新包必然失败，且会误判包被篡改）
- 事实：`mcloud_151.0.7922.99_win64_mini_installer.exe.sha256` 仍是 2026-10-09 11:42 的旧值
  `9b94110c…`（loader v2 包体），而 15:58 的 v5 包体实算为 `d558d755…`；
  原因是发布脚本只 `print` 哈希、从不写 sidecar。
- ✅ 修复：`refresh_release.py` 在复制包体的同一步用**从落盘文件重算**的哈希重写
  `.sha256`（格式 `<hash> *<文件名>`，与历史文件一致）；已实测重算并写盘，
  sidecar 与包体一致（123,466,240B）。
- 关联：D43 同时纠正了"installer 内明文字节搜索"这一无效验证通道，
  发布门改为 `chrome.7z` 载荷扫描 + mtime 链条（`chrome.dll ≤ chrome.7z ≤ mini_installer.exe`）。

### D45 release.yml 的资产上传前提在现实中不成立（打 tag 会产出空包 release）
- 严重度: **Medium**（发布链路：看起来成功，实际没有安装包）
- 事实：`release.yml` 只有 checkout → 取版本号 → 读 release notes → `if [ -f mini_installer.exe ]`
  → `softprops/action-gh-release` 上传 `mini_installer.exe` 与校验文件；**runner 上不编译内核**
  （ubuntu + 10min 超时）。而仓库根不存在 `mini_installer.exe`：
  ① `.gitignore` 排除 `mcloud_*_win64_mini_installer.exe`（ADR-003 命名）；
  ② 我们的包 123,448,320B ≈ 117.7MiB，超过 GitHub 单次 push 的 **100MiB 硬限**，即使改名入库也会被拒。
  结果：checksum 步走 "not found, skipping"，action 对缺失文件静默跳过 → 建出**没有资产的 release**。
  另外 `AGENTS.md` 原写"CI 触发：push 到 main 或推送 v* tag"，容易误读为 push main 即发布（实际 release 只认 tag）。
- 已做的处置（本轮）：`AGENTS.md` 触发口径与前提写清楚；新增本版 release notes
  （`docs/superpowers/specs/2026-10-09-release-notes-m151-r2.md`，文件名带内核主版本号
  以便 D46 修复后的选取规则匹配）；发行包按 GitHub Release 资产通道上传而非入库。
- 待决（owner：项目方，二选一）：
  A. 改 `release.yml` 为 `workflow_dispatch` + 显式接收本地产物/artifact 路径，并按
     `mcloud_<version>_win64_mini_installer.exe` 命名与生成校验（一次性把链路做对）；
  B. 启用 Git LFS 入库二进制（代价：仓库历史永久背负每版 ~118MB，不建议）。

### D46 release.yml 用 mtime 选 release notes——实际把 M150 的说明发成了 M151-r2 的正文
- 严重度: **Medium**（对外发布内容错误：GitHub Release v151.0.7922.99-r2 正文显示
  "MCloud Browser M150 Release Notes / 基于 Chromium M150 (150.0.7871.37)"）
- 根因：`NOTES_FILE=$(ls -t docs/superpowers/specs/*release-notes*.md | head -1)` 按 **mtime**
  排序，而 actions/checkout 写出的文件 mtime 是检出时刻，与版本新旧无关，选取结果不确定且实测选错。
- ✅ 修复（`.github/workflows/release.yml` Find release notes 步）：改为按**文件名日期前缀**
  排序（仓库约定 `YYYY-MM-DD-release-notes-mNNN[-suffix].md`），并三级匹配：
  带后缀 tag（`v151.0.7922.99-r2`）优先匹配 `*m<MAJOR>*<SUFFIX>*`；纯版本号 tag 优先匹配
  `*m<MAJOR>.md`（避免旧 tag 继承最新后缀版的说明）；都无则退回最新日期文件。
  `MAJOR` 仅接受数字、`SUFFIX` 白名单字符后再进 glob（不直接把 GITHUB_REF 拼进命令）。
- 本地对 5 个 tag 干跑校验选取结果：
  `v151.0.7922.99-r2 → 2026-10-09-release-notes-m151-r2.md`、
  `v151.0.7922.99 → 2026-08-06-release-notes-m151.md`、
  `v150.0.7871.37 → 2026-06-20-release-notes-m150.md`；无对应说明文件者按最新日期兜底。
- 配套：本版说明文件改名 `2026-10-09-release-notes-mcloud-r2.md` →
  `2026-10-09-release-notes-m151-r2.md`（带内核主版本号，匹配规则可用）。
- 遗留：错误正文已经发布到线上 release，需重跑该 tag 的工作流才会覆盖更新（删除并重推 tag
  属远端破坏性操作，需用户授权）；资产缺失问题仍归 D45。

### 第2周期补充证据：结构化溢出探针（crafted_pak_cases.py，23 例）
随机字节翻转很难构造出"结构合法但恶意"的头部，故补一组逐字节手工构造的探针，
两个方向都带**可用为正例**（否则"全部报错"可能只是"文件找不到"的假通过）：

- 解包方向 11 例恶意 + 1 例正控：v5 头部声称 65535 资源/65535 别名而文件仅 12B、
  有别名却无资源、别名 entry_index 越界、末条 offset=0xFFFFFFFF、offset 非单调、
  offset 相同（0 长度资源）、资源区间越 EOF 1 字节、头部截断、未知版本、
  v4 计数 0xFFFFF0 / 0xFFFFFFFF（(count+1)*6 的 32 位溢出候选）
  → 全部 rc=2/3 优雅报错；正控（含哨兵 entry 的合法 v5 pak）rc=0 ✅
- 打包方向 9 例恶意 + 2 例正控：id=65536 超 u16、别名指向不存在条目、
  索引 70000 行超计数上限、255/256 字符名（`%255s` 宽度与 PATH_MAX 组合边界）、
  `..\` 拼接超 MAX_PATH、缺 [Global]、id 非数字、空 [Resources]
  → 全部 rc=8 优雅报错；正控（单资源 / 双资源+别名）rc=0 ✅
- 结论：ASan 下 0 次 86（ASan 报告）、0 次访问违例、0 次超时挂起；
  已纳入每轮门 3b（`round_check.sh`，接在重建 ASan 二进制的门 2 之后）。

### 第2周期验证方法记录（内存溢出专项）
- 端到端边界语料 11 例（超限/CRLF/无换行/畸形行/未闭合引号/GBK 字节/巨型合并/
  超大单值/海量普通开关/用户+内置共存/真实文件对照），双通道执行：
  headless dump + WMI 子进程命令行。v3 二进制 9 例全 PASS；v5 二进制（2026-10-09 15:56 构建）**11/11 PASS**，含两个 D40 新用例（250KB `--js-flags`、4000 个普通开关）。
- **合并顺序断言的证据渠道修正（重要）**：子进程命令行**不能**用于判定我们的
  合并顺序。对照实验（`.bugreview/probe_order.py`，2026-10-09）：
  - 内置=`McloudProbeBuiltin` / 用户=`ZzzUserProbeMarker` → 子进程得到
    `McloudProbeBuiltin,ZzzUserProbeMarker`
  - 内置=`ZzzBuiltinProbe` / 用户=`AaaUserProbe` → 子进程得到
    `AaaUserProbe,ZzzBuiltinProbe`
  两组都呈**字典序**而非我们的追加序，说明 Chromium 在向子进程传播时把重复的
  --enable-features 归一化（去重+排序）为单条；此前 LUF 用例的"WRONG-ORDER/0 命中"
  抖动即源于此，而非加载器缺陷。
- 由此得到的真实语义（登记为残余风险 R6）：用户覆盖在**浏览器进程**内按
  user-first 生效（`merged = 用户值 + "," + 内置值`，代码可判定）；
  在**子进程**中若同名 feature 带不同参数同时出现，胜出者取决于 Chromium 的
  排序结果而非用户优先。规避方式（文档口径）：改 `mcloud_flags.txt` 删除被覆盖的
  内置条目，或用 `--disable-features` 反向压制，不依赖同名双写。

## 第3周期（2026-10-10，升级预评估中发现）

### D47 chrome.release 的 flags 条目无脚本产生（High，发布链路可复现性）
- 事实：构建树中 `chrome/installer/mini_installer/chrome.release` 多出的
  `mcloud_flags.txt: %(ChromeDir)s\` 一行**只存在于工作树的未提交修改**。
  `deploy_mcloud.py` 的 6 个注入步骤无一写该文件；全仓检索仅
  `win_scripts/setup.py`（遗留禁跑脚本）经 `other/mini_installer.patch` 间接涉及它；
  `docs/BUILDING_WIN.md`/`AGENTS.md`/技术规范均未记载，而 `README.md:259` 已把它当既有事实。
- 与既有记录的关系：D43/D44 轮次只是把"chrome.release 列出该文件"当作**发布门禁**核对
  （`.bugreview/refresh_release.py` 门 3），并未记为**产生缺口**。
- 后果：全新树（=任何一次内核升级）按文档执行 `deploy_mcloud.py → gn gen → autoninja chrome mini_installer`，
  编译与打包全绿，但安装包不含 `mcloud_flags.txt` → 63 行运行时标志整体丢失，且无报错。
  当前 v151.0.7922.99-r2 安装包正确，仅因这棵树恰好保留了手工改动。
- **已修复并发布（2026-10-10，M151-r3）**：新增第 7 个幂等注入脚本 `win_scripts/apply_installer_payload.py`
  （锚点 `chrome.exe: %(ChromeDir)s\` 后插入），挂入 `deploy_mcloud.py` STEPS 与 `win_scripts/verify_sources.py`
  关键脚本清单；AGENTS.md 第 7 步与 README 口径同步更正。探针 `.bugreview/d47_probe.py` 五例全过，含「干净上游
  151 文件 + 注入器 == 当前树文件（逐字节）」与「对 M155 的该文件首次注入可用」。
- 证据：`docs/tasks/m155-upgrade-preassessment.md` §7 D47；
  `git -C chromium-src/src status --porcelain -uno`（7 文件/207 行）与该文件的 `git diff` 单行 hunk。

### D48 mcloud_flags.txt 有 7 条指向不存在的 feature，升级后再加 1 条（Medium，性能面）
- 判定方法修正（重要）：新版 `BASE_FEATURE(kFoo, <default>)` 不再写名字串，
  运行时名由标识符去 `k` 推导；因此"全树搜引号名串"的旧判法会误报，
  必须按**声明位**判定。本轮据此建立目标版本已声明 feature 全集
  （M151 7412 / M155 7576 / M156 7605 项）逐项核对 60 条。
- M151（当前发布基线）即静默失效 7 条：`CanvasOopRasterization`、`EarlyData`、`AVIF`、
  `SpeculationRules`、`ServiceWorkerNavigationPreload`、`BestEffortTaskInhibitingPolicy`
  （真名 `EnableBestEffortTaskInhibitingPolicy`，见 `components/performance_manager/public/features.h:104`）、
  `DirectComposition`。升到 155/156 再失效 1 条：`FlingSchedulingImprovements`。
  另有 15 条属冗余（上游默认已等同我们的意图，含 `disable D3D12VideoDecoder`）。
- 影响：优化清单虚高（"以为开了"），非崩溃类风险；`--enable-features` 未知名被 FeatureList 忽略。
- **部分已修复并发布（2026-10-10，M151-r3）**：删除三版均不存在的 6 条；改名条目转注释保留（启用会改行为，
  待基准）；`FlingSchedulingImprovements` 保留并标「升级期删除」（M151 上真实生效）。断言脚本
  `.bugreview/flag_stability.py`（A-E 五条）PASS；`check_features.py` 双树实测 M151 53/53、M155 52/53。
  存活性校验已作为**本地轮次门禁**接入 `.bugreview/round_check.sh` 门 10（实测 53/53 通过）。
  CI 侧不接入：`verify.yml` 跑在 ubuntu runner 且没有 Chromium 检出，`check_features.py` 必须要源码树；
  若要进 CI，需先在 workflow 里做定向浅拉取（数 GB），代价与收益不匹配，故记为已知边界。
- 证据：`.bugreview/survival_check.py` + `survival_{151,155,156}.json`、`flags_table.md` 60 行明细。

### D49 文档口径"V8 连字符写法在 M151 静默失效"与 V8 源码不符（Low，文档）
- 源码证据：`v8/src/flags/flags-impl.h:19`
  `static constexpr char NormalizeChar(char ch) { return ch == '_' ? '-' : ch; }`，
  标志名比较统一经 `FlagHelpers::EqualNameWithSuffix`/`flags.cc` 归一化 →
  `--osr-from-maglev` 与 `--osr_from_maglev` 等价，`--sparkplug-plus` 同理。
- 现状：`AGENTS.md`"已知坑"与 `mcloud_flags.txt` 60-61 行注释均断言连字符写法失效；
  该实证结论来自更早会话且无可复核产物，本轮未能复现。
- 处置原则：**核实前不改 flags 文件**；如需硬结论做一次运行时歧义实验。
- 2026-10-10 运行时实验结果（**否定了"可以做运行时歧义实验"的可行性**）：
  ① `--enable-logging=stderr --v=1` 下分别注入 `--js-flags=--trace-opt-verbose`、
  `--trace_opt_verbose`、拼错的 `--trace-opt-verbos`，三者 stderr 字节数几乎相同（2207/2206/2205 B），
  V8 优化追踪命中均为 0 —— Chrome 不把 V8 的 `--trace-*` 输出转发到浏览器进程 stderr；
  ② 改用"未知标志是否报错"作判别子：注入 `--js-flags=--zzz-not-a-v8-flag` 与两个合法写法，
  stderr 中都只有无关的 GCM `DEPRECATED_ENDPOINT` 一行，**没有任何 V8 拒绝信息** —— 说明
  Chromium 对 `--js-flags` 里的未知名字是静默忽略，因此"缺少报错"不能证明"写法有效"。
  结论：该运行时通道无法判别；唯一权威依据仍是 V8 源码 `flags-impl.h:19 NormalizeChar`（`_`/`-` 等价）。
  若要确定性结论，可行路径是在树内 `autoninja d8` 后用 d8 直接跑两种写法对比（尚未执行）。
  实验脚本：`.bugreview/d49_experiment.py`（含"必须用线程读 stderr，否则 os.read 阻塞使超时失效"的修正）。

| 发布链路 | D47（chrome.release 定制无脚本产生） | ✅ 注入器 + 接线 + 探针五例全过，已随 r3 发布 | 2026-10-10 `.bugreview/d47_probe.py` |
| 性能清单 | D48（7 条静默失效 + 1 条升级期失效） | ✅ 已清理并发布（改名条目转注释、校验脚本 PASS）；CI 接入待办 | `.bugreview/flag_stability.py`、`check_features.py` 双树 |
| 性能清单 | D51（InitialWebUI params 语法不合法；feature 本身已启用） | ✅ 改写为 `param/true` 成对语法；E 断言升级为语法校验 | 改前后 `flag_runtime_state.py` 回显逐项一致（净行为不变）+ 负向对照 FAIL/PASS + M151 同象 |
| 验证方法 | D50/D51 的共性教训：静态判据与"某通道看不到"都不等于运行时状态 | ✅ 新增运行时回显核对工具，并把集合语义写进脚本注释 | `flag_runtime_state.py` 头部说明 |
### D50 SkiaGraphite 的「禁用」从未生效（Medium，定案与实现不一致）
- 事实：窗口拖拽冻结缓解定案要求 4 项永久禁用，但其中 `SkiaGraphite` 在 **151/155/156 上游默认均为
  `FEATURE_ENABLED_BY_DEFAULT`**，而 `mcloud_flags.txt` 只是把 `--enable-features=SkiaGraphite` 注释掉 ——
  不启用 ≠ 禁用。其余 3 项（`SkiaGraphitePrecompilation`、`ThrottleUnimportantFrameRate`、
  `ReduceHardwareVideoDecoderBuffers`）上游默认确为 DISABLED，注释即等效禁用，无此问题。
- 复核方法（可重复）：`.bugreview/frozen_flags_check.py`（跨 151/155/156 比对声明处默认值）。
- 处置：2026-10-10 升级时改为显式 `--disable-features=SkiaGraphite`，并同步进 `flag_stability.py` 的
  「已登记例外」（A 断言只禁止未登记的开启项）。因该项与 GPU 效率存在张力，已列入 155 上的同方法 A/B
  （拖拽场景复现 + `benchmark/tools/gpu_probe.py`）；未测前不撤销。
- 一般形式：**凡「永久禁用」清单，都必须核对上游默认值**；默认启用的项只能靠显式 disable 表达。
- 2026-10-10 补充（运行时侧证）：`.bugreview/flag_runtime_state.py` 在 M155 构建上实测，
  `--disable-features=` 里的 `SkiaGraphite` 与 `D3D12VideoDecoder` 均出现在子进程 override 的
  disable 集合中 → 两项禁用**确实生效**（此前只有静态判据）。

### D51 `InitialWebUI` 的 feature params 写法不合法（Low，静默降级；**结论经二次修正**）
- 观察：`.bugreview/flag_runtime_state.py` 在 M155 构建上比对"清单声明集合 vs 子进程命令行回显集合"，
  发现第 24 行 `--enable-features=InitialWebUI:without_spellcheck/without_translate/high_stream_priority`
  **没有出现在回显里**（其余 50 项 ours 全部命中）。
- 初判（已推翻）：条目未注册 → 整个 feature 从未生效。错因：把"回显集合"等同于"已启用集合"。
- 真实机制（源码实证，M155）：
  ① `base/feature_list.cc:880 ParseEnableFeatureString()` 按 `:`/`.`/`<` 三段切分；带 params 但没写
     study/group 时，会**合成**一个 trial（`study="Study"+名字`、`group="Group"+名字`）并返回 true；
  ② `ParseEnableFeatures()`（同文件 337 行）于是把它登记成 `InitialWebUI<StudyInitialWebUI`，
     `RegisterOverride(..., OVERRIDE_ENABLE_FEATURE, trial)` —— **feature 确实被启用**；
  ③ `base/feature_list.cc:1432 GetFeatureOverridesImpl(command_line_only=true)` 明确
     `if (entry.second.field_trial != nullptr …) continue;` —— **带 trial 的 override 被排除在回显之外**
     （它改由 field trial 共享内存通道下发）。所以"回显里没有"只说明"这条走了 trial 路径"，不说明没生效。
- 仍成立的部分：params 的**语法**确实不对。Chromium 要求 `Feature:param/value/param/value`，
  我们给了三个没有值的裸名 → 参数关联失败，三个 param 取的是代码里的**默认值**。
  查 M155 `content/public/common/content_features.cc:568` 起：
  `high_stream_priority` / `without_spellcheck` / `without_translate` 的 `BASE_FEATURE_PARAM(bool,…)`
  默认值**都是 true**，正是我们想要的取值，因此**当前净行为无差异**（这是它至今没暴露的原因）。
  风险只在于"上游若翻转默认值，我们的意图就悄悄丢了"。
- oracle 的正确读法（写进工具注释）：子进程回显 = **未关联 trial 的命令行 override**；
  带 params 的条目走 trial 通道，不参与回显。对照实验（`--control` 注入不存在的裸名会被回显）
  只能证明"回显是原样回显型"，不能反推"未回显即未启用"。
- 处置（已完成 2026-10-10）：第 24 行改写为合法语法
  `InitialWebUI:without_spellcheck/true/without_translate/true/high_stream_priority/true`；
  改后重跑 `flag_runtime_state.py`：回显集合与改前**逐项一致**（enable 51 / disable 2、InitialWebUI 仍
  因走 trial 通道不在回显内）→ 净行为不变的实证。`flag_stability.py` 的 E 断言已升级为**成对语法校验**
  （奇数 token 直接 FAIL），并用"临时改回旧写法"做了负向对照：旧写法 FAIL、新写法 PASS，验证判据本身有效。
- 跨版本核实：M151 构建（r3 时代 flags）跑同一脚本，[A] 同样只有 `InitialWebUI` 不在回显内 →
  **两版行为一致，非升级引入的回归**。
- 一般形式：**运行时可见性判据必须先弄清它统计的是什么集合**；把"某通道看不到"直接读成"没生效"
  是 D50（注释≠禁用）的同构错误，只是这次方向相反（看不到但其实生效）。

## 第3周期（2026-10-10 晚，全面测试：性能 / 内存 / 进程卡死 + 全局效率评审）

范围：运行时加载器（`inject_flags_loader.py` 的 LOADER 与注入器本体）、`win_scripts/*.py`、
`benchmark/*.ps1` 与 `benchmark/tools/*.py`、本次新入库的 `.bugreview` 验证脚本、以及树内实际
被编译的定制面（`git diff --stat` 实测 6 文件 / 229 行）。工具链侧新装了 ruff + pyflakes 做静态分析
（仓库原本没有任何 Python linter 在跑，这是一个流程缺口）。

语言与专业视角：C++（Chromium base / content 启动路径）、Python 3.12（无版本声明文件，脚本按 3.8+ 兼容写）、
PowerShell 5.1（中文必须 UTF-8 BOM，见 D38）、GN（Chromium 构建元语言）。

### D52 基准内存测量把整机 chrome 都算进去（High，测量有效性）
- 位置：`benchmark/bench_memory.ps1`（旧第 61 行 `Get-Process -Name chrome`）、
  `benchmark/tools/leak_probe.py`（旧 `workset_mb()` 同样是按进程名汇总）。
- 事实：这两处按**进程名**而非**实例**汇总，因此用户自己开着的浏览器、上一轮残留的实例、
  并行运行的另一个探针，全部计入 K2/驻留数字。被测对象与数字之间没有因果关系。
- 影响：直接污染本项目最关键的内存 KPI；也是 §5.3 里"同配置三次取值跨零、散布 ~27 MB"的主要来源之一。
  任何据此做出的采纳/否决判断都不可靠。
- 修复：以本次启动使用的 `--user-data-dir` 为指纹，用 `Win32_Process.CommandLine` 筛出属于本实例的
  PID 集合再汇总 WorkingSet64；bench_memory 与 leak_probe 同步改造，并在输出里打印进程数以暴露筛选结果。
- 验证：见 §"证据"，同一构建下修复前后各跑一次 K2 + 泄漏探针，比较进程数与散布。

### D53 leak_probe 写死 CDP 端口 9333（Medium，会驱动"别人的"浏览器）
- 位置：`benchmark/tools/leak_probe.py:DEV_PORT = 9333`。
- 事实：端口固定。若机器上已有别的 chrome 在 9333 上监听（上一轮残留 / 用户自己开了调试端口），
  `/json/new` 打到的是**那个实例**，而内存采样的却是我们启动的实例 → 数据自相矛盾且无任何报错。
- 修复：每次运行 `bind(0)` 取空闲端口并传给 `--remote-debugging-port`。
- 附带安全含义：常驻的 9333 是本地任意进程可驱动浏览器的入口，测试工具不应默认占用它。

### D54 bench_*.ps1 无 finally，异常路径留下孤儿 chrome 与临时目录（Medium，进程堆积）
- 位置：`benchmark/bench_startup.ps1`、`benchmark/bench_memory.ps1`（`$ErrorActionPreference='Stop'`
  但清理语句都是普通顺序语句，不在 try/finally 中）。
- 影响：采样阶段任何一步抛错（WMI 抖动、`Remove-Item` 被杀软占用、数组为空触发算术异常）都会让
  chrome 进程留在后台；反复运行即进程越积越多，机器表现像"卡死"，且后续测量被前面的孤儿污染。
- 修复：把启动—采样—清理包进 `try { … } finally { … }`，finally 内用 `-ErrorAction SilentlyContinue`
  保证清理自身不再抛错。

### D55 测试工具做机器级 Stop-Process（High，会杀掉用户自己的浏览器会话）
- 位置：`benchmark/tools/leak_probe.py`、`benchmark/tools/gpu_probe.py`、`.bugreview/ab_flags.py`
  的 `kill_chrome()` / `Get-Process chrome | Stop-Process -Force`。
- 事实：这三处在采样结束后**无条件终止整机所有 chrome 进程**。用户一边跑基准一边浏览网页时，
  会话和未保存的标签会被静默丢弃（本次 A/B 跑了约 90 分钟，期间就是这种状态）。
- 根因：把"清理我自己起的实例"实现成了"清理所有同名进程"。
- 修复：统一改为按临时 profile 前缀筛 PID（`OUR_PROFILE_PREFIXES`），只杀自己启动的实例；
  用户默认 profile 位于 `%LOCALAPPDATA%` 而非 `%TEMP%`，因此该筛选不会误伤。
  `ab_flags.kill_matching()` 成为共享实现，`propagated_sets()` 的内联强杀一并替换。

### D56 WMI / PowerShell 调用普遍没有 timeout（Medium，无声挂死）
- 位置：`benchmark/tools/gpu_probe.py:ps()`、`benchmark/tools/leak_probe.py:ps()`、
  `.bugreview/flag_runtime_state.py:ps()`、`.bugreview/ab_flags.py:ps()/kill_chrome()`、
  `.bugreview/flag_stability.py`、`frozen_flags_check.py`、`api_drift.py`、`name_archaeology.py`、
  `candidate_applicability.py`、`d47_probe.py`（git grep 全树检索），`win_scripts/deploy_mcloud.py`。
- 影响：`wmiprvse` 或 git 索引锁一旦卡住，整条流水线停在这一步且不报错（本轮已实际踩到过类似的
  长挂起，见 D54 的同类现象）。属于"进程卡死"类风险，不是崩溃类。
- 修复：所有 `subprocess.run` 显式 timeout（PowerShell 180 s、git grep 600–900 s、部署步骤 900 s），
  并在 `ab_flags.kill_chrome()` 里把超时降级为"跳过清理并打印警告"，绝不做机器级强杀兜底。

### D57 加载器不剥 UTF-8 BOM，首行静默丢失（Low–Medium，静默失效族）
- 位置：`win_scripts/inject_flags_loader.py` LOADER 解析循环。
- 事实：解析要求行以 `--` 开头；带 BOM 时第一行变成 `` 开头 → 该行被整条跳过。
  PowerShell 5.1 的 `Set-Content -Encoding UTF8` 与部分编辑器会写 BOM，而本项目的 `.ps1`
  规范恰恰强调 BOM，风险来源真实存在。当前 `mcloud_flags.txt` 无 BOM（实测首字节为 `# =`），
  所以尚未发作，但这是一颗"改一次文件就静默掉一条 flag"的地雷（D48 同族）。
- 修复：读取后按字节比较剥去前 3 字节（`0xEF 0xBB 0xBF`），不使用转义字面量——
  本次编辑过程中就因把 `\xEF` 经 Python 字符串写成真实字节而把源文件写坏过一次，
  字节比较形式对编码事故免疫。
- 验证：`.bugreview/loader_edge_test3.py` 的 T1 用例（BOM + 首行即 flag）在旧二进制上必失配，
  新二进制必须命中，见"证据"。

### D58 加载器在每个子进程重复读盘解析，并按各自命令行重算预算（Low，效率 + 一致性）
- 事实：调用点是 `ChromeMainDelegate::BasicStartupComplete()`，而该方法由
  `ContentMainRunnerImpl::Initialize()` 在**所有进程类型**里调用（`content/app/content_main_runner_impl.cc:964`）。
  于是 browser、renderer、GPU、utility、crashpad 每个进程启动都读一次文件、做一次 split、再走一遍预算判定。
- 影响分级说明：读的是 7.9 KB 文件，单次成本很小；**真正的风险是一致性**——子进程的
  `--enable-features` 值已经是浏览器解析后的完整列表，加载器又在其后追加一遍内置列表，
  于是子进程的预算判定基线与浏览器不同；在接近上限的语料下，子进程可能丢掉浏览器保留的条目
  （FeatureList 在浏览器与子进程之间不一致正是 Chromium 用 DCHECK 明令防备的情况）。
- 修复：`if (command_line->HasSwitch(switches::kProcessType)) return;`——子进程已经通过
  命令行继承 + field-trial 共享内存拿到最终状态，无需重复读盘。
- 诚实声明：这一项**不主张性能收益**（每进程一次小文件读，落在 §5.3 的噪声带之下，测不出来）；
  做的是"去掉无谓工作与跨进程不一致面"，属稳定前提下的正确性收敛。

### D59 flags 文件行内注释会让整条静默失效（Medium，静默失效族）
- 事实：加载器只把"整行以 `#` 开头"视为注释；`--enable-features=X # 备注` 会把 `#` 及其后文本
  并进 feature 名，Chromium 侧不报错也不生效。
- 决策（全局最优而非局部最优）：**不改运行期解析**去支持行内注释。加载器的语义应当与 Chromium
  自身对 `--enable-features` 的解析一致，多一层 shell 式注释只会让"文件里写的"与"内核看到的"更难看清。
  改为在作者侧静态拦住：`flag_stability.py` 新增 **F 断言**，活动行含 `#` 即 FAIL。
- 验证（Red→Green）：临时给 `TransientKeepAlivePolicy` 加 ` # 行内注释实验` → 稳定性门禁由
  PASS 变 FAIL（A/C/F 三条断言同时命中），恢复后回到 PASS。

### D60 loader_edge_test2.py 把 M151 树路径写死（Medium，测错对象 + 改写旧树）
- 事实：`OUT_DIR` 硬编码 `chromium-src\src\out\mcloud`。在双树并存（M151 + M155）的现状下，
  直接运行会 (a) 测到旧二进制上，结论与当前内核无关；(b) 把旧树 `out/mcloud/mcloud_flags.txt` 改写掉。
- 修复：路径改由环境变量 `LOADER_TEST_OUT` 决定（默认仍为旧值以保持既有可复现行为，但必须显式选择目标树）。
- 一般形式：任何"对着 out 目录写文件再启动浏览器"的测试都必须显式绑定被测树。

### D61 win_scripts/clean.py 里残留 `try_run(shell=True)` 死代码（Low）
- 事实：`try_run()` 在本文件无任何调用点，却使用 `shell=True`；一旦将来被人复用，
  就是把拼接字符串喂给 shell 的老问题（本仓库对 `del /S /Q` 一类命令已有严格约束）。
- 修复：删除该函数及其 `import subprocess`，行为不变（`python -m py_compile` + 干跑校验）。

### D62 加载器注入器只在"正文不一致"时才校验调用点（High，静默 no-op）
- 事实：旧逻辑 `if s[i:j] == want: print("already up to date"); sys.exit(0)` 在正文一致时直接返回，
  调用点检查写在它后面。于是"块还在、但 `LoadMcloudPerformanceFlags();` 这行被上游改写或手工删掉"
  这种情况会被完全放过：加载器变成存在但永不执行的死代码，63 行运行时优化整体静默丢失，
  而 deploy 输出显示"already up to date"。与 D47 同族（编译打包全绿、行为静默缺失）。
- 修复：调用点校验前置，任何分支都先证明调用存在；同时补 `i >= j` 的顺序断言
  （标记错位时继续替换会把中间内容复制成重复、直接写坏源文件）。
- 验证（Red→Green）：正例——M155 树输出 `loader already up to date (content match, call site verified)`；
  负例——把调用行从副本里删掉后运行，退出码 1 并给出明确错误文本。

### D63 Polly / BOLT 接线语义错误（Medium，潜伏；当前 use_polly/use_bolt=false 故无实际影响）
- 事实一：`config("polly")` 把 `-mllvm:-polly*` 放进 **ldflags**。Polly 是编译期 pass
  （SCoP 检测 + 多面体变换），只有 **cflags** 才能让它作用在逐 TU 编译上；放 ldflags 时只有
  link-time codegen 看得见 → 即便把 `use_polly` 打开也基本空转，属于"看起来开了其实没开"（D50 同族）。
- 事实二：polly config 里还写了 `ldflags = common_optimize_on_ldflags`，与 Polly 无关，
  却在开启时覆盖链接 flags 的合并语义。
- 事实三：`emit-relocs` 为 BOLT 后链接服务，而 BOLT 官方只支持 ELF/Mach-O；Windows COFF 路线未证实。
  旧写法在 `is_win` 分支给 lld 发 `-mllvm:--emit-relocs`，一旦有人打开 `use_bolt` 就是链接期报错，
  而不是给出"不支持"的明确信号。
- 修复：Polly 改走 `cflags`（Windows 用 `-mllvm:-…`，其他平台用 `-mllvm -…`）；删除无关的
  `common_optimize_on_ldflags`；`emit-relocs` 加 `!is_win` 条件。
- 说明为什么现在不动 args.gn：`use_polly`/`use_bolt` 仍必须为 false（前置依赖未就绪，见规范 2.6/10.1），
  本轮修的是"将来开启时的正确性"，不是开启它。

### D64 append_polly_configs.py 没有升级路径（Medium，自称已生效实则不改）
- 事实：脚本一旦看到 `config("polly")` 存在就只补 import 然后 `exit(0)`，正文永远停留在第一次注入的版本。
  结果是"仓库里的定义已经改了，树里还是旧的"，而且输出写着 `already present, nothing to do`——
  与 D47/D50 同族的静默不一致。加载器注入器早已改成正文比对式升级器，这里补齐同一约定。
- 修复：定位 `BEGIN → polly config 收尾 }` 整块做正文比对，不一致就整体替换；
  `ensure_import()` 保证只有一处 import。
- 验证（Red→Green）：对 BUILD.gn 副本运行两次 → 第一次 `block replaced in place`、
  第二次 `already up to date (content match)`；副本中 `compiler_opt.gni` import 计数为 1、
  `common_optimize_on_ldflags` 残留已消失。

### D65 d49_experiment.py 的读取线程闭包捕获循环变量（Medium，实验证据本身不可信）
- 事实：`_reader()` 定义在 `for label, jsflag in CASES:` 内部，捕获外层 `p` / `chunks`；
  上一轮的 daemon 线程可能在 `p` 重新绑定之后才执行 `os.read(p.stderr…)`，
  于是采到**另一个用例**的 stderr（ruff B023 命中，且此处经核查为真阳性而非误报）。
- 影响：D49 的结论依赖这份 stderr 采集；证据链必须自洽。
- 修复：`def _reader(p=p, chunks=chunks):` 显式绑定当轮对象（Python 惯用写法）。

### 3.x 全局效率评审（"稳定前提下最优效率"，而非局部最优）

- **AVX2+FMA3 基线附带 `-mf16c -mlzcnt -mbmi -mbmi2`**：看似超出 AGENTS.md 声明的基线，实际不是风险——
  商用 x86 里支持 AVX2 的处理器（Haswell 起、AMD Excavator 起）全部带 BMI1/BMI2/LZCNT/F16C，
  不存在"有 AVX2 而无 BMI2"的在产机型，所以不会因这条产生 SIGILL。记录该推理，避免以后被当作隐患反复审。
- **deploy 第 8 步与 `copy_essentials.py` 功能重复**：两处都把 `mcloud_flags.txt` 放进 `out/mcloud`，
  所以第 8 步永远打印 `already in sync`。保留（无害）但已在此记录，防止有人把它当"同步失败"信号误读；
  若日后精简，应删第 8 步而不是删 copy_essentials 的那一份（后者在单步执行路径上也必须成立）。
- **`CR_DIR` 默认指向 M151 树**：双树并存时这是最容易踩的坑（本轮实际踩到一次，因步骤幂等未致损）。
  已在 AGENTS.md 立为硬性提示。
- **验证脚本的算法成本**：`survival_check.py` 走"一次全树扫描建立声明全集 + 集合查询"，
  而 `flag_stability.py`/`frozen_flags_check.py` 是"每个条目一次 `git grep` 全树"（53 条 × 3 个版本 = 159 次
  全树检索）。单次运行约几分钟，作为本地门禁可接受，但**不能进 CI**（runner 上既无检出也无这个时间预算）。
  全局最优的判断是：把 `survival_check` 的全集缓存复用到 `flag_stability` 的 C 断言里（它已经在读
  `.bugreview/stab_151.json` 这类缓存），而不是给每个条目继续发 grep；这一步排在下轮工具优化，
  不在本轮，因为它只影响验证速度、不影响被验证的产物。
- **加载器的时间/空间复杂度**：单次读 ≤1 MiB、一次 split、O(条目数) 累积成两个字符串后各合并一次
  （v2 就消除了 v1 的 O(n²) `AppendSwitchASCII`）。预算用 `size_t` 减法比较，均在"已用 ≤ 预算"不变量下，
  不存在无符号下溢。v6 之后子进程不再走这条路（D58）。
- **`win_scripts/setup.py` 的定位**：ruff 剩下的 34 条告警绝大多数来自这个"禁止运行"的遗留全量覆盖脚本
  （F541 之类）。给它修 lint 是局部最优、全局负收益——正确处置是删除或加 refusal guard（同 ADR-003
  对 Linux legacy 面的处理方式），已列入待办而不是本轮顺手改。

## 第3周期缺陷登记（D52–D105，详版与全部证据见 `docs/tasks/bug-review-cycle3-report.md`）

一句话索引（每条的报告里有 file:line、根因、影响、修复与 Red→Green 证据）：

| # | 严重 | 一句话 | 状态 |
|---|---|---|---|
| D52 | High | `bench_memory.ps1` / `leak_probe.py` 按进程名汇总整机 chrome，K2 与被测实例无因果关系 | ✅ 实例级 PID 筛选（实测 K2 由 2586.8/58 → 2512.85/57） |
| D53 | Medium | leak_probe 写死 CDP 端口 9333，可能驱动别的实例却量我们的内存 | ✅ 每轮 `bind(0)` 取空闲端口 |
| D54 | Medium | bench_*.ps1 的清理不在 finally，异常路径留下孤儿 chrome + 临时目录 | ✅ try/finally |
| D55 | High | 测试工具 `Get-Process chrome \| Stop-Process` 会杀掉用户自己的浏览器会话 | ✅ 按临时 profile 指纹只杀本实例（三处） |
| D56 | Medium | WMI/PowerShell/git grep 普遍无 timeout，一处卡住整条链无声停住 | ✅ 统一补 180/600/900 s |
| D57 | Low–Med | 加载器不剥 UTF-8 BOM → 首行整条被丢（PS 5.1 写文件默认带 BOM） | ✅ 字节比较剥离；T1 用例 v5 FAIL / v6 PASS |
| D58 | Low | 加载器在每个子进程重复读盘解析并按各自命令行重算预算 | ✅ `kProcessType` 限定；T7 证明子进程仍继承 |
| D59 | Medium | flags 活动行尾写 ` # 备注` 会让该条整条静默失效 | ✅ 新增 F 断言静态拦住（不改运行期语义） |
| D60 | Medium | `loader_edge_test2.py` 硬编码 M151 树：测旧二进制并改写旧树 flags | ✅ 改 `LOADER_TEST_OUT` |
| D61 | Low | `clean.py` 残留 `try_run(shell=True)` 死代码 | ✅ 删除 |
| D62 | High | 注入器只在正文不一致时才看调用点 → 调用行丢失时报 "already up to date" 而加载器永不运行 | ✅ 调用点校验前置 + 标记顺序断言（负例 exit 1） |
| D63 | Medium(潜伏) | Polly 写进 ldflags（编译期 pass 基本空转）；Windows 分支给 lld 发 BOLT 不支持的参数 | ✅ 改 cflags / `!is_win` |
| D64 | Medium | `append_polly_configs.py` 见 `config("polly")` 就退出，正文永远停在首版 | ✅ 正文比对式升级器 |
| D65 | Medium | `d49_experiment.py` 读取线程闭包捕获循环变量（B023 真阳性），实验证据不可信 | ✅ 默认参数显式绑定 |
| D66 | Medium | 修复自身引入的次生缺陷：已证实 2 个（PS 数字+'|' 拼接抛异常被 except 吞成 0 值；清理后才取值），未证实假设 1 个（完整路径指纹的短名差异） | ✅ 全部修复，并把"0 进程"改成硬失败 |
| D67 | Medium | `apply_avx2_baseline.py` / `apply_polly_wiring.py` 用"标志串存在"判已应用，改正文不生效（D64 同族） | ✅ 都改为正文比对升级器（副本三态验证） |
| D68 | Medium | `verify_builtin_flags.ps1` 主路径 | M155 上 `--headless=new --dump-dom chrome://version` 已无 DOM，规范 4.1.1 写的验证方法事实失效，只剩兜底 | ✅ 子进程命令行改为主路径 |
| D69 | Low | 同文件兜底分支 | 兜底按 exe 目录过滤，会把别的实例命令行读进来（假阳性） | ✅ 按本次实例 GUID 指纹 |
| D70 | High | 同文件清理步骤 | 裸 `Remove-Item` 撞上被占用的 lockfile 抛异常，`ErrorActionPreference=Stop` 让脚本在探测**之前**就终止（真实退出码 1，管道还把它伪装成 0），并留下 9 个孤儿 chrome | ✅ 清理进 finally + SilentlyContinue + 残留即判失败 |
| D71 | High | leak_probe / gpu_probe / ab_flags 清理 | 一次性 kill 留下 crashpad-handler 尾巴，残余进程锁住 out 目录 DLL → 实测 `lld-link: failed to write ./dxcompiler.dll: permission denied`、`autoninja exit=1`，51,296 步重编被自家工具打断 | ✅ 循环杀到干净 + 残留 WARN |
| D72 | High | `package_m155.py` + 收尾链 | 构建失败后仍继续打包：门禁只看产物存在与内容证据，于是拿上一轮遗留的 installer 算出 cd6f5172 写进发布说明，无法区分「构建成功」与「构建失败但产物还在」 | ✅ 新鲜度链（dll 不早于加载器源与 4 个 GN 源）+ 构建失败即中止不打包 |
| D73 | Low | `apply_mcloud_source_defaults.py` | 上游把 `BASE_FEATURE` 拆成多行写时，精确单行匹配同时看不到 ENABLED 与 DISABLED → 自愈失效且误报「形态已变更」，deploy 直接退出 | ✅ 加空白归一化兜底；跨行形态实测 rc=0 且不写入 |
| D74 | — (成本结论) | `build/config/compiler/BUILD.gn` 的一个 config 正文 | 只改 config 的**写法**（`use_polly=false` 下展开为空）也让 `gn gen` 后 ninja 给出 51,296 步计划（≈3 小时全树重编）。零收益改动必须与真实改动同批落地 | ✅ 写进 AGENTS.md 与规范；本轮因同时要交付 loader v6 验证链而接受这次重编 |
| D75 | Low–Med | `AGENTS.md` 的 other/ 一节 + `other/*.patch` | 文档把 32 个补丁写成「关键补丁」，但当前构建链一个都不应用（唯一引用者是禁止运行的 setup.py）；其中 `mini_installer.patch` 与 D47 修复同源重复，顺手应用会造成 chrome.release 重复条目/冲突 | ✅ 口径更正为「历史/参考材料，非构建输入」并加禁打提示 |
| D76 | Low | `docs/tasks/m155-perf-features.md` §5 第 7 步 + `docs/CMDLINE_FLAGS_LIST.md` | 采纳 flags 后要「更新 CMDLINE_FLAGS_LIST.md」的指引指向的是**上游 Chromium switch 转储**（Jun 19 起未动，192 KB，非本项目台账），照着做只会改错文件 | ✅ 指引改指 `mcloud_flags.txt` 条目注释为权威台账；剩余项：需要一份带分组/依据/验证状态的机器可读 flags 索引（规范 4.1.2 已建议） |
| D77 | Medium | `src/` 590 个文件里 344 个是"与树内不同、无人应用"的惰性副本（含上一代注入痕迹），AGENTS.md 却称其为"主战场/覆盖文件" | 改这些文件不生效也不报错；拿副本与树内比对会得出错误结论 | ✅ 生成 `src/INVENTORY.md`（`.bugreview/src_inventory.py`）+ AGENTS.md 口径更正，副本保留 |
| D78 | High | `bench_navigation.ps1` | `2>$null \| Out-Null` 吞掉一切，dump 拿不到 DOM 也把墙钟当"加载耗时"输出 | ✅ stdout 落盘按字节判成功，任何无效样本即抛「导航基准不可信」 |
| D79 | High | 同上 | `& $exe` 无超时 → 页面/网络卡住时基准永久挂起（本周期目标点名的"进程卡死"面） | ✅ `WaitForExit(-TimeoutSec*1000)` + 超时 Kill + `-TimeoutSec` 参数 |
| D80 | Low | 同上 | 参数名 `$args`/`$profile` 与 PowerShell 自动变量同名 | ✅ 改名 + profile 用 PID+GUID 唯一化 + 实例级清理 |
| D81 | Low | 同上（D78 修复引入） | `$p.Wait(ms)`：PS 5.1 的 Process 没有 `Wait(int)`，MethodNotFound 直接失败 | ✅ 改 `WaitForExit(ms)`；全仓扫 `\.Wait\(` 零残留 |
| D82 | Low | 7 个 benchmark `.ps1` | 输出被管道捕获时按 GBK 编码，日志中文全乱码（护栏最初还排在首条输出之后） | ✅ 统一加 UTF-8 OutputEncoding 护栏并调序 |
| D83 | High | `final_gate_matrix.ps1` | `param()` 不在首位 → `-OutDir` 被静默丢弃、恒测默认树，且仍 exit 0 | ✅ param 归位；bogus 树实跑证明参数确被消费（日志 8 处该路径） |
| D84 | Medium | 验证方法本身 | `PSParser::Tokenize` 对"语句顺序"类错误全盲（同一文件三次 PARSE OK 却是坏的）；仓库此前无任何 PS 静态检查 | ✅ `verify_sources.py` 增 BOM/param 位置/AST 三层 + 空输入即 FAIL；三个负例文件验证可证伪 |
| D85 | Low | 新 lint 子进程 | 中文错误消息经管道回 Python 后乱码（D82 机制发生在我自己写的检查器上） | ✅ 临时脚本首行加 OutputEncoding |
| D86 | Med–High | 9 个 benchmark/工具脚本 | 默认被测树硬编码为 M151 回滚树，且日志不打印测的是哪个二进制 | ✅ env 解析 + 155 兜底 + 被测身份横幅 + 回滚树告警 + 缺失即 throw |
| D87 | Medium | `flag_stability.py` | 隐含依赖"三个 tag 对象存在于取证仓库"，缺失时表现成一大片无根因的 FAIL | ✅ `_require_revs()` 前置校验（exit 2 + 修复指引）+ 打印解析到的 commit + `--tree` |
| D88 | Low | D87 修复引入 | `--tree` 的值先被当成"基线修订"分配，报错信息指向错误对象 | ✅ 先摘 `--tree` 再分配位置参数 |
| D89 | **Critical** | `final_gate_matrix.ps1` 聚合 | 函数体内 `$results +=` 因 PowerShell 作用域规则永不累加到脚本级 → 汇总表空白、**无论门禁成败恒输出 ALL PASS 且 exit 0**（bogus 树下 `exit=1` 与 `ALL PASS` 同屏） | ✅ `$script:` 累加 + 条数自检 + NOEXIT 判失败 + 逐项打 stdout；删除同缺陷的早期草稿 |
| D90 | High | `docs/progress.md` §5.1「下次编译更新内核时的操作」 | 只让跑 `copy_essentials.py`，且树写成 M151 的 `chromium-src`；照做会**跳过全部定点注入**（加载器/AVX2/Polly 接线/chrome.release 登记），得到"能编译能打包但定制整体丢失"的结果 —— 与 D47 同一失败模式，且这条路径正是升级时会照着做的清单 | ✅ 改为 `deploy_mcloud.py` 为唯一入口 + 显式 `CR_DIR`，并补 rebase 后必做的清单（重生成 INVENTORY、flag_stability、门禁矩阵） |
| D91 | Medium | `docs/BUILDING_WIN.md` + `AGENTS.md` 的「前置文档」指针 | 该文件是上游 Thorium 文档（`C:\src\chromium\src`、VS 2022、`git clone Alex313031/mcloud`、构建 `mcloud_shell/setup` 等本项目不存在的目标、私有密钥口径与 ADR-001 冲突），**完全没有 deploy_mcloud 步骤**，却被 AGENTS.md 指为 Windows 构建前置文档 | ✅ 文件头加"上游遗留、非本仓库步骤"警示并指向权威步骤；AGENTS.md 指针改为本文「构建快速参考」+ progress §5.1 |
| D92 | Medium | `bench_navigation.ps1`（D78 修复自身引入） | `finally` 里用 `-ErrorAction SilentlyContinue` 删重定向临时文件：浏览器子进程（renderer/crashpad）仍持有 stdout 句柄时删除必然失败，而错误被吞 → 两次实跑在 `%TEMP%` 遗留 **42 个** `navdom_*/naverr_*`（0 B～400 KB），正是本周期目标点名的资源泄漏面 | ✅ 删除失败登记到 `$script:pendingCleanup`（作用域写法即 D89 的教训），Test-Mode 在杀完本实例进程后重试；实例清理改为最多 5 轮「杀→等 600 ms」；仍残留则 `Write-Warning` 报数 |
| D93 | Low（但代价高） | 我新加的 `param` 位置检查本身 | 判据用 `ln.strip().startswith(“param(”)`，会**把函数体内合法的 `param(...)` 也当违规**（函数有自己的参数块，通常缩进 4 空格）。当前仓库恰好没有这种写法所以没暴露——是 R9 复核时按「假阳性会让人关掉检查」推演出来的 | ✅ 只认顶格 `param(`；两路对照实测：合法的函数级 param 不报，顶层错位的仍报 |
| D94 | High | `benchmark/run_baseline.ps1`（KPI 基线采集器） | PS 5.1 里 `Write-Host` 走 information stream(6)，旧写法 `& 子脚本 \| Tee-Object -Variable k1out` 抓的是成功流 → **一行都抓不到**（同机实测：不加 `6>&1` 捕获 0 行，加了 6 行）；于是生成的基线报告「原始数据」为空、KPI 表恒写「见原始数据」，末尾还绿色打印「报告已写入」。另有三处同源小错：`$Version` 默认值写死 "M150"（报告标题与文件名都会标错内核）、`$env:COMPUTER_NAME` 拼错（Windows 是 `COMPUTERNAME`）→「构建机」字段恒空、子基准异常/无输出不判 → 空报告也算成功 | ✅ 统一 `6>&1` 捕获 + 正则抽出 K1/K2/K7 数值填表 + 版本从被测二进制文件版本推导 + COMPUTERNAME 修正 + 抽不到数即写进「异常记录」并 exit 1（报告仍留作取证） |
| D95 | Medium | 判据文档缺口 | 噪声带与 A/B 采纳门槛只散落在 `docs/tasks/m155-perf-features.md` §5 与工具里，**权威规范里一个字都没有** → 下一轮很容易拿跨会话数据当回归/收益（本次实测：同一会话内 K2 五采样带宽 2550.2–2553.2 MB（0.12%），跨会话却是 2550.5 vs 2586.8–2593.0（~1.5%）） | ✅ 规范新增 §4.2.1：逐指标带宽表 + 采纳/否决门槛 + 「只用同会话成对数据」「≥2 轮」「判据预注册」三条硬规则 |
| D96 | Medium | `docs/architecture/performance-build-technical-spec.md` §4.3 | 写「现有源码级默认值修改（均经 `copy_essentials.py` 复制生效）」并要求新修改「进入 `copy_essentials.py` 的文件清单」——与现行构建链相反：三处修改由 `apply_mcloud_source_defaults.py` 定点注入，而 `copy_essentials.ALLOWED_COPY` 会**主动拒绝**有上游对应物的整份复制（D41）；表内 D3D12/DoH 两行的现状也已过期（前者只回退历史覆盖、后者只做存在性校验） | ✅ 口径更正 + 表格按脚本正文逐行重述现状（注入/回退/仅校验三态） |
| D97 | Low–Med | `win_scripts/setup.py` | 遗留全量覆盖脚本只靠文档口头约定「勿在新树上运行」，任何人（或 Agent）误跑一次就污染源码树，而且没有报错指回它（D37 的收尾项） | ✅ 加拒绝闸：默认 `REFUSED` + exit 112 并指向 `deploy_mcloud.py`，需 `MCLOUD_ALLOW_LEGACY_SETUP=1` 才继续；`--help` 保持 0（实测三条路径） |
| D99 | **Critical** | `final_gate_matrix.ps1` + `loader_edge_test2/3.py` | 门禁把 `LOADER_TEST_OUT` 设成**真实构建目录**，而这两个边界测试会改写 `<out>/mcloud_flags.txt`（BOM/空文件/垃圾字节/3000 条合并上限语料），只在 finally 恢复。实测：测试被打断后发布目录里留下 106,890 B 与 300,063 B 的假 flags 文件（其一首字节 0xD6、根本不是 UTF-8），下游 A6 / flag_runtime_state / leak_probe 于是**拿测试垃圾当生产配置**测量，其中一个直接崩在裸 UnicodeDecodeError；若在此状态下跑 `mini_installer`，安装包里就是垃圾语料 | ✅ 门禁改为给测试建**硬链接沙箱** `out/mcloud_loader_test`（链全部运行时文件、跳过 args.gn/.ninja_log/.ninja_deps/build.ninja 与文件数>1000 的构建中间目录；跑完 loader 测试后真实文件 sha256 前后 `61b7670856ed` 不变）；两个测试各加 `REFUSED` 防线（目标目录出现构建特征文件即 exit 2，需 `MCLOUD_ALLOW_LOADER_TEST_ON_BUILD_DIR=1` 才放行） |
| D100 | Medium | `.bugreview/flag_runtime_state.py` | ① 以 utf-8 硬读构建目录 flags，被污染时抛裸 traceback，看不出真实原因；② 检出「与仓库不一致」只打印一行 `(!)` 就继续测——在这种状态下得到的运行时结论不属于发布配置；③ `--control` 会写生产 flags 文件（虽有 finally 恢复） | ✅ 改按 utf-8-sig 读字节，解码失败给出「产物目录被测试污染」的可执行修复指引；不一致即 exit，只有 `--allow-drift` 才继续看差异 |
| D102 | **High** | `.bugreview/package_m155.py` 的载荷判据 | 「在 chrome.7z 里搜 `mcloud_flags.txt` 文件名」是**无效量具**：7z 文件表是压缩的，对照实验里 `chrome.dll`、`resources.pak`、`icudtl.dat`、`chrome_100_percent.pak` 这些必然在包内的文件在前 16 MB 命中数**全为 0**；唯一一次命中是 chrome.dll 里加载器自己的字符串（上下文 `MCloud flags: --… skipped by command-line budget`）。于是「载荷已验证」是假的 | ✅ 改为读**打包暂存目录** `…/mini_installer/temp_installer_archive/Chrome-bin/mcloud_flags.txt`（它就是被压进 7z 的那份）并做 sha256 比对；负控制（把暂存文件改名）→ 门禁 FAIL/exit 1，恢复 → 全绿 |
| D103 | **High** | 上游 `chrome/tools/build/win/create_installer_archive.py` | `chrome.release` 里列出的条目若 glob 匹配不到源文件，**默认静默跳过**（只在 `--verbose` 时打印一句 No matches found）→ `autoninja` exit=0、打包「成功」，但包里根本没有那个文件。⚠ 本条的因果后来被 D105 推翻：干净安装日志证明文件**确实进了 7z**，真正的丢件点在**安装侧**（setup.exe 不处理根目录额外条目）。本条仍成立但只是「打包脚本对缺文件不报错」这一半，不是丢件原因 | ✅ 不改上游脚本，改为在我方门禁里加「暂存目录必须含该文件且与仓库字节一致」的硬断言（即 D102 的新判据），把静默跳过变成打包失败 |
| D104 | Medium | 已安装实例（用户机器实测） | 装完 155 后 `Application\mcloud_flags.txt` 仍是 **9-22 的旧文件**（5,878 B / sha `52e67eab7319`），chrome://version 的命令行里因此是 **D51 修复前的坏 params 形式** `InitialWebUI:without_spellcheck/without_translate/high_stream_priority`（无值 → 参数被丢弃、退回上游默认）；而 `chrome.exe`/`chrome.dll` 与本次构建**逐字节相同**（86b588a485855fd8 / 2c9812e62f16308c），说明浏览器本体装对了、只有那个额外文件没被覆盖 | ✅ 已把旧文件隔离为 `mcloud_flags.txt.stale-20260922` 并放入当前正文（8,186 B / `61b7670856ed`），待用户重启后复核 chrome://version；「安装器为何不覆盖已存在的同名文件」尚未定论，需一次干净位置的安装实验（待用户授权） |
| D105 | **Critical（发布阻断）** | `chrome.release` 里 `mcloud_flags.txt: %(ChromeDir)s\` + 上游 `install_worker.cc` | 干净系统安装实测：`C:\Program Files\Chromium\Application\` 里只有 chrome.exe / chrome_proxy.exe / chrome.VisualElementsManifest.xml，**没有 mcloud_flags.txt**；详细日志显示 setup.exe 对根目录是**逐个搬固定清单**（只搬这三个），而版本目录 `155.0.8059.40` 是**整个目录搬过去**的。也就是说：打包侧确实把文件放进了 chrome.7z（尾部 8 KB 处能看到它的正文，`-mx0` 未压缩），但安装侧根本不处理根目录的额外条目 ⇒ D47 的修复方式（登记到 ChromeDir）**在真实安装里无效**，干净机器上 53 项 feature + 3 项开关整体丢失。用户机器之所以看起来正常，是因为根目录里躺着一份9-22 手工复制的旧文件 | ✅ 方向：把登记目标从 `%(ChromeDir)s` 改为 `%(VersionDir)s`（版本目录是整目录搬迁，必然落地），同时让加载器在 exe 同目录找不到时再找 `exe_dir\<FileVersion>\mcloud_flags.txt`；需重编 chrome.dll（单 TU + 链接），改完用 `--system-level` 干净安装复验 |

流程性缺口（不是某一行代码的错）：**本轮之前仓库没有任何 Python 静态检查在跑**。
现已引入 `ruff`（F/E9/B/SIM）+ `pyflakes`，并把 ruff 的真阳性（B023/B905/F841）逐条判真伪后处置。

## 第3周期·扩展轮（D77–D105：导航基准、门禁聚合、src/ 参与度、步骤文档、临时文件）

> 编号说明：本段登记 D77–D100，其中 **D98 未启用**（复核后未成立，编号保留不复用），
> 实际共 23 条。


前一轮的收口报告说"八项门禁全绿"。扩展轮从**未被覆盖的测试面**（导航基准脚本、门禁自身的
聚合逻辑、仓库 `src/` 的实际参与度）继续查，结果先推翻的正是这句话的取证方式（D89）。
全部结论都配了"能失败"的负向对照，方法见 `docs/tasks/bug-review-cycle3-report.md` 扩展轮一节。

### D77 仓库 `src/` 里 344 个"与树内不同、却无人应用"的惰性副本，文档把它们说成主战场（Medium）

- 严重度：Medium（不损坏构建，但系统性误导人与 Agent 的判断）。
- 实测（`.bugreview/src_inventory.py`，对照 `D:\wxmuma\chromium-src-155\src`）：
  `src/` 共 **590** 个文件；**233** 个在树内没有对应路径（真正的仓库独有资产）；
  **12** 个与树内字节一致；**345** 个内容不同，其中被构建流水线真正使用的只有
  `build/config/compiler_opt.gni`（copy_essentials 白名单）1 个 —— 即 **344 个差异副本无人读取**。
  空白/换行归一后仍相同者为 **0**，说明差异是实质内容差异，不是格式漂移。
- 更危险的是新旧混杂：仓库副本 `build/config/BUILDCONFIG.gn`、`build/config/compiler/BUILD.gn`
  里带着上一代内核注入的 polly/avx2 痕迹（分别 8/13 处、9 处），而 `build/config/win/BUILD.gn`
  的副本一处都没有。拿它们和树内比对，会得出"注入丢失"的错误结论。
- 文档口径错误：`AGENTS.md` 写「`src/` — Chromium 覆盖文件（核心）… 112 个文件，修改浏览器行为的
  主战场」，实测 590 个（112 ≈ 当时的 `.cc/.h` 数，现为 106），且"覆盖文件"这个定性只对
  白名单里的 1 个成立。
- 修复：① 生成权威清单 `src/INVENTORY.md`（工具 `.bugreview/src_inventory.py --write`，
  重生成幂等、清单文件自身不计数）；② `AGENTS.md` 口径更正为"素材目录，不是生效修改集"；
  ③ D41 的 `copy_essentials.ALLOWED_COPY` 继续作为唯一整份复制闸门（有上游对应物即拒绝）。
- 验证：`python .bugreview/src_inventory.py` 输出 `总数=590 仓库独有=233 与树一致=12
  与树不同=345 实际被使用=2 惰性差异副本=344`；`INVENTORY.md` 的"实际参与构建"表只含
  compiler_opt.gni 与 chrome_main_delegate.cc（后者标注"副本不生效"）。

### D78–D81 `bench_navigation.ps1`：吞掉输出的"耗时"、无超时、自动变量重名、PS 5.1 没有 `Wait(int)`

`benchmark/bench_navigation.ps1` 是唯一还没被本轮覆盖的基准脚本，逐条读下来有四个问题，
其中两个直接属于本周期目标点名的"性能数据不可信"和"进程卡死"：

- **D78（High，数据有效性）**：旧实现用 `& $exe --headless --disable-gpu … 2>$null | Out-Null`
  测量。`--dump-dom` 什么都没拿到时，进程照样启动→退出，墙钟时间被当成"页面加载耗时"输出。
  实测 M155 上旧 headless 的 dump 可能为空（D68 同族），也就是说这条基准可以长期输出一组
  完全不代表加载性能的毫秒数而毫无征兆。
  修复：显式 `--headless=new`，stdout 落盘并**以 DOM 字节数判成功**（<200 B 记为无效样本，
  不记耗时），任何无效样本都会让脚本以 `导航基准不可信：N 例无效…` 抛出而非静默出数。
  文件头同时声明量具边界：headless 不含 GPU 合成/光栅化路径，只能看相对趋势，
  不能声称测的是真实打开体验（真实渲染路径需要窗口化 + CDP 的 K3 通道，仍在待办）。
- **D79（High，进程卡死）**：`& $exe` 没有超时，页面或网络卡住时整个基准永久挂起。
  修复：`Start-Process -PassThru` + `WaitForExit($TimeoutSec*1000)`，超时即 `Kill()` 并记为
  超时样本；新增 `-TimeoutSec` 参数（默认 60）。
- **D80（Low）**：参数名用了 `$args` / `$profile`，与 PowerShell 自动变量同名，跨作用域取值不可靠。
  修复：改名 `$argv` / `$prof`；profile 目录用 `mcloud_nav_<mode>_<PID>_<guid>` 唯一化，
  清理改为**按本次实例命令行指纹筛 PID**（不再机器级杀进程，D55 口径）。
- **D81（Low，修复自身引入）**：新代码写了 `$p.Wait($TimeoutSec * 1000)`。PS 5.1 的
  `[System.Diagnostics.Process]` 只有 `WaitForExit(int)`，没有 `Wait(int)` →
  `MethodNotFound`，脚本直接失败。修复为 `WaitForExit`，并对全仓 `.ps1` 扫 `\.Wait\(`，
  除注释外零命中。
- 验证：`-Runs 1 -TimeoutSec 45` 实跑，两种模式各 3 个 URL 全部拿到真实 DOM
  （example 2 378 B / bilibili ≈390 KB / qq ≈408 KB），耗时 330/1266/1938 ms 与
  328/1268/1418 ms，退出码 0；单轮差异（qq +36.7%）**不作为结论**——样本数 1，
  远低于本项目"至少 2 次交错重复"的判定门槛。

### D82 benchmark 脚本中文输出被按 GBK 编码，捕获到日志即乱码（Low，含护栏次序坑）

PowerShell 5.1 在 stdout 被管道/文件捕获时按 `[Console]::OutputEncoding`（本机 936/GBK）编码，
`.ps1` 源文件虽有 BOM、解析正确，输出却全是乱码；实测同一次运行的日志里"被测对象"整行不可读。
修复：给 `bench_*.ps1`、`run_baseline.ps1`、`verify_builtin_flags.ps1`、`final_gate_matrix.ps1`
统一加 `try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}`。
次生坑（同轮发现并修）：护栏最初被插在"被测对象身份横幅"（D86）**之后**，而那恰好是最需要
看清的一行；已统一调序为 param → `$ErrorActionPreference` → 护栏 → 其余输出。用无 BOM 的
`UTF8Encoding($false)` 而非 `[Text.Encoding]::UTF8`，避免流首写 BOM。
验证：`bench_size` / `bench_startup` / `bench_navigation` 三个脚本经管道输出全部可读。

### D83 `final_gate_matrix.ps1` 的 `param()` 不在首位，`-OutDir` 被静默丢弃且仍退出 0（High）

PowerShell 要求脚本级 `param(...)` 是**第一条语句**（前面只能有注释/空行）。该文件把它写在
`$ErrorActionPreference`/`Set-Content`/`function`/`$PY` 四行之后，于是 `param` 被当作命令名，
抛 `CommandNotFoundException`（非终止错误，只打印），参数块整体作废：`-OutDir` 恒为默认值，
且因 `ErrorActionPreference='Continue'` 仍返回退出码 0。

- 最小复现（实测）：`$x=1` + `param([string]$y='d')` → 输出 `side effect ran`、
  `param : 无法将"param"项识别为 cmdlet…`、`y=d x=1`，`EXIT=0`。传 `-y HELLO` 被丢弃。
- 影响面评估（诚实口径）：默认值本来就等于目标树（155），所以此前"门禁跑在 155 产物上"这一
  事实成立；这个缺陷咬人的场景是**换树验证**（例如回滚树比对、升级期比对）——那时会测到默认树
  却以为测的是指定树。属于 D72 同族（结果归属错误）。
- 修复：`param([string]$OutDir = '')` 移到注释块之后作为首条语句，并在文件头写下这条语言规则。
- 验证（负向对照即"绑定真的生效"）：`-OutDir D:\BOGUS_TREE_XYZ` 跑门禁，日志与 stdout 出现
  8 处该路径（`chrome.exe 不存在: D:\BOGUS_TREE_XYZ\chrome.exe` 等），说明参数已被消费。

### D84 我用来判 `.ps1` 可行的方法（`PSParser::Tokenize`）本身是盲的（Medium，量具可证伪性）

`Tokenize` 只做词法切分，D83 那类"语句顺序"错误它一个都不报——同一文件我三次得到 `PARSE OK`。
仓库此前**没有任何** PowerShell 静态检查（`verify_sources.py` 只查 Python 与 pak_src C）。
修复：把 `.ps1` 检查并入 `win_scripts/verify_sources.py`，三层——
① 编码规则：含非 ASCII 却无 UTF-8 BOM ⇒ FAIL（D38 约定的机器化）；
② 位置规则：`param(` 出现在任何非注释顶层语句之后 ⇒ FAIL（D83）；
③ AST 规则：`[Language.Parser]::ParseFile` 逐文件解析，有错即 FAIL；
   并且**输入为空 / CHECKED=0 一律判 FAIL**（否则扫描器坏了会被当成"全部通过"）。
可证伪性验证：临时放三个负例文件（param 后置 / 非 ASCII 无 BOM / 少一个 `}`），
门禁分别报出对应 FAIL，`RESULT: FAIL` 且 exit 1；删除后 `PASS 45/45 + AST 45/45`、exit 0。
顺带在同一轮抓到 4 个**真实**在用的文件缺 BOM（`.bugreview/build_m155.ps1`、
`cycle3_settle.ps1`、`wait_then_gate.ps1`、`.diag/collect_stutter_diag4.ps1`），已补 BOM。

### D85 `verify_sources.py` 的 PowerShell 子进程自身把错误信息也编成乱码（Low）

AST 层第一次运行时，PowerShell 抛出的中文错误消息（`语句块…缺少右"}"`）经管道回到 Python 后
显示为乱码——正是 D82 的机制，这次发生在我新写的检查器自己身上。
修复：在临时 lint 脚本首行加同一条 OutputEncoding 护栏。验证：同一条错误现在原样可读
（`[FAIL] PowerShell AST parse: PSLINT|..._negctl_syntax.ps1|2|语句块或类型定义中缺少右"}"。`）。

### D86 十处硬编码 M151 回滚树默认值：不传参就量到旧二进制，日志还看不出测了谁（Medium–High）

`bench_startup/bench_memory/bench_navigation/run_baseline/bench_size/verify_builtin_flags/
bolt_pipeline/pgo_collect/diag_igpu_green_screen` 的默认 `-ChromeExe`/`-OutDir` 全写死为
`D:\wxmuma\chromium-src\src\out\mcloud`（那是 M151 回滚参考树，当前发布对象在
`chromium-src-155`），且**没有一个脚本在输出里说明自己测的是哪个文件**。
后果与 D72 同类：结果归属错误，而且看起来完全正常。
修复（统一口径而非逐处改路径，避免下次换树再犯）：
① 默认值改为空串 + 运行时解析：`$env:MCHROME_EXE` / `$env:MCHROME_OUT` → 再退回 155 树；
② 打印被测对象身份：绝对路径、字节数、mtime、同目录 `mcloud_flags.txt` 是否存在
   （缺失即提示"内置优化不生效，结果无意义"）；
③ 路径命中回滚树特征（`chromium-src\`）时 `Write-Warning` 明示"不是当前发布对象"；
④ 目标目录/文件不存在直接 `throw`（旧 `bench_size` 只是打印空表）。
验证：`bench_startup` 输出 `被测对象: …chromium-src-155…chrome.exe | 4,389,888 B |
mtime=2026-10-11T00:20:49 | 内置标志文件=同目录存在`；`bench_size` 输出 `chrome.dll=
303,440,384 B`，与当前产物一致。

### D87 `flag_stability.py` 隐含依赖"tag 对象存在于 M151 参考树"，缺失时表现为一堆无意义 FAIL（Medium）

A–F 断言全部用 `git grep <rev>` **按修订**取证（所以指向 `chromium-src\src` 是对的：那棵树里
fetch 过 155/156 的 tag 对象，工作树没动）。但这条外部前提没写下来、也没校验：一旦该树被重新
clone/sync 不带 tags，三个 rev 全部解析失败，工具会输出一大片"未找到"的断言 FAIL，把根因藏起来。
修复：新增 `_require_revs()` 前置校验（`git rev-parse --verify <rev>^{commit}`），
失败即给出可执行修复指引并以 **exit 2** 退出；同时打印每个 rev 实际解析到的 commit，
再支持 `--tree <path>` / `FLAG_STAB_TREE` 换取证仓库（与 D86 的"被测身份要可见"同一原则）。
验证：`--tree D:\wxmuma\thorium` → `FAIL: 在 … 中解析不到修订 151.0.7922.99（基线）——tag 对象缺失`
+ exit 2；正常跑 → 打印 `151.0.7922.99 -> fbb5d9fd5e73 / 155.0.8059.40 -> cfaadc5a132d /
156.0.8078.12 -> 634b046faf21`，A–F 全 PASS（53/53 条目三版全存活）。

### D88 我新加的 `--tree` 解析顺序错，把路径当成了"基线修订"（Low，修复自身引入）

`_ARGS` 先按位置分配 REV151/155/156，再摘 `--tree` 的值 ⇒ 那条负向对照最初报出的是
"解析不到修订 D:\wxmuma\thorium"。改为先摘 `--tree` 值再分配位置参数（`.remove()` 只摘一次）。
验证：重跑同一条负例，消息变成"解析不到修订 151.0.7922.99（基线）"，exit 2 不变。

### D89 收口门禁的聚合逻辑恒报 ALL PASS——"门禁的门禁"是坏的（Critical）

`final_gate_matrix.ps1` 里 `Invoke-Gate` 函数体内用 `$results += …` 汇总。PowerShell 的作用域规则
是"读父作用域、写即建本地副本"：函数内的 `+=` 只累加到函数的局部变量，脚本级 `$results`
永远为空 ⇒ 汇总表一行都不打印、`$bad.Count -eq 0` 恒成立 ⇒ **无论各门禁实际成败，都输出
`RESULT: ALL PASS` 并以 0 退出**。

- 决定性证据（bogus 树实跑）：日志同时出现 `leak_probe(2x15) => exit=1`
  （`FileNotFoundError`，chrome.exe 不存在）与 `RESULT: ALL PASS`，进程退出码 0。
  修复后同一条命令如实报 `RESULT: FAIL x5`、exit 1，并把 8 行逐项表打到 stdout。
- 对既有结论的影响（必须说清）：本报告与 M155 升级记录里"八项门禁全绿"的**摘要行不可作为证据**。
  逐门禁的真实退出码此前已分别独立取证（verify_sources / flag_stability / loader_edge_test2·3 /
  A6 子进程命令行探测 / leak_probe / package_m155 各自有日志与退出码），本轮又用真树重跑一遍
  复核；扩展轮之后的收口以"逐项表 + 条数自检"为准，不再引用 ALL PASS 摘要。
- 修复四条（都在同一文件）：① `$script:results += $row` 显式写脚本作用域；
  ② 汇总自检 `$results.Count -ne $EXPECTED_GATES` ⇒ FAIL（采集数与调用点数不符时，
  门禁自身坏了不能当通过）；③ `ExitCode` 为 `$null` 时判 `NOEXIT` 按失败处理，
  避免"拿不到退出码"被 `-eq 0` 误判；④ 每行结果同步 `Write-Host` 到 stdout，调用方不必
  只依赖日志摘要。删除同类的早期草稿 `.bugreview/cycle3_final_gate.ps1`（同一缺陷，避免两个
  版本并存）。
- 附带清扫：写了 `.ps1` 作用域误用扫描器（顶层 `$x = @()` + 函数体内 `$x +=`），
  排除注释行后全仓只剩已修文件，无第二处。

### D90 `docs/progress.md` §5.1 的"下次更新内核时的操作"跳过了全部定点注入（High）

升级时会照着执行的那份清单（§5.1「下次编译更新内核时的操作」）只写了一步
`python3 $THOR_DIR/win_scripts/copy_essentials.py`，然后把 `args.gn` / `gn gen` / `autoninja` 排下去，
并且 `CR_DIR` 指向 `chromium-src`（M151 回滚参考树）。缺陷不在于某行写错，而在于**缺步骤**：

- 本项目对上游文件的所有定制都由 `deploy_mcloud.py` 编排的定点注入产生
  （`inject_flags_loader.py` 的加载器、`apply_avx2_baseline.py`、`apply_polly_wiring.py` +
  `append_polly_configs.py`、`apply_mcloud_source_defaults.py`、`apply_installer_payload.py`）。
- 只跑 `copy_essentials.py` 的结果是：**编译成功、打包成功、`gn gen --check` 也不报错**，
  但 `chrome_main_delegate.cc` 里没有 `LoadMcloudPerformanceFlags()`、`chrome.release` 里没有
  `mcloud_flags.txt` 条目 —— 53 项 feature + 3 项开关整体静默丢失。这与 D47（安装包不带标志文件）
  是同一个失败模式，只是这次出现在"给人看的步骤文档"里。
- 另外 §5.1 的 `chromium-src` 路径与 AGENTS.md 的多树口径冲突（默认值陷阱，2026-10-10 已踩过一次）。

修复：§5.1 重写为 `deploy_mcloud.py` 作唯一部署入口 + 显式 `CR_DIR`（155 树）+
`verify_sources.py` 作为编译前门禁，并补上 rebase 之后必做的三件事
（重生成 `src/INVENTORY.md`、跑 `flag_stability.py <基线> <新tag> <下一tag>`、
跑 `final_gate_matrix.ps1` 并只认逐项退出码）。

### D91 `docs/BUILDING_WIN.md` 是上游 Thorium 文档，却被 AGENTS.md 指为 Windows 前置文档（Medium）

逐条核对：该文件假设 Chromium 在 `C:\src\chromium\src`、要求 **VS 2022**、让你
`git clone --recursive https://github.com/Alex313031/mcloud.git`（不是本仓库），构建目标是
`autoninja -C out\mcloud mcloud chromedriver mcloud_shell setup mini_installer`
（`mcloud_shell`/`setup` 目标在本 fork 的流程里不存在，而 `setup` 在本项目里恰好是**禁止运行**
的遗留覆盖脚本名，见 AGENTS.md），密钥口径写"私有仓库、联系维护者"，与 ADR-001
（公开密钥入库）冲突。全文**没有一句**提到 `deploy_mcloud.py` 或 `win_scripts/`。

风险不是"读错文档浪费十分钟"，而是它是一个**可执行的错误流程**：新人或 Agent 按 AGENTS.md 的
"前置文档"指引过去，会产出一个不含任何本仓库定制的构建，并且完全看不出哪里出了问题
（与 D47/D90 同类，静默失效链条的源头）。

修复：① 文件顶部加醒目警示块，声明它是上游遗留材料、列出与本项目冲突的四点，
并把权威步骤指向 `AGENTS.md`「构建快速参考」与 `docs/progress.md` §5.1；
② `AGENTS.md` 第 118 行的"前置文档"指针同步更正（并保留 BUILDING_WIN.md 作为工具链背景资料）。

### D92 基准脚本的临时文件删除被 SilentlyContinue 吞掉，留下 42 个文件（Medium，资源泄漏）

D78 的修复给 `Measure-Url` 加了 `-RedirectStandardOutput/-RedirectStandardError`，并在 `finally`
里删这两个临时文件。看起来是对的，实测两次运行（24 次页面加载）后 `%TEMP%` 里留下
**22 个 `navdom_*` + 20 个 `naverr_*`**，单个最大 409 KB。

根因不是路径写错，而是 Windows 句柄语义：`chrome.exe` 主进程退出时，`--dump-dom` 的输出重定向
句柄被子进程（renderer / crashpad-handler）继承，主进程一退出 `finally` 立刻执行 `Remove-Item`
就会撞上 sharing violation；而 `-ErrorAction SilentlyContinue` 把这个失败彻底吞掉——
**泄漏本身不致命，"看不见的泄漏"才是**（同一台机器反复跑基准会持续堆积）。
交互验证：同一批遗留文件在进程全部退出后可以正常删除（`DELETE OK`），证实是时序而非权限问题。

修复三处：
1. 删除失败的文件登记进 `$script:pendingCleanup` —— 这里必须用 `$script:` 前缀，
   否则会重演 D89 的"函数内累加不生效"；
2. `Test-Mode` 的 `finally` 改为**最多 5 轮「按实例指纹杀进程 → 等 600 ms」**，
   之后再调用 `Flush-PendingCleanup()` 重试删除；
3. 重试后仍删不掉的，`Write-Warning` 明确报出数量，不再静默。

验证（判据是"跑完即净"）：清完基线后完整跑一次 `-Runs 1 -TimeoutSec 40`，
结束时 `navdom=0 naverr=0 navprof=0`；同一次运行仍产出 6 个有效样本
（example 329 ms / bilibili 1088 ms / qq 1412 ms，DOM 408 KB 级），说明改动没有牺牲测量本身。

附带收获（同一次实验里再证 D38）：我临时写的检查脚本 `/tmp/nav_leak_check.ps1` 没有 BOM，
其中文字面量在 PowerShell 5.1 下被按 GBK 解析，输出显示为"杩愯缁撴潫"；
而仓库内带 BOM 的 `bench_navigation.ps1` 同一管道里输出完全正常——BOM 规则现在由
`verify_sources.py` 自动把关，临时脚本则不在扫描范围（在仓库外的文件，属一次性工具）。

### D93 我给 `param` 位置写的新检查会产生假阳性（Low，R9 复核时发现）

`check_powershell_static()` 用 `ln.strip().lower().startswith("param(")` 找 param 块。
PowerShell 里 **函数体也可以有自己的 `param(...)`**（惯例缩进 4 空格），那是完全合法的写法，
而脚本级"param 必须首位"的规则对它不适用。按 strip() 判，一个把 `$ErrorActionPreference`
放在前面、后面定义带 param 的函数的脚本会被误判为违规。

危害不是"多打一行日志"，而是**假阳性会把人训练成忽略门禁**（检查失去可信度）。
当前 44 个 `.ps1` 恰好都写成 `function f($a, [string]$b)` 形式（不是函数内 `param`），
所以没有暴露——是 R9 逐行复核新代码时按"这段判据对哪些合法代码会误判"推出来的。

修复：只认**顶格** `param(`（顶层脚本级 param 块的写法），并在文件内注释里写明理由。
两路对照（都实测）：
- 合法对照 `$ErrorActionPreference='Stop'` + `function Get-Thing { param([string]$Name) … }` → 不报；
- 违规对照 `$x = 1` + 顶层 `param([string]$OutDir='')` → 仍报，且门禁 exit 1。

### D94 基线采集器抓不到任何子基准输出，却写出「看起来完整」的报告（High，假绿家族）

`benchmark/run_baseline.ps1` 是 K1/K2/K7 的一键采集器，产物是
`docs/dev-logs/<版本>-benchmark.md`。它有四个叠在一起的问题：

1. **抓不到输出（核心）**：PowerShell 5.1 里 `Write-Host` 写的是 **information stream(6)**，
   而旧代码 `& "$scriptDirench_startup.ps1" … | Tee-Object -Variable k1out` 管道接的是
   **成功流**。三个子基准的所有输出都走 `Write-Host`，所以 `$k1out/$k2out/$k7out` 全是空的。
   同机实测（用 `bench_size.ps1` 做判据）：不加 `6>&1` 捕获 **0 行**，加 `6>&1` 捕获 **6 行**。
2. **KPI 表里没有数字**：表格三行硬编码 `| 见原始数据 |`，而原始数据是空的 ——
   报告看起来结构完整，实际没有任何一次测量结果。
3. **失败不判**：子基准抛异常或被中断后，脚本照样 `Out-File` 写报告并绿色打印
   「报告已写入」，退出码 0。
4. **两处口径/字段错误**：`-Version` 默认值写死 `"M150"`（同时决定报告标题和**文件名**，
   于是 M155 的基线会被归档成 `M150-benchmark.md`）；环境信息行用了 `$env:COMPUTER_NAME`，
   Windows 上的变量名是 `COMPUTERNAME`（无下划线），所以「构建机」字段恒为空。

为什么算 High：这是本周期目标点名的"性能测量有效性"面，而且失效方式是**静默**——
使用者拿到一份格式漂亮的空报告，很难发现里面没有数。

修复（全部落在同一个文件）：
- `Invoke-BenchCapture` 用 `& $script @params 6>&1` 捕获（含子脚本异常，转成
  `SUB-SCRIPT-ERROR:` 行保留在原始数据里）；
- `Get-BenchValue` 按 `K1 …中位数): N ms` / `K2 …中位数): N MB` /
  `out/mcloud 总体积 : N MB`（另抽 `chrome.exe`、`mini_installer`）把数值直接填进 KPI 表；
- 任一 KPI 抽不到数 ⇒ 报告「结论与异常记录」写明哪几项失败，脚本 **exit 1**（报告仍写盘，
  因为它是取证）；
- `-Version` 留空时从被测二进制的 `ProductVersion` 推导（`M155`），不再写死；
- `COMPUTER_NAME` → `COMPUTERNAME`，并在报告里补上被测对象身份行（与 D86 同口径）。

验证（已实跑，产出 `docs/dev-logs/M155-benchmark.md`，退出码 0）：

| KPI | 本次值 | 原始数据 |
|-----|--------|----------|
| K1 冷启动中位数 | **53 ms** | 67, 45, 53, 53, 45 ms（首轮仍是 cold outlier，与既有噪声带一致） |
| K2 内存峰值（50 标签，驻留 90 s） | **2550.5 MB** | 2550.5 / 2550.6 / 2550.2 / 2550.4 / 2553.2 MB，进程数恒 58 |
| K7 体积 | **14,669.27 MB** | chrome.exe 4.19 MB、mini_installer 121.62 MB |

报告里「构建机：WIN-NDKL5A54MFO」（COMPUTERNAME 修正后可见）、标题与文件名自动推导为 M155、
被测对象身份行进报告（D86 口径）。另用微测单独验证捕获/回显/抽值三段：
`LINES=6 VALUE=[14,669.27]`，且把路径改成不存在的目录时按设计落到
`SUB-SCRIPT-ERROR:` 行、`LINES=1`、抽值为空 ⇒ 失败路径可观测、不会伪装成功。

**重要副作用（→ D95）**：K2 同会话 5 次采样的散布只有 2550.2–2553.2 MB（**0.12%**），
而与其它会话记录的 2586.8–2593.0 MB 相差 **~1.5%** —— 跨会话绝对值不能当基线。

补充（同一轮的清扫证据）：全仓 `Tee-Object` 扫描确认这种「用成功流抓 `Write-Host`」的写法**只存在于 `run_baseline.ps1` 一处**，其余脚本没有同类隐患；捕获后新增回显循环，避免采集器变成「控制台全程无输出」的黑箱。

### D99 门禁让边界测试直接改写「发布产物目录」里的 mcloud_flags.txt（Critical）

`benchmark/tools/final_gate_matrix.ps1` 原来设 `$env:LOADER_TEST_OUT = $OutDir`
（真实构建树的 `out/mcloud`），而 `.bugreview/loader_edge_test2.py` / `loader_edge_test3.py`
的工作方式正是：备份 `<OUT_DIR>/mcloud_flags.txt` → 依次写入 BOM 语料 / 空文件 / 垃圾字节 /
3000 条合并上限语料 → 启动该目录里的 `chrome.exe` 观察子进程命令行 → 在 finally 里恢复备份。

这个设计只在「测试正常跑完」时成立。同一会话内连续撞到的实测后果：

- 17:02 与 17:32 两次检查 `out/mcloud/mcloud_flags.txt`，分别看到 **300,063 B** 与
  **106,890 B** 的文件（仓库真身 8,186 B，sha256 前缀 `61b7670856ed`）——即测试正在写、
  或被中断后没恢复。
- 17:32 我打断门禁（Stop-Process）后恢复没执行；紧接着 `.bugreview/flag_runtime_state.py`
  读到**首字节 0xD6、非 UTF-8** 的该文件并抛裸 `UnicodeDecodeError`（那正是垃圾字节用例）。
- 同一条链路上的其它门禁（A6 内置标志验证、leak_probe、runtime_state）都可能落在
  **污染窗口里**：量的是测试语料的行为，却报成「发布配置已验证」。
- 若在这种状态下执行 `autoninja mini_installer`，安装包里打进去的就是测试语料。
  这条恰好被既有防线挡住一半：`.bugreview/package_m155.py` 会比对
  `out/mcloud/mcloud_flags.txt` 与仓库正文，不一致就报 problem（它也是本缺陷的检出手段）。

根因不是某个变量写错，而是**隔离边界画错了位置**：会改写被测文件的测试，
其写入目标不能是发布产物目录本身；把安全性寄托在 finally 恢复上，等于假设进程永不被打断。

修复（三层，全部实测）：

1. 门禁为 loader 测试建**硬链接沙箱** `out/mcloud_loader_test`：同卷硬链接全部运行时文件
   （零拷贝、秒级），只**不**链 `mcloud_flags.txt`（沙箱自己从仓库复制一份）；
   跳过 `args.gn / .ninja_log / .ninja_deps / build.ninja` 以及文件数 > 1000 的一级目录
   （实测 `obj/ 65k`、`gen/ 87k`、`pyproto/`、`win_clang_*`，链接它们要多花几分钟且 chrome
   启动不需要），保留 `locales/ angledata/ resources/ …` 等小目录。
2. 两个测试各加 `_refuse_real_build_dir()`：目标目录出现构建特征文件即 `REFUSED` + exit 2，
   并提示改用沙箱或显式 `MCLOUD_ALLOW_LOADER_TEST_ON_BUILD_DIR=1`。
   （这条防线本身也被实测过：第一次把沙箱建在链了 `args.gn` 的位置时，它立刻把沙箱
   判成构建目录并拒绝——说明判据有效，随后改为不链元数据文件。）
3. 隔离有效性的直接验证：沙箱里跑完 loader 测试后，真实产物文件
   sha256 `61b7670856ed → 61b7670856ed`（UNCHANGED）。

对既有结论的影响（按可证性分级，不是一句"应该没事"）：

- **安装包内容安全（口径已二次修正）**：`.bugreview/package_m155.py` 只做一次字节比对，
  而 `.bugreview/refresh_release.py:92` 早就**知道**这个风险——它的处理方式是"不一致就等 60 秒
  重试，最多 5 次"，注释里写明"这通常说明有一轮验证正在跑，不是包过期"。
  也就是说历史上的防线是**轮询等测试跑完**，而不是消除写入；测试被打断时重试永远等不回来。
  本次产物 `0602cafa…`（127,523,328 B）是在污染窗口之前就构建完成的，installer 载荷与
  `chrome.7z` 内容另有扫描证据（`mcloud_flags.txt` 条目 + 正文内特征串），故发布物本身不受影响。
  真正的问题是这条已知风险**没有传递到新写的门禁**里：`final_gate_matrix.ps1` 连重试都没有，
  直接把测试指向了发布目录。修复因此不是"加等待"，而是消除写入位置（硬链接沙箱）。
- **A6 内置标志门禁**：它断言的是生产清单里独有的条目（`InitialWebUI` 等）。
  测试语料用的是 `EdgeProbeFeat2999` 之类标记名，不含这些条目 ⇒ 该门禁 PASS 本身就说明
  它启动时读的是正文文件，因此此前 A6 的结论可保留。
- **KPI 基线（`docs/dev-logs/M155-benchmark.md`）**：**判定为作废、需重采**。时间线核对结果——
  该报告于 17:23–17:26 采集，而同一时刻门禁矩阵正跑在 loader 边界测试阶段（17:16 启动，
  17:24 前后 chrome 进程数 8 即为测试在跑），也就是说 K1/K2 极可能是在
  `out/mcloud/mcloud_flags.txt` 被换成测试语料的窗口里测的：那种状态下浏览器**没有内置优化清单**，
  K1/K2 数字不代表发布配置。文件在 17:33 才恢复为正文（8,186 B / `61b7670856ed`）。
  处置：D99 的硬链接沙箱生效后**重新采集一份**，旧文件保留但在开头标注作废原因。
- **flag_runtime_state**：崩溃前读到的是垃圾文件（D100），故其此前一轮的输出只作参考；
  收口重跑时它会先做正文一致性检查，不一致直接 exit。

### D100 `flag_runtime_state.py` 读到被污染文件时抛裸 traceback，且发现不一致仍继续给结论（Medium）

三处叠加：① 用 utf-8 硬读构建目录 flags，遇到垃圾字节抛
`UnicodeDecodeError: ‘utf-8’ codec can’t decode byte 0xd6 in position 0`，
既没指出「这是产物目录被测试污染」也没给恢复方法；② 它其实已经算出「与仓库不一致(!)」，
但只打印一行就继续做运行时比对，于是结论不属于发布配置；③ `--control` 对照实验会往
生产 flags 文件追加一行再在 finally 恢复，同样依赖「不被打断」。

修复：① 按 `utf-8-sig` 读字节再解码，失败时 `SystemExit` 说明「几乎一定是 loader 边界测试
被中断后留下的测试语料」并给出恢复方法（copy 仓库文件 / 重跑 deploy_mcloud.py）；
② 与仓库正文不一致时**直接 exit**，只有显式 `--allow-drift` 才继续（并打出大小差异）；
③ 保留 finally 恢复，但前置检查让它不再需要信任恢复。

纪律（已写进 AGENTS.md）：**测试不得写入发布产物目录**；会改写被测文件的测试一律在
硬链接沙箱里跑；写生产位置的动作必须有「特征文件即拒绝」的前门，而不是依赖 finally 恢复。

### 扩展轮的全局效率结论（稳定优先，不是局部最优）

- **优先级重排**：D89 > D78/D79/D83/D86 > D77/D84/D87 > D80/D81/D82/D85/D88。
  判据不是"改动大小"而是"错了会不会被看出来"：假绿与归属错误（D89/D72/D86）一旦成立，
  整条验证链的输出都不再是证据，比任何单点性能项都贵。
- **护栏顺序是语义的一部分**：D82 的护栏若排在首条中文输出之后，就恰好把它最该保护的那行
  留在乱码里；D83 的 `param` 位置、D89 的作用域同理——都是"看起来能跑、实则失效"的次序问题，
  所以修复必须配一个"能失败"的对照，而不是只跑一次成功样例。
- **不为局部最优牺牲可复现性**：仓库 `src/` 里 344 个惰性副本，看起来最"优"的解是直接删掉
  （少 344 个误导源），但那会一起丢掉 Thorium/Mcloud 的历史对照材料，且 ADR-003 只发 Windows
  x64、其余平台的副本本就是参考件。选择「清单化 + 文档更正 + 保留」，代价是一份自动清单，
  收益是任何 Agent 打开目录第一眼就能看到「这个文件没人用」。

## 修复状态汇总（2026-10-09 第2周期更新；扩展轮补行见末尾）

| 线 | 缺陷 | 修复 | 验证 |
|----|------|------|------|
| 基准/导航 | D78/D79/D80/D81 | ✅ DOM 字节判成功 + WaitForExit 超时 + 自动变量改名 + 实例级清理 | 实跑 2 模式×3 URL 全取到真实 DOM（2.4 KB/400 KB 级），退出码 0 |
| 工具输出 | D82/D85 | ✅ 7 个 `.ps1` 加 UTF-8 输出护栏并调至首条输出之前；lint 子进程同样处理 | 管道捕获输出全部可读 |
| 门禁自身 | D83/D84/D89 | ✅ param 归位 + `verify_sources.py` 新增 BOM/param 位置/AST 三层检查 + 聚合改 `$script:` 并自检条数 | 三个负例文件各自被检出 FAIL；bogus 树下门禁如实报 `FAIL x5`/exit 1 |
| 结果归属 | D86/D87 | ✅ 默认值改为 env+155 并打印被测身份；flag_stability 前置校验三个修订 | 横幅打印 exe/dll 路径、大小、mtime、flags 文件状态；负例 exit 2 |
| 文档口径 | D77/D90/D91 | ✅ 生成 `src/INVENTORY.md`（工具 `.bugreview/src_inventory.py`）+ AGENTS.md 口径与"前置文档"指针更正 + `progress.md` §5.1 改以 `deploy_mcloud.py` 为唯一部署入口 + `BUILDING_WIN.md` 顶部加"上游遗留、非本仓库步骤"警示 | 实测 590/233/12/345/344，真正参与构建的只有 1 个副本；§5.1 与 `deploy_mcloud.py` 的 8 个注入步骤逐条核对一致 |
| 修复次生 | D88 | ✅ `--tree` 先摘值再分配位置参数 | 负例消息指向真正的修订名 |
| pak_src | D1-D24 | ✅ 代码已改 | ✅ ASan 语料 8 组优雅报错 + v4/v5 往返字节一致（failures=0） |
| flags 加载器 | D21/D22/D23/D33 | ✅ 注入器 v2（含 D33 include 路径修复）+ 树内升级 | ✅ A6 3/3 + 边界套件（v2 语料 9 例） |
| flags 加载器 | D39/D40 | ✅ loader v3 合并值上限 + v4 全量字节预算（v5 去裸指针告警） | ✅ v3 实测 106KB 语料不崩（`probe_huge`）；✅ v5 二进制 11/11 边界用例通过（含 250KB `--js-flags` 与 4000 个普通开关） |
| win_scripts | D28-D31 | ✅ | verify_sources.py 通过 |
| 架构/文档 | D41（陈旧副本被文档指向） | ✅ AGENTS.md 改口径 + 副本头注释 + copy_essentials 白名单断言 | py_compile + 清单复核 |
| 文档 | D42（标志数量口径矛盾） | ✅ 统一为实测 63 行/60 feature + 3 开关，附复算方法 | 计数脚本实测 |
| 发布方法 | D43（installer 明文搜索无效） | ✅ 改为 chrome.7z 载荷扫描 + 打包输入判据 + mtime 链条 | 实测：installer 内 chrome.dll 亦 MISS；chrome.7z 命中条目名与新鲜度标记 |
| 发布完整性 | D44（sidecar 与包体不同步） | ✅ 发布脚本重算哈希并写 `.sha256` | sidecar 与包体同批重算一致（当前发布包 `054efb37…05ab389f`） |
| 发布链路 | D45（release.yml 资产前提不成立） | ⚠️ 口径与前提已写清 + 本版 release notes 落地；工作流改造待决（A/B） | 读 `.github/workflows/release.yml` 全文与 GitHub 100MiB push 限制核实 |
| 发布内容 | D46（notes 按 mtime 选取导致正文错误） | ✅ 改为文件名日期前缀三级匹配 + ref 值校验；notes 文件改名带内核主版本 | 5 个 tag 本地干跑选取结果全部正确；线上正文待重跑 tag 覆盖 |
| 文档 | D31/D32 | ✅ | 人工复核 |
| benchmark | D35/D38 | ✅ | PS 5.1 解析通过 + K1=68ms |
| 遗留风险 R5 | Linux legacy 面（D28 子项）| — | owner: 项目方；建议下次整理时删除或加 refusal guard（ADR-003 不维护面）|
| 遗留风险 R6 | 子进程 feature 列表由 Chromium 归一化（去重+排序），同名双写不保证用户优先 | — | 口径：改 `mcloud_flags.txt` 或用 `--disable-features`，不依赖双写；已实测记录于 D39/D40 之后的方法记录 |
| 遗留风险 R7 | MSVC ASan 无 leak detector（/fsanitize=address 不支持 detect_leaks） | — | pak_src 泄漏面以 ASan 溢出/UAF + 往返一致性覆盖；泄漏需 WPA/Dr.Mem 另行取证 |

## 待办（本档案跟踪）
- [x] D47：补 `apply_installer_payload.py`（chrome.release 单行幂等注入）并挂入 deploy_mcloud.py + verify_sources.py（r3 已发布）
- [x] D48：清理失效条目（删 6 / 注释改名 1 / 标记升级期 1）已随 r3 发布；存活性校验已进本地轮次门禁（round_check 门 10），CI 不接入原因见上文 D48
- [ ] D49：V8 连字符/下划线口径做一次运行时歧义实验后更正文档
- [x] D51：`mcloud_flags.txt` 第 24 行 InitialWebUI params 改写为 `param/value` 合法语法（净行为不变，
      已用 `flag_runtime_state.py` 改前后回显逐项一致证明），E 断言加奇数 token 校验并做负向对照
- [x] 第3周期 D52–D67 全部修复：测试工具改实例级指纹统计与清理（取不到进程即判 FAIL）、
      外部调用补 timeout、bench 清理进 finally、注入器一律正文比对升级器（含调用点校验）、
      加载器 v6（BOM 剥离 + 浏览器进程限定）、Polly 改 cflags。
      证据：`loader_edge_test2` 11/11、`loader_edge_test3` 7/7（M155/v6），
      T1 在 M151(v5) 上为 Red；`flag_stability` E/F 断言各有负向对照
- [ ] 第3周期遗留：`gn gen --check` 后出现整树重编（51,296 步）的确切成因待查；
      以后只改 GN 前先用 `autoninja -n` 看计划步数再决定是否 gen（owner：项目方）
- [ ] 第3周期遗留：工具侧 SIM115（`open()` 未用 with，79 处）统一收口；
      `win_scripts/setup.py` 删除或加 refusal guard（其 lint 噪声随之消失）
- [x] D1-D19 修复（pak_src/，2026-10-08）
- [x] pak 修复后语料回归：8 组畸形输入优雅报错 + v4/v5 真实往返字节一致（ASan，failures=0）
- [x] flags 加载器合并顺序缺陷 D21/D22/D23：注入器 v2 + 树内升级（重编译验证进行中）
- [x] win_scripts/*.py 深审（D28-D31 修复，verify_sources 通过）
- [x] 源码树 7 个定制 hunk 全量审查（BUILDCONFIG/compiler/win BUILD/loader/background/media_switches/chrome.release）
- [x] 第2周期：树内 MCloud 定制 C++ 全量差分审计（`git diff` 仅 4 文件/111 行；仓库 src/ 危险 C 调用 0 处）
- [x] D39 修复并实测（loader v3，106KB 语料不崩 + 内置列表不入子进程）
- [x] D40 修复（loader v4 全量字节预算）+ v5 告警清零与注入器正文比对
- [x] v5 重编译后：边界套件 11 例 + 五轮门（round_check.sh 已加门 7 = 加载器边界套件）
- [x] 发行包重生成：v5 源码强制全量重做并发布（SHA256 054efb37…05ab389f，sidecar 同步写盘，见 D44）
- [x] 五轮 bug + 全功能回归（第2周期轮次 6-10，每轮 8 门全绿，K1=51ms 无回归）
