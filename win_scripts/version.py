# Copyright (c) 2026 Alex313031 and gz83.

"""
LEGACY — 已禁用（bug-review 2026-10-08，缺陷 D28）。

原脚本为 M144 时代升级入口：固定旧 tag、复制已不存在的 mcloud-libjxl DEPS、
使用被永久禁用的 gclient sync --force --reset --delete_unversioned_trees
组合（2026-08-06 事故实证会清除全部定制与 buildtools/win），结尾还引导运行
已废弃的 setup.py。保留文件仅为历史参考，运行会被拒绝。

正确升级流程（AGENTS.md / docs/REBASING.md）：
  git fetch --depth 1 origin tag <目标tag>  ->  checkout  ->  gclient sync
  （不带 force/reset/delete_unversioned_trees 组合）  ->  gclient runhooks
  ->  python3 win_scripts/deploy_mcloud.py  ->  gn gen --check  ->  autoninja
"""

import sys


def main():
    print("version.py 已禁用（LEGACY，缺陷 D28）。", file=sys.stderr)
    print("请使用 AGENTS.md 的升级流程：定向浅拉取 tag + "
          "win_scripts/deploy_mcloud.py 定点部署。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
