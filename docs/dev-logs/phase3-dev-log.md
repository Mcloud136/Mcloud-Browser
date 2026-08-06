# Phase 3 开发日志 — M150 → M151 内核升级

- **开始日期**：2026-08-06
- **目标版本**：151.0.7922.99（M151 稳定分支最新 tag，ls-remote 实查确认）
- **规范依据**：`docs/architecture/performance-build-technical-spec.md` 第 9/11 章、`docs/tasks/m151-upgrade-task.md`
- **状态**：✅ 编译前置全部就绪，待用户通知后开始编译

## 已完成步骤（清单 1-8）

| 步骤 | 结果 |
|------|------|
| 1. 回退点 | 两仓库 `baseline-M150` tag 已打；升级前树状态快照 `docs/dev-logs/m151-pre-upgrade-tree-state.txt` |
| 2-3. 源码同步 | 浅克隆直取 tag（`git fetch --depth 1 origin tag 151.0.7922.99`，230MB/1 分钟，规避全量 20GB 枚举）；checkout 后 VERSION=151.0.7922.99 |
| 3b. gclient sync | 236/236 项目完成（用 `--revision src@<SHA>` 规避 src 重克隆；修复了 `.gclient` 误置于 src/ 内的布局问题） |
| 3c. runhooks | 116/116 完成（修复 thorium 版 vs_toolchain.py 强制下载远程工具链 401 问题：恢复 M151 上游版 + DEPOT_TOOLS_WIN_TOOLCHAIN=0） |
| 4. profdata | `chrome-win64-7922-*.profdata`（459MB）已下载，args.gn 路径已指向（双库同步） |
| 5. 部署 | **方案重构为定点幂等**：`win_scripts/deploy_mcloud.py` 统一入口（6 个定点脚本 + flags 复制），端到端验证幂等通过；树状态 = 6 改 + 1 新增（全部预期内） |
| 6. .rej 检查 | 定点方案零补丁，零残留 |
| 7. gn gen | `gn gen out/mcloud --check` 零告警通过（31672 targets） |
| 8. feature 校验 | `check_features.py` 49/49 全部存活于 M151 |

## 部署方案重构说明（重要经验）

升级过程中实证：仓库内 `src/` 覆盖文件基于 M150 基线，与 M151 上游存在漂移——
`compiler/BUILD.gn` 2092 行、`media_switches.cc` 369 行、`chrome_main_delegate.cc` 8 处 API 不兼容。
整体覆盖会破坏新树构建。故重构为：

- **基线策略**：chromium 树保持 M151 纯上游文件；
- **定制策略**：全部定点幂等脚本（`win_scripts/` 下 6 个 apply/inject 脚本）；
- **统一入口**：`deploy_mcloud.py`（未来升级唯一部署命令）；
- **意外收获**：MCloud 的 DoH kAutomatic 修复已被 M151 上游吸收，少一处定制。

## M151 关键确认点

- `-O3` 链路存在于 M151 上游 `compiler/BUILD.gn`（optimize_speed：`/clang:-O3`，L2686）；
- polly/emit-relocs 接线 + 定义已重新应用（use_polly/use_bolt 维持 false，前置未就绪）；
- AVX2+FMA3 基线已在 `win/BUILD.gn` 重新应用（替换上游 -msse3）；
- clang 工具链已由 runhooks 更新（llvmorg-23-init-19482）。

## 待执行（用户通知后）

1. 全量编译：`autoninja -C out/mcloud chrome mini_installer`（预计 3.5-4 小时 + 链接）；
2. A6 验证：`benchmark/tools/verify_builtin_flags.ps1`；
3. M151 基线：`benchmark/run_baseline.ps1 -Version M151`（对比 M150：K1 71ms / K2 2669.1MB）；
4. 归档：升级报告 + CHANGELOG M151 条目 + 规范基线版本更新。

## 网络经验沉淀

- 直连 chromium.googlesource.com 被 schannel 切断 → 走本地代理 `127.0.0.1:7897`（环境变量方式，不改 git 配置）；
- `git fetch --tags` 全量 tag 触发 28M+ 对象枚举（20GB 传输）→ 用 `--depth 1 ... tag <name>` 定向浅拉取；
- gclient 对浅克隆 src 会全量重克隆（66.7GB）→ 用 `--revision src@<已有SHA>` 使协商零传输。
