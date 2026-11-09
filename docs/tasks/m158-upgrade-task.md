# M158 内核升级执行任务单（M155.0.8059.40 → M158 Beta）

- **制定日期**：2026-11-08
- **决策依据**：用户 2026-11-08 指定「选 C，现在升到 M158 内核；下一次升级等 M159/M160 GA」。即**本次破例取 Beta**，之后回到跟 GA 的攒批口径（已回填技术规范 §9.1）。
- **目标版本**：`158.0.8127.30` —— Chromium **官方 git tag 列表**里 `158.0.8127.*` 系列的最新补丁 tag（用户 2026-11-08 指正）。`git ls-remote --tags https://chromium.googlesource.com/chromium/src.git 'refs/tags/158.0.8127.*'` 实测 `.4` … `.30`，最大为 `.30`；tag 解析到 commit `cb5de443be0ab0b6595c6f73c66b7bfeb017ef8a`；官方 `chrome/VERSION` = `MAJOR=158 / MINOR=0 / BUILD=8127 / PATCH=30`。
  - ⚠ **口径说明**：ChromiumDash `fetch_releases?channel=Beta` 返回的 `158.0.8127.18` 是**推送到 Beta 频道的版本**，不是源码 tag 列表顶端。按技术规范 §9.1「取稳定分支最新补丁 tag」与用户指定，本轮目标为 `.30`。
  - ⚠ 仍是**远程文本取证**，首次拿到本地 M158 树后必须用 `git describe --tags` 复核；Chrome Status 标注 158 计划 2026-11-17 转 Stable。
- **状态**：**仓库侧配置已就绪；源码拉取 / 注入 / 全量编译 / 打包 / 干净安装复验尚未执行**。

---

## 0. 环境事实与交付边界（先读）

| 事实 | 证据 | 后果 |
|---|---|---|
| 本机只有 M151（`chromium-src`）与 M155（`chromium-src-155`）两棵树 | `chrome/VERSION` 实测 151.0.7922.99 / 155.0.8059.40 | **没有本地 M158 构建树**，profdata / V8 builtins profile / 编译产物仍须在构建机生成 |
| **Chromium 官方源可达**（更正：早前一次 HTTP 000 是临时故障） | `chromium.googlesource.com/chromium/src/+/refs/tags/158.0.8127.30/<path>?format=TEXT` 返回 200；官方 `chrome/VERSION` 已核实 | 已完成 8 处注入锚点、`-O3` 链路、关键 feature 声明的**文本级取证**，见 §0.1 |
| **GitHub 镜像不作判据** | `chromium/chromium` 只镜像主 git 仓库；官方 `DEPS:3375-3376` 写明 `'src/v8': ...'/v8/v8.git@' + Var('v8_revision')` —— **v8 是 gitlink**，主树不含 v8 / third_party / CIPD / PGO profiles | V8 参数、profdata、工具链必须按 DEPS 单独取，不能从镜像推断 |
| 无 M158 profdata / V8 builtins profile | `chrome/build/pgo_profiles/` 只在真实树里 | **不得编造 8127 系列文件名**（D144：gn gen 过、ninja 才报 missing） |
| 全量编译约 3 小时 / 58,416 步 | M155 升级报告 | 必须在构建机上执行 |

⇒ 本任务单把**不依赖源码树**的部分全部做完（见 §1），把**依赖源码树**的部分列为待执行项并给出命令与判据。**没有本地 M158 树、没有编译产物之前，不得把任何数字（回显条数、pin 数、基准值）写成 M158 的实测值。**

### 0.1 官方源（Gitiles）文本级取证结果 —— 2026-11-08 晚间

取证命令：`curl -s ".../+/refs/tags/158.0.8127.30/<path>?format=TEXT" | python -c "import sys,base64; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))"`。**源为 Chromium 官方仓库，不是 GitHub 镜像。**

