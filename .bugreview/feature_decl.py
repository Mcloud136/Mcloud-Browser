# -*- coding: utf-8 -*-
"""feature_decl.py —— 从 Chromium 的 feature 声明文本里取**本构建的平台有效默认值**。

为什么要有这个模块（第7周期，缺陷 D177）：`survival_check.py` 早期只看声明行 + 2 行上下文，
于是
  · `BASE_FEATURE(kSkiaGraphite,` 后面跟的是 `#if BUILDFLAG(IS_APPLE) … ENABLED #else … DISABLED`，
    它取到第一个 FEATURE_*_BY_DEFAULT ⇒ 报 ENABLED，而 Windows 实际是 **DISABLED**；
  · `kAsyncDns` 的默认值整段在 `#if` 里且跨续行，窗口不够长就报空字符串。
错的默认值会直接污染"净收益口径"（哪些行只是 pin、哪些是真优化），而口径写在 AGENTS.md、
发布说明与 `mcloud_flags.txt` 头部。

本模块只被 survival_check.py 与 guard_audit.py 共用，避免两套判定各自漂移。
构建身份写死在这里（Windows / x64），因为本产品只发 Windows x64（ADR-003）。
"""

import re

OUR_PLATFORM = "IS_WIN"
OTHER_PLATFORMS = ("IS_POSIX", "IS_ANDROID", "IS_MAC", "IS_CHROMEOS", "IS_LINUX",
                   "IS_FREEBSD", "IS_OPENBSD", "IS_SOLARIS", "IS_APPLE")
PLATFORM_FACTS = {"IS_WIN": True, "IS_MAC": False, "IS_ANDROID": False,
                  "IS_CHROMEOS": False, "IS_LINUX": False, "IS_POSIX": False,
                  "IS_FREEBSD": False, "IS_OPENBSD": False, "IS_SOLARIS": False,
                  "IS_FUCHSIA": False, "IS_APPLE": False}

DEFAULT_RE = re.compile(r"(?:[A-Za-z_]+::)?(?:FEATURE_[A-Z_]+_BY_DEFAULT"
                        r"|feature_default::k[A-Za-z]+|kDefault[A-Za-z]*)")


def join_continuations(text):
    r"""合并反斜杠续行。守卫条件常写成 `BUILDFLAG(IS_A) || \` + 换行，
    不合并就会把条件截断，把"含 IS_WIN 的多行条件"误判成排除本构建。"""
    return re.sub(r"\\\r?\n[ \t]*", " ", text)


def eval_platform_cond(cond):
    """求值只含 BUILDFLAG(平台宏) 与 || && ! 括号 的条件；判不了返回 None（不猜）。

    刻意不用 eval：条件文本来自源码树，"把字符串喂给 eval"就是执行面。
    """
    expr = cond
    for tok, truth in PLATFORM_FACTS.items():
        expr = re.sub(r"BUILDFLAG\(\s*%s\s*\)" % tok, "True" if truth else "False", expr)
        expr = re.sub(r"\b%s\b" % tok, "True" if truth else "False", expr)
    if re.search(r"BUILDFLAG|defined", expr):
        return None
    if re.sub(r"True|False|\|\||&&|\(|\)|!|\s", "", expr):
        return None                      # 还有别的记号 ⇒ 放弃判定
    tokens = re.findall(r"True|False|\|\||&&|\(|\)|!", expr)
    if not tokens:
        return None
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def take(expected=None):
        t = peek()
        if t is None or (expected and t != expected):
            raise ValueError("token")
        pos[0] += 1
        return t

    def atom():
        t = peek()
        if t == "!":
            take("!")
            return not atom()
        if t == "(":
            take("(")
            v = or_expr()
            take(")")
            return v
        if t in ("True", "False"):
            take()
            return t == "True"
        raise ValueError("atom")

    def and_expr():
        v = atom()
        while peek() == "&&":
            take("&&")
            v = atom() and v
        return v

    def or_expr():
        v = and_expr()
        while peek() == "||":
            take("||")
            v = and_expr() or v
        return v

    try:
        result = or_expr()
        return result if pos[0] == len(tokens) else None
    except (ValueError, IndexError, RecursionError):
        return None


def platform_excludes_us(conds):
    """守卫是否把本构建（Windows）整体排除。返回 (True, 原因) 或 (False, "")。

    只看**包住整条声明**的条件；只包默认值的 #if/#else 由 effective_default() 处理。
    """
    for cond in conds:
        has_win = OUR_PLATFORM in cond
        others = [p for p in OTHER_PLATFORMS if p in cond]
        if others and not has_win and not re.search(r"!", cond):
            return True, "守卫排除本构建：%s" % cond[:90]
    return False, ""


def effective_default(decl_text):
    """返回 (默认值 或 "", 说明)。

    支持两种形态：
      ① 单支：`BASE_FEATURE(kFoo, base::FEATURE_DISABLED_BY_DEFAULT);`
      ② 平台二选一：`#if <平台条件> A #else B #endif` ⇒ 按本构建挑实际编译进来的那一支。
    遇到 #elif / 多个 #if / 条件判不了 ⇒ 返回 ("", 原因)，让调用方**硬失败**而不是猜。
    """
    text = join_continuations(decl_text)
    hits = DEFAULT_RE.findall(text)
    if not hits:
        return "", "声明文本里读不到 FEATURE_*_BY_DEFAULT"
    if len(set(h for h in hits)) == 1 and "#if" not in text:
        return hits[0].split("::")[-1] if "::" in hits[0] else hits[0], ""
    m = re.search(r"#if\s+(.*?)((?:\w+::)?FEATURE_[A-Z_]+_BY_DEFAULT)(.*?)#else\s*"
                  r"(.*?)((?:\w+::)?FEATURE_[A-Z_]+_BY_DEFAULT)(.*?)#endif", text, re.S)
    if m:
        cond = re.sub(r"\b\w+::", "", m.group(1))
        truth = eval_platform_cond(cond)
        if truth is None:
            return "", "多分支默认值但条件判不了：%s" % cond.strip()[:70]
        chosen = m.group(2) if truth else m.group(5)
        return chosen.split("::")[-1], ("按本构建走 %s 分支（条件：%s）"
                                       % ("#if" if truth else "#else", cond.strip()[:70]))
    if len(set(hits)) > 1:
        return "", "声明里有多个不同默认值分支且不是可判的二选一：%s" % sorted(set(hits))
    return hits[0].split("::")[-1], ""
