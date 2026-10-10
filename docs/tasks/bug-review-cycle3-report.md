# bug-review 第3周期报告 — 性能 / 内存 / 进程卡死 全面测试 + 全局效率评审

- 日期：2026-10-10（承接第1周期 pak_src、第2周期 flags 加载器内存安全）
- 触发：用户要求"全面详细测试是否存在影响性能、内存溢出、进程卡死的缺陷；完成后分析所有代码是否以稳定为前提的最优效率；最后做五轮深度 review"
- 专业视角：C++（Chromium base/content 启动路径）、Python 3.12、PowerShell 5.1、GN
- 被测对象：M155 构建（`D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe`，loader v6）
  与 M151 构建（同路径旧树，loader v5）作为 Red 对照
- 新增工具面：`ruff 0.17` + `pyflakes 4.0.3`（此前**仓库没有任何 Python 静态检查在跑**，属流程缺口）

## 1. 范围与真实代码面

`git diff --stat` 实测被编译进产物的定制面只有 6 个文件 / 229 行：

| 文件 | 行数 | 性质 |
|---|---|---|
| `chrome/app/chrome_main_delegate.cc` | +167 | 运行时 flags 加载器（唯一有内存/卡死风险的 C++ 面） |
| `build/config/compiler/BUILD.gn` | +39 | polly / emit-relocs config（当前 use_polly=use_bolt=false，展开为空） |
| `build/config/BUILDCONFIG.gn` | +17 | 把上述 config 接到可执行/共享库默认列表 |
| `build/config/win/BUILD.gn` | +5/−2 | AVX2+FMA3 等基线 |
| `chrome/browser/background/extensions/background_mode_manager.cc` | +1/−1 | 后台模式默认 false |
| `chrome/installer/mini_installer/chrome.release` | +1 | D47：登记 `mcloud_flags.txt` 进载荷 |

外围脚本面：`win_scripts/*.py` 15 个、`benchmark/*.ps1` 5 个、`benchmark/tools/*.py`、
本轮新入库的 `.bugreview/*.py` 验证脚本 16 个。

## 2. 缺陷清单（D52–D72，全部带 file:line 与复现）

