# M151-r3 基准记录（2026-10-10）

- 构建：M151.0.7922.99 + loader v5，全量重编译（50,795 步，`autoninja exit=0`），
  `chrome.dll` 297,052,672 B @ 10:28:42，`mini_installer.exe` 123,466,752 B @ 10:30:49
- 安装包 SHA256：`393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049`
- 本版变更仅涉数据文件（`mcloud_flags.txt` 删 7 条上游不存在的条目）与打包清单脚本，
  C++ 与 r2 同源，因此预期性能不变；下列数值用于建立 r3 的实测留痕。

| 指标 | r3 实测（本机） | 档案参考值 | 可比性说明 |
|---|---|---|---|
| K1 冷启动（中位数，ms） | **39**（63, 38, 39, 39, 39） | M151 档案 73；上一次会话记 54 | 同方法（`WaitForInputIdle` + about:blank + 5 轮）。K1 绝对值小、噪声占比高，跨次比较受系统缓存/电源状态影响，仅供趋势参考 |
| K2 50 标签驻留 90s（中位数，MB） | **2927.5**（2912, 2919, 2928.1, 2931.4, 2927.5） | M151 档案 2646.2（57 进程） | **不可直接比较**：本次实测工作集来自 64 个进程（档案为 57），页面/进程数不同。需在同一 URL 集与同一进程数下重跑才能得出回归结论 |

## 有效性验证（与性能并列的稳定性证据）

- A6（`benchmark/tools/verify_builtin_flags.ps1`）rc=0：子进程命令行可见
  `SpareRendererForSitePerProcess` / `InfiniteTabsFreezing` / `PlatformHEVCDecoderSupport` 全部 OK。
- 发布门禁（`.bugreview/refresh_release.py` 经 `package_r3.py`）全绿：dll 含加载器预算字符串、
  `out/mcloud/mcloud_flags.txt` 与仓库 SHA 一致（49f79778e4d9423e…）、`chrome.release` 已登记标志文件、
  `chrome.7z` 载荷含标志文件与 r3 清理标记。
- `.bugreview/flag_stability.py` PASS（A-E 五条断言）；`check_features.py`：M151 53/53、M155 52/53
  （唯一 NOT_FOUND 为已标注的 `FlingSchedulingImprovements`）。

## 待办

- 若要给"r3 相对 r2 无内存回归"的硬结论，需在同一条件（相同 URL 列表、相同进程数）下
  用 r2 与 r3 两个安装包各跑一次 K2；本轮未做，故不作该结论。
