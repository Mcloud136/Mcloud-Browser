# 一次性工具：向 M151 上游版 build/config/win/BUILD.gn 应用 AVX2+FMA3 基线
# （替换上游的 -msse3）。依据：技术规范 1.5 硬件基线。
import io
import sys

p = r"D:\wxmuma\chromium-src\src\build\config\win\BUILD.gn"
s = io.open(p, encoding="utf-8").read()

if "-mavx2" in s:
    print("AVX2 baseline already present, nothing to do")
    sys.exit(0)

old = '''    if (current_cpu == "x86" || current_cpu == "x64") {
      cflags += [ "-msse3" ]
    }'''
new = '''    # MCloud Browser: AVX2 + FMA3 baseline for Windows x64 builds
    # (spec 1.5 hardware baseline; Clang supports targeting any Intel
    # microarchitecture. MSVC only supports a subset of architectures.)
    if (current_cpu == "x86" || current_cpu == "x64") {
      cflags += [ "-mavx2", "-mfma", "-mf16c", "-mlzcnt", "-mbmi", "-mbmi2" ]
    }'''

assert old in s, "anchor not found"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("AVX2 baseline applied")
