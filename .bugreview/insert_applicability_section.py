#!/usr/bin/env python3
"""insert_applicability_section.py - 把 candidate_applicability.txt 转成 §1.1 表格插入 perf 文档。"""
import io
import re

DOC = r"d:\wxmuma\thorium\docs\tasks\m155-perf-features.md"
RAW = r"d:\wxmuma\thorium\.bugreview\candidate_applicability.txt"

raw = io.open(RAW, "rb").read().decode("gbk", errors="replace")  # 探针输出经 GBK stdout 重定向
blocks = []
for ln in raw.splitlines():
    m = re.match(r"^(k[A-Za-z0-9_]+)\s+\D*(\d+)\D*(\d+)", ln)
    if m:
        blocks.append([(m.group(1), int(m.group(2)), int(m.group(3))), []])
    elif blocks and "·" in ln:
        f = ln.split("·")[-1].strip()
        if "/" in f:
            blocks[-1][1].append(f)


def classify(files):
    impl, ft, android = [], False, 0
    for f in files:
        if "fieldtrial_testing_config.json" in f:
            ft = True
        elif "_unittest" in f or "_browsertest" in f or "_test." in f:
            continue
        elif "/android/" in f or "android_webview" in f or f.endswith(".java"):
            android += 1
        else:
            impl.append(f)
    return impl, ft, android


lines = [
    "## 1.1 适用性核实（M155 真实引用点，实测于 `155.0.8059.40` 对象库）",
    "",
    "方法：按**去 k 的名字**检索。消费者普遍调用 `Is<Name>Enabled()` 辅助函数，"
    "只搜 `k<Name>` 会漏报（本探针第一版就因此把 `VizDirectCompositorThreadIpcNonRoot` 误判成"
    "仅声明，已纠正）。剔除单测/浏览器测试文件后看剩余实现引用，并检查上游是否注册了 field trial。",
    "",
    "| 候选（去掉 k 前缀） | 引用文件数 | 主要实现引用 | 上游 field trial | 桌面可达性判定 |",
    "|---|---|---|---|---|",
]
for (k, ntot, _nuse), files in blocks:
    impl, ft, android = classify(files)
    main = ", ".join("`%s`" % f for f in impl[:2]) if impl else "（仅声明/头文件）"
    if impl:
        verdict = "✅ 有跨平台实现引用，桌面可达"
    elif android:
        verdict = "❌ 仅 Android 引用"
    else:
        verdict = "⚠️ 未见实现引用，启用前需再查"
    lines.append("| `%s` | %d | %s | %s | %s |"
                 % (k[1:], ntot, main, "有" if ft else "无", verdict))

lines += [
    "",
    "补充观察：",
    "",
    "- 多数候选已在 `testing/variations/fieldtrial_testing_config.json` 注册实验，"
    "即上游把它们当作待验证特性灰度发布，这与本项目「启用前必须逐项 A/B」的纪律一致。",
    "- `VizDirectCompositorThreadIpcNonRoot` 的真实消费点在 "
    "`components/viz/service/frame_sinks/compositor_frame_sink_impl.cc`、"
    "`components/viz/service/main/viz_compositor_thread_runner_impl.cc`、`content/gpu/gpu_main.cc`，"
    "属 GPU 进程路径，Windows 可达。",
    "- `MojoDirectSharedMemoryAllocation` 虽出现在 Android flag list 里，但实现引用位于 "
    "`content/app/initialize_mojo_core.cc`（所有进程的 Mojo 初始化），不是 Android 专属。",
    "- `DeferLayoutDuringBrowserStartup` 的消费点在 `chrome/browser/ui/views/frame/browser_view.cc`"
    "（Views 桌面窗口路径），对本产品直接相关。",
    "",
]
sec = "\n".join(lines)

doc = io.open(DOC, encoding="utf-8").read()
anchor = "## 2. Tier B"
if "## 1.1 适用性核实" in doc:
    start = doc.index("## 1.1 适用性核实")
    doc = doc[:start] + sec + doc[doc.index(anchor, start):]
    print("§1.1 已重写，示例:", blocks[0][0][0], len(blocks[0][1]))
else:
    assert anchor in doc
    doc = doc.replace(anchor, sec + anchor, 1)
    print("已插入 §1.1，候选 %d 个" % len(blocks))
io.open(DOC, "w", encoding="utf-8", newline="\n").write(doc)
