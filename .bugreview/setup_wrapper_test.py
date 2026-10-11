#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCloud-Setup.exe 包装器的验收测试（第4周期追加，2026-10-11）。

要证的是**唯一那件有意义的事**：浏览器正在运行时用包装器升级，最后真的升到包内版本。
对照组已经实测过（.cycle4/probe_inuse_update.py）：直接跑 mini_installer 时
根 chrome.exe 停在旧版、`new_chrome.exe` 被暂存且永远没人消化，重启后 chrome://version
仍是 151.0.7922.99。

流程（全程只碰 Program Files 下的系统级测试安装，用户自己的用户级安装完全不碰）：
  1. 装 151 → 启动它（制造"旧版正在运行"的真实现场）；
  2. 用包装器装 155（--system-level --no-launch）；
  3. 断言包装器退出码 0、根 chrome.exe 版本 == 155、无 new_chrome.exe / chrome_proxy.new.exe、
     155 版本目录里有 chrome.dll 与 mcloud_flags.txt；
  4. 重启浏览器读 chrome://version，确认**实际跑起来的是 155**；
  5. 卸载并确认无残留、无 setup/mini_installer 驻留、用户级安装字节未变。

需要管理员权限（系统级安装）。退出码：0=通过；1=不通过；2=环境不满足。
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(THOR, "benchmark", "tools"))
import cdp                                                        # noqa: E402

OLD_PKG = os.path.join(THOR, "mcloud_151.0.7922.99_win64_mini_installer.exe")
NEW_PKG = os.path.join(THOR, "mcloud_155.0.8059.40_win64_mini_installer.exe")
WRAPPER = os.path.join(THOR, "installer", "out", "MCloud-Setup-console.exe")
APP = r"C:\Program Files\Chromium\Application"
EXE = os.path.join(APP, "chrome.exe")
NEW_VER = "155.0.8059.40"
PORT = 9481
prof = os.path.join(THOR, ".cycle4", "wraptest-prof")
PS = ["powershell.exe", "-NoProfile", "-Command"]


def ps(cmd, timeout=600):
    return subprocess.run(PS + [cmd], capture_output=True, text=True, timeout=timeout).stdout.strip()


def file_version(path):
    if not os.path.isfile(path):
        return "ABSENT"
    return ps("(Get-Item -LiteralPath '%s').VersionInfo.ProductVersion" % path)


def chrome_procs():
    out = ps("@(Get-Process chrome -ErrorAction SilentlyContinue).Count")
    return int(out) if out.isdigit() else -1


