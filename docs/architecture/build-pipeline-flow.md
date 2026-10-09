# MCloud Browser — Windows 构建流水线流程图

- **产出技能**：Architecture Visualization 插件 `flow-visualizer`（场景）+ `graphviz`（格式基础）
- **图源文件**：`build-pipeline-flow.dot`（可用插件内置 DOT Canvas 直接预览）
- **证据清单**：`build-pipeline-flow.evidence.md`
- **风险与缺口**：`build-pipeline-flow.risks-and-gaps.md`
- **视图级别**：L4（文件/脚本级）+ 运行时数据流；置信度全部为 high（每条边均有代码/配置引用）

## 阅读顺序

1. **触发**：开发者在本地执行 `deploy_mcloud.py`（推荐唯一入口），或 push/PR 触发 CI 验证，或 push `v*` tag 触发发布。
2. **主路径**：部署编排 → GN 生成 → Ninja 编译 → 安装包产出 → 运行时 flags 加载。
3. **分支**：失败中止路径（红色虚线）、CI 验证路径（紫色）、遗留 setup.py 路径（灰色）。

## 主路径说明

**阶段 A — 部署（THOR_DIR → CR_DIR，全部幂等）**

`deploy_mcloud.py` 按固定顺序执行 7 步，任一步非零退出即 fail-fast 中止：

| # | 脚本 | 作用 |
|---|------|------|
| 1 | `copy_essentials.py` | 复制 `compiler_opt.gni`（无上游对应物的专有声明）+ `mcloud_flags.txt` 到 CR_DIR |
| 2 | `apply_polly_wiring.py` | `BUILDCONFIG.gn` polly/emit-relocs 接线 |
| 3 | `append_polly_configs.py` | `compiler/BUILD.gn` polly 定义 + import |
| 4 | `apply_avx2_baseline.py` | `win/BUILD.gn` AVX2+FMA3 基线（替换 -msse3） |
| 5 | `apply_mcloud_source_defaults.py` | D3D12 默认启用 / 后台模式默认关 / DoH 校验 |
| 6 | `inject_flags_loader.py` | 向 `chrome_main_delegate.cc` 幂等注入 `LoadMcloudPerformanceFlags()` |
| 7 | （编排器内联） | 复制 `mcloud_flags.txt` → `out/mcloud/`（加载器运行时读取位置） |

关键设计：除 `compiler_opt.gni` 外**不整体覆盖任何源文件**——旧基线副本与新上游树存在 API 漂移（2026-08-06 重构，见 copy_essentials.py 头注），全部定制改为定点注入。

**阶段 B — 生成与编译**

- 首次或改配置后：`cp win_args_mcloud.gn out/mcloud/args.gn` → `gn gen out/mcloud --check`
- `build_win.py`：`autoninja -C out/mcloud mcloud_all` → `autoninja -C out/mcloud setup mini_installer`，产物为 `out/mcloud/mini_installer.exe`。

**阶段 C — 运行时闭环**

安装后 `chrome.exe` 在 `BasicStartupComplete` 早期从 exe 同目录读取 `mcloud_flags.txt`，
逐行解析并合并进进程命令行（enable/disable-features 合并、用户条目优先；普通开关用户已指定则跳过）。
这就是"编译时优化 + 运行时标志"两条优化链的汇合点。
实测 `mcloud_flags.txt` 含 **66 行标志**（65 个 feature/开关行 + 1 行 `--js-flags` 复合 V8 参数），
而 AGENTS.md 声称 52 项——文档与实物已漂移，见 risks 文档 R3。

## 旁路

- **CI 验证**：push/PR → `verify.yml` → `verify_sources.py`（Python 语法 + 10 个关键脚本存在性 + pak_src C 源码检查），exit 0=PASS / 1=FAIL。
- **发布**：`v*` tag → `release.yml` → 生成 SHA256 → GitHub Release。**注意**：该工作流不执行构建，仅上传仓库根的 `mini_installer.exe`（当前依赖本地构建产物手动入库）。
- **遗留路径**：`setup.py` 全量覆盖 + `git apply` 20+ 补丁，已被定点注入流程取代，仅作历史保留。

## 假设与限制

- `mcloud_flags.txt` 实际为 66 行标志（本次逐行核实），AGENTS.md 的"52 项"已过时（见 risks 文档）。
- 图中部署步骤顺序以 `deploy_mcloud.py` 的 `STEPS` 列表为准（high）。
- `inject_flags_loader.py` 中硬编码了绝对路径 `D:\wxmuma\chromium-src\src\...`，图按 CR_DIR 默认值绘制。

## 维护说明

流水线脚本变更后，先更新 `build-pipeline-flow.evidence.md` 的行号引用，再按证据修订本图；
修改后用 Qoder 的 DOT Canvas 预览 `build-pipeline-flow.dot` 验证渲染。
