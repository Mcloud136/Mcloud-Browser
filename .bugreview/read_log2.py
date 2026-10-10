#!/usr/bin/env python3
# read_log2.py - raw printable-ASCII extraction (encoding-agnostic)
import re, sys
data = open(r'd:\wxmuma\thorium\.bugreview\build_v2.log','rb').read()
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
# ASCII runs (utf-16 text interleaved with NUL -> strip NULs first)
clean = data.replace(b'\x00', b'')
runs = re.findall(rb'[\x20-\x7e]{5,}', clean)
out = [r.decode('ascii', 'replace') for r in runs]
key = [s for s in out if re.search(r'FAILED|error|ninja|exit|Siso|siso|build|Traceback|ERROR', s, re.I)]
print("total runs:", len(out), "key:", len(key))
for s in key[:40]:
    print("|", s[:180])
print("=== first 30 runs ===")
for s in out[:30]:
    print(">", s[:180])
print("=== last 30 runs ===")
for s in out[-30:]:
    print(">", s[:180])
