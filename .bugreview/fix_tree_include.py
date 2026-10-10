#!/usr/bin/env python3
# fix_tree_include.py - remove the stale base/file_util.h include the old
# injector added in M151 (header moved to base/files/file_util.h upstream).
import io
p = r"D:\wxmuma\chromium-src\src\chrome\app\chrome_main_delegate.cc"
s = io.open(p, encoding="utf-8").read()
bad = '#include "base/file_util.h"\n'
if bad in s:
    s = s.replace(bad, "", 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("removed stale include: base/file_util.h")
else:
    print("stale include not present, nothing to do")
ok = '#include "base/files/file_util.h"' in s
print("base/files/file_util.h present:", ok)
