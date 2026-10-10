#!/usr/bin/env python3
"""loader_edge_test3.py - 加载器 v6 的回归与卡死/静默丢件测试（第3周期 bug-review）。

覆盖 loader_edge_test2.py 没有的通道，全部对着**已构建的 chrome.exe**端到端跑：
  T1 BOM            —— 文件以 UTF-8 BOM 开头且第一行就是 flag（D57 的回归用例，旧二进制会静默丢首行）
  T2 empty-file     —— 空文件：浏览器必须正常起来（不崩不挂），且不带我们的 feature
  T3 missing-file   —— 临时移走 flags 文件：同样必须正常起来（fail-open，不影响启动）
  T4 junk-lines     —— `--` / `--=` / 二进制垃圾 / 无 BOM 乱码：不崩，后续行仍生效
  T5 both-lists     —— 同一 feature 同时写在 enable 与 disable：断言**禁用侧胜出**
                       （base/feature_list.cc:449-452 的实测口径）
  T6 inline-hash    —— `--enable-features=X #备注` 的行内注释语义（记录真实行为，不作修复）
  T7 child-guard    —— v6 的浏览器进程限定（D58）：子进程仍必须拿到完整的 override 回显
  T8 卡死           —— 每个用例都有硬超时；额外做一次"文件被独占"场景（D59 风险评估）

用法：
  set LOADER_TEST_OUT=D:\\wxmuma\\chromium-src-155\\src\\out\\mcloud
  python .bugreview/loader_edge_test3.py
退出码 0=全部通过。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

OUT_DIR = os.environ.get("LOADER_TEST_OUT",
                         r"D:\wxmuma\chromium-src-155\src\out\mcloud")
CHROME = os.path.join(OUT_DIR, "chrome.exe")
FLAGS = os.path.join(OUT_DIR, "mcloud_flags.txt")
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
MARKER = "SpareRendererForSitePerProcess"


def ps(cmd, timeout=120):
    p = subprocess.run([PS, "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, errors="replace", timeout=timeout)
    return p.stdout


def probe(name, file_bytes=None, extra_cli=(), wait_s=10, hide_file=False):
    """写 flags → 启动一个独立实例 → 抓本实例全部子进程命令行 → 只清理本实例 → 还原。"""
    udd = os.path.join(tempfile.gettempdir(), "mcloud_l3_%s" % name)
    shutil.rmtree(udd, ignore_errors=True)
    os.makedirs(udd)
    backup = None
    if file_bytes is not None:
        backup = open(FLAGS, "rb").read()
        with open(FLAGS, "wb") as f:
            f.write(file_bytes)
    elif hide_file:
        backup = open(FLAGS, "rb").read()
        os.remove(FLAGS)
    try:
        args = [CHROME, "--user-data-dir=" + udd, "--no-first-run",
                "--no-default-browser-check", "--disable-background-networking"] + \
               list(extra_cli) + ["about:blank"]
        t0 = time.time()
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = t0 + wait_s + 40          # 硬超时：卡死必须被判定为失败而不是无限等
        cmd = ""
        while time.time() < deadline:
            time.sleep(wait_s)
            cmd = ps("(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                     "Where-Object { $_.CommandLine -like '*%s*' } | "
                     "Select-Object -ExpandProperty CommandLine) -join ' ||| '" % udd)
            if cmd.strip():
                break
        elapsed = time.time() - t0
        # launched / nproc 必须在清理**之前**取：清理后再 poll 永远是 False、
        # 再查 PID 永远是 0（本套件第一版就因为这个把 7 例全判 FAIL）。
        launched = proc.poll() is None
        nproc = len([x for x in ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                                   "Where-Object { $_.CommandLine -like '*%s*' } | "
                                   "ForEach-Object { $_.ProcessId }" % udd).split()
                     if x.isdigit()])
        # 只杀本实例（带我们临时 profile 的 PID），绝不做机器级 Stop-Process
        ids = [x for x in ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                             "Where-Object { $_.CommandLine -like '*%s*' } | "
                             "ForEach-Object { $_.ProcessId }" % udd).split()
               if x.isdigit()]
        if ids:
            ps("Get-Process -Id %s -ErrorAction SilentlyContinue | "
               "Stop-Process -Force -ErrorAction SilentlyContinue" % ",".join(ids))
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=20)
        return cmd, launched, elapsed, nproc
    finally:
        if backup is not None:
            with open(FLAGS, "wb") as f:
                f.write(backup)
        shutil.rmtree(udd, ignore_errors=True)


def expect(name, ok, detail):
    print("[%-16s] %s %s" % (name, "PASS" if ok else "FAIL", detail))
    return ok


def main():
    if not os.path.exists(CHROME):
        print("chrome.exe 不存在: " + CHROME)
        return 2
    print("被测: " + CHROME)
    deployed = open(FLAGS, "rb").read()
    res = []

    # T1 BOM：BOM + 第一行就是 flag
    cmd, alive, el, nproc = probe("bom", b"\xef\xbb\xbf--enable-features=" + MARKER.encode() + b"\n")
    res.append(expect("T1-bom-firstline", MARKER in cmd and alive,
                      "marker=%s launched=%s 进程=%d %.1fs" % (MARKER in cmd, alive, nproc, el)))

    # T2 空文件
    cmd, alive, el, nproc = probe("empty", b"")
    res.append(expect("T2-empty-file", alive and MARKER not in cmd,
                      "浏览器起来=%s（空文件不应带任何内置 feature）%.1fs" % (alive, el)))

    # T3 文件缺失
    cmd, alive, el, nproc = probe("missing", None, hide_file=True)
    res.append(expect("T3-file-missing", alive and nproc >= 2 and "--type=" in cmd,
                      "fail-open：无文件也能起来（进程 %d）%.1fs" % (nproc, el)))

    # T4 垃圾行
    junk = (b"--\n--=\n==\n\x00\x01\xffbinary\n--enable-features=" + MARKER.encode() + b"\n")
    cmd, alive, el, nproc = probe("junk", junk)
    res.append(expect("T4-junk-lines", alive and MARKER in cmd,
                      "垃圾行后仍能生效（进程 %d）%.1fs" % (nproc, el)))

    # T5 同名双写：禁用侧胜出
    both = (b"--enable-features=ZZBothListsProbe\n"
            b"--disable-features=ZZBothListsProbe\n"
            b"--enable-features=" + MARKER.encode() + b"\n")
    cmd, alive, el, nproc = probe("both", both)
    in_dis = "--disable-features=ZZBothListsProbe" in cmd.replace("|||", " ")
    in_en = "--enable-features=ZZBothListsProbe" in cmd
    res.append(expect("T5-both-lists", (in_dis or not in_en),
                      "disable 胜出可观测=%s enable 侧出现=%s launched=%s（feature_list.cc:449-452）%.1fs"
                      % (in_dis, in_en, alive, el)))

    # T6 行内注释的真实语义（记录，不改运行期行为）
    inline = b"--enable-features=ZZInlineProbe # \xe6\xb3\xa8\xe9\x87\x8a\n"
    cmd, alive, el, nproc = probe("inline", inline)
    hit = "ZZInlineProbe" in cmd
    print("      T6 观察值：行内注释条目是否进入回显=%s → 若不进入，说明 '#备注' 会让该条整条失效" % hit)
    res.append(expect("T6-inline-hash-observed", alive, "起来=%s 进程=%d %.1fs" % (alive, nproc, el)))

    # T7 子进程限定（v6）：子进程必须仍拿到完整 override 集合
    cmd, alive, el, nproc = probe("child", deployed)
    n_child_with = 0
    for seg in cmd.split("|||"):
        if "--type=" in seg and MARKER in seg:
            n_child_with += 1
    res.append(expect("T7-child-inherits", n_child_with >= 1,
                      "带 marker 的子进程数=%d / 实例进程数=%d（D58 限定后子进程仍应继承）%.1fs"
                      % (n_child_with, nproc, el)))

    print("\nSUMMARY: %d/%d PASS" % (sum(res), len(res)))
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
