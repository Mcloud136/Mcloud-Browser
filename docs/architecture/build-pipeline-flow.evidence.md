# Build Pipeline Flow — 证据清单

所有节点与边的证据引用（2026-08-18 核实，仓库 HEAD）。置信度均为 **high**（直接代码/配置证据）。

## 触发

| 图元素 | 证据 |
|---|---|
| 本地部署触发 | `win_scripts/deploy_mcloud.py` L1-14 头注："内核升级后唯一部署步骤" |
| push/PR 验证触发 | `.github/workflows/verify.yml` L3-7（`push: branches: [main]`, `pull_request`, `workflow_dispatch`） |
| v* tag 发布触发 | `.github/workflows/release.yml` L3-5（`push: tags: ['v*']`） |

## 阶段 A — 部署编排

| 图元素 | 证据 |
|---|---|
| 7 步顺序 + fail-fast | `deploy_mcloud.py` L25-32 `STEPS` 列表；L38-40 `FAILED at %s` 中止逻辑 |
| step1 复制 compiler_opt.gni | `copy_essentials.py` L19-23 `essential_files`；L26-38 复制逻辑（含 "src/" 前缀剥离注释 L27-31） |
| step1 复制 flags.txt | `copy_essentials.py` L40-47 |
| step2 BUILDCONFIG.gn polly 接线 | `deploy_mcloud.py` L8 头注 + `win_scripts/apply_polly_wiring.py`（存在性由 `verify_sources.py` L33 保证） |
| step3 compiler/BUILD.gn polly 定义 | `deploy_mcloud.py` L9 头注 |
| step4 AVX2+FMA3 基线 | `deploy_mcloud.py` L10 头注（"替换 -msse3"） |
| step5 D3D12/后台模式/DoH | `deploy_mcloud.py` L11 头注 |
| step6 注入加载器 | `inject_flags_loader.py` L20-22 幂等检查；L100-105 注入点 1（匿名命名空间）；L107-117 注入点 2（`BasicStartupComplete` 开头） |
| step7 复制 flags → out/mcloud | `deploy_mcloud.py` L42-46 |
| "不整体覆盖"设计原则 | `copy_essentials.py` L1-10 头注（2026-08-06 重构说明，旧副本 API 漂移实证） |

## 阶段 B — 生成与编译

| 图元素 | 证据 |
|---|---|
| args.gn 来源 | AGENTS.md「完整构建流程」：`cp win_args_mcloud.gn out/mcloud/args.gn`；仓库根存在 `win_args_mcloud.gn` |
| gn gen --check | `deploy_mcloud.py` L15、L50（"next: gn gen out/mcloud --check"）；AGENTS.md「增量与重配」 |
| autoninja mcloud_all / setup mini_installer | `build_win.py` L44、L46 |
| 产物 mini_installer.exe | `build_win.py` L48-50 |
| 编译失败 exit 111 | `build_win.py` L12-15 `fail()` |

## 阶段 C — 运行时

| 图元素 | 证据 |
|---|---|
| exe 同目录读取 flags | `inject_flags_loader.py` L43-51 注入的 `LoadMcloudPerformanceFlags()`（`base::DIR_EXE` + `mcloud_flags.txt`） |
| 逐行解析 / 注释跳过 | 同上 L55-64（`#` 注释、非 `--` 行跳过） |
| features 合并、用户优先 | 同上 L83-93（`kEnableFeatures`/`kDisableFeatures` 合并，用户条目追加在后） |
| flags 内容 66 行 | `mcloud_flags.txt` 逐行核数（65 feature/开关行 + L57 `--js-flags` 复合行） |

## CI 与发布

| 图元素 | 证据 |
|---|---|
| verify_sources 四检查 | `verify_sources.py` L2-12 docstring；L26-37 KEY_SCRIPTS（10 个）；L40-48 PAK_SRC_FILES |
| exit 0/1 门禁 | `verify_sources.py` L132-133；`verify.yml` L24-25 |
| release 不执行构建 | `release.yml` 全文无编译步骤；L60-67 仅对仓库根已存在的 `mini_installer.exe` 计算 SHA256（不存在则跳过） |
| 遗留 setup.py 路径 | `setup.py` L92-117 全量目录覆盖 + L134-161 补丁列表 + L194-263 `git apply` |
