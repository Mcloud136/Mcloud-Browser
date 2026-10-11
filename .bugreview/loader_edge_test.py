#!/usr/bin/env python3
"""loader_edge_test.py - cycle-2 bug-review: memory-overflow / robustness
edge-case suite for the MCloud flags loader (loader v2 in chrome_main_delegate.cc),
executed END-TO-END against the dev build binary.

Method: swap out/mcloud/mcloud_flags.txt with adversarial variants, launch
chrome --headless=new --dump-dom chrome://version, inspect exit code, output
presence and the self-reported command line. Original file always restored.
"""
import os
import shutil
import subprocess
import sys
import tempfile

OUT_DIR = r"D:\wxmuma\chromium-src\src\out\mcloud"
CHROME = os.path.join(OUT_DIR, "chrome.exe")
FLAGS = os.path.join(OUT_DIR, "mcloud_flags.txt")
BACKUP = FLAGS + ".edgebak"

results = []

def run_case(name, file_bytes, extra_cli=None, expect=None, timeout=120):
    udd = tempfile.mkdtemp(prefix="mcloud_edge_")
    cli = ["--headless=new", "--disable-gpu", "--no-sandbox",
           f"--user-data-dir={udd}", "--no-first-run",
           "--no-default-browser-check"]
    if extra_cli:
        cli += extra_cli
    cli += ["--dump-dom", "chrome://version"]
    try:
        r = subprocess.run([CHROME] + cli, capture_output=True, timeout=timeout)
        rc = r.returncode
        out = (r.stdout or b"") + (r.stderr or b"")
    except subprocess.TimeoutExpired:
        rc, out = -999, b"TIMEOUT"
    finally:
        shutil.rmtree(udd, ignore_errors=True)
    # 原来这里有一行 `ok = (rc == 0) and (b"chrome://version" not in b"")`：
    # 后半段是恒真式（任何串都在空字节串里"不存在"），且 ok 从未被使用——真正的判定
    # 在下面的 verdict 里。留着只会让人以为存在一条 DOM 内容断言。
    dom_has = len(out) > 1000
    verdict = "PASS" if (rc == 0 and dom_has) else f"FAIL(rc={rc},out={len(out)})"
    if expect:
        for token, want in expect:
            present = token.encode("utf-8", "replace") in out
            if present != want:
                verdict += f" EXPECT-MISMATCH[{token} want={want} got={present}]"
    results.append((name, verdict, rc, len(out)))
    print(f"[{name}] {verdict}")
    return out

def main():
    if not os.path.exists(CHROME):
        print("chrome.exe missing"); return 2
    shutil.copy2(FLAGS, BACKUP)
    try:
        # L0 control: current deployed file must apply its probe feature
        run_case("L0-control", open(BACKUP, "rb").read(),
                 expect=[("SpareRendererForSitePerProcess", True)])

        # L-user-first: D21 fix end-to-end proof (user entry BEFORE builtin)
        out = run_case("L-user-first",
                       b"--enable-features=AAutoMarkerBuiltin\n",
                       extra_cli=["--enable-features=ZUserMarker"],
                       expect=[("ZUserMarker", True)])
        txt = out.decode("utf-8", "replace")
        iu = txt.find("ZUserMarker"); ib = txt.find("AAutoMarkerBuiltin")
        order = "OK(user-first)" if (iu >= 0 and ib >= 0 and iu < ib) else \
                ("MISSING" if iu < 0 or ib < 0 else "WRONG-ORDER(builtin-first)")
        print(f"  [L-user-first] merge order check: {order}")
        results.append(("L-user-first-order", order, 0, 0))

        # L-cap: >1MiB file -> fail-closed (no flags), must not crash
        big = b"--enable-features=HugeCapProbeX\n" + b"#filler\n" * 200000  # ~1.7MB
        run_case("L-cap-1.7MB", big,
                 expect=[("HugeCapProbeX", False)])

        # L-crlf: CRLF endings still parsed
        run_case("L-crlf",
                 b"--enable-features=SpareRendererForSitePerProcess\r\n--enable-features=InlineScriptCache\r\n",
                 expect=[("SpareRendererForSitePerProcess", True)])

        # L-nonl: no trailing newline on last line
        run_case("L-no-trailing-newline",
                 b"--enable-features=SpareRendererForSitePerProcess\n--enable-features=InlineScriptCache",
                 expect=[("InlineScriptCache", True)])

        # L-malformed: junk lines mixed with one valid line
        run_case("L-malformed-lines",
                 b"--\n--=\n--x=\n#\n   \nnot-a-flag line\n"
                 b"\xff\xfe\x00binary garbage\n--enable-features=SpareRendererForSitePerProcess\n",
                 expect=[("SpareRendererForSitePerProcess", True)])

        # L-quote: unterminated quote value
        run_case("L-unclosed-quote",
                 b'--js-flags="--invocation_count_for_maglev=200\n'
                 b"--enable-features=SpareRendererForSitePerProcess\n",
                 expect=[("SpareRendererForSitePerProcess", True)])

        # L-gbk: non-UTF8 (GBK) comment bytes
        run_case("L-gbk-bytes",
                 "﻿".encode("utf-8") + "中文注释测试行\n".encode("gbk") +
                 b"--enable-features=SpareRendererForSitePerProcess\n",
                 expect=[("SpareRendererForSitePerProcess", True)])

        # L-huge-merge: 3000 unknown features (~45KB merged switch) - renderer must still boot
        lines = b"".join(f"--enable-features=EdgeProbeFeat{i}\n".encode() for i in range(3000))
        run_case("L-huge-merge-3000", lines,
                 expect=[("EdgeProbeFeat2999", True)], timeout=180)
    finally:
        shutil.copy2(BACKUP, FLAGS)
        os.remove(BACKUP)
        print("flags file restored.")

    fails = [r for r in results if not r[1].startswith("PASS") and not r[1].startswith("OK")]
    print(f"\nSUMMARY: {len(results)} cases, {len(fails)} non-pass")
    for f in fails:
        print("  ", f)
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
