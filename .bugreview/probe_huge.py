#!/usr/bin/env python3
"""probe_huge.py - prove the D39 cap actually fires: with a 3000-entry built-in
--enable-features file, no child may receive 'EdgeProbeFeat' (built-in merge
skipped) and the browser must stay alive with renderers."""
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
                          capture_output=True, text=True, timeout=120).stdout


udd = os.path.join(tempfile.gettempdir(), "mcloud_probe_huge")
shutil.rmtree(udd, ignore_errors=True)
os.makedirs(udd)
backup = FLAGS + ".probak"
shutil.copy2(FLAGS, backup)

N = 3000
with open(FLAGS, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(f"--enable-features=EdgeProbeFeat{i}" for i in range(N)) + "\n")
size = os.path.getsize(FLAGS)

errlog = os.path.join(tempfile.gettempdir(), "probe_huge_err.log")
errh = open(errlog, "wb")
try:
    proc = subprocess.Popen(
        [CHROME, f"--user-data-dir={udd}", "--no-first-run",
         "--no-default-browser-check", "--enable-logging=stderr", "about:blank"],
        stderr=errh)
    time.sleep(18)
    alive = proc.poll() is None
    out = ""
    for _ in range(3):
        out = ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                 f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
                 "ForEach-Object { $_.CommandLine }")
        if "--type=" in out:
            break
        time.sleep(2)
    ps("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
       f"Where-Object {{ $_.CommandLine -like '*{udd}*' }} | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    try:
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
finally:
    errh.close()
    shutil.copy2(backup, FLAGS)
    os.remove(backup)
    shutil.rmtree(udd, ignore_errors=True)

lines = [l for l in out.splitlines() if l.strip()]
joined = "\n".join(lines)
leaked = joined.count("EdgeProbeFeat")
renderers = len(re.findall(r"--type=renderer", joined))
ef_vals = re.findall(r"--enable-features=(\S+)", joined)
err = open(errlog, "rb").read().decode("utf-8", "replace") if os.path.exists(errlog) else ""
warn = "built-in features skipped" in err

print(f"flags file size      : {size} bytes ({N} entries)")
print(f"browser alive @18s   : {alive}")
print(f"processes captured   : {len(lines)}  (renderers={renderers})")
print(f"EdgeProbeFeat tokens : {leaked}  (0 == built-in merge skipped by cap)")
print(f"--enable-features in children: {len(ef_vals)} -> {[v[:60] for v in ef_vals[:3]]}")
print(f"stderr contains cap warning  : {warn}  (stderr bytes={len(err)})")
if err.strip():
    print("--- stderr head ---")
    print("\n".join(err.splitlines()[:12]))

ok = alive and renderers >= 1 and leaked == 0
print("RESULT:", "PASS - D39 cap effective" if ok else "CHECK - see above")
sys.exit(0 if ok else 1)
