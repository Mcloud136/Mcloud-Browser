#!/usr/bin/env python3
"""debug2.py - LUF full scan + LHUGE threshold & CHECK text."""
import os
import re
import shutil
import subprocess
import tempfile
import time

OUT_DIR = r"D:\wxmuma\chromium-src\src\out\mcloud"
CHROME = os.path.join(OUT_DIR, "chrome.exe")
FLAGS = os.path.join(OUT_DIR, "mcloud_flags.txt")
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

def ps(cmd):
    return subprocess.run([PS, "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=90).stdout

def launch(tag, file_bytes, extra_cli, wait_s=10, capture_stderr=False):
    udd = os.path.join(tempfile.gettempdir(), f"mcloud_d2_{tag}")
    shutil.rmtree(udd, ignore_errors=True); os.makedirs(udd)
    backup = FLAGS + ".d2bak"
    shutil.copy2(FLAGS, backup)
    with open(FLAGS, "wb") as f:
        f.write(file_bytes)
    err = None
    try:
        args = [CHROME, f"--user-data-dir={udd}", "--no-first-run",
                "--no-default-browser-check"] + list(extra_cli) + ["about:blank"]
        if capture_stderr:
            errf = open(os.path.join(tempfile.gettempdir(), f"chrome_err_{tag}.log"), "wb")
            proc = subprocess.Popen(args, stderr=errf)
        else:
            proc = subprocess.Popen(args)
        time.sleep(wait_s)
        rc = proc.poll()
        cmdlines = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                      f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
                      "ForEach-Object {{ \"$($_.ProcessId) :: $($_.CommandLine)\" }}")
        ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
           f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        try: proc.wait(timeout=15)
        except Exception: proc.kill()
        if capture_stderr:
            errf.close()
            err = open(os.path.join(tempfile.gettempdir(), f"chrome_err_{tag}.log"), "rb").read().decode("utf-8", "replace")
    finally:
        shutil.copy2(backup, FLAGS); os.remove(backup)
        shutil.rmtree(udd, ignore_errors=True)
    return rc, cmdlines, err

print("========== LUF: full scan of all captured cmdlines ==========")
rc, cmdlines, _ = launch("LUF", b"--enable-features=AAutoMarkerBuiltin\n",
                         ["--enable-features=ZUserMarker"])
vals = []
for l in cmdlines.splitlines():
    for m in re.finditer(r"--enable-features=(\S+)", l):
        vals.append((l.split(" :: ")[0], m.group(1)))
print(f"browser exit={rc}, occurrences={len(vals)}")
for pid, v in vals[:12]:
    has_u, has_b = "ZUserMarker" in v, "AAutoMarkerBuiltin" in v
    mark = "BOTH" if has_u and has_b else ("user" if has_u else ("builtin" if has_b else "-"))
    print(f"  pid={pid} [{mark}] v[:100]={v[:100]}")
both = [v for _, v in vals if "ZUserMarker" in v and "AAutoMarkerBuiltin" in v]
if both:
    ok = all(v.find("ZUserMarker") < v.find("AAutoMarkerBuiltin") for v in both)
    print(f"BOTH-values: {len(both)}, all user-first: {ok}")
else:
    print("BOTH-values: 0  (markers never co-occur in one switch value)")

print("========== LHUGE threshold ==========")
for n in (300, 800, 1500, 3000):
    lines = b"".join(f"--enable-features=EdgeProbeFeat{i}\n".encode() for i in range(n))
    approx_kb = sum(len(l) for l in lines.splitlines()) / 1024
    rc, cmd, _ = launch(f"T{n}", lines, [], wait_s=8)
    alive = "renderer" in cmd
    print(f"n={n} (~{approx_kb:.0f}KB merged): exit={rc} child-with-renderer={alive}")
    if rc is not None and rc != 0:
        # capture the CHECK text for the first failing size
        rc2, _, err = launch(f"E{n}", lines, ["--enable-logging=stderr", "--v=0"], wait_s=8, capture_stderr=True)
        if err:
            key = [l for l in err.splitlines() if re.search(r"CHECK|DCHECK|FATAL|assert|exceeded|size", l, re.I)]
            print("  stderr key lines:")
            for k in key[:6]:
                print("   ", k[:200])
        break
