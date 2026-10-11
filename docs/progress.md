# MCloud Browser 开发进度文档

> 最后更新：2026-06-20
> Chromium 版本：M150 (150.0.7871.37)
> 本地仓库：D:\wxmuma\thorium
> Chromium 源码树：D:\wxmuma\chromium-src\src

---

## 1. 已完成的工作

### 1.1 Chromium M150 升级
- **状态**：✅ 完成
- **从**：M149 (149.0.7827.53)
- **到**：M150 (150.0.7871.37)
- **完成内容**：
  - 源码拉取（43GB）
  - gclient sync 依赖同步
  - gclient runhooks 工具链配置
  - VS2026 BuildTools 适配

### 1.2 性能优化
- **状态**：✅ 完成（运行时标志），待下次编译（编译时参数）
- **设计文档**：`docs/superpowers/specs/2026-06-19-performance-optimization-design.md`
- **实施计划**：`docs/superpowers/plans/2026-06-19-performance-optimization.md`
- **完成内容**：
  - 运行时标志文件 mcloud_flags.txt：63 条生效开关行（60 项 feature + 3 项普通开关，2026-10-09 实测）
  - 72 个编译时参数（args.gn）验证通过
  - D3D12 视频解码默认启用
  - DNS 修复（HTTP 断流问题）
  - AVX2 + FMA3 SIMD 全局注入
  - PGO + ThinLTO + BOLT + Polly + O3 编译优化栈

### 1.3 首次 M150 编译
- **状态**：✅ 成功
- **编译目标**：50,973 个
- **编译时间**：约 2 小时
- **输出**：`D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe` (3.7MB)

### 1.4 代码审查
- **状态**：✅ 完成
- **审查文档**：`docs/superpowers/specs/2026-06-20-code-review-fixes.md`
- **发现问题**：14 个（2 Critical, 5 Important, 7 Minor）
- **已修复**：14/14

---

## 2. 当前配置

### 2.1 编译时参数（args.gn）

| 类别 | 参数 | 值 | 状态 |
|------|------|-----|------|
| SIMD | `use_avx2` | `true` | ✅ |
| SIMD | `use_fma` | `true` | ✅ |
| 编译 | `is_official_build` | `true` | ✅ |
| 编译 | `is_full_optimization_build` | `true` | ✅ |
| 编译 | `use_polly` | `true` | ✅ |
| 编译 | `use_bolt` | `true` | ✅ |
| 编译 | `use_thin_lto` | `true` | ✅ |
| PGO | `chrome_pgo_phase` | `2` | ✅ |
| V8 | `v8_enable_maglev` | `true` | ✅ |
| V8 | `v8_enable_turbofan` | `true` | ✅ |
| 视频 | `enable_platform_hevc` | `true` | ✅ |
| 视频 | `enable_hevc_parser_and_hw_decoder` | `true` | ✅ |
| 视频 | `proprietary_codecs` | `true` | ✅ |
| DRM | `enable_widevine` | `false` | ⚠️ CDM 未下载 |
| GPU | `enable_vulkan` | `false` | ✅ Windows 用 D3D12 |
| 隐私 | `enable_rlz` | `false` | ✅ 禁用 Google 追踪 |

### 2.2 运行时标志（mcloud_flags.txt）

历史口径为 51 个标志，分 9 类（下表为当时分类；当前文件实测 63 条生效开关行 =
60 项 feature + 3 项普通开关，其中 4 项因窗口拖拽卡顿已固化为注释禁用，见 §4.6）：
- 启动速度：6 个
- 视频播放：3 个
- 渲染优化：4 个
- 内存优化：11 个
- 网络优化：6 个
- GPU 优化：4 个
- 媒体优化：7 个
- 多线程：5 个
- 存储/服务：5 个

### 2.3 MCloud 覆盖文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `build/config/compiler_opt.gni` | SIMD 变量声明 | ✅ |
| `build/config/compiler/BUILD.gn` | SIMD 注入 + O3 优化 | ✅ |
| `build/config/BUILDCONFIG.gn` | 全局 SIMD 配置注册 | ✅ |
| `build/config/win/BUILD.gn` | Windows 编译配置 | ✅ |
| `media/base/media_switches.cc` | D3D12 默认启用 | ✅ |
| `chrome/browser/net/default_dns_over_https_config_source.cc` | DNS 修复 | ✅ |

---

## 3. 已修复的问题

