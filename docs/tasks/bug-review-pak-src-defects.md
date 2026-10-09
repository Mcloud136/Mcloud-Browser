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
  SHA256 `d558d755…4927fd4e`（123,466,240B，构建于 15:58，加载器 v5）。
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

## 修复状态汇总（2026-10-09 第2周期更新）
| 线 | 缺陷 | 修复 | 验证 |
|----|------|------|------|
| pak_src | D1-D24 | ✅ 代码已改 | ✅ ASan 语料 8 组优雅报错 + v4/v5 往返字节一致（failures=0） |
| flags 加载器 | D21/D22/D23/D33 | ✅ 注入器 v2（含 D33 include 路径修复）+ 树内升级 | ✅ A6 3/3 + 边界套件（v2 语料 9 例） |
| flags 加载器 | D39/D40 | ✅ loader v3 合并值上限 + v4 全量字节预算（v5 去裸指针告警） | ✅ v3 实测 106KB 语料不崩（`probe_huge`）；✅ v5 二进制 11/11 边界用例通过（含 250KB `--js-flags` 与 4000 个普通开关） |
| win_scripts | D28-D31 | ✅ | verify_sources.py 通过 |
| 架构/文档 | D41（陈旧副本被文档指向） | ✅ AGENTS.md 改口径 + 副本头注释 + copy_essentials 白名单断言 | py_compile + 清单复核 |
| 文档 | D42（标志数量口径矛盾） | ✅ 统一为实测 63 行/60 feature + 3 开关，附复算方法 | 计数脚本实测 |
| 发布方法 | D43（installer 明文搜索无效） | ✅ 改为 chrome.7z 载荷扫描 + 打包输入判据 + mtime 链条 | 实测：installer 内 chrome.dll 亦 MISS；chrome.7z 命中条目名与新鲜度标记 |
| 发布完整性 | D44（sidecar 与包体不同步） | ✅ 发布脚本重算哈希并写 `.sha256` | sidecar = `d558d755…4927fd4e`，与包体实算一致 |
| 文档 | D31/D32 | ✅ | 人工复核 |
| benchmark | D35/D38 | ✅ | PS 5.1 解析通过 + K1=68ms |
| 遗留风险 R5 | Linux legacy 面（D28 子项）| — | owner: 项目方；建议下次整理时删除或加 refusal guard（ADR-003 不维护面）|
| 遗留风险 R6 | 子进程 feature 列表由 Chromium 归一化（去重+排序），同名双写不保证用户优先 | — | 口径：改 `mcloud_flags.txt` 或用 `--disable-features`，不依赖双写；已实测记录于 D39/D40 之后的方法记录 |
| 遗留风险 R7 | MSVC ASan 无 leak detector（/fsanitize=address 不支持 detect_leaks） | — | pak_src 泄漏面以 ASan 溢出/UAF + 往返一致性覆盖；泄漏需 WPA/Dr.Mem 另行取证 |

## 待办（本档案跟踪）
- [x] D1-D19 修复（pak_src/，2026-10-08）
- [x] pak 修复后语料回归：8 组畸形输入优雅报错 + v4/v5 真实往返字节一致（ASan，failures=0）
- [x] flags 加载器合并顺序缺陷 D21/D22/D23：注入器 v2 + 树内升级（重编译验证进行中）
- [x] win_scripts/*.py 深审（D28-D31 修复，verify_sources 通过）
- [x] 源码树 7 个定制 hunk 全量审查（BUILDCONFIG/compiler/win BUILD/loader/background/media_switches/chrome.release）
- [x] 第2周期：树内 MCloud 定制 C++ 全量差分审计（`git diff` 仅 4 文件/111 行；仓库 src/ 危险 C 调用 0 处）
- [x] D39 修复并实测（loader v3，106KB 语料不崩 + 内置列表不入子进程）
- [x] D40 修复（loader v4 全量字节预算）+ v5 告警清零与注入器正文比对
- [x] v5 重编译后：边界套件 11 例 + 五轮门（round_check.sh 已加门 7 = 加载器边界套件）
- [x] 发行包重生成：v5 构建产物已发布（SHA256 d558d755…4927fd4e，sidecar 同步写盘，见 D44）
- [x] 五轮 bug + 全功能回归（第2周期轮次 6-10，每轮 8 门全绿，K1=51ms 无回归）
