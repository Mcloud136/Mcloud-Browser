# 任务：M150 → M151 内核升级

- **任务编号**：TASK-M151-UPGRADE
- **创建日期**：2026-08-05
- **优先级**：P1（依赖 M150 基线数据完成，见 docs/dev-logs/M150-benchmark.md）
- **规范依据**：`docs/architecture/performance-build-technical-spec.md` 第 9 章 / 第 11 章
- **发布范围**：仅 Windows x64（ADR-003）；profdata 仅下载 win64，不为其他平台做兼容验证
- **状态**：待执行

## 目标版本

- 151.0.7922.x 稳定分支（2026-07-28 发布，含 CVE-2026-15132 修复与 M151 新特性）。
- 执行前用 `git ls-remote --tags` 确认 151.0.7922.* 最新 tag（可能已有后续安全补丁版），以最新者为准。

## 前置条件检查

- [ ] M150 基线数据已采集归档（`docs/dev-logs/M150-benchmark.md`）
- [ ] A6 内置 flags 验证已通过（`verify_builtin_flags.ps1` 退出码 0）
- [ ] 无正在运行的 chromium-src 构建进程
- [ ] 磁盘可用空间 ≥ 100 GB

## 执行步骤（对应规范 9.2 检查清单）

```powershell
# 环境（每次会话须重设）
$env:PATH = "D:\wxmuma\depot_tools;" + $env:PATH
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = "0"
$env:vs2026_install = "C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
$env:INCLUDE = "C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;" + $env:INCLUDE

cd D:\wxmuma\chromium-src\src

# 清单 1：打基线 tag（回退点，两个仓库都要）
git -C D:\wxmuma\chromium-src\src tag baseline-M150
git -C d:\wxmuma\thorium tag baseline-M150

# 清单 2：同步主线并恢复纯净上游
bash d:/wxmuma/thorium/trunk.sh

# 清单 3：checkout 目标 tag + sync + hooks
git fetch --tags
git checkout tags/151.0.7922.XXX        # XXX = 确认后的最新补丁号
gclient sync --shallow --jobs=16 --with_branch_heads --with_tags --force --reset --delete_unversioned_trees
gclient runhooks

# 清单 4：下载 M151 对应 PGO profdata（win64）
python3 tools/update_pgo_profiles.py --target=win64 update --gs-url-base=chromium-optimization-profiles/pgo_profiles
# 校验：chrome/build/pgo_profiles/ 下出现 chrome-win64-7922*.profdata

# 清单 5：部署定制（定点幂等方案，2026-08-06 重构）
$env:THOR_DIR = "d:\wxmuma\thorium"; $env:CR_DIR = "D:\wxmuma\chromium-src\src"
python3 $env:THOR_DIR\win_scripts\deploy_mcloud.py
# 内部按序执行：copy_essentials（仅 compiler_opt.gni）→ polly 接线 → polly 定义 →
# AVX2 基线 → D3D12/后台模式/DoH → flags 加载器注入 → flags 复制到 out/mcloud
# 注意：不再整体复制任何源码/构建文件（旧基线副本会覆盖新上游产生漂移，多次实证）；
# M151 的 DoH 修复已被上游吸收（默认 kAutomatic），无需再改

# 清单 6：检查无 .rej/.orig 残留
git -C D:\wxmuma\chromium-src\src status --short | Select-String "rej|orig"

# 清单 7：GN 参数有效性核对
Copy-Item d:\wxmuma\thorium\win_args_mcloud.gn out/mcloud/args.gn -Force
gn gen out/mcloud --check
gn args out/mcloud --list >> D:\wxmuma\thorium\docs\tasks\M151-args-list.txt
# 与 M150 版 args list diff，识别被移除/更名的参数（先例：M150 移除 use_webaudio_pffft）

# 清单 8：feature flag 存活性检查（必跑）
python d:\wxmuma\thorium\benchmark\tools\check_features.py --src D:\wxmuma\chromium-src\src
# NOT_FOUND 项按规范 4.2 从 mcloud_flags.txt 移除并记录

# 清单 9：覆盖源文件对照 M151 重新合并（逐文件 diff）
#   - src/media/base/media_switches.cc（D3D12 默认启用）
#   - src/chrome/browser/net/default_dns_over_https_config_source.cc（DoH kAutomatic）
#   - src/chrome/browser/background/extensions/background_mode_manager.cc（后台默认关）
#   - src/chrome/app/chrome_main_delegate.cc（flags 加载器挂载点）
#   - src/chrome/browser/mcloud_flag_entries.h 挂载点（about_flags.cc）

# 清单 11：编译 + 冒烟
autoninja -C out/mcloud chrome mini_installer
# 冒烟：启动 / 视频播放 / 扩展商店

# 清单 12：基准回归（对比 M150 基线）
d:\wxmuma\thorium\benchmark\run_baseline.ps1 -Version M151
d:\wxmuma\thorium\benchmark\tools\verify_builtin_flags.ps1

# 清单 13/14：归档
# 升级报告 -> docs/dev-logs/M151-upgrade-report.md（参照 M149→M150 报告格式）
# CHANGELOG 新增 M151 条目；更新补丁登记表
# 打 tag v151.0.7922.XXX 触发 release.yml 发布
```

## 重点风险与预案（规范 11.3）

| 风险 | 具体点 | 预案 |
|------|--------|------|
| 补丁与 M151 源码冲突 | ffmpeg HEVC 系列（3 个）、mcloud-2024-ui、mini_installer、win_updater；当前树已存在基线漂移 | 逐补丁三方合并；上游已吸收的转移除 |
| feature flag 增删 | mcloud_flags.txt 49 个 feature | check_features.py 自动筛查 + 人工复核 |
| 覆盖源文件漂移 | media_switches.cc、chrome_main_delegate.cc 等 | 对照 M151 上游重新手工合并 |
| profdata 版本匹配 | M151 需 7922 系列 | 下载后校验文件名版本号 |
| GN 参数移除/更名 | M150 已有先例 | `gn args --list` diff |

## 回退方案

任何阶段失败：两个仓库按 `baseline-M150` tag 完整回退；回退后重新验证 M150 可编译可启动方可结束。

## 交付物

1. `docs/dev-logs/M151-upgrade-report.md`（含基准回归对比表）
2. `docs/CHANGELOG.md` M151 条目
3. 补丁登记表更新
4. `v151.0.7922.XXX` tag 发布（含 SHA256 校验和）
