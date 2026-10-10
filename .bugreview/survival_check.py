#!/usr/bin/env python3
"""survival_check.py v3 - feature survival against a Chromium rev tree.

Usage: python survival_check.py <rev> [--json out.json]

Why v3: modern Chromium declares features as `BASE_FEATURE(kFoo, <default>)` with
NO name string literal -- the runtime name is derived from the identifier (drop
the leading 'k'). So evidence must come from DECLARATION sites, not from quoted
strings (a quoted-string sweep silently misses most features) and not from a
bare identifier search (kEarlyData is an extensions enum, not a feature).

Classes:
  OK          k<Name> seen in a feature declaration, or "Name" seen in a
              legacy declaration that carries an explicit name string
  AMBIG       identifier <Name> occurs in the tree but never in a declaration
              -> most likely NOT a feature (dead entry), needs manual read
  DEAD        no evidence at all
Also reports the declaration default (ENABLED/DISABLED_BY_DEFAULT) where readable,
and nearest-neighbour candidates from the declared universe for AMBIG/DEAD.
"""
import difflib
import json
import re
import subprocess
import sys

SRC = r"D:\wxmuma\chromium-src\src"
INVENTORY = r"d:\wxmuma\thorium\.bugreview\flag_inventory.py"
KINDS = "BASE_FEATURE|BASE_DECLARE_FEATURE|DEFINE_FEATURE|UNI_FEATURE|FEATURE"
# git grep uses POSIX ERE: no (?:...), no \s, no \b -- use [[:space:]] instead.
GIT_DECL = "(" + KINDS + ")[[:space:]]*\\([[:space:]]*k[A-Za-z0-9_]+"
PY_DECL = re.compile("(" + KINDS + r")\s*\(\s*(k[A-Za-z0-9_]+)"
                     r"(?:\s*,\s*\"([^\"]+)\")?([^;]{0,220})")

rev = sys.argv[1]
inv = json.loads(subprocess.check_output(
    [sys.executable, INVENTORY], text=True, errors="replace"))
features = list(dict.fromkeys(inv["features_enable"] + inv["features_disable"]))
switches = [s.lstrip("-") for s in inv["plain_switches"] if s.lstrip("-") != "js-flags"]
v8flags = [f.lstrip("-") for f in inv["v8_inner_flags"]]


def gg(args, pathspec=None):
    cmd = ["git", "-C", SRC, "grep", "-I", "-h"] + args + [rev]
    if pathspec:
        cmd += ["--"] + pathspec
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace").stdout


# ---- A: declaration sites (both legacy string-name and modern form) -----
raw = gg(["-A2", "-E", GIT_DECL], pathspec=["*.cc", "*.h", "*.mm", "*.cpp"])
named = {}          # "Name" -> default (legacy explicit-string form)
decl_ids = set()    # every kIdent appearing at a declaration site
id_default = {}
DEFAULT_RE = r"(FEATURE_[A-Z_]+_BY_DEFAULT|feature_default::k[A-Za-z]+|kDefault[A-Za-z]*)"
for blk in re.split(r"(?m)^--$", raw):
    joined = " ".join(ln.strip() for ln in blk.splitlines())
    for m in PY_DECL.finditer(joined):
        ident, name, rest = m.group(2), m.group(3), m.group(4) or ""
        decl_ids.add(ident)
        d = re.search(DEFAULT_RE, rest)
        default = d.group(1) if d else ""
        if default:
            id_default.setdefault(ident, default)
        if name:
            named[name] = default
            if ident not in id_default and default:
                id_default[ident] = default

# ---- C: any occurrence of identifiers / quoted strings (weak evidence) --
weak_ids = set()
out = gg(["-w", "-o", "-E", "|".join(r"k?%s" % re.escape(n) for n in features)])
for ln in out.splitlines():
    for m in re.finditer(r"\bk?[A-Za-z0-9_]+", ln):
        weak_ids.add(m.group(0))
weak_lit = set()
out = gg(["-o", "-E", "|".join('"%s"' % re.escape(n) for n in features)])
for ln in out.splitlines():
    for m in re.finditer(r'"([^"]+)"', ln):
        weak_lit.add(m.group(1))

# ---- D: plain switches (switches are always quoted literals) -----------
sw_out = gg(["-o", "-E", "|".join('"%s"' % re.escape(s) for s in switches)]) if switches else ""
sw_hit = {s: ('"%s"' % s) in sw_out for s in switches}

# ---- E: V8 inner flags (v8/ is a gitlink in the main repo -> report NA) --
v8_note = {f: "v8 是独立仓库(主仓为 gitlink)，须在 src/v8 单独核对" for f in v8flags}

universe = sorted(set(list(named) + [i[1:] if i.startswith("k") else i
                                  for i in decl_ids]))
report = {"rev": rev, "declared_features": len(universe), "features": [],
          "plain_switches": sw_hit, "v8_inner_flags": v8_note,
          "counts": {"feature_lines": inv["feature_lines"]}}
for f in features:
    ident = "k" + f
    declared = ident in decl_ids or f in named
    default = named.get(f, "") or id_default.get(ident, "")
    if declared:
        state = "OK"
    elif ident in weak_ids or f in weak_lit:
        state = "AMBIG"          # occurs, but never at a declaration site
    else:
        state = "DEAD"
    report["features"].append({
        "name": f,
        "action": "enable" if f in inv["features_enable"] else "disable",
        "state": state, "default": default,
        "declared_by_identifier": ident in decl_ids,
        "declared_by_string": f in named,
        "weak_occurrence": ident in weak_ids or f in weak_lit,
        "suggest": difflib.get_close_matches(f, universe, n=5, cutoff=0.5)
                   if state != "OK" else []})
print(json.dumps(report, indent=2, ensure_ascii=False))
if "--json" in sys.argv:
    with open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
