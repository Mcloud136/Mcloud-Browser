#!/usr/bin/env python3
"""debug_luf_lhuge.py - dump raw evidence for the two failing cases."""
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

def run(tag, file_bytes, extra_cli, wait_s=10):
    udd = os.path.join(tempfile.gettempdir(), f"mcloud_dbg_{tag}")
    shutil.rmtree(udd, ignore_errors=True); os.makedirs(udd)
    backup = FLAGS + ".dbgbak"
    shutil.copy2(FLAGS, backup)
    with open(FLAGS, "wb") as f:
        f.write(file_bytes)
    try:
        args = [CHROME, f"--user-data-dir={udd}", "--no-first-run",
                "--no-default-browser-check"] + list(extra_cli) + ["about:blank"]
        proc = subprocess.Popen(args)
        time.sleep(wait_s)
        alive = proc.poll() is None
        rc = proc.poll()
        cmdlines = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                      f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
                      "ForEach-Object {{ \"$($_.ProcessId) :: $($_.CommandLine)\" }}")
        ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
           f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        try: proc.wait(timeout=15)
        except Exception: proc.kill()
    finally:
        shutil.copy2(backup, FLAGS); os.remove(backup)
        shutil.rmtree(udd, ignore_errors=True)

    print(f"===== {tag}: browser alive@query={alive} exit={rc} =====")
    lines = [l for l in cmdlines.splitlines() if l.strip()]
    print(f"processes captured: {len(lines)}")
    for l in lines[:3]:
        for m in re.finditer(r"--enable-features=(\S+)", l):
            v = m.group(1)
            if "ZUserMarker" in v or "AAutoMarkerBuiltin" in v or "EdgeProbeFeat2999" in v:
                pid = l.split(" :: ")[0]
                print(f"  pid={pid} val[:120]={v[:120]} ... val[-80:]={v[-80:]} len={len(v)}")
    return lines

if __name__ == "__main__":
    run("LUF", b"--enable-features=AAutoMarkerBuiltin\n",
        ["--enable-features=ZUserMarker"])
    lines = run("LHUGE",
                b"".join(f"--enable-features=EdgeProbeFeat{i}\n".encode() for i in range(3000)),
                [], wait_s=12)
    if not lines:
        print("LHUGE: browser produced no matching processes (exited?)")
