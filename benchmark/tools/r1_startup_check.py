#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R1 启动与运行时配置（第4周期实操检测，2026-10-11）。

与既有探针的区别：`flag_runtime_state.py` 读的是**子进程命令行**，那只能证明开关进了
命令行；本脚本要证明的是**浏览器真的把自己画成了那个样子**：

  1. 启动一个独立 profile 的窗口化实例（不传启动 URL）；
  2. 用 CDP 新建标签并**导航**到 chrome://version，读真实 DOM 文本，核对内置标志是否
     真的出现在"命令行"一行里（含 D51 修复后的 `param/true` 形式）；
  3. 导航到 chrome://gpu，读 Graphics Feature Status，核对 GPU 光栅化在、SkiaGraphite 关；
  4. 各出一张 PNG 截图（由人读图，不靠脚本自证）；
  5. 顺带确认"命令行传 chrome:// URL 当启动页"是**上游有意禁止**，不是本分支回归：
     `startup_tab_provider.cc:342` 把每个位置参数交给 `ValidateLaunchUrlWebUnsafe`，
     而 `url_util.cc:85-89` 的放行集合只有 web-safe scheme、`file:`、`about:blank`
     （外加 headless 的 `--allow-chrome-scheme-url` 与 ChromeOS 的 settings 重置页）。
     chrome:// 不在集合内 → 解析阶段就返回 kNo → 回落到 NTP。因此本脚本一律用 CDP
     导航打开 WebUI，而不是靠启动参数（https 启动参数是正常放行的，见下面对照）。

退出码：0=全部判据成立；1=有判据不成立；2=环境不满足（连不上/找不到二进制）。
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp                                                     # noqa: E402

DEV_EXE = r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"
INSTALLED_EXE = r"C:\Users\Administrator\AppData\Local\Chromium\Application\chrome.exe"
OUT = r"D:\wxmuma\thorium\.cycle4"
PORT = 9351


def must(cond, label, results):
    results[label] = bool(cond)
    return bool(cond)


def start(exe, profile, port, startup_arg=None):
    os.makedirs(profile, exist_ok=True)
    argv = [exe, "--user-data-dir=" + profile, "--remote-debugging-port=%d" % port,
            "--no-first-run", "--no-default-browser-check"]
    if startup_arg:
        argv.append(startup_arg)
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not cdp.wait_for_port(port, timeout=30):
        proc.kill()
        raise SystemExit("FAIL: 端口 %d 起不来（实例没起来或调试端口被占）" % port)
    time.sleep(3)
    return proc


def read_page(tab, url, settle=2.0):
    """导航后读**穿透 shadow DOM** 的整页文本。

    不能用 `document.body.innerText`：chrome://gpu 把整份报告渲染进 `<info-view>` 的
    shadow root，body.innerText 实测长度为 0，会把正常渲染误判成空白页（本轮 R1 首次
    跑出的 6 条 GPU 判据"不成立"就是这个探针缺陷，截图证明页面本身是好的）。
    """
    tab.navigate(url)
    txt = tab.wait_for_text(min_len=60, timeout=25)
    time.sleep(settle)
    longer = tab.wait_for_text(min_len=len(txt) + 1, timeout=4)
    return longer if len(longer) > len(txt) else txt


