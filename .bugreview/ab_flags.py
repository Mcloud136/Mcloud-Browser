#!/usr/bin/env python3
"""ab_flags.py - 在 M155 构建上对 Tier A 候选做逐项 A/B（启动 / 内存 / 泄漏 / GPU 四指标）。

只改构建目录 `out/mcloud/mcloud_flags.txt`（仓库文件不动），每测完一个配置立即恢复基线。

⚠ 变更算子必须是**编辑**而不是无脑追加。实证依据：
   base/feature_list.cc:449-452（M155）
     // Process disabled features first, so that disabled ones take precedence over
     // enabled ones (since RegisterOverride() uses emplace()).
     RegisterOverridesFromCommandLine(disable_features, OVERRIDE_DISABLE_FEATURE);
     RegisterOverridesFromCommandLine(parsed_enable_features, OVERRIDE_ENABLE_FEATURE);
   → 同名 feature 同时出现在 --disable-features 与 --enable-features 时，**禁用侧胜出**。
     所以 SkiaGraphite 的"启用"臂必须删掉 `--disable-features=SkiaGraphite` 行（回到上游
     默认 FEATURE_ENABLED_BY_DEFAULT），追加 enable 行是彻底无效的实验（会测成第二个基线）。

每个候选的静态前置校验（D48 教训：名字写错的 flag 会被 Chromium 静默忽略）：
   P1 在 155 树声明位存在，且默认值与算子方向匹配；
   P2 算子真的改变活动条目（非注释行）；
   P3 基线里该 feature 未被反向覆盖，否则等价于 P1 的默认冲突检查。

用法：
  python .bugreview/ab_flags.py                 # 全量（9 个配置，约 60 分钟）
  python .bugreview/ab_flags.py --smoke         # 冒烟（仅基线，缩短全部参数，验证解析器）
  python .bugreview/ab_flags.py --only 3        # 只测前 3 个候选
输出：.bugreview/ab_results.json（增量落盘）+ .bugreview/ab_table.md
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

THOR = r"d:\wxmuma\thorium"
SRC155 = r"D:\wxmuma\chromium-src-155\src"
OUT_FLAGS = os.path.join(SRC155, "out", "mcloud", "mcloud_flags.txt")
REPO_FLAGS = os.path.join(THOR, "mcloud_flags.txt")
CHROME = os.path.join(SRC155, "out", "mcloud", "chrome.exe")
PS = "powershell.exe"
PY = sys.executable
GIT = r"C:\Users\Administrator\.qoder-cn\bin\git\mingw64\bin\git.exe"
PYENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

# 算子：(标签, kind, arg)
#   add-enable  —— 追加一行 --enable-features=<arg>
#   drop-line   —— 删除内容含 <arg> 的活动行（回到上游默认）
CANDIDATES = [
    ("SkiaGraphite=上游默认(启用)", "drop-line", "--disable-features=SkiaGraphite"),
    ("MojoDirectSharedMemoryAllocation", "add-enable", "MojoDirectSharedMemoryAllocation"),
    ("VizDirectCompositorThreadIpcNonRoot", "add-enable", "VizDirectCompositorThreadIpcNonRoot"),
    ("DeferLayoutDuringBrowserStartup", "add-enable", "DeferLayoutDuringBrowserStartup"),
    ("ImprovedStartupBestEffortDelay", "add-enable", "ImprovedStartupBestEffortDelay"),
    ("DeferSessionStorageScavengingOnStartup",
     "add-enable", "DeferSessionStorageScavengingOnStartup"),
    ("PartitionAllocAdaptiveMemoryReclaimInterval",
     "add-enable", "PartitionAllocAdaptiveMemoryReclaimInterval"),
    ("PreconnectManagerDirectFastPath", "add-enable", "PreconnectManagerDirectFastPath"),
    # D51：基线第 24 行 InitialWebUI 的 params 写法缺 value（Chromium 语法要求 param/value），
    # 运行时 oracle 证明该条从未进入 FeatureList override → 相当于这一项一直是空的。
    # 两个臂分别测"纯名启用"和"修正 params 语法"，用 activation 检查判定哪种写法真被接受。
    ("InitialWebUI(纯名启用)", "replace-active", "InitialWebUI"),
    ("InitialWebUI(修正 params 语法)", "replace-active",
     "InitialWebUI:without_spellcheck/true/without_translate/true/high_stream_priority/true"),
]

# 上游默认（M155 实测，见 gpu_finch_features.cc:378 等）——用于静态断言方向正确
EXPECTED_DEFAULT = {
    "SkiaGraphite": "ENABLED",
    "MojoDirectSharedMemoryAllocation": "DISABLED",
    "VizDirectCompositorThreadIpcNonRoot": "DISABLED",
    "DeferLayoutDuringBrowserStartup": "DISABLED",
    "ImprovedStartupBestEffortDelay": "DISABLED",
    "DeferSessionStorageScavengingOnStartup": "DISABLED",
    "PartitionAllocAdaptiveMemoryReclaimInterval": "DISABLED",
    "PreconnectManagerDirectFastPath": "DISABLED",
    "InitialWebUI": "DISABLED",
}


def active_lines(text):
    """返回未注释的 flag 行（以 # 开头的行、含行内 # 注释的都不算活动条目）。"""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def feature_names(text):
    """从活动行中提取 enable/disable-features 的 feature 名及方向。"""
    enabled, disabled = set(), set()
    for s in active_lines(text):
        m = re.match(r"--(enable|disable)-features=(.+)$", s)
        if not m:
            continue
        for part in m.group(2).split(","):
            name = part.split(":")[0].strip()
            if name:
                (enabled if m.group(1) == "enable" else disabled).add(name)
    return enabled, disabled


