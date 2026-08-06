#!/usr/bin/env python3
# =============================================================================
# MCloud Browser — feature 清单有效性校验脚本
# =============================================================================
# 规范依据：performance-build-technical-spec.md 第 4.2 / 9.2（清单第 8 项）/ 10.4
#
# 功能：解析 mcloud_flags.txt 中的 feature 名称（--enable-features /
# --disable-features），在目标 Chromium 源码树中检索每个 feature 标识符
# 是否仍然存在，输出失效（可能被上游移除/更名）清单。
#
# 用法：
#   python3 check_features.py [--flags <mcloud_flags.txt>] [--src <chromium/src>]
# 示例：
#   python3 benchmark/tools/check_features.py --src D:/wxmuma/chromium-src/src
#
# 说明：
# - 检索以"标识符字符边界"匹配（避免子串误报），扫描整个 src 树
#   （排除 third_party 主体，仅保留 third_party/blink）的 *.cc/*.h/*.mm；
# - 非 feature 类标志（如 --enable-gpu-rasterization）不在校验范围；
# - 结果含 NOT_FOUND 时退出码为 1，便于接入升级检查清单。
# =============================================================================

import argparse
import os
import re
import sys

# feature 定义分散在多个目录（如 components/performance_manager、
# third_party/blink/common 等），采用"全源码树扫描 + 排除 third_party 主体"
# 策略，避免目录白名单遗漏（已发生先例：performance_manager）。
EXCLUDE_THIRD_PARTY_EXCEPT = {
    os.path.join("third_party", "blink"),
}
SKIP_DIR_NAMES = {
    "out", ".git", "testdata", "test", "tests",
    "third_party",  # 由白名单单独处理
}
SCAN_EXTS = {".cc", ".h", ".mm"}

# 单个 feature 条目形如 Name 或 Name:param1/param2
FEATURE_ENTRY_RE = re.compile(r"^([A-Za-z0-9_]+)")


def parse_flags_file(path):
    """从 mcloud_flags.txt 提取全部 feature 名称（去重保序）。"""
    features = []
    seen = set()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            for switch in ("--enable-features=", "--disable-features="):
                if line.startswith(switch):
                    value = line[len(switch):]
                    for entry in value.split(","):
                        m = FEATURE_ENTRY_RE.match(entry.strip())
                        if m:
                            name = m.group(1)
                            if name not in seen:
                                seen.add(name)
                                features.append(name)
    return features


def check_features(features, src_root):
    """返回 (found, not_found)。"""
    if not features:
        return [], []
    # 合并正则：匹配字符串字面量或 kXxx 常量后缀形式的 feature 名；
    # 尾部要求非标识符字符（避免长名前缀误报，如 AVIF 不匹配 AVIFDecoder）
    pattern = re.compile(
        r"(?:" + "|".join(re.escape(f) for f in features) +
        r")(?![A-Za-z0-9_])"
    )
    remaining = set(features)
    found = []

    def scan_tree(base_dir):
        for dirpath, dirnames, filenames in os.walk(base_dir):
            if not remaining:
                return
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for fn in filenames:
                if os.path.splitext(fn)[1] not in SCAN_EXTS:
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                hit = set(pattern.findall(text))
                if hit:
                    for name in hit & remaining:
                        found.append(name)
                        remaining.discard(name)
            if not remaining:
                return

    scan_tree(src_root)
    # third_party 仅扫白名单子树
    for sub in EXCLUDE_THIRD_PARTY_EXCEPT:
        if remaining:
            sub_path = os.path.join(src_root, sub)
            if os.path.isdir(sub_path):
                scan_tree(sub_path)

    not_found = [f for f in features if f in remaining]
    return found, not_found


def main():
    parser = argparse.ArgumentParser(
        description="校验 mcloud_flags.txt 中 feature 在目标 Chromium 源码中的有效性")
    default_flags = os.path.join(
        os.path.dirname(__file__), "..", "..", "mcloud_flags.txt")
    parser.add_argument("--flags", default=default_flags,
                        help="mcloud_flags.txt 路径（默认仓库根目录）")
    parser.add_argument("--src", default=None,
                        help="目标 Chromium src 目录（必填，即待升级/当前内核源码树）")
    args = parser.parse_args()

    flags_path = os.path.abspath(args.flags)
    if not os.path.isfile(flags_path):
        print(f"[ERROR] flags 文件不存在: {flags_path}")
        return 2
    if not args.src or not os.path.isdir(args.src):
        print("[ERROR] 请用 --src 指定有效的 Chromium src 目录")
        return 2

    features = parse_flags_file(flags_path)
    print(f"解析到 {len(features)} 个 feature（来自 {flags_path}）")
    print(f"在 {args.src} 中检索...\n")

    found, not_found = check_features(features, args.src)

    print(f"[OK] 存在 {len(found)} / {len(features)}")
    if not_found:
        print(f"\n[NOT_FOUND] {len(not_found)} 个 feature 未在源码中找到"
              "（可能被上游移除或更名，须按规范 4.2 处理）：")
        for name in not_found:
            print(f"  - {name}")
        print("\n处理要求：从 mcloud_flags.txt 移除并在升级报告/登记表中记录原因；"
              "如需替代 feature，按规范 4.2 审核流程新增。")
        return 1
    print("\n全部 feature 有效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
