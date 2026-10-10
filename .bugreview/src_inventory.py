#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 src/INVENTORY.md：仓库 src/ 下每个文件「是否真的参与构建」的权威清单。

为什么需要它（缺陷 D77，2026-10-10 第3周期实测）：
  仓库 src/ 有 590 个文件，其中 345 个与 M155 构建树的同名文件内容不同，
  而构建流水线只应用其中 1 个（copy_essentials.py 白名单里的
  build/config/compiler_opt.gni）。也就是说绝大多数 src/ 副本是惰性遗留：
  改它们不会有任何效果，也不会报错。实测还发现这些副本的新旧状态不一致——
  build/config/BUILDCONFIG.gn 与 compiler/BUILD.gn 的副本里带着上一代内核注入的
  polly/avx2 痕迹，而 build/config/win/BUILD.gn 的副本没有。任何人（或 AI Agent）
  拿仓库副本去和树内文件对比，都会得出错误结论（本项目历史上真的因此误判过）。

用法：
  python .bugreview/src_inventory.py [--tree <构建树 src>] [--write]
  默认 --tree 取 $env:CR_DIR_155，再退回 D:/wxmuma/chromium-src-155/src。
  不加 --write 只打印摘要（便于门禁做回归：文件数/差异数变化即提醒）。
"""
import argparse
import hashlib
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")


def applied_map():
    """从 win_scripts 源码里解析出实际被使用的仓库 src/ 路径。

    类别：
      copy —— 由 copy_essentials.py 整份复制进树（只允许「无上游对应物」的文件）
      inject-target —— 注入脚本的目标文件；仓库同名副本本身不参与构建
    """
    used = {}
    ce = os.path.join(REPO, "win_scripts", "copy_essentials.py")
    if os.path.isfile(ce):
        text = io.open(ce, encoding="utf-8").read()
        for m in re.finditer(r'"(src/[^"]+)"', text):
            used[m.group(1)[len("src/"):]] = "copy"
    inj = os.path.join(REPO, "win_scripts", "inject_flags_loader.py")
    if os.path.isfile(inj):
        used.setdefault("chrome/app/chrome_main_delegate.cc",
                        "inject-target（副本不生效）")
    return used


def sha12(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def classify(tree):
    used = applied_map()
    rows = []
    for dirpath, dirnames, filenames in os.walk(SRC):
        dirnames.sort()
        for f in sorted(filenames):
            if f == "INVENTORY.md":
                continue          # 本清单自身不计入，否则每次重生成计数会漂 1
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, SRC).replace(os.sep, "/")
            t = os.path.join(tree, rel.replace("/", os.sep))
            state = "无上游对应物（仓库独有）"
            if os.path.isfile(t):
                state = ("与树内一致" if io.open(p, "rb").read() ==
                         io.open(t, "rb").read() else "与树内不同")
            rows.append({"rel": rel, "state": state,
                         "used": used.get(rel, "unused"),
                         "sha_repo": sha12(p),
                         "sha_tree": sha12(t) if os.path.isfile(t) else "-"})
    return rows


def summarize(rows):
    return {
        "total": len(rows),
        "only_repo": sum(1 for r in rows if r["state"].startswith("无上游")),
        "same": sum(1 for r in rows if r["state"] == "与树内一致"),
        "diff": sum(1 for r in rows if r["state"] == "与树内不同"),
        "applied": [r for r in rows if r["used"] != "unused"],
        "inert_diff": [r for r in rows
                       if r["state"] == "与树内不同" and r["used"] == "unused"],
    }


def render(rows, tree):
    s = summarize(rows)
    o = []
    o.append("# src/ 参与度清单（自动生成，勿手工编辑）")
    o.append("")
    o.append("生成命令：`python .bugreview/src_inventory.py --write`")
    o.append("")
    o.append("对照的构建树：`%s`" % tree)
    o.append("")
    o.append("## 结论")
    o.append("")
    o.append("- 仓库 `src/` 共 **%d** 个文件。" % s["total"])
    o.append("- 树内没有对应路径（真正的仓库独有资产）：**%d**。" % s["only_repo"])
    o.append("- 与树内同名文件字节一致：**%d**；内容不同：**%d**。" % (s["same"], s["diff"]))
    o.append("- 被构建流水线实际使用的仓库 `src/` 文件：**%d** 个（见下表示）。"
              % len(s["applied"]))
    o.append("- 与树内不同、却没有任何脚本读取或复制它们的：**%d** 个 —— 修改这些文件"
              "**不会生效、也不会报错**（缺陷 D77）。" % len(s["inert_diff"]))
    o.append("")
    o.append("> 所以：仓库 `src/` **不是**「当前生效的修改集」，而是一份含大量旧内核快照的")
    o.append("> 素材目录。要改上游文件，请在 `win_scripts/` 下写定点幂等脚本（`apply_*` /")
    o.append("> `inject_*`）并由 `deploy_mcloud.py` 编排；不要把仓库副本加进")
    o.append("> `copy_essentials.py` 的整份复制清单——那里的白名单会直接拒绝有上游对应物的")
    o.append("> 条目（缺陷 D41）。")
    o.append("")
    o.append("## 实际参与构建的仓库 src/ 文件")
    o.append("")
    o.append("| 文件 | 使用方式 | 与对照树比对 |")
    o.append("|------|----------|--------------|")
    for r in sorted(s["applied"], key=lambda x: x["rel"]):
        o.append("| `src/%s` | %s | %s |" % (r["rel"], r["used"], r["state"]))
    if not s["applied"]:
        o.append("| （无） | — | — |")
    o.append("")
    o.append("## 与树内不同、且无人使用的副本（前 60 条，按路径序）")
    o.append("")
    o.append("这些是历史遗留快照（多为旧内核基线，含上一代注入痕迹）。列在这里只为回答")
    o.append("「这个文件到底有没有用」——答案是：没有。")
    o.append("")
    o.append("```")
    for r in sorted(s["inert_diff"], key=lambda x: x["rel"])[:60]:
        o.append("src/%s  repo=%s tree=%s" % (r["rel"], r["sha_repo"], r["sha_tree"]))
    if len(s["inert_diff"]) > 60:
        o.append("... 另有 %d 条" % (len(s["inert_diff"]) - 60))
    o.append("```")
    o.append("")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=os.environ.get(
        "CR_DIR_155", r"D:\wxmuma\chromium-src-155\src"))
    ap.add_argument("--write", action="store_true", help="写出 src/INVENTORY.md")
    args = ap.parse_args()
    if not os.path.isdir(args.tree):
        print("FAIL: 构建树不存在：%s（用 --tree 指定）" % args.tree)
        return 2
    rows = classify(args.tree)
    if not rows:
        print("FAIL: src/ 下未发现任何文件（扫描器失效，不能当作通过）")
        return 1
    s = summarize(rows)
    print("src/ 总数=%d 仓库独有=%d 与树一致=%d 与树不同=%d 实际被使用=%d 惰性差异副本=%d"
          % (s["total"], s["only_repo"], s["same"], s["diff"],
             len(s["applied"]), len(s["inert_diff"])))
    if args.write:
        doc = os.path.join(SRC, "INVENTORY.md")
        io.open(doc, "w", encoding="utf-8", newline="\n").write(
            render(rows, args.tree))
        print("written: %s" % doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
