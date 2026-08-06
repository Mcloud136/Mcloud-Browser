# 基准测试结果 — M150

- **测试日期**：2026-08-06
- **构建信息**：Chromium 150.0.7871.x（M150 树 + MCloud 覆盖：flags 内置加载器/polly-bolt 接线/D3D12 默认启用等），args.gn 模板：win_args_mcloud.gn（AVX2+FMA3、-O3、ThinLTO、PGO phase=2；use_polly/use_bolt=false）
- **对照基准**：无（首次基线）
- **采集工具**：benchmark/run_baseline.ps1（K1/K2 自动化；数值经人工从工具输出回填，因脚本 v1 的 Tee 捕获缺陷已记录待修）

## 环境信息

| 项目 | 值 |
|------|----|
| CPU | Intel(R) Core(TM) i9-14900HX |
| 内存 | 31.6 GB |
| OS | Microsoft Windows 11 专业版 10.0.26200 |
| GPU / 驱动 | GameViewer Virtual Display Adapter / 15.6.5.199（远程虚拟显示，K5/GPU 类指标不代表本机独显） |
| 电源模式 | 高性能（请确认） |
| 扩展 | 无（脚本使用全新用户数据目录） |

## KPI 结果（中位数）

| 编号 | 指标 | M150 基线值 | 备注 |
|------|------|------------|------|
| K1 | 冷启动时间 | **71 ms**（第二次运行）/ 76 ms（第一次） | WaitForInputIdle 代理指标，全新用户目录 + about:blank；两轮数据接近，可复现性良好 |
| K2 | 内存峰值（50 标签 about:blank，驻留 90s） | **2669.1 MB**（57 个进程） | 采样单调收敛（2653→2669.6），稳定 |
| K7 | 二进制体积 | chrome.exe 3.62 MB；mini_installer 112.27 MB；out/mcloud 总计 12990 MB | 仅观测（规范 1.7） |
| K3-K6 | 页面加载 / JS / 滚动 / 视频解码 | 待手工流程采集 | 见 benchmark/README.md |

## 原始数据

```
--- K1（第一轮，5 次，ms）---
145, 65, 76, 80, 68          中位数 76
--- K1（第二轮，5 次，ms）---
95, 61, 75, 66, 71           中位数 71
--- K2（50 标签驻留 90s，5 次采样，MB，进程数 57）---
2653, 2662.6, 2669.1, 2669.2, 2669.6   中位数 2669.1
--- K7 ---
chrome.exe: 3.62 MB
mini_installer.exe: 112.27 MB
out/mcloud 目录: 12990.49 MB
```

## 结论与异常记录

1. **A6 闭环确认**：本构建已包含内置 flags 加载器，verify_builtin_flags.ps1 子进程命令行探测 3/3 通过（SpareRendererForSitePerProcess / InfiniteTabsFreezing / PlatformHEVCDecoderSupport 均注入成功），K1/K2 数值即"52 条内置优化标志生效状态"下的基线。
2. K1 采用 WaitForInputIdle 代理指标，绝对值偏小（about:blank 场景）；跨版本对比时须保持同一方法与场景。
3. GPU 为远程虚拟显示适配器，视频解码 CPU（K6）与滚动流畅度（K5）测试建议在本地物理 GPU 环境复测。
4. 待办：K3-K6 手工流程采集；run_baseline.ps1 的 Tee 数据捕获缺陷修复（原始数据自动落盘）。