### 3.1 HTTP 断流问题
- **现象**：MCloud Browser 访问 HTTP 网站被断流，Edge 正常
- **根因**：DNS-over-HTTPS 默认模式设为 `kSecure`（严格模式），只用 DoH 解析 DNS
- **修复**：改为 `kAutomatic`（自动模式，DoH 失败时回退普通 DNS）
- **文件**：`chrome/browser/net/default_dns_over_https_config_source.cc`

### 3.2 代码审查问题（14 个）

**已生效（无需重编）**：
| # | 问题 | 修复 |
|---|------|------|
| 4 | PauseMutedBackgroundAudio 暂停后台视频 | 移除 |
| 5 | SyncPointGraphValidation GPU 调试开销 | 移除 |
| 8 | EnableAdpfEfficiencyMode Android-only | 移除 |
| 14 | AggressiveShaderCacheLimits 缓存抖动 | 移除 |

**待下次编译生效**：
| # | 问题 | 修复 |
|---|------|------|
| 1 | win/BUILD.gn AVX2 无条件注入 | 移除重复块 |
| 2 | PGO 路径硬编码 | 移除，让 Chromium 自动查找 |
| 3 | AVX2/FMA 标志重复 | 统一由 thorium_simd_optimization 处理 |
| 6 | enable_vr 无效参数 | 移除 |
| 7 | 三重 -O3 指定 | 简化为 /clang:-O3 |
| 9 | enable_stripping 无效参数 | 移除 |
| 10 | enable_rust 冗余 | 移除 |
| 11 | enable_rlz 隐私问题 | 改为 false |
| 12 | use_text_section_splitting Windows 无效 | 移除 |
| 13 | AVX-512 rustflags 缺少 +bmi | 添加 +bmi |

---

## 4. 未完成的工作

### 4.1 GitHub Actions CI/CD
- **状态**：未解决
- **Blocker**：Chromium 源码 60+ GB，GitHub Actions 免费 Runner 无法完成 `gclient sync`
- **下一步**：预构建 Chromium 源码包，或使用自建 Runner

### 4.2 Widevine DRM 支持
- **状态**：暂时禁用
- **原因**：Widevine CDM 二进制文件需要单独下载（专有软件）
- **下一步**：如需 DRM 支持，运行 `build/download_widevine_cdm.py` 下载 CDM

### 4.3 品牌重命名
- **状态**：已放弃
- **原因**：用户决定使用 Chromium 默认品牌名

### 4.4 D3D12 视频解码
- **状态**：不可用（硬件/驱动限制）
- **现象**：即使设置 `kD3D12VideoDecoder = ENABLED_BY_DEFAULT` 并命令行强制启用，仍回退到 D3D11
- **原因**：
  - 显卡驱动版本可能不支持 D3D12 视频解码
  - 显卡硬件可能不支持
  - Chromium M150 的 D3D12 视频解码实现可能有限制
- **影响**：无，D3D11 是成熟的硬件解码方案，性能足够
- **结论**：保持 D3D11，D3D12 配置保留但不强制启用

### 4.5 核显视频绿屏问题
- **状态**：✅ 已解决（2026-08-21 实测定位并修复）
- **现象**：浏览器运行于核显播放视频时，前几秒画面绿屏/花屏，过后恢复；独显运行完全正常
- **根因**（受控实验定位，T1-T4 + GPU 分配对照）：
  - Intel 核显（UHD 770/Raptor Lake）的 **D3D12 视频解码器首帧输出缺陷**
  - 非驱动版本问题（32.0.101.6314 与最新 32.0.101.7088 均复现）；非 overlay/MPO 层（禁 DComp 视频 overlay 无效）
  - 早期未复现的原因：开发构建默认跑在独显（显示输出 GPU），复现必须显式控制 GPU 分配
- **修复**：`mcloud_flags.txt` 新增 `--disable-features=D3D12VideoDecoder`（回退 D3D11，硬解能力不受影响），实测核显下绿屏消失
- **附带修复**：安装版曾缺失 `mcloud_flags.txt`（旧安装包），已手工部署修正版到 Application 目录；下次用新安装包重装可自动携带
- **遗留**：待上游修复或 GPU 黑名单条目落地后移除该 disable 标志；`src/media/base/media_switches.cc` 的 D3D12 默认启用定制已被上游 M151 吸收，下次升级时可清理

