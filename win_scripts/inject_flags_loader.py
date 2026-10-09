# 工具：向 chromium 树的 chrome/app/chrome_main_delegate.cc（当前上游基线）
# 注入 MCloud 内置启动标志加载器（规范 4.1.1，整改项 A6）。
#
# 背景（2026-08-05）：thorium 仓库内的 chrome_main_delegate.cc 副本为旧基线，
# 与较新内核树存在 API 漂移（base::StringPiece 移除、PackExtension 签名变更、
# OverrideCachedUIStrings/kDisableBoostPriorityMode/DIR_INTERNAL_PLUGINS 移除），
# 整体部署会导致编译失败。故加载器改为在树的当前上游文件上原位注入。
#
# 加载器行为（v2）：启动早期从 exe 同目录读取 mcloud_flags.txt（上限 1MB），
# 逐行解析（--flag / --flag=value / 引号值 / # 注释），追加到进程命令行；
# enable/disable-features 单次聚合合并，用户条目置于最前——
# base::FeatureList::RegisterOverride() 为 try_emplace 首条生效语义，
# 用户在前才能覆盖同名内置项的状态与参数（修复 D21）。
# v1 缺陷：内置在前压制用户覆盖；每行累积 AppendSwitchASCII 造成 O(n^2)
# 与 ~60 个重复开关（D22）；ReadFileToString 无大小上限（D23）。
# v3：合并后的 feature 列表超过 24KiB 时跳过内置合并（D39——子进程
# CreateProcessW 命令行上限 32767 字符，超限导致 GPU 进程无法启动 →
# FATAL "GPU process isn't usable"）。
# v4：为加载器追加的**全部**开关引入字节预算（总 24KiB，普通开关子预算
# 12KiB），超预算条目跳过并 LOG(WARNING)（D40——单个超长值如 1MB 的
# --js-flags 同样会撑爆子进程命令行，路径与 D39 相同但未覆盖）。
# 实测（2026-10-09）：真实 6.1KB 标志文件总追加约 3.4KB，预算余量充足；
# 3000 条 feature（106KB）场景下 v3 已验证浏览器存活且内置列表不进子进程。
# v5：逐行解析改用 string_view::substr，消除 -Wunsafe-buffer-usage 告警
# （v4 的 `line.data() + n` 裸指针运算在 15:43 构建日志中逐行告警）。
# 同时把"是否需要替换"的判定从版本号标记改为正文比对，避免正文与标记不同步。
import io
import os
import re
import sys

SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
p = os.path.join(SRC, "chrome", "app", "chrome_main_delegate.cc")
s = io.open(p, encoding="utf-8").read()

LOADER_BEGIN = "// --- MCloud Browser: built-in performance startup flags (mcloud_flags.txt) ---"
LOADER_END = "// --- MCloud Browser: end ---"

if LOADER_BEGIN in s and LOADER_END in s:
    # 已有标记块：是否需要替换由内容比对决定（见 LOADER 定义之后）。
    # 内容比对取代了旧的版本号标记判断——改动加载器正文不再需要同步手改版本号，
    # 也不会出现"版本号已更新、正文仍是旧版"的假升级（旧逻辑缺陷）。
    has_block = True
elif "LoadMcloudPerformanceFlags" in s:
    print("ERROR: LoadMcloudPerformanceFlags present without markers; "
          "manual intervention required")
    sys.exit(1)
else:
    has_block = False  # fresh injection below

# ---- 依赖确认 / 自动补齐 include ----
for inc in ("base/base_paths.h", "base/command_line.h",
            "base/path_service.h", "base/strings/string_util.h"):
    assert ('#include "%s"' % inc) in s, "missing include: " + inc
if '#include "base/strings/string_split.h"' not in s:
    anchor = '#include "base/path_service.h"\n'
    assert anchor in s, "path_service.h anchor not found for include insertion"
    s = s.replace(anchor, anchor + '#include "base/strings/string_split.h"\n', 1)
    print("added include: base/strings/string_split.h")
# v2 用 ReadFileToStringWithMaxSize。注意：M151 树中该头已迁移到
# base/files/file_util.h（旧 base/file_util.h 不存在，2026-10-08 构建实证，
# 缺陷 D33）；两个路径任一已在文件中即视为满足，都没有才补新路径。
if ('#include "base/files/file_util.h"' not in s and
        '#include "base/file_util.h"' not in s):
    anchor = '#include "base/path_service.h"\n'
    assert anchor in s, "path_service.h anchor not found for file_util include"
    s = s.replace(anchor, anchor + '#include "base/files/file_util.h"\n', 1)
    print("added include: base/files/file_util.h")