def declared_default(name):
    """在 155 树声明位查默认值；查不到返回 None（= 该名字不存在，必须失败）。"""
    p = subprocess.run([GIT, "grep", "-n", "-A2", "-w", "k" + name, "--", "*.cc", "*.h"],
                       cwd=SRC155, capture_output=True, text=True, errors="replace", timeout=900)
    body = (p.stdout or "") + (p.stderr or "")
    if "BASE_FEATURE(k%s," % name not in body and "BASE_FEATURE(k%s " % name not in body:
        return None
    if re.search(r"FEATURE_ENABLED_BY_DEFAULT", body):
        return "ENABLED"
    if re.search(r"FEATURE_DISABLED_BY_DEFAULT", body):
        return "DISABLED"
    return "PARAM"


def feat_name(kind, arg):
    if arg.startswith("--"):
        return arg.split("=")[-1].split(":")[0].strip()
    return arg.split(":")[0].strip()


def validate(label, kind, arg, baseline):
    """静态前置校验；返回 (ok, 说明)。"""
    name = feat_name(kind, arg)
    dd = declared_default(name)
    if dd is None:
        return False, "%s: 声明位查无此 feature（名字有误 → 会被静默忽略，D48）" % name
    if dd != EXPECTED_DEFAULT.get(name):
        return False, "%s: 默认值 %s 与预期 %s 不符" % (name, dd, EXPECTED_DEFAULT.get(name))
    en, dis = feature_names(baseline)
    if kind == "add-enable":
        if name in dis:
            return False, "%s 基线已显式禁用；追加 enable 会被禁用侧压制（feature_list.cc:449）" % name
        if name in en:
            return False, "%s 基线已启用，A/B 无差异" % name
    if kind == "replace-active":
        if name not in en:
            return False, "基线活动行里没有 --enable-features=%s…" % name
        # 关键例外：基线里那条带 params 的行经运行时 oracle 证明根本没进 FeatureList
        # （.bugreview/flag_runtime_state.py：enable 集合缺失该项），所以替换它是真实变量。
    if kind == "drop-line":
        if name not in dis:
            return False, "基线活动行里没有 --disable-features=%s" % name
        if name in en:
            return False, "%s 同时出现在启用侧，删行不等于启用" % name
    return True, "默认 %s，算子 %s 有效" % (dd, kind)


