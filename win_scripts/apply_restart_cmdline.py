# 向 M155 上游 chrome/browser/chrome_browser_main_win.cc 的 GetRestartCommandLine()
# 注入"重启命令行瘦身"，修复 RegisterApplicationRestart 因命令行超长而失败。
#
# 缺陷（第6周期，2026-10-12，D172）：
#   Windows 的 RegisterApplicationRestart 对命令行有 1024 字符上限，超限时返回
#   E_INVALIDARG。上游在 chrome_browser_main_win.cc:830-838 对该返回值打
#   LOG(WARNING) "Command line too long for RegisterApplicationRestart"，然后**照样继续**——
#   于是失败完全静默：构建、安装、门禁全绿，只是浏览器从此**不会被 Windows 重启管理器
#   恢复**（Windows 更新重启后、或崩溃后，其他已注册应用会自动恢复，本浏览器不会）。
#   实测取证：安装版启动日志里稳定出现该 WARNING。
#
#   超限的原因：本项目的 flags 加载器把 50 项 feature 追加进进程命令行，
#   --enable-features 一项就约 1.4 KB，已经超过预算。
#   GetRestartCommandLine() 只调用了 about_flags::RemoveFlagsSwitches()，而那只移除
#   chrome://flags 产生的开关；我们这批是**命令行直传**的，不在其集合内，因此原样保留。
#
# 修法：把 enable-features / disable-features / js-flags 从重启命令行里去掉。
#   这是安全的——加载器在每次启动时都会从 mcloud_flags.txt 重新读取并注入，
#   它们不需要靠命令行接力传递。去掉后重启命令行回落到约 260 字符，远低于 1024。
#   用字符串字面量而不是 switches::kXxx 常量：kEnableFeatures 的可视性依赖具体头文件，
#   而 base::CommandLine::SwitchMap 的键就是 std::string，字面量更稳且无需新增 include。
#
# 幂等：以标记行存在与否判定；已存在则比对正文，不同才整体替换。

import io
import os
import sys

# D27: 与 deploy_mcloud.py 的 CR_DIR 机制保持一致
SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "chrome", "browser", "chrome_browser_main_win.cc")
if not os.path.isfile(p):
    print("ERROR: %s not found (CR_DIR 指向的树不对？)" % p)
    sys.exit(1)
s = io.open(p, encoding="utf-8").read()

BEGIN = "  // MCloud Browser: trim the restart command line"

BLOCK = '''  // MCloud Browser: trim the restart command line (bug-review D172).
  // The built-in flag loader re-injects these from mcloud_flags.txt on every
  // launch, so they never need to be carried through the restart command line.
  // Keeping them overflowed the 1024-char RegisterApplicationRestart budget
  // (--enable-features alone is ~1.4 KB), which made the registration return
  // E_INVALIDARG and silently left the browser unrestorable after a Windows
  // update. Literal switch names are used on purpose: SwitchMap keys are plain
  // std::string, so this needs no extra include.
  switches.erase("enable-features");
  switches.erase("disable-features");
  switches.erase("js-flags");'''

ANCHOR = "  about_flags::RemoveFlagsSwitches(&switches);"
# 块边界必须落在我们自己最后一行的末尾，不能落到下一个上游语句上：早期实现用
# "// Add remaining switches" 当结束锚点，于是复跑时把夹在中间的
# `switches.erase(switches::kFromInstaller);` 一并替换掉了（第6周期实测）。
LAST_LINE = '  switches.erase("js-flags");'
# 仅用于首次注入时确认函数形状未变（不参与替换边界）。
SHAPE_PROBE = "\n  // Add remaining switches, but not non-switch arguments."

if BEGIN in s:
    i = s.index(BEGIN)
    j = s.find(LAST_LINE, i)
    if j == -1:
        print("ERROR: found our marker but not our last line after it; "
              "file shape changed, refusing to rewrite")
        sys.exit(1)
    j += len(LAST_LINE)
    cur = s[i:j]
    if cur == BLOCK.strip("\n"):
        print("restart command-line trim already present (content match), nothing to do")
        sys.exit(0)
    s = s[:i] + BLOCK.strip("\n") + s[j:]
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("restart command-line trim block replaced in place")
    sys.exit(0)

if ANCHOR not in s:
    print("ERROR: anchor %r not found; upstream shape changed, "
          "do not append blindly" % ANCHOR)
    sys.exit(1)
if SHAPE_PROBE not in s:
    print("ERROR: shape probe %r not found; upstream shape changed" % SHAPE_PROBE)
    sys.exit(1)

s = s.replace(ANCHOR, ANCHOR + "\n" + BLOCK + "\n", 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("restart command-line trim injected after RemoveFlagsSwitches()")