def main():
    res = {}
    os.makedirs(OUT, exist_ok=True)
    if not os.path.isfile(DEV_EXE):
        print("FAIL: 找不到被测二进制 %s" % DEV_EXE)
        return 2
    prof = os.path.join(OUT, "r1-prof")
    proc = start(DEV_EXE, prof, PORT)
    try:
        # --- chrome://version：真实 DOM ---
        tab = cdp.Tab(port=PORT, url="about:blank")
        vtxt = read_page(tab, "chrome://version")
        res["version_text_len"] = len(vtxt)
        res["version_page_readable"] = len(vtxt) > 1000 and not cdp.is_error_page(vtxt)
        res["version_has_product"] = "155.0.8059.40" in vtxt
        # 关键：D51 修复后的 params 形式必须带值
        res["version_params_have_value"] = ("without_spellcheck/true" in vtxt and
                                            "high_stream_priority/true" in vtxt)
        res["version_old_broken_params"] = "without_spellcheck/without_translate" in vtxt
        res["version_has_gpu_raster"] = "enable-gpu-rasterization" in vtxt
        res["version_has_disable_bg_media"] = "disable-background-media-suspend" in vtxt
        res["version_skia_graphite_disabled"] = "disable-features=" in vtxt and "SkiaGraphite" in vtxt
        res["version_fling_gone"] = "FlingSchedulingImprovements" not in vtxt
        res["version_jsflags_present"] = "invocation_count_for_maglev" in vtxt
        res["screenshot_version_bytes"] = tab.screenshot(os.path.join(OUT, "r1_version.png"))
        # 把命令行那一行原样留下（人读）
        line = [l for l in vtxt.splitlines() if "enable-features" in l]
        res["cmdline_line"] = line[0] if line else "NONE"

        # --- chrome://gpu：真实 DOM（内容在 <info-view> 的 shadow root 里）---
        gtxt = read_page(tab, "chrome://gpu")
        res["gpu_text_len"] = len(gtxt)
        # 判据用空白折叠后的文本：shadowRoot 没有 innerText，取到的是 textContent，
        # 列表项之间不产生换行，直接 raw 匹配会因 DOM 结构而非语义差异误判。
        gn = " ".join(gtxt.split())
        for label, needle in (("gpu_canvas_hw", "Canvas: Hardware accelerated"),
                              ("gpu_webgl_hw", "WebGL: Hardware accelerated"),
                              ("gpu_decode_hw", "Video Decode: Hardware accelerated"),
                              ("gpu_compositing_hw", "Compositing: Hardware accelerated"),
                              ("gpu_raster_hw", "Rasterization: Hardware accelerated"),
                              ("gpu_graphite_off", "Skia Graphite: Disabled")):
            res[label] = needle in gn
        # 取到内容极少 = 页面/探针本身失败，必须与"特性不达标"区分开，否则又会假绿。
        res["gpu_page_readable"] = len(gtxt) > 5000 and not cdp.is_error_page(gtxt)
        res["gpu_software_fallback"] = "Software only, hardware acceleration" in gn
        res["screenshot_gpu_bytes"] = tab.screenshot(os.path.join(OUT, "r1_gpu.png"))

        # --- 真实站点渲染 ---
        stxt = read_page(tab, "https://www.example.com")
        res["site_text_len"] = len(stxt)
        res["site_page_readable"] = len(stxt) > 20 and not cdp.is_error_page(stxt)
        res["site_title"] = tab.evaluate("document.title")
        res["screenshot_site_bytes"] = tab.screenshot(os.path.join(OUT, "r1_site.png"))
        tab.close()

        # --- 启动参数行为对照：chrome:// URL vs https URL ---
        for tag, arg, port in (("startup_chrome_url", "chrome://version", PORT + 10),
                               ("startup_https_url", "https://www.example.com", PORT + 11)):
            p2 = os.path.join(OUT, "r1-" + tag)
            start(DEV_EXE, p2, port, startup_arg=arg)
            try:
                time.sleep(6)
                pages = [t for t in cdp.available_targets(port) if t.get("type") == "page"]
                res[tag] = [t.get("url") for t in pages]
            finally:
                kill_profile(p2)
    finally:
        kill_profile(prof)
        try:
            proc.wait(timeout=20)
        except Exception:                                    # noqa: BLE001
            proc.kill()

    print(json.dumps(res, ensure_ascii=False, indent=2))
    hard_fail = []
    for k in ("version_page_readable", "version_has_product", "version_params_have_value",
              "version_has_gpu_raster", "version_has_disable_bg_media",
              "version_skia_graphite_disabled", "version_fling_gone",
              "version_jsflags_present",
              "gpu_page_readable", "gpu_canvas_hw", "gpu_webgl_hw", "gpu_decode_hw",
              "gpu_compositing_hw", "gpu_raster_hw", "gpu_graphite_off",
              "site_page_readable"):
        if not res.get(k):
            hard_fail.append(k)
    if res.get("version_old_broken_params"):
        hard_fail.append("version_old_broken_params(broken param form still present)")
    if res.get("gpu_software_fallback"):
        hard_fail.append("gpu_software_fallback(software rendering)")
    print("\nFAILED-CHECKS: %s" % (hard_fail or "none"))
    return 1 if hard_fail else 0


def kill_profile(profile):
    left = cdp.kill_instance(profile)
    if left:
        print("WARN: profile %s 仍有 %d 个进程残留" % (profile, left))
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    "Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % profile],
                   capture_output=True)


if __name__ == "__main__":
    sys.exit(main())
