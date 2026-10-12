# -*- coding: utf-8 -*-
"""平台守卫与默认值可达性审计（第7周期，缺陷 D177）。

为什么需要它：survival_check.py 只回答"这个名字在树里声明了吗"，
它既不解析预处理守卫（D142 那两条 `#if BUILDFLAG(IS_POSIX)` / Android-only buildflag
的死声明就是这么漏掉的），也只看声明**同一行**上的默认值
（`kAsyncDns` 的默认值写在 `#if` 块里，于是抽取出 `default == ""`）。
本脚本对 mcloud_flags.txt 里每一条 feature 定位定义处，重建定义所在的预处理条件链，
并按"我们的构建 = Windows / x64 / official"判定：

  ACTIVE      守卫在本构建下成立（无守卫，或守卫含 IS_WIN / 非平台条件待人工判定）
  DEAD        守卫在本构建下必然不成立 ⇒ 声明是死声明，Chromium 静默忽略（D142 同族）
  UNKNOWN     默认值拿不到（写在 #if 块里、宏形态特殊、或跨行未覆盖）

判据设计原则（本仓纪律）：取不到数据一律非 0，不得把"没测到"当成通过。
用法：
    python .bugreview/guard_audit.py                       # 用 CR_DIR（默认 M155 树）
    python .bugreview/guard_audit.py --root D:/path/src    # 指定源码树
    python .bugreview/guard_audit.py --json out.json
退出码：0=全部 ACTIVE 且默认值可读；1=存在 DEAD/UNKNOWN/定位失败。
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feature_decl          # noqa: E402 —— 平台/默认值判定的唯一实现

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FLAGS = os.path.join(REPO, "mcloud_flags.txt")

KIND_DEF = re.compile(r"\b(BASE_FEATURE|UNI_FEATURE|DEFINE_FEATURE|BASE_DECLARE_FEATURE)"
                      r"\s*\(\s*(k[A-Za-z0-9_]+)")
DEFAULT_RE = feature_decl.DEFAULT_RE   # 与 feature_decl 共用，避免两处判定各自漂移
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def features_from_flags(path):
    """返回 [(action, name)]，只取 enable-/disable-features 行（注释行跳过）。"""
    out = []
    with io.open(path, encoding="utf-8", newline="") as fh:
        for raw in fh:
            t = raw.strip()
            if not t or t.startswith("#"):
                continue
            m = re.match(r"--(enable|disable)-features=(.*)$", t)
            if not m:
                continue
            for item in m.group(2).split(","):
                name = item.split(":", 1)[0].strip()
                if name:
                    out.append((m.group(1), name))
    return out


def grep_defs(root, ident, name):
    """在树里找该 feature 的定义行。返回 [(file, lineno, text)]。

    ⚠ 必须按**标识符全等**筛，不能只看"这行有 BASE_FEATURE("：
    `git grep -F kBackForwardCache` 会同时命中 `kBackForwardCacheSize` 等更长名字，
    取首条就会跑到别的文件、把存在的声明报成 NOTFOUND（首版实测踩到）。
    """
    hits = []
    seen = set()
    for p in ([ident] if ident else []) + ['"%s"' % name]:
        r = subprocess.run(["git", "-C", root, "grep", "-n", "-F", p, "--",
                            "*.cc", "*.h", "*.mm"],
                           capture_output=True, text=True, errors="replace")
        for line in (r.stdout or "").splitlines():
            fp, _, rest = line.partition(":")
            ln, _, text = rest.partition(":")
            if not ln.isdigit():
                continue
            key = (fp, ln)
            if key in seen:
                continue
            m = KIND_DEF.search(text)
            if not m:
                continue
            captured = m.group(2)
            if p == '"%s"' % name:
                # 字符串形态：BASE_FEATURE(kFoo, "Name", ...) —— 名字要全等
                if not re.search(r"[\"']%s[\"']" % re.escape(name), text):
                    continue
                if captured != ident and m.group(1) == "BASE_DECLARE_FEATURE":
                    continue
            else:
                if captured != ident:
                    continue
            if not re.search(r"\b(BASE_FEATURE|UNI_FEATURE|DEFINE_FEATURE)\s*\(", text):
                continue
            seen.add(key)
            hits.append((os.path.join(root, fp), int(ln), text.strip()))
    return hits


def guard_chain(text, upto):
    """重建 text[:upto] 处生效的预处理条件链（朴素栈，够用于 Chromium 风格）。"""
    stack = []
    for m in re.finditer(r"^[ \t]*#[ \t]*(if|ifdef|ifndef|else|elif|endif)\b[ \t]*(.*)$",
                         text[:upto], re.M):
        kind, arg = m.group(1), m.group(2).strip()
        if kind in ("if", "ifdef", "ifndef"):
            stack.append(kind + " " + arg if arg else kind)
        elif kind == "endif":
            if stack:
                stack.pop()
        elif kind in ("else", "elif") and stack:
            stack[-1] = ("<分支:" + kind + " " + arg + ">"
                         if kind == "elif" else "<分支:else>")
    return stack


def join_decl(text, start):
    """从定义行起点取到匹配的 ');'，返回该声明的完整文本（含内部 #if）。"""
    depth = 0
    i = text.index("(", start)
    for j in range(i, min(len(text), i + 4000)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                k = text.find(";", j)
                return text[start:(k + 1) if k > 0 else j + 1]
    return text[start:start + 800]


GN_FACTS = {
    # 本构建身份（见 AGENTS.md 构建快速参考 / win_args_mcloud.gn）
    "is_win": True, "is_android": False, "is_mac": False, "is_chromeos": False,
    "is_linux": False, "is_posix": False, "is_fuchsia": False,
    "current_cpu": "x64", "target_cpu": "x64", "target_os": "win",
    "is_component_build": False, "is_debug": False, "is_official_build": True,
}


def gn_eval(expr):
    """安全求值 GN 表达式（只允许布尔/比较/名字/字面量，不 eval）。

    返回 (True/False/None, 未解析的原子名)。None = 判不了，交给人，绝不猜。
    """
    import ast

    # GN 用 C 风格运算符，Python 语法不接受，必须先翻译（首版漏了这步，
    # SyntaxError 被吞掉后把"能判定为假"的 buildflag 报成"判不了"）。
    expr = expr.strip()
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?!=)", " not ", expr)
    unknown = []

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            if any(v is None for v in vals):
                return None
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            v = ev(node.operand)
            return None if v is None else (not v)
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                return None
            left, right = ev(node.left), ev(node.comparators[0])
            if left is None or right is None:
                return None
            op = node.ops[0]
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            return None
        if isinstance(node, ast.Name):
            if node.id in GN_FACTS:
                return GN_FACTS[node.id]
            unknown.append(node.id)
            return None
        if isinstance(node, ast.Constant):
            return node.value
        return None

    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return None, []
    return ev(tree.body if isinstance(tree, ast.Expression) else tree), sorted(set(unknown))


