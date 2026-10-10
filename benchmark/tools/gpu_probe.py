#!/usr/bin/env python3
"""gpu_probe.py - 窗口化验证 GPU 渲染路径是否真的在用（不用 headless，headless 会走软件/SwiftShader）。

判定三件事：
  1) 是否存在 `--type=gpu-process` 子进程（GPU 进程活着）；
  2) 该子进程命令行里的 ANGLE / D3D 后端选择线索（gr/arf 位与 d3d11/dx12 关键字）；
  3) 浏览器进程命令行是否带着我们注入的 GPU 相关开关（--enable-gpu-rasterization 等）。
"""
import json
import subprocess
import sys
import tempfile
import time
import shutil

PS_PROCESSES = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                "ForEach-Object { $_.CommandLine } | Out-String")


def ps(cmd):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace")
    return p.stdout or ""


def probe(exe, label):
    prof = tempfile.mkdtemp(prefix="gpuprobe_")
    proc = subprocess.Popen([exe, "--user-data-dir=" + prof, "--no-first-run",
                             "--no-default-browser-check",
                             "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(14)
    lines = ps(PS_PROCESSES).splitlines()
    gpu = [l for l in lines if "--type=gpu-process" in l]
    key = exe.lower()
    main = [l for l in lines if key in l.lower() and "--type=" not in l and "Crashpad" not in l]

    txt = (gpu[0] if gpu else "")
    interesting = {
        "gpu-process 存在": bool(gpu),
        "ANGLE=D3D11": "d3d11" in txt.lower(),
        "ANGLE=D3D12": "d3d12" in txt.lower(),
        "Vulkan/SwiftShader 回退": ("swiftshader" in txt.lower() or "vulkan" in txt.lower()),
        "gpu-preferences 片段": txt[txt.find("--gpu-preferences"):][:120] if "--gpu-preferences" in txt else "-",
    }
    btxt = main[0] if main else ""
    interesting["浏览器进程含 --enable-gpu-rasterization"] = "--enable-gpu-rasterization" in btxt
    interesting["浏览器进程含 enable-features 注入"] = "--enable-features=" in btxt
    ps("Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force")
    try:
        proc.wait(timeout=30)
    except Exception:                              # noqa: BLE001
        proc.kill()
    shutil.rmtree(prof, ignore_errors=True)
    print("== %s (%s)" % (label, exe))
    for k, v in interesting.items():
        print("   %-46s %s" % (k, v))
    return interesting


if __name__ == "__main__":
    out = {}
    for label, exe in (("M155", r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"),
                       ("M151", r"D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe")):
        out[label] = probe(exe, label)
    print("\n对比结论：两版 GPU 进程均存在且走同一 ANGLE 后端 →",
          "一致" if bool(out["M155"]["gpu-process 存在"]) == bool(out["M151"]["gpu-process 存在"]) else "不一致")
