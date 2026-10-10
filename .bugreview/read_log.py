#!/usr/bin/env python3
# read_log.py - tolerant decode + key-line extraction for build_v2.log
import re
data = open(r'd:\wxmuma\thorium\.bugreview\build_v2.log','rb').read()
print("size:", len(data))
# try utf-16 if mostly nulls
nulls = data.count(0)
if nulls > len(data)//4:
    txt = data.decode('utf-16-le', errors='replace')
else:
    txt = data.decode('utf-8', errors='replace')
txt = txt.replace('\x00','')
lines = [l for l in txt.splitlines() if l.strip()]
print("lines:", len(lines))
pat = re.compile(r'FAILED|error|Error|exit|ninja: |load|build start|build done|warning: Load|Siso|iso', re.I)
print("=== key lines ===")
for l in lines:
    if pat.search(l):
        print(l[:200])
print("=== last 20 lines ===")
for l in lines[-20:]:
    print(l[:200])
