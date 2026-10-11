#!/usr/bin/env python3
"""Minimal source verification for win_scripts/, pak_src/, benchmark/ and infra/.

Checks:
  1. Python syntax check (py_compile) for every .py under win_scripts/
     (excluding win_scripts/old/ and __pycache__).
  2. Presence check for the key build pipeline scripts.
  3. Presence check for all pak_src/ C/H sources.
  4. Optional: gcc -fsyntax-only on pak_src/*.c when a compiler is available,
     Windows only (reported as SKIPPED on non-Windows platforms, since pak_src
     has an unguarded <windows.h> include, and when no compiler is available).
  5. PowerShell lint for every tracked .ps1 (Windows only, SKIPPED elsewhere):
       - files containing non-ASCII text must be UTF-8 *with BOM* (AGENTS.md rule,
         defect D38: PowerShell 5.1 otherwise reads them as GBK and fails to parse);
       - `param(...)` must be the first statement of the script — statements before
         it make PowerShell treat `param` as a command name, the whole parameter
         block dies, and the documented override switches (-OutDir/-ChromeExe) are
         silently ignored while the script still exits 0 (defect D83);
       - a real AST parse via [System.Management.Automation.Language.Parser].
         PSParser::Tokenize is NOT enough: it accepts a misplaced param block
         (defect D84 — the check itself must be falsifiable, so this is covered by
         the negative controls documented in docs/tasks/bug-review-cycle3-report.md).

Exit code 0 = PASS, 1 = FAIL. Usage: python3 win_scripts/verify_sources.py
"""

import io
import os
import platform
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIN_SCRIPTS = REPO_ROOT / "win_scripts"
PAK_SRC = REPO_ROOT / "pak_src"

# Directories that are vendored/generated and must not be linted as our code.
PS_SKIP_DIRS = {".git", "depot_tools", "third_party", "node_modules", "__pycache__",
                "old", "out"}

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
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            failures.append((c_file.name, proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "unknown"))
    if failures:
        return "failed", "; ".join(f"{n}: {e}" for n, e in failures)
    return "passed", f"{checked} file(s) syntax-checked with {Path(gcc).name}"


def collect_powershell_files():
    """Every tracked-ish .ps1 in the repo, minus vendored/generated dirs.

    `.cycleN/` 也排除：按 AGENTS.md 约定那是每轮 bug-review 的**一次性取证脚本与证据**、
    整目录 gitignore（同 `.cycle4/`）。它们会刻意包含"坏写法"来做 Red 验证
    （例如 D137 的 regex_test.ps1 同时写了错误的 `\\|` 与正确的 `\\\\|` 以证明差异），
    把它们纳入源码门禁会让门禁在自己的取证语料上失败。
    """
    out = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in PS_SKIP_DIRS and not d.startswith(".cycle")]
        for f in filenames:
            if f.lower().endswith(".ps1"):
                out.append(Path(dirpath) / f)
    return sorted(out)


def _first_statement(lines):
    """Return (lineno, text) of the first non-comment, non-blank line."""
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        return i, s
    return 0, ""


def check_powershell_static():
    """BOM rule + param-position rule. Returns (checked, failures)."""
    failures = []
    files = collect_powershell_files()
    for p in files:
        rel = p.relative_to(REPO_ROOT)
        raw = p.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            failures.append((rel, "not valid UTF-8: %s" % exc))
            continue
        if not has_bom and any(ord(c) > 127 for c in text):
            failures.append((rel, "contains non-ASCII but has no UTF-8 BOM "
                                  "(PowerShell 5.1 reads it as GBK and fails to "
                                  "parse - see AGENTS.md / defect D38)"))
        lines = text.splitlines()
        first_ln, first_txt = _first_statement(lines)
        # 只判**顶层** param：脚本级 param 块按约定顶格写，而函数体内的 param 是
        # 合法的（函数自己的参数块，通常缩进 4 空格）。用 strip() 会把后者也抓进来，
        # 造成对合法代码的假阳性——假阳性的代价是"人们开始关掉这条检查"。
        param_ln = 0
        for i, ln in enumerate(lines, 1):
            low = ln.lower()
            if low.startswith("param(") or low == "param":
                param_ln = i
                break
        if param_ln and first_ln and param_ln > first_ln:
            failures.append((rel, "param(...) at line %d is preceded by statement "
                                  "%r (line %d): PowerShell then treats `param` as a "
                                  "command name, the parameter block is discarded and "
                                  "documented overrides are silently ignored while the "
                                  "script still exits 0 (defect D83)"
                                  % (param_ln, first_txt[:60], first_ln)))
        # D137 回归闸：M151 回滚树护栏的正则曾写成 chromium-src(\|$)。那里的 \| 是
        # **转义竖线**（匹配字面量 "|"），任何真实路径都不含它，于是这条护栏在 9 个脚本
        # 10 处从未触发过——本机恰好有两棵树，正是它要防的场景。正确写法是 (\\|$)。
        # 只判代码行：bench_memory.ps1 的注释里刻意引用了错误写法来解释这个坑。
        for i, ln in enumerate(lines, 1):
            if ln.lstrip().startswith("#"):
                continue
            if "chromium-src(\\|$)" in ln:
                failures.append((rel, "line %d uses the dead M151-tree guard regex "
                                      "chromium-src(\\|$): '\\|' is an escaped pipe so it "
                                      "matches a literal '|' and never a real path; use "
                                      "chromium-src(\\\\|$) instead (defect D137)" % i))
    return len(files), failures


