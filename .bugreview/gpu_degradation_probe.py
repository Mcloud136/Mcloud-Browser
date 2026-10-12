#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU 降级路径验证 —— 在**有独显的机器上**模拟"无独显环境"会怎样。

本机事实（第5周期 D143 钉死）：独显 RTX 4070 Laptop 驱动全部显示器，核显不驱动显示，
所以"没有独显/驱动挂了"这类场景在这台机器上只能靠命令行开关模拟。验三件事：

  1. 禁用 GPU 后 chrome://gpu **如实**报告软件渲染（不是嘴上禁用、页面仍报硬件加速）；
  2. 软件渲染下页面仍能渲染、WebGL 软件上下文仍能创建（SwiftShader 回退链真的在包里）；
  3. 默认路径作为对照：本机必须仍然报硬件加速 —— 没有这条，场景 1 的"报告变化"
     可能只是"页面没读到"（同族：缺席型判据要有正向对照）。

与 .cycle6 那份被回退的初版相比的三处改动（都是本仓纪律，不是风格）：
  * 端口不再写死 9361：与别的实例/上一轮残留抢端口就会连到**别人的浏览器**（D53）；
  * profile 落临时目录并在 finally 删除，不再写进 `.cycle6/`（D99：不在别人的证据目录里留产物）；
  * 页面判据**不依赖外网内容**：改用 `chrome://version`（本地、稳定）与 `data:` URL。
    记忆与 D137 一族都记着"example.com 正文改版会让判据莫名变红"。

退出码：0=判据成立；1=有判据不成立；2=环境不满足（找不到二进制/端口起不来/CDP 不可用）。
"""
import contextlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(THOR, "benchmark", "tools"))
import cdp                                                   # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INSTALLED = os.environ.get("MCHROME_INSTALLED_EXE") or \
    r"C:\Program Files\Chromium\Application\chrome.exe"


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


WEBGL_JS = ("(function(){try{var c=document.createElement('canvas');"
            "var gl=c.getContext('webgl')||c.getContext('experimental-webgl');"
            "if(!gl)return 'no-context';"
            "var dbg=gl.getExtension('WEBGL_debug_renderer_info');"
            "return dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):'ctx-ok';"
            "}catch(e){return 'err:'+e.message;}})()")


def run_case(name, extra_args, needles_gpu, prof_root, port):
    """跑一个场景：启动 → 读 chrome://gpu → 读本地页面 → 建 WebGL 上下文 → 收尾。"""
    prof = os.path.join(prof_root, "gpu-degrade-" + name)
    res = {"case": name, "extra": extra_args}
    try:
        cdp.launch(INSTALLED, prof, port, extra=extra_args)
    except Exception as exc:                                  # noqa: BLE001
        res["env_fail"] = "启动失败：%s" % exc
        return res
    try:
        if not cdp.wait_for_port(port, timeout=40):
            res["env_fail"] = "调试端口起不来（%d）" % port
            return res
        tab = cdp.Tab(port=port, url="about:blank")
        try:
            tab.navigate("chrome://gpu")
            # 等到确实读到驱动信息为止，而不是"有字符就行"——
            # chrome://gpu 正文开头只有内联 CSS，短文本判据会被样式满足（D184 同族）。
            gtxt = ""
            for _ in range(60):
                try:
                    gtxt = tab.deep_text()
                except cdp.CDPError:
                    gtxt = ""
                if "GL_RENDERER" in gtxt or "Graphics Feature Status" in gtxt:
                    break
                import time
                time.sleep(0.5)
            gn = " ".join(gtxt.split())
            res["gpu_text_len"] = len(gtxt)
            if not gn:
                res["env_fail"] = "chrome://gpu 正文读不到"
                return res
            for label, needle in needles_gpu:
                res[label] = needle in gn
            # 本地页面（不依赖外网）：chrome://version 必然有内容
            tab.navigate("chrome://version")
            vtxt = tab.wait_for_text(min_len=40, timeout=25)
            res["local_page_ok"] = len(vtxt) > 40 and not cdp.is_error_page(vtxt)
            # data: 页面上建 WebGL 上下文（软件回退的关键能力）
            tab.navigate("data:text/html,<title>gl</title><canvas id=c></canvas>")
            res["webgl"] = tab.evaluate(WEBGL_JS)
        finally:
            with contextlib.suppress(Exception):
                tab.close()
    finally:
        res["residue"] = cdp.kill_instance(prof, port=port)
        shutil.rmtree(prof, ignore_errors=True)
    return res


