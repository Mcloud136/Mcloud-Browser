#!/usr/bin/env python3
"""candidate_applicability.py - 判定 M155 Tier A 候选是否真的作用于 Windows 桌面路径。

对每个 feature 标识符：找引用它的文件（排除自身声明文件），统计目录分布，
标记 android/ mac/ linux/ chromeos/ 等专属路径与 cros/woa 依赖；输出可据以
判断"启用了在本产品里到底走不走得到"。
"""
import subprocess
import sys

SRC = r"D:\wxmuma\chromium-src\src"
REV = sys.argv[1] if len(sys.argv) > 1 else "155.0.8059.40"
CAND = [
    "kDeferLayoutDuringBrowserStartup", "kImprovedStartupBestEffortDelay",
    "kDeferSessionStorageScavengingOnStartup", "kMojoDirectSharedMemoryAllocation",
    "kVizDirectCompositorThreadIpcNonRoot", "kPreconnectManagerDirectFastPath",
    "kBindURLLoaderFactoryToHighPriorityTaskRunner", "kCacheControlImmutable",
    "kDnsPlatformFailFastAndRetry", "kEnableIntermediateDnsResults",
    "kUseDnsHttpsSvcbAddressHints", "kAsyncDnsQuicJob", "kQuicUseReadMultiple",
    "kPartitionAllocAdaptiveMemoryReclaimInterval", "kDecodeScriptsInBlink",
    "kFontDataManagerPrewarming", "kResampleScrollEventsForFling",
    "kApplyScrollRailingInRenderer", "kPrioritizeResizeTaskRunnerOnStartup",
]

for k in CAND:
    # 消费者往往调用 Is<Name>Enabled() 辅助函数，因此按去 k 的名字匹配
    needle = k[1:] if k.startswith("k") and k[1:2].isupper() else k
    out = subprocess.run(
        ["git", "-C", SRC, "grep", "-I", "-l", needle, REV],
        capture_output=True, text=True, errors="replace", timeout=900).stdout
    files = [ln.split(":", 1)[1] for ln in out.splitlines() if ":" in ln]
    decl = [f for f in files if f.endswith(("_features.cc", "features.cc",
                                            "feature_list.cc", "features.h"))]
    use = [f for f in files if f not in decl]
    plat = set()
    for f in files:
        if "/android/" in f or f.startswith("chrome/android") or f.startswith("content/public/android"):
            plat.add("android")
        if "/mac/" in f or "/darwin/" in f:
            plat.add("mac")
        if "/linux/" in f or "/posix/" in f:
            plat.add("linux")
        if "chromecast" in f or "cros/" in f or "chromeos" in f:
            plat.add("cros/cast")
        if "/win/" in f:
            plat.add("win")
    print("%-52s 引用文件 %2d 个  非声明引用 %2d 个  平台分布 %s"
          % (k, len(files), len(use), ",".join(sorted(plat)) or "-"))
    for f in use[:4]:
        print("      ·", f)
