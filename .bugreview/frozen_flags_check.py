#!/usr/bin/env python3
"""frozen_flags_check.py - 复核"窗口拖拽冻结缓解"4 项禁用标志与 GPU 相关项在 151→155 的默认状态。

若某项在 151 是默认禁用、到 155 变成默认启用，那么仅靠"我们没写进 flags"已经不够，
必须显式 --disable-features 才能维持既有定案（用户已确认有效并固化为禁用）。
同时反向检查：我们在 r3 里 --enable-features 的 GPU 相关项，上游默认是否已变。
"""
import re
import subprocess
import sys

SRC = r"D:\wxmuma\chromium-src\src"
KINDS = "BASE_FEATURE|BASE_DECLARE_FEATURE|DEFINE_FEATURE|UNI_FEATURE|FEATURE"
GIT_DECL = "(" + KINDS + ")[[:space:]]*\\([[:space:]]*k[A-Za-z0-9_]+"
PY_DECL = re.compile("(" + KINDS + r")\s*\(\s*(k[A-Za-z0-9_]+)"
                     r"(?:\s*,\s*\"([^\"]+)\")?([^;]{0,220})")
DEF_RE = re.compile(r"(FEATURE_[A-Z_]+_BY_DEFAULT|feature_default::k[A-Za-z]+)")

MUST_STAY_DISABLED = ["SkiaGraphite", "SkiaGraphitePrecompilation",
                      "ThrottleUnimportantFrameRate",
                      "ReduceHardwareVideoDecoderBuffers"]
GPU_ORIENTED = ["GpuShaderDiskCache", "IncreasedCmdBufferParseSlice",
                "ResourcePoolPreferExactSizeReuse", "HighFramerateRequestFromClient",
                "EnableGpuRasterization", "DefaultEnableGpuRasterization",
                "DirectCompositionResizeFixes", "DirectCompositionSoftwareOverlays",
                "DirectCompositionUnlimitedOverlays", "VizDirectCompositorThreadIpcNonRoot",
                "VizDirectCompositorThreadIpcFrameSinkManager",
                "QueuedCompositorWebContentsUpdates", "ReuseScanoutRenderPassBacking",
                "CanvasOopRasterization", "GpuMemoryBufferVideoFrames"]


def decl_map(rev):
    out = subprocess.run(["git", "-C", SRC, "grep", "-I", "-h", "-A2", "-E", GIT_DECL,
                          rev, "--", "*.cc", "*.h", "*.mm"],
                         capture_output=True, text=True, errors="replace").stdout
    m = {}
    for blk in re.split(r"(?m)^--$", out):
        joined = " ".join(ln.strip() for ln in blk.splitlines())
        for mm in PY_DECL.finditer(joined):
            ident, rest = mm.group(2), mm.group(4) or ""
            d = DEF_RE.search(rest)
            m.setdefault(ident[1:], d.group(1) if d else "")
    return m


maps = {rev: decl_map(rev) for rev in ("151.0.7922.99", "155.0.8059.40", "156.0.8078.12")}


def short(v):
    if v is None:
        return "NO-DECL"
    if "ENABLED" in v:
        return "default-ENABLED"
    if "DISABLED" in v:
        return "default-DISABLED"
    return v or "decl-without-default"


bad = []
print("A) MUST-STAY-DISABLED (freeze mitigation, 4 items)")
for n in MUST_STAY_DISABLED:
    row = [maps[r].get(n) if n in maps[r] else None for r in maps]
    txt = "  ".join("%s=%s" % (r.split(".")[0], short(v)) for r, v in zip(maps, row))
    print("  %-36s %s" % (n, txt))
    if "ENABLED" in (row[1] or "") or "ENABLED" in (row[2] or ""):
        bad.append("%s 在 M155/156 已默认启用 → 需显式 --disable-features 才能维持定案" % n)
    if row[1] is None:
        bad.append("%s 在 M155 已无声明 → 该缓解项在上游消失，需重新评估冻结问题是否仍复现" % n)

print("\nB) GPU 取向相关项的默认状态漂移")
for n in GPU_ORIENTED:
    row = [maps[r].get(n) if n in maps[r] else None for r in maps]
    if all(v is None for v in row):
        continue
    ch = "CHANGED" if (short(row[0]) != short(row[1])) else "same"
    print("  %-40s 151=%-9s 155=%-9s 156=%-9s %s"
          % (n, short(row[0]), short(row[1]), short(row[2]), ch))

print("\n判定:", "PASS — 定案仍成立（4 项在 155/156 仍默认禁用或已不存在但需复核）" if not bad else "需要动作")
for b in bad:
    print("  !!", b)
