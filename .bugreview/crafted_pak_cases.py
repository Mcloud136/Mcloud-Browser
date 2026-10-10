#!/usr/bin/env python3
"""crafted_pak_cases.py - structured (not random) overflow probes for pak_src.

Random byte flips (fuzz_round.py) almost never produce a *structurally valid but
hostile* pak header, which is exactly the input class that used to trip the
32-bit arithmetic in the unpack/pack paths (defects D5/D9/D12/D13/D14/D15).
Each case below is built byte-exact to reach a specific arithmetic decision.

Pass criteria per case: the ASan-instrumented tool must exit with a graceful
error code, never an ASan report (86) and never an access violation.
"""
import os
import struct
import subprocess
import sys

WORK = r"d:\wxmuma\thorium\.bugreview"
PAK = os.path.join(WORK, "pak_fixed.exe")
OUT = os.path.join(WORK, "crafted_out")
os.makedirs(OUT, exist_ok=True)

# MSVC ASan reports with ASAN_OPTIONS=exitcode=86; 0xC0000005 = access violation.
CRASH_CODES = {86, 0xC0000005, 3221225477, 0xC0000409, 3221225985,
               0xC0000374, 3221226092, -999}  # -999 = timeout (hang)
GRACEFUL = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 32, 33, 34, 111}

os.environ["ASAN_OPTIONS"] = "exitcode=86:abort_on_error=0"
os.environ["PATH"] = (
    r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools"
    r"\MSVC\14.51.36231\bin\Hostx64\x64;" + os.environ.get("PATH", ""))

V5 = struct.Struct("<IB3xHH")   # version, encoding, pad, res_count, alias_count
V4 = struct.Struct("<IBI")      # version, res_count(u32)?? -> see note below
ENTRY = struct.Struct("<HI")    # resource_id(u16), offset(u32)
ALIAS = struct.Struct("<HH")    # resource_id(u16), entry_index(u16)


def v5_header(res=0, alias=0, version=5, enc=0):
    return V5.pack(version, enc, res, alias)


def entries(rows):
    return b"".join(ENTRY.pack(rid, off) for rid, off in rows)


def aliases(rows):
    return b"".join(ALIAS.pack(rid, idx) for rid, idx in rows)


CASES = []


def case(name, blob):
    CASES.append((name, blob))


# U1: header claims 65535 resources + 65535 aliases in a 12-byte file.
#     Table range check must reject before any calloc(entry*count) is used.
case("U1_max_counts_tiny_file", v5_header(0xFFFF, 0xFFFF))

# U2: zero resources but one alias (alias table read + entry_index lookup path).
case("U2_alias_without_resources",
     v5_header(0, 1) + b"\x00\x00\x00\x00" + aliases([(1, 0)]))

# U3: alias entry_index points past the entry table.
case("U3_alias_index_out_of_range",
     v5_header(1, 1) + entries([(0, 12)]) + b"data" + aliases([(9, 5)]))

# U4: last entry offset = 0xFFFFFFFF (u32 max) with real data of 4 bytes:
#     size computed as (next_offset - offset) wraps to a huge/negative value.
case("U4_offset_u32_max",
     v5_header(2, 0) + entries([(0, 12), (1, 0xFFFFFFFF)]) + b"data")

# U5: non-monotonic offsets (offset decreases) -> must be rejected, and must not
#     produce a negative->huge memcpy length.
case("U5_nonmonotonic",
     v5_header(3, 0) + entries([(0, 12), (1, 40), (2, 20)]) + b"x" * 64)

# U6: identical offsets (zero-length resource) -> legal in real paks, must not
#     under-allocate.
case("U6_identical_offsets",
     v5_header(2, 0) + entries([(0, 12), (1, 12)]) + b"tail-data")

# U7: declared resource range extends past EOF by one byte.
case("U7_off_by_one_past_eof",
     v5_header(1, 0) + entries([(0, 12)]) + b"abc")

# U8: truncated header (5 bytes: version readable, counts missing).
case("U8_truncated_header", b"\x05\x00\x00\x00\x00")

# U9: version 6 with v5-sized header (unknown version path).
case("U9_unknown_version", v5_header(1, 0, version=6))

# U10: v4 pak (9-byte header, u32 resource_count) claiming 0xFFFFF0 resources.
case("U10_v4_huge_count", struct.pack("<II", 4, 0xFFFFF0) + b"\x00" + b"\x00" * 8)

# U11: v4 header claiming exactly the maximum u32 count (overflow in
#      (count+1)*PAK_ENTRY_SIZE if computed in 32 bits).
case("U11_v4_count_u32_max", struct.pack("<II", 4, 0xFFFFFFFF) + b"\x00")

