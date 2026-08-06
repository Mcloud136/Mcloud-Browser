# M151 升级报告（M150 → M151.0.7922.99）

- **执行日期**：2026-08-06
- **执行人**：Qoder Agent + 用户协同
- **任务依据**：`docs/tasks/m151-upgrade-task.md`、技术规范第 9/11 章
- **结果**：✅ 成功（构建通过 + A6 验证通过 + 基线无回归）

## 执行清单核对（任务文档 14 项）

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | baseline-M150 tag（两仓库）+ 树状态快照 | ✅ |
| 2 | 主线同步 | ✅ 改用定向浅拉取（见偏差 1） |
| 3 | checkout 151.0.7922.99 + gclient sync + runhooks | ✅ sync 236/236、runhooks 116/116 |
| 4 | win64 PGO profdata | ✅ chrome-win64-7922-*.profdata（459MB）+ V8 builtins profiles 15.1.206.13 |
| 5 | 部署定制 | ✅ deploy_mcloud.py 定点幂等方案（见偏差 2） |
| 6 | .rej 残留检查 | ✅ 定点方案零补丁零残留 |
| 7 | gn gen --check | ✅ 零告警（31672 targets） |
| 8 | feature 存活性 | ✅ check_features.py 49/49 |
| 9 | 覆盖源文件对照合并 | ✅ 上游基线 + 定点注入（DoH 修复已被上游吸收，少一处定制） |
| 11 | 编译 + 冒烟 | ✅ 54824 步 EXIT 0；chrome.dll 链接 537s |
| 12 | A6 验证 + 基线对比 | ✅ 3/3 通过；K1 持平、K2 -0.86% |
| 13-14 | 报告 + CHANGELOG | ✅ 本文档 + CHANGELOG M151 条目 |

## 关键偏差与决策

1. **定向浅拉取替代 trunk.sh**：`git fetch --depth 1 origin tag 151.0.7922.99`（230MB/1 分钟），规避全量 tag 枚举（28M 对象/20GB）与代理不稳定问题；
2. **定点幂等部署替代整体覆盖**：实证仓库内副本与 M151 上游漂移（compiler/BUILD.gn 2092 行等），全部定制改为 6 个定点脚本（`win_scripts/deploy_mcloud.py` 统一入口）；
3. **V8 builtins profiles 直连下载**：gclient hook 不可用时从 GCS 桶直连（by-version/15.1.206.13/）；
4. **DoH 定制移除**：M151 上游默认已是 kAutomatic，MCloud 的 M150 修复被上游吸收。

## 故障处置记录

1. mksnapshot profile 版本不匹配 → 下载匹配版本 profiles；
2. gclient sync `--force --reset --delete_unversioned_trees` 清除定制与 buildtools/win → deploy_mcloud.py 恢复 + cipd ensure 恢复 gn.exe；经验固化：该参数组合永久禁用；
3. 代理宕机致 cipd 域名污染 → 重启代理解决；代理需开机自启。

## 基线对比（详见 docs/dev-logs/M151-benchmark.md）

| 指标 | M151 | M150 | 变化 |
|------|------|------|------|
| K1 冷启动 | 73ms | 71ms | +2.8%（噪声内） |
| K2 内存 50 标签 | 2646.2 MB | 2669.1 MB | **-0.86%** |
| mini_installer | 117.72 MB | 112.27 MB | +4.9%（仅观测） |

## 遗留事项

1. K3-K6 手工基准待采集（本地物理 GPU 环境）；
2. mini_installer 是否随包分发 mcloud_flags.txt 待验证（当前安装版生效性未测）；
3. Widevine CDM 未包含、核显绿屏问题沿用 M150 状态；
4. run_baseline.ps1 的 Tee 输出捕获缺陷待修（当前数值人工回填）。
