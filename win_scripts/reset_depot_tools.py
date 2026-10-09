# Copyright (c) 2026 Alex313031, midzer and gz83.
#
"""
LEGACY — 已禁用（bug-review 2026-10-08，缺陷 D37/D28 同族）。

本脚本会删除 DEPOT_TOOLS_DIR 指向的整个目录并从 googlesource 重克隆最新
master——直接破坏本项目"depot_tools 固定修订版本"策略（仓库内 depot_tools/
与根目录 gclient/g 文件即为固定版本资产）。另有边界风险：DEPOT_TOOLS_DIR
若配置为盘根带尾斜杠（如 "D:\"），`del /S /Q "D:\\\*"` 将清空整个盘；删除
失败后仍会继续 clone，可能造成半删状态。

如确需重置 depot_tools：手动移走旧目录后按项目固定修订重新拉取，或参考
depot_tools/DEPOT_TOOLS_REVISION 记录版本，不要使用本脚本。
"""

import sys


def main():
    print("reset_depot_tools.py 已禁用（LEGACY，缺陷 D37）。", file=sys.stderr)
    print("本项目 depot_tools 为固定修订版本，禁止整目录删除+重克隆 master。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
