#!/usr/bin/env python3
"""fuzz_mutate.py - mutation fuzzer for the ASan-instrumented pak tool.

Round-1 deep test: random bit-flips + truncation on a real v5 pak and its
pak_index.ini. Any ASan error (exit 86), access violation (huge NTSTATUS),
or timeout is reported as a crash candidate and the offending corpus file is
preserved.
"""
import os
import random
import subprocess
import sys

WORK = r"d:\wxmuma\thorium\.bugreview"
PAK = os.path.join(WORK, "pak_fixed.exe")
SRC_PAK = r"D:\wxmuma\chromium-src\src\out\mcloud\chrome_100_percent.pak"
SRC_IDX = None  # set after unpack dir exists (rt3/pak_index.ini)
OUT = os.path.join(WORK, "fuzz_out")
os.makedirs(OUT, exist_ok=True)
os.environ["ASAN_OPTIONS"] = "exitcode=86:abort_on_error=0"
# ASan dynamic runtime must be on PATH or every run fails with STATUS_DLL_NOT_FOUND
os.environ["PATH"] = (
    r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64"
    + ";" + os.environ.get("PATH", ""))

random.seed(20261008)
N_UNPACK = int(sys.argv[1]) if len(sys.argv) > 1 else 150
N_PACK = int(sys.argv[2]) if len(sys.argv) > 2 else 80

base = open(SRC_PAK, "rb").read()

# locate a valid unpacked dir for pack-side fuzzing (verify_fixes produced rt3)
rt = os.path.join(WORK, "rt3", "pak_index.ini")
have_pack = os.path.exists(rt)

CRASH = lambda rc: rc == 86 or rc < 0 or rc >= 3221225472
UNPACK_OK = {0, 1, 2, 3, 4, 32, 33}
PACK_OK = {0, 5, 6, 7, 8, 9, 32, 33}

def mutate(buf, max_flips=6):
    b = bytearray(buf)
    for _ in range(random.randint(1, max_flips)):
        b[random.randrange(len(b))] = random.randrange(256)
    if random.random() < 0.3:
        b = b[: random.randrange(1, len(b))]
    return bytes(b)

bad = []

for i in range(N_UNPACK):
    p = os.path.join(OUT, "fz.pak")
    with open(p, "wb") as f:
        f.write(mutate(base))
    try:
        r = subprocess.run([PAK, "-u", p, os.path.join(OUT, "o")],
                           capture_output=True, timeout=60)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = -999
    if CRASH(rc) or rc not in UNPACK_OK:  # unexpected internal codes too
        bad.append(("unpack", i, rc, p))
        os.replace(p, os.path.join(OUT, f"repro_unpack_{i}_{rc}.pak"))
        print(f"[CRASH] unpack iter={i} rc={rc}")
        if len(bad) >= 3:
            break
    else:
        # ok: handled paths are 0..4
        pass

if have_pack:
    idx = open(rt, "rb").read()
    for i in range(N_PACK):
        p = os.path.join(OUT, "fz_index.ini")
        with open(p, "wb") as f:
            f.write(mutate(idx, max_flips=10))
        try:
            r = subprocess.run([PAK, "-p", p, os.path.join(OUT, "re.pak")],
                               capture_output=True, timeout=60)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -999
        if CRASH(rc) or rc not in PACK_OK:
            bad.append(("pack", i, rc, p))
            os.replace(p, os.path.join(OUT, f"repro_pack_{i}_{rc}.ini"))
            print(f"[CRASH] pack iter={i} rc={rc}")
            if len(bad) >= 3:
                break

print(f"DONE unpack={N_UNPACK} pack={N_PACK if have_pack else 0} crashes={len(bad)}")
for kind, i, rc, path in bad:
    err = ""
    print("  ", kind, i, rc, path)
