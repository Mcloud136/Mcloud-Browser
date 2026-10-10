# M155 升级报告（M151.0.7922.99-r3 → M155.0.8059.40）

- **执行日期**：2026-10-10
- **执行人**：Qoder Agent（用户授权「开始升级到 155 内核」）
- **任务依据**：`docs/tasks/m155-upgrade-task.md`、技术规范第 9 章 14 项清单、`docs/tasks/m155-upgrade-preassessment.md`
- **结果**：✅ 成功（一次编译通过 + 全部门禁绿 + 同机成对基准无回归、内存略降）
- **工作树**：升级在独立第二棵树 `D:/wxmuma/chromium-src-155` 完成，M151 树与其构建产物原样保留为回退点

## 执行清单核对（任务单 20 项 → 结果）

| 阶段 | 检查项 | 结果 |
|---|---|---|
| 0 | 155 源码 + 工具链预拉取 | ✅ `155.0.8059.40`（`cfaadc5a13`）、gn 2562、ninja 1.12.1、clang-cl(`llvmorg-24-init-7747`)、8059 profdata 104.4 MiB；`gclient sync --jobs=4` rc=0 |
| 1 | baseline tag（回退点） | ✅ `thorium: baseline-M151-r3`、`155 树: baseline-M155-start`；树纯净（0 修改） |
| 2-3 | `deploy_mcloud.py` 7 步 + `gn gen --check` | ✅ 7 步在全新 155 树一次通过；`35,747 targets from 5,034 files`，零未知参数告警 |
| 4 | 定制面复核 | ✅ 首次注入后 7 文件/207 行，与 151 树逐项一致；D3D12 清理后 **6 文件/206 行** |
| 5 | D47 装配清单 | ✅ `chrome.release` +1 行由注入器产生（探针 5 例含「155 文件首次注入可用」） |
| 6 | flags 收口 | ✅ 删 `FlingSchedulingImprovements`；显式禁用 `SkiaGraphite`；`flag_stability [155,156]` PASS；`check_features(155)` 53/53 |
| 7 | V8 builtins profile | ✅ 首编译被缺 profile 挡住（`x64-rl.profile`）→ `download_profiles.py download` + `validate --check-v8-revision` 通过（版本 15.5.35.20，revision 与 DEPS 一致） |
| 8-11 | 全量编译 + 冒烟 | ✅ 58,416 步 `autoninja exit=0`（14:33→17:28）；D3D12 清理后重打包（18:14，127,541,248 B）；A/B 后随 D51 语法修正再次重打包（20:25，**127,543,808 B**，SHA256 `195f9349…2dd81`，门禁全绿） |
| 12 | A6 / 基准 / 泄漏 / GPU | ✅ 见下表 |
| 13 | 文档口径切换 | ✅ AGENTS.md / README / win_args_mcloud.gn（8059 profdata）/ mcloud_flags.txt 注释；构建流程补三条工具链坑 |
| 14 | 发布 | ⏳ 待用户授权与 L3 门禁（发布说明文件须命名 `…-release-notes-m155.md`，否则选择器会退回 r3 正文） |

## 同机成对基准（18:2x，同一时刻先测 155 再测 151）

| 指标 | M151-r3 | M155 | 差 |
|---|---|---|---|
| K1 冷启动中位数（ms，5 轮） | 46（59,46,46,47,46） | 45（62,45,47,45,44） | -2.2% |
| K2 50 标签驻留中位数（MB） | 2590（56 进程） | 2563.3 | **-1.0%** |
| 泄漏探针（4 轮 × 25 标签，关标签后驻留序列，MB） | 872.7→876.6→878.6→883.8（+3.7/轮） | 957.5→949.1→938.0→950.3（**-2.4/轮**） | 155 无正漂移 |
| GPU（窗口化探针） | GPU 进程存在；D3D11+D3D12；无 SwiftShader | 同左，`--gpu-preferences` 逐字一致 | 持平 |

> 修正记录：`docs/dev-logs/M151-r3-benchmark.md` 里 r3 单独测得的 K1=39ms / K2=2927.5MB（64 进程）与本报告条件不同（机器状态、进程数），
> **A/B 结论一律以本报告的同机同时刻成对数据为准**。

## 升级期问题与处置

1. **`SkiaGraphite` 从未真正禁用（D50）**：三版上游默认均为 ENABLED，而冻结缓解只注释了启用行。已改为显式
   `--disable-features=SkiaGraphite`；因它与 GPU 效率存在张力，列入 A/B 队列（拖拽复现 + chrome://gpu 双看）。