def gen_buildflag_map(root, out_dir):
    """从**已生成的** buildflags 头里取本构建的实际取值（最权威，不用我替 GN 求值）。

    返回 {宏名: True/False}。取不到（没编译过 / 目录不存在）返回空字典，
    调用方退回 .gni 表达式求值路径。
    """
    vals = {}
    if not out_dir or not os.path.isdir(out_dir):
        return vals
    pat = re.compile(r"BUILDFLAG_INTERNAL_([A-Z0-9_]+)\(\)\s*\((\d)\)")
    n_files = 0
    for dirpath, dirnames, filenames in os.walk(out_dir):
        # 只在源码生成区找；obj/ 是编译中间产物（几十万个文件），必须剪掉而不是逐文件试读
        dirnames[:] = [d for d in dirnames if d != "obj"]
        for fn in filenames:
            if "buildflag" not in fn.lower() or not fn.endswith(".h"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > 400000:
                    continue
                with io.open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            n_files += 1
            for m in pat.finditer(text):
                vals[m.group(1)] = m.group(2) == "1"
    if n_files == 0:
        print("  [note] %s 下没找到已生成的 buildflags 头 ⇒ 退回 .gni 表达式求值" % out_dir)
    return vals


GEN_FLAGS = {}


def resolve_buildflag(root, token):
    """返回 (可读值元组 或 None, 出处)。先看已生成的 buildflags 头，再看 .gni。"""
    if token in GEN_FLAGS:
        return ("const", GEN_FLAGS[token]), "out/…/gen 已生成的 buildflags.h（本构建实际取值）"
    return _resolve_buildflag_gni(root, token)


def _resolve_buildflag_gni(root, token):
    """在 .gni 里找 buildflag 的赋值行，返回 (可读值表达式 或 None, 出处)。

    GN 侧约定：`declare_args()` 里的变量是小写形式（大写宏名由 buildflag 生成器转换），
    所以大写找不到必须再试小写，否则会把"能解析"报成"找不到"。
    """
    for cand in (token, token.lower()):
        r = subprocess.run(["git", "-C", root, "grep", "-n", "-E",
                            r"(^|[^A-Za-z0-9_])%s *=" % cand, "--", "*.gni"],
                           capture_output=True, text=True, errors="replace")
        out = (r.stdout or "").splitlines()
        for _k, line in enumerate(out):
            fp, _, rest = line.partition(":")
            ln, _, text = rest.partition(":")
            if cand not in text or not ln.isdigit():
                continue
            rhs = text.split("=", 1)[1].strip().rstrip(",")
            # GN 里常把表达式换行写（`= ` 后另起一行），只取首行会得到空串，
            # 于是把"能判定"的 buildflag 报成"判不了"（实测 partition_alloc.gni:588）。
            if rhs.count("(") != rhs.count(")") or not rhs:
                with io.open(os.path.join(root, fp), encoding="utf-8",
                                     errors="replace") as fh:
                            src_lines = fh.read().split("\n")
                i = int(ln)  # 1-based → 下一条从 i 开始
                def unfinished(x):
                    return (not x) or x.count("(") != x.count(")") or re.search(
                        r"(&&|\|\|\||==|!=\|\+|,|\b(and|or)\b)\s*$", x)
                while unfinished(rhs) and i < len(src_lines):
                    nxt = src_lines[i].strip()
                    i += 1
                    if not nxt or nxt.startswith("#") or nxt.startswith("declare_args"):
                        break
                    rhs = (rhs + " " + nxt).strip().rstrip(",")
                    if not unfinished(rhs):
                        break
            if re.match(r"^(True|False)$", rhs):
                return ("const", rhs == "True"), "%s:%s" % (fp.replace("\\", "/"), ln)
            val, unknown = gn_eval(rhs)
            if val is not None:
                return ("eval", val, rhs), "%s:%s" % (fp.replace("\\", "/"), ln)
            return ("unknown", rhs, unknown), "%s:%s" % (fp.replace("\\", "/"), ln)
    return None, ""


def classify(root, guards, decl):
    """返回 (verdict, note, 有效默认值)。

    两类 `#if` 必须分开对待（首版把它们混在一起，把 SkiaGraphite 这种
    "只包默认值的 #if"误判成 DEAD）：
      * **外层守卫**（定义整条声明外面）⇒ 条件不成立 = 声明根本没编译进来 = DEAD；
      * **声明内部的 #if/#else**，且两支都给出 FEATURE_*_BY_DEFAULT ⇒ 只是**默认值分支**，
        声明照样编译进来，应按本构建取实际那一支，不构成排除。
    """
    eff, eff_note = feature_decl.effective_default(decl)
    conds = []
    weak_guards = []
    for g in guards:
        parts = g.split(" ", 1)
        if len(parts) == 2 and parts[0] == "if":
            conds.append(parts[1])
        elif parts[0] in ("ifdef", "ifndef"):
            # 已知局限：`#ifdef X` / `#ifndef X` 里 X 若是平台宏（OS_WIN 之类）本脚本不判定，
            # 会退化成 ACTIVE。当前 52 项实测的守卫全是 BUILDFLAG(IS_*) 形态，没有这种写法；
            # 内核升级后若出现，这里会显式 WARN 而不是静默算通过。
            weak_guards.append(g.strip())
    if "#if" in decl and not eff:
        # 内层 #if 不是"默认值二选一"（取不出唯一有效默认值）⇒ 按守卫对待，
        # 它可能包住整条声明（D142 的两条死声明就是这种形态）
        for m in re.finditer(r"^[ \t]*#[ \t]*(if|elif)[ \t]*(.*)$", decl, re.M):
            conds.append(m.group(2).strip())

    dead, why = feature_decl.platform_excludes_us(conds)
    if dead:
        return "DEAD", why, ""

    # 非平台 buildflag：必须给出出处让人判定，不许静默算通过
    flags = set()
    for cond in conds:
        for m in re.finditer(r"(?:PA_)?BUILDFLAG\(\s*([A-Z0-9_]+)\s*\)", cond):
            tok = m.group(1)
            if tok not in feature_decl.PLATFORM_FACTS:
                flags.add(tok)
    unresolved = []
    for tok in sorted(flags):
        got, src = resolve_buildflag(root, tok)
        if got is None:
            unresolved.append("%s（.gni 里找不到赋值）" % tok)
            continue
        kind = got[0]
        if kind in ("const", "eval"):
            if not got[1]:
                rhs = got[2] if kind == "eval" else str(got[1])
                return "DEAD", "buildflag 在本构建为假：%s = %s @%s" % (tok, rhs, src), ""
            # 明确为真 ⇒ 该条件不构成排除
        else:
            unresolved.append("%s = %s @%s（表达式含未知原子 %s，不替人判定）"
                              % (tok, got[1][:60], src, ",".join(got[2]) or "?"))
    if unresolved:
        return ("UNRESOLVED_FLAG",
                "条件依赖非平台 buildflag，本脚本不替人判定：%s" % "；".join(unresolved), "")

    if eff:
        if weak_guards:
            eff_note = ((eff_note + " ; " if eff_note else "") +
                        "⚠ 外层有 ifdef/ifndef 守卫未判定：" + " / ".join(weak_guards)[:80])
        return "ACTIVE", eff_note, eff
    return ("UNKNOWN_DEFAULT",
            (eff_note or "默认值不可读") + "——不得当成'已知默认禁用'；"
            "pin 判定与净收益口径都会漏算（D177）", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("CR_DIR") or
                    r"D:\wxmuma\chromium-src-155\src")
    ap.add_argument("--flags", default=DEFAULT_FLAGS)
    ap.add_argument("--out", default=None,
                    help="构建输出目录（默认自动探测 <root>/out/mcloud，再退 out/*/gen）")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(os.path.join(root, "base")):
        print("[FATAL] 源码树不对（找不到 base/）：%s —— 设 CR_DIR 或 --root，"
              "不得在错误的树上出结论" % root)
        return 2
    out_dir = args.out
    if not out_dir:
        cand = os.path.join(root, "out", "mcloud")
        if not os.path.isdir(cand):
            odir = os.path.join(root, "out")
            cand = next((os.path.join(odir, d) for d in sorted(os.listdir(odir))
                         if os.path.isdir(os.path.join(odir, d, "gen"))), None) \
                if os.path.isdir(odir) else None
        out_dir = cand or ""
    GEN_FLAGS.clear()
    GEN_FLAGS.update(gen_buildflag_map(root, out_dir))
    if GEN_FLAGS:
        print("已生成 buildflags：读到 %d 个宏的实际取值（%s）" % (len(GEN_FLAGS), out_dir))
    flags = features_from_flags(args.flags)
    if not flags:
        print("[FATAL] %s 里没解析到任何 feature，判据自身失效" % args.flags)
        return 2

    results = []
    bad = 0
    for action, name in flags:
        ident = "k" + name[0].upper() + name[1:]
        defs = grep_defs(root, ident, name)
        rec = {"action": action, "name": name, "ident": ident,
               "defs": len(defs), "verdict": None, "note": "",
               "default": "", "file": "", "line": 0, "guards": []}
        if not defs:
            rec["verdict"] = "NOTFOUND"
            rec["note"] = "树里找不到定义（D48 同族：上游无此 feature）"
        else:
            fpath, lineno, _ = defs[0]
            try:
                with io.open(fpath, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as e:
                rec["verdict"] = "READFAIL"
                rec["note"] = str(e)
                results.append(rec)
                bad += 1
                print("[FAIL] %-45s %s" % (name, rec["note"]))
                continue
            joined = feature_decl.join_continuations(text)
            m = re.search(r"\b(?:BASE_FEATURE|UNI_FEATURE|DEFINE_FEATURE)\s*\(\s*"
                          + re.escape(ident) + r"\b", joined)
            if not m:
                m = re.search(r"\b(?:BASE_FEATURE|UNI_FEATURE|DEFINE_FEATURE)\s*\(\s*"
                              r"[A-Za-z0-9_]+\s*,\s*\"" + re.escape(name) + r"\"", joined)
            if not m:
                rec["verdict"] = "NOTFOUND"
                rec["note"] = "定位不到定义式（只有引用/同名 switch？）"
                results.append(rec)
                bad += 1
                print("[MISS] %-45s %s:%s  %s" % (name, rec["file"], rec["line"], rec["note"]))
                continue
            start = m.start()
            guards = guard_chain(joined, start)
            decl = join_decl(joined, start)
            rec["file"] = os.path.relpath(fpath, root)
            rec["line"] = lineno
            rec["guards"] = guards
            v, why, eff = classify(root, guards, decl)
            rec["verdict"] = v
            rec["note"] = why
            rec["default"] = eff
            if v != "ACTIVE":
                bad += 1
        results.append(rec)
        mark = {"ACTIVE": "ok  ", "DEAD": "DEAD", "UNKNOWN_DEFAULT": "UNK ",
                "AMBIGUOUS_DEFAULT": "AMB ", "UNRESOLVED_FLAG": "FLAG",
                "NOTFOUND": "MISS", "READFAIL": "ERR "}.get(rec["verdict"], "???? ")
        if mark != "ok  " or action == "disable":
            print("[%s] %-45s %s:%s  guards=%d  %s"
                  % (mark, name, rec["file"], rec["line"], len(rec["guards"]), rec["note"]))

    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    tally = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print("\n审计 %d 条：%s" % (len(results), "  ".join(
        "%s=%d" % (k, v) for k, v in sorted(tally.items()))))
    print("稳定性结论：%s" % ("全部守卫可达、默认值可读且唯一" if bad == 0
                          else "存在 %d 条需要处置（详见上面逐条）" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