# U12: positive control - a structurally correct v5 pak (entry table carries the
#      trailing sentinel entry whose offset marks the end of the last resource)
#      must unpack with rc=0, otherwise the whole unpack suite proves nothing.
#      layout: header(12) + (3+1)*6 entries + 1*4 alias + data @ 40
_body = b"AA" + b"BBBB" + b"CCCCCCCCCC"          # ends at 40+16 = 56
case("U12_positive_control",
     v5_header(3, 1)
     + entries([(0, 40), (1, 42), (2, 46), (0, 56)])   # last = sentinel
     + aliases([(7, 1)])
     + _body)

# ---- pack-direction (index .ini) structured cases ----
# Files referenced by the positive controls are created by the runner below.
PACK_POSITIVE = {}        # tag -> dict(extra files), handled in run_pack

case("I1_id_above_u16",
     b"[Global]\nversion=5\n\n[Resources]\n65536=ok.txt\n")
case("I2_alias_target_missing",
     b"[Global]\nversion=5\n\n[Resources]\n0=ok.txt\n\n[Alias]\n9=40\n")
case("I3_res_count_over_u16",
     b"[Global]\nversion=5\n\n[Resources]\n"
     + "".join(f"{i % 65535}=ok.txt\n" for i in range(70000)).encode())
# 255/256-char names: the parser's %255s capture is width-limited (D2), and the
# composed path (index dir + name) must stay inside PATH_MAX (D10). Both are
# expected to be *refused* when the index path is absolute - the point is that
# refusal is graceful, not that the pack succeeds.
case("I4_name_len_255_boundary",
     b"[Global]\nversion=5\n\n[Resources]\n0=" + b"a" * 255 + b"\n")
case("I5_name_len_256_overflow",
     b"[Global]\nversion=5\n\n[Resources]\n0=" + b"a" * 256 + b"\n")
case("I6_path_beyond_maxpath",
     b"[Global]\nversion=5\n\n[Resources]\n0=" + b"..\\" * 130 + b"ok.txt\n")
case("I7_missing_global_tag", b"[Resources]\n0=ok.txt\n")
case("I8_nonnumeric_id", b"[Global]\nversion=5\n\n[Resources]\nx=ok.txt\n")
case("I9_no_resources_line", b"[Global]\nversion=5\n\n[Resources]\n")
# Positive controls: prove the pack path really works in this harness, so the
# rejections above cannot be "file not found" artifacts.
case("I10_positive_single_resource",
     b"[Global]\nversion=5\n\n[Resources]\n0=ok.txt\n")
case("I11_positive_two_plus_alias",
     b"[Global]\nversion=5\n\n[Resources]\n0=ok.txt\n1=ok2.txt\n\n[Alias]\n9=1\n")
PACK_POSITIVE = {"I10_positive_single_resource", "I11_positive_two_plus_alias"}


def run_unpack(blob, tag):
    p = os.path.join(OUT, f"{tag}.pak")
    with open(p, "wb") as f:
        f.write(blob)
    dst = os.path.join(OUT, tag + "_out")
    try:
        return subprocess.run([PAK, "-u", p, dst], capture_output=True,
                              timeout=60).returncode
    except subprocess.TimeoutExpired:
        return -999


def run_pack(blob, tag):
    d = os.path.join(OUT, tag + "_src")
    os.makedirs(d, exist_ok=True)
    for nm in ("ok.txt", "ok2.txt"):
        with open(os.path.join(d, nm), "wb") as f:
            f.write(b"hello")
    p = os.path.join(d, "index.ini")
    with open(p, "wb") as f:
        f.write(blob)
    out = os.path.join(d, "re.pak")
    cwd = os.getcwd()
    try:
        os.chdir(d)  # index paths are relative to the index file directory
        try:
            return subprocess.run([PAK, "-p", p, out], capture_output=True,
                                  timeout=120).returncode
        except subprocess.TimeoutExpired:
            return -999
    finally:
        os.chdir(cwd)


if not os.path.exists(PAK):
    print("FAIL: " + PAK + " not built (run verify_fixes.ps1 / round gate 2 first)")
    sys.exit(2)

fails = 0
print(f"crafted pak probes: {len(CASES)} cases (ASan build: {os.path.basename(PAK)})")
for name, blob in CASES:
    if name.startswith("I"):
        rc = run_pack(blob, name)
        want_zero = name in PACK_POSITIVE
    else:
        rc = run_unpack(blob, name)
        want_zero = name == "U12_positive_control"
    bad = rc in CRASH_CODES or rc not in GRACEFUL
    if want_zero and rc != 0:
        bad = True          # positive control must actually pack/unpack
    status = "FAIL" if bad else "pass"
    if bad:
        fails += 1
    print(f"  [{status}] {name:32s} rc={rc} (0x{rc & 0xFFFFFFFF:08X})"
          + ("  <- must be 0" if want_zero else ""))

print("")
print("RESULT:", "ALL GRACEFUL" if fails == 0 else f"{fails} case(s) crashed/hung")
sys.exit(1 if fails else 0)
