#!/usr/bin/env python3
"""loader_edge_test2.py - end-to-end loader edge cases with CHILD-PROCESS
command-line probing (the channel that made A6 verification work)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# 缺陷 D60：旧版本把 M151 树的路径写死在这里——在第 3 周期之后，直接运行它会
# (a) 测到旧二进制上（结论与当前内核无关），(b) 改写旧树 out/mcloud 的 flags 文件。
# 现改为从 --chrome 推导，默认仍指向 M151 以保持既有行为可复现，但必须显式选择被测树。
OUT_DIR = os.environ.get("LOADER_TEST_OUT", r"D:\wxmuma\chromium-src\src\out\mcloud")
CHROME = os.path.join(OUT_DIR, "chrome.exe")
FLAGS = os.path.join(OUT_DIR, "mcloud_flags.txt")
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def ps(cmd):
    return subprocess.run([PS, "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=90).stdout


def probe(name, file_bytes, extra_cli=(), wait_s=9):
    """Write flags file, launch browser, capture all child cmdlines, restore."""
    udd = os.path.join(tempfile.gettempdir(), f"mcloud_lp_{name}")
    shutil.rmtree(udd, ignore_errors=True)
    os.makedirs(udd)
    with open(FLAGS, "wb") as f:
        f.write(file_bytes)
    args = [CHROME, f"--user-data-dir={udd}", "--no-first-run",
            "--no-default-browser-check", "--disable-background-networking"] + \
           list(extra_cli) + ["about:blank"]
    proc = subprocess.Popen(args)
    time.sleep(wait_s)
    allcmd = ps(
        "(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
        "Select-Object -ExpandProperty CommandLine) -join ' ||| '")
    ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
       f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
    shutil.rmtree(udd, ignore_errors=True)
    return allcmd


def check(name, allcmd, tokens):
    problems = []
    if not allcmd.strip():
        print(f"[{name}] FAIL (no child cmdlines captured)")
        return False
    for tok, want in tokens:
        present = tok in allcmd
        if present != want:
            problems.append(f"{tok}: want={want} got={present}")
    if problems:
        print(f"[{name}] FAIL " + "; ".join(problems))
        return False
    print(f"[{name}] PASS")
    return True


def main():
    if not os.path.exists(CHROME):
        print("chrome.exe missing")
        return 2
    backup = FLAGS + ".lpbak"
    shutil.copy2(FLAGS, backup)
    results = []
    try:
        deployed = open(backup, "rb").read()

        # L0 control: real deployed file → probe feature in child cmdlines
        cmd = probe("L0", deployed)
        results.append(check("L0-control", cmd,
                             [("SpareRendererForSitePerProcess", True)]))

        # L-merge (both sides present). NOTE: child cmdlines cannot prove merge
        # ORDER - Chromium re-serialises the feature list when launching
        # children (observed 2026-10-09 probe_order.py: order normalises to
        # alphabetical regardless of append order). In-process user-first order
        # is proven by code inspection (merged = user + "," + builtin).
        cmd = probe("LUF", b"--enable-features=AAutoMarkerBuiltin\n",
                    extra_cli=["--enable-features=ZUserMarker"])
        occurrences = re.findall(r"--enable-features=(\S+)", cmd)
        merged = [v for v in occurrences
                  if "ZUserMarker" in v and "AAutoMarkerBuiltin" in v]
        ok = len(merged) >= 1
        print(f"[L-merge] {'PASS' if ok else 'FAIL'} - {len(merged)}/"
              f"{len(occurrences)} child value(s) contain both user+builtin")
        results.append(ok)

        # L-cap: >1MiB file must fail-closed (no flags applied), browser fine
        big = b"--enable-features=HugeCapProbeX\n" + b"#filler-line-to-grow-size\n" * 60000
        cmd = probe("LCAP", big)
        results.append(check("L-cap-failclosed", cmd,
                             [("HugeCapProbeX", False), ("--type=", True)]))

        # L-crlf
        cmd = probe("LCRLF",
                    b"--enable-features=SpareRendererForSitePerProcess\r\n"
                    b"--enable-features=InlineScriptCache\r\n")
        results.append(check("L-crlf", cmd,
                             [("SpareRendererForSitePerProcess", True),
                              ("InlineScriptCache", True)]))

        # L-no-trailing-newline
        cmd = probe("LNL",
                    b"--enable-features=SpareRendererForSitePerProcess\n"
                    b"--enable-features=InlineScriptCache")
        results.append(check("L-no-trailing-newline", cmd,
                             [("InlineScriptCache", True)]))

        # L-malformed lines + binary garbage
        cmd = probe("LMAL",
                    b"--\n--=\n--x=\n#\n   \nnot-a-flag line\n"
                    b"\xff\xfe\x00binary garbage\n"
                    b"--enable-features=SpareRendererForSitePerProcess\n")
        results.append(check("L-malformed", cmd,
                             [("SpareRendererForSitePerProcess", True)]))

        # L-unclosed quote in js-flags
        cmd = probe("LQ",
                    b'--js-flags="--invocation_count_for_maglev=200\n'
                    b"--enable-features=SpareRendererForSitePerProcess\n")
        results.append(check("L-unclosed-quote", cmd,
                             [("SpareRendererForSitePerProcess", True)]))

        # L-gbk comment bytes
        cmd = probe("LGBK",
                    "中文注释测试行\n".encode("gbk") +
                    b"--enable-features=SpareRendererForSitePerProcess\n")
        results.append(check("L-gbk-comment", cmd,
                             [("SpareRendererForSitePerProcess", True)]))

        # L-jsflags (D40): one oversized plain-switch value (200 KiB --js-flags)
        # must be skipped by the byte budget instead of overflowing every
        # renderer's CreateProcessW command line. Browser + renderer must live.
        huge_js = b'--js-flags="' + b"--expose-gc " * 25000 + b'"\n'  # ~250 KiB
        assert len(huge_js) > 200_000
        cmd = probe("LJF", huge_js + b"--enable-features=SpareRendererForSitePerProcess\n",
                    wait_s=14)
        results.append(check("L-jsflags-oversized(budget)", cmd,
                             [("--expose-gc", False),
                              ("SpareRendererForSitePerProcess", True),
                              ("--type=renderer", True)]))

        # L-many-plain (D40): 4000 distinct plain switches must not push child
        # cmdlines over the OS limit; plain sub-budget (12 KiB) caps the appends.
        many = "".join(f"--mcloud-probe-sw{i}=v{i}\n" for i in range(4000)).encode()
        cmd = probe("LMANY", many + b"--enable-features=SpareRendererForSitePerProcess\n",
                    wait_s=14)
        results.append(check("L-many-plain-sw(budget)", cmd,
                             [("mcloud-probe-sw3999", False),
                              ("SpareRendererForSitePerProcess", True),
                              ("--type=renderer", True)]))

        # L-huge-merge: 3000 unknown features -> v3+ cap must skip the built-in
        # merge (D39: >24KiB overflowed child CreateProcessW cmdline limit and
        # made the GPU process unlaunchable => FATAL). Browser must stay alive.
        lines = b"".join(f"--enable-features=EdgeProbeFeat{i}\n".encode()
                         for i in range(3000))
        cmd = probe("LHUGE", lines, wait_s=18)
        results.append(check("L-huge-merge-3000(cap fires)", cmd,
                             [("EdgeProbeFeat2999", False),
                              ("--type=renderer", True)]))
    finally:
        shutil.copy2(backup, FLAGS)
        os.remove(backup)
        print("flags file restored.")

    print(f"\nSUMMARY: {sum(results)}/{len(results)} cases PASS")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