2. **D3D12 自相矛盾覆盖清理**：`media_switches.cc` 翻 ENABLED + flags 再 disable 的互相抵消做法结束；上游默认保持
   DISABLED，禁用意图单一来源化。净行为不变（解码器仍禁用，Intel 核显绿屏规避仍成立）。
3. **工具链三坑**：`--jobs=16` → 429；`python3` 命中 WindowsApps 占位程序 → `mklink /H`；缺 V8 builtins profile → 树内脚本下载。
4. **自伤一次**：把重打包放在 `timeout 580s` 的前台命令里，误杀了正在做的 ThinLTO 链接（表现为 lld 无诊断的 FAILED）。
   改为脱离会话重跑后正常。教训：长链接必须脱离工具超时执行。
5. **`InitialWebUI` 的 params 写法不合法（D51，新发现）**：`Feature:a/b/c` 少了值，Chromium 要求
   `Feature:param/value/…`。运行时回显核对显示该条走的是 field-trial 通道（不判为失效），且三个参数
   的上游默认恰为 `true`，所以**净行为不变**；已改写为显式 `/true` 形式并把语法校验加进
   `.bugreview/flag_stability.py` 的 E 断言（奇数 token 直接 FAIL，已做负向对照验证）。M151 与 M155
   的回显对比证据见缺陷档案。
6. **`deploy_mcloud.py` 的 `CR_DIR` 默认指向 M151 树**（`D:\wxmuma\chromium-src\src`）。本轮在未设
   `CR_DIR` 的情况下跑了一次部署，实际作用在旧树上——因全部步骤幂等而未造成损坏，但**双树并存时
   必须显式指定 `CR_DIR`**（已写进 AGENTS.md）。附带发现：deploy 第 8 步"复制 flags 到 out/mcloud"
   与 `copy_essentials.py` 的第 1 步功能重复，所以它永远打印 "already in sync"（不是同步失败）。

## A/B 结论（Tier A 候选，2026-10-10 完成）

见 `docs/tasks/m155-perf-features.md` §5.1–§5.3。要点：**8 项候选全部不采纳**——不是有害，而是
现有四项判据在"同配置重复"测出的噪声带（K1 ±4 ms、K2 ±0.19 %、泄漏 ±8.9 MB）内无法证明任何收益；
round 1 曾按预登记阈值判 `PartitionAllocAdaptiveMemoryReclaimInterval` 过采纳线，round 2 的交错复测
把它否掉了（三次取值跨零）。`SkiaGraphite` 保持显式禁用：四项判据看不出差别，而撤销定案需要的是
拖拽+视频场景的人工复现证据。

**发布物已知偏差（重要）**：已发布的 M151-r3 安装包**不含** `--disable-features=SkiaGraphite`
（D50 是升级期才发现并修的，晚于 r3 打包）。证据：r3 时代构建目录的运行时清单经回显核对只带
`D3D12VideoDecoder` 一项禁用。也就是说 r3 用户实际跑在 Graphite 启用状态，而 2026-10-08 的冻结缓解
定案要求它禁用——M155 包修正了这一点。若关心拖拽冻结是否会在 r3 上复现，应以 M155 包为准。

## 遗留事项

- ~~Tier A 候选的逐项 A/B~~ → 已完成，结论"全部不采纳"，并给出下轮 A/B 的方法学门槛（§5.3）
- `SkiaGraphite` 撤销与否：等用户在拖拽+视频场景做人工复现后再定（自动化 KPI 无法判定）
- 网络/滚动类候选（DNS、QUIC、Cache-Control、fling 重采样等）需 K3/net-log 与帧时采集通道才能判，
  本轮判据不覆盖（清单见 `m155-perf-features.md` §5.2）
- D49：V8 `_`/`-` 等价性需 `autoninja d8` 才能定论
- 把 `check_features.py` 存活性校验接入 CI 的可行性（当前记为不接入：runner 无 Chromium 检出）
- 发布：push / tag / 资产上传（用户 2026-10-10 决定暂缓，先做 A/B；A/B 与第3周期 bug-review 均已完成，等待发布指示）。
  当前本地产物：127,523,328 B，SHA256 `0602cafabb94f221e7a6ec5bfd59605fceaceb0b2fa8c4d7e88339ea50717090`（第3周期全量重编后的 8 项门禁版本；⚠ 该「ALL PASS」摘要行因缺陷 D89 的失效聚合不可作证据，已在扩展轮修复并逐项重跑 8/8，见 docs/tasks/bug-review-cycle3-report.md §8）；
  旧的 `cd6f5172…` 因 D72（构建失败仍打包）作废。

