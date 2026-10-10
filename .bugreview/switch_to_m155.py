#!/usr/bin/env python3
"""switch_to_m155.py - 把仓库的配置与文档口径切到 M155（升级已完成并验收）。"""
import io

REPO = r"d:\wxmuma\thorium"
NEW = "155.0.8059.40"
OLD = "151.0.7922.99"
PROF = ("chrome-win64-8059-1790681878-a5a326a93a5b6da6820b51c3dd27c598393c85c9"
        "-bafd721ba752e4b3753f103970251e378ca171d6.profdata")


def edit(path, pairs, required=True):
    s = io.open(path, encoding="utf-8").read()
    hit = 0
    for a, b in pairs:
        if a in s:
            s = s.replace(a, b)
            hit += 1
        elif required:
            print("  !! 未命中 @%s: %s" % (path, a[:70]))
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)
    print("  %s: %d/%d" % (path, hit, len(pairs)))


print("== AGENTS.md ==")
edit(REPO + r"\AGENTS.md", [
    ("Chromium（当前 M151，151.0.7922.x，硬件基线 AVX2+FMA3）",
     "Chromium（当前 M155，155.0.8059.40，硬件基线 AVX2+FMA3）"),
    ("| Chromium M151 | 浏览器内核（当前 151.0.7922.x，tag 151.0.7922.99） |",
     "| Chromium M155 | 浏览器内核（当前 155.0.8059.40） |"),
    ("| Chromium M151 | 浏览器内核（tag 151.0.7922.99） |",
     "| Chromium M155 | 浏览器内核（tag 155.0.8059.40） |"),
    ("cd src && git checkout tags/151.0.7922.99", "cd src && git checkout tags/" + NEW),
])

print("== README.md ==")
edit(REPO + r"\README.md", [
    ("[Chromium M151 (151.0.7922.99)]", "[Chromium M155 (155.0.8059.40)]"),
    ("mcloud_151.0.7922.99_win64_mini_installer.exe", "mcloud_155.0.8059.40_win64_mini_installer.exe"),
    ("git fetch --depth 1 origin tag 151.0.7922.99", "git fetch --depth 1 origin tag " + NEW),
    ("git checkout 151.0.7922.99", "git checkout " + NEW),
    ("--revision src@151.0.7922.99", "--revision src@" + NEW),
    ('git commit -m "M151: Chromium 151.0.7922.99"', 'git commit -m "M155: Chromium 155.0.8059.40"'),
    ('git tag -a v151.0.7922.99 -m "MCloud Browser M151 (151.0.7922.99)"',
     'git tag -a v' + NEW + ' -m "MCloud Browser M155 (' + NEW + ')"'),
])

print("== win_args_mcloud.gn ==")
edit(REPO + r"\win_args_mcloud.gn", [
    ('# profdata 须与内核大版本严格匹配（M150=7871，M151=7922），升级时同步更新；',
     '# profdata 须与内核大版本严格匹配（M151=7922，M155=8059），升级时同步更新；'),
    ('pgo_data_path = "D:/wxmuma/chromium-src/src/chrome/build/pgo_profiles/chrome-win64-7922-'
     '1785260615-6ac4e83baf0934c1f70f2af0592d9696b32a86e1-0c69bbe6064e347ebf2e6316e669d4eaa4163879.profdata"',
     'pgo_data_path = "D:/wxmuma/chromium-src/src/chrome/build/pgo_profiles/' + PROF + '"'),
])

print("== mcloud_flags.txt 口径 ==")
edit(REPO + r"\mcloud_flags.txt", [
    ("# V8 flag 命名使用下划线（M151 确认）；", "# V8 flag 命名使用下划线（M151 确认；V8 源码里 _ 与 - 归一化等价，见缺陷 D49）；"),
])