| # | 严重 | 位置 | 类别 | 一句话 | 状态 |
|---|---|---|---|---|---|
| D52 | High | `bench_memory.ps1:61`、`leak_probe.workset_mb()` | 测量有效性 | 按进程名汇总**整机** chrome，K2/驻留与被测实例无因果关系 | ✅ 改为实例级 PID 筛选 |
| D53 | Medium | `leak_probe.py:DEV_PORT=9333` | 串台/安全 | 写死调试端口，可能驱动别的实例却量我们的内存 | ✅ 每次 `bind(0)` 取空闲端口 |
| D54 | Medium | `bench_startup.ps1`、`bench_memory.ps1` | 进程堆积 | `ErrorActionPreference=Stop` 但清理不在 finally → 异常路径留孤儿 chrome + 临时目录 | ✅ 包进 try/finally |
| D55 | High | `leak_probe`、`gpu_probe`、`ab_flags.kill_chrome` | 用户可见破坏 | 测试工具无条件 `Get-Process chrome \| Stop-Process`，会杀掉用户自己的浏览器会话 | ✅ 全部改为按临时 profile 指纹只杀本实例 |
| D56 | Medium | 12+ 处 `subprocess.run` | 无声挂死 | PowerShell/WMI/git grep 全无 timeout，一处卡住整条链停住且无报错 | ✅ 统一补 timeout（180/600/900 s） |
| D57 | Low–Med | `inject_flags_loader.py` LOADER | 静默失效 | 不剥 UTF-8 BOM → 首行被整条丢弃（PowerShell 5.1 写文件默认带 BOM） | ✅ 按字节剥离 + T1 用例证明 |
| D58 | Low | 调用点 `BasicStartupComplete` | 效率/一致性 | 每个子进程都重复读盘解析，并按各自命令行重算预算（跨进程不一致面） | ✅ 加 `kProcessType` 限定；不主张可测收益 |
| D59 | Medium | flags 文件语法 | 静默失效 | 活动行尾写 ` # 备注` 会让该条整条被忽略 | ✅ 新增 F 断言静态拦住（不改运行期语义） |
| D60 | Medium | `loader_edge_test2.py:12` | 测错对象 | 硬编码 M151 树路径：会测旧二进制并改写旧树 flags | ✅ 改 `LOADER_TEST_OUT` |
| D61 | Low | `win_scripts/clean.py` | 潜在危险 | 残留 `try_run(shell=True)` 死代码 | ✅ 删除 |
| D62 | High | `inject_flags_loader.py` has_block 分支 | 静默 no-op | 正文一致即 exit(0)，从不校验调用点 → 调用行丢失时"63 行优化整体静默消失"却报 already up to date | ✅ 调用点校验前置 + 标记顺序断言 |
| D63 | Medium(潜伏) | `append_polly_configs.py` | "开了也没开" | Polly 是编译期 pass 却写进 ldflags；Windows 分支给 lld 发 BOLT 不支持的参数 | ✅ 改 cflags / emit-relocs 加 `!is_win` |
| D64 | Medium | `append_polly_configs.py` | 静默不一致 | 见到 `config("polly")` 就只补 import 后退出，正文永远停在首版 | ✅ 改为正文比对式升级器 |
| D65 | Medium | `.bugreview/d49_experiment.py` | 证据不可信 | 读取线程闭包捕获循环变量（B023 真阳性），可能采到别的用例的 stderr | ✅ `_reader(p=p, chunks=chunks)` 显式绑定 |
| D66 | Medium | 本周期修复自身 | 次生缺陷（自查发现，按证据强度分级） | ①**已证实**：PowerShell 里 `double + '\|' + int` 抛"无法把 '\|' 转成 System.Double"（独立复现见 §4），被 `except ValueError` 吞成 `0.0 MB / 0 进程` → 量具静默产出假数据；②**已证实**：`loader_edge_test3` 的 `launched`/`nproc` 在清理之后才取 → 7 例假 FAIL；③**假设未证实**：完整路径实例指纹可能因 8.3 短名 vs 长名落空——当时的 0 读数由 ① 已充分解释，③从未复现，改叶子名只是"两种写法里更稳的一种"而非已证明的修复 | ✅ ① 改 `-f` 格式化；② 取值顺序前移；③ 统一叶子名并把"0 进程"变成硬 FAIL（护栏独立于 ③ 是否成立都值得加） |
| D67 | Medium | `apply_avx2_baseline.py:12`、`apply_polly_wiring.py:14` | 静默分叉 | 都用 `if "<标志串>" in s: exit(0)` 判"已应用" → **改了标志列表/接线正文再跑，树里仍是老版本**（与 D64 同族） | ✅ 两个脚本都改为正文比对式升级器（不一致整段替换；上游形状变了则带指引地报错） |
| D73| Low| apply_mcloud_source_defaults.py| 上游把 BASE_FEATURE 拆成多行写时，精确单行匹配同时看不到 ENABLED 与 DISABLED：自愈失效且误报「形态已变更」→ deploy 直接退出| 加空白归一化兜底匹配（跨行形态实测 rc=0 且不误写） |

D66 值得单独留档：**修 D52/D55 的那一批改动自己带了三个新缺陷，全部被回归测试当场抓出来**。
其中第 ③ 个（PowerShell 数字与字符串用 `+` 拼接会抛类型转换异常，而异常被宽 `except` 吞掉）
是本轮最隐蔽的一个：它让"实例级内存采样"看起来完全正常地返回 0，却仍然打印 PASS。
这正是"每改一处判据/工具，必须立刻跑一次能失败的正例 + 让取不到数据变成硬失败"的必要性证据。

## 3. 五轮深度 review（每轮一个视角，逐条落到 file:line）

