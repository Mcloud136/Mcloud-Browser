#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测：开着浏览器时安装新版，到底生效没有（决定安装包装器要不要"关闭旧实例"）。

背景（源码级推断，本脚本负责证真或证伪）：
  * 载荷是**旁路新版本目录**（install_worker.cc:295-306），运行中的 chrome.dll 不被覆盖；
  * 根目录启动桩被锁，上游走 in-use 分支：暂存成 new_chrome.exe / chrome_proxy.new.exe
    并写一条 rename-chrome-exe AppCommand（install_worker.cc:867-901）；
  * 收尾改名在**系统级安装**下整个委托给 Google Update（upgrade_util_win.cc:505-506），
    而我们不发布 Google Update ⇒ 推断：改名永远不会发生，用户下次启动仍是旧版。

做法：先装 151（系统级）→ 启动它并保持运行 → 再装 155（r5，系统级）→ 对比
根 chrome.exe 的文件版本、出现了哪些暂存文件、注册表里有没有待执行的改名命令、
旧版本目录是否被删；最后关掉旧实例、重新双击根 chrome.exe，读 chrome://version
看**实际跑起来的是哪一版**。用完卸载并确认机器复原。

只用这次 Program Files 下的测试安装；用户自己的用户级安装完全不碰。
"""
import json
import os
import subprocess
import sys
import time
import winreg

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "benchmark", "tools"))
import cdp                                                        # noqa: E402

THOR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OLD_PKG = os.path.join(THOR, "mcloud_151.0.7922.99_win64_mini_installer.exe")
NEW_PKG = os.path.join(THOR, "mcloud_155.0.8059.40_win64_mini_installer.exe")
APP = r"C:\Program Files\Chromium\Application"
EXE = os.path.join(APP, "chrome.exe")
PORT = 9471
prof = os.path.join(THOR, ".cycle4", "inuse-prof")
PS = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]


def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def file_version(path):
    if not os.path.isfile(path):
        return "ABSENT"
    out = run(PS + ["(Get-Item -LiteralPath '%s').VersionInfo.ProductVersion" % path]).stdout
    return out.strip() or "(empty)"


def snapshot(label):
    dirs = sorted(d for d in os.listdir(APP)) if os.path.isdir(APP) else ["<no Application dir>"]
    ver_dirs = [d for d in dirs if d[:1].isdigit()]
    snap = {
        "label": label,
        "root_chrome_exe_version": file_version(EXE),
        "root_new_chrome_exe": os.path.isfile(os.path.join(APP, "new_chrome.exe")),
        "root_chrome_proxy_new_exe": os.path.isfile(os.path.join(APP, "chrome_proxy.new.exe")),
        "version_dirs": ver_dirs,
        "setup_metrics": os.path.isdir(os.path.join(APP, "SetupMetrics")),
        "flags_in_155_dir": os.path.isfile(os.path.join(APP, "155.0.8059.40", "mcloud_flags.txt")),
        "flags_in_151_dir": os.path.isfile(os.path.join(APP, "151.0.7922.99", "mcloud_flags.txt")),
        "app_commands": dump_app_commands(),
    }
    return snap


def dump_app_commands():
    r"""把 Clients\...\Commands 下的待执行改名命令原样抓出来。"""
    found = []
    for hive, name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
        try:
            key = winreg.OpenKey(hive, r"SOFTWARE\Chromium\Clients")
        except OSError:
            continue
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                guid = winreg.EnumKey(key, i)
                for sub in (r"%s\Commands" % guid, r"%s" % guid):
                    try:
                        k2 = winreg.OpenKey(key, sub)
                    except OSError:
                        continue
                    try:
                        for j in range(winreg.QueryInfoKey(k2)[1]):
                            n, v, _t = winreg.EnumValue(k2, j)
                            if isinstance(v, str) and ("rename" in n.lower() or "rename" in v.lower()):
                                found.append("%s\\Clients\\%s -> %s = %s" % (name, sub, n, v[:160]))
                    finally:
                        winreg.CloseKey(k2)
        finally:
            winreg.CloseKey(key)
    return found


def install(pkg):
    t0 = time.time()
    r = run(PS + ["$p = Start-Process -FilePath '%s' -ArgumentList "
                  "'--system-level','--verbose-logging' -Wait -PassThru; $p.ExitCode" % pkg],
            timeout=900)
    return {"rc": r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?",
            "secs": round(time.time() - t0, 1), "stderr": r.stderr.strip()[:200]}


def running_version_dirs():
    """运行中的 chrome.dll 来自哪个版本目录（直接看进程的模块路径）。"""
    out = run(PS + ["Get-Process chrome -ErrorAction SilentlyContinue | "
                    "ForEach-Object { try { $_.Modules | Where-Object { $_.ModuleName -eq 'chrome.dll' } | "
                    "ForEach-Object { $_.FileName } } } catch {} | Select-Object -Unique"])
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def main():
    res = {"steps": []}
    for p in (OLD_PKG, NEW_PKG):
        if not os.path.isfile(p):
            print("FAIL: 找不到安装包 %s" % p)
            return 2
    if os.path.isdir(APP):
        print("FAIL: %s 已存在，先确认这不是别人的现场" % APP)
        return 2
    try:
        res["steps"].append(("install 151", install(OLD_PKG)))
        res["after_151"] = snapshot("after-151")
        os.makedirs(prof, exist_ok=True)
        proc = subprocess.Popen([EXE, "--user-data-dir=" + prof,
                                 "--remote-debugging-port=%d" % PORT,
                                 "--no-first-run", "--no-default-browser-check"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
        res["running_dll_paths_before"] = running_version_dirs()
        res["browser_running"] = proc.poll() is None
        if not res["browser_running"]:
            print(json.dumps(res, ensure_ascii=False, indent=2))
            print("FAIL: 旧版没起来，实验前提不成立")
            return 2
        # 关键一步：浏览器开着的时候装新版
        res["steps"].append(("install 155 while running", install(NEW_PKG)))
        res["after_inuse_install"] = snapshot("after-inuse-install")
        res["running_dll_paths_after"] = running_version_dirs()
        # 关掉旧实例，再"用户下次双击"看看跑到哪一版
        cdp.kill_instance(prof)
        time.sleep(3)
        subprocess.Popen([EXE, "--user-data-dir=" + prof + "2",
                                  "--remote-debugging-port=%d" % PORT,
                                  "--no-first-run", "--no-default-browser-check"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
        if cdp.wait_for_port(PORT, timeout=40):
            tab = cdp.Tab(port=PORT, url="about:blank")
            tab.navigate("chrome://version")
            txt = tab.wait_for_text(1000, timeout=30)
            tab.close()
            line = [l for l in txt.splitlines() if "Chromium" in l or "151." in l or "155." in l]
            res["launched_version_line"] = line[:3]
            res["actually_running"] = ("155.0.8059.40" if "155.0.8059.40" in txt
                                       else "151.0.7922.99" if "151.0.7922.99" in txt else "?")
        res["after_relaunch"] = snapshot("after-relaunch")
        res["running_dll_paths_relaunched"] = running_version_dirs()
        cdp.kill_instance(prof)
        cdp.kill_instance(prof + "2")
    finally:
        if os.path.isdir(APP):
            r = run(PS + ["$p = Start-Process -FilePath (Get-ChildItem '%s' -Recurse -Filter setup.exe "
                          "| Select-Object -First 1).FullName -ArgumentList "
                          "'--uninstall','--system-level','--verbose-logging' -Wait -PassThru; $p.ExitCode"
                          % APP], timeout=600)
            res["uninstall_rc"] = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
        time.sleep(3)
        res["program_files_still_present"] = os.path.isdir(APP)
        res["leftover_chrome_procs"] = len(run(
            PS + ["@(Get-Process chrome -ErrorAction SilentlyContinue)"]).stdout.split())
        run(PS + ["Remove-Item -Recurse -Force '%s','%s' -ErrorAction SilentlyContinue"
                  % (prof, prof + "2")])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
