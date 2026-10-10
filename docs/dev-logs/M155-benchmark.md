> ⚠ **本文件的 K1/K2 数值判定为作废（缺陷 D99）**：采集时段（17:23–17:26）与门禁矩阵的
> loader 边界测试阶段重叠，而当时测试会把 `out/mcloud/mcloud_flags.txt` 改写成边界语料
> （恢复依赖 finally，被中断即遗留）。那种状态下浏览器**没有内置优化清单**，
> 因此这里的启动与内存数字不代表发布配置。D99 已改为硬链接沙箱隔离，
> 需在沙箱生效后重跑 `benchmark/run_baseline.ps1` 覆盖本文件。

# 基准测试结果 — M155

- **测试日期**：2026-10-11
- **构建信息**：Chromium M155，args.gn 模板：win_args_mcloud.gn，构建机：WIN-NDKL5A54MFO
- **对照基准**：无（首次基线）

## 环境信息

| 项目 | 值 |
|------|----|
| CPU | Intel(R) Core(TM) i9-14900HX |
| 内存 | 31.6 GB |
| OS | Microsoft Windows 11 专业工作站版 10.0.26200 |
| GPU / 驱动 | MuMu Virtual Display Adapter / 20.36.41.498 |
| 电源模式 | 请手工确认已设为高性能 |
| 扩展 | 无（脚本使用全新用户数据目录） |

## KPI 结果

| KPI | 指标 | 本次值 | 上次基线 | 判定 |
|-----|------|--------|----------|------|
| K1 | 冷启动时间（中位数，ms） | 53 | — | 待比对 |
| K2 | 内存峰值 50 标签（中位数，MB） | 2550.5 | — | 待比对 |
| K7 | 二进制体积（out/mcloud，MB） | 14,669.27 | — | —（仅观测） |
| K7-细分 | chrome.exe / mini_installer（MB） | 4.19 / 121.62 | — | —（仅观测） |

## 原始数据

```
--- K1 ---
被测对象: D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe | 4,389,888 B | mtime=2026-10-11T00:20:49 | 内置标志文件=同目录存在
[1/5] 冷启动: 67 ms
[2/5] 冷启动: 45 ms
[3/5] 冷启动: 53 ms
[4/5] 冷启动: 53 ms
[5/5] 冷启动: 45 ms

K1 冷启动时间（5 次有效，中位数）: 53 ms
原始数据: 67, 45, 53, 53, 45 ms
请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）
--- K2 ---
被测对象: D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe | 4,389,888 B | mtime=2026-10-11T00:20:49 | 内置标志文件=同目录存在
驻留 90 秒等待稳定...
[1/5] 工作集合计: 2550.5 MB（进程数 58）
[2/5] 工作集合计: 2550.6 MB（进程数 58）
[3/5] 工作集合计: 2550.2 MB（进程数 58）
[4/5] 工作集合计: 2550.4 MB（进程数 58）
[5/5] 工作集合计: 2553.2 MB（进程数 58）

K2 内存峰值（50 标签驻留 90s，中位数）: 2550.5 MB
原始数据: 2550.5, 2550.6, 2550.2, 2550.4, 2553.2 MB
请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）
--- K7 ---
被测产物目录: D:\wxmuma\chromium-src-155\src\out\mcloud | chrome.dll=303,440,384 B | mtime=2026-10-11T00:20:24
chrome.exe          : 4.19 MB
mini_installer      : 121.62 MB  (mini_installer.exe)
out/mcloud 总体积   : 14,669.27 MB

提示：体积仅为观测指标（规范 1.7），记录到 docs/dev-logs/ 即可，不设上限。
```

## 结论与异常记录

- 三项自动化 KPI 均成功采数（K1/K2/K7 数值已填进上表）。
- 被测对象：D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe（4389888 B，mtime 2026-10-11T00:20:49）
- 其余（待填写）