### R1 内存与所有权（C++ string/size_t 边界、Python 句柄与临时资源）
- LOADER：`substr(2, equals-2)` 在 `equals==2`（`--=v`）时得到空名并被 `switch_name.empty()` 拦下；
  `line=="--"` 走无 `=` 分支同样得到空名；`-` 开头不带 `--` 的行被 `StartsWith("--")` 拒绝。
  BOM 剥离有 `contents.size() >= 3` 前置。预算比较全部是 `cost > 预算 - 已用`，
  而"已用 ≤ 预算"由每次加账前的同一判断维持 → **不存在无符号下溢**。
  读文件上限 1 MiB（D23 遗留的 v2 修复仍在位）。
- Python：`ab_flags`/`flag_runtime_state` 用 `json.dump(..., open(...))` 依赖引用计数关句柄（ruff SIM115 79 处同类）。
  结论：**CPython 下不构成泄漏**，本轮不改（改了会稀释真正重要的 diff）；已在待办里记为"工具侧统一收口"。
- 真实修复：D65（线程闭包捕获循环变量）、D53（端口占用串台）、D54（孤儿进程）。

### R2 并发与卡死
- 全部 PowerShell/WMI 与 git grep 调用补 timeout（D56）；`ab_flags.kill_chrome()` 把超时降级为
  "跳过清理并打印警告"，**绝不**回落到机器级强杀（避免 D55 的回退路径）。
- `deploy_mcloud.py` 每步 900 s timeout：某步挂死时 deploy 以非零码退出而不是无声停住。
- `leak_probe` 主循环现在在 `nb == 0` 时直接判 FAIL 返回 2（防止"采不到却报 PASS"这一类静默假绿）。

### R3 边界输入与解析
- 语料覆盖：BOM、CRLF、无末尾换行、空文件、文件缺失、二进制垃圾、未闭合引号、GBK 注释、
  250 KiB `--js-flags`、4000 个普通开关、3000 条 feature（触发合并上限）、同名双写、行内注释。
- 结论：v6 二进制下 11 例（test2）全 PASS；test3 的 7 例见 §4。
  行内注释（T6）实测**不进入**回显 → 证实 D59 的"整条失效"而非"仅注释部分被忽略"。
- 同名双写（T5）实测：`--disable-features=X` 在回显中可见、enable 侧不可见 → 与
  `base/feature_list.cc:449-452` 的"禁用先注册 + emplace 首条生效"一致，写成产品口径。

### R4 静默失效与证据链（本项目最贵的一类缺陷）
- D62（调用点校验前置）、D64（polly 无升级路径）、D60（测试脚本硬编码旧树）、
  D57/D59（flags 语法静默丢件）都属于同一族：**流程输出绿色但实际内容没生效**。
  处置原则统一为：注入器一律"正文比对 + 关键锚点存在性校验"，静态门禁再加一层语法形状校验（E/F 断言）。
- 每条修复都要求"能失败的正例"：D59 用临时加行内注释让门禁 FAIL 再恢复；D62 用删调用点的副本
  得到 exit 1；D64 用 BUILD.gn 副本连跑两次得到 replaced → already up to date。

**追加发现（同一轮内，D68–D72）——全部是在"跑自己的验收脚本 / 跑自己的构建链"时暴露的**

