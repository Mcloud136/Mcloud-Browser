# MCloud Browser Changelog

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

### 📦 发行包
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
