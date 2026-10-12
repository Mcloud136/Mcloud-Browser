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
    ap.add_argument("--embed", default=None,
                    help="要内嵌进 EXE 的 mini_installer 路径（发布用）")
    ap.add_argument("--console", action="store_true", help="编译成控制台程序（测试用）")
    ap.add_argument("--version", default=None,
                    help="写入文件版本元数据的 4 段版本号（如 155.0.8059.40）。"
                         "不给则 csc 默认 0.0.0.0 —— 用户在属性对话框/审计工具里看不到版本，"
                         "第6轮曾试图用 /version: 实现，那是错的（见下）")
    ap.add_argument("--allow-nondeterministic", action="store_true",
                    help="明知产物不可复现仍继续（仅供本机排错，发布路径禁止使用）")
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
    # 缺陷 D130：这里曾经"退回旧 csc 并继续"，于是发布脚本照样写 .sha256、照样出发布说明，
    # 而那份哈希每次重编都会变——同一份源码两次编译实测 c4c5da27… vs 2025fcdd…，
    # 用 Roslyn /deterministic+ 跨目录同名两次一致 2e25c93e…。发布物的 SHA 一旦不可复现，
    # "核对哈希"这条验收就整个作废，而它在日志里只表现为一句可以被划过去的提示。
    # 所以不可复现必须让构建失败，而不是让下游拿到一个每次都不一样的期望值。
    if not deterministic and not args.allow_nondeterministic:
        fail("找不到支持 /deterministic 的 Roslyn csc，旧 csc 编出的 EXE 每次 SHA 都不同（缺陷 D130）。"
             "\n  根因：发布流程随后会写 %s.sha256 与发布说明里的预期值，不可复现的哈希等于没有验收。"
             "\n  修法一（推荐）：安装 VS BuildTools（本机为 Microsoft Visual Studio/18/BuildTools），"
             "使 MSBuild\\Current\\Bin\\Roslyn\\csc.exe 存在。"
             "\n  修法二：仅在本机排错时使用，显式加 --allow-nondeterministic（发布路径禁止）。", 113)
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
    extra_src = None
    if args.version:
        parts = args.version.split(".")
        if len(parts) != 4 or not all(p.isdigit() for p in parts):
            fail("--version 需要 4 段数字版本号（如 155.0.8059.40），收到 %r；"
                 "AssemblyVersion 不接受其它形式" % args.version)
        # ⚠ csc **没有**"设置程序集版本"的开关：`/version`（不带冒号）是"打印编译器版本并退出"。
        # 第6轮曾写成 `/version:155.0.8059.40`，csc 返回 0 却**根本不产出文件**（缺陷 D164），
        # 而当时的调用方只看 returncode，于是流水线在"没有产物"这一步才以另一种形式暴露。
        # 正确做法：生成一个 AssemblyInfo 源文件与主源码同批编译。
        # 放固定路径（installer/out/ 已 gitignore）而不是 mkstemp 的随机名 ——
        # 排除"源文件路径进元数据"这类可能的不可复现来源。
        extra_src = os.path.join(OUTDIR, "mcloud_setup_assemblyinfo.cs")
        with open(extra_src, "w", encoding="utf-8", newline="\r\n") as f:
            f.write('[assembly: System.Reflection.AssemblyVersion("%s")]\n'
                    '[assembly: System.Reflection.AssemblyFileVersion("%s")]\n'
                    '[assembly: System.Reflection.AssemblyInformationalVersion("%s")]\n'
                    % (args.version, args.version, args.version))
        cmd.append(extra_src)
    cmd.append(SRC)

    print("编译：%s" % (" ".join(cmd[:6]) + " ... " + os.path.basename(SRC)))
    # csc 按系统 ANSI 代码页（本机 cp936）输出中文，用 text=True 的默认编码解码；
    # errors="replace" 保证万一有奇数字节也只是显示乱码，不会像首版那样直接抛
    # UnicodeDecodeError 把编译结果一起吞掉（'stdout' 变 None 后 AttributeError）。
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    finally:
        if extra_src and os.path.isfile(extra_src):
            os.unlink(extra_src)
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
