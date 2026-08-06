# 工具：向 chromium 树的 chrome/app/chrome_main_delegate.cc（当前上游基线）
# 注入 MCloud 内置启动标志加载器（规范 4.1.1，整改项 A6）。
#
# 背景（2026-08-05）：thorium 仓库内的 chrome_main_delegate.cc 副本为旧基线，
# 与较新内核树存在 API 漂移（base::StringPiece 移除、PackExtension 签名变更、
# OverrideCachedUIStrings/kDisableBoostPriorityMode/DIR_INTERNAL_PLUGINS 移除），
# 整体部署会导致编译失败。故加载器改为在树的当前上游文件上原位注入。
#
# 加载器行为：启动早期从 exe 同目录读取 mcloud_flags.txt，逐行解析
# （--flag / --flag=value / 引号值 / # 注释），追加到进程命令行；
# enable/disable-features 与用户命令行合并（用户条目在后优先），
# 其余标志若用户已指定则跳过。
import io
import re
import sys

p = r"D:\wxmuma\chromium-src\src\chrome\app\chrome_main_delegate.cc"
s = io.open(p, encoding="utf-8").read()

if "LoadMcloudPerformanceFlags" in s:
    print("loader already present, nothing to do")
    sys.exit(0)

# ---- 依赖确认 / 自动补齐 include ----
for inc in ("base/base_paths.h", "base/command_line.h", "base/path_service.h",
            "base/strings/string_util.h"):
    assert ('#include "%s"' % inc) in s, "missing include: " + inc
if '#include "base/strings/string_split.h"' not in s:
    anchor = '#include "base/path_service.h"\n'
    assert anchor in s, "path_service.h anchor not found for include insertion"
    s = s.replace(anchor, anchor + '#include "base/strings/string_split.h"\n', 1)
    print("added include: base/strings/string_split.h")

LOADER = r'''
// --- MCloud Browser: built-in performance startup flags (mcloud_flags.txt) ---
// Reads `mcloud_flags.txt` from the executable directory and appends the
// flags to the current process command line. User-specified switches take
// precedence (plain switches are skipped; enable/disable-features are merged
// with user entries appended last so per-entry parameters resolve to the
// user's values). See docs/architecture/performance-build-technical-spec.md
// section 4.1.1.
void LoadMcloudPerformanceFlags() {
  base::FilePath exe_dir;
  if (!base::PathService::Get(base::DIR_EXE, &exe_dir)) {
    return;
  }
  const base::FilePath flags_path = exe_dir.AppendASCII("mcloud_flags.txt");
  std::string contents;
  if (!base::ReadFileToString(flags_path, &contents)) {
    return;
  }

  base::CommandLine* command_line = base::CommandLine::ForCurrentProcess();

  for (std::string_view line :
       base::SplitStringPiece(contents, "\n", base::TRIM_WHITESPACE,
                              base::SPLIT_WANT_NONEMPTY)) {
    // Skip comment lines.
    if (line.empty() || line[0] == '#') {
      continue;
    }
    if (!base::StartsWith(line, "--", base::CompareCase::SENSITIVE)) {
      continue;
    }

    std::string switch_name;
    std::string value;
    size_t equals = line.find('=');
    if (equals != std::string_view::npos) {
      switch_name.assign(line.data() + 2, equals - 2);
      value.assign(line.data() + equals + 1, line.size() - equals - 1);
      // Strip paired double quotes (supports --js-flags="... ...").
      if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        value = value.substr(1, value.size() - 2);
      }
    } else {
      switch_name.assign(line.data() + 2, line.size() - 2);
    }
    if (switch_name.empty()) {
      continue;
    }

    if (switch_name == switches::kEnableFeatures ||
        switch_name == switches::kDisableFeatures) {
      // Merge feature lists: built-ins first, user entries appended last.
      std::string merged = value;
      if (command_line->HasSwitch(switch_name)) {
        merged += "," + command_line->GetSwitchValueASCII(switch_name);
      }
      command_line->AppendSwitchASCII(switch_name, merged);
    } else if (!command_line->HasSwitch(switch_name)) {
      command_line->AppendSwitchASCII(switch_name, value);
    }
  }
}
// --- MCloud Browser: end ---

'''

# ---- 注入点 1：匿名命名空间开头 ----
anchor_ns = "namespace {"
idx = s.find(anchor_ns)
assert idx != -1, "namespace { anchor not found"
insert_pos = idx + len(anchor_ns) + 1  # skip the newline after "namespace {"
s = s[:insert_pos] + LOADER + s[insert_pos:]

# ---- 注入点 2：BasicStartupComplete 函数体开头 ----
m = re.search(
    r"(std::optional<int> ChromeMainDelegate::BasicStartupComplete\(\) \{\n)",
    s)
assert m, "BasicStartupComplete anchor not found"
call = (
    "\n  // MCloud Browser: inject built-in performance startup flags before\n"
    "  // feature parsing.\n"
    "  LoadMcloudPerformanceFlags();\n"
)
s = s[:m.end()] + call + s[m.end():]

# ---- 依赖确认：switches::kEnableFeatures / kDisableFeatures 来自 content_switches ----
assert "content/public/common/content_switches.h" in s, \
    "content_switches.h not included (kEnableFeatures/kDisableFeatures)"

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("loader injected into chrome_main_delegate.cc")