| 检查项 | 官方 tag 结果 | 对升级的意义 |
|---|---|---|
| `chrome/VERSION` | `MAJOR=158 / BUILD=8127 / PATCH=30` | tag 真实存在，`KERNEL_VERSION` 取值成立 |
| `chrome/app/chrome_main_delegate.cc` | `namespace {`(:285)、`std::optional<int> ChromeMainDelegate::BasicStartupComplete()`(:1194)、`content/public/common/content_switches.h`(:80)、`base/base_switches.h`(:107) | `inject_flags_loader.py` 4 类锚点全部保留 |
| `build/config/win/BUILD.gn` | `:123 cflags += [ "-msse3" ]` | `apply_avx2_baseline.py` 原锚点保留 |
| `media/base/media_switches.cc` | `:1617 BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_DISABLED_BY_DEFAULT);` | 与 D178 定案一致，`apply_mcloud_source_defaults.py` 的自愈分支会走 `[ok]`，无需翻转 |
| `chrome/browser/background/extensions/background_mode_manager.cc` | `:354 RegisterBooleanPref(..., true)`、`:640 SetBoolean(..., false)`；**与 M155 逐行一致（仅行号 351/622 → 354/640）** | 第一处注入可执行；第二处的目标态上游已是 `false`，`patch_file()` 的 `if new in s` 会 `[skip]`，**不会报 anchor not found** |
| `chrome/installer/mini_installer/chrome.release` | `:9 chrome.exe: %(ChromeDir)s\` | `apply_installer_payload.py` 锚点保留 |
| `chrome/browser/chrome_browser_main_win.cc` | `:1032 about_flags::RemoveFlagsSwitches(&switches);` | `apply_restart_cmdline.py` 锚点保留 |
| `build/config/BUILDCONFIG.gn` / `compiler/BUILD.gn` | `set_defaults(...)` 多处；`:2551 common_optimize_on_ldflags = []` | Polly 接线两处锚点保留 |
| `chrome/browser/net/.../default_dns_over_https_config_source.cc` | `:32 net::SecureDnsMode::kAutomatic` | DoH 无需修改，校验分支通过 |
| `-O3` 链路 | M155 `:2730` → M158 `:2781`，均为 `cflags += [ "/clang:-O3" ]` | **形态未变，仅行号漂移**；ADR-002 要求的 rebase 核对可判「无回退」 |
| M155→M158 新增 feature 声明 | 5 个性能关键文件 diff 出 30+ 条新增，含 11 个 Windows 默认禁用的性能向候选 | 详见 `docs/tasks/m158-perf-features-candidates.md` §2 |

**`.18` → `.30` 复核（2026-11-08 18:2x，用户指正后重跑）**：在 `.30` 上重取后确认——8 处锚点行号与 `.18` **逐项一致**（`chrome_main_delegate.cc` 80/94/107/285/1194、`win/BUILD.gn` 123、`media_switches.cc` 1617、`background_mode_manager.cc` 354/640、`chrome.release` 9、`chrome_browser_main_win.cc` 1032、`BUILDCONFIG.gn` 448、`compiler/BUILD.gn` 2551、DoH 32）；`-O3` 仍为 `:2781 cflags += [ "/clang:-O3" ]`；4 个性能关键文件的 `BASE_FEATURE` 声明集合**零差异**，16 个候选 flag 的默认值**零变化**。因此 `docs/tasks/m158-perf-features-candidates.md` 的结论直接沿用，只需替换 tag 号。

⚠ **效力边界**：以上是 Gitiles 的**文本级**证据，不等于本地构建树可用。注入器是「正文比对式」，仍需在真实树上实跑；`guard_audit.py` 需要 `out/mcloud` 才能判平台守卫与 buildflag 实际取值；profdata / V8 builtins profile / CIPD 工具链只能由 `gclient sync` 落地。**不得据此跳过阶段 1–4 的任何一步。**

---

## 1. 本轮已完成（仓库侧，可直接复现）

| 文件 | 改动 |
|---|---|
| `win_scripts/tree_check.py` | `KERNEL_MAJOR` 155→**158**、`KERNEL_VERSION`→`158.0.8127.30`、示例 `CR_DIR` 指向 `chromium-src-158`；加注释说明这是**预期的升级阻断**（旧树注入会 exit 114） |
| `win_args_mcloud.gn` | `pgo_data_path` 由写死的 8059 文件名改为占位符 `__M158_PROFDATA_REQUIRED__` + 完整说明。`build_win.py::preflight_args` 会在编译前硬失败并点名根因 |
| `win_scripts/resolve_pgo_profiles.py` | **新增**。扫描真实树 `chrome/build/pgo_profiles/chrome-win64-<BUILD>-*.profdata`，校验存在且非空，原子写回 `out/mcloud/args.gn`。已做 Green / Red 对照：正常解析并写入成功；build 号不匹配时 rc=2 且报「没有匹配且非空的 profdata」 |
| `docs/architecture/performance-build-technical-spec.md` §9.1 | 回填双周发布下的**攒批**口径 + 本次 Beta 抢跑的例外登记 + 下次锚定 159/160 GA |

**刻意没动的文件**（动了就会制造假绿或破坏发布链）：
- `mcloud_flags.txt` —— 发布载荷；存活性未取证前不改，且**改注释也会让 `release_chain_check.py` 红**（指纹三处不一致）。
- `.bugreview/flag_stability.py` —— 断言语义绑定 M151 基线，无 M158/159 tag 时改了**无法验证**，见 §5。
- `AGENTS.md` / `README.md` / `CHANGELOG` —— 里面全是 M155 实测数据，产物未出前回填会把旧数据写成新口径，见 §8。
- `docs/superpowers/specs/*release-notes*m158*.md` —— **现在绝不能建**。`release.yml` 的选择器按 tag 的 MAJOR 找 `*m158*.md`，建一个空模板就会取代正式发布说明被发出去。发布当天才建。

---

## 2. 版本绑定硬单点（漏一个 = 编译过但产物不含定制）

| # | 位置 | 要改成什么 |
|---|---|---|
| 1 | `win_scripts/tree_check.py` `KERNEL_VERSION` | 用真实树 `git describe --tags` 的结果定稿 |
| 2 | `CR_DIR` | **显式**设为 `D:\wxmuma\chromium-src-158\src`；默认值仍指向 M151 树（D186） |
| 3 | `win_args_mcloud.gn` → `out/mcloud/args.gn` 的 `pgo_data_path` | 跑 `python win_scripts/resolve_pgo_profiles.py --src <CR_DIR> --build 8127 --write <CR_DIR>/out/mcloud/args.gn` |
| 4 | V8 builtins profile | `python v8/tools/builtins-pgo/download_profiles.py download` + `validate --check-v8-revision`；M151 曾因缺 `x64-rl.profile` 被 mksnapshot 挡住 |
| 5 | `chrome_pgo_phase=2` 与 profdata BUILD 号 | 必须与 `chrome/VERSION` 的 BUILD 一致 |
| 6 | `v8/` 是 gitlink | `v8_enable_maglev/turbofan/fast_torque/wasm_simd256_revec` 与 4 个 `--js-flags` 参数要按 DEPS 固定的 v8 修订**单独核对**（`src/flags/flag-definitions.h`） |
| 7 | `.bugreview/flag_stability.py` 三版集合 | `151.0.7922.99 / 155.0.8059.40 / 156.0.8078.12` → **155 / 158 / 159**；且 A/B/C 断言语义整体重写，见 §5 |
| 8 | 发布说明文件名 | 发布当天新建 `docs/superpowers/specs/<日期>-release-notes-m158.md`（文件名必须含 `m158`） |
| 9 | 仓库副本 / `src/INVENTORY.md` | `python .bugreview/src_inventory.py --write` 重生成 |

---

## 3. 执行清单（阶段 0–6）

**阶段 0 · 源码与工具链**
1. 打回退点：`git -C thorium tag baseline-M155`；M155 树与其产物原样保留。
2. 新建独立第三棵树 `chromium-src-158`（**不要复用 M155 树**），定向浅拉取目标 tag；`gclient sync --shallow --jobs=4`（`--jobs=16` 实测 429）、`DEPOT_TOOLS_UPDATE=0`、`python3` 用 `mklink /H` 指向真实 Python。
3. 核对 `chrome/VERSION`、`clang-cl --version`（cr_build_revision 会跳变）、gn 2562 / ninja 1.12.1、DEPS 全量、V8 builtins profile、8127 profdata。
4. 用 `git describe --tags` 定稿 `KERNEL_VERSION`。

**阶段 1 · 部署定制**
5. `python win_scripts/deploy_mcloud.py`（8 步幂等）。任一脚本报 `anchor not found` **立即停下人工核对，禁止顺手改锚点跳过**（M151 教训）。
6. 逐脚本确认输出；`copy_essentials.py` 白名单仍只允许 `compiler_opt.gni` 一项（D41）。
7. `cp win_args_mcloud.gn out/mcloud/args.gn` → 立刻跑 §2 第 3 条的解析脚本填 `pgo_data_path`。
8. `gn gen out/mcloud --check`，与 M155 输出 diff：零未知参数告警；`use_avx2/use_fma=true`、`use_polly/use_bolt=false` 保持不变（项目铁律）。**按 ADR-002 逐一核对 `-O3` 生效链路**（`compiler/BUILD.gn` 约 3092-3100 / 2515-2550 / 2888-2927 行可能漂移）。

**阶段 2 · 注入锚点核对**（逐项 `git grep`/`git show`，方法见 `m155-upgrade-preassessment.md` §3）

| 上游文件 | 锚点 | 脚本 |
|---|---|---|
| `build/config/BUILDCONFIG.gn` | 两个 `set_defaults()` | `apply_polly_wiring.py` |
| `build/config/compiler/BUILD.gn` | `common_optimize_on_ldflags` | `append_polly_configs.py` |
| `build/config/win/BUILD.gn` | `cflags += ["-msse3"]` 块 | `apply_avx2_baseline.py` |
| `chrome/app/chrome_main_delegate.cc` | `namespace {`、`std::optional<int> ChromeMainDelegate::BasicStartupComplete() {`、5 个 include | `inject_flags_loader.py` |
| `chrome/browser/background/extensions/background_mode_manager.cc` | 两处 `RegisterBooleanPref(..., true)` / `SetBoolean(..., true)` | `apply_mcloud_source_defaults.py` |
| `media/base/media_switches.cc` | `BASE_FEATURE(kD3D12VideoDecoder, ...)`（churn 最高） | 同上 |
| `chrome/installer/mini_installer/chrome.release` | `chrome.exe: %(ChromeDir)s\` | `apply_installer_payload.py` |
| `chrome/browser/chrome_browser_main_win.cc` | `about_flags::RemoveFlagsSwitches(&switches);` | `apply_restart_cmdline.py` |

⚠ API 漂移先例：D41 中仓库旧副本与 M151 有 8 处 API 漂移，整份覆盖导致最后一个 TU 编译失败。**注入器是正文比对式，`anchor not found` 会硬失败（好事）；不要退回整份覆盖。**

**阶段 3 · flags 与门禁**
9. 先 `check_features.py --src <M158树>` 逐项存活性；再按 §5 重写 `flag_stability.py` 并跑 A–F。
10. `guard_audit.py --json g.json` 重算**平台有效默认值**与 pin 集合；`flags_lint.py --file mcloud_flags.txt --stab .bugreview/stab_158.json --guard g.json`。
11. `flag_runtime_state.py --chrome <安装版 chrome.exe>` 重新定回显期望值（当前 M155 是 `enable 50 / disable 2`，**M158 必然变化**）。
12. 顺序铁律：**C 断言证明存活 → 提交 → 基线跟上 → 复跑 A–F 全绿**。A/B 断言基线是 `git show HEAD:mcloud_flags.txt`，只改工作树不提交会一直红。
13. 新 flags 候选见 `docs/tasks/m158-perf-features-candidates.md`；**任何新增开启项都必须先过 C 断言 + guard_audit + 同机成对 A/B 才能写进 `mcloud_flags.txt`**，且注释必须独占一行（D59）。

**阶段 4 · 编译与验证**
14. `autoninja -C out/mcloud chrome mini_installer`（首轮全量，参考 58,416 步 / 约 3 小时；长链接不要在带 timeout 的前台命令里跑）。
15. 冒烟：启动、HEVC/AC3/EAC3 硬解、扩展商店、DoH、下载 shelf、拖拽+视频（4 项冻结缓解定案不得顺手恢复）。
16. 同机成对 K1/K2/K7 + K2-CPU + 泄漏探针 + GPU 三场（禁用 GPU / SwiftShader / 默认对照）。跨会话绝对值差可达 1.5%，**不得当收益**。
17. 按**核显**口径复核 `D3D12VideoDecoder`（绿屏）、`SkiaGraphite` 上游默认值、ANGLE 渲染路径（D178/D182）。

**阶段 5 · 发布**
18. `verify_sources.py` → `release_chain_check.py`（三处指纹一致）→ 打包（**只改暂存目录不重压 7z = 判据假绿**，D102）。
19. **干净安装复验四断言**：版本目录 flags 落地 / 与仓库字节一致 / 对安装后的二进制回显 / 根目录无残留 `mcloud_flags.txt`。命令：`mcloud_<ver>_win64_setup.exe --quiet --system-level`（rc=0）；卸载 `setup.exe --uninstall --system-level --force-uninstall`（rc=19）。
20. 只发 **setup 包装器**（D119：裸 mini_installer 在浏览器运行时静默不更新）+ SHA256；Roslyn csc `/deterministic`（旧 csc 走 exit 113）。发布当天才建 `…-release-notes-m158.md`。
21. 无自动更新 ⇒ 存量用户必须**手动重装**；发布说明要写明。

**阶段 6 · 归档**
22. `docs/dev-logs/M158-upgrade-report.md` + CHANGELOG + §8 口径回填 + 本任务单偏差登记。

---

## 4. flags 门禁：为什么 `flag_stability.py` 不能只换版本号

当前脚本 `.bugreview/flag_stability.py` 的断言语义是**围绕 M151 基线**写的：
- B：「r2 中被移除的每一条，在 **M151** 上都非 OK」→ 基线必须改成 M155；
- C：「每条 feature 在 **151/155/156** 三版均为 OK」→ 改成 155/158/159；
- `UPGRADE_MARKER = "FlingSchedulingImprovements"` 已在 M155 升级期删除，需清理；
- `DISABLE_EXCEPTIONS["SkiaGraphite"]` 的说明写「151/155/156 上游默认启用」，已被 **D178 翻案**（Windows 上上游默认即 DISABLED），必须一并更正；
- 取证仓库（`FLAG_STAB_TREE`，默认 M151 树）必须**同时含三个 tag 对象**；159 目前是 Canary，tag 可能取不到 ⇒ 需在报告里明确是「两版取证」还是等 159 Beta tag，不得静默少一版。

⇒ 这一步**必须在构建机上、拿到 158/159 tag 之后做**，且改完要能跑出 Green 与一次实测的 Red 才能算数。本机无 tag，故本轮未改。

---

## 5. 待回填口径清单（产物出来后逐项改，别提前改）

`AGENTS.md`（M155/155.0.8059.40/52 项/15 pin/35 真新增/`enable 50 / disable 2`/8059 profdata/`chromium-src-155` 路径/安装命令示例）、`README.md`（简介、56 条开关的过时口径、基准表、系统要求）、`CHANGELOG`、发布说明、`docs/progress.md`、`win_args_mcloud.gn` 注释里的 M155 字样、`.github/workflows/release.yml` 无需改（按 tag MAJOR 自动匹配）。

---

## 6. 风险与回退

- **版本风险**：158 是 Beta，11-17 才 GA；GA 后若上游继续出补丁 tag，本包会立刻落后。下一次按用户要求锚定 159/160 GA。
- **行为兼容**：156 IndexedDB→SQLite（新 data store）、157 Background Fetch 强制 CORS / FencedFrame 移除、**158 XSLT 在 Stable 停止工作**（老 RSS/XML sitemap/内网系统会显示裸 XML，OT/企业策略例外到 Chrome 176 / 2027-08-17）。冒烟要覆盖这些。
- **回退点**：`baseline-M155` tag + 原 M155 树与产物保留；`MCLOUD_ALLOW_TREE_MISMATCH=1` 只用于升级前取证，**不得用于发布构建**。

---

## 7. 验收标准

- `deploy_mcloud.py` 8 步在 M158 树全部成功且可重复运行（幂等），锚点无一被「顺手改」。
- `pgo_data_path` 指向真实存在且非空的 8127 profdata，`gn gen --check` 零未知参数告警。
- flags 门禁 A–F 全绿（且提交后复跑），`guard_audit` 52/52 ACTIVE，回显期望值已按 M158 重定。
- 干净安装复验四断言全过；发布链三处指纹一致；同机成对 K1/K2/K7 无回归（±3% 内）。
- 升级报告 + CHANGELOG + release notes（文件名含 `m158`）+ 口径回填完成。

---

## 8. 阶段 D 实编暴露的两个环境缺陷（2026-11-08 记录）

仓库侧已完整（`gclient_entries` 249/249 目录齐全、`src` 在 `cb5de443`、`gclient sync --jobs 8` rc=0/1431s/0 fatal），
两次「编译刚起步就 fail」都不是缺代码，而是构建机工具链配置：

**D-MM-SDK-INCLUDE —— vcvarsall 不注入 Windows SDK**
- 症状：`[1/59035]` 起就 `corecrt_terminate.h file not found` / `new.h file not found`，全落在 libc++。
- 根因：`build/toolchain/win/setup_toolchain.py` 的 `include_flags_imsvc` 与 link 的 `libpath` 完全由
  vcvarsall 的 `INCLUDE`/`LIB` 派生（第 308–357 行）。本机 VS18 BuildTools 的 `vcvarsall.bat amd64 <sdk>`
  实测对 **10.0.28000.0 与 10.0.26100.0 都只输出 MSVC 三条**（MSVC/include、MSVC/ATLMFC/include、
  VC/Auxiliary/VS/include），没有任何 `Windows Kits` 条目 —— SDK 装得是全的（Include/Lib 的
  ucrt/um/shared/winrt/cppwinrt + x64 库都在），只是 vcvars 没吐出来。
- 修法：`chromium-src-158/build_env.sh` 预置完整 `INCLUDE`/`LIB`（vcvarsall 是前置不是覆盖，实测
  自置的 atlmfc 条目会原样保留在后面）。修后 `rule cxx` 的 `-imsvc` 由 3 条变 11 条、
  `toolchain.ninja` 出现 35 处 `ucrt`、link `-libpath` 由 2 条变 6 条。
- 教训：**`gn gen` 成功 ≠ 工具链正确**。判据要落在 `out/*/toolchain.ninja` 里 grep `ucrt` 与
  `-libpath:...Kits`，而不是看 gn gen 的退出码。

**D-MM-ACL-UTF8 —— icacls 中文输出按 UTF-8 解码**
- 症状：`obj/build/config/win/acls.stamp` 失败，`UnicodeDecodeError: 'utf-8' codec can't decode
  byte 0xd2 in position 626`，ninja 在第 5 个 target 停止。
- 根因：`testing/scripts/common.py::set_lpac_acls` 用 `universal_newlines=True` 读 `icacls` 输出，
  解码依赖 Python 默认编码；构建用 `third_party/cpython3/host` 是 3.11.9 且 `sys.flags.utf8_mode=1`，
  中文 Windows 的 icacls 本地化输出是 CP936 ⇒ 严格解码必炸。M155 未炸是因为当时该 python 走 locale 编码。
- 修法：该处 `check_output` 加 `errors='replace'`（ACL 有效内容是 ASCII 的 SID+权限串，
  非 ASCII 只出现在目录名等无关文本，不影响 `CORRECT_ACL_VARIANTS` 匹配）。
- 备注：属上游在 CJK locale 下的真实缺陷，补丁带注释，重装/换树时需一并重放。

---

## 9. 阶段 D 完成 + 打包（2026-11-09 04:36）

**结果**：全量编译 53,349 条边全部成功（RC=0），`chrome` 与 `mini_installer` 均产出。

| 产物 | 大小 | FileVersion |
|---|---|---|
| `chrome.dll` | 315,154,432 B | 158.0.8127.30 |
| `chrome.exe` | 4,068,864 B | 158.0.8127.30 |
| `mini_installer.exe` | 134,298,112 B | 158.0.8127.30 |
| `setup.exe` | 7,039,488 B | 158.0.8127.30 |

安装载荷核对：`Chrome-bin\158.0.8127.30\mcloud_flags.txt` 存在（20,377 B），
即 D105 认定的「版本目录整目录搬迁」路径，不是根级登记。

**打包**（`.bugreview/package_m158.py`）：门禁全绿（dll 加载器证据 / flags 一致 /
chrome.release 登记 / 暂存目录=载荷真身 / mtime 链）。

| 发布物 | 大小 | SHA256 |
|---|---|---|
| `mcloud_158.0.8127.30_win64_mini_installer.exe` | 134,298,112 | `ee428235…1d2d69fd` |
| `mcloud_158.0.8127.30_win64_setup.exe` | 134,325,248 | `c570f9b4…a7cd90` |

### 新增缺陷 D-MM-SDK-BIN（PATH 缺 Windows SDK bin）

- **症状**：`FAILED: obj/.../Vulkan.res`，`rc.py` 抛
  `FileNotFoundError: [WinError 2]`。
- **根因**：`build/toolchain/win/rc/rc.py:263` 用 `subprocess.call(['rc', ...])`
  调用**真 MS rc.exe** 做 `.res` 交叉校验，只认 PATH 不给绝对路径；而本机
  `vcvarsall` 的 `%WindowsSdkVerBinPath%` 为空，它往 PATH 里塞的是字面量
  `bin\x64`（在 `out/mcloud/environment.x64` 里可见），SDK 的 bin 目录从未进入。
- **与 D-MM-SDK-INCLUDE 同源**：上次只补了 INCLUDE/LIB，漏了 PATH。
- **修法**：`build_env.sh` 与 `build_m158.bat` 都前置 SDK bin；PATH 是冒号分隔，
  必须写 `/c/Program Files...` 形式（写成 `C:/...` 会在盘符冒号处被切断）。
  改完必须重跑 `gn gen` 让 `environment.x64` 重新快照。
- **判据**：`environment.x64` 里出现 `...\Windows Kits\10\bin\10.0.28000.0\x64`；
  单目标 `ninja -C out/mcloud obj/.../Vulkan.res` 返回 0。

### 链接期 lld-link 偶发崩溃（未改配置）

- **症状**：`LINK(DLL) chrome.dll` 时 `lld-link.exe` 异常码 `0xC0000005`，
  栈回溯 15 层，无任何 OOM 文本。
- **判别**：环境干净时单独重试 **9m23s 成功**，产物 315 MB。故判定为**偶发**——
  当时 32 个 `clang-cl` 正在收尾、链接同时启动，瞬时内存峰值叠加。
- **未做改动**：`/opt:lldltojobs=all`（`build/config/compiler/BUILD.gn:829`，
  上游硬编码、无 GN 开关）保持原样。若复现再降到 8–12。
- **实测峰值**：lld 工作集 12.4 GB，提交 27.0/61.1 GB，物理空闲最低 5.2 GB。

### 中断残留文件范式（贯穿本周期）

被中断那一刻正在写的产物（`.rsp` / `.obj.tmp` / `.rcgu.bc` / `.rlib.d`）会进入
「能读、能改名、不能覆写也不能删」的状态，ACL/SDDL/属主/属性全部正常。
**唯一有效解法是改名**（`unstick.py`，`O_WRONLY` 探测 + 改名 `.stuck`），
ninja 视输出缺失从而重建。该步骤已内置到 `build_m158.bat`。

⚠ **禁止用 `echo x >` 探测真实构建产物的可写性**——本周期因此写坏了
`obj/skia/*.rlib`，导致 `E0786: invalid metadata for crate skia_rust_common`，
最终不得不清空 `obj/`+`gen/` 重编。探测请用 `O_WRONLY` 打开后立即关闭。

⚠ **删 `out/mcloud/obj` 会连带删掉 gn 生成的 `obj/**/*.ninja`**（`subninja` 引用），
删完必须 `source build_env.sh && gn gen out/mcloud`，否则报
`loading 'obj/apps/apps.ninja': 找不到路径`。

### 待办
- 干净安装四断言（会覆盖现有 155 系统级安装，需单独确认）
- 对外 push / tag（需单独授权；任务单第 18 条要求 L3 安全审查）

---

## 10. 安装器旧版本目录策略：B + A（2026-11-09 04:46）

**背景**：用户提出「安装包能否直接清理与自身版本不一致的其他版本号目录」。

**代码事实**：上游 `delete_old_versions.cc:237` 的 `DeleteOldVersions()` **本来就在做**——
枚举 `Application\` 直属子目录，保留「名字可解析为 **4 段**版本号」且「不等于
`chrome.exe` / `new_chrome.exe` 文件版本」的项，三趟删除（无匹配 exe 的目录 /
无匹配目录的 exe / 成对）。判据不比对安装包版本。失败唯一实质原因是**文件被占用**；
上游对此的应对是等：`install.cc:517` 失败即起后台 `setup.exe --delete-old-versions`，
`setup_main.cc:461` 最多重试 3 次（先等 15 秒，之后每次隔 5 分钟，约 10 分钟窗口）。

**决策：不重写删除逻辑**，采用 B + A：

- **B（已有）**：`mcloud_setup.cs` 主流程在调 `mini_installer` 前执行
  `OurBrowserProcesses(appDir)` + `CloseInstances()`，且**按安装路径**识别实例
  （不按进程名），因此从 `Application\<旧版本>\chrome.exe` 启动的实例会被关闭，
  让上游第一次删除就能成功。
- **A（本次新增）**：`ReportStaleVersionDirs(appDir, wantVersion)` —— 安装后扫描
  `Application\` 下仍存在的四段版本目录（额外要求目录内含 `chrome.dll`，防误判），
  逐个打印路径与体积，并提示「后台会继续清理；10 分钟后仍在就再跑一次安装器」。
  **明确不参与失败判定**（与 D109 同一条取舍：不能让无关残留卡住升级）。
  UI 完成语在 `ok && staleDirs > 0` 时变为「完成：已更新到 X（旧版本目录后台清理中）」。

**未采用**：wrapper 自写删除。风险为：删掉正在运行的那份导致浏览器崩溃、误删非本产品目录、
并发安装互相破坏、失去回滚点。若后续确需强制当场清理，必须先实现「按进程占用判断 +
严格路径白名单 + 尊重 SetupSingleton」三条防线，并保留一次改名备份。

**附带修复**：`win_scripts/build_setup_exe.py` 的编译命令补 `/codepage:65001`。
`installer/mcloud_setup.cs` 是 UTF-8 无 BOM 且含大量中文界面文案；不显式声明代码页时，
Roslyn 会先试 UTF-8（本机结果正确），但旧 Framework 编译器按 ANSI/GBK 读会把中文读成乱码，
而乱码只体现在安装器界面上、构建与哈希全部"正常"。锁定 65001 后：正常产物不变，
源码若不是合法 UTF-8 则直接编译失败。

**验证**：`MCloud-Setup-console.exe --list-only` 界面中文正常、退出码 0；
新增三处文案（`旧版本目录仍在` / `旧版本目录后台清理中` / `旧版本目录未被清理`）在
两份产物中均以 UTF-16 存在（第三处为编造的对照串，正确缺失）。
**未执行** `.bugreview/setup_wrapper_test.py`——该测试会先装 151 再卸载，属破坏性端到端，
需单独授权。

**发布物变化**（仅 setup 包装器，mini_installer 未变）：

| 发布物 | 大小 | SHA256 |
|---|---|---|
| `mini_installer.exe` | 134,298,112 | `ee428235…1d2d69fd`（不变） |
| `setup.exe` | 134,325,760 | `d9661d57…9bd3b955`（+512 B，原 `c570f9b4…`） |

---

## 11. 层一品牌文案落地 + xtb 数字 ID 陷阱（2026-11-09 05:36）

**背景**：关于页长期显示 `Chromium` / `The Chromium Authors`。核查确认这**不是** M158 回归：
`deploy_mcloud.py` 的 `STEPS` 里从来没有品牌/文案步骤，`infra/BRANDING` 与
`infra/mcloud_strings.grd` 只是死素材，M155 树内同样 0 命中——即从未实现过。

**决策**：只做「层一」（改 UI 文案），不做「层二」（改 BRANDING）。层二会改变安装子目录、
注册表键、卸载项，使新包与已装版本成为两个产品并存，须另立迁移方案。
`chrome/app/theme/chromium/BRANDING` **未改动**。

### 改动（`git diff` 恰好 3 行）

| 文件 | 变量 | 改为 |
|---|---|---|
| `chrome/app/chromium_strings.grd` | `IDS_PRODUCT_NAME`（非 testing 分支） | `Mcloud` |
| `chrome/app/chromium_strings.grd` | `IDS_ABOUT_VERSION_COPYRIGHT` | `Copyright <ph YEAR> Mcloud. All rights reserved.` |
| `chrome/app/resources/chromium_strings_zh-CN.xtb` | 中文版权 | `版权所有 <ph YEAR /> 狗木马` |

年份保留 `{0,date,y}` 运行时占位符：今天渲染 2026，明年自动变 2027。

### 陷阱：改英文原文会静默丢弃中文翻译

`.xtb` 的 `<translation id="…">` 里的数字 **不是** 稳定 key，而是**英文原文的哈希**：

```
id = grit.extern.tclib.GenerateMessageId(可呈现文本, meaning=None)
可呈现文本里 <ph name="YEAR">…</ph> 渲染成占位符名 "YEAR"
```

实测标定（两组均与现网 xtb 完全吻合）：
- `'The Chromium Authors'` → `985602178874221306`
- `'Copyright YEAR The Chromium Authors. All rights reserved.'` → `8586442755830160949`

因此把英文改成 `Copyright YEAR Mcloud. All rights reserved.` 后，ID 变为
**`8967849939165870724`**；若不同步改 `.xtb` 的 id，grit **不报错、不告警**，直接回退英文。
构建成功、哈希正常、只有关于页退回英文——第一版就是这么踩的，靠对比 `branded_strings_zh-CN.pak`
里 14,751 个汉字但唯独缺这一条才发现。

**修法**：`apply_branding_strings.py` 内置 `compute_message_id()`，从改后的英文反算 id，
再整条重写 `<translation>`。换树/换内核/上游改措辞都不会再丢。

### 配套

- 新增 `win_scripts/apply_branding_strings.py`（幂等：重跑报「已是最新 1 处」、自检 PASS）
- 纳入 `deploy_mcloud.py` 的 `STEPS`，下一次升级不会漏
- `build_setup_exe.py` 编译命令补 `/codepage:65001`：源码 UTF-8 无 BOM 且含中文界面文案，
  不锁代码页时旧编译器按 ANSI/GBK 读会得到乱码，而乱码只体现在界面上、构建与哈希全"正常"

### 验证与产物

- `gen/chrome/branded_strings_zh-CN.pak`：`狗木马`/`版权所有` 在，英文版权不在
- `locales/zh-CN.pak`：同上；`locales/en-US.pak`：`Copyright {0,date,y} Mcloud. All rights reserved`
- 增量重建 241 边、RC=0、FAILED=0（05:35:39）
- ⚠ 本轮已装机验证的是**改前**的 158；改后版本需重装才能看到关于页变化

| 发布物 | 大小 | SHA256 |
|---|---|---|
| `mini_installer.exe` | 134,295,040 | `0cae250a…f6c99446` |
| `setup.exe` | 134,322,688 | `3f917e54…3e21fb89` |

### 顺带确认（用户问过的旧版本清理）

本机 `C:\Program Files\Chromium\Application\` 现只剩 `158.0.8127.30`，
`155.0.8059.40` **已被上游 `DeleteOldVersions` 删除**——即安装器升级与旧目录清理实测有效。

---

## 12. DoH 默认不生效的根因与修法（2026-11-09 06:00）

用户问「怎么测 DNSPod / 阿里云 DoH 是否生效」，实测过程中发现**加提供方条目 ≠ 默认走 DoH**。

### 实测四组对照（判据看 netlog 的 `DNS_CONFIG_CHANGED` 事件）

| 模式 | `kDnsOverHttpsTemplates` | 系统 DNS | netlog 结果 | 是否走 DoH |
|---|---|---|---|---|
| `automatic` | 空 | 路由器 `192.168.1.1` | `mode=1, servers=[]` | **否** |
| `automatic` | `https://doh.pub/dns-query` | 路由器 | `mode=1, servers=[{doh.pub}]` | **是** |
| `secure` | `https://doh.pub/dns-query` | 路由器 | `mode=2, servers=[{doh.pub}]` | **是** |

