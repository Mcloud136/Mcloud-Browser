# MCloud Browser 性能优化与构建配置技术规范

- **文档编号**：MCLOUD-SPEC-PERF-BUILD-001
- **版本**：1.0
- **编制日期**：2026-08-05
- **内核基线**：Chromium 151.0.7922.x（M151 稳定版，2026-07-28 发布）
- **状态**：发布执行稿

---

## 目录

1. 总则
2. 编译器与工具链规范
3. GN 构建参数规范
4. 运行时性能调优规范
5. 补丁管理规范
6. 多平台构建与发布规范
7. 性能验证与基准测试规范
8. 风险与兼容性管控规范
9. 版本管理与升级规范
10. 进阶优化路线图
11. M150 → M151 内核升级执行方案

---

# 1. 总则

## 1.1 规范目的

本规范是 MCloud Browser 项目在以下领域的统一技术标准：

- 编译器与工具链优化（SIMD、-O3、ThinLTO、PGO、BOLT、Polly）；
- GN 构建参数配置与参数治理；
- 运行时性能调优（启动参数、feature flag、默认配置）；
- 补丁管理与 Chromium 上游版本升级（rebase）；
- 多平台构建、打包与发布；
- 性能验证与风险管控。

项目内任何构建配置变更、优化项引入、补丁新增与内核升级，均须符合本规范；与本规范冲突的既有文件应在下一次变更时同步修订。

## 1.2 适用范围

| 范围 | 说明 |
|------|------|
| 适用仓库 | MCloud Browser（工作目录 `thorium`，GitHub: `Mcloud136/Mcloud-Browser`） |
| 适用平台 | **仅 Windows x64 为发布平台**（ADR-003）；其他平台构建文件留于仓库但不再维护与发布 |
| 适用人员 | 构建维护者、补丁作者、发布负责人 |
| 不适用 | Chromium 上游代码本身的行为约定；第三方扩展兼容性 |

## 1.3 术语定义

| 术语 | 定义 |
|------|------|
| GN / Ninja | Chromium 构建系统：GN 生成 `.ninja` 文件，Ninja 执行编译；`autoninja` 为 depot_tools 提供的 Ninja 封装 |
| args.gn | 构建目录（`out/mcloud`）下的 GN 参数文件，定义一次构建的全部编译配置 |
| -O2 / -O3 | Clang 优化等级。-O2 为 Chromium 上游默认（保守内联、保守向量化、不增大体积）；-O3 叠加更激进内联、循环展开与自动向量化，收益更高但二进制体积与编译时间增加 |
| ThinLTO | 轻量链接时优化（Link-Time Optimization），跨编译单元内联与去重，Chromium 官方构建默认启用 |
| PGO | Profile-Guided Optimization，依据运行时采样数据（`*.profdata`）指导编译器优化热点路径；`chrome_pgo_phase = 2` 表示使用 profdata 做最终优化构建 |
| profdata | LLVM 格式的 PGO 采样数据文件，须与目标 Chromium 大版本匹配 |
| BOLT | LLVM Binary Optimization and Layout Tool，后链接阶段依据 perf/instrumentation 数据重排二进制布局，主要收益为冷启动 |
| Polly | LLVM 多面体循环优化器，针对嵌套循环的仿射变换优化；Chromium 中需自建含 Polly 的 clang |
| ICF | Identical Code Folding，链接期合并完全相同的函数体以减小体积 |
| feature flag | Chromium `base::Feature` 机制的开关，经 `--enable-features` / `--disable-features` 或源码默认值控制 |
| rebase | 将本项目对 Chromium 的全部定制（覆盖文件 + 补丁）迁移到新上游版本的过程 |
| 覆盖文件 | 本仓库 `src/` 下用于整体替换 Chromium 源码树中同名文件的定制文件 |
| stock Chromium | 未经任何定制的上游原版 Chromium，作为性能对照基准 |

## 1.4 版本基线

| 项目 | 基线 | 依据 |
|------|------|------|
| 目标内核版本 | Chromium 151.0.7922.x（M151 稳定版） | 2026-07-28 发布；实际执行时以 `git ls-remote --tags` 查到的最新 151.0.7922.* tag 为准（可能已有后续安全补丁版） |
| 现状基线（升级前） | Chromium 150.0.7871.37（M150） | `docs/CHANGELOG.md`、`win_args_mcloud.gn` |
| 本规范撰写口径 | 以 M151 为基线撰写，涉及现状时注明 M150 | — |

## 1.5 硬件基线声明（设计决策）

- 【必须】正式发布构建以 **AVX2 + FMA3** 为唯一 x64 指令集基线。此为项目明确的设计目标而非兼容性约束：2013 年后的 CPU（Intel Haswell 起、AMD Excavator / Ryzen 起）几乎全部支持 AVX2；更早的设备不在本项目兼容目标范围内。
- 【必须】AVX2 基线不纳入风险清单、不提供低指令集降级构建。
- 【推荐】在安装器或首次启动引导中，通过 CPU 特性检测（参考仓库根目录 `check_simd.sh` 的检测逻辑）向用户明示最低 CPU 要求，对不满足条件的设备给出明确提示而非崩溃。
- 【必须】SSE4.2 及以下梯度构建（SSE2/SSE3/SSE4.1/SSE4.2）**废弃，不再保留**为发布或支持选项；相关历史文件（`other/SSE2/`~`other/SSE4.2/`、`setup.sh` 对应分支、相关文档描述）列入清理清单，见附录 A。

## 1.6 规范条目级别定义

| 级别 | 含义 |
|------|------|
| 【必须】 | 强制执行，违反视为配置错误，审查时须阻断 |
| 【推荐】 | 强烈建议执行，偏离时须在变更记录中说明理由 |
| 【可选】 | 视条件执行，不做强制 |
| 【待补充】 | 当前依据不足，条目同时列出所需数据或验证手段，补齐后升级为正式条款 |

## 1.7 设计优先级声明（性能优先）

- 【必须】性能为项目第一目标：二进制体积**不作为约束指标**，任何优化决策不得以牺牲运行时性能换取体积。
- 【必须】Windows 官方构建（`is_official_build = true`）必须保持全量 -O3（实现链路见 2.1），任何以体积为由降级优化等级的变更一律禁止。
- 【必须】二进制体积仅作观测指标记录（K7），不设上限、不作为发布阻断条件。

---

# 2. 编译器与工具链规范

**本章文件依据**：`src/build/config/compiler_opt.gni`、`src/build/config/compiler/BUILD.gn`、`src/build/config/win/BUILD.gn`、`src/tools/clang/scripts/build.py`、`win_args_mcloud.gn`、`args.gn`、`infra/build_polly.sh`。

## 2.1 优化等级（-O2 / -O3）

### 2.1.1 语义约定

| 等级 | 语义 | 适用 |
|------|------|------|
| -O2 | 上游默认，保守内联与向量化，体积友好 | Debug 构建、对照基准构建 |
| -O3 | 激进内联（更高阈值）、循环展开、激进自动向量化 | 正式发布构建 |

