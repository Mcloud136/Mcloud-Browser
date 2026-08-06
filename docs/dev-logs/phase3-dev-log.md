# Phase 3 开发日志 — M150 → M151 内核升级

- **开始日期**：2026-08-06
- **目标版本**：151.0.7922.99（M151 稳定分支最新 tag，ls-remote 实查确认）
- **规范依据**：`docs/architecture/performance-build-technical-spec.md` 第 9/11 章、`docs/tasks/m151-upgrade-task.md`
- **状态**：✅ M151 升级完成（构建通过 + A6 验证 3/3 + 基线无回归，见 M151-upgrade-report.md）

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

## 编译故障处置链（2026-08-06，已全部解除）

首次编译在 22143/56386 失败，连环排查与修复：

1. **V8 builtins PGO profile 版本不匹配**：mksnapshot 报 `Rejected profile data for RecordWriteSaveFP due to function change`——本地 profiles 是 M150 时代（6/19）。处置：查 v8-version.h 得 15.1.206.13，从 GCS 直连下载 `chromium-v8-builtins-pgo/by-version/15.1.206.13/` 全部 5 个文件（meta.json 校验通过）；
2. **gclient sync 副作用**：带 `--force --reset --delete_unversioned_trees` 的 sync 清除了 src 内全部定制并中断后删掉了 buildtools/win（含 gn.exe）。处置：`deploy_mcloud.py` 重跑完整恢复定制（定点幂等体系经受实战验证）；gn.exe 用 `cipd ensure -root buildtools\win` 按 DEPS 固定版本（gn_version git_revision:1d86777e...）单独恢复；
3. **网络故障链**：设备宕机后代理软件未自启 → cipd 服务域被 DNS 污染（解析到 157.240.x）无法直连、DoH 也不可达；用户重启代理（7897）后 cipd 4 秒完成下载；
4. **经验固化**：
   - gclient sync 绝不再用 `--force --reset --delete_unversioned_trees`（会清定制与 CIPD 二进制）；安全参数组合：`--nohooks --jobs 8 --revision src@<SHA>`，src 有定制时 gclient 会拒绝同步但无破坏性；
   - V8 profiles 下载不依赖 gclient hook，可直接 HTTPS 拉 GCS 桶（storage.googleapis.com 可直连时）；
   - cipd/gclient/git 对 Google 域的访问均需代理（域名被污染），代理软件需随开机自启。

恢复后编译已重启，ninja 重生成成功（gn.exe 生效），全速推进中。

## 执行结果（2026-08-06 完成）

1. ✅ 全量编译成功：54824 步 EXIT 0（chrome.dll 链接 537s）；产物：chrome.exe 3.70MB / chrome.dll 283.3MB / mini_installer.exe 117.72MB；
2. ✅ A6 验证通过：verify_builtin_flags.ps1 子进程探测 3/3，52 条内置标志真实生效；
3. ✅ M151 基线采集完成（K1 73ms / K2 2646.2MB，vs M150：持平/内存 -0.86%），归档 M151-benchmark.md；
4. ✅ 升级报告 M151-upgrade-report.md + CHANGELOG M151 条目已归档。

## 追加：M151-opt 运行时优化（2026-08-06）

在 M151 基线上实施三类运行时优化 + V8 flag 修正，详见 `docs/dev-logs/M151-opt-benchmark.md`：

1. **V8 flag 命名修正**（确定性 bug）：旧连字符写法 `--invocation-count-for-maglev` 在 M151 不生效，改为下划线 `invocation_count_for_maglev=200`（默认 400）+ `invocation_count_for_turbofan=1500`（默认 3000）+ `osr-from-maglev` + `sparkplug-plus`；
2. 新增 17 项 feature（启动预载 7 + 脚本加载 7 + MSE 3），均经 check_features.py 核实存活（66/66）；
3. 基准结果：K1 79ms（+8%，首跑噪声）；**K2 内存 +50MB（+1.9%）**——预载类 feature 内存代价，建议评估移除 MultipleSpareRPHs/LoadingPredictorPrefetch/NewTabPageTriggerForPrerender2 后重测；
4. B 站弹幕 GPU 加速在源码未找到专属 feature，标注待验证。

## 网络经验沉淀

- 直连 chromium.googlesource.com 被 schannel 切断 → 走本地代理 `127.0.0.1:7897`（环境变量方式，不改 git 配置）；
- `git fetch --tags` 全量 tag 触发 28M+ 对象枚举（20GB 传输）→ 用 `--depth 1 ... tag <name>` 定向浅拉取；
- gclient 对浅克隆 src 会全量重克隆（66.7GB）→ 用 `--revision src@<已有SHA>` 使协商零传输。
