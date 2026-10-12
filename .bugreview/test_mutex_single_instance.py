#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D132 单实例互斥的 Red→Green 判据（第7周期收口补写）。

背景与**为什么这次才算真的有判据**：
  * 缺陷档案里 D132 长期是「⬜ 待跟进」，位置栏写的就是"全文件无 Mutex"；
  * 被回退的第6轮曾交来一份同名测试，声称是 D132 的 Red→Green —— 但
    `git log -S"Mutex" -- installer/mcloud_setup.cs` **零命中**，说明包装器里
    从来没实现过互斥。一份"验证不存在的功能"的测试，通过与否都不说明任何事；
  * 所以本文件的顺序是：先实现互斥（mcloud_setup.cs），再用这份测试**双向**证明：
      Green：当前源码编译出的包装器 ⇒ 第二个并发实例必须 rc=2 并给出互斥提示；
      Red   ：HEAD 版本（改动前）编译出的包装器 ⇒ 第二个实例**不会**被挡住。
    没有 Red 这条，Green 的通过毫无意义（同 installer_arg_test.py 的 A/A' 结构）。

安全性（这是本仓纪律，不是可选项）：
  * 用 `--user-level --no-launch --package <睡 6 秒的 stub>`，不碰系统级、不启动浏览器；
  * **前门**：机器上若存在本产品的运行实例，直接 REFUSED/exit 2 —— 包装器会按安装路径
    优雅关闭它们（D52/D55/D106），绝不允许判据在被测目标正运行时顺手关掉别人的会话；
  * 四条污染自检（两个安装目录指纹 + 实例数 + 临时目录），且**自己**的临时目录在
    finally 里删掉并复核（第一版正是漏了这条才被本轮审计抓到）。

