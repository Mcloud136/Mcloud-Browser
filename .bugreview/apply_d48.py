#!/usr/bin/env python3
"""apply_d48.py - 清理 mcloud_flags.txt 的失效条目（D48），且保证 M151 行为不变。

原则：只删除"在 M151 上本就不存在、因此今天也是静默无操作"的条目；
任何在 M151 上真实生效的条目一律保留（FlingSchedulingImprovements 属此类，
它只在升级 155 后才失效，因此加注释标记升级期处置，不在 r3 动它）。
改名条目改为注释保留（避免 r3 引入未经基准验证的行为变化）。
"""
import io
import sys

PATH = r"d:\wxmuma\thorium\mcloud_flags.txt"
s = io.open(PATH, encoding="utf-8").read()

# 1) 删除：在 151/155/156 三个版本上均无对应 feature 声明（实测，见缺陷档案 D48）
dead = [
    "--enable-features=CanvasOopRasterization",
    "--enable-features=DirectComposition",
    "--enable-features=EarlyData",
    "--enable-features=AVIF",
    "--enable-features=SpeculationRules",
    "--enable-features=ServiceWorkerNavigationPreload",
]
for line in dead:
    if line + "\n" not in s:
        print("FAIL: 待删除行未找到: %s" % line)
        sys.exit(1)
    s = s.replace(line + "\n", "", 1)

# 2) 改名条目：先注释保留（上游真名为 EnableBestEffortTaskInhibitingPolicy，
#    启用它会改变运行时行为，须按第 7 章基准单独验证，不在清理版直接生效）
old = "--enable-features=BestEffortTaskInhibitingPolicy\n"
new = ("# [D48 改名候选，r3 不直接启用] 本行原写作 BestEffortTaskInhibitingPolicy，"
       "上游并无该 feature（真名 EnableBestEffortTaskInhibitingPolicy，"
       "components/performance_manager/public/features.h，151/155 均默认禁用）。\n"
       "# 启用前需按规范第 7 章跑 K1/K2/K7 基准；确认收益后再取消下行注释。\n"
       "#--enable-features=EnableBestEffortTaskInhibitingPolicy\n")
if old not in s:
    print("FAIL: 改名目标行未找到")
    sys.exit(1)
s = s.replace(old, new, 1)

# 3) FlingSchedulingImprovements：M151 真实生效（默认禁用，我们启用）→ 保留，
#    但 M155 起上游已彻底移除该标识符，升级时必须删除并重新评估滚动调度。
old2 = "--enable-features=FlingSchedulingImprovements\n"
new2 = ("# [升级期处置] M151 上真实存在（默认禁用，本行启用）；155 起该 feature 标识符"
        "已从源码彻底消失（kFlingSchedulingImprovements 全树 0 命中，无同名后继），"
        "升到 155 时必须删除本行并重新评估滚动/合成调度类替代项（见 kResampleScrollEventsForFling、"
        "kApplyScrollRailingInRenderer）。\n"
        "--enable-features=FlingSchedulingImprovements\n")
if old2 not in s:
    print("FAIL: Fling 行未找到")
    sys.exit(1)
s = s.replace(old2, new2, 1)

# 4) 在文件头部登记本次清理与稳定性不变式
marker = "# --- Cold Startup Optimization ---"
note = ("# =====================================================================\n"
        "# [r3 清理 2026-10-10，缺陷 D48] 按声明位核对 151/155/156 三个版本后，\n"
        "# 删除 6 条在上游根本不存在、因而一直被 Chromium 静默忽略的条目：\n"
        "#   CanvasOopRasterization / DirectComposition / EarlyData / AVIF /\n"
        "#   SpeculationRules / ServiceWorkerNavigationPreload\n"
        "# 删除不改变当前版本行为（它们在 M151 上本就无操作）。\n"
        "# 稳定性不变式：本文件每条 feature 都必须在 151、155、156 三版全部声明存在，\n"
        "# 唯一例外是上面标注 [升级期处置] 的 FlingSchedulingImprovements。\n"
        "# 校验脚本：python .bugreview/flag_stability.py（升级后必须重跑）。\n"
        "# =====================================================================\n"
        "\n")
if "# [r3 清理 2026-10-10，缺陷 D48]" not in s:
    s = s.replace(marker, note + marker, 1)

io.open(PATH, "w", encoding="utf-8", newline="\n").write(s)
print("mcloud_flags.txt 已按 D48 清理（删除 6 条 / 改名转注释 1 条 / 升级期标记 1 条）")
