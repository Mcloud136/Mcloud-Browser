"""
LEGACY — 已禁用（bug-review 2026-10-08，缺陷 D28）。

trunk.py 会 git checkout -f origin/main 整树重置并使用被永久禁用的
gclient sync --force --reset --delete_unversioned_trees 组合
（2026-08-06 事故实证；升级报告偏差 1 已改用定向浅拉取）。
正确流程见 AGENTS.md / docs/REBASING.md。
"""

import sys


def main():
    print("trunk.py 已禁用（LEGACY，缺陷 D28）。", file=sys.stderr)
    print("内核升级请使用：git fetch --depth 1 origin tag <tag> + "
          "win_scripts/deploy_mcloud.py（见 AGENTS.md）。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
