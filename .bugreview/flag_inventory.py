#!/usr/bin/env python3
"""flag_inventory.py - parse mcloud_flags.txt into a machine-readable inventory.

Output (stdout JSON): features_enable / features_disable / plain_switches /
v8_inner_flags, plus an alternation regex usable by `git grep -E`.
Cross-checks the AGENTS.md claim: 63 effective lines = 60 feature lines + 3 plain.
"""
import json
import re
import sys

FLAGS = r"d:\wxmuma\thorium\mcloud_flags.txt"

feat_en, feat_dis, plain, v8_inner = [], [], [], []
effective = 0

for raw in open(FLAGS, encoding="utf-8"):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    effective += 1
    m = re.match(r"^--(enable|disable)-features=(.+)$", line)
    if m:
        # a single line may carry a comma-separated list; strip ":param" suffixes
        for item in m.group(2).split(","):
            name = item.strip().split(":")[0].strip()
            if name:
                (feat_en if m.group(1) == "enable" else feat_dis).append(name)
        continue
    m = re.match(r"^--js-flags=\"?(.*?)\"?$", line)
    if m:
        plain.append("--js-flags")
        v8_inner = [t.lstrip("-").split("=")[0] for t in m.group(1).split() if t.startswith("-")]
        continue
    m = re.match(r"^(--[a-z0-9][a-z0-9-]*)", line)
    if m:
        plain.append(m.group(1).lstrip("-"))

# de-dup, keep order
uniq = lambda xs: list(dict.fromkeys(xs))
feat_en, feat_dis, plain, v8_inner = map(uniq, (feat_en, feat_dis, plain, v8_inner))

print(json.dumps({
    "effective_lines": effective,
    "feature_lines": len(feat_en) + len(feat_dis),
    "features_enable": feat_en,
    "features_disable": feat_dis,
    "plain_switches": plain,
    "v8_inner_flags": v8_inner,
}, indent=2, ensure_ascii=False))

if "--features-grep-regex" in sys.argv:
    names = uniq(feat_en + feat_dis)
    print("|".join(re.escape(n) for n in sorted(names)))