### 根因

`kAutomatic` 单独存在时**不会**启用 DoH。自动升级只认一条判据——
`net/dns/public/doh_provider_entry.h:30-34`：条目必须有非空 `dns_over_53_server_ip_strs`
或 `dns_over_53_tls_hostnames`，**且系统 53 端口 DNS 的 IP 命中该列表**。

我们加的 DNSPod（`119.29.29.29`/`119.29.28.28`）、Aliyun（`223.5.5.5`/`223.6.6.6`）
条目本身齐全，但用户接路由器上网（DNS=`192.168.1.1`），永远不满足命中条件。

**注意：M158 已移除 `--dns-over-https-*` 命令行开关**（`grep -rn "dns-over-https"`
在 `chrome/ net/ content/ services/` 下无命中），只能用配置项控制，命令行传参会被静默忽略。

### 修法（已写入 `apply_mcloud_source_defaults.py`）

`chrome/browser/net/default_dns_over_https_config_source.cc` 加：

```cpp
localServer->SetDefaultPrefValue(prefs::kDnsOverHttpsTemplates,
                                 base::Value("https://doh.pub/dns-query"));
```

**保持 `kAutomatic` 不变**，只补默认模板。取舍：默认就走 DoH，且 DoH 不可用时
自动回退明文，不像 `secure` 那样直接断网。换阿里云只改这一行 URL。

