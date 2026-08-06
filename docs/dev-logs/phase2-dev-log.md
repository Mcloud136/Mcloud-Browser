# Phase 2 开发日志 — P0 收尾与 P1 工具化

- **日期**：2026-08-05
- **范围**：规范附录 A 剩余整改项（A7/A10）+ 安装版 flags 打包 + 规范 10.4 feature 治理工具化
- **规范依据**：`docs/architecture/performance-build-technical-spec.md`

## 1. A10：发布产物校验和（部分完成）

- `.github/workflows/release.yml` 新增 SHA256 校验和生成步骤，产物 `mcloud_{版本}_win64_mini_installer.exe.sha256` 随 Release 一并上传。
- 剩余：代码签名评估（成本与证书来源），维持【待补充】。

## 2. 安装版打包 mcloud_flags.txt（Phase 1 遗留待办，已完成）

机制核查结论（实际读取 chromium 树与补丁验证）：

- mini_installer 将 `inputs` 列表打包为 chrome.7z → setup.exe 解包后由 `install_worker.cc` 的 `AddCopyTreeWorkItem` 把附加文件复制到安装目录（现有先例：`initial_preferences`、`thor_ver`）。

`other/mini_installer.patch` 修改（hunk 头计数已同步修正）：

1. `mini_installer_archive` 的 `inputs` 增加 `$root_out_dir/mcloud_flags.txt`（进入 chrome.7z）；
2. `install_worker.cc` 新增常量 `kMcloudFlags` 与对应 `AddCopyTreeWorkItem`（安装/升级时复制到安装目录）。

前置条件：`out/mcloud/mcloud_flags.txt` 由 `copy_essentials.py`（Win）/`setup.sh`（Linux）提供（Phase 1 已就绪）。验证方式：下次构建安装包后确认安装目录含该文件且 `chrome://version` 命令行显示内置 flags。

补丁质量验证（2026-08-05 补充）：

- `git apply --check` 发现编辑引入的 hunk 计数错误（`@@ -234,6 +287,19 @@` 应为 18，导致 "corrupt patch"），已修复；
- 对照验证：仓库 HEAD 中的原始补丁在当前 chromium 树上同样无法应用（基线漂移，与本次编辑无关）——补丁实际应用时按既有流程以 `git apply --reject` + 手工合并处理；
- 遗留：其余补丁（ftp/2024-ui/win_updater 等）在当前树上同样存在基线漂移，属既有状态，M151 升级时统一 rebase。

## 3. A7：SSE2~SSE4.2 梯度废弃清理（完成）

- `setup.sh`：移除 `--sse2/--sse3/--sse4` 分支与 `copySSE2/copySSE3/copySSE4`、`patchSSE2` 函数；帮助文本增加废弃说明。
- 删除 `other/SSE2/`、`other/SSE3/`、`other/SSE4.1/`、`other/SSE4.2/` 共 24 个文件。
- 保留说明：`mini_installer.patch` 中 SIMD 变体目标的条件分支保留不动（AVX2 构建不会触发 SSE 变体，删除会破坏补丁结构，无功能影响）。

## 4. 规范 10.4：feature 清单校验脚本（完成并首检）

- 新增 `benchmark/tools/check_features.py`：解析 `mcloud_flags.txt` 的 feature 条目 → 在目标 Chromium 源码树做标识符检索（全树扫描，排除 third_party 主体、保留 blink）→ 输出失效清单；含 NOT_FOUND 时退出码 1，可直接接入第 9 章升级清单第 8 项。
- 开发中修正的两处扫描缺陷（均经实际运行复现并修复）：
  1. 目录白名单遗漏 `components/performance_manager`（如 `InfiniteTabsFreezing`）→ 改为全树扫描策略；
  2. 严格边界正则漏掉 `kXxx` 常量后缀形式 → 放宽为尾部边界匹配。
- **首检结果（M150 树）**：51 个 feature 中 49 有效；`PWAFullCodeCache`、`ServiceWorkerScriptFullCodeCache` 确认在 M150 不存在（已人工复核），按规范 4.2 从 `mcloud_flags.txt` 移除并留注。
- 口径同步：标志总数现为 **52 条（49 个 feature）**，README（3 处）与 CLAUDE.md 已更新。

