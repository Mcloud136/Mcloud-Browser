#!/usr/bin/env python3
"""name_archaeology.py - 对失效条目找后继/毕业证据，并顺带产出候选新特性。

对每个关键词，在 151 与 155 的 feature 声明位里找包含该关键词的 kIdent，
读取声明块判定上游默认状态，输出 "151 有/无 -> 155 有/无 + 默认" 便于判断
失效条目属于"改名/毕业/删除"，同时暴露可评估的性能候选。
"""
import re
import subprocess
import sys

SRC = r"D:\wxmuma\chromium-src\src"
KINDS = "BASE_FEATURE|BASE_DECLARE_FEATURE|DEFINE_FEATURE|UNI_FEATURE|FEATURE"
PY_DECL = re.compile("(" + KINDS + r")\s*\(\s*(k[A-Za-z0-9_]+)"
                    r"(?:\s*,\s*\"([^\"]+)\")?([^;]{0,240})")
DEF_RE = re.compile(r"(FEATURE_[A-Z_]+_BY_DEFAULT|feature_default::k[A-Za-z]+)")
KEYWORDS = sys.argv[1:] or ["CanvasOop", "AVIF", "Speculation", "NavigationPreload",
                           "EarlyData", "DirectComposi", "Fling", "TaskInhibiting"]


def scan(rev):
    out = subprocess.run(
        ["git", "-C", SRC, "grep", "-I", "-h", "-A2", "-E",
         "(" + KINDS + ")[[:space:]]*\\([[:space:]]*k[A-Za-z0-9_]+",
         rev, "--", "*.cc", "*.h", "*.mm"],
        capture_output=True, text=True, errors="replace").stdout
    found = {}
    for blk in re.split(r"(?m)^--$", out):
        joined = " ".join(ln.strip() for ln in blk.splitlines())
        for m in PY_DECL.finditer(joined):
            ident, rest = m.group(2), m.group(4) or ""
            d = DEF_RE.search(rest)
            default = d.group(1) if d else "?"
            found.setdefault(ident, default)
    return found


res = {rev: scan(rev) for rev in ("151.0.7922.99", "155.0.8059.40")}
if "--dump" in sys.argv:
    import json
    json.dump({r: res[r] for r in res}, open(r"d:\wxmuma\thorium\.bugreview\declared_features_151_155.json",
              "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    a, b = res["151.0.7922.99"], res["155.0.8059.40"]
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    PERF = ("Prefetch", "Preconnect", "Prerender", "Speculat", "Cache", "Raster", "Compositor",
            "Thread", "Priority", "Jit", "JIT", "Maglev", "Turbofan", "Sparkplug", "Discard",
            "Freeze", "Memory", "Zero", "Copy", "Snap", "Decode", "Encoder", "Dns", "DNS",
            "TLS", "EarlyData", "Http", "HTTP", "Quic", "QUIC", "Startup", "Launch", "Scroll",
            "Fling", "Input", "Latency", "Throttle", "Idle", "Schedul", "Prewarm", "Warm",
            "Inline", "Compil", "Optimiz", "Parallel", "Async", "Batch", "Pool", "Reuse")
    perf_added = [k for k in added if any(p in k for p in PERF)]
    print("155 新增声明 %d 个，155 移除 %d 个，其中含性能关键词的新增 %d 个"
          % (len(added), len(removed), len(perf_added)))
    for k in perf_added:
        print("   +%-56s 155默认=%s" % (k, b[k]))
    print("--- 155 移除（仅列含性能关键词，用于失效归因）---")
    for k in removed:
        if any(p in k for p in PERF):
            print("   -%-56s 151默认=%s" % (k, a[k]))
    sys.exit(0)
for kw in KEYWORDS:
    a = {k: v for k, v in res["151.0.7922.99"].items() if kw in k}
    b = {k: v for k, v in res["155.0.8059.40"].items() if kw in k}
    print("### 关键词 %s" % kw)
    for k in sorted(set(a) | set(b)):
        in151 = "151:%s" % a[k] if k in a else "151:—"
        in155 = "155:%s" % b[k] if k in b else "155:已无"
        print("   %-52s %-34s %s" % (k, in151, in155))
