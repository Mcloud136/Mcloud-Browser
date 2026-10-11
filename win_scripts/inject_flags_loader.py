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
# v6：浏览器进程限定（D58）+ UTF-8 BOM 剥离（D57）。
# v7（2026-10-11，缺陷 D105）：**安装版布局回退查找**。setup.exe 对 Application 根目录
# 只搬固定清单（chrome.exe / chrome_proxy.exe / VisualElementsManifest.xml），根级
# chrome.release 条目不会被安装——实测干净系统安装后包内的 mcloud_flags.txt 根本不落地。
# 文件改登记到 %(VersionDir)s（版本目录是整目录搬迁），加载器则在 exe 同目录找不到时
# 到 exe_dir\<版本号>\ 里找（该目录必须同时含 chrome.dll 才算数）。
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

# v7（D105）需要 FileEnumerator（在安装版里找版本目录）与 base::Version
# （多个版本目录并存时挑最新的那个）。锚点用 file_util.h，它由上面一段保证存在。
_inc_anchor = None
for cand in ('#include "base/files/file_util.h"\n', '#include "base/file_util.h"\n'):
    if cand in s:
        _inc_anchor = cand
        break
assert _inc_anchor, "no file_util include to anchor the v7 includes against"
for inc in ('#include "base/files/file_enumerator.h"\n', '#include "base/version.h"\n'):
    if inc not in s:
        s = s.replace(_inc_anchor, _inc_anchor + inc, 1)
        print("added include:", inc.strip())