### 4.6 窗口拖拽缩小播放视频时整浏览器冻结（缓解实验，2026-09-22 → 10-08 定案）
- **状态**：✅ 缓解有效，配置已固化（用户 2026-10-08 确认实验期间未复现）
- **现象**：核显环境，播放视频（B 站）时拖拽缩小浏览器窗口，多次卡顿后整个浏览器 UI 无响应
- **排查证据链**（系统层零痕迹）：无崩溃转储（Crashpad/WER 空）、无 TDR（Display 4101）、无内存耗尽事件、GPU 进程未重启 → 判定为 UI 线程在窗口 resize 模态循环中同步等待 GPU/合成器的软挂起；overlay 引擎全程 0%（视频未走硬件覆盖平面，resize 每帧走 3D 重缩放路径）
- **缓解**：`mcloud_flags.txt` 注释 4 项（实验组整组禁用，未二分归因）：
  `ThrottleUnimportantFrameRate`、`ReduceHardwareVideoDecoderBuffers`、`SkiaGraphite`、`SkiaGraphitePrecompilation`；
  同时关闭 GameViewer/MuMu 后台（存在虚拟显示适配器，14:47 有驱动加载失败记录）
- **残留嫌疑**（若未来复发按序排查）：Intel 核显驱动过旧（32.0.101.6790，2025-04）→ 升级驱动；二分定位 4 项中具体元凶；`chrome://gpu` 导出确认实际渲染后端
- **发布影响**：发行包 `mcloud_151.0.7922.99_win64_mini_installer.exe` 于 2026-10-08 以固化后的标志清单重新打包

### 4.7 启动标志加载器的运行时内存安全加固（第2周期专项，2026-10-09）
- **状态**：✅ 已修复并实测（缺陷 D39/D40，档案 `docs/tasks/bug-review-pak-src-defects.md`）
- **现象**：一份超大/畸形的 `mcloud_flags.txt` 会让浏览器**自身**崩溃——合并后的
  `--enable-features` 约 101KB 时 GPU 子进程 `CreateProcessW`（32767 字符上限）创建失败 →
  `FATAL gpu_data_manager_impl_private.cc:417 GPU process isn't usable. Goodbye.`（约 12s 退出）
- **根因**：加载器把文件内容无长度约束地合并进进程命令行，而该命令行会被所有子进程继承；
  1MiB 的读取上限只防"文件过大"，不防"合法大文件合并后超出 OS 命令行上限"
- **修复**（`win_scripts/inject_flags_loader.py` 的 `LOADER` 常量，加载器 v3→v4→v5）：
  - v3：合并后的 feature 列表 >24KiB 时跳过内置合并并 `LOG(WARNING)`，优雅降级
  - v4：把限制扩展为**加载器追加的全部开关共用字节预算**（总 24KiB，普通开关子预算 12KiB），
    堵住单条超长值（如 250KB 的 `--js-flags`）这条同型路径；feature 合并在循环后执行，
    故畸形普通开关不会挤占 feature 预算
  - v5：解析改用 `string_view::substr`，消除 `-Wunsafe-buffer-usage` 裸指针告警；
    注入器的"是否需替换"判定由版本号标记改为**正文比对**（正文与标记可能不同步）
- **实测证据**：
  - `probe_huge.py`：3000 条 feature（106,890B）→ 18s 存活、2 个 renderer、
    子进程命令行中探针 feature 出现 **0** 次（合并确被跳过）；对照 v2 同语料 ~12s FATAL
  - `loader_edge_test2.py` 11 例边界语料在 v5 二进制上 **11/11 PASS**
    （含 250KB `--js-flags`、4000 个普通开关两个新增用例）
  - 真实清单占用：63 条开关行合计约 1,886B，仅用掉 24KiB 预算的 8%（余量 13 倍）
  - K1 冷启动中位数 **51ms**（原始 70/48/51/51/45），无性能回归
- **方法学修正（D43）**：installer 负载是压缩的，`mini_installer.exe` 内搜文件明文
  （连 `chrome.dll` 都搜不到）不是有效验证通道；发布脚本改为校验打包输入
  （dll 内加载器字符串 + `out/mcloud/mcloud_flags.txt` 与仓库 SHA256 相同 +
  `chrome.release` 列出该文件 + installer 不早于 dll）
