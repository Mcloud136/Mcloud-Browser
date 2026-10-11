#!/usr/bin/env python3
"""flag_runtime_state.py - 用子进程命令行做 flags 的**运行时生效**核对（比静态声明位更强的证据）。

机制依据（M155 源码实证）：
  base/metrics/field_trial.cc:690 `PopulateLaunchOptionsWithFieldTrialState()`
    // Append --enable-features and --disable-features switches corresponding
    // to the features enabled on the command-line, so that child and browser
    // process command lines match and clearly show what has been specified
    // explicitly by the user.
    FeatureList::GetInstance()->GetCommandLineFeatureOverrides(&en, &dis);
  → 浏览器把**已注册的命令行 override** 序列化进子进程命令行。因此从 Win32_Process 的
    CommandLine 里解析 `--enable-features=` / `--disable-features=`，就能拿到加载器注入
    之后**真正被 FeatureList 接受**的条目集合（操作系统命令行看不到进程内追加的开关，
    但子进程是浏览器用改过的 CommandLine 启动的，所以可见）。

本脚本回答三件事：
  1) 清单里声明要启用的 feature，有哪些没有进入运行时 override；
  2) 运行时 override 里有哪些不是我们清单带来的（= 上游侧命令行 override）；
  3) 控制实验：故意注入一个不存在的名字，看它会不会出现在 override 列表里——
     决定这套 oracle 的严格性（"只收真实 feature" 还是 "原样回显"）。

⚠ 集合语义（2026-10-10 读源码修正，见缺陷档案 D51）：回显来自
   `GetFeatureOverridesImpl(command_line_only=true)`，它会**跳过带 field_trial 的 override**
   （`base/feature_list.cc:1453-1456`）。因此"回显里没有"有两种可能：
     a) 该条走了 trial 通道（写 params 的条目必然如此：`ParseEnableFeatureString()` 会合成
        Study<Name>/Group<Name>）→ **仍然启用**，只是不在此集合；
     b) 该条根本没进命令行（语法被整串拒绝 / D39-D40 字节预算整块跳过）。
   本脚本无法区分 a/b，只能给出"需要进一步确认"的名单；判定 a/b 请用
   `--control` 对照（不存在的裸名会被回显 → 说明回显是原样回显型，未知名也收）。

用法：
  python .bugreview/flag_runtime_state.py [--chrome <exe>] [--control]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

THOR = r"d:\wxmuma\thorium"
DEFAULT_CHROME = r"D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe"
PS = "powershell.exe"


def ps(cmd):
    p = subprocess.run([PS, "-NoProfile", "-Command", cmd], capture_output=True,
                       text=True, errors="replace")
    return p.stdout or ""


def active_entries(text):
    """清单里的活动条目 → (enabled{name: params}, disabled{set}, plain{set})。"""
    en, dis, plain = {}, {}, set()
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"--(enable|disable)-features=(.+)$", s)
        if m:
            for part in m.group(2).split(","):
                name = part.split(":")[0].strip()
                params = part.split(":", 1)[1] if ":" in part else ""
                if not name:
                    continue
                (en if m.group(1) == "enable" else dis)[name] = params if m.group(1) == "enable" else None
        elif s.startswith("--"):
            plain.add(s[2:].split("=")[0])
    return en, dis, plain


def _instance_pids(prof):
    """只返回本次 profile 对应的 chrome 进程 PID（缺陷 D106 的修法核心）。"""
    key = os.path.basename(prof)
    out = []
    for line in ps(
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" } | Out-String"
    ).splitlines():
        pid, _, cmd = line.partition("\t")
        if key and key in cmd and pid.strip().isdigit():
            out.append(int(pid.strip()))
    return out


def propagate_probe(exe, wait=16):
    """启动一次带窗口 chrome，抓所有子进程命令行，返回 (合并后的 enable 集合, disable 集合, 原始行)。"""
    prof = tempfile.mkdtemp(prefix="frs_")
    proc = subprocess.Popen([exe, "--user-data-dir=" + prof, "--no-first-run",
                             "--no-default-browser-check", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(wait)
    lines = [l for l in ps(
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        "ForEach-Object { $_.CommandLine } | Out-String").splitlines() if l.strip()]
    # ⚠ 缺陷 D106（2026-10-11 自查发现，Critical 级工具缺陷）：这里原本是
    #   `Get-Process chrome | Stop-Process -Force`——**机器级**杀进程，会把用户自己
    #   开着的浏览器（含未保存标签）一起干掉。这与 D52/D55 早已确立的纪律直接冲突，
    #   而且本文件是唯一没被改过来的那个（其它探针都按实例指纹清理了）。
    #   现在按本次 profile 的叶子名筛 PID，循环清理到干净；残留即报错，不再假装成功。
    for _ in range(6):
        pids = _instance_pids(prof)
        if not pids:
            break
        arg = ",".join(str(x) for x in pids)
        ps("Get-Process -Id @(%s) -ErrorAction SilentlyContinue | Stop-Process -Force" % arg)
        time.sleep(1.5)
    try:
        proc.wait(timeout=30)
    except Exception:                       # noqa: BLE001
        proc.kill()
    leftover = _instance_pids(prof)
    shutil.rmtree(prof, ignore_errors=True)
    if leftover:
        raise SystemExit("FAIL: 本工具启动的实例仍有 %d 个进程残留（PID=%s）；"
                         "继续跑会锁住构建目录（D71 同族）" % (len(leftover), leftover))

    en, dis, plain = set(), set(), set()
    for l in lines:
        for m in re.finditer(r"--(enable|disable)-features=([^\"]+?)(?= --|\s--|$)", l):
            for part in m.group(2).split(","):
                name = part.split(":")[0].strip()
                if not name:
                    continue
                (en if m.group(1) == "enable" else dis).add(name)
        for tok in l.split():
            if tok.startswith("--"):
                plain.add(tok[2:].split("=")[0].strip('"'))
    return en, dis, plain, lines


def _newest_payload_dir(d):
    """exe 同级里"带 chrome.dll 且目录名是四段版本号"的最新一个（安装版布局）。"""
    best = None
    best_ver = None
    if not os.path.isdir(d):
        return None
    for name in os.listdir(d):
        sub = os.path.join(d, name)
        if not (os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "chrome.dll"))):
            continue
        parts = name.split(".")
        if len(parts) != 4 or not all(x.isdigit() for x in parts):
            continue
        ver = tuple(int(x) for x in parts)
        if best_ver is None or ver > best_ver:
            best_ver, best = ver, sub
    return best


def flags_candidates(exe):
    """加载器 v8 的**完整**读取顺序（缺陷 D109）。

    v8 以 base::DIR_MODULE（= chrome.dll 所在目录）为第一候选，与上游
    `main_dll_loader_win.cc:175-191 GetModulePath` 同口径。Python 侧拿不到
    DIR_MODULE，但可以等价地判断：exe 同目录有 chrome.dll → 扁平布局（开发树/便携包），
    没有 → 安装版布局，程序目录是版本目录。
    把整条候选链都暴露出来，是为了让"存在多份且内容不同"这种压制场景**看得见**——
    v7 时代 oracle 与加载器同序且只看第一个，根目录残留能把正式文件压掉而门禁全绿。

    已知边界（刻意不处理）：升级中途若根 chrome.exe 比"最新版本目录"旧，二进制读的是自己
    编译期写死的那个版本目录（`chrome::kChromeVersion`），而这里只能挑"最新的载荷目录"，
    两者会差一版。这种混版状态本身是瞬时的，且候选链会**整条打印 + 各带 sha256**，
    人眼能立刻看出读的是哪一份；为它去调 PowerShell 取 ProductVersion 不值。
    """
    d = os.path.dirname(os.path.abspath(exe))
    payload = _newest_payload_dir(d)
    module_dir = d if os.path.isfile(os.path.join(d, "chrome.dll")) else (payload or d)
    dirs = [module_dir, d]
    if payload and payload not in dirs:
        dirs.append(payload)
    seen, out = set(), []
    for x in dirs:
        p = os.path.normpath(os.path.join(x, "mcloud_flags.txt"))
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_flags_path(exe):
    """返回加载器实际会读到的那份（候选链上第一个存在的）。"""
    for cand in flags_candidates(exe):
        if os.path.isfile(cand):
            return cand
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=DEFAULT_CHROME)
    ap.add_argument("--control", action="store_true", help="附带不存在名字的对照实验")
    ap.add_argument("--allow-drift", action="store_true", help="允许构建目录与仓库正文不一致（仅用于看差异）")
    args = ap.parse_args()

    exe = args.chrome
    flags_path = resolve_flags_path(exe)
    repo_flags = os.path.join(THOR, "mcloud_flags.txt")
    if not flags_path:
        # 注意：文案里有 %(VersionDir)s 这种字面量，不能用 % 格式化（会被当成命名占位符）。
        raise SystemExit(
            "找不到 mcloud_flags.txt（既不在 " + os.path.dirname(os.path.abspath(exe)) +
            " 也不在其版本子目录）。\n"
            "  开发树应在 exe 同目录；安装版应在 Application\\<版本号>\\ 下"
            "（D105 之后由 chrome.release 的 %(VersionDir)s 条目投递，加载器 v8 同址回退）。")
    # D109：把整条候选链摊开。存在多份且内容不同时，加载器只会读第一份——
    # 过去 oracle 与加载器同序且只看第一份，所以"根目录残留压制正式文件"这件事
    # 在门禁里是完全隐形的。现在至少让人看得见是谁压住了谁。
    present = [c for c in flags_candidates(exe) if os.path.isfile(c)]
    if len(present) > 1:
        import hashlib
        print("  候选链（加载器按此顺序读取，第一个命中即生效）：")
        for c in present:
            digest = hashlib.sha256(open(c, "rb").read()).hexdigest()[:12]
            print("    %s  sha256=%s  %s"
                  % (c, digest, "<= 实际生效" if c == present[0] else "<= 被压制"))
        if len({open(c, "rb").read() for c in present}) > 1:
            print("  WARN: 多份候选内容不一致（D109）——请删掉被压制之外的那份，"
                  "否则这份文件改名/删除的瞬间行为就会变。")
    raw_flags = open(flags_path, "rb").read()
    try:
        base_text = raw_flags.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # 缺陷 D99/D100：构建目录的 flags 文件曾被中断的 loader 边界测试留成垃圾语料
        # （首字节 0xD6，非 UTF-8）。旧实现在这里抛裸 traceback，看不出"产物目录被污染"
        # 这个真实原因。现在给出可执行的修复指引。
        raise SystemExit(
            "FAIL: %s 不是合法 UTF-8（%s）。这几乎一定是 loader 边界测试被中断后留下的"
            "测试语料——恢复方法：copy %s 过去（或重跑 deploy_mcloud.py），"
            "并把测试指向硬链接沙箱而不是构建目录。"
            % (flags_path, exc, os.path.join(THOR, "mcloud_flags.txt"))) from exc
    repo_text = open(repo_flags, "rb").read().decode("utf-8-sig")
    same = "与仓库一致" if base_text == repo_text else "与仓库不一致(!)"
    if base_text != repo_text and not args.allow_drift:
        raise SystemExit(
            "FAIL: 构建目录 flags 与仓库正文不一致（%d B vs %d B）。"
            "在这种状态下任何运行时结论都不属于发布配置；"
            "先恢复（重跑 deploy_mcloud.py 或 copy 仓库文件），确认要看差异才加 --allow-drift。"
            % (len(raw_flags), len(open(repo_flags, "rb").read())))

    want_en, want_dis, want_plain = active_entries(base_text)
    print("构建目录 flags = %s（%d 行活动条目 / %d 项 feature / %d 项普通开关）[%s]"
          % (flags_path, len(base_text.splitlines()), len(want_en) + len(want_dis),
             len(want_plain), same))

    en, dis, plain, lines = propagate_probe(exe)
    print("运行时 override：enable %d 项 / disable %d 项；子进程命令行 %d 条"
          % (len(en), len(dis), len(lines)))

    missing = sorted(set(want_en) - en)
    extra = sorted(en - set(want_en))
    print("\n[A] 清单声明启用、但不在 command-line-only 回显中的（%d）"
          "——需按 D51 区分 a/b，不一定是失效：" % len(missing))
    for n in missing:
        print("    - %s%s" % (n, ("  params=%s" % want_en[n]) if want_en[n] else ""))
    print("[B] 运行时 override 中有、但不是我们清单带来的（%d，多为上游默认 trial）：" % len(extra))
    print("    " + (", ".join(extra) if extra else "无"))

    if want_dis:
        print("[C] 清单声明禁用的是非：", {n: ("已禁用" if n in dis else "未生效!") for n in want_dis})
    lost_plain = sorted(want_plain - plain)
    print("[D] 清单里的普通开关未出现在任何进程命令行（%d）: %s"
          % (len(lost_plain), lost_plain or "无"))

    if args.control:
        bogus = "ZZCMCloudNoSuchFeature20261010"
        print("\n[E] 对照实验：注入不存在的 feature 名 %s" % bogus)
        out = subprocess.run([sys.executable, "-c",
                              "import io,sys;p=%r;t=open(p,encoding='utf-8').read();"
                              "open(p,'w',encoding='utf-8',newline='\\n').write(t.rstrip('\\n')+'\\n--enable-features=%s\\n')"
                              % (flags_path, bogus)])
        assert out.returncode == 0
        try:
            en2, _d2, _p2, _l2 = propagate_probe(exe, wait=14)
            print("    不存在的名字是否出现在 override 列表: %s" % (bogus in en2))
            print("    → oracle 判定为：%s"
                  % ("严格（只回显真实注册条目，缺失即静默失效）" if bogus not in en2
                     else "宽松（原样回显命令行，含未知名；缺失才说明条目根本没进命令行）"))
        finally:
            with open(flags_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(base_text)
            print("    已恢复原 flags 文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
