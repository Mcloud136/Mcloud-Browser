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
import os
import sys

# D27: 与 deploy_mcloud.py 的 CR_DIR 机制保持一致
SRC = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")

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

# 1. D3D12 视频解码：不再翻转上游默认（阶段 3b 清理，2026-10-10 M155 升级期）
#
# 历史做法：把上游 kD3D12VideoDecoder 默认从 DISABLED 翻成 ENABLED，再由
# mcloud_flags.txt 的 --disable-features=D3D12VideoDecoder 抵回去 —— 净效果等于上游默认，
# 却多背一个源码 hunk（Intel 核显 D3D12 绿屏缺陷要求该解码器保持禁用）。
# 现在改为只校验上游默认，并且自愈：若树上还留着历史的 ENABLED 覆盖，回退为 DISABLED。
msw = SRC + r"\media\base\media_switches.cc"
DISABLED = "BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_DISABLED_BY_DEFAULT);"
ENABLED = "BASE_FEATURE(kD3D12VideoDecoder, base::FEATURE_ENABLED_BY_DEFAULT);"


def _norm(t):
    """D73：上游常把 BASE_FEATURE 拆成多行写，精确单行匹配会同时落空，
    于是既看不到 ENABLED 历史覆盖（自愈失效），也看不到 DISABLED（误报"形态已变更"）。
    先按原样匹配，匹配不到再用空白归一化的形态兜底。"""
    return " ".join(t.split())


_s = io.open(msw, encoding="utf-8").read()
_n = _norm(_s)
if ENABLED in _s:
    _s = _s.replace(ENABLED, DISABLED, 1)
    io.open(msw, "w", encoding="utf-8", newline="\n").write(_s)
    print("  [fixed] 回退历史覆盖：kD3D12VideoDecoder 恢复上游 DISABLED_BY_DEFAULT"
          "（禁用意图改由 mcloud_flags.txt 显式声明）")
elif DISABLED in _s or _norm(DISABLED) in _n:
    print("  [ok] kD3D12VideoDecoder 上游默认 DISABLED（无需覆盖，禁用由 flags 显式保证）"
          + ("，跨行声明形态" if DISABLED not in _s else ""))
elif _norm(ENABLED) in _n:
    print("  [WARN] 树上是跨行形态的 ENABLED 历史覆盖，不做盲改；请人工把该声明回退为 "
          "FEATURE_DISABLED_BY_DEFAULT 后重跑")
    sys.exit(1)
else:
    print("  [WARN] kD3D12VideoDecoder 声明形态已变更，请人工核对 media/base/media_switches.cc")
    sys.exit(1)

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
