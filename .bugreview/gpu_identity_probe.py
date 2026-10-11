#!/usr/bin/env python3
"""gpu_identity_probe.py - 实测 Chromium 到底在用集显还是独显，以及硬解能力真相。

背景（第5周期）：仓库文档一律把独显记作 "GTX 1050 Ti"（Pascal，无 AV1 硬解单元），
并据此在 D118 里把实测到的 av1 `powerEfficient=true` 判为"只证明被选中、不证明硬件单元存在"。
但 nvidia-smi 与 PCI ID（VEN_10DE&DEV_2860）证明真机独显是 **RTX 4070 Laptop（Ada，8GB）**，
它是有 AV1 硬解单元的。WMI Win32_VideoController.Name 报 "GTX 1050 Ti" 是错的。

本探针不复用任何文档结论，直接从运行中的浏览器取四类证据：
  A) chrome://gpu 的 Graphics Feature Status / Driver Information / 实际适配器；
  B) MediaCapabilities 对 h264/hevc/vp9/av1 的 supported+powerEfficient；
  C) 浏览器进程与 GPU 子进程命令行里的后端线索；
  D) WebGL 的 UNMASKED_RENDERER_WEBGL（这是**唯一能确定实际渲染适配器**的口径）。

退出码：0=四类证据齐全 / 1=有判据取不到或不成立 / 2=环境不满足（无产物、端口不通）。
纪律：只清理本次启动的实例（cdp.kill_instance 按 profile 叶子名），取不到数据一律非 0。
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "benchmark", "tools"))

import cdp  # noqa: E402

DEFAULT_EXE = os.environ.get(
    "MCHROME_EXE", r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe")
PORT = int(os.environ.get("MCGPU_PORT", "9455"))

# D 判据：WebGL 扩展给出的真实适配器串，headless/SwiftShader 会在这里露馅
WEBGL_EXPR = r"""
(() => {
  const out = {webgl: null, renderer: null, vendor: null, err: null};
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    if (!gl) { out.err = 'no webgl context'; return JSON.stringify(out); }
    const e = gl.getExtension('WEBGL_debug_renderer_info');
    out.webgl = gl.getParameter(gl.VERSION);
    out.renderer = e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL)
                     : gl.getParameter(gl.RENDERER);
    out.vendor = e ? gl.getParameter(e.UNMASKED_VENDOR_WEBGL)
                   : gl.getParameter(gl.VENDOR);
  } catch (ex) { out.err = String(ex); }
  return JSON.stringify(out);
})()
"""

# B 判据：M155 起 VideoConfiguration.framerate 必填（D118），缺了整次调用抛 TypeError
MC_EXPR = r"""
(async () => {
  const codecs = {
    'h264': 'avc1.640033',
    'hevc': 'hvc1.1.6.L153.B0',
    'vp9':  'vp09.00.40.08',
    'av1':  'av01.0.08M.08',
  };
  const res = {};
  for (const [name, cs] of Object.entries(codecs)) {
    try {
      const r = await navigator.mediaCapabilities.decodingInfo({
        type: 'file',
        video: {contentType: 'video/mp4; codecs="' + cs + '"',
                width: 3840, height: 2160, bitrate: 20000000, framerate: 30},
      });
      res[name] = {supported: r.supported, smooth: r.smooth,
                   powerEfficient: r.powerEfficient};
    } catch (e) { res[name] = {error: String(e)}; }
  }
  return JSON.stringify(res);
})()
"""

GPU_SECTIONS = [
    "Graphics Feature Status",
    "Driver Information",
    "Direct composition",
    "Supports overlays",
    "Skia Backend",
    "Passthrough Command Decoder",
    "Display type",
    "OpenGL max shader precision",
    "Video Decode Accelerator Supported Profile",
]


def ps_cmd(cmd):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, errors="replace",
                       timeout=180)
    return p.stdout or ""


def host_gpu_truth():
    """主机侧显卡真相：nvidia-smi（独显权威）+ PCI ID（不受 WMI 名称污染）。"""
    truth = {}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,pci.device_id,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            parts = [x.strip() for x in out.stdout.strip().split(",")]
            truth["nvidia_smi"] = {"name": parts[0], "pci": parts[1],
                                   "vram": parts[2], "driver": parts[3]}
    except Exception as exc:  # noqa: BLE001
        truth["nvidia_smi_error"] = str(exc)
    pnp = ps_cmd("Get-CimInstance Win32_PnPEntity -Filter \"PNPClass='Display'\" | "
                 "ForEach-Object { $_.Name + ' | ' + $_.DeviceID }")
    truth["pnp_display"] = [l.strip() for l in pnp.splitlines() if l.strip()]
    wmi = ps_cmd("Get-CimInstance Win32_VideoController | "
                 "ForEach-Object { $_.Name + ' | ' + $_.VideoProcessor }")
    truth["wmi_name_vs_processor"] = [l.strip() for l in wmi.splitlines() if l.strip()]
    return truth


def proc_backends(profile_key):
    """C 判据：本实例子进程命令行里的后端线索。只按 profile 叶子名筛。"""
    out = ps_cmd("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                 "ForEach-Object { $_.CommandLine }")
    lines = [l for l in out.splitlines() if profile_key in l]
    gpu = [l for l in lines if "--type=gpu-process" in l]
    info = {"instance_procs": len(lines), "gpu_proc_present": bool(gpu)}
    if gpu:
        txt = gpu[0].lower()
        info["angle_d3d11"] = "d3d11" in txt
        info["angle_d3d12"] = "d3d12" in txt
        info["swiftshader_fallback"] = "swiftshader" in txt
        m = re.search(r"--use-angle=(\S+)", gpu[0])
        info["use_angle"] = m.group(1) if m else None
        m = re.search(r"--gpu-preferences=(\S+)", gpu[0])
        info["gpu_preferences"] = (m.group(1)[:200] if m else None)
    return info


def main():
    exe = DEFAULT_EXE
    if not os.path.isfile(exe):
        print("ENV FAIL: 被测产物不存在: %s" % exe)
        return 2
    st = os.stat(exe)
    print("== 被测身份 ==")
    print("   exe      : %s" % os.path.abspath(exe))
    print("   bytes    : %d   mtime: %s" % (st.st_size, st.st_mtime))
    fl = os.path.join(os.path.dirname(os.path.abspath(exe)), "mcloud_flags.txt")
    print("   flags    : %s (%s)" % (fl, "存在" if os.path.isfile(fl) else "缺失"))
    print("")

    print("== A0 主机侧显卡真相（不采信 WMI Name） ==")
    truth = host_gpu_truth()
    print(json.dumps(truth, ensure_ascii=False, indent=2))
    print("")

    profile = tempfile.mkdtemp(prefix="mcgpu_")
    key = os.path.basename(profile.rstrip("/\\"))
    proc = cdp.launch(exe, profile, PORT,
                      extra=["--enable-logging=stderr", "--v=0"],
                      log_path=os.path.join(HERE, "gpu_probe_launch.log"))
    ok = False
    results = {}
    try:
        if not cdp.wait_for_port(PORT, timeout=40):
            print("ENV FAIL: 调试端口 %d 未就绪" % PORT)
            return 2
        ok = True
        results["C_proc_backends"] = proc_backends(key)

        tab = cdp.Tab(port=PORT, url="about:blank")
        # D) WebGL 真实适配器
        tab.navigate("about:blank", settle=1.0)
        raw = tab.evaluate(WEBGL_EXPR, user_gesture=True)
        results["D_webgl"] = json.loads(_unwrap(raw)) if raw else None

        # B) MediaCapabilities
        raw = tab.evaluate(MC_EXPR, user_gesture=True)
        results["B_mediacapabilities"] = json.loads(_unwrap(raw)) if raw else None

        # A) chrome://gpu 全文（deep_text 穿透 shadow root，D107 修复后的口径）
        tab.navigate("chrome://gpu", settle=4.0)
        txt = tab.deep_text()
        results["A_gpu_text_len"] = len(txt or "")
        with open(os.path.join(HERE, "gpu_page_full.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write(txt or "")
        results["A_gpu_sections"] = {}
        for sec in GPU_SECTIONS:
            i = (txt or "").find(sec)
            results["A_gpu_sections"][sec] = (
                txt[i:i + 700].replace("\n", " | ") if i >= 0 else None)
        # 段落名跨版本会变：把全文里所有形如 "Xxx Yyy:" 的标题行抓出来，供校准判据
        results["A_gpu_headings"] = sorted(set(re.findall(
            r"^([A-Z][A-Za-z0-9 /&\-\(\)]{3,60}):\s*$", txt or "", re.M)))[:80]
        # Video Decode 能力清单（AV1/HEVC/VP9 是否真在硬解 profile 里）
        results["A_video_decode_lines"] = [
            l.strip() for l in (txt or "").splitlines()
            if re.search(r"\b(av1|hevc|vp9|h264|AV1|HEVC|VP9|H264)\b", l)
        ][:60]
        # 实际被 Chromium 选中的适配器名（Driver Information 段）
        for pat in (r"GL_RENDERER:\s*([^\n|]+)", r"GL_VENDOR:\s*([^\n|]+)",
                    r"Direct3D11 renderers:\s*([^\n|]+)",
                    r"DawnAdapterInfo:\s*([^\n|]+)"):
            m = re.search(pat, txt or "")
            if m:
                results.setdefault("A_gl_identity", {})[pat.split(":")[0]] = m.group(1).strip()
        with contextlib.suppress(Exception):
            tab.close()
    finally:
        left = cdp.kill_instance(profile, port=PORT)
        try:
            if proc.poll() is None:
                proc.wait(timeout=30)
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                proc.kill()
        print("")
        print("== 清理 ==  残留进程数=%d（必须为 0，否则锁住 out 目录 DLL，见 D71）" % left)
        results["cleanup_leftover"] = left
        with open(os.path.join(HERE, "gpu_identity_result.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"host_truth": truth, "results": results}, fh,
                      ensure_ascii=False, indent=2)
        print("== 结果已写 %s ==" % os.path.join(HERE, "gpu_identity_result.json"))

    if not ok:
        return 2

    print("")
    print("== 判据汇总 ==")
    fail = []
    d = results.get("D_webgl") or {}
    print("   D WebGL renderer : %s" % d.get("renderer"))
    print("   D WebGL vendor   : %s" % d.get("vendor"))
    if not d.get("renderer"):
        fail.append("D: 取不到 WebGL 真实适配器")
    elif "swiftshader" in d.get("renderer", "").lower() or \
         "software" in d.get("renderer", "").lower():
        fail.append("D: 渲染回退到软件/SwiftShader")

    mc = results.get("B_mediacapabilities") or {}
    for c in ("h264", "hevc", "vp9", "av1"):
        v = mc.get(c) or {}
        print("   B %-5s supported=%s smooth=%s powerEfficient=%s %s" % (
            c, v.get("supported"), v.get("smooth"), v.get("powerEfficient"),
            v.get("error", "")))
        if "error" in v:
            fail.append("B: %s 查询抛错 %s" % (c, v["error"]))
    if not mc:
        fail.append("B: MediaCapabilities 无结果")

    cb = results.get("C_proc_backends") or {}
    print("   C 本实例进程数   : %s   gpu-process=%s  use-angle=%s  d3d11=%s d3d12=%s" % (
        cb.get("instance_procs"), cb.get("gpu_proc_present"), cb.get("use_angle"),
        cb.get("angle_d3d11"), cb.get("angle_d3d12")))
    if not cb.get("gpu_proc_present"):
        fail.append("C: 没有 GPU 子进程")

    a = results.get("A_gpu_text_len") or 0
    print("   A chrome://gpu 文本长度: %d" % a)
    if a < 2000:
        fail.append("A: chrome://gpu 文本过短(%d)，deep_text 可能没穿透 shadow root" % a)
    for sec, val in (results.get("A_gpu_sections") or {}).items():
        if val is None:
            fail.append("A: chrome://gpu 找不到段落 %r" % sec)
    print("   A GL 身份: %s" % json.dumps(results.get("A_gl_identity") or {},
                                          ensure_ascii=False))
    if results.get("cleanup_leftover"):
        fail.append("清理: 残留 %d 个进程" % results["cleanup_leftover"])

    print("")
    if fail:
        print("VERDICT: FAIL（%d 项）" % len(fail))
        for f in fail:
            print("   - %s" % f)
        return 1
    print("VERDICT: PASS（四类证据齐全）")
    return 0


def _unwrap(raw):
    """CDP evaluate 回来的可能是 {'type':'string','value':...} 或直接字符串。"""
    if isinstance(raw, dict):
        v = raw.get("value", raw)
        return v if isinstance(v, str) else json.dumps(v)
    return raw if isinstance(raw, str) else json.dumps(raw)


if __name__ == "__main__":
    sys.exit(main())