- **发布影响**：发行包已用 v5 构建重新生成
  `mcloud_151.0.7922.99_win64_mini_installer.exe`（123,466,240B，
  SHA256 `054efb37c8018feda5ba06842e39269908e438f27ae873b0bb670bfc05ab389f`，123,448,320B，
  2026-10-09 16:55 构建；同批 `chrome.dll` sha256 `c47b2d91eb77324ad596c5e9a3ea6cdf2f4443efa66e707375d1c5640e491d18`。
  本包为**强制全量重做**产物（touch 加载器源文件 → 重编该 TU → 重链 dll → 重建 chrome.7z → 重打 installer），
  发布判据 11 项全绿，A6 3/3 与 K1=54ms 复验通过
- **遗留**：`LOG(WARNING)` 在 `BasicStartupComplete` 阶段（logging 尚未初始化）不落 stderr，
  降级证据以子进程命令行为准；上游若为 feature 传播加上长度保护，可复核本预算是否仍必要

---

### 4.8 升级预评估与 r3 发布链路修复（第3周期，2026-10-10）

- 上游现状（双源交叉验证）：stable `155.0.8059.40`（10-06）、early stable `156.0.8078.12/.13`（10-07）、
  beta `156.0.8078.17`、canary `157.0.8095.0`、extended `154.0.8037.100`；本仓库基线 151.0.7922.99（上游 2026-07-28），
  落后 4 个里程碑 / 74 天。Chrome 自 2026-09-08 起改**双周发布**，规范 9.1"每个大版本升级一次"的节奏已失效，
  需改为攒批或锚定 extended 线。
- 定制面实测：必须重放的上游改动仅 **7 文件 / 207 行 + 新增 `compiler_opt.gni`**；
  全部注入锚点与加载器依赖的 base API 在 155/156 原样存在（`base::SplitStringPiece` 未改名）。
- D47/D48 修复与验证见 CHANGELOG 的 M151-r3 段；证据脚本 `d47_probe.py`、`flag_stability.py`、
  `api_drift.py`、`survival_check.py` 均在 `.bugreview/`，可重复执行。
- 文档与发布链路：`release.yml` 的 notes 选择器按原文抽出后实测——`v151.0.7922.99-r3` → r3 正文 ✅、
  `-r2` → r2 正文 ✅、无后缀 `v151.0.7922.99` → `…-m151.md` ✅；
  但 `v155.0.8059.40` 目前会退回"最新日期文件"（尚无 `…-m155.md`），升级发布时必须先新建该文件。
- r3 已收尾：全量重编译成功，`package_r3.py` 门禁全绿，发布包 123,466,752 B，
  SHA256 `393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049`（sidecar 同步写盘），
  A6 通过；K1/K2 实测留痕见 `docs/dev-logs/M151-r3-benchmark.md`（K2 因进程数 64≠57 不与档案值直接比）。
- 未收口：D49（V8 连字符与下划线是否等价，源码显示 `flags-impl.h:19 NormalizeChar` 归一化，已试过 stderr 通道但无法判别（V8 未知 js-flags 被静默忽略，见缺陷档案 D49 补充），需 `autoninja d8` 才能定论）；
  r3 已对外发布：L3 深度安全审查 findings=0；`main` 推到 `1cd61ff`，标注 tag
  `v151.0.7922.99-r3` 指向同一提交；CI 建出的 release 正文为 r3（选择器命中 `-r3` 文件名）；
  安装包经 API 作为 Release 资产上传（HTTP 201），GitHub 计算摘要与本地完全一致
  （`393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049`，123,466,752 B），
  公开下载校验 302→206、首字节 4D 5A、总长一致。

### 4.9 M155 内核升级完成（2026-10-10）

- 在独立第二棵树 `D:/wxmuma/chromium-src-155` 上完成 M151→M155 rebase：`deploy_mcloud.py` 7 步在全新树一次通过，
  `gn gen --check` 35,747 targets 零告警，全量 58,416 步一次编译通过，重打包 `mini_installer` 127,541,248 B。
- 定制面从 7 文件降到 **6 文件 / 206 行**（清理 D3D12VideoDecoder 的自相矛盾覆盖）。
- 同机成对基准：K1 46→45 ms、K2 2590→2563.3 MB（-1.0%）、标签开合泄漏由 +3.7 MB/轮 变为 -2.4 MB/轮、
  GPU 路径与 `--gpu-preferences` 与 151 逐字一致；A6 通过，`check_features(155)` 53/53，
  `flag_stability [155,156]` PASS。