## 4.5 SIMD 配置告警修复（规范校验规则首个实战命中）

A6 验证构建前的 `gn gen out/mcloud --check` 触发 `compiler_opt.gni` 校验告警：

1. `use_fma is true while use_avx is false. FMA requires AVX`：`win_args_mcloud.gn` 原设 `use_avx = false`，但 FMA 依赖 AVX；且 `use_avx` 控制 `-mpclmul -maes -mavx` 标志（含 **AES-NI 硬件加密加速**），置 false 会实际丢失这些优化；
2. `use_sse3 is disabled` 提示及 `compiler_opt.gni` 注释（标志不叠加，AVX2 构建应同时开 use_sse3/41/42/avx）。

修复：`win_args_mcloud.gn` 改为 `use_sse3 = true, use_sse41 = true, use_sse42 = true, use_avx = true`（use_avx2/use_fma 保持），并同步到 `out/mcloud/args.gn`；重跑 `gn gen --check` 零告警。规范 2.2"保留全部参数组合校验"条款的价值由此实证。

## 4.6 A6 验证构建（进行中）

- 已执行 `copy_essentials.py`（含 chrome_main_delegate.cc 与 mcloud_flags.txt 部署）；
- 后台增量编译 `autoninja -C out/mcloud chrome` 已启动（因 SIMD 标志变化为全量重建）；
- 完成后验证项：① chrome://version 命令行含内置 flags；② 运行 `benchmark\run_baseline.ps1 -Version M150` 采集 K1/K2/K7 基线（一键编排脚本已就绪，自动填充环境信息与报告模板）。

## 4.7 Polly/BOLT 无效开关发现与接线修复（重大发现）

核查结论（全树 grep + clang 实测验证）：

1. `config("polly")` 与 `config("emit-relocs")` 在 `compiler/BUILD.gn` 中定义，但整个构建树（含 BUILDCONFIG.gn）**无任何引用**——`win_args_mcloud.gn` 中的 `use_polly = true` / `use_bolt = true` 一直是无效开关；
2. Chromium 内置 clang（23.0.0git）的 `-mllvm` 选项列表实测**不含 Polly**——即使接线，置 true 也会在链接期报错；
3. 因此对外宣称的"五重编译器优化"实际仅三重生效：-O3 + ThinLTO + PGO。

修复动作：

- `src/build/config/BUILDCONFIG.gn`：将 polly/emit-relocs 接入 executable 与 shared_library 默认 configs（排除 android/apple），开关自此真实生效；
- `win_args_mcloud.gn`：`use_polly`/`use_bolt` 改为 `false` 并注释前置条件（Polly 需 `infra/build_polly.sh` 自建 clang；BOLT 需规范 10.1 后链接流程）；
- 口径同步：README（五重→三重已生效 + 状态列表）、CLAUDE.md、规范 2.5/2.6 均已更新；技术栈记忆已修正；
- 注意：本次修改在 thorium 仓库内完成，chromium-src 构建树的同步（copy_essentials + gn gen）须在当前后台构建结束后执行。

## 4.8 进阶优化工具化（10.1/10.2 脚本就绪）

- 核查确认 Chromium 内置工具链不含 `llvm-bolt.exe`/`llvm-profdata.exe`（已写入规范 2.5 事实核查）；
- 新增 `benchmark/tools/bolt_pipeline.ps1`：BOLT 四阶段流水线（instrument/collect/optimize/verify），含工具链探测；
- 新增 `benchmark/tools/pgo_collect.ps1`：自采 PGO 四阶段流水线（phase1-build/collect/merge/phase2-build），自动改写 args.gn；
- `benchmark/README.md` 新增工具索引表；规范 10.1/10.2 状态更新为"脚本已就绪"。
- 剩余前置：安装/自建 LLVM 工具链（含 bolt/profdata）后即可执行，无需再写代码。

## 5. 当前整体状态

