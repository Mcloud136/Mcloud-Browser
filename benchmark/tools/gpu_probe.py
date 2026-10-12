#!/usr/bin/env python3
"""gpu_probe.py - 窗口化验证 GPU 渲染路径是否真的在用（不用 headless，headless 会走软件/SwiftShader）。

判定三件事：
  1) 是否存在 `--type=gpu-process` 子进程（GPU 进程活着）；
  2) **实际用的 ANGLE 后端与适配器**——只能读 chrome://gpu，不能猜命令行；
  3) 浏览器/子进程命令行是否带着我们注入的 GPU 相关开关（--enable-gpu-rasterization 等）。

⚠ 第 2 条以前是这么写的（第7周期，缺陷 D184 已修）：
    "ANGLE=D3D11": "d3d11" in txt.lower()   /   "ANGLE=D3D12": "d3d12" in txt.lower()
    而 GPU 进程命令行里根本没有 `--use-angle`，那两处子串命中的是**我们自己的 feature 名**：
      MediaFoundation**D3D11**VideoCaptureZeroCopy（在 --enable-features 里）
      --disable-features=**D3D12**VideoDecoder
    ⇒ 两个判据同时为 True，而这从不能证明后端。现在改成经 CDP 打开 chrome://gpu 取
    gl_renderer / VENDOR_ID / DEVICE_ID，取不到就判量具失效（rc=2），不再退回字符串猜测。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import shutil
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp as _cdp           # noqa: E402  —— 同目录的零依赖 CDP 客户端


class GpuInstrumentError(RuntimeError):
    """读不到 chrome://gpu ⇒ 后端/适配器未知。不得用猜测顶替。"""


def _free_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_json(path, port, method="GET", timeout=10.0):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace").strip()
            return json.loads(body) if body.startswith("[") or body.startswith("{") else {"raw": body}
    except Exception as exc:                                # noqa: BLE001
        raise GpuInstrumentError("CDP %s %s 失败：%s" % (method, path, type(exc).__name__)) from exc