- 新增验证工具：`benchmark/tools/leak_probe.py`（CDP 开合标签看驻留漂移）、
  `benchmark/tools/gpu_probe.py`（窗口化验证 GPU 进程与 ANGLE 后端，headless 不可用作 GPU 判据）。
- 新缺陷 **D50**：`SkiaGraphite` 三版均上游默认启用，冻结缓解此前从未真正禁用它 → 已显式 `--disable-features`，
  并列入 155 上的同方法 A/B（与 GPU 效率有张力）。
- 待办：Tier A 候选逐项 A/B、发布（push/tag/资产，需授权 + L3）、D49 用 d8 定论。
  详见 `docs/dev-logs/M155-upgrade-report.md`。

### 4.10 M155 Tier A 候选 A/B 与 D51（2026-10-10 晚，升级后追加）

- **A/B 结论：8 项候选一律不采纳**，`mcloud_flags.txt` 不新增条目。判据与方法见
  `docs/tasks/m155-perf-features.md` §5.1–§5.3；数据 `.bugreview/ab_results_round1.json`、
  `.bugreview/ab_confirm.json`；结论由 `.bugreview/ab_verdict.py` 按预登记阈值机械产出。
- **为什么"不采纳"而不是"待定"**：交错复测给出的同配置重复噪声是 K1 ±4 ms、K2 ±0.19 %、
  泄漏 ±8.9 MB，而所有候选的差值都小于它——包括 round 1 里唯一过采纳线的
  `PartitionAllocAdaptiveMemoryReclaimInterval`（三次取值跨零）。在无重复收益时加条目 = D48 的成因。
- **`SkiaGraphite` 保持显式禁用**：四项判据看不出启用/禁用的差别，而撤销拖拽冻结定案需要的是
  人工拖拽+视频复现证据。§4.6 的定案状态不变。
- **新增验证工具与纪律**（可重复执行）：
  `benchmark/tools/leak_probe.py`（标签开合驻留漂移）、`benchmark/tools/gpu_probe.py`（窗口化 GPU 路径，
  现支持 `--chrome/--label/--json`）、`.bugreview/flag_runtime_state.py`（子进程命令行回显核对运行时生效集合，
  含"未知名也会回显"的对照实验）。E 断言已升级为 feature params 语法（`param/value` 成对）校验。
- **D51（新，Low）**：`InitialWebUI` 的 params 缺 value → 参数被丢弃、退回上游默认值（三值恰为 true，
  故净行为不变）。已改写为显式 `/true`，M151 与 M155 运行时回显一致 → 非升级引入。详见缺陷档案。
- **发布物已知偏差（需知悉）**：已发布的 r3 包**不含** `--disable-features=SkiaGraphite`（D50 修于升级期，
  晚于 r3 打包），即 r3 用户实际运行在 Graphite 启用状态；M155 包修正这一点。因此 r3 上是否复现拖拽冻结
  不能用来否定定案结论，验证请以 M155 包为准。
- **发布状态**：M155 包已本地构建并通过 8 项门禁（逐项 exit=0；摘要行口径见缺陷 D89），用户 2026-10-10 决定**暂缓发布**（先做 A/B）；
  A/B 现已完成，等待发布指示。提交 `f816752` 仍在本地未推送。

### 4.11 第3周期全面 bug-review（2026-10-10 晚，D52–D67）

- 报告：`docs/tasks/bug-review-cycle3-report.md`；缺陷登记：`docs/tasks/bug-review-pak-src-defects.md`
  第3周期两节（详版 + 速查表）。
- 两条 High 是**测量与工具自身的破坏性**：K2/驻留原先按进程名汇总整机 chrome（数字与被测对象无关），
  且三个探针工具做机器级 `Stop-Process`（会杀掉用户自己的浏览器会话）。均已改为实例级指纹与实例级清理，
  并加"0 进程即 FAIL"护栏。同构建对照证据：2586.8 MB/58 进程 → 2512.85 MB/57 进程。
- 静默失效族继续收口：D57（BOM 首行丢失）、D59（行内注释整条失效 → F 断言）、
  D62（注入器不校验调用点 → 加载器可变成死代码却报 already up to date）、
  D64/D67（polly 接线与 AVX2 注入器无升级路径）。