| # | 严重 | 位置 | 事实与证据 |
|---|---|---|---|
| D68 | Medium | `benchmark/tools/verify_builtin_flags.ps1` | A6 的主路径 `--headless=new --dump-dom chrome://version` 在 M155 上**不再返回该页 DOM**（实测无输出）。脚本会落到兜底分支，于是"规范 4.1.1 写明的验证方法"事实上已经失效，只剩兜底在做事后补救；一旦兜底也出问题，门禁会给出没有依据的结论 |
| D69 | Low | 同上 | 兜底分支的过滤器是 `CommandLine -like "*$exeDir*"`（整个 out 目录），会把**别的实例**（另一个探针、另一次 A/B）的命令行一起读进来 → 假阳性 |
| D70 | High | 同上 | 清理临时目录用裸 `Remove-Item -Recurse -Force`，而 profile 的 `lockfile` 仍被无头实例子进程占用 → 抛 IOException；`$ErrorActionPreference='Stop'` 让脚本**在探测之前就终止**（实测真实退出码 1），并且留下一整组孤儿 chrome（实测 9 个）。旧版退出码还被管道吃掉，看起来像成功 |
| D71 | High | `benchmark/tools/leak_probe.py` 等 | 实例清理是**一次性** kill：浏览器被杀时 crashpad-handler 会重启，残余进程继续持有 `out/mcloud` 里 DLL 的句柄。实测后果：`lld-link: error: failed to write output './dxcompiler.dll': permission denied` → `autoninja exit=1`，51,296 步的重编被自己的测试工具打断 |
| D72 | High | `.bugreview/package_m155.py` + `cycle3_finalize.ps1` | 编译失败后链上继续跑打包，门禁只看"产物存在 + 内容证据 + installer≥dll"，于是拿**上一轮遗留的 installer** 算出 `cd6f5172…` 并打印"门禁全绿"、写进发布说明。门禁无法区分"构建成功"与"构建失败但产物还在" |

修复与原则：
- A6 脚本重写为**子进程命令行主路径**（实例 GUID 指纹筛选、取不到进程即 throw、
  禁用侧 `SkiaGraphite` 也要证明、清理全部 `SilentlyContinue` 且放进 `finally`、
  收尾检查 `mcloud_a6_*` 残留并按失败处理）。PSParser 校验 PARSE OK。
- `leak_probe/gpu_probe/ab_flags` 的实例清理改为**循环杀到干净**（最多 4 轮，仍有残留就打印 WARN），
  不再指望一次性 kill。
- `package_m155.py` 增加新鲜度链：`chrome.dll` 必须不早于 `chrome_main_delegate.cc`，
  且不早于 4 个 GN 源文件；`cycle3_finalize.ps1` 在 `autoninja` 非零时**直接退出，不再打包**。
  这条正是"能失败的正例"：在修复前跑一次就产出了假的"门禁全绿 + 新哈希"。
- 规范 4.1.1 的验证方法描述随之更正（不能再写"通过 chrome://version 抽查"作为主路径）。

### R5 效率与全局最优（详见 §5）

## 4. 证据

命令与完整输出见 `.bugreview/cycle3_verify.log`、`.bugreview/cycle3_verify2.log`。

- 静态分析：`python -m ruff check --select F,E9,B,SIM win_scripts benchmark .bugreview`
  → 首轮 119 条（含 B023×2 真阳性、B905×1、F841×1、其余为 SIM115/F401/F541 类风格项）；
  本轮修完真阳性与全部 High/Medium 项，剩余集中在**禁止运行**的遗留脚本 `win_scripts/setup.py`。
- 加载器回归（M155 / v6）：`loader_edge_test2.py` → `SUMMARY: 11/11 cases PASS`
  （含 L-huge-merge-3000 触发合并上限、L-jsflags-oversized 触发字节预算两条关键路径）。
- 修复后的 K2 口径变化：实例级筛选下 50 标签 **2512.85 MB / 57 进程**，
  而整机口径此前给出 2586.8 MB / 58 进程 → 差值即"多算了一个不属于被测实例的进程"，D52 成立。
- `flag_stability.py` 新增 F 断言后：正常清单 PASS；临时注入行内注释 → `稳定性结论: FAIL`
  （A/C/F 三条同时命中），随后恢复逐字节一致。

**加载器边界套件（`loader_edge_test3.py`，7 例，本轮新增）**

