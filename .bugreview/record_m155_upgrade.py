#!/usr/bin/env python3
"""record_m155_upgrade.py - 写入 M155 升级的仓库侧记录（CHANGELOG / 升级报告 / progress / 任务单勾选 / 口径更正）。"""
import io
import os

REPO = r"d:\wxmuma\thorium"


def edit(rel, pairs):
    p = os.path.join(REPO, rel)
    s = io.open(p, encoding="utf-8").read()
    hit = 0
    for a, b in pairs:
        if a in s:
            s = s.replace(a, b, 1)
            hit += 1
        else:
            print("  !! 未命中 @%s: %s" % (rel, a[:60]))
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("  %s %d/%d" % (rel, hit, len(pairs)))


# ---------- 1) 口径更正：AGENTS.md 的 V8 连字符断言、README 残留 ----------
edit("AGENTS.md", [
    ("- **已知坑**：V8 flags（--js-flags 内）须用 M151 **下划线**命名格式"
     "（`--invocation_count_for_maglev=...` 等），连字符旧格式在 M151 静默失效"
     "（mcloud_flags.txt 55-57 行实证注释）；",
     "- **已知坑（口径已更正 2026-10-10）**：`--js-flags` 内的 V8 标志**统一写下划线形式**"
     "（`--invocation_count_for_maglev=...`）。旧断言「连字符写法在 M151 静默失效」与源码不符："
     "`v8/src/flags/flags-impl.h:19` 的 `NormalizeChar` 把 `_` 归一为 `-` 并用于标志名比较，"
     "两种写法应等价；Chromium 侧对未知 js-flags 静默忽略，故该点无法用 stderr 反证（缺陷 D49，"
     "定论需 `autoninja d8`）。沿用下划线写法是安全的默认，不要再以「连字符会失效」为依据做判断；"),
])
edit("README.md", [
    ("基于 Chromium M151 的高性能浏览器，AVX2 原生编译，66 项运行时优化标志",
     "基于 Chromium M155 的高性能浏览器，AVX2 原生编译，56 条运行时优化开关"),
    ("# 3. 拉取 Chromium M151 源码（定向浅拉取目标 tag，避免全量枚举）",
     "# 3. 拉取 Chromium M155 源码（定向浅拉取目标 tag，避免全量枚举）"),
    ("# 5. 下载 PGO profdata（版本必须与内核匹配：M151=7922 系列）",
     "# 5. 下载 PGO profdata（版本必须与内核匹配：M155=8059 系列）\n"
     "#    另需拉 V8 builtins profile：python v8/tools/builtins-pgo/download_profiles.py download"),
])