### 2.1.2 条款

- 【必须】发布构建（`is_official_build = true`）使用 -O3 等级优化，通过 `is_full_optimization_build = true` 声明（定义于 `src/build/config/compiler_opt.gni` 第 16 行）。
- 【必须】Debug 构建（`is_debug = true`）禁用全部进阶优化开关；`compiler_opt.gni` 第 109-113 行已有 assert 强制校验，不得移除。
- 【必须】Windows 官方构建必须使用 -O3，生效链路由以下两处共同保证，升级 rebase 后必须逐一核对未被上游回退：① `optimize` config（`src/build/config/compiler/BUILD.gn` 第 3092-3100 行）对 `is_win` 显式叠加 `/O2` + `/clang:-O3` + `-Xclang -O3`（clang-cl 语义差异已修正）；② `no_chromium_code` config（同文件第 2515-2550 行）对第三方代码同样追加 `-Xclang -O3`；另保留 `-mllvm -aggressive-ext-opt` 与 `-mllvm -enable-gvn-hoist` 两项 LLVM 调优开关（BUILD.gn 第 2888-2927 行区域）。
- 【必须】对照基准构建（stock Chromium）使用上游默认 -O2，以隔离 -O3 的真实收益；禁止用 -O3 构建作为"原版对照"。
- 【推荐】-O3 带来的体积膨胀无需刻意抵消（见 1.7 性能优先原则）；ICF、BOLT、`enable_stripping`、`use_text_section_splitting` 因本身对性能有利或中性（改善 i-cache、启动速度）而保留，不得以体积为由关闭 -O3 或相关优化。
- 【待补充】本项目 -O3 相对 -O2 的实测收益数据（体积代价按 1.7 不作约束）。需要：同一 M 版本分别以两档优化构建，执行第 7 章 K1-K6 性能基准对比。

## 2.2 SIMD 指令集目标

### 2.2.1 能力层级（历史能力描述）

构建系统（`compiler_opt.gni`）保留完整的 SIMD 开关层级，仅作能力描述，不代表发布支持：

| 开关 | 指令集 | 代表 CPU | 发布状态 |
|------|--------|----------|----------|
| `use_sse2` | SSE2 | Pentium 4 / Athlon 64 | 废弃 |
| `use_sse3` | SSE3 | Prescott / 二代 Opteron | 废弃 |
| `use_sse41` | SSE4.1 | Penryn / Jaguar | 废弃 |
| `use_sse42` | SSE4.2（x86-64-v2） | Nehalem / Bulldozer | 废弃 |
| `use_avx` | AVX（128 位） | Sandy Bridge / Bulldozer | 废弃（不单独发布） |
| `use_avx2` | AVX2（256 位，x86-64-v3） | Haswell / Excavator / Zen | **正式发布基线** |
| `use_avx512` | AVX-512 公共子集 | Skylake-X / Zen 4 | 实验（见 2.2.3） |
| `use_fma` | FMA3 | Haswell / Piledriver | 随 AVX2 基线启用 |

### 2.2.2 条款

- 【必须】发布构建设置 `use_avx2 = true` 且 `use_fma = true`（`win_args_mcloud.gn` 第 15-16 行口径）。
- 【必须】保留 `compiler_opt.gni` 中的全部参数组合校验（assert 与 warning，第 109-172 行），包括：AVX 系列必须 x64、FMA 不得用于 x86/arm、`use_avx2` 未配 `use_fma` 告警等。禁止为"简化配置"删除这些校验。
- 【必须】AVX2 基线属设计决策：不为旧 CPU 提供降级构建，不在文档中将其表述为兼容性风险。
- 【必须】废弃 SSE4.2 及以下构建：规范生效后，新发布、新文档不得再引用 SSE2/SSE3/SSE4 构建选项；存量文件清理见附录 A。
- 【推荐】`use_sse3`/`use_sse41`/`use_sse42` 等低档开关在 args.gn 中显式置 false（如 `win_args_mcloud.gn` 第 11-14 行），避免与 AVX2 叠加产生语义歧义。

### 2.2.3 AVX-512 实验分支

- 【可选】保留 `--avx512` 构建能力用于实验，但不得作为正式发布渠道；AVX-512 在不同厂商实现间宽度/频率行为差异大，且部分 Intel 平台存在降频问题。
- 【待补充】AVX-512 构建在本项目的收益与热节流数据。需要：在 Intel 与 AMD 各一台支持机型上跑第 7 章基准并监控频率。

## 2.3 ThinLTO

- 【必须】发布构建启用 `use_thin_lto = true` 与 `thin_lto_enable_optimizations = true`（与上游官方构建一致）。
- 【必须】`is_component_build = false`（静态链接）以保障 LTO 覆盖面；component build 仅限 Debug。
- 【推荐】`thin_lto_enable_cache` 在本地反复增量构建时开启以缩短编译时间，但发布构建的正式产物须在干净缓存下生成，避免缓存引入不可复现差异。
- 【必须】ThinLTO 构建内存需求高（链接阶段可达数十 GB），构建机内存低于 16 GB 时不得开启 PGO+BOLT 叠加组合。

## 2.4 PGO

- 【必须】发布构建设置 `chrome_pgo_phase = 2` 并提供 `pgo_data_path`。
- 【必须】profdata 文件版本与 Chromium 大版本严格匹配（如 M151 对应 `chrome-win64-*.profdata` 的 7922 系列）；内核升级时同步更新，检查清单见第 9 章。
- 【必须】profdata 路径使用构建环境通用形式（相对路径或环境变量展开），**禁止硬编码个人目录**；现有 `win_args_mcloud.gn` 的 `D:/wxmuma/...` 与 `win_args.gn` 的 `/home/alex/...` 属违规现状，列入整改清单（附录 A）。
- 【推荐】中期以自采 profdata（真实用户场景：启动、多标签、B 站/YouTube 播放）替代上游通用 profdata，流程见 10.2。
- 【必须】`v8_enable_builtins_optimization = true`（V8 builtins 的 PGO）在所有平台发布构建中保持启用——本项目在 Windows/macOS 上强制打开上游默认关闭的此项，属既有设计（`docs/ABOUT_GN_ARGS.md`），升级时不得被上游默认值回退。
- 【待补充】自采 profdata 相对上游 profdata 的收益对比数据。需要：两套 profdata 分别构建后执行第 7 章 K1、K3、K4 基准。

## 2.5 BOLT