| 用例 | M155（loader v6） | M151（loader v5，Red 对照） | 结论 |
|---|---|---|---|
| T1 BOM + 首行即 flag | **PASS**（marker=True，实例 9 进程） | **marker=False** | 该用例确有鉴别力；D57 修复生效 |
| T2 空文件 | PASS（起来，不带任何内置 feature） | 同 | 空文件不炸不挂 |
| T3 文件缺失 | PASS（fail-open，8 进程） | 同 | 没有 flags 文件也能正常启动 |
| T4 垃圾行（`--`/`--=`/二进制） | PASS（后续行仍生效） | 同 | 解析器对畸形输入健壮 |
| T5 同名双写 enable+disable | PASS：disable 侧可见、enable 侧不可见 | 同 | 实测印证 `feature_list.cc:449-452` |
| T6 行内注释 `X # 备注` | 观察值：条目**不进入**回显 | 同 | 证实 D59"整条失效"，非 v6 引入 |
| T7 子进程限定（D58 之后） | PASS：6 个子进程仍带 marker | PASS：5 个 | 浏览器进程限定不影响向子进程下发 |

SUMMARY：M155 上 **7/7 PASS**；`loader_edge_test2.py`（12 例既有语料，含 3000 条 feature 触发合并上限、
250 KiB `--js-flags` 触发字节预算）在 v6 二进制上 **11/11 PASS** → D58 的限定没有引入回归。
日志：`.bugreview/cycle3_verify.log`、`.bugreview/cycle3_verify2.log`。

**修复后的内存口径对照（D52 的量级证明）**：同一构建、同一时刻，
实例级筛选 K2 = **2512.85 MB / 57 进程**，而整机口径给出 2586.8 MB / 58 进程 ——
差的那一个进程不属于被测实例，却被算进了 KPI。

**PowerShell 类型陷阱（D66-③ 的独立复现）**：

```
$p=@(Get-Process -Id $PID); [math]::Round(...)+'|'+$p.Count   → rc=1 "无法将值 '|' 转换为 System.Double"
$ids=...; ('{0}|{1}' -f ..., $p.Count)                          → rc=0 "66.8|1"
```

**注入器升级路径（D67）Red→Green**：对 155 树 `BUILDCONFIG.gn` / `win/BUILD.gn` 的**副本**运行：
真实形状 → `already up to date (content match)`（证明修脚本不会引发 gn 重编）；
把正文改成旧变体 → `replaced`；再跑 → `up-to-date`。

**门禁**：`flag_stability.py`（A–F 全断言）PASS；`verify_sources.py` PASS；
D59 的负向对照（临时加行内注释）→ FAIL，恢复后 → PASS。

**产物状态**：加载器升到 v6 需要重编 `chrome.dll`，而 `gn gen --check` 之后 ninja 给出了
51,296 步的整树重编计划（步骤序列里出现大量 `RUST ... .rlib/.rustflags.json` 与
`third_party/**.obj` 重编）。**确切成因本轮未定论**——polly/AVX2 两块 GN 正文在
`use_polly=false` 下展开为空，理论上不该改变任何命令行；最可疑的是 gn 重算 Rust crate 元数据
导致下游全部目标重编。已列入待办（下次只改 GN 时先 `autoninja -n` 看计划步数再决定要不要 gen）。
本轮选择**接受这一次全量重编**，理由是"仓库正文 == 二进制源码"必须重新成立，
否则又是一次 D64 式的仓库与产物分叉。重建 + 打包 + 门禁链见 `.bugreview/cycle3_finalize.log`。

## 5. 全局效率评审（"稳定前提下的最优效率"）

0. **本轮最贵的一条成本结论（D74）：GN 里 config 的正文改动 = 全树重编，即使语义为空。**
   归因证据：21:22 那一轮 deploy 里唯一改变树内容的动作是把
   `build/config/compiler/BUILD.gn` 的 `config("polly")`/`config("emit-relocs")` 正文
   从"ldflags 版"换成"cflags 版"（`use_polly/use_bolt` 均为 false，两者展开都是空）；
   紧接着 `gn gen --check` 后 ninja 给出 **51,296 步**计划（约 3 小时）。
   中途因孤儿进程锁文件失败后重跑，仍是 34,310 步。
   → 可执行的纪律：**"把注释/写法改正确"这类零收益的 GN 改动，必须与真实改动同批落地**，
   绝不为它单开一次全树重编；本轮的选择是接受这次重编（因为同时要交付 loader v6 的完整验证链），
   并把该成本写进规范，避免以后重复支付。机制层面（为何空展开仍改变每条命令行）未细究，已列待办。

