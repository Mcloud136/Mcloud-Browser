# M155 升级执行任务单（M151.0.7922.99 → M155.0.8059.40）

- **制定日期**：2026-10-10
- **目标版本决定依据**：用户 2026-10-10 指定 M155（而非等 M156 的 10-20 全量稳定）
- **前置**：M151-r3 已发布（D47 注入器 + D48 清理已验证），M155 代码与工具链预拉取在 `D:/wxmuma/chromium-src-155`
- **关联文档**：可行性证据 `docs/tasks/m155-upgrade-preassessment.md`；性能新特性候选 `docs/tasks/m155-perf-features.md`；流程规范 技术规范第 9 章 14 项清单
- **稳定性总原则（用户要求）**：升级后当前生效的 flag 必须继续生效。已用 `.bugreview/flag_stability.py` 在升级前就把这条变成机器断言——r3 的 53 条 feature 中 52 条在 151/155/156 三版全部声明存在，唯一例外 `FlingSchedulingImprovements` 已标注升级期处置。

## 阶段 0：预拉取核对（本次已在做，完成后再进阶段 1）

| 项 | 期望 | 核对命令 |
|---|---|---|
| src 版本 | `155.0.8059.40`（commit `cfaadc5a…`） | `git -C chromium-src-155/src describe --tags` |
| DEPS 全量 | `third_party/ffmpeg`、`buildtools/win/gn.exe`、`third_party/ninja/ninja.exe`、`testing/location_tags.json`、`.gn` 均存在 | 见 `finish_m155_sync.log` 尾部 Test-Path 列表 |
| 工具链 | `third_party/llvm-build/Release+Asserts/bin/clang.exe` 可执行并打印版本 | `clang.exe --version` |
| V8 builtins profiles | `third_party/v8/builtins` 存在且版本与 V8 匹配（`checkout_pgo_profiles = True`） | 目录列表 |
| PGO profdata | `chrome/build/pgo_profiles/chrome-win64-8059-1790681878-a5a326a93a5b6da6820b51c3dd27c598393c85c9-bafd721ba752e4b3753f103970251e378ca171d6.profdata` | 已下载（104.4 MiB） |

已知坑（本轮实测）：① `gclient sync --jobs=16` 会被 chromium.googlesource.com **429 限流**中断，须降到 `--jobs=4` 并多轮重试；② depot_tools 必须先 `DEPOT_TOOLS_UPDATE=0`（仓库内为固定修订，自更新失败会直接终止 sync）；③ 钩子按字面调用 `python3`，若解析到 `WindowsApps` 占位程序会全线失败，修法是在真实 Python 目录内 `mklink /H python3.exe python.exe` 并把该目录置于 PATH 前。

### 阶段 0 实测结果（2026-10-10 预拉取完成）

| 检查项 | 实测 | 判定 |
|---|---|---|
| src 版本 | `cfaadc5a13` / `git describe` = `155.0.8059.40` | ✅ |
| DEPS 依赖 | `v8`、`third_party/ffmpeg`、`third_party/blink`、`buildtools/win/gn.exe`（gn 2562）、`third_party/ninja/ninja.exe`（1.12.1）、`testing/location_tags.json` 均到位；补跑一轮 `gclient sync --jobs=4` 返回 **rc=0** | ✅ |
| 编译器 | `third_party/llvm-build/Release+Asserts/bin/` 内为 **clang-cl.exe / lld-link.exe / llvm-ml.exe** 等（Windows 路线没有 `clang.exe`，151 树同样如此）；`cr_build_revision` = `llvmorg-24-init-7747-g62397f8b-27`（151 为 `llvmorg-23-init-19482-g53d18800-1`） | ✅ 已更新到 155 对应修订 |
| PGO profdata | `chrome-win64-8059-1790681878-a5a326a93a5b6da6820b51c3dd27c598393c85c9-bafd721ba752e4b3753f103970251e378ca171d6.profdata`（104.4 MiB） | ✅ 记入 `pgo_data_path` |
| runhooks | Windows 关键钩子全部先于断点成功：`win_toolchain`、`clang_tot`、`lastchange`（含 skia/dawn/gpu_lists 变体）、`rc_win`、`apache_win32`。断点为 `generate_location_tags.py` 报 `root dir is not in a git repository`（gclient 以解决方案根目录为 cwd 执行钩子，该目录不是 git 仓库），其**后**剩余钩子均属测试/telemetry/CastOS/reclient 类，不参与本机 `chrome` + `mini_installer` 构建 | ⚠️ 可容忍，升级构建前无需修复；若需完全清洁，可单独用真实 python3 在 `src/` 内生成该文件（本轮已生成成功） |

补充：`third_party/v8/builtins` 在两棵树都不存在（V8 builtins profiles 实际由 DEPS/钩子按 `checkout_pgo_profiles` 放到别处），因此该项不作为完成判据——151 树同样没有却构建正常。

## 阶段 1：基线与回退点（清单第 1 项）

1. 在 `thorium` 与 `chromium-src`（151 树）各打 `baseline-M151-r3` tag；`chromium-src-155` 打 `baseline-M155-start`。
2. 快照 151 树状态到 `docs/dev-logs/m155-pre-upgrade-tree-state.txt`（`git status --porcelain -uno` + `git diff --stat`，沿用 M151 那次格式）。

## 阶段 2：部署定制（清单第 2–9 项）