- 【重要事实（2026-08-05 核查）】`config("emit-relocs")` 此前在构建树中**从未被引用**，`use_bolt` 属无效开关；Phase 2 已在 `src/build/config/BUILDCONFIG.gn` 完成接线（executable + shared_library，排除 android/apple），开关自此真实生效。
- 【必须】启用 BOLT 时保持 `use_bolt = true` 与 emit-relocs 接线（`src/build/config/compiler/BUILD.gn` 第 3244-3253 行，已含 Windows 分支 `-mllvm:--emit-relocs`）。
- 【必须】BOLT 优化须基于真实负载采集的 profile 执行；无 profile 的 BOLT 构建禁止发布。后链接执行流程未落地前（见 10.1），`use_bolt` 必须保持 `false`（emit-relocs 只会徒增体积）——当前 `win_args_mcloud.gn` 已按此设置。
- 【必须】BOLT 与 Debug 构建互斥（`compiler_opt.gni` 第 112 行 assert 保留）。
- 【推荐】Windows 构建补齐 BOLT 后链接流程（instrument → 跑负载 → `llvm-bolt` 优化），参照 `src/tools/clang/scripts/build.py` 第 1651 行起的实现范式；落地方案见 10.1。
- 【待补充】BOLT 在本项目的实测冷启动收益；就绪前不得在对外文档宣称 BOLT 收益。
- 【重要事实（2026-08-05 核查）】Chromium 内置工具链（third_party/llvm-build）**不含 `llvm-bolt.exe` 与 `llvm-profdata.exe`**；BOLT/自采 PGO 落地前须先准备独立 LLVM 工具链（随 LLVM release 安装或随自建 clang 一并构建），此项已列为 10.1/10.2 的前置依赖。

## 2.6 Polly

- 【重要事实（2026-08-05 核查）】① `config("polly")` 此前从未被引用，`use_polly` 属无效开关，Phase 2 已在 BUILDCONFIG.gn 完成接线；② 已验证 Chromium 内置 clang（23.0.0git）的 `-mllvm` 选项列表**不含 Polly**——即接线后若置 true 会在链接期报未知参数错误。故 Polly 启用前置条件为自建含 Polly 的 clang。
- 【必须】启用 Polly 前须使用含 Polly 的自建 clang（`infra/build_polly.sh`），并设置 `clang_use_chrome_plugins = false`（自定义 clang 与 Chromium 插件不兼容，`docs/ABOUT_GN_ARGS.md` 第 111 行）。前置条件未就绪时 `use_polly` 必须为 `false`。
- 【必须】Polly 与 Debug 构建互斥（`compiler_opt.gni` 第 111 行 assert 保留）。
- 【推荐】Polly 显著增加编译时间且收益集中在循环密集代码；自建 clang 就绪后启用，每次内核升级后须验证自建 clang 与新源码的兼容性。
- 【待补充】Polly 在本项目的实测收益数据（当前无任何实测依据，对外文档不得宣称）。需要：开/关 Polly 双构建 + 第 7 章 K4（JS/WASM）与 K6（视频解码）基准对比。

## 2.7 链接器与体积优化

- 【必须】使用 lld（`use_lld = true`）。
- 【必须】Windows 链接保持 `/OPT:REF` + `/OPT:ICF` + `/OPT:NOLLDTAILMERGE`（`src/build/config/win/BUILD.gn` 第 183-194 行，静态 Release 构建自动生效）。**纠正性说明**：`win_args_mcloud.gn` 中 `use_icf = false` 的注释"ICF not supported by lld-link on Windows"与事实不符——lld-link 支持 ICF 且本项目已通过 `/OPT:ICF` 启用；该 GN 开关仅控制 GN 层的追加逻辑。args.gn 模板中须更正此注释（附录 A）。
- 【必须】Linux 构建保持 `use_icf = true` 与 `use_text_section_splitting = true`（`args.gn` 第 34、80 行现状）。
- 【必须】发布构建保持 `symbol_level = 0`、`v8_symbol_level = 0`、`blink_symbol_level = 0`、`exclude_unwind_tables = true`、`enable_stripping = true`。
- 【推荐】崩溃排查依赖符号时，单独构建 symbol_level=1 的诊断包，不发布给用户。

## 2.8 编译器与工具链版本

- 【必须】使用 Chromium 内置 clang（depot_tools 自动管理版本），禁止混用系统 clang。
- 【必须】Polly/BOLT 等需要自定义 LLVM 组件时，统一通过 `src/tools/clang/scripts/build.py` 脚本构建并记录 LLVM 版本到升级报告。
- 【推荐】Windows 工具链保持 `DEPOT_TOOLS_WIN_TOOLCHAIN=0` + 本机 VS Build Tools 的现状（`CLAUDE.md`），工具链版本变更须同步更新构建文档。

---

# 3. GN 构建参数规范

**本章文件依据**：`win_args_mcloud.gn`、`win_args.gn`、`args.gn`、`src/build/config/compiler_opt.gni`、`docs/ABOUT_GN_ARGS.md`、`infra/args.list`。

## 3.1 参数分类

### 3.1.1 必选参数（所有发布构建）

| 分组 | 参数 | 要求值 | 说明 |
|------|------|--------|------|
| 目标 | `target_os` / `target_cpu` | 按平台 | Windows x64 为 `"win"`/`"x64"` |
| 构建类型 | `is_official_build` | `true` | 触发上游全部官方优化 |
| 构建类型 | `is_debug` / `dcheck_always_on` | `false` | 去除调试开销 |
| SIMD | `use_avx2` / `use_fma` | `true` | 见 2.2；低档开关显式 `false` |
| 优化栈 | `is_full_optimization_build` | `true` | -O3 总开关 |
| 优化栈 | `use_thin_lto` + `thin_lto_enable_optimizations` | `true` | ThinLTO |
| 优化栈 | `chrome_pgo_phase` + `pgo_data_path` | `2` / 匹配版本 | PGO |
| 优化栈 | `use_polly` / `use_bolt` | `true` | 见 2.5/2.6 的组合限制 |
| 符号 | `symbol_level` / `v8_symbol_level` / `blink_symbol_level` | `0` | 体积与剥离 |
| 符号 | `exclude_unwind_tables` | `true` | 体积 |
| V8 | `v8_enable_maglev` / `v8_enable_turbofan` / `v8_enable_fast_torque` / `v8_enable_builtins_optimization` / `v8_enable_wasm_simd256_revec` / `use_v8_context_snapshot` | `true` | V8 优化组，升级时不得被上游默认值回退 |
| 编译 | `is_clang` / `use_lld` | `true` | 工具链 |
| 编译 | `is_component_build` | `false` | 保障 LTO |
| 稳定性 | `disable_fieldtrial_testing_config` | `true` | 关闭 field trial，保障可复现（`docs/ABOUT_GN_ARGS.md` 第 53 行） |
| WebUI | `optimize_webui` | `true` | WebUI 资源打包压缩 |
| 安全 | `init_stack_vars_zero` | `true` | 栈变量零初始化 |

### 3.1.2 平台差异可选参数

