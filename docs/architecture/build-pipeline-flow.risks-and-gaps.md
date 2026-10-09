# Build Pipeline Flow — 风险与缺口

基于 `build-pipeline-flow.dot` 的已确认流程，列出证据支持的缺口与建议验证动作。

## R1 — release.yml 不构建，只上传（风险：高）

`release.yml` 全文无编译步骤，仅对仓库根已存在的 `mini_installer.exe` 计算 SHA256 并上传。
当前仓库根确实提交了 `mini_installer.exe` 与 `mcloud_151.0.7922.99_win64_mini_installer.exe`（二进制入库）。
**后果**：打 tag 者若忘记先本地构建并替换仓库根 installer，会发布过时二进制且 CI 无任何拦截。
**建议**：要么在 release.yml 增加 windows-latest 构建 job（需解决 Chromium 构建时长/缓存），要么在 tag 流程文档中把"更新仓库根 installer"写成显式前置检查，并加校验步骤比对 installer 哈希与 thor_ver。

## R2 — inject_flags_loader.py 硬编码绝对路径（风险：中）

L17 `p = r"D:\wxmuma\chromium-src\src\chrome\app\chrome_main_delegate.cc"`，
与流水线其余脚本统一使用的 `CR_DIR` 环境变量约定不一致；换机器/换目录即失效。
**建议**：改为 `os.environ.get('CR_DIR', ...)` 拼接路径，并纳入 verify_sources 的存在性检查范围。

## R3 — 文档与实物漂移：flags 计数（风险：低，已在本图修正）

AGENTS.md、README 均声称"52 项运行时优化标志"，实测 `mcloud_flags.txt` 为 66 行标志
（65 feature/开关行 + 1 行 `--js-flags` 复合 V8 参数）。
**建议**：更新文档口径，或在 verify_sources.py 中增加 flags 行数/关键 feature 存在性断言，防止再次漂移。

## R4 — 双入口并存：setup.py（全量覆盖）vs deploy_mcloud.py（定点注入）（风险：中）

AGENTS.md 流水线章节仍把 `setup.py` 列为第 1 步"入口脚本"，但 `copy_essentials.py` 头注
（2026-08-06 重构）已明确整体覆盖会因旧基线漂移破坏构建。两条策略互相矛盾，
新贡献者误跑 setup.py 会污染 Chromium 树。
**建议**：在 setup.py 顶部加废弃警告（或直接移除），并同步修正 AGENTS.md 流水线顺序。

## R5 — 注入锚点脆弱性只在部署期暴露（风险：中）

`inject_flags_loader.py` 依赖上游 `chrome_main_delegate.cc` 的精确文本锚点
（`namespace {`、`BasicStartupComplete` 函数签名正则）。上游小改动即 assert 失败——
fail-fast 是好事，但发现时机被推迟到部署期，且 verify_sources.py 只做语法/存在性检查，
无法预先捕获锚点漂移。
**建议**：内核版本升级（tot.py/trunk.py 同步）后把"重跑 deploy + gn gen"纳入升级 checklist 第一步。

## Unknown / validate next

- **PGO profiles**：`setup.py` 会下载 win64/V8 PGO profiles，但 `deploy_mcloud.py` 不下载。
  若 `win_args_mcloud.gn` 实际启用了 PGO，新树首次部署会缺 profiles——需核对 args 中
  `chrome_pgo_phase` 取值（本次未展开核实）。
- **Polly 步骤实际效果**：step2/step3 的接线存在，但 AGENTS.md 声明 `use_polly=false`
  （依赖未落地），即这两步目前是"接线但不生效"，图中按结构存在绘制。
