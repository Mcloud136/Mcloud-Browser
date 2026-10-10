#!/usr/bin/env python3
"""probe_order.py - dump RAW child cmdlines to settle the merged --enable-features
order question (who wins when the user overrides a built-in feature)."""
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

BUILTIN = "ZzzBuiltinProbe"
USER = "AaaUserProbe"


def ps(cmd):
    r = subprocess.run([PS, "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=120)
    return r.stdout


udd = os.path.join(tempfile.gettempdir(), "mcloud_probe_order")
shutil.rmtree(udd, ignore_errors=True)
os.makedirs(udd)
backup = FLAGS + ".probebak"
shutil.copy2(FLAGS, backup)

probe_lines = (
    "# probe\n"
    f"--enable-features={BUILTIN}\n"
    f"--disable-features={BUILTIN}Disable\n"
    "--ignore-gpu-blocklist\n"
)
with open(FLAGS, "w", encoding="utf-8", newline="\n") as f:
    f.write(probe_lines)

try:
    proc = subprocess.Popen(
        [CHROME, f"--user-data-dir={udd}", "--no-first-run",
         "--no-default-browser-check",
         f"--enable-features={USER}",
         f"--disable-features={USER}Disable",
         "about:blank"])
    time.sleep(11)
    alive = proc.poll() is None
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
             f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
             "ForEach-Object { $_.CommandLine }")
    ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
       f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
finally:
    shutil.copy2(backup, FLAGS)
    os.remove(backup)
    shutil.rmtree(udd, ignore_errors=True)

lines = [l for l in out.splitlines() if l.strip()]
print(f"alive={alive}  processes={len(lines)}")
for l in lines:
    m = re.search(r"--type=([a-z\-]+)", l)
    role = m.group(1) if m else "BROWSER"
    ef = re.findall(r"--enable-features=(\S+)", l)
    df = re.findall(r"--disable-features=(\S+)", l)
    print(f"\n### {role}  (len={len(l)})")
    print(f"  --enable-features occurrences={len(ef)}")
    for v in ef:
        print(f"     value: {v[:200]}")
    print(f"  --disable-features occurrences={len(df)}")
    for v in df:
        print(f"     value: {v[:200]}")
    if ef:
        joined = " ".join(ef)
        print(f"  order: builtin@{joined.find(BUILTIN)} user@{joined.find(USER)}"
              f"  -> {'BUILTIN-FIRST' if joined.find(BUILTIN) < joined.find(USER) else 'USER-FIRST'}")