LOADER = r'''
// --- MCloud Browser: built-in performance startup flags (mcloud_flags.txt) ---
// loader v5: line parsing via string_view::substr (no raw pointer arithmetic,
// clean under -Wunsafe-buffer-usage) on top of v4 (shared command-line byte
// budget for every appended switch, D40), v3 (merged-feature-list cap, D39)
// and v2 (single-pass accumulation, user-first merge, capped read).
// Reads `mcloud_flags.txt` from the executable directory (max 1 MiB) and
// appends the flags to the current process command line. User-specified
// switches take precedence:
//  - plain switches are skipped when the user already provided them;
//  - enable/disable-features are merged with the USER list placed FIRST,
//    because base::FeatureList::RegisterOverride() uses try_emplace()
//    (first entry per name wins), so user state and per-entry parameters
//    override same-named built-ins.
// Appended switches are inherited by child processes, and CreateProcessW caps
// a command line at 32767 chars, so the loader enforces a byte budget: an
// over-budget entry is skipped with a warning instead of poisoning every child
// launch (oversized lists previously made the GPU process unlaunchable =>
// FATAL "GPU process isn't usable", bug-review D39/D40).
// See docs/architecture/performance-build-technical-spec.md section 4.1.1.
void LoadMcloudPerformanceFlags() {
  base::FilePath exe_dir;
  if (!base::PathService::Get(base::DIR_EXE, &exe_dir)) {
    return;
  }
  const base::FilePath flags_path = exe_dir.AppendASCII("mcloud_flags.txt");
  std::string contents;
  if (!base::ReadFileToStringWithMaxSize(flags_path, &contents, 1u << 20)) {
    return;
  }

  base::CommandLine* command_line = base::CommandLine::ForCurrentProcess();

  // Total byte budget for everything appended here, and the smaller sub-budget
  // for plain (non-feature) switches. Keeping half of the budget free for the
  // feature lists is deliberate: they are the load-bearing part of the file,
  // and their merge happens after the loop.
  constexpr size_t kMaxAppendedBytes = 24u * 1024u;
  constexpr size_t kMaxPlainSwitchBytes = 12u * 1024u;
  size_t appended_bytes = 0;
  size_t plain_bytes = 0;

  std::string builtin_enable;
  std::string builtin_disable;
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
    const size_t equals = line.find('=');
    // substr() over string_view keeps this warning-free under clang's
    // -Wunsafe-buffer-usage (raw `line.data() + n` arithmetic is flagged even
    // when provably in range); both call sites below are guarded by
    // StartsWith("--") above and by find() returning an index < size().
    if (equals != std::string_view::npos) {
      switch_name = std::string(line.substr(2, equals - 2));
      value = std::string(line.substr(equals + 1));
      // Strip paired double quotes (supports --js-flags="... ...").
      if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
        value = value.substr(1, value.size() - 2);
      }
    } else {
      switch_name = std::string(line.substr(2));
    }
    if (switch_name.empty()) {
      continue;
    }

    if (switch_name == switches::kEnableFeatures) {
      if (!builtin_enable.empty()) {
        builtin_enable.push_back(',');
      }
      builtin_enable += value;
    } else if (switch_name == switches::kDisableFeatures) {
      if (!builtin_disable.empty()) {
        builtin_disable.push_back(',');
      }
      builtin_disable += value;
    } else if (!command_line->HasSwitch(switch_name)) {
      // D40: cost = "--name=" + value + separator/NUL headroom.
      const size_t cost = switch_name.size() + value.size() + 5;
      if (cost > kMaxPlainSwitchBytes - plain_bytes ||
          cost > kMaxAppendedBytes - appended_bytes) {
        LOG(WARNING) << "MCloud flags: --" << switch_name
                     << " skipped by command-line budget (plain "
                     << plain_bytes << "/" << kMaxPlainSwitchBytes
                     << ", total " << appended_bytes << "/"
                     << kMaxAppendedBytes << " bytes; bug-review D40).";
        continue;
      }
      plain_bytes += cost;
      appended_bytes += cost;
      command_line->AppendSwitchASCII(switch_name, value);
    }
  }

  // D39/D40 guard: merged feature lists beyond the remaining budget overflow
  // child-process command-line limits (CreateProcessW caps at 32767 chars),
  // which makes the GPU process unlaunchable and the browser FATAL("GPU process
  // isn't usable"). Skip the built-in merge with a warning instead of poisoning
  // every child launch; the user's own switch (if any) is left untouched.
  auto merge_user_first = [command_line, &appended_bytes](
                              std::string_view switch_name,
                              const std::string& builtin) {
    if (builtin.empty()) {
      return;
    }
    std::string merged = command_line->HasSwitch(switch_name)
                             ? command_line->GetSwitchValueASCII(switch_name)
                             : std::string();
    if (!merged.empty()) {
      merged += ",";
    }
    merged += builtin;
    const size_t cost = switch_name.size() + merged.size() + 5;
    if (cost > kMaxAppendedBytes - appended_bytes) {
      LOG(WARNING) << "MCloud flags: merged --" << switch_name << " is "
                   << merged.size() << " bytes, exceeding the remaining "
                   << kMaxAppendedBytes - appended_bytes
                   << "-byte command-line budget; built-in features skipped to "
                   << "keep child launches usable (bug-review D39/D40).";
      return;
    }
    appended_bytes += cost;
    command_line->AppendSwitchASCII(switch_name, merged);
  };
  merge_user_first(switches::kEnableFeatures, builtin_enable);
  merge_user_first(switches::kDisableFeatures, builtin_disable);
}
// --- MCloud Browser: end ---

'''

# ---- 升级路径：树内已有标记块 → 内容不同才整体替换 ----
# 索引必须在 include 补齐完成后重新计算（include 插入会平移文本位置）。
if has_block:
    want = LOADER.strip("\n")
    i = s.index(LOADER_BEGIN)
    j = s.index(LOADER_END) + len(LOADER_END)
    if s[i:j] == want:
        print("loader already up to date (content match), nothing to do")
        sys.exit(0)
    if not re.search(r"\n(  //)? *LoadMcloudPerformanceFlags\(\);", s):
        print("ERROR: loader block found but call site missing; "
              "manual intervention required")
        sys.exit(1)
    s = s[:i] + want + s[j:]
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("loader block replaced in place (content differed from repo version)")
    sys.exit(0)

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