| 参数 | Windows | Linux | macOS | 说明 |
|------|---------|-------|-------|------|
| `win_enable_cfg_guards` / `is_cfi` | `true`（CFG） | `true`（CFI） | 按上游 | 控制流完整性，安全项不可裁剪 |
| `use_vaapi` | 不适用 | `true` | 不适用 | Linux 硬解 |
| `enable_vulkan` | `false`（走 D3D12） | 按平台 | 按平台 | Windows 现状决策（`win_args_mcloud.gn` 第 104 行） |
| `is_component_ffmpeg` | `false`（静态，利于 LTO） | `true`（允许用户替换 libffmpeg.so） | `false`（否则安装包构建失败） | 三平台取值不同属有意设计 |
| `use_webaudio_pffft` | 按版本有效性 | 按版本有效性 | 关闭（系统 FFT 更快） | M150 已移除该参数，升级时按第 9 章清单核对 |
| `enable_rlz` | 统一口径 | 统一口径 | 统一口径 | 见 3.4 整改项 |
| Widevine 组（`enable_widevine` 等） | 视 CDM 可得性 | `true`（Linux 现状） | 视 CDM | 无 CDM 时整组置 false 并注释原因 |

## 3.2 标准 args.gn 模板骨架

- 【必须】每个平台维护一个受管的 args.gn 模板文件，命名规则：`{平台}_args_{变体}.gn`（如 `win_args_mcloud.gn`）；构建时复制为 `out/mcloud/args.gn`。
- 【必须】模板按以下分区组织并以注释分隔：SIMD → 构建目标 → 构建类型 → 编译器优化 → PGO → V8 → 渲染/UI → 平台特定 → 媒体/FFmpeg → DRM → WebRTC → GPU → 资源/报告。
- 【必须】每个非默认取值参数须附单行注释说明理由；优化类参数注明预期影响面（启动/内存/体积/安全）。
- 【推荐】Debug 构建单独维护 `{平台}_args_debug.gn`，仅保留 `is_debug = true` 与最小必要参数，禁止在 Debug 模板中出现进阶优化开关。

### 3.2.1 Windows x64 Release 模板要点（基于 `win_args_mcloud.gn`）

保留现有全部分区；须整改项见附录 A（profdata 路径、use_icf 注释、RLZ 口径）。

### 3.2.2 Linux x64 Release 模板要点（基于 `args.gn`）

在现有 `args.gn` 基础上：将 SIMD 从 SSE4.2 基线升级为 AVX2+FMA3（与 1.5 基线声明一致）；启用 `use_polly`/`use_bolt`（当前被注释）前须先按 10.1/2.6 验证流程补齐 profile 采集。

### 3.2.3 ARM / Raspberry Pi 模板要点

沿用 `arm/raspi/raspi_args.gn` 与 `arm/config/compiler/BUILD.gn` 的 `is_raspi` 参数；SIMD 章节不适用于 ARM，仅保留通用必选参数组。

## 3.3 参数命名与冲突校验规则

- 【必须】新增自定义 GN 参数须在 `compiler_opt.gni`（或对应 .gni）中用 `declare_args()` 声明默认值，并附注释说明；禁止仅在 args.gn 中出现无声明来源的参数。
- 【必须】存在依赖/互斥关系的参数组合须编写 assert 校验（模式参照 `compiler_opt.gni` 第 109-172 行）：已知必守规则包括——AVX 系必须配 x64；`use_avx2` 应配 `use_fma`；Polly/BOLT/full-optimization 与 Debug 互斥；macOS 禁 `is_component_ffmpeg = true`。
- 【必须】每次修改 args.gn 后执行 `gn gen out/mcloud --check`，未通过校验不得进入编译。
- 【推荐】每次内核升级后执行 `gn args out/mcloud --list >> ARGS.list` 与上一版本 diff，识别被移除/更名的参数（先例：M150 移除 `use_webaudio_pffft`，见 `win_args_mcloud.gn` 第 73 行注释）。

## 3.4 一致性整改项（针对现状违规）

以下现状问题列入整改清单（附录 A），整改完成前不得发布新版本：

1. 【必须】`enable_rlz` 口径统一：`win_args_mcloud.gn` 第 63 行为 `true`（注释称"for search engine attribution"），而 `CLAUDE.md` 关键参数表写的是 `enable_rlz = false # 禁用 Google 追踪`。两处必须二选一并同步全部文档；涉及隐私语义，决策须记录为 ADR（`docs/decisions/`）。
2. 【必须】`pgo_data_path` 去除个人目录硬编码（`win_args_mcloud.gn` 第 48 行、`win_args.gn` 第 86 行）。
3. 【已确认，无需整改】Google API 密钥（`win_args_mcloud.gn` 第 114-116 行、`CLAUDE.md`、`launch_browser.bat`）为 Chromium 衍生生态公开共享的通用密钥，无滥用风险，维持入库现状；本项经项目方确认移出整改清单。
4. 【必须】`use_icf` 注释更正（见 2.7）。
5. 【必须】统一对外口径的优化项数量（README 称 51 项、CLAUDE.md 称 60+），以 `mcloud_flags.txt` 实际条目数为准并在文档中引用该文件。

---

# 4. 运行时性能调优规范

**本章文件依据**：`mcloud_flags.txt`、`src/chrome/browser/mcloud_flag_entries.h`、`src/chrome/browser/about_flags.cc`、`src/media/base/media_switches.cc`、`src/chrome/browser/net/default_dns_over_https_config_source.cc`、`win_scripts/copy_essentials.py`、`docs/superpowers/plans/2026-06-19-performance-optimization.md`。

## 4.1 标志清单管理（mcloud_flags.txt）

### 4.1.1 生效链路（【必须】整改项）

审查发现：`mcloud_flags.txt` 在当前仓库内无任何 `.gn`/`.cc`/`.py` 引用，实施计划中仅将其 `cp` 到 Chromium 源码树根目录，而 Chromium 本身不读取该文件——即约 50 项运行时优化存在未生效风险，与 README"参数已内置"的宣称不符。

- 【必须】在 M151 升级完成前，核实实际构建产物中该清单的生效方式（检查 chromium 树是否有额外补丁/机制）。
- 【必须】若确认未生效，选择以下任一正规方式固化，并在升级报告中记录所选方案：
  - 方案 A（推荐）：源码级默认值——参照 `media_switches.cc`（D3D12 默认启用）的既有做法，将各 feature 的默认 state 改为 ENABLED；
  - 方案 B：内置启动参数——在浏览器主进程初始化处读取随包分发的标志文件并追加到命令行；
  - 方案 C：全部转为 `mcloud_flag_entries.h` 的 chrome://flags 条目并设默认启用。
- 【必须】生效验证方法：构建后通过 `chrome://version` 命令行、`chrome://flags`、`base::FeatureList::IsEnabled` 日志抽查，至少覆盖启动、内存、媒体三组各 2 项。

### 4.1.2 清单组织与注释

- 【必须】标志按功能域分组（冷启动/视频/渲染/内存/网络/GPU/媒体/线程等，维持 `mcloud_flags.txt` 现有分区），每条目附单行注释说明预期收益。
- 【必须】带参数 feature（如 `InitialWebUI:without_spellcheck/without_translate/high_stream_priority`、`--js-flags`）须单独标注参数含义与修改风险。
- 【推荐】为清单建立机器可读索引（如 JSON/CSV：feature 名、分组、引入版本、依据、验证状态），供第 9 章升级检查脚本消费。