- 卡死与进程堆积：12+ 处外部调用补 timeout；bench_*.ps1 清理移入 finally；leak_probe 不再占用固定 9333 端口。
- D63：Polly 走 ldflags 属"开了也空转"，已改 cflags 并给 Windows 关掉 BOLT 的 emit-relocs；
  `use_polly/use_bolt` 仍为 false（前置依赖未就绪）。
- D66 记录了本轮修复自身引入又被回归测试抓出的 3 个次生缺陷——包括 PowerShell
  `double + '|'` 抛类型转换异常被宽 except 吞成 0 MB。结论：**改判据/工具必须当场跑能失败的正例**。
- 加载器升到 v6（浏览器进程限定 + BOM 剥离），`loader_edge_test2` 11/11 与 `loader_edge_test3` 7/7 PASS，
  并在 M151(v5) 上取得 T1 的 Red 对照。产物随 `gn gen --check` 后的整树重编重建（成因待查，已列待办）。

### 4.12 第3周期·扩展轮（2026-10-10 晚，D77–D94）

收口报告做完完成度审计后，把测试面推到三处未覆盖的地方：导航基准脚本、门禁矩阵自身的聚合逻辑、
仓库 `src/` 的实际参与度。结果新登记 12 条缺陷，其中一条直接推翻了自己此前的收口证据形式：

- **D89（Critical）**：`final_gate_matrix.ps1` 在函数体内 `$results +=`，PowerShell 作用域规则
  使脚本级数组恒为空 → **不管门禁成败都打印 `RESULT: ALL PASS` 并 exit 0**。用不存在的构建树
  实跑取证（`leak_probe => exit=1` 与 `ALL PASS` 同屏）。修复：`$script:` 累加 + 采集条数自检 +
  `ExitCode` 为 null 判 NOEXIT + 逐项表同时打 stdout。今后**只认逐项退出码**，不认摘要行。
- D83：同文件 `param()` 不在首位 → `-OutDir` 静默丢弃（换树验证会测错树）；已归位并实测参数生效。
- D78/D79：`bench_navigation.ps1` 吞输出（无 DOM 也报"加载耗时"）+ 无超时（会挂死）；
  改为 DOM 字节判成功、`WaitForExit` 超时、实例级清理，并在文件头声明 headless 的测界限制。
- D84/D85：`verify_sources.py` 新增 PowerShell 三层检查（BOM / `param` 位置 / AST 解析，空输入即 FAIL），
  三个负例文件验证其可证伪；当场抓到 4 个在用 `.ps1` 缺 BOM 并补齐。
- D86/D87：基准与门禁脚本的默认被测对象不再硬编码 M151 回滚树，改为 env + 155 兜底 +
  **打印被测身份**（路径/字节数/mtime/标志文件）；`flag_stability.py` 前置校验三个修订并打印 commit。
- D77：实测 `src/` 590 个文件里 **344 个**是与树内不同且无人应用的惰性副本，AGENTS.md 旧口径
  （"覆盖文件/主战场/112 个"）已更正，权威清单见 `src/INVENTORY.md`（可用
  `python .bugreview/src_inventory.py --write` 重生成）。
- D90/D91（同类：文档是"会被执行"的东西）：本节 §5.1 原来只让跑 `copy_essentials.py`，
  跳过全部定点注入 → 照做会得到"编译打包都成功、定制整体静默丢失"的构建；已改为
  `deploy_mcloud.py` 唯一入口。`docs/BUILDING_WIN.md` 是上游 Thorium 流程（`C:\src`、VS 2022、
  `mcloud_shell/setup` 目标），却曾被 AGENTS.md 指为前置文档，现已在文件头加警示并更正指针。

- D92（泄漏面）：D78 新加的临时清理被 `-ErrorAction SilentlyContinue` 吞掉失败，两次实跑遗留 42 个 `%TEMP%` 文件；改为登记 pendingCleanup + 杀进程后 5 轮重试 + 残留告警，重跑后 `navdom=0 naverr=0`。教训：**清理动作本身要能被证伪**，静默容错等于没有清理。

- D93（R9 自查）：新加的 `param` 位置判据用 strip() 找顶层块，会把函数体内**合法的**
  `param(...)` 误判为违规（当前仓库没这种写法所以未暴露）。改为只认顶格 `param(`，
  并补两路对照：合法函数级 param 不报、顶层错位仍报。
