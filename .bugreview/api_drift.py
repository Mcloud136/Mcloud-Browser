#!/usr/bin/env python3
"""api_drift.py - do the MCloud injection anchors / APIs / GN args still exist
in a candidate upstream Chromium rev?

Usage: python api_drift.py <rev> [<rev2> ...]

Everything is read from the git object store (`git show rev:path`, `git grep rev`),
so the working tree (still M151 and actively used by out/mcloud) is never touched.
"""
import re
import subprocess
import sys

SRC = r"D:\wxmuma\chromium-src\src"

# (label, path, needle, mode)  mode: "in" substring, "re" regex search, "count1"
ANCHORS = [
    ("delegate: namespace{", "chrome/app/chrome_main_delegate.cc", "namespace {", "in"),
    ("delegate: BasicStartupComplete 签名", "chrome/app/chrome_main_delegate.cc",
     r"std::optional<int> ChromeMainDelegate::BasicStartupComplete\(\) \{", "re"),
    ("delegate: include base_paths.h", "chrome/app/chrome_main_delegate.cc",
     '#include "base/base_paths.h"', "in"),
    ("delegate: include command_line.h", "chrome/app/chrome_main_delegate.cc",
     '#include "base/command_line.h"', "in"),
    ("delegate: include path_service.h", "chrome/app/chrome_main_delegate.cc",
     '#include "base/path_service.h"', "in"),
    ("delegate: include string_util.h", "chrome/app/chrome_main_delegate.cc",
     '#include "base/strings/string_util.h"', "in"),
    ("delegate: include content_switches.h", "chrome/app/chrome_main_delegate.cc",
     "content/public/common/content_switches.h", "in"),
    ("win/BUILD.gn: -msse3 锚点块", "build/config/win/BUILD.gn",
     'if (current_cpu == "x86" || current_cpu == "x64") {\n      cflags += [ "-msse3" ]', "in"),
    ("BUILDCONFIG: set_defaults(executable) 唯一", "build/config/BUILDCONFIG.gn",
     'set_defaults("executable") {', "count1"),
    ("BUILDCONFIG: set_defaults(shared_library) 唯一", "build/config/BUILDCONFIG.gn",
     'set_defaults("shared_library") {', "count1"),
    ("compiler/BUILD.gn: common_optimize_on_ldflags", "build/config/compiler/BUILD.gn",
     "common_optimize_on_ldflags", "in"),
    ("media_switches: kD3D12VideoDecoder 声明原文", "media/base/media_switches.cc",
     r"BASE_FEATURE\(kD3D12VideoDecoder,[^\n]*\)", "re"),
    ("bg_mode: RegisterBooleanPref 原文", "chrome/browser/background/extensions/background_mode_manager.cc",
     r"registry->RegisterBooleanPref\(prefs::kBackgroundModeEnabled, *(true|false)\)", "re"),
    ("bg_mode: SetBoolean 原文", "chrome/browser/background/extensions/background_mode_manager.cc",
     r"service->SetBoolean\(prefs::kBackgroundModeEnabled, *(true|false)\)", "re"),
    ("doh: 默认 kAutomatic", "chrome/browser/net/default_dns_over_https_config_source.cc",
     "net::SecureDnsMode::kAutomatic", "in"),
    ("base API: SplitStringPiece", "base/strings/string_split.h", r"SplitStringPiece", "re"),
    ("base API: SplitString(string_view 版)", "base/strings/string_split.h",
     r"(std::vector<std::string_view>|absl::string_view) ", "re"),
    ("base API: ReadFileToStringWithMaxSize", "base/files/file_util.h",
     "ReadFileToStringWithMaxSize", "in"),
    ("base API: StartsWith(CompareCase)", "base/strings/string_util.h",
     r"bool StartsWith\(", "re"),
    ("base API: PathService::Get", "base/path_service.h", r"static bool Get\(", "re"),
    ("base API: DIR_EXE", "base/base_paths.h", "DIR_EXE", "in"),
    ("base API: CommandLine::AppendSwitchASCII", "base/command_line.h",
     "AppendSwitchASCII", "in"),
    ("base API: CommandLine::GetSwitchValueASCII", "base/command_line.h",
     "GetSwitchValueASCII", "in"),
    ("switches: kEnableFeatures 定义处(base_switches.h)", "base/base_switches.h",
     "kEnableFeatures", "in"),
    ("switches: kDisableFeatures 定义处(base_switches.h)", "base/base_switches.h",
     "kDisableFeatures", "in"),
    ("delegate: include base_switches.h(实际取常量处)", "chrome/app/chrome_main_delegate.cc",
     "base/base_switches.h", "in"),
    ("feature API: RegisterOverride 语义仍为 try_emplace", "base/feature_list.cc",
     r"try_emplace|RegisterOverride", "re"),
]