## 4.2 feature flag 增删审核流程

- 【必须】新增 feature 须提交：上游出处（源码位置/commit）、预期收益描述、影响面（启动/内存/功耗/流量/稳定性）、初步验证结果；未经登记直接合入属违规。
- 【必须】以下高风险类别默认不启用，启用须额外提供实测证据：自旋锁类（如 `BaseLockTrySpin`）、取消后台节流类（如 `--disable-background-media-suspend`，影响功耗）、预测预取类（如 `SpeculationRules`，影响流量）。
- 【必须】删除/失效 feature 须记录原因；上游已默认启用的 feature 应从清单移除（避免重复声明掩盖上游变更）。
- 【必须】每次内核升级后执行 feature 有效性检查（脚本或人工 grep 源码确认 feature 名仍存在），先例：M150 移除 `use_webaudio_pffft`（`win_args_mcloud.gn` 第 73 行）；代码审查已移除 4 项不当 flag（`docs/superpowers/specs/2026-06-20-code-review-fixes.md`）。
- 【待补充】清单中各 feature 的单独基准验证数据。需要：按 4.4 基准方法逐项开关对比，优先覆盖高风险类别与内存组 11 项。

## 4.3 默认配置基线（源码级默认值修改登记）

现有源码级默认值修改（均经 `copy_essentials.py` 复制生效）：

| 修改 | 文件 | 说明 |
|------|------|------|
| D3D12 视频解码默认启用 | `src/media/base/media_switches.cc` | 已知问题：不可用时回退 D3D11；核显绿屏待修复（CHANGELOG M150 已知限制） |
| DoH 模式改为 kAutomatic | `src/chrome/browser/net/default_dns_over_https_config_source.cc` | 修复 HTTP 断流（CHANGELOG M150） |
| 后台模式默认关闭 | `src/chrome/browser/background/extensions/background_mode_manager.cc` | — |

- 【必须】任何新的源码级默认值修改须同步登记到上表（维护于升级报告与本规范），并进入 `copy_essentials.py` 的文件清单。
- 【必须】登记条目须含：修改目的、已知副作用、每次升级时的合并注意事项。
- 【推荐】能用 feature flag 实现的默认值变更优先用 flag，减少升级时的手工合并面。

## 4.4 V8 运行时参数

- 【必须】保持 `--js-flags="--invocation-count-for-maglev=500 --invocation-count-for-turbofan=1500"`（降低 JIT 升级阈值）的现状，但每次内核升级须核对这两个 V8 flag 是否仍存在。
- 【待补充】该阈值调整对启动（正向）与长时运行内存/CPU（潜在负向）的实测数据。需要：K1 启动基准 + 30 分钟多标签驻留场景采样。

---

# 5. 补丁管理规范

**本章文件依据**：`other/` 目录全部 `.patch` 文件、`setup.sh`（patchThor 流程，第 92-203 行）、`docs/REBASING.md`。

## 5.1 命名与目录组织

- 【必须】补丁文件命名：`{功能名}.patch`（小写加下划线/连字符，如 `ftp-support-mcloud.patch`、`fix_dangling_pointer_tooltip.patch`）。
- 【必须】补丁统一存放 `other/` 目录；ffmpeg 相关补丁在应用时复制到 `${CR_SRC_DIR}/third_party/ffmpeg/` 后再 `git apply`（维持现状流程）。
- 【推荐】崩溃修复类补丁以 `fix_` 前缀命名，功能类以功能名命名，便于分类检索。

## 5.2 应用顺序与执行要求

- 【必须】补丁应用顺序以 `setup.sh` 中 `patchThor` 函数的既有顺序为准（ffmpeg 系 → policy templates → FTP → GPC → 2024 UI → 下载栏 → mini_installer → 其余杂项），新增补丁须插入合适位置而非随意追加。
- 【必须】`setup.sh` 使用 `git apply --reject` 允许部分失败并生成 `.rej` 文件；构建前【必须】检查源码树无残留 `.rej`/`.orig` 文件（建议加入 setup 脚本末尾的自动检查），防止补丁静默失败进入构建。
- 【必须】Windows 流程（`copy_essentials.py`）与 Linux 流程（`setup.sh`）覆盖的补丁范围须保持一致性核对，避免平台间行为差异。

## 5.3 补丁清单登记制度

- 【必须】维护补丁登记表（建议 `other/PATCHES_INDEX.md`）：补丁名、目的、影响文件、引入版本、预计可移除条件。
- 【必须】上游已修复的补丁及时移除；执行先例：`setup.sh` 中 M144 移除 8 项、M145 移除 1 项、M149 移除 1 项的注释记录（第 109-127 行）。每次升级后更新登记表。
- 【推荐】能用覆盖文件（`src/` 目录整体替换）解决的定制优先用覆盖文件，补丁仅用于无法整体替换的第三方目录（如 ffmpeg、angle）。

## 5.4 rebase 策略

- 【必须】rebase 工作流遵循 `docs/REBASING.md` 与 `trunk.sh`/`version.sh` 脚本：先恢复纯净上游 → 切换目标版本 → 重放覆盖文件与补丁 → 人工合并冲突。
- 【必须】每次 rebase 产出升级报告（格式参照 `docs/superpowers/specs/2026-06-19-m149-to-m150-upgrade-report.md`），归档至 `docs/dev-logs/`。
- 【推荐】冲突合并使用三方对比工具（REBASING.md 推荐 Meld），逐文件对照上游 diff 与本地定制。

---

# 6. 多平台构建与发布规范

**本章文件依据**：`build.sh`、`build_win.sh`、`build_mac.sh`、`build_android.sh`、`win_scripts/`、`.github/workflows/release.yml`、`infra/`（APPIMAGE/Flatpak/portable 等）。

## 6.1 构建脚本标准

- 【必须】各平台构建脚本遵循统一模式：`CR_DIR` 环境变量支持（默认 `$HOME/chromium/src`）、`--help` 支持、`NINJA_SUMMARIZE_BUILD=1` 与统一 `NINJA_STATUS` 格式、错误即终止（`die` 模式）。
- 【必须】构建目标统一为 `mcloud_all`（浏览器全家桶）+ 平台安装包目标：

| 平台 | 脚本 | 安装包目标 |
|------|------|-----------|
| Linux | `build.sh` | `chrome/installer/linux:stable_deb` + `stable_rpm` |
| Windows | `build_win.sh` / `win_scripts/build_win.py` | `mcloud_installer`（mini_installer） |
| macOS | `build_mac.sh` + `create_dmg.sh` | `chrome/installer/mac` |
| Android | `build_android.sh` + `arm/android/` args | APK |

- 【必须】构建目录名固定 `out/mcloud`（`trunk.sh`、`build.sh` 硬依赖此名称，见 docs/BUILDING.md 说明）。
- 【推荐】编译并发度由调用参数传入（`./build.sh 8`），不硬编码。

## 6.2 打包格式矩阵

**发布范围（ADR-003，2026-08-06）：仅发布 Windows x64 平台，其他平台不再发布。**

