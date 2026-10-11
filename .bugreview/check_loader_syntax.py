#!/usr/bin/env python3
"""check_loader_syntax.py - 对 inject_flags_loader.py 的 LOADER C++ 正文做粗粒度语法自检。

不能替代真实编译（那需要完整 Chromium 构建），但能拦住括号/引号失衡这类
"改一行就编译不过"的低级错误——本轮往 LOADER 里加了 LOG(WARNING) 与 FilePath 流式输出。
"""
import io
import os
import re
import sys

# 从本文件位置推仓库根，不依赖调用者的 cwd（.bugreview/ 下的判据脚本都要能在任意目录跑）
THOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(THOR, "win_scripts", "inject_flags_loader.py")


def strip_noise(text):
    """去掉字符串字面量、字符字面量与注释，避免把里面的括号算进去。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append('""')
            continue
        if c == "'":
            i += 1
            while i < n and text[i] != "'":
                i += 2 if text[i] == "\\" else 1
            i += 1
            out.append("''")
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = (j + 2) if j >= 0 else n
            continue
        out.append(c)
        i += 1
    return "".join(out)


def main():
    with io.open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"^LOADER = r'''(.*?)'''", src, re.S | re.M)
    if not m:
        print("FAIL: 没能在 %s 里定位 LOADER 正文" % SRC)
        return 1
    body = m.group(1)
    clean = strip_noise(body)

    failures = []
    print("LOADER 正文行数: %d" % body.count("\n"))
    for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
        a, b = clean.count(opener), clean.count(closer)
        status = "OK" if a == b else "MISMATCH"
        print("  %s%s : %d / %d  %s" % (opener, closer, a, b, status))
        if a != b:
            failures.append("%s%s 不平衡（%d vs %d）" % (opener, closer, a, b))

    # 分号/语句级粗检：流式 LOG(...) 语句必须以分号收尾。
    # 注意判据是"某行以 ; 结束"而不是 ");" —— 流式写法最后一行形如
    #   << "defaults, all built-in performance flags are INACTIVE.";
    # 收尾是 `";` 而非 `);`。首版用 ");" 判，把两处**已编译进 r5 的既存** LOG
    # 也误报了，说明检查器本身要先被证伪。
    for idx, line in enumerate(body.splitlines(), 1):
        s = line.strip()
        if s.startswith("LOG("):
            window = body.splitlines()[idx - 1: idx + 8]
            if not any(w.rstrip().endswith(";") for w in window):
                failures.append("第 %d 行的 LOG 语句在随后 8 行内找不到收尾分号" % idx)

    # 本轮新增行的针对性检查
    if "not found (tried module dir" not in body:
        failures.append("找不到 D146 新增的 LOG(WARNING) 行")
    if ".value()" in body and "module_dir.value()" in body:
        failures.append("仍在用 module_dir.value()（Windows 上是 std::wstring，应直接流 FilePath）")

    print("")
    if failures:
        print("VERDICT: FAIL")
        for f in failures:
            print("  - %s" % f)
        return 1
    print("VERDICT: PASS（括号平衡、LOG 语句收尾、D146 行存在且未用 .value()）")
    print("注意：这只是粗粒度自检，**不等于编译通过**；LOADER 改动需 deploy + 重编译才算数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