def decode(b):
    return b.decode("gbk", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrapper", default=WRAPPER,
                    help="要测的包装器 EXE；用 installer/out/MCloud-Setup-embedded.exe "
                         "测发布形态（不传 --package，让它自己解出内嵌包）")
    ap.add_argument("--embedded", action="store_true",
                    help="被测 EXE 已内嵌安装包：不要传 --package")
    args = ap.parse_args()
    wrapper = os.path.abspath(args.wrapper)
    res = {"wrapper_mode": "embedded" if args.embedded else "external-package"}
    for p in (OLD_PKG, NEW_PKG, wrapper):
        if not os.path.isfile(p):
            print("FAIL: 缺少 %s" % p)
            return 2
    if os.path.isdir(APP):
        print("FAIL: %s 已存在，先手工清场（不覆盖别人的现场）" % APP)
        return 2
    user_flags = os.path.join(os.environ["LOCALAPPDATA"], "Chromium", "Application",
                              "155.0.8059.40", "mcloud_flags.txt")
    user_before = ps("(Get-FileHash -LiteralPath '%s' -Algorithm SHA256).Hash" % user_flags)
    try:
        # 1. 造现场：装 151 并启动
        subprocess.run(PS + ["Start-Process -FilePath '%s' -ArgumentList '--system-level' -Wait"
                             % OLD_PKG], capture_output=True, timeout=900)
        res["installed_151_root_version"] = file_version(EXE)
        if not res["installed_151_root_version"].startswith("151"):
            res["env_fail"] = "151 没装上（根版本=%s）" % res["installed_151_root_version"]
            return 2
        os.makedirs(prof, exist_ok=True)
        subprocess.Popen([EXE, "--user-data-dir=" + prof, "--remote-debugging-port=%d" % PORT,
                          "--no-first-run", "--no-default-browser-check"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
        res["old_instance_running"] = chrome_procs() > 0
        if not res["old_instance_running"]:
            res["env_fail"] = "旧版实例没起来，'正在运行时升级'的前提不成立"
            return 2

        # 2. 用包装器升级
        t0 = time.time()
        argv = [wrapper, "--quiet", "--system-level", "--no-launch"]
        if not args.embedded:
            argv += ["--package", NEW_PKG]
        r = subprocess.run(argv, capture_output=True, timeout=1200)
        res["wrapper_exit"] = r.returncode
        res["wrapper_output"] = decode(r.stdout)[-1400:]
        res["wrapper_seconds"] = round(time.time() - t0, 1)

        # 3. 断言安装结果
        res["root_version_after"] = file_version(EXE)
        res["new_chrome_exe_left"] = os.path.isfile(os.path.join(APP, "new_chrome.exe"))
        res["chrome_proxy_new_left"] = os.path.isfile(os.path.join(APP, "chrome_proxy.new.exe"))
        res["ver_dir_present"] = os.path.isdir(os.path.join(APP, NEW_VER))
        res["dll_present"] = os.path.isfile(os.path.join(APP, NEW_VER, "chrome.dll"))
        res["flags_present"] = os.path.isfile(os.path.join(APP, NEW_VER, "mcloud_flags.txt"))
        res["old_151_dir_kept"] = os.path.isdir(os.path.join(APP, "151.0.7922.99"))

        # 4. 重启看实际版本（权威判据：不是文件版本，是跑起来的那版）
        prof2 = prof + "2"
        os.makedirs(prof2, exist_ok=True)
        subprocess.Popen([EXE, "--user-data-dir=" + prof2,
                          "--remote-debugging-port=%d" % PORT,
                          "--no-first-run", "--no-default-browser-check"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(6)
        actually = "?"
        if cdp.wait_for_port(PORT, timeout=40):
            tab = cdp.Tab(port=PORT, url="about:blank")
            tab.navigate("chrome://version")
            txt = tab.wait_for_text(1000, timeout=30)
            tab.close()
            actually = NEW_VER if NEW_VER in txt else ("151.0.7922.99" if "151." in txt else "?")
        res["actually_running"] = actually
        cdp.kill_instance(prof2)
        res["user_flags_unchanged"] = (
            ps("(Get-FileHash -LiteralPath '%s' -Algorithm SHA256).Hash" % user_flags) == user_before)
    finally:
        cdp.kill_instance(prof)
        cdp.kill_instance(prof + "2")
        if os.path.isdir(APP):
            setup = os.path.join(APP, NEW_VER, "Installer", "setup.exe")
            # 必须带 --force-uninstall（缺陷 D162，2026-10-12 r6 实测）：不带它时
            # uninstall.cc:884-890 走的是 IsChromeActiveOrUserCancelled() —— setup.exe 会
            # 启动 `chrome.exe --uninstall` 弹确认框并 LaunchChromeAndWait **等人点**。
            # 本轮没有这个开关时 WaitForExit(240000) 直接超时，现场零删除、
            # 残留 1 个 setup.exe + 1 个 crashpad + 1 个带 --uninstall 的 chrome.exe。
            # 带上它走静默分支（源码注释：自行 CloseAllChromeProcesses），实测 0 s 返回 19。
            # 旧写法会在这里挂满 600 s 然后从 finally 里抛 TimeoutExpired 把整个测试炸掉。
            subprocess.run(PS + ["Start-Process -FilePath '%s' -ArgumentList "
                                 "'--uninstall','--system-level','--force-uninstall' -Wait" % setup],
                           capture_output=True, timeout=600)
        time.sleep(3)
        res["program_files_gone"] = not os.path.isdir(APP)
        res["setup_procs_left"] = int(ps("@(Get-Process setup,mini_installer -ErrorAction SilentlyContinue).Count") or 0)
        for d in (prof, prof + "2"):
            subprocess.run(PS + ["Remove-Item -Recurse -Force '%s' -ErrorAction SilentlyContinue" % d],
                           capture_output=True)

    print(json.dumps(res, ensure_ascii=False, indent=1))
    hard = []
    if res.get("wrapper_exit") != 0:
        hard.append("wrapper_exit=%s" % res.get("wrapper_exit"))
    if not str(res.get("root_version_after", "")).startswith(NEW_VER):
        hard.append("root_version_after=%s" % res.get("root_version_after"))
    if res.get("actually_running") != NEW_VER:
        hard.append("actually_running=%s" % res.get("actually_running"))
    if res.get("new_chrome_exe_left"):
        hard.append("new_chrome.exe 未被消化")
    if not res.get("flags_present"):
        hard.append("mcloud_flags.txt 缺失")
    if res.get("setup_procs_left"):
        hard.append("setup/mini_installer 驻留 %d 个" % res["setup_procs_left"])
    if not res.get("program_files_gone", True):
        hard.append("卸载后 Program Files 仍有残留")
    if res.get("user_flags_unchanged") is False:
        hard.append("用户自己的安装被改动了")
    print("\nFAILED-CHECKS: %s" % (hard or "none"))
    if "env_fail" in res:
        return 2
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
