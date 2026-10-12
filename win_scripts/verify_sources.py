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
  5. pak_src_fixed/: presence check plus a real compile + round-trip gate
     (defects D190/D191/D193, 2026-10-12). Runs wherever a C compiler exists:
     gcc/clang on Linux/macOS, cl on an MSVC-initialized Windows shell. Without
     it the check reports SKIPPED with the reason — never a silent pass.
  6. PowerShell lint for every tracked .ps1 (Windows only, SKIPPED elsewhere):
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

import contextlib
import io
import os
import platform
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 控制台代码页（本机 cp936）装不下的字符必须被替换而不是抛 UnicodeEncodeError：
# 实测过一次这样的崩溃把已缓冲的结论整段吞掉，rc 还非 0，看起来像门禁在响，实际是
# 门禁自己被输出打死（第7周期 r11）。
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(errors="replace")


REPO_ROOT = Path(__file__).resolve().parent.parent
WIN_SCRIPTS = REPO_ROOT / "win_scripts"
PAK_SRC = REPO_ROOT / "pak_src"
PAK_FIXED = REPO_ROOT / "pak_src_fixed"

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


def check_flags_lint():
    """Run .bugreview/flags_lint.py on mcloud_flags.txt.

    Gate added after defect D59 (2026-10-12): the startup flag loader does not
    strip trailing comments, so a line like
        --enable-features=Foo   # note
    makes the whole enable-features string unparsable and silently disables
    *every* performance flag. Build, install and every other gate stay green,
    so nothing but this check catches it.
    Returns (status, detail); 'skipped' when the linter is absent.
    """
    linter = REPO_ROOT / ".bugreview" / "flags_lint.py"
    flags = REPO_ROOT / "mcloud_flags.txt"
    if not linter.is_file():
        return "skipped", "flags_lint.py not present"
    if not flags.is_file():
        return "failed", "mcloud_flags.txt not found at repo root"
    proc = subprocess.run([sys.executable, str(linter), "--file", str(flags)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode == 0:
        return "passed", "no trailing comments, switch names well-formed"
    detail = "see flags_lint output"
    for line in (proc.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("[FATAL]") or s.startswith("L"):
            detail = s
            break
    return "failed", detail


PAK_FIXED_FILES = [
    "pak.c", "Makefile", "run_test.sh", "build_and_test.bat",
    os.path.join("t_in", "pak_index.ini"),
    os.path.join("t_in", "1.html"),
    os.path.join("t_in", "2.png"),
]


def check_pak_fixed_sources():
    """pak_src_fixed/ 必须带齐源码 + 两套构建入口 + 测试样本（缺陷 D194）。"""
    return [name for name in PAK_FIXED_FILES if not (PAK_FIXED / name).is_file()]


def _find_c_compiler():
    """返回 (编译器路径, 'posix'|'msvc')；找不到返回 (None, None)。"""
    for name in ("cc", "gcc", "clang"):
        path = shutil.which(name)
        if path:
            return path, "posix"
    if platform.system() == "Windows":
        for name in ("cl", "cl.exe"):
            path = shutil.which(name)
            if path:
                return path, "msvc"
    return None, None


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def check_pak_roundtrip():
    """编译 pak_src_fixed/pak.c 并跑真往返判据（D190/D191/D193）。

    没有编译器时明确 SKIPPED——绝不把"没测"报成"通过"（本仓假绿族的老毛病）。
    """
    cc, kind = _find_c_compiler()
    if not cc:
        return "skipped", ("no C compiler on PATH (Linux CI runs this with gcc; on "
                           "Windows the MSVC environment must be initialised first)")
    tmpdir = tempfile.mkdtemp(prefix="pak-roundtrip-")
    try:
        src = str(PAK_FIXED / "pak.c")
        exe = os.path.join(tmpdir, "pak.exe" if kind == "msvc" else "pak")
        if kind == "msvc":
            flags = ["/nologo", "/W4", "/std:c11", "/utf-8",
                     "/D_CRT_SECURE_NO_WARNINGS",
                     "/Fo" + tmpdir + os.sep, "/Fe" + exe]
        else:
            flags = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-O2", "-o", exe]
        proc = subprocess.run([cc] + flags + [src], cwd=tmpdir,
                              capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            first = (proc.stderr or proc.stdout or "").strip().splitlines()
            return "failed", "compile failed: %s" % (first[0] if first else "no output")
        warn = sum(1 for line in (proc.stdout + proc.stderr).splitlines()
                   if "warning" in line)

        def run_pak(*args):
            return subprocess.run([exe] + list(args), cwd=tmpdir,
                                  capture_output=True, text=True, timeout=300)

        work = os.path.join(tmpdir, "in")
        shutil.copytree(str(PAK_FIXED / "t_in"), work)
        ini = os.path.join("in", "pak_index.ini")
        a, b = os.path.join(tmpdir, "a.pak"), os.path.join(tmpdir, "b.pak")
        for out in (a, b):
            if run_pak("-p", ini, out).returncode != 0:
                return "failed", "-p on the baseline fixture returned non-zero"
        # D190：同一输入两次打包必须字节一致，且 v5 头部的 3 个 padding 必须为 0
        if _read(a) != _read(b):
            return "failed", "D190 regression: packing the same input twice gave different bytes"
        head = _read(a)[:12]
        if head[0:4] == b"\x05\x00\x00\x00" and head[5:8] != b"\x00\x00\x00":
            return "failed", "D190 regression: v5 header padding not zero (%s)" % head[5:8].hex()

        out_dir = os.path.join(tmpdir, "un")
        if run_pak("-u", "a.pak", "un").returncode != 0:
            return "failed", "-u returned non-zero"
        for name in ("1.html", "2.png"):
            src_f = os.path.join(work, name)
            out_f = os.path.join(out_dir, name)
            if not os.path.isfile(out_f):
                return "failed", "unpacked output missing %s" % name
            if _read(src_f) != _read(out_f):
                return "failed", "%s changed across the round trip" % name

        # D193：version=4 + [Alias] 必须被拒绝，而不是静默丢掉别名表
        v4 = os.path.join(tmpdir, "v4")
        shutil.copytree(str(PAK_FIXED / "t_in"), v4)
        with open(os.path.join(v4, "pak_index.ini"), "w", newline="\n") as f:
            f.write("[Global]\nversion=4\nencoding=0\n\n[Resources]\n"
                    "1=1.html\n2=2.png\n\n[Alias]\n10=1\n")
        res = run_pak("-p", os.path.join("v4", "pak_index.ini"), "v4.pak")
        if res.returncode == 0 or os.path.exists(os.path.join(tmpdir, "v4.pak")):
            return "failed", "D193 regression: version=4 with [Alias] was silently accepted"

        # 畸形输入必须非 0
        truncated = _read(os.path.join(tmpdir, "a.pak"))[:8]
        with open(os.path.join(tmpdir, "trunc.pak"), "wb") as f:
            f.write(truncated)
        if run_pak("-u", "trunc.pak", "bad").returncode == 0:
            return "failed", "truncated .pak was treated as success"

        return "passed", ("%s compile + round-trip + malformed-input checks all passed "
                          "(%d warning(s) during compile)" % (Path(cc).name, warn))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def check_pak_asan():
    """ASan + LeakSanitizer 跑一遍 pak_src_fixed（仅 POSIX 侧有意义）。

    实测（第7周期，MSVC 14.51 / clang 21）：Windows 上设 ASAN_OPTIONS=detect_leaks=1
    会直接以 "detect_leaks is not supported on this platform" 退出——本机 ASan 只能证
    越界，**不能**证无泄漏。因此泄漏判据只在有 gcc/clang 的 POSIX 侧执行；Windows 上
    一律 SKIPPED 并写明原因，绝不把"平台不具备该能力"报成通过。
    """
    cc, kind = _find_c_compiler()
    if not cc:
        return "skipped", "no C compiler on PATH"
    if kind != "posix":
        return "skipped", ("MSVC ASan has no LeakSanitizer (measured: 'detect_leaks is "
                           "not supported on this platform'); the overflow checks run "
                           "on Windows via .bugreview/pak_fixed_verify.py")
    tmpdir = tempfile.mkdtemp(prefix="pak-asan-")
    try:
        exe = os.path.join(tmpdir, "pak")
        proc = subprocess.run(
            [cc, "-std=c11", "-g", "-fsanitize=address", "-fno-omit-frame-pointer",
             "-o", exe, str(PAK_FIXED / "pak.c")],
            cwd=tmpdir, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0 or not os.path.exists(exe):
            first = (proc.stderr or proc.stdout or "").strip().splitlines()
            return "skipped", ("ASan runtime unavailable, cannot build with "
                               "-fsanitize=address: %s"
                               % (first[0] if first else "no output"))
        work = os.path.join(tmpdir, "in")
        shutil.copytree(str(PAK_FIXED / "t_in"), work)

        def run_pak(*args):
            return subprocess.run([exe] + list(args), cwd=tmpdir,
                                  capture_output=True, text=True, timeout=600)

        combined = ""
        for args in (("-p", os.path.join("in", "pak_index.ini"), "a.pak"),
                     ("-u", "a.pak", "un")):
            res = run_pak(*args)
            combined += res.stdout + res.stderr
            if res.returncode != 0 and "AddressSanitizer" not in combined:
                return "failed", "asan build returned non-zero on a valid case"
        if "AddressSanitizer" in combined:
            kind_msg = "leak" if "LeakSanitizer" in combined or "leaked" in combined \
                else "memory error"
            for line in combined.splitlines():
                if "ERROR: AddressSanitizer" in line or "SUMMARY:" in line:
                    return "failed", "%s reported: %s" % (kind_msg, line.strip()[:200])
            return "failed", "%s reported (details truncated)" % kind_msg
        return "passed", "ASan+LSan clean on pack and unpack (no overflow, no leak)"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

    # D59 gate: a trailing '#' comment on a switch line silently kills the whole
    # runtime flag set, so it must be caught here rather than in production.
    status, detail = check_flags_lint()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] mcloud_flags.txt lint: {detail}")
    if status == "failed":
        ok = False

    status, detail = check_pak_syntax()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] pak_src C syntax: {detail}")
    if status == "failed":
        ok = False

    missing = check_pak_fixed_sources()
    if missing:
        ok = False
        print(f"[FAIL] pak_src_fixed files missing: {', '.join(missing)}")
    else:
        print(f"[PASS] pak_src_fixed sources: {len(PAK_FIXED_FILES)}"
              f"/{len(PAK_FIXED_FILES)} present")

    # CI 上"没编译器"不能算通过：GitHub 的 ubuntu runner 必带 cc，所以
    # compile+round-trip 若在 CI 上是 SKIPPED，就说明判据根本没跑，而不是"没问题"。
    # ASan 则只 WARN——runner 上是否装了 libasan 我在这台机器上无法证实，
    # 把一个未验证的前提写成硬失败，只会制造一条没人敢信的红。
    on_ci = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"

    status, detail = check_pak_roundtrip()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] pak_src_fixed compile+round-trip: {detail}")
    if status == "failed":
        ok = False
    elif status == "skipped" and on_ci:
        ok = False
        print("[FAIL] CI skipped pak_src_fixed compile+round-trip => the criteria never "
              "ran, which is not a pass (an ubuntu runner is expected to provide cc; if it "
              "genuinely does not, fix the runner instead of loosening this gate)")

    status, detail = check_pak_asan()
    label = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}[status]
    print(f"[{label}] pak_src_fixed ASan+LSan: {detail}")
    if status == "failed":
        ok = False
    elif status == "skipped" and on_ci:
        print("[WARN] no ASan runtime on the runner => this round has no "
              "overflow/leak evidence (not a failure, but do not call it verified)")

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
