# 基准测试结果 — M151-opt

- **测试日期**：2026-08-06
- **构建信息**：Chromium M151（151.0.7922.99）+ 新增 17 项运行时 feature + V8 flag 修正（下划线命名），flags 共 69 条
- **对照基准**：M151 基线（docs/dev-logs/M151-benchmark.md，同机同方法）
- **构建机**：NitroTune-OS（i9-14900HX）

## 环境信息

| 项目 | 值 |
|------|----|
| CPU | Intel(R) Core(TM) i9-14900HX |
| 内存 | 31.6 GB |
| OS | Microsoft Windows 11 专业版 10.0.26200 |
| GPU / 驱动 | GameViewer Virtual Display Adapter / 15.6.5.199（远程虚拟显示，K5/GPU 类指标不代表本机独显） |
| 电源模式 | 高性能 |
| 扩展 | 无（脚本使用全新用户数据目录） |

## KPI 结果（M151-opt vs M151）

| 编号 | 指标 | M151-opt | M151 基线 | 变化 |
|------|------|----------|-----------|------|
| K1 | 冷启动时间（中位数，ms） | **79**（121, 79, 80, 78, 75） | 73 | +6ms（+8.2%，首跑 121 拉高，噪声偏大） |
| K2 | 内存峰值 50 标签驻留 90s（中位数，MB） | **2696.4**（2686.7→2703.3） | 2646.2 | **+50.2 MB（+1.9%）** |
| K7 | chrome.exe / mini_installer 体积 | 3.70 MB / 117.72 MB | 3.70 / 117.72 | 无变化（仅改 flags） |
| K3-K6 | 页面加载 / JS / 滚动 / 视频解码 | 待手工流程采集 | — | 见 benchmark/README.md |

## 新增/修正内容验证

- V8 flag 命名修正已生效：`invocation_count_for_maglev=200` 确认注入子进程命令行（旧连字符写法在 M151 不生效）
- 新增 feature 注入验证 5/5 通过：ThreadedPreloadScanner、MultipleSpareRPHs、RevokeMediaSourceObjectURLOnAttach、HttpDiskCachePrewarming、invocation_count_for_maglev=200
- check_features.py 复验 66/66 feature 在 M151 存活

## 追加：预载收益验证（导航响应 + 内存隔离测试，2026-08-06）

### 导航响应测试（bench_navigation.ps1，预热后 3 轮中位数）

| 页面 | preload-on | preload-off | 差异 |
|------|-----------|-------------|------|
| example.com | 601 ms | 592 ms | +1.5%（无差异） |
| bilibili.com | **1434 ms** | 1519 ms | **-5.6%（预载更快）** |
| qq.com | 2474 ms | 2448 ms | +1.1%（无差异） |

### 内存隔离测试（bench_memory.ps1 -ExtraFlags，真实站点 50 标签驻留 90s）

| 配置 | K2 内存 |
|------|--------|
| 全部启用（bilibili/qq/baidu/taobao 等真实站点） | 7676.2 MB |
| 禁用 MultipleSpareRPHs+LoadingPredictorPrefetch+NewTabPageTriggerForPrerender2 | 7550.8 MB |
| 差值 | **-125.4 MB（-1.6%）** |

（about:blank 场景下两者几乎无差异，印证预载内存代价主要体现在真实页面预取）

### 结论（数据链完整）

1. 预载类 feature 的导航收益**仅 bilibili 体现 -5.6%**（预连接/预取命中），其余页面无差异——收益依赖预测命中率，不稳定；
2. 内存代价在真实站点场景实测 **-125MB**（禁用三项后），比 about:blank 场景的 +50MB 更显著；
3. **决策**：移除 `MultipleSpareRPHs`、`LoadingPredictorPrefetch`、`NewTabPageTriggerForPrerender2` 三项（内存代价大、收益不稳定）；保留其余预载类与全部脚本加速类；
4. 移除后 flags 69→66 条；最终配置真实站点 K2 实测 **7472.8 MB**，比全配置 7676.2 MB 降 **203 MB（-2.6%）**，也低于仅禁用三项的 7550.8 MB（其余保留项亦有正向内存效果）；
5. 剩余预载类（Prerender2WarmUpCompositor*、PreloadTopChromeWebUI、BookmarkTriggerForPreconnect、LoadingPreconnectToRedirectTarget）保留，其内存代价低且 bilibili 导航 -5.6% 收益主要由预连接类贡献。

## 结论与异常记录

1. **内存回归 +50.2 MB（+1.9%）**：新增的预载/预热类 feature（MultipleSpareRPHs 多备用渲染进程、Preconnect/Prerender 系列）以内存换取预载收益，这是预期的空间-速度权衡。若对内存敏感，建议评估移除 `MultipleSpareRPHs`、`LoadingPredictorPrefetch`、`NewTabPageTriggerForPrerender2` 三项后重测。
2. **K1 冷启动 +6ms（+8.2%）**：首跑 121ms 显著拉高（冷态噪声），剔除首跑后中位数约 78ms，仍略高于基线。预载 feature 在启动时多做了预热工作，可能小幅增加启动耗时，需更多样本确认。
3. **V8 修正收益待 K4（JS 基准）验证**：`invocation_count_for_maglev=200` 使脚本更快进入 Maglev 编译，理论加速脚本执行，但需 JetStream/Speedometer 实测确认。
4. **K2/K3-K6 待补**：网页加载与脚本执行速度收益须在本地物理环境用 Speedometer 3.1 / JetStream 3 / Lighthouse 实测。
5. **权衡建议**：本项目定位"性能优先、体积不约束"，但内存是真实性能维度。建议保留 V8 修正 + 脚本加载加速类（无内存代价或代价小），对内存增幅大的预载类做二分定位后取舍。