GN_ARGS = [
    "use_sse3", "use_sse41", "use_sse42", "use_avx", "use_avx2", "use_fma",
    "use_avx512", "target_os", "target_cpu", "is_official_build", "is_debug",
    "dcheck_always_on", "symbol_level", "v8_symbol_level", "blink_symbol_level",
    "exclude_unwind_tables", "is_clang", "use_lld", "use_icf", "use_thin_lto",
    "thin_lto_enable_optimizations", "thin_lto_enable_cache",
    "enable_precompiled_headers", "treat_warnings_as_errors", "init_stack_vars_zero",
    "is_full_optimization_build", "use_polly", "use_bolt", "chrome_pgo_phase",
    "pgo_data_path", "v8_enable_fast_torque", "v8_enable_builtins_optimization",
    "v8_enable_maglev", "v8_enable_turbofan", "v8_enable_wasm_simd256_revec",
    "use_v8_context_snapshot", "optimize_webui", "win_enable_cfg_guards",
    "enable_rlz", "media_use_ffmpeg", "media_use_libvpx", "enable_hls_demuxer",
    "proprietary_codecs", "ffmpeg_branding", "enable_ffmpeg_video_decoders",
    "is_component_ffmpeg", "enable_library_cdms", "enable_widevine",
    "bundle_widevine_cdm",
]
# args that MCloud itself declares in //build/config/compiler_opt.gni (copied in)
MCLOUD_DECLARED = {"is_full_optimization_build", "use_polly", "use_bolt",
                   "use_sse3", "use_sse41", "use_sse42", "use_avx", "use_avx2",
                   "use_fma", "use_avx512"}


def show(rev, path):
    p = subprocess.run(["git", "-C", SRC, "show", "%s:%s" % (rev, path)],
                       capture_output=True, text=True, errors="replace", timeout=900)
    return p.stdout if p.returncode == 0 else None


def grep_count(rev, pattern, pathspec):
    cmd = ["git", "-C", SRC, "grep", "-I", "-h", "-E", pattern, rev, "--"] + pathspec
    out = subprocess.run(cmd, capture_output=True, text=True,
                         errors="replace").stdout
    return out


for rev in sys.argv[1:]:
    print("=" * 70)
    print("rev:", rev)
    cache = {}
    for label, path, needle, mode in ANCHORS:
        if path not in cache:
            cache[path] = show(rev, path)
        s = cache[path]
        if s is None:
            print("  %-46s FILE_MISSING (%s)" % (label, path))
            continue
        if mode == "in":
            ok = needle in s
            extra = ""
        elif mode == "re":
            m = re.search(needle, s)
            ok = bool(m)
            extra = (m.group(0).strip()[:70] if m else "")
        else:  # count1
            n = s.count(needle)
            ok = n == 1
            extra = "count=%d" % n
        print("  %-46s %s %s" % (label, "OK  " if ok else "DRIFT", extra))

    # GN args: one combined scan of assignment/declaration sites.
    # git grep is POSIX ERE: [[:space:]] not \s, no \b -- boundaries are enforced
    # afterwards in Python over whole matched lines (no -o).
    pat = "|".join("[A-Za-z0-9_.]*%s[[:space:]]*=" % re.escape(a) for a in GN_ARGS)
    out = grep_count(rev, pat, ["*.gn", "*.gni"])
    print("  --- GN 参数（上游声明/赋值点计数；0 = 上游无该名字） ---")
    missing = []
    counts = {}
    for a in GN_ARGS:
        n = len(re.findall(r"(?<![A-Za-z0-9_.])%s[ \t]*=" % re.escape(a), out))
        counts[a] = n
        if n == 0:
            missing.append(a)
            tag = "MCloud 自声明(compiler_opt.gni)" if a in MCLOUD_DECLARED else "MISSING"
            print("    %-36s 0  <%s>" % (a, tag))
    print("    其余 %d 个参数在上游有声明/赋值点" % (len(GN_ARGS) - len(missing)))
    truly_missing = [a for a in missing if a not in MCLOUD_DECLARED]
    print("  RESULT: %s" % ("GN 参数无失踪" if not truly_missing
                            else "上游已无此参数: " + ", ".join(truly_missing)))
