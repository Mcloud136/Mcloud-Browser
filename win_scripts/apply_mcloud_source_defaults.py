# 工具：在 chromium 树（任意上游基线）上应用 MCloud 的源码级默认值修改。
# 采用定点单点修改（幂等），避免整体覆盖带来的跨版本漂移（2026-08-06 起，
# 取代 copy_essentials.py 整体复制以下三个文件的旧方案）：
#   1. media/base/media_switches.cc          kD3D12VideoDecoder 默认启用
#   2. chrome/browser/background/extensions/background_mode_manager.cc
#                                            kBackgroundModeEnabled 默认 false
#   3. chrome/browser/net/default_dns_over_https_config_source.cc
#                                            无需修改（M151 上游默认已是 kAutomatic，
#                                            MCloud 的 M150 修复已被上游吸收）
import io
import sys

SRC = r"D:\wxmuma\chromium-src\src"

def patch_file(path, old, new, desc, ok_if_new_present=None):
    s = io.open(path, encoding="utf-8").read()
    if new in s:
        print("  [skip] %s（已是目标状态）" % desc)
        return
    if old not in s:
        print("  [WARN] %s：未找到锚点，请人工检查上游是否变更" % desc)
        sys.exit(1)
    s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)
    print("  [done] %s" % desc)

print("应用 MCloud 源码级默认值修改：")

# 1. D3D12 视频解码默认启用
patch_file(
    SRC + r"\media\base\media_switches.cc",
    "BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_DISABLED_BY_DEFAULT);",
    "BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_ENABLED_BY_DEFAULT);",
    "kD3D12VideoDecoder -> ENABLED_BY_DEFAULT",
)

# 2. 后台模式默认关闭（注册与激活两处）
patch_file(
    SRC + r"\chrome\browser\background\extensions\background_mode_manager.cc",
    "registry->RegisterBooleanPref(prefs::kBackgroundModeEnabled, true);",
    "registry->RegisterBooleanPref(prefs::kBackgroundModeEnabled, false);",
    "kBackgroundModeEnabled 注册默认 false",
)
patch_file(
    SRC + r"\chrome\browser\background\extensions\background_mode_manager.cc",
    "service->SetBoolean(prefs::kBackgroundModeEnabled, true);",
    "service->SetBoolean(prefs::kBackgroundModeEnabled, false);",
    "kBackgroundModeEnabled SetBoolean false",
)

# 3. DoH：确认上游默认已是 kAutomatic（不修改，仅校验）
doh = io.open(SRC + r"\chrome\browser\net\default_dns_over_https_config_source.cc",
              encoding="utf-8").read()
if "net::SecureDnsMode::kAutomatic" in doh:
    print("  [ok] DoH 默认 kAutomatic（上游已内置，无需修改）")
else:
    print("  [WARN] DoH 默认值异常，请人工检查")
    sys.exit(1)

print("完成。")