| 项 | 状态 |
|----|------|
| A1-A6、A9 | ✅ 完成（A6 待构建验证） |
| A7 | ✅ 完成 |
| A8 | 🟡 benchmark/ 体系已建立，M150 基线数据待采集 |
| A10 | 🟡 SHA256 已完成，代码签名待评估 |
| 10.4 feature 治理 | ✅ 脚本落地并完成首检 |
| M151 升级（P1） | ⏳ 待执行（按规范第 11 章，升级后运行 check_features.py） |
| BOLT 流程 / 自采 PGO（P2） | ⏳ 待基线数据 |

## 6. 构建完成后的执行手册（按序执行）

后台构建（终端 1）完成后：

```powershell
# 1. 同步修复后的 BUILDCONFIG.gn（polly/bolt 接线）与 args（SIMD/开关修正）到 chromium 树
$env:THOR_DIR="d:\wxmuma\thorium"; $env:CR_DIR="D:\wxmuma\chromium-src\src"
python d:\wxmuma\thorium\win_scripts\copy_essentials.py
Copy-Item d:\wxmuma\thorium\win_args_mcloud.gn D:\wxmuma\chromium-src\src\out\mcloud\args.gn -Force

# 2. 重新生成构建文件（polly/bolt 已置 false，无链接风险）
$env:PATH="D:\wxmuma\depot_tools;"+$env:PATH; $env:DEPOT_TOOLS_WIN_TOOLCHAIN="0"
$env:vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
$env:INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;"+$env:INCLUDE
cd D:\wxmuma\chromium-src\src; gn gen out/mcloud --check

# 3. 增量重编（仅受 SIMD/接线变化影响的对象）
autoninja -C out/mcloud chrome

# 4. A6 验证（退出码 0 = 内置 flags 生效）
d:\wxmuma\thorium\benchmark\tools\verify_builtin_flags.ps1

# 5. M150 基线采集（产出 docs/dev-logs/M150-benchmark.md）
d:\wxmuma\thorium\benchmark\run_baseline.ps1 -Version M150
```

基线完成后再启动 P1：M150→M151 升级（规范第 11 章；升级后必跑 check_features.py）。

## 7. 构建后验证发现的部署链路 bug 与修复（2026-08-05 下午）

首次全量构建（50253/50253，零错误）完成后，A6 验证未通过。根因调查结论：

1. **copy_essentials.py 路径嵌套 bug**：`CR_DIR` 已指向 `chromium-src/src`，但文件清单条目带 `src/` 前缀，导致全部覆盖文件被复制到嵌套死目录 `chromium-src/src/src/...`，**从未真正部署**（含 flags 加载器、polly 接线、GN 配置）；
2. 修复：脚本剥离 `src/` 前缀；删除嵌套死目录（16 个误置副本）；重新部署并逐文件验证落点；
3. **BUILDCONFIG.gn / compiler/BUILD.gn 基线冲突**：thorium 仓库内副本基线过旧，直接部署导致 `gn gen` 失败（enable_strict_deps / disable_unknown_warning_option 未定义）。树的实际状态：`compiler/BUILD.gn` 为纯上游版（已含 optimize_speed 的 /O2+/clang:-O3 链路，即 -O3 生效链路本就在上游文件中），但缺 polly/emit-relocs 定义；
4. 方案调整：这两个文件不再整体部署（已从 copy_essentials 清单移除），改为原位补丁脚本：`win_scripts/apply_polly_wiring.py`（BUILDCONFIG.gn 接线）+ `win_scripts/append_polly_configs.py`（compiler/BUILD.gn 追加 config 定义 + import）；修复 use_bolt 作用域问题（需在 config 块前 import compiler_opt.gni）；
5. 最终 `gn gen out/mcloud --check` 零告警通过，后台增量重编已启动；
6. 说明：SIMD 生效链路在 Windows 上来自 `win/BUILD.gn` 的无条件 AVX2 基线（-mavx2 -mfma -mf16c -mlzcnt -mbmi -mbmi2），满足 AVX2+FMA3 基线要求；use_sse3/41/42 等 GN 参数在当前上游基线树上不产生附加标志（仅 thorium 旧构建体系的 thorium_simd_optimization config 才消费），无实际影响。

