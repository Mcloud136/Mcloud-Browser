# ADR-001：RLZ 启用状态与 Google API 密钥保留

- **状态**：已采纳
- **日期**：2026-08-05
- **决策人**：项目方
- **依据条款**：`docs/architecture/performance-build-technical-spec.md` 3.4-1、3.4-3

## 背景

1. `win_args_mcloud.gn` 中 `enable_rlz = true`，而 `CLAUDE.md` 关键参数表写的是 `enable_rlz = false # 禁用 Google 追踪`，两处口径矛盾（整改项 A3）。
2. 仓库中多处明文存放 Google API 密钥（`win_args_mcloud.gn` L114-116、`CLAUDE.md`、`launch_browser.bat`），此前审查曾建议移除（整改项 A2）。

## 决策

### 1. RLZ 维持启用（`enable_rlz = true`）

- 理由：与 `win_args.gn`（L61，`enable_rlz = true`）及上游 Thorium 系 Windows 构建口径一致；RLZ 用于搜索引擎归因，与本项目保留 Google 服务集成（Sync、翻译等）的产品定位一致（参照 FAQ 第 4 条：本项目不做 UnGoogled 路线）。
- 同步动作：`CLAUDE.md` 已更正为 `true`。

### 2. Google API 密钥保留，不移除

- 理由：经项目方确认，该密钥为 **Chromium 衍生生态公开共享的通用密钥**（Thorium/gz83 等项目公开引用），非私有凭据，无滥用风险。
- 同步动作：整改项 A2 已撤销（规范附录 A2 标注为已撤销）。

## 后果与约束

- 后续内核升级时保持 `enable_rlz = true` 不变。
- 安全审查/规范修订时不得再将上述密钥列为整改项。
- 若未来项目转向隐私强化路线，须新开 ADR 推翻本决策。
