# 工具：在 chromium 树（任意上游基线）上应用 MCloud 的源码级默认值修改。
# 采用定点单点修改（幂等），避免整体覆盖带来的跨版本漂移（2026-08-06 起，
# 取代 copy_essentials.py 整体复制以下三个文件的旧方案）：
#   1. media/base/media_switches.cc          kD3D12VideoDecoder 默认启用
#   2. chrome/browser/background/extensions/background_mode_manager.cc
#                                            kBackgroundModeEnabled 默认 false
#   3. chrome/browser/net/default_dns_over_https_config_source.cc
#                                            DoH 默认模式改 kSecure + doh.pub 模板
#                                            （2026-11-09 实测：kAutomatic 不生效）
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

# 3. DoH：默认模式与模板由下方 3b 段统一接管（旧的「仅校验 kAutomatic」已移除——# 3b. DoH：默认模式改 kSecure + doh.pub 模板（2026-11-09 实测驱动，第二次修正）
#
# 为什么必须是 kSecure，而不是上一版试过的「kAutomatic + 预置模板」：
#   实测（同机、同二进制，只改配置；判据是 netstat 抓到的活动连接）：
#     - secure    + 模板 → 命中 5 条到 1.12.12.12:443 / 120.53.53.53:443
#     - automatic + 模板 → 全新 profile 零配置，0 条（两次复现）
#   源码原因：net/dns/host_resolver_manager.cc:1372-1377。kAutomatic 下若
#   DnsClient::FallbackFromSecureTransactionPreferred() 返回 true，则**只发明文查询**；
#   该函数的判据是 NumAvailableDohServers()==0（net/dns/dns_client.cc:233）。
#   而「服务器可用」只能由一次成功的 DoH 事务或一次 DoH 探测来记录，探测只服务于
#   「自动升级」路径（host_resolver_manager.cc:1953-1962）。模板是预置的、不走升级，
#   于是没人发起探测 —— 形成闭环：不可用→只发明文→永远不会变可用。
#   结论：kAutomatic + 预置模板 = 纯明文 DNS，netlog 里的 servers 字段只是配置对象
#   携带的副本，不代表被使用。
#
# 代价（必须清楚）：kSecure 没有明文回退。若所在网络封了到 doh.pub 的 443，域名解析
#   直接失败、页面打不开。用户在「设置 → 隐私和安全 → 安全 DNS」改回「自动」即可恢复。
#   默认只留 DNSPod（doh.pub）一个模板；阿里云 dns.alidns.com 已在第 4 步加入下拉列表，
#   用户可自行切换（需要双模板时可写成空格分隔的两个 URL）。
DOH_DEFAULT_TEMPLATE = "https://doh.pub/dns-query"
DOH_CFG = SRC + r"\chrome\browser\net\default_dns_over_https_config_source.cc"

_doh_target = (
    "    local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsMode,\n"
    "                                     base::Value(SecureDnsConfig::ModeToString(\n"
    "                                         net::SecureDnsMode::kSecure)));\n"
    "    // MCloud: kAutomatic + 预置模板实测不启用 DoH（见脚本第 3b 段的长注释），\n"
    "    // 故默认设为 kSecure；代价是无明文回退，用户可在设置里改回「自动」。\n"
    "    local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsTemplates,\n"
    '                                     base::Value("%s"));\n'
    "  }" % DOH_DEFAULT_TEMPLATE
)

# 两种可能的「改动前」形态：上游原样（只有 mode），以及上一版 MCloud 补丁（mode+模板）。
_doh_from_upstream = (
    "    local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsMode,\n"
    "                                     base::Value(SecureDnsConfig::ModeToString(\n"
    "                                         net::SecureDnsMode::kAutomatic)));\n"
    "  }"
)
_doh_from_v1 = (
    "    local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsMode,\n"
    "                                     base::Value(SecureDnsConfig::ModeToString(\n"
    "                                         net::SecureDnsMode::kAutomatic)));\n"
    "    // MCloud: kAutomatic 单独存在不会启用 DoH（自动升级只匹配系统 DNS 的\n"
    "    // 53 端口 IP），必须给默认模板才真正走 DoH，失败仍可回退明文。\n"
    "    local_state->SetDefaultPrefValue(prefs::kDnsOverHttpsTemplates,\n"
    '                                     base::Value("%s"));\n'
    "  }" % DOH_DEFAULT_TEMPLATE
)

_doh_s = io.open(DOH_CFG, encoding="utf-8").read()
if _doh_target in _doh_s:
    print("  [skip] DoH 默认 secure + %s（已是目标状态）" % DOH_DEFAULT_TEMPLATE)
else:
    _hit = None
    for _cand, _label in ((_doh_from_v1, "上一版 automatic+模板补丁"),
                          (_doh_from_upstream, "上游原样")):
        if _cand in _doh_s:
            _hit, _label_hit = _cand, _label
            break
    if _hit is None:
        print("  [WARN] DoH 默认值：未找到已知形态，请人工检查上游是否变更")
        sys.exit(1)
    _doh_s = _doh_s.replace(_hit, _doh_target, 1)
    io.open(DOH_CFG, "w", encoding="utf-8", newline="\n").write(_doh_s)
    print("  [done] DoH 默认 secure + %s（由「%s」改写）"
          % (DOH_DEFAULT_TEMPLATE, _label_hit))

