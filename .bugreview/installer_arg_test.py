#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D121 / D129 的**参数级**验收：包装器到底给 mini_installer 传了什么参数。

为什么不是交接文档建议的「给 setup_wrapper_test.py 补一条不带 --system-level 的用例」：
  那条路径会真的往 %LOCALAPPDATA%\\Chromium\\Application 装一份浏览器。而注册表
  HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences 里恰好有一条指向该路径的
  GpuPreference=1（1=省电=优先**核显**，缺陷 D154；本判据运行时实测该条目仍在），
  于是测试会把这台机器上的用户级安装钉在 Intel 核显上——而核显正是 D3D12 绿屏那一侧，
  与所有既有 GPU 基准不可比；收尾的卸载本身又是一次真实安装变更。
  按 D99 纪律（测试不得污染被测目标）改成录参数：**D121 的缺陷面只是「传给
  mini_installer 的参数」**，用一个假安装包（stub）把收到的 argv 落到文件里，
  就能在不碰任何安装位置的前提下**真正执行到**那条从未被执行过的分支。

用例：
  A  用户级 Green  HEAD 源码 + --user-level   → stub 必须收到**空参数**
  A' 用户级 Red    68838c1 源码（硬编码那版）→ stub 必须收到 --system-level
                   （A' 成立才证明 A 有区分力，而不是「两边都恰好通过」）
  B  D129 参与判定 stub 以 MCLOUD_STUB_RC=3 退出 → 日志必须出现「安装器自身返回 3」且 rc=1
  C  系统级        stub 必须收到 --system-level。仅在「已提权 且 系统级目录下没有正在运行的
                   本产品实例」时才执行——否则它会先 WM_CLOSE 掉用户正在用的浏览器（D52/D55
                   纪律：不得机器级清理、不得扰动被测目标）。跳过时整体判 PARTIAL，
                   **不允许用「两半通过」冒充全绿**。

退出码：0=可执行用例全部成立且 C 已执行 / 1=有断言不成立 / 2=环境不满足（C 未能执行）
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(THOR, "win_scripts"))
import build_setup_exe as BSE  # noqa: E402  复用编译器发现逻辑，避免与打包路径漂移（D130 同族）

PREFIX_REV = "68838c1"          # D121 修复前的那一版（第 613 行硬编码 --system-level）
WANT_VERSION = "155.0.8059.40"  # 只用来让包装器读得出「目标版本号」，不涉及真实安装
USER_APPDIR = os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application")
SYSTEM_APPDIR = r"C:\Program Files\Chromium\Application"

# 注意：这里一律**不**传 errors=。CPython 的 subprocess 里 encoding/errors 会隐式打开文本模式，
# 传了就把 stdout 变成 str，后面的 .decode() 直接 AttributeError —— 判据自己炸掉不算红，
# 但它会让真实结论读不到（同 test_build_win_preflight.py 在 -X utf8 下假红的那族脆弱性）。
STUB_CS = r'''
using System;
using System.IO;
[assembly: System.Reflection.AssemblyVersion("%V%")]
[assembly: System.Reflection.AssemblyFileVersion("%V%")]
[assembly: System.Reflection.AssemblyInformationalVersion("%V%")]
internal static class McloudArgStub {
    // 冒充 mini_installer：只把「收到了什么参数」录进文件，不做任何安装动作。
    // 退出码由 MCLOUD_STUB_RC 控制，用来证明包装器会让安装器自身的返回码参与判定（D129）。
    private static int Main(string[] argv) {
        string log = Environment.GetEnvironmentVariable("MCLOUD_STUB_LOG");
        if (!string.IsNullOrEmpty(log)) {
            try {
                File.AppendAllText(log, (argv.Length == 0 ? "(no-args)" : string.Join("|", argv))
                                        + Environment.NewLine);
            } catch (Exception) { }
        }
        int code = 0;
        string rc = Environment.GetEnvironmentVariable("MCLOUD_STUB_RC");
        if (rc != null) { int.TryParse(rc, out code); }
        return code;
    }
}
'''.replace("%V%", WANT_VERSION).lstrip()

RUNNING_PS = r'''
$sys = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
         Where-Object { $_.ExecutablePath -like ($env:T_SYS + '\*') })
$user = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
          Where-Object { $_.ExecutablePath -like ($env:T_USER + '\*') })
Write-Output ("SYS=" + $sys.Count + " USER=" + $user.Count)
'''


def find_csc():
    for pat in BSE.ROSLYN_GLOBS:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    if os.path.isfile(BSE.LEGACY_CSC):
        return BSE.LEGACY_CSC
    raise SystemExit("找不到 csc.exe（既无 VS Roslyn 也无 %s）" % BSE.LEGACY_CSC)


def compile_cs(csc, cs_path, out_path):
    """与 win_scripts/build_setup_exe.py 同参数集，只是源文件可指到临时副本。"""
    cmd = [csc, "/nologo", "/optimize+", "/warnaserror-", "/target:exe", "/out:" + out_path]
    cmd += ["/reference:" + r for r in BSE.REFS]
    cmd.append(cs_path)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not os.path.isfile(out_path):
        raise SystemExit("编译失败：%s\n%s" % (cs_path, show(r.stdout) + show(r.stderr)))


