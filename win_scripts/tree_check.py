# 源码树身份断言（第7周期，缺陷 D186）。
#
# 为什么需要：win_scripts 里 `CR_DIR` 的默认值指向 **M151 回滚参考树**
# （r"D:\wxmuma\chromium-src\src"），而本机同时存在 chromium-src（M151）与
# chromium-src-155（发布树）。忘记设 CR_DIR 时，注入脚本会在**旧树**上找到同名文件、
# 成功改写、打印 "already up to date"，而编译与发布用的是另一棵树 —— 定制静默丢失。
# 这个坑 2026-10-10 真踩过（全部步骤幂等所以未致损），AGENTS.md 把它写成了一条"要记得"
# 的约定。约定会被忘记，所以改成机器判定。
#
# 用法（在注入脚本开头调用）：
#     from tree_check import require_tree
#     SRC = require_tree(os.environ.get("CR_DIR") or DEFAULT)
#
# 内核升级 rebase 时必须同步改 KERNEL_MAJOR（见 docs/REBASING.md / 记忆 mcloud-rebase）。
import io
import os
import re
import sys

KERNEL_MAJOR = 155          # 本仓库当前定制所依附的上游内核主版本
KERNEL_VERSION = "155.0.8059.40"

# 默认树历史上写死的是 M151 回滚参考树；这里保留同样的默认，但**不再让它悄悄通过**。
M151_MARKERS = (r"D:\wxmuma\chromium-src\src", "D:/wxmuma/chromium-src/src")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def read_version(src):
    """读 <src>/chrome/VERSION 的 MAJOR/MINOR，返回 (major, version_string)。"""
    p = os.path.join(src, "chrome", "VERSION")
    if not os.path.isfile(p):
        return None, None
    kv = {}
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^([A-Z_]+)\s*=\s*(\S+)", line)
            if m:
                kv[m.group(1)] = m.group(2)
    major = kv.get("MAJOR")
    ver = ".".join([kv.get(k, "?") for k in ("MAJOR", "MINOR", "BUILD", "PATCH")])
    return (int(major) if major and major.isdigit() else None), ver


def require_tree(src, script_name=""):
    """校验 src 是预期内核版本的源码树；不符即退出码 114，除非显式放行。"""
    tag = ("%s: " % script_name) if script_name else ""
    if not os.path.isdir(src):
        print("%sERROR: 源码树目录不存在：%s" % (tag, src), file=sys.stderr)
        return 114
    major, ver = read_version(src)
    if major is None:
        print("%sERROR: %s 下读不到 chrome/VERSION —— 它不是 Chromium 源码树，"
              "不要在没有身份确认的树上做注入" % (tag, src), file=sys.stderr)
        return 114
    if major != KERNEL_MAJOR:
        allowed = os.environ.get("MCLOUD_ALLOW_TREE_MISMATCH") == "1"
        looks_m151 = os.path.normpath(src).lower() in [os.path.normpath(m).lower()
                                                      for m in M151_MARKERS]
        print("%sERROR: 源码树身份不符：期望 M%d（%s），实测 M%d（%s）@%s"
              % (tag, KERNEL_MAJOR, KERNEL_VERSION, major, ver, src), file=sys.stderr)
        if looks_m151:
            print("       这正是 **M151 回滚参考树**。定制必须落在当前发布树上，否则编译产物"
                  "不含改动而脚本照样自称成功（第7周期 D186）。", file=sys.stderr)
        print("   修法：设 CR_DIR 指向当前发布树后重跑，例如 "
              "set CR_DIR=D:\\wxmuma\\chromium-src-155\\src", file=sys.stderr)
        if not allowed:
            print("   确需在别的树上运行（例如升级 pre-assessment）："
                  "set MCLOUD_ALLOW_TREE_MISMATCH=1", file=sys.stderr)
            return 114
        print("%sWARN: 已用 MCLOUD_ALLOW_TREE_MISMATCH=1 放行，结果归属请自行记录" % tag,
              file=sys.stderr)
    print("%s源码树：M%d（%s）@%s" % (tag, major, ver, src))
    return 0