退出码：0=Green 成立且 Red 复现且无污染；1=判据不成立；2=环境不满足/前门拒绝。
"""
import glob
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "win_scripts"))
import build_setup_exe as BSE          # noqa: E402  复用同一套编译器发现逻辑（勿另写一份）

SRC_REL = "installer/mcloud_setup.cs"
SYSTEM_APPDIR = r"C:\Program Files\Chromium\Application"
USER_APPDIR = os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application")

STUB_CS = """
using System;
using System.Threading;
internal static class SleepStub {
    private static int Main(string[] argv) {
        Console.Out.WriteLine("stub start " + string.Join("|", argv));
        Console.Out.Flush();
        Thread.Sleep(6000);              // 把第一个实例按在临界区里
        return 0;
    }
}
"""

PS_INSTANCE_IDS = (
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.ExecutablePath -like ($env:T_SYS + '\\*') -or "
    "$_.ExecutablePath -like ($env:T_USER + '\\*') } | ForEach-Object { $_.ProcessId }")


def show(raw):
    """包装器是 GUI/控制台混合体，cp936 与 utf-8 都可能出现；两种都试过再判。"""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def has(raw_bytes, needle):
    """判据本身不依赖控制台编码（AGENTS.md「Python 判据脚本三条语言坑」②）。"""
    return any(needle.encode(enc) in (raw_bytes or b"") for enc in ("utf-8", "gbk"))


def ps_instance_ids():
    env = dict(os.environ, T_SYS=SYSTEM_APPDIR, T_USER=USER_APPDIR)
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", PS_INSTANCE_IDS],
                         capture_output=True, text=True, errors="replace",
                         env=env, timeout=180).stdout
    return sorted(int(x) for x in out.split() if x.strip().isdigit())


def listing(root):
    """目录指纹：文件记 (相对路径, 大小, sha16)，目录只记 (相对路径, 大小)。

    目录不记 mtime —— 空目录的 mtime 会被文件系统瞬态拨动，造成复现不出来的一次性红
    （第6周期 cycle-6 复核时实测，AGENTS.md 已记）。
    """
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, _dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        out.append(("D:" + rel, 0, ""))
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
                h = ""
                if st.st_size <= 8 * 1024 * 1024:
                    with io.open(p, 'rb') as bf:
                        h = hashlib.sha256(bf.read()).hexdigest()[:16]
                out.append(("F:" + os.path.relpath(p, root), st.st_size, h))
            except OSError:
                out.append(("F:" + os.path.relpath(p, root), -1, "STATFAIL"))
    return sorted(out)


def build_variant(content, out_path, tmp):
    """把指定内容的 mcloud_setup.cs 编成控制台版包装器。

    用 build_setup_exe.py 的 --source 入口，**不碰工作树里被跟踪的那份**：
    早期写法是"备份→覆盖→编译→还原"，finally 能兜住异常但兜不住硬中断，
    会把仓库留在变体内容上（本仓判据的一贯要求：Red 验证不得改写已跟踪文件）。
    """
    cs = os.path.join(tmp, "mcloud_setup_variant.cs")
    with io.open(cs, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)
    r = subprocess.run([sys.executable, os.path.join(REPO, "win_scripts", "build_setup_exe.py"),
                        "--console", "--source", cs, "--out", out_path], capture_output=True)
    if r.returncode != 0 or not os.path.isfile(out_path):
        raise SystemExit("编译变体失败：%s%s" % (show(r.stdout), show(r.stderr)))
    return out_path


def run_pair(exe, stub, tmp, tag):
    """启动两个实例（第二个在第一个的临界区内启动），返回 (rc1, rc2, out2)。"""
    p1 = subprocess.Popen([exe, "--quiet", "--no-launch", "--user-level", "--package", stub],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(2.0)                       # 确保第一个已进入临界区
    r2 = subprocess.run([exe, "--quiet", "--no-launch", "--user-level", "--package", stub],
                        capture_output=True, timeout=300)
    try:
        p1.wait(timeout=180)
    except subprocess.TimeoutExpired:
        p1.kill()
        p1.wait(timeout=30)
    out1 = p1.stdout.read()
    print("  %s：第一个 rc=%s，第二个 rc=%s" % (tag, p1.returncode, r2.returncode))
    return p1.returncode, r2.returncode, r2.stdout, out1


def main():
    # 前门：有任何本产品实例在跑就拒绝执行（包装器会按安装路径优雅关闭它们）
    pre = ps_instance_ids()
    if pre:
        print("REFUSED: 机器上有 %d 个本产品实例正在运行（PID %s…）。本判据会触发包装器的" 
              "「关闭正在运行的实例」流程，先把它们退出再跑。"
              % (len(pre), pre[:5]))
        return 2
    if not os.path.isfile(os.path.join(REPO, SRC_REL)):
        print("REFUSED: 找不到 %s" % SRC_REL)
        return 2

    tmp = tempfile.mkdtemp(prefix="mcloud-mutex-test-")
    fails = []
    notes = []
    try:
        # stub（假安装包：睡 6 秒）
        stub_cs = os.path.join(tmp, "sleep_stub.cs")
        with io.open(stub_cs, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(STUB_CS)
        csc = None
        for pat in BSE.ROSLYN_GLOBS:
            hits = sorted(glob.glob(pat))
            if hits:
                csc = hits[0]
                break
        if not csc:
            print("REFUSED: 找不到 Roslyn csc（旧 csc 不可复现，见 D130）")
            return 2
        stub = os.path.join(tmp, "sleep_stub.exe")
        r = subprocess.run([csc, "/nologo", "/deterministic+", "/target:exe",
                            "/out:" + stub, stub_cs], capture_output=True)
        if r.returncode != 0 or not os.path.isfile(stub):
            print("REFUSED: 假安装包编译失败：%s" % show(r.stderr))
            return 2

        fp_before = {"sys": listing(SYSTEM_APPDIR), "user": listing(USER_APPDIR)}

        # Green：当前工作树（含 D132 互斥实现）
        with io.open(os.path.join(REPO, SRC_REL), encoding="utf-8") as gf:
            green_src = gf.read()
        green = build_variant(green_src, os.path.join(tmp, "wrap_green.exe"), tmp)
        rc1, rc2, out2, out1 = run_pair(green, stub, tmp, "Green（工作树：有互斥）")
        if rc2 != 2:
            fails.append("Green：第二个实例 rc=%s（期望 2）—— 互斥没生效" % rc2)
        if not has(out2, "另一个 MCloud 安装包装器正在运行"):
            fails.append("Green：第二个实例没有给出互斥提示")
        if rc1 not in (0, 1):
            fails.append("Green：第一个实例 rc=%s（期望 0/1，它应当跑完）" % rc1)

        # Red：HEAD（改动前，无互斥）—— 必须**不被挡住**，否则 Green 的证明力为零
        head_src = subprocess.run(["git", "-C", REPO, "show", "HEAD:%s" % SRC_REL],
                                  capture_output=True).stdout.decode("utf-8", "replace")
        if "_singleInstance" in head_src:
            print("NOTE: HEAD 已包含互斥实现（本判据的 Red 分支在互斥落地后自动失效，"
                  "改判为跳过；此时 A' 的证明力由 installer_arg_test.py 的分支承担）")
            notes.append("Red 跳过（HEAD 已修）")
        else:
            red = build_variant(head_src, os.path.join(tmp, "wrap_red.exe"), tmp)
            rrc1, rrc2, rout2, rout1 = run_pair(red, stub, tmp, "Red（HEAD：无互斥）")
            if rrc2 == 2 and has(rout2, "另一个 MCloud 安装包装器正在运行"):
                fails.append("Red：HEAD 版本也被挡住了 ⇒ 挡住的不是这段改动，判据不成立")
            else:
                print("  Red 复现：HEAD 的第二个实例 rc=%s（未被互斥挡住）⇒ Green 的通过有意义" % rrc2)

        # 污染自检
        fp_after = {"sys": listing(SYSTEM_APPDIR), "user": listing(USER_APPDIR)}
        for key, label in (("sys", "系统级安装目录"), ("user", "用户级安装目录")):
            if fp_before[key] != fp_after[key]:
                diff = set(fp_after[key]) ^ set(fp_before[key])
                det = ["%s 前=%s 后=%s" % (d[0], d[1], d[2]) for d in sorted(diff)][:6]
                fails.append("污染.%s 目录指纹变化（%d 项）：%s" % (label, len(diff), "; ".join(det)))
        post = ps_instance_ids()
        if post:
            fails.append("污染.进程 判据结束时仍有本产品实例：PID %s" % post[:5])

        # 自己的临时目录必须删干净（第一版就是漏了这条被本轮审计抓到）
        leftovers_before = glob.glob(os.path.join(tempfile.gettempdir(), "MCloudSetup-*"))
        print("  残留 MCloudSetup-* 目录：%d" % len(leftovers_before))
        if leftovers_before:
            fails.append("污染.临时目录 留下 %s" % leftovers_before[:3])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(tmp):
            fails.append("污染.自己的临时目录 未能删除：%s" % tmp)

    print("\n明细：%d 条不成立" % len(fails))
    for f in fails:
        print("  [FAIL] " + f)
    for n in notes:
        print("  [NOTE] " + n)
    if fails:
        print("VERDICT: FAIL")
        return 1
    print("VERDICT: PASS（并发第二个实例被互斥体挡住并 rc=2；HEAD 版本不挡住；未污染任何安装位置）")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
