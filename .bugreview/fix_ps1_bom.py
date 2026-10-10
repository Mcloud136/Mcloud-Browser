#!/usr/bin/env python3
"""fix_ps1_bom.py - ensure PS 5.1 parses Chinese-comment .ps1 files:
add UTF-8 BOM to any .ps1 containing non-ASCII bytes without one."""
from pathlib import Path

roots = [Path(r"D:\wxmuma\thorium\benchmark"), Path(r"D:\wxmuma\thorium\win_scripts"),
         Path(r"D:\wxmuma\thorium\.bugreview")]
fixed = []
for root in roots:
    for p in sorted(root.rglob("*.ps1")):
        data = p.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            print("WARN not utf8:", p)
            continue
        if any(ord(c) > 127 for c in text):
            p.write_bytes(b"\xef\xbb\xbf" + data)
            fixed.append(str(p))
print("BOM added to:", len(fixed))
for f in fixed:
    print("  ", f)