def gpu_identity(port):
    """打开 chrome://gpu 并抽出后端与适配器身份。返回 dict。"""
    _http_json("/json/version", port)
    new = _http_json("/json/new?chrome://gpu", port, method="PUT")
    tid = (new or {}).get("id")
    if not tid:
        raise GpuInstrumentError("/json/new?chrome://gpu 没返回 target id：%s" % new)
    tab = _cdp.Tab(port=port, target_id=tid, timeout=40.0)
    # 正文一开始只有内联 CSS，`wait_for_text` 会被它满足 ⇒ 读到的不是驱动信息（实测首条
    # 900 字符全是样式）。必须等 GL_RENDERER 出现，等不到就判量具失效（D184 同族）。
    text = ""
    for _ in range(60):
        try:
            text = tab.deep_text()
        except _cdp.CDPError as exc:
            raise GpuInstrumentError("读取 chrome://gpu 正文失败：%s" % exc) from exc
        if "GL_RENDERER" in text:
            break
        time.sleep(0.5)
    if "GL_RENDERER" not in text:
        raise GpuInstrumentError("chrome://gpu 正文 30 秒内没出现 GL_RENDERER（读到 %d 字符）"
                                 % len(text))

    def grab(pattern):
        m = re.search(pattern, text, re.I)
        return m.group(1).strip() if m else ""

    # 注意标签格式：chrome://gpu 写的是 `GL_RENDERER<空格>:值`（冒号，不是等号）。
    # 首版正则用 `=` ⇒ 永远取不到，于是把"我读法不对"误报成"页面没驱动信息"。
    out = {
        "gl_renderer": grab(r"GL_RENDERER\s*[:=]\s*(.+)"),
        "gl_vendor": grab(r"GL_VENDOR\s*[:=]\s*(.+)"),
        "gl_version": grab(r"GL_VERSION\s*[:=]\s*(.+)"),
        "skia_backend": grab(r"Skia backend\s*[:=]\s*(\w+)"),
    }
    # 适配器身份：ANGLE 串形如 `ANGLE (NVIDIA, <名称> (0x00002860) Direct3D11 …, D3D11-…)`。
    # ⚠ 按 D143 的纪律：**名称不可信**（本机注册表把 RTX 4070 Laptop 改成了字面量 "GTX 1050 Ti"，
    # 该错误名称会经 DXGI 一路传进 chrome://gpu），设备号才是身份。所以这里同时输出两者，
    # 并明确"以 0x… 设备号为准"。
    m = re.search(r"ANGLE \(\s*([^,]+),", out["gl_renderer"])
    out["adapter_vendor"] = m.group(1).strip() if m else "?"
    m = re.search(r"0x([0-9a-fA-F]{4,8})", out["gl_renderer"])
    out["adapter_device_id"] = ("0x" + m.group(1)) if m else "?"
    out["adapter"] = "%s / 设备号 %s（名称按 D143 不可信，以设备号为准）" % (
        out["adapter_vendor"], out["adapter_device_id"])
    for backend, token in (("D3D11", "Direct3D11"), ("D3D12", "Direct3D12"),
                           ("Vulkan", "Vulkan"), ("SwiftShader", "SwiftShader")):
        if token.lower() in (out["gl_renderer"] + " " + out["gl_version"]).lower():
            out["angle_backend"] = backend
            break
    else:
        out["angle_backend"] = "未识别（gl_renderer/gl_version 里没有已知后端字样）"
    if not out["gl_renderer"]:
        raise GpuInstrumentError("读到了 chrome://gpu 正文但取不到 GL_RENDERER（标签格式变了？）")
    return out


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
    port = _free_port()
    proc = subprocess.Popen([exe, "--user-data-dir=" + prof, "--no-first-run",
                             "--no-default-browser-check",
                             "--remote-debugging-port=%d" % port,
                             "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(14)
    lines = [l for l in ps(PS_PROCESSES).splitlines() if key in l]
    gpu = [l for l in lines if "--type=gpu-process" in l]
    main = [l for l in lines if exe.lower() in l.lower()
            and "--type=" not in l and "Crashpad" not in l]

    interesting = {
        "gpu-process 存在": bool(gpu),
        "本实例进程数": len(lines),
        "浏览器主进程命令行可见": bool(main),
    }
    # D184：后端与适配器一律读 chrome://gpu。取不到就记 "量具失效" 并让退出码非 0，
    # **不得**退回命令行子串猜测（那正是旧版把 feature 名当成 ANGLE 后端的地方）。
    try:
        ident = gpu_identity(port)
        interesting["ANGLE 后端（chrome://gpu）"] = ident["angle_backend"]
        interesting["渲染适配器 PCI 身份"] = ident.get("adapter", "?")
        interesting["GL_RENDERER"] = ident["gl_renderer"][:120]
    except GpuInstrumentError as exc:
        interesting["ANGLE 后端（chrome://gpu）"] = "量具失效：%s" % exc
        interesting["渲染适配器 PCI 身份"] = "未知"
        interesting["GL_RENDERER"] = "未知"
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
        # 复检必须与首检用**同一个**指纹（profile 叶子名）。旧实现这里用完整路径 prof，
        # 而 prof 可能是 8.3 短名形式、chrome 命令行里是长名（或反之），整批匹配会落空 →
        # pids 变空 → 循环 break → 不打印任何 WARN，进程其实还活着（缺陷 D140）。
        # 后果不只是"报告失真"：残留 chrome 会锁住 out 目录里的 DLL，让下一次链接以
        # lld-link permission denied 失败（D71 实测）。
        idout = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                   "Where-Object { $_.CommandLine -like '*%s*' } | "
                   "ForEach-Object { $_.ProcessId }" % key)
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
    # 被测对象口径（AGENTS.md 缺陷 D86/D72 纪律）：benchmark/ 与 benchmark/tools/* 的默认
    # 对象必须取 $env:MCHROME_EXE / $env:MCHROME_OUT，再退回当前 155 树。本机同时存在
    # chromium-src（M151 回滚参考树）与 chromium-src-155（发布树），写死就会把结果归属到
    # 错误的产物树，而日志里看不出来。旧实现直接写死 155 树，没走环境变量（缺陷 D141）。
    fallback = r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"
    default_exe = os.environ.get("MCHROME_EXE") or fallback
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=default_exe)
    ap.add_argument("--label", default="build")
    ap.add_argument("--json", action="store_true", help="只输出一行 JSON，供脚本消费")
    args = ap.parse_args(argv)
    got = probe(args.chrome, args.label)
    if args.json:
        print(json.dumps(got, ensure_ascii=False))
    backend = str(got.get("ANGLE 后端（chrome://gpu）", ""))
    if not got["gpu-process 存在"]:
        return 1
    if backend.startswith("量具失效") or backend.startswith("未识别"):
        print("FAIL（量具失效）：读不到 ANGLE 后端 —— %s" % backend)
        return 2
    if "SwiftShader" in backend:
        print("FAIL：渲染回退到软件后端（%s）" % backend)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main())
    fallback = r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"
    out = {}
    for label, exe in (("M155", os.environ.get("MCHROME_EXE") or fallback),
                       ("M151", r"D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe")):
        if not os.path.isfile(exe):
            print("SKIP %s：产物不存在（%s）" % (label, exe))
            continue
        out[label] = probe(exe, label)
    if len(out) == 2:
        same = (out["M155"].get("ANGLE 后端（chrome://gpu）")
                == out["M151"].get("ANGLE 后端（chrome://gpu）"))
        # 旧文案写的是"两版均走同一 ANGLE 后端 → 一致"，但它比较的其实是
        # "gpu-process 是否存在"两个布尔值 —— 与后端无关（D184 同族的"结论超出测量"）。
        print("\n对比结论：ANGLE 后端%s（M155=%s / M151=%s）；适配器 PCI 身份 %s / %s"
              % ("相同" if same else "不同",
                 out["M155"].get("ANGLE 后端（chrome://gpu）"),
                 out["M151"].get("ANGLE 后端（chrome://gpu）"),
                 out["M155"].get("渲染适配器 PCI 身份"),
                 out["M151"].get("渲染适配器 PCI 身份")))