def show(raw):
    return (raw or b"").decode("gbk", "replace").replace("\r\n", "\n")


def has(raw_bytes, needle):
    """包装器是中文输出的 .NET 控制台程序，控制台代码页随环境变（cp936 / utf-8 都出现过）。
    判据不依赖解码：对同一句中文，两种编码都试一遍。"""
    return any(needle.encode(enc) in raw_bytes for enc in ("utf-8", "gbk"))


def listing(root):
    """目录指纹（相对路径 + 大小 + mtime）。用来断言测试没往真实安装位置写东西。"""
    out = set()
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root)
            try:
                st = os.stat(p)
                out.add((rel, st.st_size, int(st.st_mtime)))
            except OSError:
                out.add((rel, -1, -1))
    return out


def running_counts(cwd, ps_path):
    env = dict(os.environ, T_SYS=SYSTEM_APPDIR, T_USER=USER_APPDIR)
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", ps_path], capture_output=True, env=env)
    if r.returncode != 0:
        # 取不到数据一律非 0 退出，不得当成「0 个实例，安全」
        raise SystemExit("实例计数失败：" + show(r.stderr))
    lines = [x for x in show(r.stdout).splitlines() if x.startswith("SYS=")]
    if not lines:
        raise SystemExit("实例计数无输出，判 FAIL")
    m = re.match(r"SYS=(\d+) USER=(\d+)", lines[0])
    if not m:
        raise SystemExit("实例计数输出无法解析：" + lines[0])
    return int(m.group(1)), int(m.group(2))


def snapshot(cwd, ps_path):
    return {
        "user": listing(USER_APPDIR),
        "sys": listing(SYSTEM_APPDIR),
        "counts": running_counts(cwd, ps_path),
        "tempsets": set(d for d in os.listdir(tempfile.gettempdir())
                        if d.startswith("MCloudSetup-")),
    }


def run_case(exe, level_args, stub, log_path, stub_rc):
    env = dict(os.environ, MCLOUD_STUB_LOG=log_path, MCLOUD_STUB_RC=str(stub_rc))
    r = subprocess.run([exe, "--quiet", "--no-launch"] + level_args + ["--package", stub],
                       capture_output=True, env=env, timeout=300)
    got = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [x.strip() for x in f if x.strip()]
        got = lines[-1] if lines else ""
    return r.returncode, r.stdout, got


class Verdict:
    def __init__(self):
        self.rows, self.failed, self.skipped = [], [], []

    def check(self, name, desc, ok, detail=""):
        self.rows.append((name, desc, ok, detail))
        print("   %-5s %s %s" % ("[ok]" if ok else "[!!]", name,
                                 desc if ok else desc + "   <- " + str(detail)))
        if not ok:
            self.failed.append(name)

    def skip(self, name, why):
        self.skipped.append(name)
        print("   SKIP  %s  %s" % (name, why))