3. `THOR_DIR=D:\wxmuma\thorium`、`CR_DIR=D:\wxmuma\chromium-src-155\src` 下运行 `python win_scripts/deploy_mcloud.py` —— 现在含 **7 步**（第 7 步 `apply_installer_payload.py` 是 D47 修复；`d47_probe.py` 已验证它对 M155 的 `chrome.release` 首次注入可用）。
4. 逐脚本确认输出：任一脚本报 `anchor not found` 即停下人工核对，禁止"顺手改锚点"跳过（这正是 M151 那次把 `setup.py` 全量覆盖废掉的原因）。
5. `copy_essentials.py` 仍只允许 `src/build/config/compiler_opt.gni` 一项入库（D41 白名单）；其余 `src/` 副本一律不参与构建，不要整份覆盖。
6. 放置 `win_args_mcloud.gn` → `out/mcloud/args.gn`，并把 `pgo_data_path` 改成阶段 0 表里的 8059 文件（**必须与内核大版本一致，否则 mksnapshot 拒绝**）。
7. `gn gen out/mcloud --check`，与 151 的输出做 diff，确认无未知参数告警（`use_polly`/`use_bolt` 仍为 false，`use_avx2`/`use_fma` 保持 true —— 项目铁律）。

## 阶段 3：flags 与性能项（用户两条硬要求）

8. **删除** `--enable-features=FlingSchedulingImprovements`（155 已无该 feature），并在 `mcloud_flags.txt` 变更记录里写明依据。
9. 跑 `python .bugreview/flag_stability.py`

   2026-10-10 预演证据（用项目自带工具，对两棵真实源码树各跑一遍）：
   `benchmark/tools/check_features.py --src chromium-src/src`（M151）→ **[OK] 53/53**；
   `--src chromium-src-155/src`（M155）→ **[OK] 52/53，唯一 NOT_FOUND 就是 FlingSchedulingImprovements**。
   也就是说 r3 清理后的 flags 文件在升级后只剩这一条已知失效项，其余 52 条在 155 上照常有效。（先把其中 `REV151/REV155/REV156` 集合改为 `[当前基线=155, 下一版=156]`）：要求全部条目 OK、且不存在"升级后新失效"条目。
10. 按 `docs/tasks/m155-perf-features.md` Tier A 逐条 A/B：一次只加 1 条 → 重新部署 flags → 采 K1/K2/K3-K7 ≥5 轮 → 与"去掉该条"的同构建基线对比；无收益或回退即撤回。内存类候选（`PartitionAllocAdaptiveMemoryReclaimInterval`）必须同时确认 K2 不劣化。
11. 谨慎项 `PrioritizeResizeTaskRunnerOnStartup` 启用前必须复现窗口拖拽/缩放场景（与 `docs/progress.md` 4.6 的 4 项永久禁用定案对照，勿顺手恢复任何被禁标志）。

## 阶段 4：编译与验证（清单第 11–12 项）

12. `autoninja -C out/mcloud chrome mini_installer`（首轮全量，参考 M151：54824 步；记录链接耗时）。
13. 冒烟：启动、视频硬解（HEVC/AC3/EAC3）、扩展（MV2 兼容）、DoH、下载 shelf。
14. `benchmark/tools/check_features.py` 49+ 项特性存活性；`benchmark/tools/verify_builtin_flags.ps1` 做 A6（子进程命令行内可见性）验证；注意测试脚本会临时替换 `out/mcloud/mcloud_flags.txt`，**不得与发布门禁并行**。
15. 基准回归 K1/K2/K7 对比 r3（当前 r3 参考值：K1 54 ms、K2 见 `docs/dev-logs/M151-benchmark.md`）。

## 阶段 5：发布（清单第 13–14 项 + D44/D45/D46 口径）

16. `.bugreview/refresh_release.py` 门禁全绿后复制发行包并写 sidecar（文件名沿用 `mcloud_<版本>_win64_mini_installer.exe`）。
17. **新建 `docs/superpowers/specs/<日期>-release-notes-m155.md`**（无后缀 tag 才会命中 `*m155.md`；已实测选择器：`v155.0.8059.40` 目前会退回到"最新日期文件"，若不新建就会把 r3 的正文发出去）。若走 `-rX` 后缀 tag，则命名 `…-m155-rX.md`。
18. 推送与打 tag 属对外发布：先过 L3 安全审查门禁并取得用户授权，commit 与 push 不得写在同一条命令里。
19. 资产 >100 MiB 不能入库，走 GitHub Release 资产上传（D45 现状未变）。
20. 升级报告归档 `docs/dev-logs/M155-upgrade-report.md`，CHANGELOG 增条，规范第 9 章清单回填本轮偏差（429 限流、jobs=4、DEPOT_TOOLS_UPDATE=0）。

## 验收标准

- `deploy_mcloud.py` 7 步在 155 树全部成功且可重复运行（幂等）。
- `flag_stability.py` 在 `[155, 156]` 集合下 PASS：每条 feature 声明存在，无"当前生效、升级后失效"的条目。
- 安装包 `chrome.7z` 载荷含 155 版 flags 文件（含 r3 清理标记 + 后续 Tier A 变更）。
- K1/K2 相对 r3 无回归（±3% 内）；A6 验证通过。
- 升级报告 + CHANGELOG + release notes 文件命名符合第 17 条。