_PS_LINT_SCRIPT = r"""
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$ErrorActionPreference = 'Stop'
$listFile = $args[0]
$paths = @(Get-Content -LiteralPath $listFile | Where-Object { $_.Trim() -ne '' })
# 量具必须能被证伪：输入为空绝不能报 OK（第3周期缺陷 D66/D84 同一类假绿）。
if ($paths.Count -eq 0) { Write-Host 'PSLINT|EMPTY_INPUT'; exit 1 }
$bad = 0
foreach ($f in $paths) {
  $tok = $null; $errs = $null
  try {
    $null = [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$tok, [ref]$errs)
  } catch {
    Write-Host ("PSLINT|{0}|0|{1}" -f $f, $_.Exception.Message); $bad++; continue
  }
  if ($errs -and $errs.Count -gt 0) {
    foreach ($e in $errs) {
      Write-Host ("PSLINT|{0}|{1}|{2}" -f $f, $e.Extent.StartLineNumber, $e.Message)
    }
    $bad += $errs.Count
  }
}
Write-Host ("PSLINT|CHECKED={0}|ERRORS={1}" -f $paths.Count, $bad)
if ($bad -gt 0) { exit 1 }
exit 0
"""


def check_powershell_ast_parse():
    """AST-parse every .ps1 with PowerShell itself. Returns (status, detail)."""
    if platform.system() != "Windows":
        return "skipped", "non-Windows platform (no PowerShell lint)"
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return "skipped", "powershell.exe not found"
    files = collect_powershell_files()
    if not files:
        return "failed", "no .ps1 files discovered (scanner broken, not a clean pass)"
    tmpdir = tempfile.mkdtemp(prefix="verify_ps_")
    try:
        lint_path = os.path.join(tmpdir, "pslint.ps1")
        list_path = os.path.join(tmpdir, "files.txt")
        with io.open(lint_path, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + _PS_LINT_SCRIPT.encode("utf-8"))
        with io.open(list_path, "w", encoding="utf-8") as fh:
            for f in files:
                fh.write(str(f) + "\n")
        proc = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", lint_path, list_path],
            capture_output=True, timeout=600)
        out = proc.stdout.decode("utf-8", "replace")
        errs = proc.stderr.decode("utf-8", "replace")
        if proc.returncode != 0:
            bad = [ln for ln in out.splitlines() if ln.startswith("PSLINT|")
                   and not ln.startswith("PSLINT|CHECKED")]
            detail = "; ".join(bad[:6]) if bad else ("runner exit=%d %s"
                                                     % (proc.returncode, errs.strip()[:200]))
            return "failed", detail
        checked = 0
        for ln in out.splitlines():
            if ln.startswith("PSLINT|CHECKED="):
                try:
                    checked = int(ln.split("CHECKED=")[1].split("|")[0])
                except ValueError:
                    checked = 0
        if checked == 0:
            return "failed", "PowerShell lint reported CHECKED=0 (no file was parsed)"
        return "passed", "%d .ps1 file(s) AST-parsed clean" % checked
    except subprocess.TimeoutExpired:
        return "failed", "PowerShell lint timed out after 600s"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

    checked, ps_failures = check_powershell_static()
    if ps_failures:
        ok = False
        print(f"[FAIL] PowerShell static lint: "
              f"{len(ps_failures)}/{checked} file(s) flagged")
        for rel, msg in ps_failures:
            print(f"       - {rel}: {msg}")
    else:
        print(f"[PASS] PowerShell static lint: {checked} .ps1 file(s) "
              f"(UTF-8 BOM rule + param-position rule) OK")

    status, detail = check_powershell_ast_parse()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] PowerShell AST parse: {detail}")
    if status == "failed":
        ok = False

    print()
    print("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