1. **不在测不出收益的地方宣称收益**。本轮把 `SkiaGraphite` 与 8 个 Tier A 候选全部留在噪声带内不采纳
   （`docs/tasks/m155-perf-features.md` §5.3），并据此否掉了上一轮自己给出的"采纳 PartitionAlloc"结论。
   同理，D58 的修复**不主张性能收益**：每进程一次 8 KB 读盘落在噪声下，修它的理由是去掉跨进程不一致面。
2. **改运行期语义 vs 改作者习惯**。D59 选择不给加载器加"行内注释"解析，而是静态拦住——
   多支持一种语法会让"文件里写的"与"内核看到的"再次分叉，代价大于收益。
3. **AVX2 基线附带 BMI/LZCNT/F16C 不是隐患**：在产 x86 里支持 AVX2 的处理器全部具备这些扩展，
   不存在"有 AVX2 无 BMI2"的机型，因此不会因这条产生非法指令。已记录推理，避免反复复审。
4. **Polly/BOLT 当前必须保持 false**（前置依赖未就绪：需自建含 Polly 的 clang；BOLT 只支持 ELF/Mach-O）。
   本轮修的是"开启时的正确性"（D63），而不是开启它——后者会在没有验证通道时给出假信号。
5. **验证脚本的算法成本**：`flag_stability` 系按"每条 × 每版本"发一次全树 `git grep`（53×3），
   而 `survival_check` 已有"一次扫描建全集"的做法。全局最优是把全集缓存复用给前者
   （159 次全树检索 → 3 次），但它只影响验证速度、不影响产物，排下轮；**不进 CI** 的结论不变。
6. **deploy 第 8 步与 `copy_essentials` 重复**：两处都写 `out/mcloud/mcloud_flags.txt`，
   导致第 8 步永远打印 `already in sync`。保留（无害）但已立档，防止被误读成"同步失败"。
7. **`win_scripts/setup.py`**：剩余 lint 告警大多来自这个"禁止运行"的遗留全量覆盖脚本。
   给它修 lint 是局部最优、全局负收益；正确处置是删除或加 refusal guard（同 ADR-003 对 Linux legacy 面），
   已列入待办。

## 6. 剩余风险（带定级与 owner）

| 风险 | 定级 | 说明 / owner |
|---|---|---|
| `kill_matching` 依赖命令行含临时 profile 名 | Low | 若用户把 `--user-data-dir` 设成与探针同名目录会被误杀（概率极低）；owner：项目方 |
| D49 仍未定论（V8 `_`/`-`） | Low | 需 `autoninja d8`；本轮已修 d49 脚本的证据采集缺陷（D65），实验本身待重跑 |
| 内存泄漏判据分辨率不足 | Medium | 泄漏探针噪声 ±8.9 MB，小于此的回归测不出；需要 malloc 计数或 WPA 侧证据；owner：项目方 |
| Polly/BOLT 路线未验证 | Low（当前关闭） | 启用前需自建 clang + 独立验证通道（规范 2.6 / 10.1） |
| 工具侧 SIM115（79 处 `open()` 未用 with） | Low | CPython 下不构成泄漏；列入"工具统一收口"待办 |

## 7. 待办（本周期新增）

- [ ] 把 `survival_check` 的声明全集缓存复用到 `flag_stability`，去掉 159 次全树 grep
- [ ] `win_scripts/setup.py` 删除或加 refusal guard（连同其 lint 噪声一起消失）
- [ ] D49：用修好的 `d49_experiment.py` 重跑，并 `autoninja d8` 做权威判定
- [ ] 泄漏判据升级（malloc 计数 / WPA），使 ±5 MB 级别的内存回归可测
- [ ] `.bugreview` 工具统一 `with open(...)`（SIM115 收口）
