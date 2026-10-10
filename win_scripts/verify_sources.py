#!/usr/bin/env python3
"""Minimal source verification for win_scripts/ and pak_src/.

Checks:
  1. Python syntax check (py_compile) for every .py under win_scripts/
     (excluding win_scripts/old/ and __pycache__).
  2. Presence check for the key build pipeline scripts.
  3. Presence check for all pak_src/ C/H sources.
  4. Optional: gcc -fsyntax-only on pak_src/*.c when a compiler is available,
     Windows only (reported as SKIPPED on non-Windows platforms, since pak_src
     has an unguarded <windows.h> include, and when no compiler is available).

Exit code 0 = PASS, 1 = FAIL. Usage: python3 win_scripts/verify_sources.py
"""

import platform
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIN_SCRIPTS = REPO_ROOT / "win_scripts"
PAK_SRC = REPO_ROOT / "pak_src"

# Key scripts that the build pipeline depends on.
KEY_SCRIPTS = [
    "setup.py",
    "copy_essentials.py",
    "apply_mcloud_source_defaults.py",
    "inject_flags_loader.py",
    "apply_avx2_baseline.py",
    "append_polly_configs.py",
    "apply_polly_wiring.py",
    "apply_installer_payload.py",
    "build_win.py",
    "deploy_mcloud.py",
    "version.py",
]

# Expected pak_src sources (pack/unpack tool).
PAK_SRC_FILES = [
    "main.c", "main.h", "pak_defs.h",
    "pak_file.c", "pak_file.h",
    "pak_file_io.c", "pak_file_io.h",
    "pak_get_file_type.c", "pak_get_file_type.h",
    "pak_header.c", "pak_header.h",
    "pak_pack.c", "pak_pack.h",
    "commandlinetoargva.h",
]


def check_python_syntax():
    """Syntax-check every .py under win_scripts/ (excluding old/)."""
    failures = []
    checked = 0
    for py_file in sorted(WIN_SCRIPTS.rglob("*.py")):
        rel = py_file.relative_to(REPO_ROOT)
        if rel.parts[1] == "old" or "__pycache__" in rel.parts:
            continue
        checked += 1
        try:
            py_compile.compile(str(py_file), doraise=True, quiet=2)
        except py_compile.PyCompileError as exc:
            failures.append((rel, str(exc.msg if exc.msg else exc)))
    return checked, failures


def check_key_scripts():
    """Verify the key pipeline scripts exist."""
    missing = [name for name in KEY_SCRIPTS if not (WIN_SCRIPTS / name).is_file()]
    return missing


def check_pak_sources():
    """Verify all pak_src sources exist."""
    missing = [name for name in PAK_SRC_FILES if not (PAK_SRC / name).is_file()]
    return missing


def check_pak_syntax():
    """Optional gcc -fsyntax-only pass on pak_src/*.c. Returns (status, detail)."""
    if platform.system() != "Windows":
        # pak_src is Windows-oriented: main.h includes <windows.h> unguarded,
        # so syntax-checking on Linux/macOS would always fail.
        return "skipped", "non-Windows platform (pak_src has unguarded windows.h in main.h)"
    gcc = shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
    if not gcc:
        return "skipped", "no C compiler found"
    checked = 0
    failures = []
    for c_file in sorted(PAK_SRC.glob("*.c")):
        checked += 1
        proc = subprocess.run(
            [gcc, "-fsyntax-only", "-I", str(PAK_SRC), str(c_file)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            failures.append((c_file.name, proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "unknown"))
    if failures:
        return "failed", "; ".join(f"{n}: {e}" for n, e in failures)
    return "passed", f"{checked} file(s) syntax-checked with {Path(gcc).name}"


def main():
    ok = True

    checked, py_failures = check_python_syntax()
    if py_failures:
        ok = False
        print(f"[FAIL] Python syntax: {len(py_failures)}/{checked} file(s) failed")
        for rel, msg in py_failures:
            print(f"       - {rel}: {msg}")
    else:
        print(f"[PASS] Python syntax: {checked} file(s) under win_scripts/ OK")

    missing = check_key_scripts()
    if missing:
        ok = False
        print(f"[FAIL] Key scripts missing: {', '.join(missing)}")
    else:
        print(f"[PASS] Key scripts: {len(KEY_SCRIPTS)}/{len(KEY_SCRIPTS)} present")

    missing = check_pak_sources()
    if missing:
        ok = False
        print(f"[FAIL] pak_src files missing: {', '.join(missing)}")
    else:
        print(f"[PASS] pak_src sources: {len(PAK_SRC_FILES)}/{len(PAK_SRC_FILES)} present")

    status, detail = check_pak_syntax()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] pak_src C syntax: {detail}")
    if status == "failed":
        ok = False

    print()
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