### 用户侧验证（已确认生效）

用户在 GUI 里手动选了 DNSPod，`Local State` 写入
`{"mode":"secure","templates":"https://doh.pub/dns-query"}`。关掉代理后
`doh.pub` 解析为 `1.12.12.12` / `120.53.53.53`，用已装二进制跑并高频 `netstat` 采样，抓到：

```
TCP 192.168.1.38:17367  1.12.12.12:443    ESTABLISHED
TCP 192.168.1.38:43093  1.12.12.12:443    ESTABLISHED
TCP 192.168.1.38:26601  120.53.53.53:443  TIME_WAIT
```

43 条采样命中，全部指向 DNSPod DoH 端点 ⇒ 网络层确证走 DoH。

### 方法论备注（本周期踩到的两个坑）

1. **负向对照不能用环回地址**：`https://127.0.0.1:9/dns-query` 会被 Chromium 直接判为
   无效模板而丢弃，页面照常加载，看起来像「secure 模式有回退」的假象。要用
   「公网可达但非 DoH 服务」的地址才有判别力。
2. **netlog 的 `--net-log-capture-mode=Everything` 仍不记录 DoH 请求事件**
   （无 `DOH_URL_REQUEST`），只能看到配置（`secure_dns_mode` / `doh_config.servers`）。
   要证明真实走向，得靠网络层采样（`netstat -ano` 高频轮询 + 目标 IP 匹配）。