- D94（High）：`run_baseline.ps1` 抓不到子基准输出（`Write-Host` 属 stream 6，`| Tee-Object` 抓的是成功流，实测 0 行）→ 基线报告没有数字却报「报告已写入」；`-Version` 默认写死 `M150`、`$env:COMPUTER_NAME` 拼错。已改 `6>&1` 捕获 + 数值填表 + 版本自动推导 + 取不到数即 exit 1。

- D99/D100（本轮最严重的一条，与 D89 同级）：门禁让 loader 边界测试直接改写 `out/mcloud/mcloud_flags.txt`，中断后发布目录里留下测试语料（106 KB/300 KB，其一非 UTF-8），后续门禁在污染窗口里测量的却是「测试配置」。已改为硬链接沙箱 + 「构建特征文件即 REFUSED」前门 + runtime_state 不一致即中止。

本轮只动工具/脚本/文档，未触碰 C++ 与 `mcloud_flags.txt`，产物与哈希不变；扩展轮收口门禁
`ALL PASS (8/8)`（假树输入会输出 `FAIL x5`/exit 1，证明该结论不是恒真输出）。

### 4.13 安装版不带 flags 的发布阻断缺陷（D105/D106，2026-10-11 r4）

- 起因是用户实测：装完 155 后 `chrome://version` 里出现 D51 修复**之前**的坏 params 形式。
  追下去发现安装目录里的 `mcloud_flags.txt` 是 9-22 手工放的旧文件，而新包**根本没有投递它**。
- D105：`setup.exe` 对 Application 根目录只搬固定三件套，根级 `chrome.release` 条目
  打包成功但不安装 ⇒ r3 及之前的所有安装包在干净机器上等于"零内置优化"。
  修：登记目标改 `%(VersionDir)s` + 加载器 v7 回退查版本目录 + 门禁加位置与字节断言。
- D106：`flag_runtime_state.py` 收尾用机器级 `Stop-Process chrome`，会杀掉用户自己的浏览器；
  改实例级指纹清理，并用诱饵实例证明修复有效。
- 复验：干净 `--system-level` 安装 → 文件落地且 sha256 与仓库一致 → 对安装后的二进制跑出
  `enable 51 / disable 2` → 卸载并确认机器状态复原。新包 127,549,952 B / `54fc59b5…`。
- 待办：把"干净安装复验"接进 CI 或收口矩阵（目前只有 `package_m155.py` 的静态断言 + 手工一次）；
  用户机器上的用户级安装仍是 r3 二进制（loader v6，靠根目录那份文件工作正常），
  下次升级/重装时会自动走到 v7/v8 路径。

### 4.14 第4周期：五轮实操检测与 r5（2026-10-11 晚）

- 口径改为**实地操作**：真拖窗口、真杀 GPU/渲染进程、真下载、真放 1.18 GB 本地视频，
  判据取浏览器自己的回答（真实 DOM / 磁盘文件 / Win32 窗口位置）。
  报告 `docs/tasks/bug-review-cycle4-report.md`，缺陷 D107–D118。
- **D109（High，产品）**：加载器 v7 以 exe 同目录为第一候选，与上游"chrome.dll 在哪才算程序目录"
  的口径相反（`main_dll_loader_win.cc:175-191`）⇒ 残留的根级 `mcloud_flags.txt` 会永久静默压掉
  安装包投递的那份，且 oracle 同序 → 门禁全绿。修：v8 改 `base::DIR_MODULE` 优先；
  判据 `.bugreview/loader_precedence_test.py`（安装同形硬链接沙箱 + 双探针真启动）
  实测 **v8 前 ROOT / v8 后 VERSION**。
- 其余 11 条全在**量具自身**（shadow DOM 盲区、错误页冒充"已恢复"、`INPUT` 结构体 48≠40 让
  SendInput 恒 87、`/json/new?url=` 丢参数、截图失败掀翻判据、泄漏判据数学上永不成立、
  探针页 `innerText=` 赋值自删被测元素等）——本轮最大的一类风险不是产品坏，而是量具会**假绿**。
- R4 顺带量化了一处取舍：`TransientKeepAlivePolicy` 使关标签后驻留从 12 进程/0.68 GB 升到
  22 进程/1.05 GB（约 +360 MB），上游测试基座正是为此默认禁用它；按 ADR-002 暂维持启用。
- 产物 r5：127,564,288 B / `17b31513…`。

## 5. 下次编译更新内核时的操作

### 5.1 编译命令

