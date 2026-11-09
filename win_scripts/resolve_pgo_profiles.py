#!/usr/bin/env python3
"""resolve_pgo_profiles.py — 在真实源码树里解析 PGO profdata 并回填 args.gn。

背景（缺陷 D144）：GN 只断言 pgo_data_path 非空、不校验文件存在
（build/config/compiler/pgo/BUILD.gn:149）。内核升级时凭猜测写死 profdata 文件名，
会让 `gn gen --check` 照常通过、ninja 才在 inputs += [pgo_data_path] 报一句完全
不指向根因的 "missing and no known rule to make it"。本脚本把"事前猜测"改成
"对真实目录的解析"，避免编造 M158 的 8127 系列文件名。

补充（M158 实测）：GCS 上 8127 系列 profdata 对象带 `contentEncoding: gzip`，
直接 curl 下来的 111 MB 是压缩流，size/md5 与 GCS 元数据完全一致却仍是假绿，
clang-cl 会报 `invalid instrumentation profile data (bad magic)`；必须
`gzip -dc` 解压成约 514 MB、以 `\xfflprofi` 开头的文件才能用。
因此候选筛选除了"非空"还要校验 LLVM profdata magic。

用法：
  python win_scripts/resolve_pgo_profiles.py --src <CR_DIR> --build 8127
  python win_scripts/resolve_pgo_profiles.py --src <CR_DIR> --build 8127 \
      --write <CR_DIR>/out/mcloud/args.gn
  python win_scripts/resolve_pgo_profiles.py --src <CR_DIR> --build 8127 --pick <文件名>

退出码：0 成功 / 1 参数错误 / 2 环境不满足 / 3 写入失败。
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import tempfile

PROFDATA_PATTERN = "chrome-win64-{build}-*.profdata"
GN_KEY = "pgo_data_path"
GN_LINE_RE = re.compile(r"^\s*" + GN_KEY + r"\s*=")
# LLVM indexed profdata 的 magic（M155 8059 / M158 8127 实测一致）。
# gzip 压缩流以 1f 8b 开头，size/md5 都可能"校验通过"，但 clang 读不了。
PROFDATA_MAGIC = b"\xff\x6c\x70\x72\x6f\x66\x69"  # "\xfflprofi"


def has_profdata_magic(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(PROFDATA_MAGIC)) == PROFDATA_MAGIC
    except OSError:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Locate the PGO profdata matching the target kernel BUILD number."
    )
    p.add_argument("--src", required=True, help="Chromium 源码树根（含 chrome/VERSION）")
    p.add_argument("--build", required=True, help="内核 BUILD 号，例如 8127（M158）")
    p.add_argument("--pick", default="", help="多个候选时指定文件名（basename）")
    p.add_argument("--write", default="", help="把结果写入该 args.gn 的 pgo_data_path 行")
    return p


def die(code: int, msg: str) -> None:
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(code)


def check_tree(src: str) -> None:
    version = os.path.join(src, "chrome", "VERSION")
    if not os.path.isfile(version):
        die(2, "读不到 %s —— --src 不是 Chromium 源码树" % version)


def candidates(src: str, build: str) -> list[str]:
    if not build.isdigit():
        die(1, "--build 必须是纯数字（例如 8127），收到 %r" % build)
    d = os.path.join(src, "chrome", "build", "pgo_profiles")
    if not os.path.isdir(d):
        die(2, "目录不存在：%s（先跑 tools/update_pgo_profiles.py --target=win64 update）" % d)
    pattern = os.path.join(d, PROFDATA_PATTERN.format(build=build))
    return sorted(p for p in glob.glob(pattern)
                  if os.path.isfile(p) and os.path.getsize(p) > 0
                  and has_profdata_magic(p))


def choose(hits: list[str], pick: str) -> str:
    if not hits:
        die(2, "没有匹配、非空且以 \\xfflprofi 开头的 profdata；确认 --build 号与内核 "
               "BUILD 一致。若文件是 gzip 压缩流（1f 8b 开头，GCS 的 "
               "contentEncoding=gzip），先 `gzip -dc <file> > <同名 .profdata>` 解压")
    if pick:
        for p in hits:
            if os.path.basename(p) == pick:
                return p
        die(1, "--pick %r 不在候选列表里：%s"
            % (pick, [os.path.basename(x) for x in hits]))
    if len(hits) > 1:
        print("WARN: 找到 %d 个候选，默认取字典序最后一个；用 --pick 明确指定："
              % len(hits), file=sys.stderr)
        for p in hits:
            print("  %s" % os.path.basename(p), file=sys.stderr)
    return hits[-1]


def write_gn(path: str, profdata: str) -> None:
    """原子替换 args.gn 里的 pgo_data_path 行；不存在则追加。"""
    if not os.path.isfile(path):
        die(2, "args.gn 不存在：%s（先 cp win_args_mcloud.gn out/mcloud/args.gn）" % path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines(keepends=True)
    repl = '%s = "%s"\n' % (GN_KEY, profdata.replace("\\", "/"))
    out, found = [], False
    for ln in lines:
        if GN_LINE_RE.match(ln):
            out.append(repl)
            found = True
        else:
            out.append(ln if ln.endswith("\n") else ln + "\n")
    if not found:
        out.append(repl)
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".args.gn.", dir=d, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.writelines(out)
        os.replace(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.unlink(tmp)
        die(3, "写入失败：%s" % path)


def main() -> int:
    args = build_parser().parse_args()
    src = os.path.abspath(args.src)
    check_tree(src)
    profdata = choose(candidates(src, args.build), args.pick)
    print('%s = "%s"' % (GN_KEY, profdata.replace("\\", "/")))
    print("size=%d bytes" % os.path.getsize(profdata))
    if args.write:
        write_gn(os.path.abspath(args.write), profdata)
        print("已写入：%s" % args.write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