# 4. DoH：在可信提供方列表加入 DNSPod / 阿里云 公共 DNS（下拉选择 + 自动升级）
#    权威列表位于 net/dns/public/doh_provider_entry.cc 的 DohProviderEntry::GetList()。
#    chrome://settings/security 的「安全 DNS」解析器下拉框从该列表读取
#    display_globally=true 且 ui_name / privacy_policy 非空的条目。
#    端点以官方域名为准（DNSPod 2024-09-29 起不再公开推荐 IP 接入，域名 doh.pub 为主推；
#    阿里云 dns.alidns.com 为官方 DoH）。不固定 endpoint IP，由正常 DNS 解析域名。
doh_list = SRC + r"\net\dns\public\doh_provider_entry.cc"
doh_old = '       }})));'
doh_new = (
    '       },\n'
    '       {\n'
    '           "DNSPod",\n'
    '           MAKE_STATIC_STORAGE_BASE_FEATURE(kDohProviderDnspod,\n'
    '                                            base::FEATURE_ENABLED_BY_DEFAULT),\n'
    '           {"119.29.29.29", "119.29.28.28"},\n'
    '           /*dns_over_tls_hostnames=*/{"dot.pub"},\n'
    '           "https://doh.pub/dns-query",\n'
    '           /*ui_name=*/"DNSPod Public DNS (腾讯)",\n'
    '           /*privacy_policy=*/"https://www.dnspod.cn/Products/Public.DNS",\n'
    '           /*display_globally=*/true,\n'
    '           /*display_countries=*/{},\n'
    '       },\n'
    '       {\n'
    '           "Aliyun",\n'
    '           MAKE_STATIC_STORAGE_BASE_FEATURE(kDohProviderAliyun,\n'
    '                                            base::FEATURE_ENABLED_BY_DEFAULT),\n'
    '           {"223.5.5.5", "223.6.6.6", "2400:3200::1", "2400:3200:baba::1"},\n'
    '           /*dns_over_tls_hostnames=*/{"dns.alidns.com"},\n'
    '           "https://dns.alidns.com/dns-query",\n'
    '           /*ui_name=*/"Aliyun Public DNS (阿里云)",\n'
    '           /*privacy_policy=*/"https://alidns.com/",\n'
    '           /*display_globally=*/true,\n'
    '           /*display_countries=*/{},\n'
    '       }})));'
)
patch_file(doh_list, doh_old, doh_new, "DoH 列表加入 DNSPod / 阿里云")

# 5. DoH：同步 histograms.xml 的 DohProviderId 枚举（LINT.IfChange / LINT.ThenChange 契约）
hist = SRC + r"\tools\metrics\histograms\metadata\net\histograms.xml"
hist_old = (
    '  <variant name="Spectrum2."\n'
    '      summary="Charter Communications/Spectrum DoH endpoint2."/>\n'
    '</variants>'
)
hist_new = (
    '  <variant name="Spectrum2."\n'
    '      summary="Charter Communications/Spectrum DoH endpoint2."/>\n'
    '  <variant name="Aliyun."\n'
    '      summary="Aliyun (Alibaba) public DNS."/>\n'
    '  <variant name="DNSPod."\n'
    '      summary="DNSPod (Tencent) public DNS."/>\n'
    '</variants>'
)
patch_file(hist, hist_old, hist_new, "histograms.xml 同步 DohProviderId")

# 6. 快捷方式名固定为 Chromium（与 IDS_PRODUCT_NAME 解耦）
#
# chrome/installer/util/install_util.cc:583 里：
#     std::wstring InstallUtil::GetShortcutName() {
#       return installer::GetLocalizedString(IDS_PRODUCT_NAME_BASE);
#     }
# 也就是说桌面/开始菜单/任务栏快捷方式名**直接取自 IDS_PRODUCT_NAME**。
# 层一把 IDS_PRODUCT_NAME 改成 Mcloud 之后，快捷方式随之变成 "Mcloud.lnk"（实测
# C:\Users\Public\Desktop\Mcloud.lnk）。需求是：关于页显示 Mcloud，快捷方式仍叫
# Chromium —— 两者必须解耦，故在此固定返回值。
sh = SRC + r"\chrome\installer\util\install_util.cc"
sh_old = (
    "std::wstring InstallUtil::GetShortcutName() {\n"
    "  // IDS_PRODUCT_NAME is automatically mapped to the mode-specific shortcut\n"
    "  // name; see MODE_SPECIFIC_STRINGS in prebuild/create_string_rc.py.\n"
    "  return installer::GetLocalizedString(IDS_PRODUCT_NAME_BASE);\n"
    "}"
)
sh_new = (
    "std::wstring InstallUtil::GetShortcutName() {\n"
    "  // MCloud: shortcut name is pinned to \"Chromium\" on purpose.\n"
    "  // Upstream derives it from IDS_PRODUCT_NAME_BASE, but MCloud overrides\n"
    "  // IDS_PRODUCT_NAME to \"Mcloud\" for the About page. Keeping the two\n"
    "  // coupled would rename the desktop/start-menu shortcut to Mcloud.lnk,\n"
    "  // which is not wanted. Decouple here instead of duplicating the string.\n"
    "  return L\"Chromium\";\n"
    "}"
)
patch_file(sh, sh_old, sh_new, "快捷方式名固定 Chromium（与 IDS_PRODUCT_NAME 解耦）")

print("完成。")
