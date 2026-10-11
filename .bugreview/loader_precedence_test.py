#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""加载器路径优先级实操测试（第4周期，2026-10-11；缺陷 D109）。

要证的事：安装版布局下 `Application\\mcloud_flags.txt`（根目录残留）会不会**静默压制**
`Application\\<版本号>\\mcloud_flags.txt`（安装包真正写进去的那份）。

为什么这是个真问题，而不是理论：
  * 上游决定"程序住在哪个目录"的依据是 **chrome.dll 在哪**
    （`chrome/app/main_dll_loader_win.cc:175-191`：先试 `exe_dir\\<kChromeVersion>\\chrome.dll`，
    找不到才退回 `exe_dir\\chrome.dll`）。安装版里 chrome.dll 在版本目录，根目录的
    chrome.exe 只是 4 MB 的启动桩。
  * 加载器 v7 的依据却是 **exe 在哪**，且把 exe 同目录排在前面 —— 与上游口径相反。
  * 本机实测存在这种残留：`C:\\Users\\Administrator\\AppData\\Local\\Chromium\\Application\\mcloud_flags.txt`
    由 9 月排障脚本 `.diag/verify_flags_edit.ps1` 手写产生，至今仍在。
  * 更糟的是验证链同构地错：`.bugreview/flag_runtime_state.py` 的 `resolve_flags_path()`
    照抄了 v7 的优先级，于是"读的是被压制的那份、断言的也是那份"→ 门禁全绿而线上跑的是
    旧文件（假绿，D47/D62 同族）。

做法（不碰用户安装目录、不碰 out/mcloud）：用**硬链接**在 out 树外拼一个与真实安装
同形的沙箱目录，两份 flags 各带一个不同的探针开关，然后真启动一次浏览器，从
chrome://version 的"命令行"行读回**实际生效**的那枚探针。

退出码：0=生效的是版本目录那份（正确）；1=生效的是根目录残留（D109 复现）；
2=环境不满足（起不来 / 读不到命令行）。判不出来一律非 0。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THOR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(THOR, "benchmark", "tools"))
import cdp                                                        # noqa: E402

DEFAULT_OUT = os.environ.get("MCHROME_OUT",
                             r"D:\wxmuma\chromium-src-155\src\out\mcloud")
VERSION = "155.0.8059.40"          # 必须等于编译进 chrome.exe 的 chrome::kChromeVersion
SANDBOX_MARK = ".mcloud-loader-sandbox"
# 安装版运行所需的子目录（只这些；obj/gen 等构建中间目录一律不链）
RUNTIME_DIRS = ("locales", "resources", "angledata", "MEIPreload", "IwaKeyDistribution",
                "PrivacySandboxAttestationsPreloaded", "hyphen-data", "Dictionaries",
                "extensions")
PROBE = "--mcloud-shadow-probe="

# 控制台编码不是 UTF-8 时，中文说明可能触发 UnicodeEncodeError 把测试结果一起带走；
# 判据行本身是 ASCII（verdict / EXIT），所以这里只要求"永不因编码崩"。
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:                                           # noqa: BLE001
    pass


def link_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError as exc:
        # 跨卷没有硬链接：沙箱与被测树必须同卷，否则只能整份拷贝（305 MB chrome.dll）。
        raise SystemExit("FAIL: 硬链接 %s -> %s 失败（%s）。沙箱必须与被测树同卷，"
                         "用 --sandbox 换一个同卷路径。" % (src, dst, exc)) from exc


def build_sandbox(sb, out_dir, flags_src):
    """拼出安装版同形布局：<sb>/mcloud_root/chrome.exe + <sb>/mcloud_root/<VERSION>/{chrome.dll,...}。"""
    if os.path.exists(sb) and not os.path.exists(os.path.join(sb, SANDBOX_MARK)):
        raise SystemExit("REFUSED: %s 已存在但不是本工具建的沙箱，拒绝删除陌生目录" % sb)
    if os.path.exists(sb):
        shutil.rmtree(sb)
    os.makedirs(sb)
    # 标记写在沙箱根：下次运行据此确认"这个目录确实是我建的"才敢删
    open(os.path.join(sb, SANDBOX_MARK), "w").close()
    root = os.path.join(sb, "mcloud_root")
    os.makedirs(root)
    exe = os.path.join(out_dir, "chrome.exe")
    dll = os.path.join(out_dir, "chrome.dll")
    if not (os.path.isfile(exe) and os.path.isfile(dll)):
        raise SystemExit("FAIL: %s 里没有 chrome.exe/chrome.dll，被测树不对" % out_dir)
    # 根目录：只有启动桩（与真实安装一致）——刻意**不放** chrome.dll
    link_file(exe, os.path.join(root, "chrome.exe"))
    ver = os.path.join(root, VERSION)
    os.makedirs(ver)
    link_file(dll, os.path.join(ver, "chrome.dll"))
    for name in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, name)
        # mcloud_flags.txt 必须排除：硬链接共享同一份数据，就地写会**截断 out/ 里的真文件**
        # （D99 同族的破坏面，只是这次方向反过来——沙箱反噬被测树）
        if os.path.isfile(p) and name not in ("chrome.dll", "mcloud_flags.txt"):
            link_file(p, os.path.join(ver, name))
    for d in RUNTIME_DIRS:
        src = os.path.join(out_dir, d)
        if not os.path.isdir(src):
            continue
        for dirpath, _dirnames, filenames in os.walk(src):
            rel = os.path.relpath(dirpath, src)
            for f in filenames:
                s = os.path.join(dirpath, f)
                link_file(s, os.path.join(ver, d, rel, f) if rel != "."
                          else os.path.join(ver, d, f))
    # 两份可区分的 flags：内容都来自仓库正文，只差探针开关
    body = open(flags_src, encoding="utf-8-sig").read()
    root_flags = os.path.join(root, "mcloud_flags.txt")
    ver_flags = os.path.join(ver, "mcloud_flags.txt")
    open(root_flags, "w", encoding="utf-8", newline="\n").write(body + "\n%sROOT\n" % PROBE)
    open(ver_flags, "w", encoding="utf-8", newline="\n").write(body + "\n%sVERSION\n" % PROBE)
    return root, root_flags, ver_flags


