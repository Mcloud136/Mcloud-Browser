"""
LEGACY — 已禁用（bug-review 2026-10-08，缺陷 D28）。

tot.py 使用 git checkout -f 与永久禁用的
gclient sync --force --reset --delete_unversioned_trees 组合。
本项目遵循稳定版节奏升级（规范 9.1），不使用 ToT 同步脚本。
"""

import sys


def main():
    print("tot.py 已禁用（LEGACY，缺陷 D28）。", file=sys.stderr)
    print("请使用 AGENTS.md 升级流程（稳定版 tag + deploy_mcloud.py）。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