def run_ps(script, args, timeout=1200):
    # 强制 PowerShell 以 UTF-8 写管道，否则 5.1 按控制台码页输出、中文锚点无法匹配
    cmd = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
           "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; & '%s' %s"
           % (script, " ".join(args))]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")


# 本流水线在 %TEMP% 下创建的 profile 前缀。只允许终止命令行里带这些前缀的 chrome 实例。
# 缺陷 D55：旧实现 `Get-Process chrome | Stop-Process -Force` 会连带杀掉用户自己开着的浏览器
# （会话与未保存标签一起丢）。用户默认 profile 在 %LOCALAPPDATA% 而不在 %TEMP%，
# 因此按临时目录前缀筛选既能收掉本流水线的孤儿进程，又不会误伤。
OUR_PROFILE_PREFIXES = ("mcloud_bench_k1_", "mcloud_bench_k2_", "leakprobe_", "abact_",
                        "gpuprobe_", "mcloud_lp_", "frs_", "abverify_", "cmddbg_", "dbg_")


def kill_matching(prefixes, settle=3):
    cond = " -or ".join("$_.CommandLine -like '*%s*'" % x for x in prefixes)
    try:
        out = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                 "Where-Object { %s } | ForEach-Object { $_.ProcessId }" % cond)
    except subprocess.TimeoutExpired:
        print("   [warn] WMI 查询超时，跳过清理（不做机器级强杀）", flush=True)
        return
    pids = [x for x in out.split() if x.isdigit()]
    # 循环杀到干净：一次性强杀会留 crashpad-handler 尾巴，
    # 残余进程会锁住 out 目录里的 DLL 并打断下一次链接（缺陷 D71 实测）
    for _ in range(4):
        if not pids:
            break
        try:
            ps("Get-Process -Id %s -ErrorAction SilentlyContinue | "
               "Stop-Process -Force -ErrorAction SilentlyContinue" % ",".join(pids))
        except subprocess.TimeoutExpired:
            print("   [warn] 终止进程超时", flush=True)
            break
        time.sleep(2)
        try:
            out = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                     "Where-Object { %s } | ForEach-Object { $_.ProcessId }" % cond)
        except subprocess.TimeoutExpired:
            break
        pids = [x for x in out.split() if x.isdigit()]
    if pids:
        print("   [warn] 本流水线仍有 %d 个实例进程未退出（可能锁住 out 目录）" % len(pids),
              flush=True)
    if settle:
        time.sleep(settle)


def kill_chrome():
    kill_matching(OUR_PROFILE_PREFIXES)


def k1(runs):
    out = run_ps(os.path.join(THOR, "benchmark", "bench_startup.ps1"),
                 ["-ChromeExe", CHROME, "-Runs", str(runs)], timeout=900)
    m = re.search(r"中位数[^\d]*(\d+)", out)
    vals = [int(v[1]) for v in re.findall(r"\[(\d)/\d+\][^\d]*(\d+)\s*ms", out)]
    return (int(m.group(1)) if m else None), vals, out


def k2(samples, interval, tabs, settle):
    out = run_ps(os.path.join(THOR, "benchmark", "bench_memory.ps1"),
                 ["-ChromeExe", CHROME, "-Tabs", str(tabs), "-Samples", str(samples),
                  "-SampleInterval", str(interval), "-SettleSeconds", str(settle)],
                 timeout=1500)
    m = re.search(r"中位数[^\d]*([\d.]+)\s*MB", out)
    procs = re.findall(r"进程数 (\d+)", out)
    return (float(m.group(1)) if m else None), (procs[-1] if procs else "?"), out


def leak(rounds, tabs, label):
    p = subprocess.run([PY, os.path.join(THOR, "benchmark", "tools", "leak_probe.py"),
                        "--chrome", CHROME, "--rounds", str(rounds), "--tabs", str(tabs),
                        "--label", label], capture_output=True, text=True,
                       errors="replace", timeout=2400, env=PYENV)
    out = (p.stdout or "") + (p.stderr or "")
    d = re.search(r"轮间漂移合计\s*([+-]?[\d.]+)\s*MB", out)
    per = re.search(r"[（(]\s*([+-]?[\d.]+)\s*MB/轮[)）]", out)
    se = re.search(r"采样序列:(.*)MB", out)
    return (float(d.group(1)) if d else None), (float(per.group(1)) if per else None), \
        (se.group(1).strip() if se else "?"), out


