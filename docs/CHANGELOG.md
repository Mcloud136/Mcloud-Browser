# MCloud Browser Changelog

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