LOADER = r'''
// --- MCloud Browser: built-in performance startup flags (mcloud_flags.txt) ---
// loader v8: resolve the flags file from base::DIR_MODULE -- the directory that
// actually hosts chrome.dll, matching upstream GetModulePath -- so a stray
// root-level copy can no longer shadow the installed payload file (D109), on top
// of v7: installed-layout lookup (D105);
// v6: browser-process-only guard (D58) + UTF-8 BOM strip (D57), v5: line parsing
// via string_view::substr (no raw pointer arithmetic, clean under
// -Wunsafe-buffer-usage), v4 (shared command-line byte budget for every appended
// switch, D40), v3 (merged-feature-list cap, D39) and v2 (single-pass
// accumulation, user-first merge, capped read).
// Reads `mcloud_flags.txt` (max 1 MiB) and appends the flags to the current
// process command line. User-specified switches take precedence:
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

// D105: in an *installed* build chrome.exe sits in `Application\` while the
// payload (chrome.dll and everything else registered under %(VersionDir)s) is
// moved as one directory into `Application\<version>\`. setup.exe copies only a
// fixed list of root files (chrome.exe / chrome_proxy.exe /
// chrome.VisualElementsManifest.xml), so a root-level chrome.release entry is
// packed into chrome.7z and then never installed -- verified with a clean
// `--system-level` install plus --verbose-logging on 2026-10-11. The file is
// therefore registered under %(VersionDir)s, and this helper finds it. Returns
// an empty path when no payload directory carries it.
base::FilePath FindInstalledMcloudFlagsPath(const base::FilePath& exe_dir) {
  base::FilePath best;
  std::string best_version_string;
  base::FileEnumerator dirs(exe_dir, /*recursive=*/false,
                            base::FileEnumerator::DIRECTORIES);
  for (base::FilePath child = dirs.Next(); !child.empty(); child = dirs.Next()) {
    // A payload directory must hold chrome.dll too; that keeps unrelated
    // sub-directories (locales/, Dictionaries/) out of consideration.
    if (!base::PathExists(child.AppendASCII("chrome.dll"))) {
      continue;
    }
    const base::FilePath candidate = child.AppendASCII("mcloud_flags.txt");
    if (!base::PathExists(candidate)) {
      continue;
    }
    // Multiple versions can coexist after an upgrade; take the newest.
    // M155's base::Version has no NewFromString()/GreaterThan() -- it is built
    // from a string_view and compared through the free operators (first build
    // attempt failed on exactly that, 2026-10-11).
    const std::string name = child.BaseName().AsUTF8Unsafe();
    const base::Version version(name);
    if (!version.IsValid()) {
      continue;
    }
    if (best.empty() || version > base::Version(best_version_string)) {
      best_version_string = name;
      best = candidate;
    }
  }
  return best;
}

void LoadMcloudPerformanceFlags() {
  base::CommandLine* command_line = base::CommandLine::ForCurrentProcess();

  // D58: only the browser process needs to read the file. ContentMain calls
  // BasicStartupComplete() in EVERY process (content_main_runner_impl.cc:964),
  // so without this guard each renderer/GPU/utility process re-reads and
  // re-parses the file at launch -- and re-applies the budget against its own
  // inherited command line, which can make a child drop entries the browser
  // kept. Children already receive the resolved overrides (browser -> child
  // command line + field-trial shared memory), so skipping the read loses
  // nothing.
  if (command_line->HasSwitch(switches::kProcessType)) {
    return;
  }

  base::FilePath exe_dir;
  if (!base::PathService::Get(base::DIR_EXE, &exe_dir)) {
    return;
  }
  // D109: "which directory holds the program" has to be answered the way upstream
  // answers it -- by where chrome.dll is, not where chrome.exe is.
  // main_dll_loader_win.cc:175-191 (GetModulePath) tries
  // `<exe_dir>\<chrome::kChromeVersion>\chrome.dll` first and only then
  // `<exe_dir>\chrome.dll`, so in an installed build the running program lives in
  // the version directory while `Application\` holds a 4 MB launcher stub.
  // base::DIR_MODULE is exactly that directory (base_paths.cc:68 derives it from
  // FILE_MODULE, and this code is compiled into chrome.dll), so it is the correct
  // first candidate for every layout: version dir when installed, exe dir when
  // flat/dev/portable. v7 asked DIR_EXE first, which let a stray
  // `Application\mcloud_flags.txt` -- and one has existed on this machine since
  // the D104 investigation, left there by a manual copy -- silently shadow the
  // packaged file forever; the runtime oracle mirrored the same order, so the
  // gates read the shadowed copy and stayed green (reproduced by
  // .bugreview/loader_precedence_test.py, verdict ROOT before v8).
  base::FilePath module_dir;
  if (!base::PathService::Get(base::DIR_MODULE, &module_dir)) {
    module_dir = exe_dir;
  }
  base::FilePath flags_path = module_dir.AppendASCII("mcloud_flags.txt");
  std::string contents;
  bool loaded = base::ReadFileToStringWithMaxSize(flags_path, &contents, 1u << 20);
  if (!loaded && module_dir != exe_dir) {
    // Flat layouts keep the file next to chrome.exe; there DIR_MODULE == DIR_EXE
    // already, so this branch only runs when the module directory genuinely
    // lacks the file.
    flags_path = exe_dir.AppendASCII("mcloud_flags.txt");
    loaded = base::ReadFileToStringWithMaxSize(flags_path, &contents, 1u << 20);
    if (!loaded) {
      contents.clear();
    }
  }
  if (!loaded) {
    // Last resort: newest payload directory that carries the file (D105).
    contents.clear();
    flags_path = FindInstalledMcloudFlagsPath(exe_dir);
    if (flags_path.empty() ||
        !base::ReadFileToStringWithMaxSize(flags_path, &contents, 1u << 20)) {
      // D146: this used to be a bare `return`, so losing the whole runtime
      // optimisation set produced *no* in-process signal at all -- exactly the
      // D105 release blocker (build and packaging both succeeded, the installed
      // browser simply ran without any of the flags, silently).
      // Caveat, verified against M155: this runs from
      // ChromeMainDelegate::BasicStartupComplete (chrome_main_delegate.cc:1372),
      // while InitLogging() only happens later in PreSandboxStartup
      // (chrome_main_delegate.cc:1756). So this warning reaches
      // OutputDebugString/a attached debugger, NOT the user's console, even with
      // --enable-logging=stderr. The authoritative detection therefore remains
      // the external oracle .bugreview/flag_runtime_state.py; this line exists
      // so the failure is at least diagnosable rather than invisible.
      LOG(WARNING) << "MCloud flags: mcloud_flags.txt not found (tried module dir "
                   << module_dir << ", exe dir " << exe_dir
                   << ", and installed payload dirs) -- starting with upstream "
                      "defaults, all built-in performance flags are INACTIVE.";
      return;
    }
  }
  // D57: strip a UTF-8 BOM. Windows PowerShell 5.1 `Set-Content -Encoding UTF8`
  // and some editors write one; the parser requires lines to start with "--",
  // so a BOM silently drops the first line (a comment today, a flag tomorrow --
  // the same failure mode as D48).
  if (contents.size() >= 3 &&
      static_cast<unsigned char>(contents[0]) == static_cast<unsigned char>(0xEF) &&
      static_cast<unsigned char>(contents[1]) == static_cast<unsigned char>(0xBB) &&
      static_cast<unsigned char>(contents[2]) == static_cast<unsigned char>(0xBF)) {
    contents.erase(0, 3);
  }

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
    # D62：块内容一致不等于"注入完整"。调用点若被上游改写或被手工删除，加载器就变成
    # 存在但永不运行的死代码（静默失效，与 D47 同族）。因此两种分支都必须先校验调用点。
    if not re.search(r"\n(  //)? *LoadMcloudPerformanceFlags\(\);", s):
        print("ERROR: loader block present but the call to "
              "LoadMcloudPerformanceFlags() is missing from "
              "BasicStartupComplete(); manual intervention required")
        sys.exit(1)
    if i >= j:
        # 标记顺序异常（文件被破坏或手工编辑过）时，继续替换会把中间内容复制成重复，
        # 直接写坏源文件；停下让人处理。
        print("ERROR: LOADER_END at %d is not after LOADER_BEGIN at %d; "
              "refusing to rewrite %s" % (j, i, p))
        sys.exit(1)
    if s[i:j] == want:
        print("loader already up to date (content match, call site verified), nothing to do")
        sys.exit(0)
    s = s[:i] + want + s[j:]
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("loader block replaced in place (content differed from repo version)")
    sys.exit(0)

# ---- 注入点 1：匿名命名空间开头 ----
# D63b：用整行匹配定位，不再依赖"namespace { 之后恰好有一个换行"的偏移量假设；
# 上游若把匿名命名空间写成 `namespace {` 后跟空行/注释，旧的 idx+len+1 会把加载器
# 插到错误位置（编译期才暴露，且报错信息与真实原因无关）。
_mm_ns = re.search(r"\nnamespace \{\n", s)
assert _mm_ns, "line-anchored 'namespace {' not found (upstream file shape changed?)"
insert_pos = _mm_ns.end()
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
