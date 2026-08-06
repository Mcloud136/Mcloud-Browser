# Phase 1 开发日志 — 规范落地与 P0 整改执行

- **日期**：2026-08-05
- **范围**：《性能优化与构建配置技术规范》10.5 优先级表中全部 P0 项 + 整改项 A9
- **规范依据**：`docs/architecture/performance-build-technical-spec.md`

## 1. feature 生效链路修复（规范 4.1.1，方案 B）

**核查结论**：`mcloud_flags.txt` 已被复制到 chromium 源码树根目录，但全树无任何 `.gn/.cc/.py` 引用——54 项运行时优化标志实际未生效（与 README 宣称不符，整改项 A6）。

**实施方案**：内置命令行加载（方案 B）。

| 文件 | 变更 |
|------|------|
| `src/chrome/app/chrome_main_delegate.cc` | 新增 `LoadMcloudPerformanceFlags()`：启动时从 exe 同目录读取 `mcloud_flags.txt`，逐行解析（支持 `--flag`、`--flag=value`、引号值、注释行），在 `BasicStartupComplete()` 最早期注入命令行；`enable/disable-features` 与用户命令行合并且用户条目优先，其余标志用户已指定则跳过 |
| `win_scripts/copy_essentials.py` | 清单新增 `chrome_main_delegate.cc`；新增将 `mcloud_flags.txt` 复制到 `out/mcloud/` 的步骤 |
| `setup.sh` | Linux 流程同步复制 `mcloud_flags.txt` 到 `out/mcloud/` |

**验证方法（待构建后执行）**：`chrome://version` 命令行应显示合并后的 `--enable-features=...`；对启动/内存/媒体三组各抽查 2 项。

**已知限制**：mini_installer 安装包当前不会把 `mcloud_flags.txt` 打进安装目录（`other/mini_installer.patch` 未修改），即**开发构建生效、安装版暂不生效**，列入下一阶段待办。

## 2. 一致性整改（规范 3.4 / 附录 A）

| 项 | 处理 |
|----|------|
| A1 profdata 路径 | `win_args_mcloud.gn` 补充版本匹配规则与换机说明注释（GN 不支持环境变量展开，路径指向构建机标准 chromium-src 位置） |
| A3 RLZ 口径 | 决策：维持 `enable_rlz = true`；`CLAUDE.md` 已同步更正；决策记录 `docs/decisions/ADR-001` |
| A4 use_icf 注释 | `win_args_mcloud.gn` 注释更正：Windows ICF 实际由 `/OPT:ICF` 保障（`src/build/config/win/BUILD.gn`） |
| A5 数量口径 | 实测 `mcloud_flags.txt` 为 **54 项**；README（3 处）与 CLAUDE.md 已统一改为"54 项运行时优化标志"并引用该文件 |
| A6 flags 生效 | 见第 1 节（已修复，待构建验证） |
| A9 package.sh | `docs/BUILDING.md` 修订为指向 `build.sh`（打包已集成于 build.sh） |

## 3. 决策记录（ADR）

- `docs/decisions/ADR-001-rlz-and-public-api-keys.md`：RLZ 维持 true；Google API 密钥为生态公开密钥，保留不移除（整改项 A2 撤销）。
- `docs/decisions/ADR-002-performance-over-size.md`：性能优先，体积不作约束，Windows 必须全量 -O3；附 -O3 生效链路清单（升级时核对）。

## 4. 基准测试体系（规范第 7 章，整改项 A8）

新建 `benchmark/` 目录：

- `bench_startup.ps1`（K1 冷启动，5 次中位数）
- `bench_memory.ps1`（K2 50 标签内存，可指定 URL 列表）
- `bench_size.ps1`（K7 体积，仅观测）
- `README.md`（KPI 总览、环境要求、K3-K6 手工流程、对照基准要求、归档规则）
- 结果模板：`docs/dev-logs/benchmark-template.md`

## 5. 待办（下一阶段）

| 优先级 | 事项 |
|--------|------|
| P0 收尾 | 重新执行 `copy_essentials.py` + `gn gen` + 编译，验证 flags 加载生效（chrome://version 抽查） |
| P0 收尾 | mini_installer 打包 `mcloud_flags.txt`（修改 `other/mini_installer.patch` 或安装后复制） |
| P0 | 建立 M150 基线数据（K1-K7 全套，用 benchmark/ 脚本） |
| P1 | M150 → M151 内核升级（规范第 11 章执行方案，profdata 需更新为 7922 系列） |
| P1 | feature 清单治理脚本（规范 10.4） |
| P2 | BOLT 后链接流程落地、自采 PGO（规范 10.1/10.2，依赖基线数据） |

## 6. 本轮变更文件清单

```
src/chrome/app/chrome_main_delegate.cc        （新增 flags 加载器）
win_scripts/copy_essentials.py                （清单+flags 复制）
setup.sh                                      （flags 复制）
win_args_mcloud.gn                            （A1/A3/A4 整改）
CLAUDE.md                                     （RLZ/数量口径/目录说明）
README.md                                     （数量口径 x3）
docs/BUILDING.md                              （A9 修订）
docs/decisions/ADR-001-rlz-and-public-api-keys.md   （新增）
docs/decisions/ADR-002-performance-over-size.md     （新增）
benchmark/                                    （新增目录，4 文件）
docs/dev-logs/benchmark-template.md           （新增）
docs/dev-logs/phase1-dev-log.md               （本文件）
```