def main():
    cwd = os.getcwd()
    csc = find_csc()
    tmp = tempfile.mkdtemp(prefix="mcloud-installer-argtest-")
    v = Verdict()
    try:
        ps_path = os.path.join(tmp, "count_running.ps1")
        with open(ps_path, "w", encoding="ascii", newline="\r\n") as f:
            f.write(RUNNING_PS)

        before = snapshot(cwd, ps_path)
        admin = is_admin()
        print("环境：提权=%s 系统级实例=%d 用户级实例=%d"
              % ({True: "是", False: "否", None: "未知"}[admin],
                 before["counts"][0], before["counts"][1]))

        stub_cs = os.path.join(tmp, "stub.cs")
        with open(stub_cs, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(STUB_CS)
        stub = os.path.join(tmp, "mcloud_arg_stub.exe")
        compile_cs(csc, stub_cs, stub)

        # HEAD：走真实打包脚本编译（顺带证明发布管线能编译当前源码）
        head = os.path.join(tmp, "MCloud-Setup-head.exe")
        r = subprocess.run([sys.executable, os.path.join(THOR, "win_scripts", "build_setup_exe.py"),
                            "--console", "--out", head], capture_output=True)
        if r.returncode != 0 or not os.path.isfile(head):
            print(show(r.stdout), show(r.stderr))
            raise SystemExit("build_setup_exe.py 编译 HEAD 失败")

        # Red 参照：逐字从 git 取修复前的源码，不改动任何已跟踪文件
        old = subprocess.run(["git", "-C", THOR, "show", "%s:installer/mcloud_setup.cs" % PREFIX_REV],
                             capture_output=True)
        if old.returncode != 0:
            raise SystemExit("git show %s 失败，无法构造 Red 参照：%s" % (PREFIX_REV, show(old.stderr)))
        pre_cs = os.path.join(tmp, "mcloud_setup_pre.cs")
        with open(pre_cs, "wb") as f:
            f.write(old.stdout)
        pre = os.path.join(tmp, "MCloud-Setup-pre.exe")
        compile_cs(csc, pre_cs, pre)

        print("\n== A 用户级（Green，HEAD 源码）：期望 stub 收到空参数 ==")
        rc, out, got = run_case(head, ["--user-level"], stub, os.path.join(tmp, "A.log"), 0)
        v.check("A", "stub 收到的参数为空（而不是 --system-level）",
                got in ("", "(no-args)"), "实际收到：" + got)
        v.check("A.rc", "包装器 rc 非 0（用户目录本来没装东西，复验必须判不过）",
                rc != 0, "rc=%d" % rc)

        print("== A' 用户级（Red，%s 硬编码那版）：期望 stub 收到 --system-level ==" % PREFIX_REV)
        rc2, out2, got2 = run_case(pre, ["--user-level"], stub, os.path.join(tmp, "Apre.log"), 0)
        v.check("A.red", "旧代码确实传了 --system-level —— 没有这条，A 的通过毫无意义",
                "--system-level" in got2, "实际收到：" + (got2 or "(空)"))

        print("== B D129：stub 返回 3 时必须参与判定 ==")
        rc3, out3, got3 = run_case(head, ["--user-level"], stub, os.path.join(tmp, "B.log"), 3)
        v.check("B.arg", "参数仍为空（B 只改返回码，不能顺带改参数）",
                got3 in ("", "(no-args)"), "实际收到：" + got3)
        v.check("B.note", "日志出现「安装器自身返回 3」", has(out3, "安装器自身返回 3"),
                "日志片段：" + show(out3)[:200])
        v.check("B.rc", "rc==1（安装器失败不得被判成「已确认更新」）", rc3 == 1, "rc=%d" % rc3)

        print("== C 系统级：期望 stub 收到 --system-level ==")
        if admin is not True:
            v.skip("C", "当前不是管理员或无法判定提权状态，会走 RelaunchElevated 自举分支（弹 UAC），"
                        "不适合无人值守判据。以管理员身份重跑可补齐。")
        elif before["counts"][0] != 0:
            v.skip("C", "%s 下有 %d 个本产品实例正在运行，执行会先 WM_CLOSE 掉它们。"
                   "把浏览器全部退出后重跑本判据，补齐 D121 的另一半。"
                   % (SYSTEM_APPDIR, before["counts"][0]))
        else:
            rc4, out4, got4 = run_case(head, ["--system-level"], stub, os.path.join(tmp, "C.log"), 0)
            v.check("C", "stub 收到的参数含 --system-level",
                    "--system-level" in got4, "实际收到：" + (got4 or "(空)"))
            v.check("C.rc", "系统级分支跑完 rc==0（stub 返回 0 且真实安装目录复验通过）",
                    rc4 == 0, "rc=%d 日志片段：%s" % (rc4, show(out4)[:160]))

        after = snapshot(cwd, ps_path)
        for key, label in (("user", "用户级安装目录"), ("sys", "系统级安装目录")):
            diff = after[key] ^ before[key]
            if diff:
                # 明细必须打印**变化的字段**，只打印名字等于没诊断（实测：一次 FAIL 只显示
                # 两条同名条目，看不出是 size 还是 mtime 变了，只能靠猜）
                det = []
                for rel in sorted(set(x[0] for x in diff)):
                    b = [x for x in before[key] if x[0] == rel]
                    a = [x for x in after[key] if x[0] == rel]
                    det.append("%s: 前=%s 后=%s" % (rel, b[0][1:] if b else "无",
                                                    a[0][1:] if a else "无"))
            else:
                det = []
            v.check("污染." + label, "测试前后目录指纹逐项一致（未写入/删除任何文件）",
                    not diff, "；".join(det[:4]))
        v.check("污染.进程", "本产品实例数量前后不变（没有关闭用户正在用的浏览器）",
                before["counts"] == after["counts"], "前=%s 后=%s" % (before["counts"], after["counts"]))
        newtmp = sorted(after["tempsets"] - before["tempsets"])
        v.check("污染.临时目录", "没有留下未清理的 MCloudSetup-* 目录", not newtmp,
                "新增：" + ", ".join(newtmp[:3]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n== 明细：%d 条断言，%d 条不成立，%d 组跳过 ==" % (len(v.rows), len(v.failed), len(v.skipped)))
    for name, desc, ok, _ in v.rows:
        print("  [%s] %-10s %s" % ("PASS" if ok else "FAIL", name, desc))
    if v.failed:
        print("VERDICT: FAIL（" + ", ".join(v.failed) + "）")
        return 1
    if v.skipped:
        print("VERDICT: PARTIAL — 环境不满足，系统级分支（D121 的另一半）未能执行；"
              "不允许用「两半通过」冒充全绿")
        return 2
    print("VERDICT: PASS（用户级与系统级参数分支都被真实执行、D129 判定分支被触发、未污染任何安装位置）")
    return 0


def is_admin():
    """True / False / None（取不到就是 None，交给「环境不满足」分支，不当成「非管理员」）。"""
    try:
        from ctypes import windll
        return bool(windll.shell32.IsUserAnAdmin())
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