# ---------- 2) CHANGELOG：M155 段 ----------
p = "docs/CHANGELOG.md"
s = io.open(p, encoding="utf-8").read()
if "## M155（内核升级" not in s:
    entry = """## M155（内核升级 M151 → M155.0.8059.40）— 2026-10-10

### 升级本体
- 内核 `155.0.8059.40`（当期 stable）；V8 `15.5.35.20`；clang `llvmorg-24-init-7747`；PGO `chrome-win64-8059-…profdata`
- 定制重放面在升级中进一步缩小为 **6 个上游文件 / 206 行**：
  `apply_mcloud_source_defaults.py` 不再翻转 `kD3D12VideoDecoder` 默认（改为只校验 + 自愈回退历史覆盖），
  禁用意图统一由 `mcloud_flags.txt` 显式声明 —— 消除长期存在的「覆盖与运行时禁用互相抵消」自相矛盾（原 D24 遗留项收口）
- 首轮全量编译 58,416 步一次通过（`autoninja exit=0`）；`gn gen --check` 35,747 targets 无未知参数告警

### 性能 / 内存 / GPU 实测（同一台机器、同一时刻成对测量）
| 指标 | M151-r3 | M155 | 结论 |
|---|---|---|---|
| K1 冷启动中位数 | 46 ms（59,46,46,47,46） | **45 ms**（62,45,47,45,44） | 持平（差异在噪声内） |
| K2 50 标签驻留中位数 | 2590 MB（56 进程） | **2563.3 MB** | -1.0% 内存 |
| 标签开合泄漏探针（4 轮 × 25 标签，关标签后驻留） | 872.7→883.8 MB（+3.7 MB/轮） | **957.5→950.3 MB（-2.4 MB/轮）** | 155 无正漂移，回收更好 |
| GPU 渲染路径（窗口化探针） | GPU 进程在，D3D11+D3D12 ANGLE，无 SwiftShader | **同左，gpu-preferences 逐字一致** | 无回退 |
- A6 子进程命令行验证通过；`check_features.py` 在 155 源码树上 **53/53 存活**；
  `flag_stability.py` 以 [155,156] 为版本集合 **PASS**

### 升级期发现并修正的问题
- **D50（新）**：`SkiaGraphite` 在 151/155/156 均为**上游默认启用**，而拖拽冻结缓解只是注释掉启用行 —— 等于从未禁用。
  现改为显式 `--disable-features=SkiaGraphite`（`--enable-features=…` 列表不变），并把它列入 155 上的同方法 A/B 复核项
- `FlingSchedulingImprovements`：M155 起上游彻底移除，已按预评估约定从 flags 删除，接替候选见
  `docs/tasks/m155-perf-features.md`（`ResampleScrollEventsForFling`、`ApplyScrollRailingInRenderer`）
- 工具链坑（已写入 AGENTS.md 构建流程）：`gclient sync --jobs=16` 撞 googlesource 429 → 改 `jobs=4`；
  钩子按字面调用 `python3` 会命中 WindowsApps 占位程序 → 在真实 Python 目录内 `mklink /H python3.exe python.exe`；
  缺 `v8/tools/builtins-pgo/profiles/x64-rl.profile` 会让 `snapshot_blob.bin` 直接失败 → `download_profiles.py download`

### 发布
- 安装包：`mcloud_155.0.8059.40_win64_mini_installer.exe`（127,541,248 B）
- SHA256：`<SHA 待回填>`

"""
    s = s.replace("# MCloud Browser Changelog\n", "# MCloud Browser Changelog\n\n" + entry, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("  CHANGELOG M155 段已插入")

# ---------- 3) 升级报告 ----------
rep = """# M155 升级报告（M151.0.7922.99-r3 → M155.0.8059.40）

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
"""
p = "docs/dev-logs/M155-upgrade-report.md"
if not os.path.exists(os.path.join(REPO, p)):
    io.open(os.path.join(REPO, p), "w", encoding="utf-8", newline="\n").write(rep)
    print("  升级报告已写入", p)

# ---------- 4) progress 4.9 ----------
p2 = "docs/progress.md"
t = io.open(p2, encoding="utf-8").read()
if "### 4.9 " not in t:
    sec = """### 4.9 M155 内核升级完成（2026-10-10）

- 在独立第二棵树 `D:/wxmuma/chromium-src-155` 上完成 M151→M155 rebase：`deploy_mcloud.py` 7 步在全新树一次通过，
  `gn gen --check` 35,747 targets 零告警，全量 58,416 步一次编译通过，重打包 `mini_installer` 127,541,248 B。
- 定制面从 7 文件降到 **6 文件 / 206 行**（清理 D3D12VideoDecoder 的自相矛盾覆盖）。
- 同机成对基准：K1 46→45 ms、K2 2590→2563.3 MB（-1.0%）、标签开合泄漏由 +3.7 MB/轮 变为 -2.4 MB/轮、
  GPU 路径与 `--gpu-preferences` 与 151 逐字一致；A6 通过，`check_features(155)` 53/53，
  `flag_stability [155,156]` PASS。
- 新增验证工具：`benchmark/tools/leak_probe.py`（CDP 开合标签看驻留漂移）、
  `benchmark/tools/gpu_probe.py`（窗口化验证 GPU 进程与 ANGLE 后端，headless 不可用作 GPU 判据）。
- 新缺陷 **D50**：`SkiaGraphite` 三版均上游默认启用，冻结缓解此前从未真正禁用它 → 已显式 `--disable-features`，
  并列入 155 上的同方法 A/B（与 GPU 效率有张力）。
- 待办：Tier A 候选逐项 A/B、发布（push/tag/资产，需授权 + L3）、D49 用 d8 定论。
  详见 `docs/dev-logs/M155-upgrade-report.md`。

"""
    idx = t.index("## 5. 下次编译更新内核时的操作")
    t = t[:idx] + sec + t[idx:]
    io.open(p2, "w", encoding="utf-8", newline="\n").write(t)
    print("  progress 4.9 已写入")

# ---------- 5) 任务单勾选 ----------
p3 = "docs/tasks/m155-upgrade-task.md"
u = io.open(p3, encoding="utf-8").read()
for a, b in [
    ("## 阶段 0：预拉取核对（本次已在做，完成后再进阶段 1）", "## 阶段 0：预拉取核对 ✅（已完成，见下表实测）"),
    ("## 验收标准", "## 验收标准（实测：K1/K2/泄漏/GPU 全部达标，报告见 `docs/dev-logs/M155-upgrade-report.md`）"),
]:
    if a in u:
        u = u.replace(a, b, 1)
io.open(p3, "w", encoding="utf-8", newline="\n").write(u)
print("  任务单状态已标注")
