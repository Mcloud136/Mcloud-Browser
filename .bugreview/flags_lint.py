#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flags_lint.py — mcloud_flags.txt 静态闸门（防"整份清单静默失效"）。

为什么需要这个脚本（缺陷 D59，2026-10-12）：
  加载器（win_scripts/inject_flags_loader.py 的 LOADER v8）按行解析，**只跳过整行
  注释**（行首 `#`），不剥离行尾注释。于是

      --enable-features=BackForwardCache   # pin: 上游默认已启用

  被解析成 switch 值 `BackForwardCache   # pin: 上游默认已启用`，feature 名里带空格
  与中文 → FeatureList 无法匹配 → **整串 enable-features 被拒**。实测后果：
  运行时 override 从 50 项掉到 1 项，全部性能优化无声失效，而构建、安装、门禁全绿
  （同 D48/D57 一族：失效不可见）。

  本闸门在 CI 与发布前拦住这类写法，也顺带查重复名、非法字符与未知 feature。

用法：
    python .bugreview/flags_lint.py                     # 校验仓库根 mcloud_flags.txt
    python .bugreview/flags_lint.py --file <path>
    python .bugreview/flags_lint.py --stab .bugreview/stab_155.json   # 追加 feature 存在性核对
退出码：0 = PASS，1 = FAIL
"""
import argparse
import io
import json
import os
import re
import sys

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(THOR, "mcloud_flags.txt")

# feature 名：字母开头，只允许字母数字与下划线（Chromium BASE_FEATURE 命名惯例）。
# 参数段（冒号后）单独校验，允许 / 与更多的字符。
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SWITCH_RE = re.compile(r"^--([A-Za-z0-9_-]+)(=(.*))?$")


def parse(path):
    """返回 (entries, inline_comment_lines)。entries = [(lineno, raw, name_or_switch, value)]"""
    entries = []
    inline = []
    with io.open(path, encoding="utf-8") as fh:
        for i, raw in enumerate(fh.read().split("\n"), start=1):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if not s.startswith("--"):
                continue
            # D59 核心：开关行里出现 '#' 即行尾注释（引号内的 # 也可能，但本清单
            # 只有 --js-flags 带引号且其值不含 #，故直接判定为致命）。
            if "#" in s:
                inline.append((i, raw.rstrip()))
            m = SWITCH_RE.match(s)
            if not m:
                inline.append((i, raw.rstrip() + "   <-- 无法解析为 switch"))
                continue
            entries.append((i, s, m.group(1), m.group(3) or ""))
    return entries, inline


def check_names(entries):
    """feature 名合法性 + 重复检测。返回 (errors, warnings)。"""
    errors, warnings = [], []
    seen = {}
    for lineno, raw, switch, value in entries:
        if switch not in ("enable-features", "disable-features"):
            continue
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            name = item.split(":", 1)[0].strip()
            params = item.split(":", 1)[1] if ":" in item else None
            if not NAME_RE.match(name):
                errors.append(
                    "L%d: feature 名非法 %r（含空格/中文/标点会被 FeatureList 整串拒绝，"
                    "进而使全部条目失效）：%s" % (lineno, name, raw))
            if params is not None and not params.strip():
                warnings.append(
                    "L%d: %s 带了空参数段（参数语法为 param/value，见 D51）" % (lineno, name))
            if name in seen:
                errors.append("L%d: feature 重复声明 %s（首次出现于 L%d）"
                              % (lineno, name, seen[name]))
            else:
                seen[name] = lineno
    return errors, warnings


def check_against_stab(entries, stab_path):
    """对照 stab 清单核对 feature 是否在内核中真实声明。调用方已保证文件存在。"""
    msgs = []
    with io.open(stab_path, encoding="utf-8") as fh:
        stab = json.load(fh)
    known = {f["name"] for f in stab.get("features", [])}
    unknown_default = {f["name"]: f.get("default", "")
                       for f in stab.get("features", [])}
    for lineno, _raw, switch, value in entries:
        if switch not in ("enable-features", "disable-features"):
            continue
        for item in value.split(","):
            name = item.split(":", 1)[0].strip()
            if not name:
                continue
            if name not in known:
                msgs.append("L%d: %s 在 %s 中未声明（会被 Chromium 静默忽略，同 D48）"
                            % (lineno, name, os.path.basename(stab_path)))
            elif switch == "enable-features" and \
                    unknown_default.get(name) == "FEATURE_ENABLED_BY_DEFAULT":
                # 非致命：钉住（pin）是有意的，但必须是显式注释说明过的。
                msgs.append("L%d: note %s 上游默认已启用，本行为 pin（净效果为零，见 D171）"
                            % (lineno, name))
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--stab", default=None,
                    help="可选：stab_<ver>.json，追加 feature 存在性核对")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print("flags_lint: 找不到 %s" % args.file, file=sys.stderr)
        return 1

    entries, inline = parse(args.file)
    errors, warnings = check_names(entries)

    print("flags_lint: %s" % args.file)
    print("  开关条目：%d" % len(entries))

    if inline:
        print("\n[FATAL] 行尾注释 / 不可解析行（%d）——加载器不剥离行尾注释，"
              "会让整串 feature 静默失效（D59）：" % len(inline))
        for lineno, raw in inline:
            print("    L%d: %s" % (lineno, raw))
        errors.append("行尾注释 %d 处" % len(inline))

    if errors:
        print("\n[FAIL] %d 个致命问题" % len(errors))
        for e in errors:
            if not e.startswith("行尾注释"):
                print("    " + e)
        return 1

    notes = []
    if args.stab:
        # 缺文件不得算通过：核对没执行 ≠ 全部声明存在（同 D89/D138 一族，"量具取不到
        # 数据必须硬失败"）。此前这里会把"找不到 stab 文件"降级成一句 note，
        # 然后照样印"全部声明存在"并返回 0（缺陷 D176）。
        if not os.path.isfile(args.stab):
            print("\n  [FAIL] 找不到 stab 文件：%s —— 存在性核对未执行，不得判为通过"
                  % args.stab)
            return 1
        notes = check_against_stab(entries, args.stab)
        fatal = [m for m in notes if "未声明" in m]
        print("\n  存在性核对（%s）：%s" % (os.path.basename(args.stab),
                                            "全部声明存在" if not fatal else "%d 项未声明" % len(fatal)))
        for m in fatal:
            print("    [FAIL] " + m)
        pins = [m for m in notes if m.startswith("L") and " note " in m]
        if pins:
            print("  pin 项（上游默认已启用，净效果为零）：%d" % len(pins))
        if fatal:
            return 1

    for w in warnings:
        print("  [WARN] " + w)
    print("\n[PASS] flags 清单静态检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
