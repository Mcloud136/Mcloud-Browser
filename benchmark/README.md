# MCloud Browser 基准测试体系（benchmark/）

本目录是《性能优化与构建配置技术规范》第 7 章（性能验证与基准测试规范）的落地实现。
所有优化项的收益验证、内核升级的回归测试均须使用本体系，结果归档至 `docs/dev-logs/`。

## KPI 总览（规范 7.1）

| 编号 | 指标 | 脚本/方法 | 状态 |
|------|------|-----------|------|
| K1 | 冷启动时间 | `bench_startup.ps1`（自动） | 可用 |
| K2 | 内存峰值（50 标签） | `bench_memory.ps1`（自动） | 可用 |
| K3 | 页面加载（FCP/LCP/SI） | Lighthouse CLI（手工流程，见下） | 流程文档化 |
| K4 | JS/WASM 性能 | Speedometer 3.1 / JetStream 3（手工流程，见下） | 流程文档化 |
| K5 | 滚动/渲染流畅度 | DevTools Performance（手工流程，见下） | 流程文档化 |
| K6 | 视频解码 CPU | 固定视频样本 + 系统采样（手工流程，见下） | 流程文档化 |
| K7 | 二进制体积 | `bench_size.ps1`（自动，仅观测，规范 1.7） | 可用 |

## 环境要求（规范 7.2，每次测试必须记录）

- 电源模式：高性能；关闭后台大负载程序；
- 浏览器无扩展、清空缓存（K1 使用全新用户数据目录，脚本已内置）；
- 记录：CPU 型号与频率策略、内存、OS 版本、GPU 驱动版本；
- 每项指标至少 5 次采样取中位数（脚本默认行为）。

## 自动化脚本用法

```powershell
# K1 冷启动（默认 5 次取中位数）
.\bench_startup.ps1 -ChromeExe "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe"

# K2 内存（50 标签 about:blank；站点级测试用 -UrlsFile urls.txt）
.\bench_memory.ps1 -Tabs 50 -SettleSeconds 90

# K7 体积
.\bench_size.ps1 -OutDir "D:\wxmuma\chromium-src\src\out\mcloud"
```

## 手工流程

### K3 页面加载（Lighthouse）

1. `npm install -g lighthouse`；
2. 以固定站点集（建议：bilibili.com 首页、youtube.com、wikipedia.org、github.com）逐个执行：
   `lighthouse <url> --chrome-flags="--headless" --output=json --output-path=<file>`；
3. 每站点 3 次取中位数，记录 FCP / LCP / Speed Index。

### K4 JS/WASM（Speedometer 3.1 / JetStream 3）

1. 克隆官方套件：`git clone https://github.com/WebKit/PerformanceTests`（Speedometer 位于 `Speedometer/`）；
2. 用被测浏览器本地打开套件页面运行，记录总分；JetStream 3 同理（`https://browserbench.org/JetStream/` 或本地部署）；
3. 对照构建（同版本 stock Chromium，-O2 默认参数）执行同一套件。

### K5 滚动流畅度

1. 固定页面（建议：长列表页面）打开 DevTools → Performance，勾选"Frame"轨道；
2. 用固定脚本或手动匀速滚动 10 秒，记录掉帧数与总帧数；
3. 同一页面同一操作重复 5 次取中位数。

### K6 视频解码 CPU

1. 准备固定 4K 视频样本（HEVC 与 AV1 各一，本地文件或固定在线地址）；
2. 全屏播放 60 秒，用任务管理器/`Get-Counter` 采样浏览器全部进程的 CPU 占用均值；
3. 硬解（默认）与软解（`--disable-accelerated-video-decode`）分别记录。

## 对照基准要求（规范 7.2）

- 每次发布前执行 K1-K7 全套；
- 优化项收益验证必须与**同版本 stock Chromium**（上游默认参数，-O2）对照；
- 内核升级前后各跑一次全套，升级报告附回归对比表。

## 结果归档

使用 `docs/dev-logs/benchmark-template.md` 复制为 `{版本}-benchmark.md` 归档；
README/CHANGELOG 中的性能数字必须可追溯到归档数据（规范 7.3）。

## 进阶优化工具（tools/）

| 脚本 | 用途 | 规范依据 | 前置依赖 |
|------|------|---------|---------|
| `tools/check_features.py` | feature 清单有效性校验（升级后必跑） | 4.2 / 9.2 第 8 项 / 10.4 | 无（已首检 M150：49/49） |
| `tools/bolt_pipeline.ps1` | BOLT 后链接优化四阶段流水线 | 10.1 | llvm-bolt.exe（内置工具链不含） |
| `tools/pgo_collect.ps1` | 自采 PGO profile 四阶段流水线 | 10.2 | llvm-profdata.exe（内置工具链不含） |
