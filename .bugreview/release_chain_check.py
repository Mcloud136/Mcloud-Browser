# -*- coding: utf-8 -*-
"""release_chain_check.py —— 发布链一致性闸门（第7周期新增）。

断掉的链长这样：仓库改了 `mcloud_flags.txt` → 构建树/打包暂存载荷/已安装实例仍是旧的
→ 全部编译与门禁绿灯 → 发出去的包装出来的是上一版清单。这条链在 D102 / D175 /
第6周期 §8.2 里断过**三次**，每次都靠人事后想起来。

本脚本把"想起来"变成机器判定：三处指纹各自核对，任一不一致即 FAIL 并给出处置方式。
它**不修改任何东西**，只判定。

三处：
  REPO      d:\\wxmuma\\thorium\\mcloud_flags.txt          （提交进仓库的那份）
  PAYLOAD   <CR_DIR>/out/mcloud/gen/chrome/installer/mini_installer/mini_installer/
            temp_installer_archive/Chrome-bin/<版本>/mcloud_flags.txt
            （打包用的暂存载荷 = `chrome.7z` 的真身，见 D102：在 installer 本体里搜字节串
             永远搜不到，必须看归档前的暂存目录）
  INSTALLED C:\\Program Files\\Chromium\\Application\\<版本>\\mcloud_flags.txt

用法：
    python .bugreview/release_chain_check.py            # 三处全查
    python .bugreview/release_chain_check.py --payload-only
退出码：0 = 一致（或某处不存在但显式接受）；1 = 不一致或该存在却缺失。
"""

import argparse
import hashlib
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CR_DIR = os.environ.get("CR_DIR") or r"D:\wxmuma\chromium-src-155\src"
VERSION = os.environ.get("MCLOUD_VERSION") or "155.0.8059.40"
PAYLOAD = os.path.join(
    CR_DIR, "out", "mcloud", "gen", "chrome", "installer", "mini_installer",
    "mini_installer", "temp_installer_archive", "Chrome-bin", VERSION, "mcloud_flags.txt")
INSTALLED = os.path.join(r"C:\Program Files\Chromium\Application", VERSION, "mcloud_flags.txt")
REPO_FILE = os.path.join(REPO, "mcloud_flags.txt")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def sha16(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()[:16]


def active_lines(path):
    out = []
    with io.open(path, encoding="utf-8", newline="") as fh:
        for raw in fh:
            t = raw.strip()
            if t and not t.startswith("#"):
                out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload-only", action="store_true", help="只比仓库与打包暂存载荷")
    args = ap.parse_args()

    if not os.path.isfile(REPO_FILE):
        print("[FAIL] 仓库清单不存在：%s" % REPO_FILE)
        return 1
    repo_sha = sha16(REPO_FILE)
    print("仓库        %-16s %s" % (repo_sha, REPO_FILE))

    rows = [("打包暂存载荷", PAYLOAD)]
    if not args.payload_only:
        rows.append(("已安装实例", INSTALLED))

    bad = []
    for label, path in rows:
        if not os.path.isfile(path):
            print("%s %-16s 文件不存在：%s" % (label, "MISSING", path))
            bad.append((label, "不存在", path))
            continue
        sha = sha16(path)
        same = "一致" if sha == repo_sha else "**不一致**"
        print("%s %-16s %s" % (label, sha, same))
        if sha != repo_sha:
            # 区分"只是注释不同"与"开关集合真的不同"，两者处置不同
            a, b = active_lines(REPO_FILE), active_lines(path)
            diff = sorted(set(a) ^ set(b))
            if not diff:
                print("   ↳ 有效开关集合相同，只差注释/排版 ⇒ 运行时行为不变，"
                      "但发布物仍与仓库不同字节，**下一次发布必须重跑打包**")
            else:
                print("   ↳ 有效开关集合也不同（%d 项）：%s" % (len(diff), diff[:4]))
            bad.append((label, same, path))

    if bad:
        print("\n结论：发布链**断裂**（第 %d 处：%s）。" % (len(bad), bad[0][0]))
        print("处置（不要手工 copy 到安装目录或暂存目录 —— 那正是 D175 的形态）：")
        print("  1) 重新打包：python .bugreview/package_m155.py（会重压 chrome.7z 与 mini_installer）")
        print("  2) 干净安装复验（AGENTS.md 的非交互口径：--quiet --system-level / --force-uninstall）")
        print("  3) 复跑本脚本，直到三处指纹相同")
        return 1
    print("\n结论：三处指纹一致，发布链完整。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
