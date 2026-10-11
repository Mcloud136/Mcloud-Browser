#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编译 MCloud-Setup.exe（安装包装器）。

为什么用 csc.exe 而不是 cl/dotnet：
  * `C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe` 是 .NET Framework 自带
    编译器，**每台 Windows 都有**，不需要 SDK、不需要 restore、产物是单个自包含 EXE；
  * 上游 mini_installer 没有任何进度 UI（`ProgressCalculator::Calculate()` 除单元测试外
    无消费者），也没有静默开关，所以界面只能由外层提供；
  * 不选"给 mini_installer 打补丁加 UI"：那会让每次内核 rebase 都要重打安装器补丁，
    而本仓库约定是"改上游一律走 apply_*/inject_* 幂等脚本，且不动安装器"。

用法：
    python3 win_scripts/build_setup_exe.py                 # 只编译逻辑（测试用，不内嵌包）
    python3 win_scripts/build_setup_exe.py --embed <路径>   # 把 mini_installer 内嵌进 EXE（发布用）
    python3 win_scripts/build_setup_exe.py --console        # 产出控制台版（自动化测试可直接读输出）
"""
import argparse
import os
import subprocess
import sys

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(THOR, "installer", "mcloud_setup.cs")
OUTDIR = os.path.join(THOR, "installer", "out")
# 编译器选择：优先 Roslyn（VS BuildTools 自带），回退 .NET Framework 自带的旧 csc。
# 旧 csc（Framework64\v4.0.30319）不支持 /deterministic，用它编出来的 EXE 每次 MVID
# 都不同 ⇒ 同一份源码两次编译 SHA 不一样，发布物哈希就失去意义（实测：源码未变却从
# b0bc7652… 变成 96376b3c…）。所以是否传 /deterministic+ 取决于用的是哪个编译器。
ROSLYN_GLOBS = [
    r"C:\Program Files*\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe",
    r"C:\Program Files*\Microsoft Visual Studio\*\*\MSBuild\*\Bin\Roslyn\csc.exe",
]
LEGACY_CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
REFS = ["System.dll", "System.Core.dll", "System.Drawing.dll", "System.Windows.Forms.dll"]


def fail(msg, code=111):
    print("build_setup_exe: %s" % msg, file=sys.stderr)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", default=None, help="要内嵌进 EXE 的 mini_installer 路径（发布用）")
    ap.add_argument("--console", action="store_true", help="编译成控制台程序（测试用）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.isfile(SRC):
        fail("找不到源文件 %s" % SRC)
    import glob as _glob
    csc = None
    for pat in ROSLYN_GLOBS:
        hits = sorted(_glob.glob(pat))
        if hits:
            csc = hits[0]
            break
    deterministic = csc is not None
    if csc is None and os.path.isfile(LEGACY_CSC):
        csc = LEGACY_CSC
    if csc is None:
        fail("既找不到 VS 的 Roslyn csc，也找不到 %s" % LEGACY_CSC)
    print("编译器：%s（%s）" % (csc, "支持 /deterministic" if deterministic else "旧版，产物不可复现"))
    os.makedirs(OUTDIR, exist_ok=True)
    out = args.out or os.path.join(
        OUTDIR, "MCloud-Setup-console.exe" if args.console else "MCloud-Setup.exe")

    cmd = [csc, "/nologo", "/optimize+", "/warnaserror-",
           "/target:" + ("exe" if args.console else "winexe"),
           "/out:" + out]
    if deterministic:
        cmd.insert(1, "/deterministic+")
    for r in REFS:
        cmd.append("/reference:" + r)
    if args.embed:
        if not os.path.isfile(args.embed):
            fail("--embed 指定的安装包不存在：%s" % args.embed)
        # 逻辑名必须与 C# 里的 PackageResName 一致（按后缀匹配）
        cmd.append("/resource:%s,mcloud_mini_installer.exe" % args.embed)
    cmd.append(SRC)

    print("编译：%s" % (" ".join(cmd[:6]) + " ... " + os.path.basename(SRC)))
    # csc 按系统 ANSI 代码页（本机 cp936）输出中文，用 text=True 的默认编码解码；
    # errors="replace" 保证万一有奇数字节也只是显示乱码，不会像首版那样直接抛
    # UnicodeDecodeError 把编译结果一起吞掉（'stdout' 变 None 后 AttributeError）。
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        fail("csc 退出码 %d\n%s" % (r.returncode, r.stderr.strip()))
    if not os.path.isfile(out):
        fail("csc 报成功但没有产出文件：%s" % out)

    print("OK -> %s  (%s bytes)" % (out, format(os.path.getsize(out), ",")))
    if args.embed:
        print("   内嵌安装包：%s" % os.path.basename(args.embed))
    else:
        print("   未内嵌安装包：运行时需 --package <mini_installer.exe>")
    # 编译器产物是二进制，不入库；提示一下避免误提交
    gi = os.path.join(THOR, ".gitignore")
    if os.path.isfile(gi) and "installer/out/" not in open(gi, encoding="utf-8").read():
        print("NOTE: 记得把 installer/out/ 加进 .gitignore（编译产物不入库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
