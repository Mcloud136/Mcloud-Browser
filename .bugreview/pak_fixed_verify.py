#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pak_src_fixed 修复后的实测判据（第7周期收口轮，D190/D191/D192 的复验）。

为什么不用 .bat：cmd 里 %CC% 指向带空格路径必须整体加引号，未加引号时
cl 根本没被调用，而 .cycle7 目录里留着上一轮的 pak_old.exe/pak_new.exe，
"文件存在即通过"式判据于是把没编译成功报成成功（这正是本仓反复登记的假绿族）。
本脚本用 subprocess 传 argv 数组，并且判据是**本轮产物时间戳**，不复用旧二进制。

退出码：0=全部判据成立；1=有判据不成立；2=环境不满足（编译器缺失）。
"""
import os
import re
import subprocess
import sys
import hashlib
import shutil
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VC = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231"
SDK = r"C:\Program Files (x86)\Windows Kits\10"
SDKVER = "10.0.26100.0"
CL = os.path.join(VC, "bin", "Hostx64", "x64", "cl.exe")
WORK = os.path.join(THOR, ".cycle7", "pakverify")
OLD_SRC = os.path.join(THOR, "pak_src")
NEW_SRC = os.path.join(THOR, "pak_src_fixed", "pak.c")
FIXTURE = os.path.join(THOR, "pak_src_fixed", "t_in")

BASE_FLAGS = ["/nologo", "/W4", "/D_CRT_SECURE_NO_WARNINGS"]
NEW_FLAGS = BASE_FLAGS + ["/std:c11", "/utf-8"]


def env():
    inc = [os.path.join(VC, "include")]
    for sub in ("ucrt", "um", "shared"):
        inc.append(os.path.join(SDK, "Include", SDKVER, sub))
    lib = [os.path.join(VC, "lib", "x64")]
    for sub in ("ucrt", "um"):
        lib.append(os.path.join(SDK, "Lib", SDKVER, sub, "x64"))
    e = dict(os.environ)
    e["INCLUDE"] = ";".join(inc)
    e["LIB"] = ";".join(lib)
    e["PATH"] = os.path.join(VC, "bin", "Hostx64", "x64") + os.pathsep + e["PATH"]
    return e


def run(argv, cwd=None):
    p = subprocess.run(argv, cwd=cwd, env=env(), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("gbk", "replace")


def build(name, flags, sources, objdir, start_ts):
    exe = os.path.join(objdir, name)
    for f in (exe,):
        if os.path.exists(f):
            os.remove(f)
    rc, out = run([CL] + flags + ["/Fo" + objdir + os.sep, "/Fe" + exe] + sources)
    fresh = os.path.exists(exe) and os.path.getmtime(exe) >= start_ts - 1
    if rc != 0 or not fresh:
        print("  [FAIL] build %s rc=%d fresh=%s" % (name, rc, fresh))
        print(out)
        return None
    return exe


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def diff_bytes(a, b):
    """返回 (是否相同, 首个差异偏移, 人话描述)。文件缺失也算"不相同"而不是异常。"""
    for p in (a, b):
        if not os.path.isfile(p):
            return False, None, "缺少产物 %s" % os.path.basename(p)
    da, db = read_bytes(a), read_bytes(b)
    if da == db:
        return True, None, "%d B 完全一致" % len(da)
    n = min(len(da), len(db))
    for i in range(n):
        if da[i] != db[i]:
            return False, i, ("%s=%d B / %s=%d B，首个差异在偏移 %d：0x%02X vs 0x%02X"
                              % (os.path.basename(a), len(da), os.path.basename(b),
                                 len(db), i, da[i], db[i]))
    return False, n, "前 %d 字节相同，长度不同（%d vs %d）" % (n, len(da), len(db))


def listing(d):
    """目录 -> {相对路径: (字节数, sha16)}；目录不存在返回空 dict（由调用方判空）。"""
    out = {}
    if not os.path.isdir(d):
        return out
    for root, _, fs in os.walk(d):
        for fn in fs:
            p = os.path.join(root, fn)
            out[os.path.relpath(p, d).replace("\\", "/")] = (os.path.getsize(p), sha(p))
    return out


def main():
    if not os.path.isfile(CL):
        print("ENV: 找不到 cl.exe：%s" % CL)
        return 2
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    fails = []
    start_ts = time.time()

    print("== [0] 从零编译两个工具（判据用本轮时间戳，不复用 .cycle7 里的旧二进制）==")
    old_c = [os.path.join(OLD_SRC, n) for n in
             ("main.c", "pak_header.c", "pak_file.c", "pak_file_io.c",
              "pak_pack.c", "pak_get_file_type.c")]
    old_exe = build("pak_old.exe", BASE_FLAGS, old_c, WORK, start_ts)
    if old_exe is None:
        print("ENV: 原始 pak_src 编译失败，无法做对照")
        return 2
    new_exe = build("pak_new.exe", NEW_FLAGS, [NEW_SRC], WORK, start_ts)
    if new_exe is None:
        return 1
    print("  [OK] 两个工具均为本轮产物")

    print("== [1] 编码旗标判据：/utf-8 必须让警告行号指向真实代码 ==")
    body = read_bytes(NEW_SRC).decode("utf-8")
    lines = body.split("\n")
    total = len(lines) - (1 if lines and lines[-1] == "" else 0)
    print("  pak.c 物理行数 = %d" % total)
    crt = re.compile(r"\b\w*(?:scanf|printf|strcpy|strncpy|strcat|fopen)\s*\(")

    def warnlist(extra):
        rc, out = run([CL] + ["/nologo", "/W4", "/std:c11"] + extra
                      + ["/c", "/Fo" + WORK + os.sep, NEW_SRC])
        found = re.findall(r"pak\.c\((\d+)\)\s*:\s*warning (C\d+)", out)
        return rc, out, found

    # 1a 发布旗标（与 build_and_test.bat 完全一致）：rc=0 且零警告
    rc, out, w_ship = warnlist(["/utf-8", "/D_CRT_SECURE_NO_WARNINGS"])
    print("  [1a] 发布旗标（/utf-8 + 安全警告宏）：rc=%d，警告 %d 条" % (rc, len(w_ship)))
    if rc != 0 or len(w_ship) != 0:
        fails.append("发布旗标下应零警告且编译成功，实得 rc=%d 警告=%d 条" % (rc, len(w_ship)))

    # 1b 正向对照：去掉 /utf-8 必须出现 C4819（证明这条判据能红）
    rc, out, w_noutf = warnlist(["/D_CRT_SECURE_NO_WARNINGS"])
    c4819 = [x for x in w_noutf if x[1] == "C4819"]
    print("  [1b] 去掉 /utf-8：警告 %d 条，其中 C4819 %d 条（C4819 出现=判据可红）"
          % (len(w_noutf), len(c4819)))
    if not c4819:
        fails.append("去掉 /utf-8 后仍无 C4819：D192 的红测不成立，1a 的绿灯无意义")

    # 1c /utf-8 下去掉安全警告宏：C4996 必须出现，且每条行号指向真的 CRT 调用
    rc, out, w_sec = warnlist(["/utf-8"])
    c4996 = [(int(n), c) for n, c in w_sec if c == "C4996"]
    print("  [1c] /utf-8 且不开安全宏：C4996 %d 条" % len(c4996))
    if not c4996:
        fails.append("未关闭安全宏却零 C4996：判据空转")
    for n, _c in c4996:
        real = 1 <= n <= total and bool(crt.search(lines[n - 1]))
        print("     %s pak.c(%d) -> %s" % ("[OK]  " if real else "[FAIL]",
                                           n, (lines[n - 1].strip()[:72]
                                               if 1 <= n <= total else "<行不存在>")))
        if not real:
            fails.append("/utf-8 下 C4996 行号 %d 没有指向 CRT 调用" % n)

    # 1d 反向对照：无 /utf-8 时同一批 C4996 的行号必须指向错的代码（= D192 的红）
    rc, out, w_plain = warnlist([])
    p4996 = sorted(int(n) for n, c in w_plain if c == "C4996")
    n4996 = sorted(n for n, c in c4996)
    print("  [1d] 无 /utf-8 的 C4996 行号 %s vs 有 /utf-8 的 %s" % (p4996, n4996))
    if p4996 == n4996:
        fails.append("两种编码下行号完全一致：/utf-8 没有改变任何事，1a 的绿灯无意义")
    bad = [n for n in p4996 if not (1 <= n <= total and crt.search(lines[n - 1]))]
    print("     无 /utf-8 时行号指错代码的条数 = %d/%d" % (len(bad), len(p4996)))
    if not bad:
        fails.append("无 /utf-8 的 C4996 行号居然全部指对代码：D192 的红测不成立")


    print("== [2-4] 三组样本的确定性 / 与原始工具字节一致 / 交叉解包 ==")

    def matrix(tag, desc, indir, files, inispec):
        ini_p = os.path.join(indir, "pak_index.ini")
        with open(ini_p, "w", newline="\n") as f:
            f.write(inispec)
        a = os.path.join(WORK, tag + "_a.pak")
        b = os.path.join(WORK, tag + "_b.pak")
        old_pak = os.path.join(WORK, tag + "_old.pak")
        outs = []
        for t in (a, b):
            outs.append(run([new_exe, "-p", ini_p, t]))
        rc_new, out_new = outs[1]
        rc_old, out_old = run([old_exe, "-p", ini_p, old_pak])
        for nm, r, o in (("新", rc_new, out_new), ("旧", rc_old, out_old)):
            if r != 0 or "error" in o.lower() or "失败" in o:
                print("     %s工具 -p 输出(rc=%d)：%s" % (nm, r, " / ".join(
                    l.strip() for l in o.splitlines() if l.strip())[:300]))
        same_ab, _, desc_ab = diff_bytes(a, b)
        same_ao, _, desc_ao = diff_bytes(a, old_pak)
        print("  %s %s 两次打包一致：%s" % ("[OK] " if same_ab else "[FAIL]", desc, desc_ab))
        print("  %s %s 与原始工具一致(rc=%d)：%s" % ("[OK] " if same_ao else "[FAIL]",
                                                    desc, rc_old, desc_ao))
        if not same_ab:
            fails.append("%s: 输出不可复现（D190 未修净）——" % desc + desc_ab)
        if not same_ao:
            fails.append("%s: 与原始工具产物不一致——" % desc + desc_ao)
        u1 = os.path.join(WORK, tag + "_u1")
        u2 = os.path.join(WORK, tag + "_u2")
        r1, _ = run([old_exe, "-u", a, u1])
        r2, _ = run([new_exe, "-u", old_pak, u2])
        if r1 or r2:
            fails.append("%s: 交叉解包 rc=%d/%d" % (desc, r1, r2))
        # 解包产物按"魔数推断的扩展名"命名，不沿用索引里的文件名（两个工具同行为，
        # 已实测）。因此判据是：两工具落地的 名字->内容哈希 映射完全一致，
        # 且落地内容的多重集 == 源载荷多重集（一个字节都不能变）。
        l1, l2 = listing(u1), listing(u2)
        same_list = l1 == l2 and bool(l1)
        print("  %s %s 解包清单一致：%s（%d 个文件，%s）"
              % ("[OK] " if same_list else "[FAIL]", desc,
                 "是" if same_list else "否", len(l1),
                 ", ".join(sorted(l1)) if len(l1) <= 6 else "%d 项" % len(l1)))
        if not same_list:
            fails.append("%s: 两工具解包清单不一致 old=%s new=%s" % (desc, l1, l2))
        src_map = sorted(((s, hh) for (s, hh) in
                          ((os.path.getsize(os.path.join(indir, n)),
                            sha(os.path.join(indir, n))) for n in files)))
        got_map = sorted(v for k, v in l1.items() if k != "pak_index.ini")
        payload_ok = src_map == got_map and len(got_map) == len(files)
        idx_made = "pak_index.ini" in l1
        print("  %s %s 载荷字节多重集与源文件一致：%s；同时生成 pak_index.ini=%s" %
              ("[OK] " if payload_ok else "[FAIL]", desc, payload_ok, idx_made))
        if not payload_ok:
            fails.append("%s: 解包后载荷与源文件不逐字节相同 %s vs %s"
                         % (desc, src_map, got_map))
        if not idx_made:
            fails.append("%s: 解包未生成 pak_index.ini（与工具既有行为不符）" % desc)
        return a, ini_p

    # 样本 S1：仓库里已提交的 t_in（v5 / 2 资源 / 1 别名）
    inA = os.path.join(WORK, "inA")
    shutil.copytree(FIXTURE, inA)
    aA, iniA = matrix("S1", "v5-2资源-1别名", inA, ("1.html", "2.png"),
                      read_bytes(os.path.join(inA, "pak_index.ini")).decode("utf-8"))

    # 样本 S2：v4 头部（9 字节、无别名——v4 格式没有 alias_count 字段，见 D193）
    inB = os.path.join(WORK, "inB")
    os.makedirs(inB)
    shutil.copy(os.path.join(FIXTURE, "1.html"), os.path.join(inB, "1.html"))
    shutil.copy(os.path.join(FIXTURE, "2.png"), os.path.join(inB, "2.png"))
    shutil.copy(os.path.join(FIXTURE, "2.png"), os.path.join(inB, "3.js"))
    aB, iniB = matrix("S2", "v4-3资源-无别名", inB, ("1.html", "2.png", "3.js"),
                      "[Global]\nversion=4\nencoding=0\n\n[Resources]\n"
                      "1=1.html\n2=2.png\n3=3.js\n")

    # 样本 S3：64 KB 载荷 + 含 0x80/0xFF 的二进制，覆盖 size 字段高位
    inC = os.path.join(WORK, "inC")
    os.makedirs(inC)
    blob = bytes(range(256)) * 256
    with open(os.path.join(inC, "1.html"), "wb") as f:
        f.write(b"<!doctype html>\x80\xff")
    with open(os.path.join(inC, "2.png"), "wb") as f:
        f.write(blob)
    aC, iniC = matrix("S3", "v5-64KB二进制", inC, ("1.html", "2.png"),
                      "[Global]\nversion=5\nencoding=0\n\n[Resources]\n"
                      "1=1.html\n2=2.png\n\n[Alias]\n10=1\n")


    print("== [4b] v4 声明别名必须被拒绝，而不是静默丢掉别名表（D193）==")
    inD = os.path.join(WORK, "inD193")
    os.makedirs(inD)
    for n in ("1.html", "2.png"):
        shutil.copy(os.path.join(FIXTURE, n), os.path.join(inD, n))
    iniD = os.path.join(inD, "pak_index.ini")
    with open(iniD, "w", newline="\n") as f:
        f.write("[Global]\nversion=4\nencoding=0\n\n[Resources]\n"
                "1=1.html\n2=2.png\n\n[Alias]\n10=1\n")
    pakD_new = os.path.join(WORK, "D193_new.pak")
    pakD_old = os.path.join(WORK, "D193_old.pak")
    rcD_new, outD_new = run([new_exe, "-p", iniD, pakD_new])
    rcD_old, outD_old = run([old_exe, "-p", iniD, pakD_old])
    made_new = os.path.isfile(pakD_new)
    print("   %s 新工具 rc=%d 产物=%s；旧工具 rc=%d 产物=%s"
          % ("[OK]  " if (rcD_new != 0 and not made_new) else "[FAIL]",
             rcD_new, "有" if made_new else "无", rcD_old,
             "有" if os.path.isfile(pakD_old) else "无"))
    if rcD_new == 0 or made_new:
        fails.append("D193 未修净：v4 + 别名仍然静默产出（丢弃别名表）")
    if rcD_old == 0 and rcD_new != 0:
        fails.append("差分方向反了：旧工具接受而新工具拒绝，需重新归因")

    print("== [5] ASan：三组样本的打包/解包 + 畸形输入，都不得报越界（D191）==")
    asan = build("pak_asan.exe", NEW_FLAGS + ["/Zi", "/fsanitize=address"],
                 [NEW_SRC], WORK, start_ts)
    if asan is None:
        fails.append("ASan 目标编译失败，越界判据无法执行")
    else:
        cases = []
        for tag, ini_p, packed in (("S1", iniA, aA), ("S2", iniB, aB), ("S3", iniC, aC)):
            cases.append(("pack-" + tag, [asan, "-p", ini_p,
                                          os.path.join(WORK, "asan_%s.pak" % tag)], True))
            cases.append(("unpack-" + tag, [asan, "-u", packed,
                                            os.path.join(WORK, "asan_out_" + tag)], True))
        # 畸形输入：必须既不越界，也不得被当成成功（要用 S3 产物做样本，
        # 所以先把 6 条正常用例跑完，再构造畸形输入）
        good = list(cases)
        cases = []

        def runall(lst):
            for label, argv, want_ok in lst:
                if os.path.isdir(argv[-1]):
                    shutil.rmtree(argv[-1])
                rc, out = run(argv)
                hit = "AddressSanitizer" in out
                if hit:
                    hits.append(label)
                    for line in out.splitlines():
                        if "ERROR" in line or "SUMMARY" in line or "#0 " in line:
                            print("     " + line.strip())
                if want_ok and (hit or rc != 0):
                    fails.append("ASan %s：rc=%d asan=%s（期望 rc=0 且无越界）"
                                 % (label, rc, "HIT" if hit else "clean"))
                if not want_ok and hit:
                    fails.append("ASan %s：畸形输入触发越界" % label)
                if not want_ok and rc == 0:
                    fails.append("ASan %s：畸形输入被当成成功（rc=0）" % label)
                print("   %s %-24s rc=%-3d asan=%s"
                      % ("[FAIL]" if hit else "[OK]  ", label, rc,
                         "HIT" if hit else "clean"))

        hits = []
        runall(good)
        trunc = os.path.join(WORK, "trunc.pak")
        s3_pak = os.path.join(WORK, "asan_S3.pak")
        if not os.path.isfile(s3_pak):
            fails.append("没有 asan_S3.pak，畸形输入用例无法构造（判据不能空跑）")
            return 1 if fails else 0
        raw = read_bytes(s3_pak)
        with open(trunc, "wb") as f:
            f.write(raw[:8])                      # 头部不完整
        short = os.path.join(WORK, "short.pak")   # 头部完好但载荷被截
        with open(short, "wb") as f:
            f.write(raw[:len(raw) - 5])
        zeros = os.path.join(WORK, "zeros.pak")
        with open(zeros, "wb") as f:
            f.write(b"\x00" * 40)
        junk = os.path.join(WORK, "junk.pak")
        with open(junk, "wb") as f:
            f.write(b"\xff" * 40)
        for nm, t in (("trunc8", trunc), ("payload-short", short),
                      ("all-zero", zeros), ("all-ff", junk)):
            cases.append(("corrupt-" + nm, [asan, "-u", t,
                                            os.path.join(WORK, "asan_bad_" + nm)], False))
        with open(os.path.join(WORK, "bad_ini.txt"), "w", newline="\n") as f:
            f.write("[Global]\nversion=999\nencoding=7\n\n[Resources]\n")
        cases.append(("corrupt-pack-bad-ini",
                      [asan, "-p", os.path.join(WORK, "bad_ini.txt"),
                       os.path.join(WORK, "asan_bad.pak")], False))

        hits = []
        runall(cases)
        if cases and len(hits) == len(good) + len(cases):
            fails.append("全部 ASan 用例都报越界：多半是量具/构建问题而非代码，需人工归因")

    print("== [6] Red 对照：把 D191 的修复从副本里删掉，ASan 必须报越界 ==")
    red_src = os.path.join(WORK, "pak_red.c")
    src_text = read_bytes(NEW_SRC).decode("utf-8")
    if "f.buffer[f.size] = '\\0';" not in src_text:
        fails.append("pak.c 里找不到 D191 的 NUL 终止行，Red 对照无法构造")
    else:
        red = src_text.replace("f.buffer[f.size] = '\\0';", "/* RED: 修复被移除 */")
        with open(red_src, "w", encoding="utf-8", newline="") as f:
            f.write(red)
        red_asan = build("pak_red.exe", NEW_FLAGS + ["/Zi", "/fsanitize=address"],
                         [red_src], WORK, 0)
        if red_asan is None:
            fails.append("Red 变体编译失败，D191 的红灯无法证实")
        else:
            rc, out = run([red_asan, "-p", iniA, os.path.join(WORK, "red.pak")])
            hit = "AddressSanitizer" in out
            print("   %s 去掉 NUL 终止后 ASan %s（rc=%d）"
                  % ("[OK]  " if hit else "[FAIL]", "报越界" if hit else "仍然干净", rc))
            for line in out.splitlines():
                if "ERROR" in line or "SUMMARY" in line:
                    print("     " + line.strip())
            if not hit:
                fails.append("Red 变体未报越界：[5] 的绿灯不能作为 D191 的证据")



    print("\nFAILED-CHECKS: %s" % (fails or "none"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
