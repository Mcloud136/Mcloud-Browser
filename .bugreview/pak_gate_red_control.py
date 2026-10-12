#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""负向对照：证明 verify_sources.check_pak_roundtrip() 会红（第7周期收口轮）。

不改工作树里被跟踪的 pak.c（测试不得改写被测目标）：把整个 pak_src_fixed 复制到
临时目录，在副本上做两处"退回修复前"的删改，再把模块级 PAK_FIXED 指向副本跑门禁。
预期：删掉 memset -> D190 判据红；删掉 v4 别名拒绝 -> D193 判据红。
任何一条没红，就说明那条判据是假的绿灯，不能拿来当证据。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

THOR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(THOR / "win_scripts"))
import verify_sources as V  # noqa: E402

VC = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC"
          r"\Tools\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDKVER = "10.0.26100.0"

MUTATIONS = [
    ("D190", "memset(buf, 0, h->header_size);"),          # 删掉头部清零
    ("D193", "if (h.version == 4 && aliasDeclared > 0) {"),  # 删掉别名拒绝块的开头
]


def mutate(src, needle):
    """D190：把整行换成空操作。D193：从该行起删掉整个 if 块（按花括号配平）。"""
    if needle not in src:
        return None
    if needle.startswith("if ("):
        i = src.index(needle)
        depth, j = 0, i + len(needle) - 1
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        return src[:i] + "/* RED: v4 alias rejection removed */" + src[j + 1:]
    return src.replace(needle, "/* RED: header memset removed */", 1)


def msvc_env():
    e = dict(os.environ)
    e["INCLUDE"] = ";".join([str(VC / "include")] +
                            [str(SDK / "Include" / SDKVER / s)
                             for s in ("ucrt", "um", "shared")])
    e["LIB"] = ";".join([str(VC / "lib" / "x64")] +
                        [str(SDK / "Lib" / SDKVER / s / "x64") for s in ("ucrt", "um")])
    e["PATH"] = str(VC / "bin" / "Hostx64" / "x64") + os.pathsep + e["PATH"]
    return e


def main():
    if not (VC / "bin" / "Hostx64" / "x64" / "cl.exe").is_file():
        print("ENV: 没有 cl.exe")
        return 2
    os.environ.update(msvc_env())
    src = (THOR / "pak_src_fixed" / "pak.c").read_text(encoding="utf-8")
    results = []
    for tag, needle in MUTATIONS:
        tmp = Path(tempfile.mkdtemp(prefix="pakgate-"))
        try:
            for item in ("Makefile", "run_test.sh", "build_and_test.bat"):
                shutil.copy(str(THOR / "pak_src_fixed" / item), str(tmp / item))
            shutil.copytree(str(THOR / "pak_src_fixed" / "t_in"), str(tmp / "t_in"))
            mutated = mutate(src, needle)
            if mutated is None:
                print("FAIL: 源码里找不到 %r，Red 无法构造" % needle)
                return 1
            (tmp / "pak.c").write_text(mutated, encoding="utf-8", newline="")
            V.PAK_FIXED = tmp
            status, detail = V.check_pak_roundtrip()
            red = status == "failed" and ("D190" in detail or "D193" in detail)
            print("%s %-6s -> status=%s detail=%s"
                  % ("[OK]  " if red else "[FAIL]", tag, status, detail))
            results.append(red)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # 反向自检：未变异的源码必须绿
    V.PAK_FIXED = THOR / "pak_src_fixed"
    st, dt = V.check_pak_roundtrip()
    print("%s GREEN  -> status=%s detail=%s" % ("[OK]  " if st == "passed" else "[FAIL]", st, dt))
    results.append(st == "passed")
    if not all(results):
        print("VERDICT: FAIL — 至少一条判据在被人为破坏后仍然通过")
        return 1
    print("VERDICT: PASS — D190/D193 两条判据都能红，且正常源码为绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