| 平台 | 格式 | 状态 | 依据 |
|------|------|------|------|
| Windows | mini_installer | **唯一发布渠道** | `build_win.sh`、`other/mini_installer.patch` |
| Linux | .deb / .rpm / AppImage / Flatpak / portable | 遗留（不发布） | `build.sh`、`infra/` |
| macOS | .dmg | 遗留（不发布） | `create_dmg.sh` |
| Android | APK | 遗留（不发布） | `arm/android/` |

- 【必须】发布产物仅 Windows mini_installer；命名含版本号与平台（如 `mcloud_151.0.7922.x_win64_mini_installer.exe`）。
- 【可选】其他平台的构建脚本/配置保留在仓库供参考，但升级流程（第 9/11 章）不再为其做兼容性验证；如未来恢复某平台发布，须新开 ADR 并重新纳入本规范验证范围。

## 6.3 CI/CD 流程要求

- 【必须】保持现有发布流程：本地编译 → 打 `v{版本}` tag → 推送触发 `.github/workflows/release.yml` 自动上传安装包到 GitHub Release（M150 起已移除 CI 编译，见 CHANGELOG）。
- 【推荐】release.yml 中增加产物校验和生成与上传。
- 【待补充】可复现构建与代码签名流程。需要：① 构建环境固定化记录（clang/VS 版本、依赖 snapshot）；② Windows Authenticode 签名方案与成本评估。补齐前发布产物无签名状态须在发布说明中明示。

---

# 7. 性能验证与基准测试规范

**本章文件依据**：当前仓库**无任何基准测试脚本与数据**，本章为新建标准；README 中的性能宣称（冷启动 -20%、内存 -30% 等）无测量来源，须按本章补齐。

## 7.1 关键性能指标（KPI）

| 编号 | 指标 | 定义 | 测量方法 |
|------|------|------|----------|
| K1 | 冷启动时间 | 进程启动到首屏可交互 | 全新用户数据目录，关机后冷态，重复 5 次取中位数；可用 `chrome://tracing` startup 轨道或进程计时 |
| K2 | 内存峰值 | 固定标签集（如 50 标签）驻留后的总工作集 | 系统任务管理器/进程 API 采样工作集之和 |
| K3 | 页面加载 | 固定站点集的 FCP/LCP/Speed Index | Lighthouse CLI，每站点 3 次取中位数 |
| K4 | JS/WASM 性能 | Speedometer 3.1 与 JetStream 3 得分 | 官方套件，默认参数 |
| K5 | 滚动/渲染流畅度 | 固定页面的掉帧率 | DevTools Performance / `chrome://gpu` 配合固定滚动脚本 |
| K6 | 视频解码 CPU | 4K HEVC/AV1 视频播放时 CPU 占用 | 固定视频样本，硬解/软解分别采样 60 秒均值 |
| K7 | 二进制体积 | chrome 主产物与安装包体积 | 构建产物直接测量；**仅观测记录，不作约束**（见 1.7） |

## 7.2 测试方法与环境

- 【必须】对照基准：同版本 stock Chromium（同 args.gn 但去除全部定制，或官方 Chrome 同版本），用于隔离各优化项收益。
- 【必须】测试环境固定并记录：CPU 型号/频率策略（高性能电源模式）、内存、OS 版本、GPU 驱动版本、无扩展、清空缓存（K1 需冷态）。
- 【必须】每项指标至少 5 次采样取中位数；报告须附原始数据或脚本输出。
- 【推荐】基准脚本统一放置 `benchmark/` 目录（新建），随仓库版本管理。

## 7.3 数据采集与归档

- 【必须】每次正式发布前执行 K1-K7 全套，结果连同环境信息归档至 `docs/dev-logs/{版本}-benchmark.md`。
- 【必须】README/CHANGELOG 中的性能宣称数字必须可追溯到上述归档；无法追溯的数字不得写入对外文档。
- 【推荐】内核升级前后各跑一次全套基准，升级报告中给出回归对比表。

## 7.4 基线缺失声明

- 【待补充】**本章全部 KPI 当前无基线数据**（仓库内无任何基准脚本与历史数据，README 数字无来源）。需要：先建立 M150 现状基线（K1-K7 全套），作为 M151 升级与后续一切优化的对比起点；此项优先级最高，阻塞第 10 章多数进阶项的收益验证。

---

# 8. 风险与兼容性管控规范

**本章文件依据**：`docs/FAQ.md`（Widevine/VMP 限制）、`docs/CHANGELOG.md`（M150 已知限制）、`win_args_mcloud.gn`、`docs/ABOUT_GN_ARGS.md`。

## 8.1 优化项三维评估标准

每项优化引入/保留须按下表评估并记录结论：

| 维度 | 评估问题 | 红线 |
|------|---------|------|
| 稳定性 | 是否引入崩溃/回归路径？上游是否已有该 feature 的稳定性记录？ | 无验证数据不得进入发布清单 |
| 安全性 | 是否削弱安全机制？ | 安全项只增不减（见 8.2） |
| 可维护性 | 升级 rebase 成本？是否可用 flag 替代源码修改？ | 源码级修改须登记（见 4.3） |

## 8.2 安全基线（不可裁剪）

- 【必须】以下安全项在任何发布构建中不得关闭：`win_enable_cfg_guards`（Windows CFG）、`is_cfi`（Linux CFI）、`init_stack_vars_zero`、沙箱相关默认配置。
- 【必须】关闭 `disable_fieldtrial_testing_config`（即重新启用 field trial）的决策须单独评审——现状关闭是为稳定性/隐私/可复现（`docs/ABOUT_GN_ARGS.md` 第 53 行），重新启用会丧失上游远程修复能力以外的可复现性优势。
- 【必须】Widevine/DRM 状态须在发布说明中明示：Windows 当前无 CDM（`enable_widevine = false`），Linux 为软件安全级 L3（FAQ 第 2 条已说明 VMP 签名成本限制）。

## 8.3 风险清单（当前有效项）

| 风险项 | 影响 | 管控 |
|--------|------|------|
| 运行时 feature 清单未验证（含未生效风险） | 性能宣称失实/潜在回归 | 4.1/4.2 流程 + 第 7 章基准 |
| 源码级默认值修改（D3D12 等） | 升级合并成本、已知绿屏问题 | 4.3 登记 + CHANGELOG 跟踪 |
| 关闭 field trial | 无法接收上游远程配置修复 | 重大问题时允许手工干预路径，FAQ 已确认产品策略 |
| 大量补丁 | rebase 成本（FAQ：每次 8+ 小时） | 第 5 章登记与及时移除 |
| AVX2 基线 | （设计决策，非风险） | 仅按 1.5 向用户明示 CPU 要求 |

## 8.4 回退方案要求