def main():
    if not os.path.isfile(INSTALLED):
        print("FAIL: 找不到安装后的二进制 %s（设 MCHROME_INSTALLED_EXE）" % INSTALLED)
        return 2
    prof_root = tempfile.mkdtemp(prefix="mcloud_gpu_degrade_")
    port = free_port()
    try:
        # 场景 1：整机禁用 GPU —— 页面必须报软件渲染，且不得再报硬件合成
        dg = run_case("disable-gpu", ["--disable-gpu"],
                      [("reports_software_only", "Software only, hardware acceleration unavailable"),
                       ("still_claims_hw_compositing", "Compositing: Hardware accelerated")],
                      prof_root, port)
        # 场景 2：强制软件 GL —— 软件 WebGL 必须可用
        ss = run_case("swiftshader", ["--use-gl=angle", "--use-angle=swiftshader"],
                      [("gpu_page_readable", "GL_RENDERER")], prof_root, port)
        # 场景 3：默认路径（正向对照）—— 本机必须仍报硬件加速
        df = run_case("default", [],
                      [("compositing_hw", "Compositing: Hardware accelerated"),
                       ("canvas_hw", "Canvas: Hardware accelerated"),
                       ("decode_hw", "Video Decode: Hardware accelerated")],
                      prof_root, port)
    finally:
        shutil.rmtree(prof_root, ignore_errors=True)

    cases = [dg, ss, df]
    hard = []
    for c in cases:
        if c.get("env_fail"):
            hard.append("%s: %s" % (c["case"], c["env_fail"]))
            continue
        if c["case"] == "disable-gpu":
            if not c.get("reports_software_only"):
                hard.append("disable-gpu: chrome://gpu 没有如实报告软件渲染")
            if c.get("still_claims_hw_compositing"):
                hard.append("disable-gpu: 禁用后仍报「Compositing: Hardware accelerated」（假阳性）")
            if not c.get("local_page_ok"):
                hard.append("disable-gpu: 软件渲染下本地页面都渲染不出来")
            # WebGL 的"软件实现"判据不能靠列厂商名：本机实测禁用 GPU 后拿到的是
            # `ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) …)` —— WARP，
            # 也是软件渲染器，写死 SwiftShader 会把好结果判成红（首版就是这么错的）。
            # 改用与默认场景对照 + 设备号排除：软件路径必须**不是**那块硬件适配器。
            webgl = str(c.get("webgl", ""))
            m = re.search(r"0x([0-9a-fA-F]{4,8})", str(df.get("webgl", "")))
            hw_id = m.group(1).lower() if m else ""
            if webgl in ("", "no-context") or webgl.startswith("err:"):
                hard.append("disable-gpu: WebGL 上下文创建失败：%s" % webgl)
            elif hw_id and hw_id in webgl.lower():
                hard.append("disable-gpu: WebGL 仍在用硬件适配器（设备号 %s）：%s" % (hw_id, webgl))
            elif webgl == str(df.get("webgl", "")):
                hard.append("disable-gpu: WebGL 渲染器与默认场景完全相同 ⇒ 禁用没起作用：%s" % webgl)
        elif c["case"] == "swiftshader":
            if not c.get("gpu_page_readable"):
                hard.append("swiftshader: chrome://gpu 读不到 GL_RENDERER")
            if not c.get("local_page_ok"):
                hard.append("swiftshader: 页面不可用")
            if "swiftshader" not in str(c.get("webgl", "")).lower():
                hard.append("swiftshader: WebGL 报告的不是软件实现：%s" % c.get("webgl"))
        else:
            for k in ("compositing_hw", "canvas_hw", "decode_hw", "local_page_ok"):
                if not c.get(k):
                    hard.append("default（对照）: %s 不成立 ⇒ 默认路径的硬件加速掉了，"
                                "此时上面两场的结论都失去对照" % k)
        if c.get("residue"):
            hard.append("%s: 收尾后仍残留 %s 个进程" % (c["case"], c["residue"]))

    print(json.dumps(cases, ensure_ascii=False, indent=1))
    print("\nFAILED-CHECKS: %s" % (hard or "none"))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