def gpu(label):
    p = subprocess.run([PY, os.path.join(THOR, "benchmark", "tools", "gpu_probe.py"),
                        "--chrome", CHROME, "--label", label, "--json"],
                       capture_output=True, text=True, errors="replace", timeout=300,
                       env=PYENV)
    for ln in (p.stdout or "").splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except ValueError:
                pass
    return None


def propagated_sets():
    """返回 (运行时 override 的 enable 名集合, disable 名集合)。

    依据 base/metrics/field_trial.cc:690 `PopulateLaunchOptionsWithFieldTrialState()`：
    浏览器把**已注册的命令行 override** 通过 GetCommandLineFeatureOverrides() 序列化进子进程
    命令行。进程内追加的开关在操作系统命令行里看不到，但子进程是浏览器用改过的 CommandLine
    启动的，所以从 Win32_Process 取子进程命令行就能拿到 FeatureList 真正接受的条目集合。
    2026-10-10 对照实验（.bugreview/flag_runtime_state.py --control）：故意注入的不存在裸名
    **会**被原样回显 → 该 oracle 是"回显型"，未知名也收；因此"命中"是可靠的注册证据，
    而"未命中"只说明"不在 command-line-only 集合里"（带 params 的条目走 trial 通道，见 D51）。
    """
    import shutil
    import tempfile
    prof = tempfile.mkdtemp(prefix="abact_")
    subprocess.Popen([CHROME, "--user-data-dir=" + prof, "--no-first-run",
                      "--no-default-browser-check", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(14)
    lines = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
               "ForEach-Object { $_.CommandLine } | Out-String").splitlines()
    kill_matching([os.path.basename(prof)])
    shutil.rmtree(prof, ignore_errors=True)
    en, dis = set(), set()
    for l in lines:
        for m in re.finditer(r"--(enable|disable)-features=(\S+)", l):
            for part in m.group(2).split(","):
                n = part.split(":")[0].strip()
                if n:
                    (en if m.group(1) == "enable" else dis).add(n)
    return en, dis


def ps(cmd, timeout=180):
    # 缺陷 D56：WMI/powershell 调用必须有超时，否则 wmiprvse 卡住时整条流水线无声挂死。
    p = subprocess.run([PS, "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, errors="replace", timeout=timeout)
    return p.stdout or ""


def activation_ok(name, kind):
    """返回 (该臂的期望后置状态是否成立, 说明)。

    ⚠ 判读边界（D51）：回显来自 `GetFeatureOverridesImpl(command_line_only=true)`，它会跳过
      **带 field trial 的 override**（`base/feature_list.cc:1453-1456`），而写 params 的条目必然
      带合成 trial。所以 add-enable 臂若名字带 ':' 而未命中，不能推断为失效；本 harness 的
      候选一律用裸名（无 params），命中即证明"这条开关确实进了 FeatureList 命令行 override"。
    """
    en, dis = propagated_sets()
    if kind == "drop-line":
        ok = name not in en and name not in dis
        return ok, ("两集合均无该项 → override 已解除，回到上游默认" if ok
                    else "仍在 %s 回显中 → 删行未生效" % ("disable" if name in dis else "enable"))
    ok = name in en
    return ok, ("enable 回显命中 → 已注册" if ok
                else "未进 enable 回显（若带 params 则属 trial 通道，不据此判失效）")


def write_flags(baseline, kind, arg):
    if kind is None:
        body = baseline
    elif kind in ("add-enable", "replace-active"):
        entry = arg
        if kind == "replace-active":
            name = entry.split(":")[0]
            kept, replaced = [], 0
            for ln in baseline.splitlines():
                s = ln.strip()
                if (s.startswith("--enable-features=") and replaced == 0
                        and s[len("--enable-features="):].split(",")[0].split(":")[0].strip() == name):
                    kept.append("--enable-features=" + entry)
                    replaced += 1
                    continue
                kept.append(ln)
            if replaced != 1:
                raise SystemExit("replace-active 期望替换 1 行，实际 %d 行：%s" % (replaced, name))
            body = "\n".join(kept) + "\n"
        else:
            body = baseline.rstrip("\n") + (
                "\n\n# --- A/B 临时追加（由 .bugreview/ab_flags.py 写入，测完即恢复） ---\n"
                + "--enable-features=" + entry + "\n")
    elif kind == "drop-line":
        keep, dropped = [], 0
        for ln in baseline.splitlines():
            if ln.strip() == arg:
                dropped += 1
                continue
            keep.append(ln)
        if dropped != 1:
            raise SystemExit("drop-line 期望删 1 行，实际 %d 行：%s" % (dropped, arg))
        body = "\n".join(keep) + "\n"
    else:
        raise SystemExit("未知算子 " + str(kind))
    with open(OUT_FLAGS, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", type=int, default=0)
    ap.add_argument("--repeat", type=int, default=1,
                    help="整组连续测 N 遍，遍间交错；基线重复本身即噪声带估计")
    ap.add_argument("--subset", default="",
                    help="逗号分隔标签子串；只测标签含任一子串的候选（基线始终测）")
    ap.add_argument("--leak-rounds", type=int, default=0)
    ap.add_argument("--json-out", default="ab_results.json")
    a = ap.parse_args()

    if a.smoke:
        cfg = dict(runs=2, samples=2, interval=3, tabs=8, settle=25, leak_rounds=1,
                   leak_tabs=4, cooldown=3)
        cands = [("(基线)", None, None)]
    else:
        cfg = dict(runs=5, samples=3, interval=3, tabs=50, settle=90, leak_rounds=3,
                   leak_tabs=20, cooldown=25)
        cands = [("(基线)", None, None)] + list(CANDIDATES)
    if a.leak_rounds:
        cfg["leak_rounds"] = a.leak_rounds
    if a.only:
        cands = cands[:1 + a.only]
    if a.subset:
        keys = [k.strip() for k in a.subset.split(",") if k.strip()]
        cands = [c for c in cands if c[0].startswith("(") or any(k in c[0] for k in keys)]
    if a.repeat > 1:
        # 交错而不是"基线一次+候选各一次"：时间漂移（散热/后台任务）会均摊到每个配置上
        seq = []
        for i in range(a.repeat):
            for c in cands:
                seq.append((c[0] if i == 0 else "%s#%d" % (c[0], i + 1),) + c[1:])
        cands = seq

    baseline = open(REPO_FLAGS, encoding="utf-8").read()

    # 静态校验先行：任一候选无效就整轮拒绝开跑，避免 60 分钟测出无差异数据
    bad = []
    for label, kind, arg in cands:
        if kind is None:
            continue
        ok, why = validate(label, kind, arg, baseline)
        print("[%s] %s — %s" % ("ok " if ok else "FAIL", label, why), flush=True)
        if not ok:
            bad.append(label)
    if bad:
        raise SystemExit("候选静态校验未通过: %s" % bad)

    results = []
    json_path = os.path.join(THOR, ".bugreview", a.json_out)
    try:
        for label, kind, arg in cands:
            t0 = time.time()
            write_flags(baseline, kind, arg)
            name = feat_name(kind, arg) if arg else ""
            act = None
            if name:
                ok, why = activation_ok(name, kind)
                act = ok
                print("   [activation] %-42s %s（%s）" % (name, "符合预期" if ok else "不符",
                                                          why), flush=True)
                if not ok:
                    # 没能注册的臂去测数据只会得到"与基线无差异"的假结论，直接记为未采纳并跳过
                    results.append({"label": label, "op": arg, "activated": False,
                                    "skipped": "activation: " + why})
                    json.dump(results, open(json_path, "w", encoding="utf-8"), indent=1,
                              ensure_ascii=False)
                    kill_chrome()
                    continue
            kill_chrome()
            s, raw, o1 = k1(cfg["runs"])
            m2, pr, o2 = k2(cfg["samples"], cfg["interval"], cfg["tabs"], cfg["settle"])
            d, per, se, o3 = leak(cfg["leak_rounds"], cfg["leak_tabs"], label[:12])
            g = gpu(label[:12])
            r = {"label": label, "op": arg, "activated": act, "k1_ms": s, "k1_raw": raw,
                 "k2_mb": m2,
                 "procs": pr, "leak_drift_mb": d, "leak_per_round_mb": per,
                 "leak_series": se, "gpu": g, "secs": round(time.time() - t0)}
            results.append(r)
            json.dump(results, open(json_path, "w", encoding="utf-8"), indent=1,
                      ensure_ascii=False)          # 增量落盘，崩了也不丢已完成配置
            print("%-42s K1=%-6s K2=%-9s 进程=%-4s 泄漏=%-8s GPU(gpu-process=%s/swiftshader=%s) "
                  "[%ds]" % (label, s, m2, pr, d,
                             (g or {}).get("gpu-process 存在"),
                             (g or {}).get("Vulkan/SwiftShader 回退"), r["secs"]), flush=True)
            if None in (s, m2, d) or g is None:
                with open(os.path.join(THOR, ".bugreview", "ab_parse_fail.log"), "w",
                          encoding="utf-8") as fh:
                    fh.write("== K1 ==\n%s\n== K2 ==\n%s\n== LEAK ==\n%s\n" % (o1, o2, o3))
                print("!! 解析失败（详见 .bugreview/ab_parse_fail.log），提前中止。", flush=True)
                break
            kill_chrome()
            time.sleep(cfg["cooldown"])
    finally:
        write_flags(baseline, None, None)
        same = open(OUT_FLAGS, encoding="utf-8").read() == baseline
        print("已恢复基线 flags 到构建目录（与仓库逐字节一致: %s）" % same, flush=True)

    emit_table(results, json_path.replace(".json", "_table.md"))
    return 0


def emit_table(results, table_path=None):
    rows = ["| 配置 | K1 中位数(ms) | K2 中位数(MB) | 进程数 | 泄漏漂移(MB) | MB/轮 | GPU 进程 | "
            "SwiftShader 回退 | vs 基线 |",
            "|---|---|---|---|---|---|---|---|---|"]
    base = results[0] if results else None
    for r in results:
        g = r.get("gpu") or {}
        if "skipped" in r:
            rows.append("| %s | — | — | — | — | — | — | — | **未注册，跳过**（%s） |"
                        % (r["label"], r["skipped"]))
            continue
        if base is r:
            rows.append("| %s | %s | %s | %s | %s | %s | %s | %s | — |"
                        % (r["label"], r["k1_ms"], r["k2_mb"], r["procs"], r["leak_drift_mb"],
                           r["leak_per_round_mb"], g.get("gpu-process 存在"),
                           g.get("Vulkan/SwiftShader 回退")))
            continue
        dk1 = (r["k1_ms"] - base["k1_ms"]) if None not in (r["k1_ms"], base["k1_ms"]) else "?"
        dk2 = round(r["k2_mb"] - base["k2_mb"], 1) if None not in (r["k2_mb"], base["k2_mb"]) else "?"
        dlk = (round((r["leak_drift_mb"] or 0) - (base["leak_drift_mb"] or 0), 1)
               if None not in (r["leak_drift_mb"], base["leak_drift_mb"]) else "?")
        rows.append("| %s | %s | %s | %s | %s | %s | %s | %s | K1 %+s ms / K2 %+s MB / 泄漏 %+s MB |"
                    % (r["label"], r["k1_ms"], r["k2_mb"], r["procs"], r["leak_drift_mb"],
                       r["leak_per_round_mb"], g.get("gpu-process 存在"),
                       g.get("Vulkan/SwiftShader 回退"), dk1, dk2, dlk))
    text = "\n".join(rows) + "\n"
    with open(table_path or os.path.join(THOR, ".bugreview", "ab_table.md"), "w",
              encoding="utf-8") as f:
        f.write(text)
    print("\n" + text)


if __name__ == "__main__":
    sys.exit(main())