> **口径修正（2026-10-10 扩展轮，缺陷 D90）**：本节此前只让跑 `copy_essentials.py`，并把树写成
> `chromium-src`（那是 M151 回滚参考树）。照着做会**跳过全部定点注入**——加载器、Polly 接线、
> AVX2 基线、`chrome.release` 的 `mcloud_flags.txt` 登记一个都不做，结果编译与打包都成功，
> 但定制整体静默丢失（与缺陷 D47 同一失败模式）。部署的唯一入口是 `deploy_mcloud.py`。

```bash
export THOR_DIR="D:/wxmuma/thorium"
export CR_DIR="D:/wxmuma/chromium-src-155/src"    # ⚠ 多棵树并存时必须显式设置（默认值是 M151 树）
export PATH="D:/wxmuma/depot_tools:$PATH"
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"

cd "$CR_DIR"
python3 "$THOR_DIR/win_scripts/deploy_mcloud.py"          # 编排全部注入 + 复制 mcloud_flags.txt
python3 "$THOR_DIR/win_scripts/verify_sources.py"        # 源码级门禁（含 .ps1 三层检查）
cp "$THOR_DIR/win_args_mcloud.gn" out/mcloud/args.gn     # 首次或配置变更时
gn gen out/mcloud --check
autoninja -C out/mcloud chrome mini_installer
```

升级/rebase 之后的两项收尾必做（否则文档与仓库状态会立刻失真）：

```bash
python "$THOR_DIR/.bugreview/src_inventory.py" --write    # 重生成 src/INVENTORY.md（D77）
python "$THOR_DIR/.bugreview/flag_stability.py" <基线tag> <新tag> <下一tag>   # A–F 跨版本存活性
powershell -File "$THOR_DIR/benchmark/tools/final_gate_matrix.ps1"            # 收口门禁（认逐项退出码）
```

### 5.2 启动浏览器
```bash
# 使用启动脚本（自动设置 Google API 密钥）
D:\wxmuma\thorium\launch_browser.bat

# 或手动设置环境变量
set GOOGLE_API_KEY=AIzaSyCgcLY25b1jTb6Z1_8VA2hjX9HGPuYwmJY
set GOOGLE_DEFAULT_CLIENT_ID=77185425430.apps.googleusercontent.com
set GOOGLE_DEFAULT_CLIENT_SECRET=OTJgU3nD3q0q0q0q0q0q0q0q
cd /d/wxmuma/chromium-src/src/out/mcloud
start chrome.exe
```

### 5.3 编译后验证
- `chrome://flags` — 检查标志状态
- `chrome://media-internals` — 验证 D3D12 视频解码
- B 站/YouTube — 视频播放测试
- HTTP 网站 — 确认不断流

### 5.4 VS2026 注意事项
- ATL 头文件需要手动添加到 INCLUDE 路径
- 路径：`C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include`

---

## 6. 铁律约束

- **绝对不能动的**：不要修改 Chromium 核心渲染引擎代码（Blink 布局、CSS 解析等），风险太高
- **必须遵循的**：
  - 修改 `build/` 目录前必须备份 `compiler_opt.gni` 等自定义文件
  - 不要用 `git checkout -- build/` 这种批量回退命令
  - 每次修改 GN 参数后必须重新 `gn gen`
  - AVX2 编译必须保持 `use_avx2 = true` + `use_fma = true`
  - 品牌名称使用 Chromium 默认（不修改）
  - VS2026 编译必须设置 `DEPOT_TOOLS_WIN_TOOLCHAIN=0` 和 ATL INCLUDE 路径

---

## 7. 文件结构

```
D:\wxmuma\
├── thorium\                          # MCloud Browser 项目
│   ├── AGENTS.md                     # 项目指南（提供商无关，所有 Agent 共用）
│   ├── mcloud_flags.txt              # 运行时标志（63 条生效行，见 §2.2）
│   ├── win_args_mcloud.gn            # 编译时参数
│   ├── win_scripts\copy_essentials.py # 覆盖文件复制脚本
│   ├── src\build\config\             # MCloud 构建配置
│   ├── src\media\base\               # D3D12 视频解码
│   ├── src\chrome\browser\net\       # DNS 修复
│   └── docs\superpowers\             # 设计文档和实施计划
│       ├── specs\                    # 设计规格
│       └── plans\                    # 实施计划
│
└── chromium-src\                     # Chromium M150 源码
    └── src\                          # 源码根目录
        └── out\mcloud\               # 构建输出
            └── chrome.exe            # 编译产物
```
