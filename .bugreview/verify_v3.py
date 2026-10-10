#!/usr/bin/env python3
"""verify_v3.py - decisive checks: (1) user-first merge visible in renderer
cmdline; (2) D39 cap keeps browser alive with 3000-feature file (v2 died at ~12s)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

OUT_DIR = r"D:\wxmuma\chromium-src\src\out\mcloud"
CHROME = os.path.join(OUT_DIR, "chrome.exe")
FLAGS = os.path.join(OUT_DIR, "mcloud_flags.txt")
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

def ps(cmd):
    return subprocess.run([PS, "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True, timeout=90).stdout

def case(name, file_bytes, extra_cli, wait_s, stderr_log=None):
    udd = os.path.join(tempfile.gettempdir(), f"mcloud_v3_{name}")
    shutil.rmtree(udd, ignore_errors=True); os.makedirs(udd)
    backup = FLAGS + ".v3bak"
    shutil.copy2(FLAGS, backup)
    with open(FLAGS, "wb") as f:
        f.write(file_bytes)
    errh = open(stderr_log, "wb") if stderr_log else subprocess.DEVNULL
    try:
        args = [CHROME, f"--user-data-dir={udd}", "--no-first-run",
                "--no-default-browser-check"] + list(extra_cli) + ["about:blank"]
        proc = subprocess.Popen(args, stderr=errh)
        time.sleep(wait_s)
        rc = proc.poll()
        cmdlines = ""
        for _attempt in range(3):
            cmdlines = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                          f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
                          "ForEach-Object { $_.CommandLine }")
            if "--enable-features" in cmdlines:
                break
            time.sleep(2)
        ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
           f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        try: proc.wait(timeout=20)
        except Exception: proc.kill()
    finally:
        if stderr_log: errh.close()
        shutil.copy2(backup, FLAGS); os.remove(backup)
        shutil.rmtree(udd, ignore_errors=True)
    return rc, cmdlines

fails = 0

# (1) user-first merge in renderer cmdline
rc, cmd = case("UF", b"--enable-features=AAutoMarkerBuiltin\n",
               ["--enable-features=ZUserMarker"], 12)
vals = re.findall(r"--enable-features=(\S+)", cmd)
both = [v for v in vals if "ZUserMarker" in v and "AAutoMarkerBuiltin" in v]
if both and all(v.index("ZUserMarker") < v.index("AAutoMarkerBuiltin") for v in both):
    print(f"[UF] PASS - {len(both)} merged value(s), user-first in all; sample: {both[0][:90]}")
else:
    fails += 1
    print(f"[UF] FAIL - exit={rc} occurrences={len(vals)} both={len(both)}")
    for v in vals[:6]:
        print("   ", v[:110])

# (2) D39: 3000 features -> browser must stay alive (v2 died ~12s with FATAL)
big = "".join(f"--enable-features=EdgeProbeFeat{i}\n" for i in range(3000)).encode()
errlog = os.path.join(tempfile.gettempdir(), "v3_huge_err.log")
rc, cmd = case("HUGE", big, ["--enable-logging=stderr"], 18, stderr_log=errlog)
alive = rc is None
has_render = "--type=renderer" in cmd
warn = "built-in features skipped" in open(errlog, "rb").read().decode("utf-8", "replace") if os.path.exists(errlog) else False
if alive and has_render:
    print(f"[HUGE] PASS - browser alive at 18s (v2 died ~12s), renderer present={has_render}, cap-warning={warn}")
else:
    fails += 1
    print(f"[HUGE] FAIL - exit={rc} alive={alive} renderer={has_render} cap-warning={warn}")

print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAIL")
sys.exit(1 if fails else 0)
