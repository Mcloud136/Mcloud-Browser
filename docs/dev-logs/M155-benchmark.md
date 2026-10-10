> 采集前提（2026-10-11）：本轮在 **D99 修复之后**采集——loader 边界测试已改为跑在硬链接沙箱 `out/mcloud_loader_test`，不再改写 `out/mcloud/mcloud_flags.txt`（跑完后该文件与仓库字节一致，sha256 `61b7670856ed`）。此前 17:23 那一版与 loader 测试时段重叠，判定作废并被本文件覆盖。
> 判读纪律见 `docs/architecture/performance-build-technical-spec.md` §4.2.1：K1 同会话带 ±12 ms、K2 同会话带 0.12%，而**跨会话**差值可达 ~1.5% ⇒ 跨会话绝对值差不得当回归/收益。

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
| K1 | 冷启动时间（中位数，ms） | 47 | — | 待比对 |
| K2 | 内存峰值 50 标签（中位数，MB） | 2564.3 | — | 待比对 |
| K7 | 二进制体积（out/mcloud，MB） | 14,669.93 | — | —（仅观测） |
| K7-细分 | chrome.exe / mini_installer（MB） | 4.19 / 121.62 | — | —（仅观测） |

## 原始数据

```
--- K1 ---
被测对象: D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe | 4,389,888 B | mtime=2026-10-11T00:20:49 | 内置标志文件=同目录存在
[1/5] 冷启动: 61 ms
[2/5] 冷启动: 47 ms
[3/5] 冷启动: 51 ms
[4/5] 冷启动: 46 ms
[5/5] 冷启动: 46 ms

K1 冷启动时间（5 次有效，中位数）: 47 ms
原始数据: 61, 47, 51, 46, 46 ms
请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）
--- K2 ---
被测对象: D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe | 4,389,888 B | mtime=2026-10-11T00:20:49 | 内置标志文件=同目录存在
驻留 90 秒等待稳定...
[1/5] 工作集合计: 2558.8 MB（进程数 57）
[2/5] 工作集合计: 2558.1 MB（进程数 57）
[3/5] 工作集合计: 2564.3 MB（进程数 57）
[4/5] 工作集合计: 2567.3 MB（进程数 57）
[5/5] 工作集合计: 2589.5 MB（进程数 57）

K2 内存峰值（50 标签驻留 90s，中位数）: 2564.3 MB
原始数据: 2558.8, 2558.1, 2564.3, 2567.3, 2589.5 MB
请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）
--- K7 ---
被测产物目录: D:\wxmuma\chromium-src-155\src\out\mcloud | chrome.dll=303,440,384 B | mtime=2026-10-11T00:20:24
chrome.exe          : 4.19 MB
mini_installer      : 121.62 MB  (mini_installer.exe)
out/mcloud 总体积   : 14,669.93 MB

提示：体积仅为观测指标（规范 1.7），记录到 docs/dev-logs/ 即可，不设上限。
```

## 结论与异常记录

- 三项自动化 KPI 均成功采数（K1/K2/K7 数值已填进上表）。
- 被测对象：D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe（4389888 B，mtime 2026-10-11T00:20:49）
- 其余（待填写）
