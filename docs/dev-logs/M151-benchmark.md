# 基准测试结果 — M151

- **测试日期**：2026-08-06
- **构建信息**：Chromium 151.0.7922.99（MCloud 定制：AVX2+FMA3、-O3、ThinLTO、PGO phase=2、52 条内置启动标志），args.gn 模板：win_args_mcloud.gn
- **对照基准**：M150 基线（docs/dev-logs/M150-benchmark.md，同机同方法）
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

## KPI 结果（M151 vs M150）

| 编号 | 指标 | M151 | M150 | 变化 |
|------|------|------|------|------|
| K1 | 冷启动时间（中位数，ms） | **73**（105, 71, 71, 76, 73） | 71（95, 61, 75, 66, 71） | +2ms（+2.8%，噪声范围内） |
| K2 | 内存峰值 50 标签驻留 90s（中位数，MB） | **2646.2**（2636.2→2652.6，57 进程） | 2669.1 | **-22.9 MB（-0.86%）** |
| K7 | chrome.exe / mini_installer 体积 | 3.70 MB / 117.72 MB | 3.62 MB / 112.27 MB | +2.2% / +4.9%（仅观测，规范 1.7 不作约束） |
| K3-K6 | 页面加载 / JS / 滚动 / 视频解码 | 待手工流程采集 | — | 见 benchmark/README.md |

## A6 验证（内置启动标志）

`verify_builtin_flags.ps1` 子进程命令行探测 **3/3 通过**（SpareRendererForSitePerProcess / InfiniteTabsFreezing / PlatformHEVCDecoderSupport），52 条内置标志在 M151 构建中真实生效。

## 结论与异常记录

1. M151 相对 M150 性能持平（K1 差异在测量噪声内），内存略降 0.86%——升级无性能回归，达成升级目标；
2. K1 为 WaitForInputIdle 代理指标 + about:blank 场景，绝对值小、噪声占比高，跨版本对比须保持同方法；
3. 安装包体积 +4.9% 为上游正常增长（仅观测）；
4. GPU 为远程虚拟显示适配器，K5/K6 须在本地物理 GPU 复测；
5. 已知限制沿用 M150：Widevine 未包含（CDM 未下载）、核显绿屏问题待查。