- 【必须】每项运行时优化须有单项回退路径：feature 从清单移除或源码默认值还原，不得存在"只能整体回退"的优化项。
- 【必须】编译级优化（-O3/Polly/BOLT/PGO）的回退即修改对应 args.gn 开关重新构建；每个开关须可独立关闭而不破坏其余配置（`compiler_opt.gni` 的 assert 已保障组合合法性）。
- 【必须】内核升级失败的回退方案见 11.5（git 基线分支/tag）。
- 【推荐】为发布后的紧急问题准备"用户侧应急清单"：通过 `chrome://flags` 关闭单项、命令行 `--disable-features` 覆盖、干净用户配置启动。

---

# 9. 版本管理与升级规范

**本章文件依据**：`trunk.sh`、`version.sh`、`setup.sh`、`win_scripts/copy_essentials.py`、`docs/REBASING.md`、`docs/superpowers/specs/2026-06-19-m149-to-m150-upgrade-report.md`。

## 9.1 升级策略

- 【必须】跟踪上游稳定版：以 Chrome 稳定频道的大版本发布为升级触发点，原则上每个大版本升级一次（项目历史节奏：M130 → M149 → M150 → M151）。
- 【必须】目标版本选择稳定分支的最新补丁 tag（如 151.0.7922.* 中的最新者），同时获得安全修复。
- 【推荐】重大安全公告（如 CVE）发布后 7 天内评估是否需要提前升级或回合补丁。

## 9.2 内核升级检查清单（每次升级逐项执行并打勾记录）

| 序号 | 检查项 | 工具/方法 | 级别 |
|------|--------|-----------|------|
| 1 | 升级前打 git 基线分支/tag（回退点） | `git tag baseline-M{旧版本}` | 【必须】 |
| 2 | 同步主线并恢复纯净上游 | `trunk.sh` | 【必须】 |
| 3 | checkout 目标 tag + gclient sync + runhooks | `version.sh` + 手工 | 【必须】 |
| 4 | 下载目标版本匹配的 PGO profdata | `version.sh` / `tools/update_pgo_profiles.py` | 【必须】 |
| 5 | 重放覆盖文件与补丁 | `copy_essentials.py`（Win）/ `setup.sh`（Linux） | 【必须】 |
| 6 | 检查无 `.rej`/`.orig` 残留 | 源码树全局搜索 | 【必须】 |
| 7 | GN 参数有效性核对 | `gn gen --check` + `gn args --list` 与上版 diff | 【必须】 |
| 8 | feature flag 存活性检查 | 逐项 grep 源码确认（见 4.2） | 【必须】 |
| 9 | 覆盖文件对照新版本重新合并 | 逐文件 diff（media_switches.cc、about_flags、dns 配置等） | 【必须】 |
| 10 | 自建 clang（Polly/BOLT）与新源码兼容性验证 | `build_polly.sh` + 编译 | 【推荐】 |
| 11 | 编译通过 + 冒烟测试（启动/视频/扩展商店） | 手工 | 【必须】 |
| 12 | 基准回归测试（K1-K7 对比升级前） | 第 7 章流程 | 【必须】 |
| 13 | 升级报告归档 + CHANGELOG 新增条目 | `docs/dev-logs/` | 【必须】 |
| 14 | 补丁登记表更新（新增/移除/待移除） | 见 5.3 | 【必须】 |

## 9.3 本次 M150→M151 升级作为首个按本清单执行的实例

执行方案见第 11 章；执行过程中的偏差与教训须回填本清单，形成持续改进。

---

# 10. 进阶优化路线图

**本章依据**：前序审查的仓库探索结论；`src/tools/clang/scripts/build.py`、`src/build/config/compiler/BUILD.gn`（第 3079-3091 行上游注释）、`mcloud_flags.txt`。

> 前置条件：本章多数项依赖第 7 章基准体系先行建立（7.4 基线缺失项优先落地）。

## 10.1 BOLT 后链接流程落地【推荐，脚本已就绪】

- 目标：补齐 Windows 构建的 BOLT 实际执行链路（当前仅 `use_bolt = true` + emit-relocs 接线，缺 profile 采集与执行步骤）。
- 方案：参照 `src/tools/clang/scripts/build.py` 第 1651 行起的实现（llvm-bolt instrument → 运行负载采集 prof.fdata → llvm-bolt 重排）；Windows 无 perf，采用 instrumentation 方式。
- 实现状态（2026-08-05）：流水线脚本已提供 `benchmark/tools/bolt_pipeline.ps1`（instrument/collect/optimize/verify 四阶段，含工具链探测与失败回退提示）；剩余前置依赖为 LLVM 工具链（llvm-bolt.exe/merge-fdata.exe，Chromium 内置工具链不含，见 2.5 事实核查）与一次 use_bolt=true 的构建。
- 预期效果：冷启动（K1）提升，幅度以实测为准。
- 验证：K1 前后对比；失败时回退为 `use_bolt = false` 单项开关。

## 10.2 自采 PGO profile【推荐，脚本已就绪】

- 目标：以真实用户场景 profdata 替代上游通用 profdata，使热点优化贴合产品定位（启动/多标签/B 站/YouTube）。
- 方案：`chrome_pgo_phase = 1`（instrumented）构建 → 脚本驱动典型场景 → `llvm-profdata merge` → phase=2 重建。
- 实现状态（2026-08-05）：流水线脚本已提供 `benchmark/tools/pgo_collect.ps1`（phase1-build/collect/merge/phase2-build 四阶段，自动改写 args.gn 的 phase 与 pgo_data_path）；剩余前置依赖为 llvm-profdata.exe（内置工具链不含，见 2.5）与两次全量构建的机时。
- 预期效果：K1/K2/K4 改善，幅度以实测为准。
- 验证：两套 profdata 双构建对比；回退为上游 profdata。

## 10.3 热点目标选择性 -O3【可选，默认不启用】

- 目标：对 V8/Blink/ffmpeg/net 热点目标单独调优。上游在 Android 上采用该策略的理由主要是体积（`src/build/config/compiler/BUILD.gn` 第 3079-3091 行注释）。
- 适用边界：本项目体积不作约束（见 1.7），故**默认维持全量 -O3**；仅当第 7 章基准数据显示全量 -O3 因 i-cache 压力在特定场景出现性能回归时，才考虑热点策略。
- 验证：K3/K4/K5 对比；任何情况下不得出现以体积为由的降级。

## 10.4 feature 清单治理【必须，已落地】

- 目标：M151 升级时同步完成新 feature 盘点（V8/媒体/GPU 方向）与冗余/失效 flag 清理。
- 实现：校验脚本已提供 `benchmark/tools/check_features.py`（解析清单 → 全源码树标识符检索 → 输出失效清单，含 NOT_FOUND 时退出码 1）；每次内核升级后按第 9 章清单第 8 项运行。
- 首次执行结果（2026-08-05，M150 树）：49/51 有效；`PWAFullCodeCache`、`ServiceWorkerScriptFullCodeCache` 已确认失效并从 `mcloud_flags.txt` 移除（清单现为 52 条标志 / 49 个 feature）。
- 验证：脚本已在 M150 源码树实际运行并产出上述结果。

## 10.5 优先级总览

