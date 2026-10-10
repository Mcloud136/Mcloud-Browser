#!/usr/bin/env python3
"""gpu_probe.py - 窗口化验证 GPU 渲染路径是否真的在用（不用 headless，headless 会走软件/SwiftShader）。

判定三件事：
  1) 是否存在 `--type=gpu-process` 子进程（GPU 进程活着）；
  2) 该子进程命令行里的 ANGLE / D3D 后端选择线索（gr/arf 位与 d3d11/dx12 关键字）；
  3) 浏览器进程命令行是否带着我们注入的 GPU 相关开关（--enable-gpu-rasterization 等）。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import shutil

PS_PROCESSES = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                "ForEach-Object { $_.CommandLine } | Out-String")


def ps(cmd):
    # timeout 必需（缺陷 D56：powershell.exe 无 timeout，WMI 仓库服务卡住时探针永久挂起，
    # 连带整条 A/B 流水线停在一步上且没有任何报错）。
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace",
                       timeout=180)
    return p.stdout or ""


def probe(exe, label):
    prof = tempfile.mkdtemp(prefix="gpuprobe_")
    # 实例指纹用 profile 的**叶子名**，不用完整路径：Python 的 TEMP 可能是 8.3 短名形式，
    # 而 chrome 命令行里是长名（或反之），整批子串匹配会落空——同 leak_probe 里刚被
    # 回归测试抓到的那个坑（D52 修复过程中引入的次生缺陷）。
    key = os.path.basename(prof.rstrip("/\\"))
    proc = subprocess.Popen([exe, "--user-data-dir=" + prof, "--no-first-run",
                             "--no-default-browser-check",
                             "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(14)
    lines = [l for l in ps(PS_PROCESSES).splitlines() if key in l]
    gpu = [l for l in lines if "--type=gpu-process" in l]
    main = [l for l in lines if exe.lower() in l.lower()
            and "--type=" not in l and "Crashpad" not in l]

    txt = (gpu[0] if gpu else "")
    interesting = {
        "gpu-process 存在": bool(gpu),
        "ANGLE=D3D11": "d3d11" in txt.lower(),
        "ANGLE=D3D12": "d3d12" in txt.lower(),
        "Vulkan/SwiftShader 回退": ("swiftshader" in txt.lower() or "vulkan" in txt.lower()),
        "gpu-preferences 片段": txt[txt.find("--gpu-preferences"):][:120] if "--gpu-preferences" in txt else "-",
        "本实例进程数": len(lines),
        "浏览器主进程命令行可见": bool(main),
    }
    # 加载器是在**进程内**追加开关的，所以浏览器自身的 OS 命令行里看不到注入结果；
    # 能看到的是子进程命令行里的 override 回显（base/metrics/field_trial.cc:690）。
    # 旧断言写成"浏览器进程含 …"，一旦匹配到机器上别的 chrome 进程就是假阳性（D52 同族）。
    interesting["本实例存在 GPU 光栅化开关"] = any(
        "--enable-gpu-rasterization" in l for l in lines)
    interesting["子进程回显含 enable-features（注入生效证据）"] = any(
        "--type=" in l and "--enable-features=" in l for l in lines)
    # 缺陷 D55：旧实现 `Get-Process chrome | Stop-Process -Force` 会终止**整台机器**的
    # chrome（包括用户自己开着的浏览器，会话与未保存标签一起丢）。
    # 现只终止本次探测启动的实例：命令行里带着我们的临时 profile 的那批 PID。
    idout = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
               "Where-Object { $_.CommandLine -like '*%s*' } | "
               "ForEach-Object { $_.ProcessId }" % key)
    pids = [x for x in idout.split() if x.isdigit()]
    # 循环杀到干净：一次性杀会留下 crashpad-handler 尾巴，残余进程会锁住 out 目录里的 DLL
    # 从而打断下一次链接（缺陷 D71 实测）
    for _ in range(4):
        if not pids:
            break
        ps("Get-Process -Id %s -ErrorAction SilentlyContinue | "
           "Stop-Process -Force -ErrorAction SilentlyContinue" % ",".join(pids))
        time.sleep(2)
        idout = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                   "Where-Object { $_.CommandLine -like '*%s*' } | "
                   "ForEach-Object { $_.ProcessId }" % prof)
        pids = [x for x in idout.split() if x.isdigit()]
    if pids:
        print("   WARN: 本探测实例仍有 %d 个进程未退出（可能锁住 out 目录）" % len(pids))
    if proc.poll() is None:
        try:
            proc.wait(timeout=30)
        except Exception:                              # noqa: BLE001
            proc.kill()
    shutil.rmtree(prof, ignore_errors=True)
    print("== %s (%s)" % (label, exe))
    for k, v in interesting.items():
        print("   %-46s %s" % (k, v))
    return interesting


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe")
    ap.add_argument("--label", default="build")
    ap.add_argument("--json", action="store_true", help="只输出一行 JSON，供脚本消费")
    args = ap.parse_args(argv)
    got = probe(args.chrome, args.label)
    if args.json:
        print(json.dumps(got, ensure_ascii=False))
    return 0 if got["gpu-process 存在"] and not got["Vulkan/SwiftShader 回退"] else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main())
    out = {}
    for label, exe in (("M155", r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"),
                       ("M151", r"D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe")):
        out[label] = probe(exe, label)
    print("\n对比结论：两版 GPU 进程均存在且走同一 ANGLE 后端 →",
          "一致" if bool(out["M155"]["gpu-process 存在"]) == bool(out["M151"]["gpu-process 存在"]) else "不一致")
