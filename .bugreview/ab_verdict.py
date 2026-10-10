#!/usr/bin/env python3
"""ab_verdict.py - 按**预先定死的判定标准**把 ab_results.json 转成采纳/撤回结论。

判定标准写在这里而不是看完数据再定，避免事后找理由（见 docs/tasks/m155-perf-features.md §5.1 第 6 条）。

噪声带：取基线自身 K1 的 5 轮散布 (max-min)/2，下限 3 ms。K2/泄漏用固定相对阈值。

规则：
  否决（任一命中）：
    · K1 比基线慢 > max(3, 噪声带) ms
    · K2 比基线高 > 2%
    · 泄漏漂移比基线差 > 5 MB
    · GPU 探针显示 gpu-process 丢失 或 出现 SwiftShader/Vulkan 回退
  采纳（未被否决且至少一项超出噪声带）：
    · K1 快 ≥ max(3, 噪声带) ms，或 K2 低 ≥ 3%，或 泄漏漂移好 ≥ 5 MB
  其余：无差异 → 不采纳。
  特例：SkiaGraphite 属窗口拖拽冻结缓解定案（4 项永久禁用之一），
        只出数据，不据此自动撤销，需用户人工复现拖拽+视频场景后再决定。
"""
import json
import os
import sys

THOR = r"d:\wxmuma\thorium"
ALWAYS_DISABLED = ("SkiaGraphite",)          # 定案项：数据不自动改判


def verdict():
    path = os.path.join(THOR, ".bugreview", "ab_results.json")
    rows = json.load(open(path, encoding="utf-8"))
    base = next(r for r in rows if r["label"].startswith("("))
    band = max(3.0, (max(base["k1_raw"]) - min(base["k1_raw"])) / 2.0) if base.get("k1_raw") else 3.0
    out = ["基线 K1=%s ms（原始 %s）→ 噪声带 ±%.1f ms；K2=%s MB；泄漏漂移=%s MB"
           % (base["k1_ms"], base["k1_raw"], band, base["k2_mb"], base["leak_drift_mb"])]
    for r in rows:
        if r is base or "skipped" in r or r.get("k1_ms") is None:
            if "skipped" in r:
                out.append("%-42s 跳过：%s" % (r["label"], r["skipped"]))
            continue
        dk1 = r["k1_ms"] - base["k1_ms"]
        dk2pct = 100.0 * (r["k2_mb"] - base["k2_mb"]) / base["k2_mb"]
        dlk = r["leak_drift_mb"] - base["leak_drift_mb"]
        g = r.get("gpu") or {}
        gb = base.get("gpu") or {}
        gpu_bad = (not g.get("gpu-process 存在")) or \
                  (g.get("Vulkan/SwiftShader 回退") and not gb.get("Vulkan/SwiftShader 回退"))
        veto = []
        if dk1 > band:
            veto.append("K1 慢 %.0f ms（>%.1f）" % (dk1, band))
        if dk2pct > 2.0:
            veto.append("K2 涨 %.1f%%" % dk2pct)
        if dlk > 5.0:
            veto.append("泄漏差 %.1f MB" % dlk)
        if gpu_bad:
            veto.append("GPU 回退/掉进程")
        gain = []
        if dk1 <= -band:
            gain.append("K1 快 %.0f ms" % -dk1)
        if dk2pct <= -3.0:
            gain.append("K2 省 %.1f%%" % -dk2pct)
        if dlk <= -5.0:
            gain.append("泄漏好 %.1f MB" % -dlk)
        if veto:
            call = "撤回"
        elif gain:
            call = "采纳"
        else:
            call = "无差异（不采纳）"
        if any(a in r["label"] for a in ALWAYS_DISABLED):
            call += "｜定案项：不据此自动撤销，需人工拖拽复现"
        out.append("%-42s K1 %+5.0f ms / K2 %+6.1f%% / 泄漏 %+5.1f MB → %s%s"
                   % (r["label"], dk1, dk2pct, dlk, call,
                      ("（" + "; ".join(veto) + "）") if veto else
                      ("（" + "; ".join(gain) + "）" if gain else "")))
    text = "\n".join(out)
    with open(os.path.join(THOR, ".bugreview", "ab_verdict.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(verdict())