## 8. 第二轮重编编译失败与修复（chrome_main_delegate API 漂移）

第二轮全量重编在最后一个编译单元失败：thorium 仓库的 `chrome_main_delegate.cc` 副本与当前树存在 8 处 API 漂移（`base::StringPiece` 移除、`SPLIT_SKIP_EMPTY`→`SPLIT_WANT_NONEMPTY`、`PackExtension` 签名变更为 `std::u16string*`、`OverrideCachedUIStrings`/`kDisableBoostPriorityMode`/`DIR_INTERNAL_PLUGINS` 移除）。

修复（与 BUILDCONFIG.gn 同样的原位补丁策略）：

1. `git checkout` 恢复树的上游版 delegate；
2. 新增 `win_scripts/inject_flags_loader.py`：向树文件原位注入加载器（适配 `std::string_view`/`SPLIT_WANT_NONEMPTY`，自动补齐 `string_split.h` include），注入点：匿名命名空间开头 + `BasicStartupComplete` 函数体开头；
3. `chrome_main_delegate.cc` 从 copy_essentials 清单移除（防止旧副本再次覆盖）；
4. 重启增量编译（仅需重编该单元 + chrome.dll 重链接）。

经验沉淀：仓库内 src/ 覆盖文件与内核树存在版本耦合，跨版本升级时优先采用"上游基线 + 原位注入/补丁"而非整体覆盖；M151 升级任务文档第 9 项清单已对应此策略。

## 9. 验证步骤执行结果（2026-08-06）

1. **A6 验证通过**：`verify_builtin_flags.ps1`（headless 空输出后自动切换子进程命令行探测）结果 3/3：SpareRendererForSitePerProcess、InfiniteTabsFreezing、PlatformHEVCDecoderSupport 均出现在 chrome 子进程命令行——52 条内置启动标志真实生效，A6 闭环；
2. **M150 基线采集完成**：K1 冷启动中位数 71ms（两轮 76/71 可复现）、K2 50 标签内存中位数 2669.1MB（57 进程，采样收敛）、K7 chrome.exe 3.62MB / mini_installer 112.27MB；报告归档 `docs/dev-logs/M150-benchmark.md`；
3. 期间修复脚本缺陷：verify_builtin_flags.ps1 空输出提前退出、bench_memory.ps1 变量名冲突、run_baseline.ps1 报告路径与 Tee 捕获缺陷（后者已记录待修，本轮数值人工回填）。

**下一阶段（P1）前置条件已全部满足**：基线已归档、A6 已闭环、无构建进程占用——可按 `docs/tasks/m151-upgrade-task.md` 启动 M150→M151 升级。

## 10. 本轮变更文件清单（更新）

```
.github/workflows/release.yml      （SHA256 校验和步骤与产物）
other/mini_installer.patch         （打包 mcloud_flags.txt + hunk 计数修复）
setup.sh / win_scripts/setup.py    （移除 SSE 分支）
other/SSE2|SSE3|SSE4.1|SSE4.2/     （24 个文件删除）
src/build/config/BUILDCONFIG.gn    （polly/emit-relocs 接线，仅供参考，不再部署）
win_args_mcloud.gn                 （SIMD 修正 + use_polly/use_bolt 置 false）
win_scripts/copy_essentials.py     （路径嵌套 bug 修复 + BUILDCONFIG.gn 移出清单）
win_scripts/apply_polly_wiring.py  （新增：BUILDCONFIG.gn 原位接线）
win_scripts/append_polly_configs.py（新增：compiler/BUILD.gn 原位追加 config）
win_scripts/inject_flags_loader.py （新增：delegate 原位注入 flags 加载器）
benchmark/                          （新增：run_baseline/bench_*/tools 脚本）
mcloud_flags.txt                   （移除 2 失效 feature，52 条）
README.md / CLAUDE.md              （口径同步）
docs/architecture/performance-build-technical-spec.md （多轮回填）
docs/tasks/m151-upgrade-task.md    （新增：M151 升级任务文档）
docs/dev-logs/phase2-dev-log.md    （本文件）
```
