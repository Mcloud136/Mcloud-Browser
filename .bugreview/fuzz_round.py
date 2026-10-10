#!/usr/bin/env python3
"""fuzz_round.py - parameterized mutation fuzz for one review round.
Usage: python fuzz_round.py <round>  (unpacks 300, packs 150; seed derived from round)
Exit 0 = clean, 1 = crashes found (repro files preserved in fuzz_out/).
"""
import os
import random
import subprocess
import sys

WORK = r"d:\wxmuma\thorium\.bugreview"
PAK = os.path.join(WORK, "pak_fixed.exe")
SRC_PAK = r"D:\wxmuma\chromium-src\src\out\mcloud\chrome_100_percent.pak"
RT_IDX = os.path.join(WORK, "rt3", "pak_index.ini")
OUT = os.path.join(WORK, "fuzz_out")
os.makedirs(OUT, exist_ok=True)
os.environ["ASAN_OPTIONS"] = "exitcode=86:abort_on_error=0"
os.environ["PATH"] = (
    r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64"
    + ";" + os.environ.get("PATH", ""))

rnd_no = int(sys.argv[1]) if len(sys.argv) > 1 else 1
random.seed(20261008 + rnd_no * 1000)
base = open(SRC_PAK, "rb").read()
have_pack = os.path.exists(RT_IDX)
UNPACK_OK = {0, 1, 2, 3, 4, 32, 33}
PACK_OK = {0, 5, 6, 7, 8, 9, 32, 33}

def mutate(buf, flips):
    b = bytearray(buf)
    for _ in range(random.randint(1, flips)):
        b[random.randrange(len(b))] = random.randrange(256)
    if random.random() < 0.3:
        b = b[: random.randrange(1, len(b))]
    return bytes(b)

bad = 0
for i in range(300):
    p = os.path.join(OUT, "fr.pak")
    open(p, "wb").write(mutate(base, 6))
    try:
        rc = subprocess.run([PAK, "-u", p, os.path.join(OUT, "o")],
                            capture_output=True, timeout=60).returncode
    except subprocess.TimeoutExpired:
        rc = -999
    if rc not in UNPACK_OK:
        bad += 1
        os.replace(p, os.path.join(OUT, f"r{rnd_no}_unpack_{i}_{rc}.pak"))
        print(f"[CRASH] unpack i={i} rc={rc}")
        break

if have_pack:
    idx = open(RT_IDX, "rb").read()
    for i in range(150):
        p = os.path.join(OUT, "fr_index.ini")
        open(p, "wb").write(mutate(idx, 10))
        try:
            rc = subprocess.run([PAK, "-p", p, os.path.join(OUT, "re.pak")],
                                capture_output=True, timeout=60).returncode
        except subprocess.TimeoutExpired:
            rc = -999
        if rc not in PACK_OK:
            bad += 1
            os.replace(p, os.path.join(OUT, f"r{rnd_no}_pack_{i}_{rc}.ini"))
            print(f"[CRASH] pack i={i} rc={rc}")
            break

print(f"round {rnd_no}: fuzz clean={450 - bad} bad={bad}")
sys.exit(1 if bad else 0)