---

## 13. 快捷方式名与产品名解耦（2026-11-09 06:00）

**症状**：层一改完 `IDS_PRODUCT_NAME` 为 `Mcloud` 后，桌面快捷方式变成
`C:\Users\Public\Desktop\Mcloud.lnk`（实测创建于 05:46）。用户要求快捷方式保持 `Chromium`。

**根因**：`chrome/installer/util/install_util.cc:583`

```cpp
std::wstring InstallUtil::GetShortcutName() {
  // IDS_PRODUCT_NAME is automatically mapped to the mode-specific shortcut name
  return installer::GetLocalizedString(IDS_PRODUCT_NAME_BASE);
}
```

**同一个字符串同时驱动「关于页产品名」与「快捷方式名」**，改一处必然牵动另一处。

**修法**：在同一注入脚本里把 `GetShortcutName()` 固定返回 `L"Chromium"`，并附注释说明
解耦理由。不采用「另加一个 IDS 再映射」的方案——`IDS_PRODUCT_NAME_BASE` 经
`create_string_rc.py` 的 `MODE_SPECIFIC_STRINGS` 按安装模式生成多个变体，
再插一层映射会让安装器字符串表结构变复杂，收益不值。

**判据**：重装后 `%PUBLIC%\Desktop\` 下应为 `Chromium.lnk`，关于页仍显示 `Mcloud`。

---

## 14. 最终构建与打包（2026-11-09 06:27，重启后收尾）

**重启中断的位置**：`chrome.dll` 重链接（06:05 那轮只走到 `[3/10]`）。重启后 `chrome.dll`
仍是 05:58:30 的旧产物 ⇒ 链接确实未完成，必须重跑。

**重启后的环境变化（值得记）**：本机 WorkBuddy 的**后台 shell 全部不可用**——
凡是 `run_in_background` 的命令都在 103 ms 内失败，报
`[SandboxError] sandbox creation failed (code 0xFFFFF826) / center 规则快照不可用`，
连 `echo` 都跑不动；而**前台命令加沙箱豁免则正常**。所以本轮改用前台分段执行：

| 段 | 命令 | 结果 |
|---|---|---|
| 1 | `ninja -C out/mcloud -j 32 chrome.dll` | `[1/1] LINK(DLL) chrome.dll` RC=0 |
| 2 | `SKIP_UNSTICK=1 JOBS=32 bash resume_stage_d_clean.sh` | `[1/6]…[6/6]` RC=0，耗时 150 s |

**重启前先做的定点探测**（替代全树 `unstick.py`，避免十几分钟扫描）：只探待编 10 条边会写的
403 个文件（`out/mcloud/*.rsp|*.dll|*.exe|*.lib|*.pdb|*.res` +
`obj/chrome/installer/util/with_no_strings/` + `initialexe/` + `gen/chrome/installer/mini_installer/`），
**stuck = 0**。结论：重启已清除句柄，中断残留文件问题在这台机器上是「进程退出即自愈」。

### 三处改动的验证判据

| 改动 | 判据 | 实测 |
|---|---|---|
| DoH 默认模板 | 全新 profile、零配置跑，看 netlog 的 `DNS_CONFIG_CHANGED` | `mode=1`（automatic）+ `servers=[{template:'https://doh.pub/dns-query'}]` **通过** |
| 快捷方式名解耦 | 时间链 `install_util.cc` 05:56 → `.obj` 06:02 → `setup.exe` 06:25 | 逐级递进，**补丁已编入** |
| 品牌文案 | `locales/zh-CN.pak` 与 `en-US.pak` 内容 | 05:35 那轮已验证通过 |

### 发布物（最终）

| 产物 | 大小 | SHA256 |
|---|---|---|
| `mcloud_158.0.8127.30_win64_mini_installer.exe` | 134,288,384 | `6fe4d74b…eced27a` |
| `mcloud_158.0.8127.30_win64_setup.exe` | 134,316,032 | `202d1f48…3bc0df8` |

门禁全绿，两个 `.sha256` sidecar 已更新并**实算复核 MATCH**。

### 一个副作用需要知道

`InstallUtil::GetDisplayName()`（`install_util.cc:568-570`）内部**直接返回
`GetShortcutName()`**。因此固定快捷方式名为 `Chromium` 会顺带把**卸载项 DisplayName、
开始菜单项、防火墙规则名、应用注册名**全部保持为 `Chromium`；只有关于页读
`IDS_PRODUCT_NAME`，显示 `Mcloud`。这正是想要的分界——安装身份不动，只改 UI 文案。

### 待办
- 需**重新安装**才能看到三处改动（当前装机版本是 05:58 之前的构建）
- 干净安装四断言（会覆盖现有系统级安装，需单独确认）
- 对外 push / tag（需单独授权；第 18 条要求 L3 安全审查）

---

## 15. DoH 最终定案：默认 kSecure（2026-11-09 06:56）

§12 的结论（「保持 kAutomatic、只补默认模板即可默认走 DoH」）**经实测证伪**，此处纠正。

### 实测证据（同机、同二进制，只改配置；判据为 netstat 活动连接）

| 配置 | 到 DoH 端点的活动连接 | 判读 |
|---|---|---|
| `secure` + 模板 | 5 条（`1.12.12.12:443` / `120.53.53.53:443`） | DoH 生效（同时验证采样方法有效） |
| `automatic` + 模板（全新 profile 零配置） | **0 条**（两次复现） | **未走 DoH** |

⚠ 过程中出现过一次「175 条命中」的假信号，追查后属主是 **PID 13672**，与测试实例 PID 不同 ——
是本机上用户手动设了 DNSPod 的已装浏览器产生的流量。**必须按 PID 归属过滤**，否则极易误判。

### 根因（源码级）

`net/dns/host_resolver_manager.cc:1372-1377`：

```cpp
case SecureDnsMode::kAutomatic:
  if (dns_client.FallbackFromSecureTransactionPreferred(resolve_context)) {
    // Don't run a secure DnsTask if there are no available DoH servers.
    if (dns_tasks_allowed && insecure_tasks_allowed)
      out_tasks->push_back(dns_task_type);      // 只发明文
  }
```

`FallbackFromSecureTransactionPreferred`（`net/dns/dns_client.cc:233`）判据是
`NumAvailableDohServers() == 0`。而「服务器可用」只能由一次成功的 DoH 事务或一次
DoH 探测记录；探测（`host_resolver_manager.cc:1953-1962` `CreateDohProbeRunner`）
只服务于**自动升级**路径。模板是预置的、不走升级 ⇒ 没人发起探测 ⇒ 闭环：
不可用→只发明文→永远不会变可用。

结论：**`kAutomatic` + 预置模板 = 纯明文 DNS**。netlog 的 `dns_config.servers` 只是配置
对象携带的副本，不代表被使用（这一点尤其容易误判为「已生效」）。

### 定案（用户选择「方案 3」）

`chrome/browser/net/default_dns_over_https_config_source.cc`：

```cpp
local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsMode,
                                 base::Value(SecureDnsConfig::ModeToString(
                                     net::SecureDnsMode::kSecure)));
local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsTemplates,
                                 base::Value("https://doh.pub/dns-query"));
```

- 模板只留 DNSPod（与用户手动配置一致）；阿里云仍在提供方下拉列表里，用户可自行切换。
- **代价（已知并接受）**：`kSecure` 无明文回退。若网络封了到 `doh.pub` 的 443，域名解析
  直接失败、页面打不开；用户在「设置 → 隐私和安全 → 安全 DNS」改回「自动」即可恢复。

### 验证（新构建）

| 项 | 结果 |
|---|---|
| netlog `DNS_CONFIG_CHANGED` | `mode=2`（secure）+ `servers=[{template:'https://doh.pub/dns-query'}]` |
| 活动连接（按 PID 差集过滤） | 2 条 `ESTABLISHED` 到 `120.53.53.53:443`，PID 属本次实例 |
| 页面加载 | 成功（DOM 372 KB） |
| 注入脚本 | 幂等（第二次运行全部 `[skip]`），并清掉了残留的旧 `kAutomatic` 校验输出 |

### 发布物（最终）

| 产物 | 大小 | SHA256 |
|---|---|---|
| `mcloud_158.0.8127.30_win64_mini_installer.exe` | 134,281,728 | `f5f21911…f77da6a3` |
| `mcloud_158.0.8127.30_win64_setup.exe` | 134,309,376 | `84a10de7…a38ef4a7` |

门禁全绿，两个 `.sha256` sidecar 已更新并实算复核 MATCH。

---

## 16. 安装器受阻：D-MM-INSTALL-57（2026-11-09 07:45，未闭环）

用户要求「重编后走正常安装流程并自行实机测试」。**安装环节未通过**，但实机验证已用
手工部署完成。此处如实记录，问题未解决。

### 现象

| 时机 | 安装对象 | 结果 |
|---|---|---|
| 06:58 | 158 setup.exe --quiet --no-launch（就地更新已装 158） | mini_installer 退出码 = 57，复验判为未通过 |
| 07:04-07:35 | 158 mini_installer.exe --system-level（多次，含清空暂存/重打归档后） | 恒为 **57** |
| 07:36 / 07:44 | **155** mcloud_155.0.8059.40_win64_setup.exe --system-level（干净机器、清空注册表后） | 同样 **57** |

**关键判据：155 包也失败 ⇒ 不是 158 构建特有，而是本机/环境级的安装器故障。**
（155 包此前在本机成功安装过。）

### 已排除的因素（都有实测）

| 怀疑项 | 结论 |
|---|---|
| 归档损坏 | **排除**。py7zr 读 chrome.7z：254 条目，含 Chrome-bin/chrome.exe 4,068,864 B、chrome_proxy.exe 2,642,432 B，CRC 正常；chrome.packed.7z 为单条目 chrome.7z 封装 |
| 暂存目录陈旧 | **排除**。暂存与 out/mcloud 的 chrome.dll / chrome.exe / chrome_proxy.exe **哈希完全一致**（时间戳旧只是复制保留原值） |
| 安装树脏 | **排除**。删掉 C:////Program Files\\Chromium 与 SOFTWARE\\Chromium（含 Uninstall\\Chromium，32 位视图）后重试，仍 57 |
| 杀软拦截 | **排除**。MsMpEng.exe 未运行，无第三方 AV，Defender 事件为空 |
| 磁盘/过滤驱动 | **排除**。在 C:////Program Files\\Chromium\\Temp 写入 460 MB 文件，8 秒后仍在、大小正确 |
| TEMP 指向异常 | **排除**。TEMP/TMP 均为 C:////Users////Administrator////AppData////Local////Temp |

### 失败链（来自 C:////Windows////SystemTemp////chromium_installer.log）

**路径 A（mini_installer -> setup）**

    Uncompressing archive to path C:////Program Files\\Chromium\\Temp\\source<pid>_<rand>
    Unable to open install archive: .../chrome.7z: 系统找不到指定的文件 (0x2)

即：从 chrome.packed.7z 解压出的 chrome.7z 在数秒后被判为不存在 -> setup 返回 57
（UNPACKING_FAILED，见 chrome/installer/util/util_constants.h）。
实时监控证实：chrome.7z 曾出现在该目录，随后目录变空。

**路径 B（直接 setup.exe，chrome.7z 就在同目录）**

解包成功（254 文件落地），失败在工作项：

    Could not move .../Chrome-bin/chrome.exe, as it does not exist
    -> item execution failed -> Install failed, rolling back... result: 7

即使归档中确有该文件、且监控到它被解出，工作项仍报缺失。

### 当前机器状态（已手工恢复可用）

因卸载中途被中断、安装目录被清，为不阻塞实机验证，**用归档直接部署**了一份可用安装：

- py7zr 解 test_chrome.7z -> C:////Program Files\\Chromium\\Application\\，并把 Chrome-bin/*
  拍平到 Application\\（与安装器布局一致）。
- 手工写入注册表（32 位视图）：SOFTWARE\\Chromium 的 pv=158.0.8127.30；
  ...\\Uninstall\\Chromium 的 DisplayName=Chromium、DisplayVersion、InstallLocation、
  UninstallString、DisplayIcon。
- 这是**手工部署**，不是安装器产物；Installer\\setup.exe 等安装器私有文件不在位。
  后续修好安装器后应重装一次以回到正规状态。

### 实机验证结果（用已安装二进制，全部通过）

| 项 | 判据 | 结果 |
|---|---|---|
| 默认 DoH | 全新 profile 零配置，netlog DNS_CONFIG_CHANGED | mode=2（secure）+ servers=[{template:https://doh.pub/dns-query}] |
| DoH 真实流量 | netstat 按启动前 PID 差集过滤 | 3 条 ESTABLISHED 到 1.12.12.12:443 / 120.53.53.53:443（PID 属本次实例） |
| 页面可用性 | --dump-dom https://www.163.com | 366,721 B，正常渲染 |
| 中文版权 | locales/zh-CN.pak | 含 狗木马、版权所有、Mcloud |
| 英文版权 | locales/en-US.pak | 含 Mcloud. All rights reserved |
| 快捷方式 | %PUBLIC%\\Desktop | 仍为 Chromium.lnk，无 Mcloud.lnk |

### 下一步建议（按性价比）

1. **先重启再重试安装**：本日出现过异常硬复位，且有一次卸载被 SIGTERM 中断；重启可清掉
   可能的残留内核句柄/安装器单例状态。成本最低。
2. 若仍 57：用 **Process Monitor** 过滤 Path contains chrome.7z 与 Result is DELETE，
   定位是谁在解压后删除中间归档（路径 A 的核心疑点）。
3. 并行方案：排查 create_installer_archive.py 的 GetLZMAExec 产物与 setup 内置
   seven_zip 读取器的兼容性；必要时改为 BN（未压缩二进制）资源形态规避解压环节。
