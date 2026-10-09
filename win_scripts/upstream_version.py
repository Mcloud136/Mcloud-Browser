"""
LEGACY — 已禁用（bug-review 2026-10-08，缺陷 D28）。

upstream_version.py 使用被永久禁用的
gclient sync --force --reset --nohooks --delete_unversioned_trees 组合
（2026-08-06 事故实证：清除全部定制与 buildtools/win）。
正确流程见 AGENTS.md：浅拉取 tag + deploy_mcloud.py 定点幂等部署。
"""

import sys


def main():
    print("upstream_version.py 已禁用（LEGACY，缺陷 D28）。", file=sys.stderr)
    print("请使用 AGENTS.md 升级流程。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