def probe(root_exe, port):
    """真启动一次，返回 chrome://version 命令行里出现的探针值（ROOT/VERSION/None）。"""
    prof = os.path.join(os.path.dirname(root_exe), "profile")
    subprocess.Popen([root_exe, "--user-data-dir=" + prof,
                             "--remote-debugging-port=%d" % port,
                             "--no-first-run", "--no-default-browser-check"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not cdp.wait_for_port(port, timeout=40):
            return None, "port %d never opened" % port
        time.sleep(3)
        tab = cdp.Tab(port=port, url="about:blank")
        tab.navigate("chrome://version")
        txt = tab.wait_for_text(min_len=1000, timeout=30)
        hit = [v for v in ("ROOT", "VERSION") if (PROBE + v) in txt]
        # 两枚都在 = 两份文件都被读了；一枚都没有 = 加载器根本没跑（都必须判环境失败）
        if len(hit) != 1:
            return None, "expected exactly one probe marker, got %s (text_len=%d)" % (hit, len(txt))
        return hit[0], None
    finally:
        left = cdp.kill_instance(os.path.dirname(root_exe))
        if left:
            print("WARN: 沙箱仍有 %d 个进程残留" % left)
        shutil.rmtree(prof, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT, help="被测构建目录（提供 chrome.exe/dll）")
    ap.add_argument("--sandbox", default=None, help="沙箱根（默认 out 同级目录之外）")
    ap.add_argument("--port", type=int, default=9381)
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    flags_src = os.path.join(THOR, "mcloud_flags.txt")
    if not os.path.isfile(flags_src):
        print("FAIL: 仓库根没有 mcloud_flags.txt")
        return 2
    sb = args.sandbox or os.path.join(
        # 默认落在 **构建目录与 git checkout 都之外**：out/mcloud 里面不行（D99 纪律），
        # src/ 里面也不行（会在 chromium 树里留一个 untracked 目录）。取 src 的上一级的
        # 上一级 = <...>\chromium-src-155\mcloud_loader_sandbox —— 与被测树同卷，硬链接
        # 才成立。首版默认值算出的是 src/out/mcloud_loader_sandbox，踩了前者。
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))),
        "mcloud_loader_sandbox")
    sb = os.path.abspath(sb)
    if os.path.commonpath([sb, out_dir]) == out_dir:
        print("FAIL: 沙箱路径 %s 落在被测树 %s 里面（D99 纪律：测试不得写发布目录）" % (sb, out_dir))
        return 2
    if "out" in [c.lower() for c in os.path.normpath(sb).split(os.sep)[:-1]]:
        print("FAIL: 沙箱路径 %s 位于某个 out/ 之下，会污染构建树" % sb)
        return 2
    if os.path.exists(os.path.join(sb, "args.gn")) or os.path.exists(os.path.join(sb, "build.ninja")):
        print("FAIL: 沙箱路径 %s 看起来是构建目录，拒绝使用" % sb)
        return 2

    root, root_flags, ver_flags = build_sandbox(sb, out_dir, flags_src)
    print("sandbox root   : %s" % root)
    print("  root flags   : %s (marker ROOT)" % root_flags)
    print("  version flags: %s (marker VERSION)" % ver_flags)
    try:
        winner, err = probe(os.path.join(root, "chrome.exe"), args.port)
    finally:
        shutil.rmtree(sb, ignore_errors=True)

    if winner is None:
        print(json.dumps({"verdict": "ENV-FAIL", "reason": err}, ensure_ascii=False))
        return 2
    print(json.dumps({"verdict": winner,
                      "meaning": {"ROOT": "根目录残留压制了版本目录里的正式文件（D109 成立）",
                                  "VERSION": "生效的是版本目录那份（优先级与上游 chrome.dll 口径一致）"}[winner]},
                     ensure_ascii=False))
    return 1 if winner == "ROOT" else 0


if __name__ == "__main__":
    sys.exit(main())