| 优先级 | 项目 | 依赖 |
|--------|------|------|
| P0 | 基准体系建立（7.4） | 无 |
| P0 | feature 生效链路核实与固化（4.1.1） | 无 |
| P0 | 3.4 一致性整改（profdata 路径/RLZ/ICF 注释） | 无 |
| P1 | M151 内核升级（第 11 章） | P0 基准基线 |
| P1 | feature 清单治理（10.4） | M151 升级 |
| P2 | BOLT 流程落地（10.1） | P0 基准 |
| P2 | 自采 PGO（10.2） | P0 基准 |
| P3 | 热点选择性 -O3（10.3） | P2 完成后的数据积累 |

---

# 11. M150 → M151 内核升级执行方案

**本章依据**：计划批准的执行方案；`trunk.sh`、`version.sh`、`setup.sh`、`copy_essentials.py`、M149→M150 升级报告先例。

## 11.1 目标版本

- 151.0.7922.x 稳定分支（2026-07-28 发布，含 CVE-2026-15132 修复与 M151 新特性：`<usermedia>` 元素、声明式 Shadow DOM slot 分配、soft-navigation 性能条目等）。
- 【必须】执行前用 `git ls-remote --tags` 确认 151.0.7922.* 最新 tag（可能已有后续安全补丁版），以最新者为准。

## 11.2 执行步骤（对应 9.2 清单）

1. 打基线 tag（回退点）；
2. `trunk.sh` 同步主线并恢复纯净；
3. checkout 151.0.7922.* tag → `gclient sync` + `runhooks`；
4. `version.sh` 下载 M151 对应 PGO profdata（win64）；
5. `copy_essentials.py` / `setup.sh` 重放覆盖文件与补丁；
6. `.rej`/`.orig` 残留检查；
7. `gn gen out/mcloud --check` 核对全部 GN 参数；
8. 编译 `autoninja -C out/mcloud chrome` + `mini_installer`；
9. 冒烟测试 + K1-K7 基准回归；
10. 升级报告归档 + CHANGELOG 新增 M151 条目 + 打 tag 发布。

## 11.3 重点风险项与预案

| 风险 | 具体点 | 预案 |
|------|--------|------|
| 补丁与 M151 源码冲突 | ffmpeg HEVC 系列（add-hevc-ffmpeg-decoder-parser 等 3 个）、mcloud-2024-ui、mini_installer、win_updater | 逐补丁三方合并；上游已吸收的补丁转为移除（更新登记表） |
| feature flag 增删 | `mcloud_flags.txt` 约 50 项逐项核对 | 参照 M150 移除 use_webaudio_pffft 先例；失效项移除并记录 |
| 覆盖源文件漂移 | media_switches.cc、about_flags（mcloud_flag_entries.h 挂载点）、dns 配置、background_mode_manager.cc | 对照 M151 上游新基线重新手工合并 |
| profdata 版本匹配 | M151 需 7922 系列 profdata | version.sh 自动下载后校验文件名版本号 |
| GN 参数移除/更名 | M150 已有先例（use_webaudio_pffft） | `gn args --list` diff 核对 |

## 11.4 交付物

- 升级报告：参照 `docs/superpowers/specs/2026-06-19-m149-to-m150-upgrade-report.md` 格式，归档至 `docs/dev-logs/`（含基准回归对比表）；
- `docs/CHANGELOG.md` 新增 M151 条目；
- 补丁登记表更新；
- `v151.0.7922.x` tag 触发发布。

## 11.5 回退方案

- 【必须】升级前在 thorium 仓库与 chromium 源码树分别打基线 tag；任何阶段失败可按 tag 完整回退到 M150 构建状态；
- 【必须】回退后重新验证 M150 构建可编译可启动，方可结束回退操作。

---

# 附录 A：整改清单（现状违规项汇总）

| 编号 | 问题 | 出处 | 整改要求 | 条款依据 | 执行状态 |
|------|------|------|---------|----------|----------|
| A1 | profdata 路径硬编码个人目录 | `win_args_mcloud.gn` L48、`win_args.gn` L86 | 改为环境变量/相对路径 | 2.4 | ✅ 已整改（2026-08-05）：GN 不支持环境变量展开，已改为构建机标准 chromium-src 路径并附版本匹配/换机说明注释 |
| A2 | ~~Google API 密钥明文入库~~ 已撤销 | `win_args_mcloud.gn` L114-116、`CLAUDE.md` | 经项目方确认为谷歌公开的通用密钥，无滥用风险，维持现状 | — |
| A3 | enable_rlz 口径矛盾 | `win_args_mcloud.gn` L63 vs `CLAUDE.md` | 二选一并记录 ADR | 3.4-1 | ✅ 已整改（2026-08-05）：维持 true，ADR-001 |
| A4 | use_icf 注释误导 | `win_args_mcloud.gn` L35 | 更正注释（实际 ICF 由 /OPT:ICF 保障） | 2.7 | ✅ 已整改（2026-08-05） |
| A5 | 优化项数量口径不一（51 vs 60+） | `README.md` vs `CLAUDE.md` | 以 mcloud_flags.txt 实际条目为准 | 3.4-5 | ✅ 已整改（2026-08-05）：以实际条目为准（移除 2 失效项后现为 52 条标志），文档已统一 |
| A6 | mcloud_flags.txt 生效链路不明 | 全仓库无引用 | 核实并按 4.1.1 固化 | 4.1 | ✅ 已闭环（2026-08-06）：确认未生效 → inject_flags_loader.py 原位注入 → 重编 → verify_builtin_flags.ps1 子进程探测 3/3 通过；安装版打包待 mini_installer 补丁生效 |
| A7 | SSE2~SSE4.2 梯度文件废弃清理 | `other/SSE2/`~`other/SSE4.2/`、`setup.sh` 对应分支、相关文档 | 按废弃决议清理或标注仅存档 | 1.5 | ✅ 已整改（2026-08-05）：setup.sh 分支/patchSSE2 函数已移除，4 个目录共 24 个文件已删除 |
| A8 | 无任何性能基准数据 | 仓库全局 | 建立 benchmark/ 与 M150 基线 | 7.4 | 🟡 大部分完成（2026-08-06）：体系建立 + M150 基线 K1/K2/K7 已采集归档（docs/dev-logs/M150-benchmark.md）；K3-K6 手工流程待采集 |
| A9 | package.sh 缺失（BUILDING.md 引用但仓库不存在） | `docs/BUILDING.md` L225-229 | 补充脚本或修订文档指向 build.sh | 6.1 | ✅ 已整改（2026-08-05）：文档改为指向 build.sh |
| A10 | 发布产物无签名/无校验和 | `.github/workflows/release.yml` | 补 SHA256；评估代码签名 | 6.3 | 🟡 部分完成（2026-08-05）：release.yml 已生成并上传 SHA256 校验和；代码签名待评估 |

---

*本规范基于仓库内实际文件内容编写；标注【待补充】的条目在数据补齐前不具强制效力，但不得在对外文档中作出相应性能宣称。*
