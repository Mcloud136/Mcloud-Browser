#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新旧 pak 工具的行为差分（第7周期收口轮，对 pak_src_fixed 的兼容性核查）。

逐条边界输入同时喂给 pak_src（原始）与 pak_src_fixed/pak.c（重写），比较
退出码 + 是否产出 + 产物字节。目的：把"等价于原工具"这句话变成可测判据，
并找出静默丢数据的分支。只读仓库、只写 .cycle7/pakdiff，不改被测源码。
"""
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(THOR, ".cycle7", "pakverify")
OLD = os.path.join(BIN, "pak_old.exe")
NEW = os.path.join(BIN, "pak_new.exe")
OUT = os.path.join(THOR, ".cycle7", "pakdiff")

CASES = [
    ("v4+alias",        "[Global]\nversion=4\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n\n[Alias]\n10=1\n", False),
    ("v4+alias0",       "[Global]\nversion=4\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n\n[Alias]\n", True),
    ("v4-noalias",      "[Global]\nversion=4\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n", True),
    ("v5+alias",        "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n\n[Alias]\n10=1\n", True),
    ("v5-no-alias",     "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n", True),
    ("double-eq",       "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1=2.png\n", False),
    ("id-65536",        "[Global]\nversion=5\nencoding=0\n\n[Resources]\n65536=1.html\n", False),
    ("alias-oob",       "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1.html\n\n[Alias]\n10=99\n", False),
    ("alias-self",      "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1.html\n\n[Alias]\n10=0\n", True),
    ("no-global",       "[Resources]\n1=1.html\n", False),
    ("version-6",       "[Global]\nversion=6\nencoding=0\n\n[Resources]\n1=1.html\n", False),
    ("encoding-300",    "[Global]\nversion=5\nencoding=300\n\n[Resources]\n1=1.html\n", True),
    ("encoding-256",    "[Global]\nversion=5\nencoding=256\n\n[Resources]\n1=1.html\n", True),
    ("crlf",            "[Global]\r\nversion=5\r\nencoding=0\r\n\r\n[Resources]\r\n1=1.html\r\n2=2.png\r\n\r\n[Alias]\r\n10=1\r\n", True),
    ("empty-resources", "[Global]\nversion=5\nencoding=0\n\n[Resources]\n", False),
    ("res-before-glob", "[Resources]\n1=1.html\n\n[Global]\nversion=5\nencoding=0\n", False),
    ("alias-before-res", "[Global]\nversion=5\nencoding=0\n\n[Alias]\n10=0\n\n[Resources]\n1=1.html\n", False),
    ("dup-resource-id", "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=1.html\n1=2.png\n", True),
    ("missing-file",    "[Global]\nversion=5\nencoding=0\n\n[Resources]\n1=nope.html\n", False),
]


def prep(name, inispec):
    d = os.path.join(OUT, "in_" + "".join(c for c in name if c.isalnum() or c in "-_"))
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    shutil.copy(os.path.join(THOR, "pak_src_fixed", "t_in", "1.html"),
                os.path.join(d, "1.html"))
    shutil.copy(os.path.join(THOR, "pak_src_fixed", "t_in", "2.png"),
                os.path.join(d, "2.png"))
    with open(os.path.join(d, "pak_index.ini"), "wb") as f:
        f.write(inispec.encode("utf-8"))
    return d


def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()


def attempt(exe, d, tag):
    pak = os.path.join(OUT, "%s_%s.pak" % (tag, os.path.basename(d)))
    if os.path.exists(pak):
        os.remove(pak)
    p = subprocess.run([exe, "-p", os.path.join(d, "pak_index.ini"), pak],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt = p.stdout.decode("gbk", "replace")
    made = os.path.isfile(pak)
    blob = read_bytes(pak) if made else b""
    msgs = " / ".join(l.strip() for l in txt.splitlines() if l.strip())[:90]
    return p.returncode, made, blob, msgs


def main():
    if not (os.path.isfile(OLD) and os.path.isfile(NEW)):
        print("ENV: 先运行 pakverify.py 生成两个工具")
        return 2
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    rows = []
    for name, inispec, want_ok in CASES:
        d = prep(name, inispec)
        ro, mo, bo, so = attempt(OLD, d, "old")
        rn, mn, bn, sn = attempt(NEW, d, "new")
        verdict = "同" if (ro == rn and mo == mn and bo == bn) else "异"
        rows.append((name, want_ok, ro, mo, rn, mn, verdict, len(bo), len(bn), so, sn))
    print("%-18s %-4s | %-14s | %-14s | 结论  产物字节" %
          ("用例", "期望", "旧(rc/产物)", "新(rc/产物)"))
    for (name, want_ok, ro, mo, rn, mn, v, lo, ln_, so, sn) in rows:
        print("%-18s %-4s | rc=%-3d %-5s | rc=%-3d %-5s | %s  %d/%d" %
              (name, "ok" if want_ok else "err", ro, "yes" if mo else "no",
               rn, "yes" if mn else "no", v, lo, ln_))
        if so.strip() and so.strip() != sn.strip():
            print("      旧消息: %s" % so)
            print("      新消息: %s" % sn)
    diff = [r[0] for r in rows if r[6] == "异"]
    silent = [r[0] for r in rows if r[4] == 0 and r[5] and not r[3] and r[2] != 0]
    wrong = [r[0] for r in rows
             if (r[1] and (r[4] != 0 or not r[5])) or ((not r[1]) and r[4] == 0)]
    print("\n行为不一致: %s" % (diff or "无"))
    print("新工具在旧工具拒绝时静默成功: %s" % (silent or "无"))
    print("新工具自身判据不符(期望ok却失败/期望err却成功): %s" % (wrong or "无"))
    if len(rows) != len(CASES):
        print("自检失败: 用例 %d 条但结果 %d 条" % (len(CASES), len(rows)))
        return 1
    ok_cases = [r[0] for r in rows if r[1] and r[5]]
    if not ok_cases:
        print("自检失败: 没有任何用例成功产出，对照组不成立")
        return 1
    print("自检: %d 条用例，其中 %d 条成功产出、%d 条按预期被拒绝"
          % (len(rows), len(ok_cases), len(rows) - len(ok_cases)))
    return 1 if (diff or silent or wrong) else 0


if __name__ == "__main__":
    sys.exit(main())
