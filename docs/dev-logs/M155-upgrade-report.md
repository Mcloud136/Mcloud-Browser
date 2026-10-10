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
| 8-11 | 全量编译 + 冒烟 | ✅ 58,416 步 `autoninja exit=0`（14:33→17:28）；D3D12 清理后重打包（18:14，127,541,248 B） |
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

## 遗留事项

- Tier A 19 项性能候选的逐项 A/B（`docs/tasks/m155-perf-features.md`），以及 `SkiaGraphite` 禁用的收益/代价复核
- D49：V8 `_`/`-` 等价性需 `autoninja d8` 才能定论
- 把 `check_features.py` 存活性校验接入 CI 的可行性（当前记为不接入：runner 无 Chromium 检出）
- 发布：push / tag / 资产上传（待授权 + L3 门禁）
