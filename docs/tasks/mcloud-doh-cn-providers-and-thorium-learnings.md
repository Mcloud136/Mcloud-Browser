# MCloud 上游借鉴项与 DoH 可信列表改造（交付开发 AI 文档）

> 用途：把「上游 Thorium / 新版本 Chromium 有哪些可借鉴」与「DoH 可信下拉列表改造（已落地 DNSPod、阿里云）」
> 这两件事整理成一份自包含文档，供开发 AI 直接执行与复核。
> 生成日期：2026-11-08。基线：M155 构建树 `D:\wxmuma\chromium-src-155\src`，分叉仓库 `D:\wxmuma\thorium`。

---

## 0. 结论速览（先读这里）

1. **上游 Thorium 没有专门的「TLS 版本」补丁。** 网上流传的「TLS 握手续航 15–20%」本质是
   AVX2 / AES-NI 在 BoringSSL 上的**编译加速副作用**；MCloud 本就做 AVX2 原生编译（且
   `compiler_opt.gni` 带 AES 指令），该收益**已经继承**，没有可额外抄的 TLS 专项。
2. **真正值得借鉴的三件事**：
   - DoH secure-mode 加固（精选可信模板，默认走安全模式）—— 本次已落地并扩展了可信列表；
   - QUIC 连接迁移健壮性 flag（混合网络 / 切网场景的稳定性）；
   - **跟随内核升级白捡**的 BoringSSL 后量子（ML-DSA / ML-KEM）、ECH GREASE、ALPS 等安全能力。
3. **本次已实现**：DoH 下拉可信列表新增 `DNSPod`、`Aliyun（阿里云）公共 DNS`，全局可见、支持自动升级。
   改动通过 MCloud 幂等注入器 `win_scripts/apply_mcloud_source_defaults.py` 落地，已对 M155 构建树实跑验证。

---

## 1. 上游 Thorium / 新版本可借鉴项（已逐项核实）

| 借鉴点 | 来源 | 状态 | 说明 / MCloud 动作 |
|---|---|---|---|
| DoH Secure Mode + 精选可信模板 | Cromite / uazo，Thorium 沿用 | **本次强化** | 最小头机制 MCloud 已有（`dns_transaction.cc` 的 `LOAD_MINIMAL_HEADERS`）；本次新增可信提供方 DNSPod / 阿里云并默认全局可见 |
| Disable Captive Portals Detection | Cromite / uazo | 可选 | 企业/校园网场景可能依赖 captive portal，默认不抄，按需评估 |
| `disable_fieldtrial_testing_config = true` | Thorium | **已照搬** | `args.gn:21`、`win_args_mcloud.gn` 已设置，稳定性 + 可复现，M158 迁移后需保持 |
| `QuicAlwaysCancelPreExistingProbingOnMigration` | M158 新增 | 进 A/B 队列 | 笔记本切 Wi-Fi/蜂窝、多宿主场景减少连接卡死 |
| `QuicUseReadMultiple` | **M155 已存在，非 M158 新增** | 旧候选复核 | QUIC socket 读吞吐；官方 `net/base/features.cc` M155:879 / M158:892 均声明、默认 DISABLED，按 `docs/tasks/m155-perf-features.md` Tier A 旧候选处理 |
| `HttpChunkedDecoderInRust` | M158 新增 | 评估 | net 解码可靠性，需冒烟测试 |
| BoringSSL 后量子 + ECH GREASE + ALPS | Chromium M155+ | 跟随内核 | 升级内核即获得，最大安全收益来自「保持内核最新」而非任何开关 |
| **0-RTT（`EnableTLS13EarlyData`）** | — | **明确不采纳** | 重放攻击风险，且非性能瓶颈；MCloud 已默认关闭并列为安全决策 |
| 隐私类：GPC / Do Not Track / 禁用 Privacy Sandbox | Thorium | 不抄 | 与性能/稳定性无关，且可能破坏部分站点 |

> 纠偏：本仓库 `mcloud_flags.txt` 历史上写过的 `EarlyData` 是一条**死声明**（D48/D142 证实从未生效），
> 不要为了「借鉴 Thorium」去默认开启 0-RTT。

---

## 2. DoH 可信列表下拉改造（已落地）

### 2.1 机制说明（开发 AI 必须知道）

- **下拉框数据来源**：`net/dns/public/doh_provider_entry.cc` 的 `DohProviderEntry::GetList()`。
  这是 Chromium 所有 DoH 提供方的权威列表（自动升级 + 设置页下拉共用）。
- **哪些条目进下拉**：`display_globally == true` **且** `ui_name` / `privacy_policy` 均非空。
  （`display_globally == false` 时，需 `display_countries` 命中本地国家码才显示，如 Cznic→CZ。）
- **自动升级**：当用户系统 DNS 命中条目的 `ip_addresses`（53 端口 IP）或 `dns_over_tls_hostnames`（DoT 主机名）时，
  自动模式会把明文/DoT 升级到该条目的 DoH 模板。
- **同步契约**：`tools/metrics/histograms/metadata/net/histograms.xml` 的 `DohProviderId` 枚举，
  与 `.cc` 通过 `LINT.IfChange / LINT.ThenChange` 绑定，新增提供方需同步加 variant（否则 presubmit 会报）。
- **MCloud 注入机制**：不要在分叉仓库直接改这份文件——它位于**构建树**。正确入口是
  `win_scripts/apply_mcloud_source_defaults.py` 的 `patch_file()`（幂等、带锚点替换），
  在构建时把改动注入到构建树对应文件。

### 2.2 新增条目（已注入 `chromium-src-155/src/net/dns/public/doh_provider_entry.cc`）

```cpp
       {
           "DNSPod",
           MAKE_STATIC_STORAGE_BASE_FEATURE(kDohProviderDnspod,
                                            base::FEATURE_ENABLED_BY_DEFAULT),
           {"119.29.29.29", "119.29.28.28"},
           /*dns_over_tls_hostnames=*/{"dot.pub"},
           "https://doh.pub/dns-query",
           /*ui_name=*/"DNSPod Public DNS (腾讯)",
           /*privacy_policy=*/"https://www.dnspod.cn/Products/Public.DNS",
           /*display_globally=*/true,
           /*display_countries=*/{},
       },
       {
           "Aliyun",
           MAKE_STATIC_STORAGE_BASE_FEATURE(kDohProviderAliyun,
                                            base::FEATURE_ENABLED_BY_DEFAULT),
           {"223.5.5.5", "223.6.6.6", "2400:3200::1", "2400:3200:baba::1"},
           /*dns_over_tls_hostnames=*/{"dns.alidns.com"},
           "https://dns.alidns.com/dns-query",
           /*ui_name=*/"Aliyun Public DNS (阿里云)",
           /*privacy_policy=*/"https://alidns.com/",
           /*display_globally=*/true,
           /*display_countries=*/{},
       }
```

**端点依据（官方，已联网核实）**：
- DNSPod 公共 DNS：官方 DoH `https://doh.pub/dns-query`。
  注：DNSPod 2024-09-29 起**不再公开推荐 IP 接入**（`https://1.12.12.12/dns-query` 等），
  域名 `doh.pub` 是官方主推接入方式，故模板用域名。公共 DNS IP `119.29.29.29 / 119.29.28.28` 用于自动升级匹配。
- 阿里云公共 DNS：官方 DoH `https://dns.alidns.com/dns-query`（RFC 8484，支持 TLS 1.2/1.3）。
  公共 DNS IP `223.5.5.5 / 223.6.6.6` 及 IPv6 `2400:3200::1 / 2400:3200:baba::1` 用于自动升级匹配。
- **未固定 endpoint IP**（条目的 `dns_over_https_server_ip_strs` 留空）：由正常 DNS 解析 `doh.pub` / `dns.alidns.com`，
  避免 anycast IP 漂移导致硬编码失效。

### 2.3 已落地的代码改动

1. `win_scripts/apply_mcloud_source_defaults.py`：新增 `#4 DoH 列表加入 DNSPod / 阿里云`
   与 `#5 histograms.xml 同步 DohProviderId` 两个 `patch_file()` 调用（幂等，锚点替换）。
2. 实跑验证（M155 构建树）：
   ```
   CR_DIR="D:/wxmuma/chromium-src-155/src" python win_scripts/apply_mcloud_source_defaults.py
   ```
   输出 `[done] DoH 列表加入 DNSPod / 阿里云`、`[done] histograms.xml 同步 DohProviderId`，锚点命中，括号结构与上游一致。

### 2.4 验证步骤（构建后执行）

- `chrome://settings/security` → 「安全 DNS」→ 下拉解析器列表应出现
  `DNSPod Public DNS (腾讯)` 与 `Aliyun Public DNS (阿里云)`。
- 选中其一 → 打开 `https://dnsleaktest.com` 确认出口 DNS 为该提供方。
- 自动模式验证：把系统 DNS 设为 `119.29.29.29`（DNSPod）或 `223.5.5.5`（阿里云），
  应自动升级到对应 DoH（`chrome://net-internals/#dns` 观察）。
- 编译期 DCHECK：下拉条目要求 `ui_name` / `privacy_policy` 非空（已满足）；`ip_addresses` 须为合法 IP（已满足）。

### 2.5 备选 / 收尾

- **若只想对中国区展示**（对齐上游区域提供方惯例）：把两条的 `display_globally` 改为 `false`，
  `display_countries` 改为 `{"CN"}`。当前为 `true` 以保证 MCloud 中国用户全局可见。
- **隐私政策链接**：当前 `privacy_policy` 指向官方产品页（`dnspod.cn/Products/Public.DNS`、`alidns.com/`）。
  如需更精确的隐私声明页，可替换为官方隐私政策 URL（仅影响下拉里展示的链接，不影响功能）。
- **M158 升级**：上游 `doh_provider_entry.cc` 列表可能增删条目，升级后需重新跑 `apply_mcloud_source_defaults.py`
  并由 `patch_file` 的「未找到锚点」告警核验锚点是否漂移。

### 2.6 M158 升级复核与已知风险（2026-11-08，官方源取证）

以 **Chromium 官方 tag `158.0.8127.30`**（`chromium.googlesource.com`，非 GitHub 镜像）复核：

| 项 | 结果 |
|---|---|
| `doh_provider_entry.cc` 注入锚点 `'       }})));'` | 唯一 1 处，位于 `:391`（`Spectrum2` 条目之后） |
| `histograms.xml` 注入锚点（Spectrum2 块 + `</variants>`） | 唯一 1 处（`</variants>` 全文件 33 处，但带 Spectrum2 前缀的仅 1 处） |
| `DohProviderEntry` 构造函数 | M155 与 M158 **签名一致**（9 参数，第 10 个 `dns_over_https_server_ip_strs` 有默认值），注入条目字段数匹配 |
| `MAKE_STATIC_STORAGE_BASE_FEATURE` / LINT 契约 | 仍在（26 处）/ 仍在（`.cc:392`、`xml:125`） |

⇒ **升级后注入可重放、结构兼容**。三项风险经复核后结论如下：

1. **模板缺 `{?dns}` —— 已实测排除，无需修改**。官方 M158 的 26 个 DoH 模板全部带 `{?dns}`，注入的两条不带 ⇒ Chromium 对无占位符模板走 RFC 8484 POST。2026-11-08 用真实 DNS wire 查询实测：`https://doh.pub/dns-query` 与 `https://dns.alidns.com/dns-query` 的 **POST 与 GET 均返回 HTTP 200 / `application/dns-message` / DNS rcode=0**（468 B、72 B 响应）。POST 路径可用，保持现有模板。
2. **variant 字母序 —— 仅上游合规，不阻塞本机构建**。`DohProviderId` 的 variant 按字母序排列，把 `Aliyun.` / `DNSPod.` 追加在 `Spectrum2.` 之后破坏顺序，可能触发上游 histograms presubmit；但该校验不属于 `autoninja` 编译链，不影响本分支出包。建议后续按字母序整理，不必赶在 M158 编译前。
3. **改注入文本会破坏幂等性（仍须记住）**：`patch_file()` 靠 `if new in s` 判「已注入」。一旦为修第 2 项而修改 `doh_new` / `hist_new`，在**已注入的 M155 树**上 `new in s` 会失败，而 `old`（`       }})));`）仍在 ⇒ 会执行 `s.replace(old, new, 1)` 造成**重复注入**（重复 feature 名，编译报错）。要改文本必须同时给 `patch_file()` 加「检测 `kDohProviderDnspod` 已存在」的迁移分支。

⇒ **结论：三项均不构成本次 M158 编译的阻塞，注入脚本保持现状即可**；升级时 `deploy_mcloud.py` 第 6 步会自动重放，全量编译通过后跑 §2.4 冒烟即可验收。

⚠ 至今只验证过注入器输出 `[done]`，**从未编译验证**；M158 全量编译是补齐这一环的机会。

---

## 3. 给开发 AI 的下一步

1. 把 `win_scripts/apply_mcloud_source_defaults.py` 的本次改动并入构建流水线（脚本已就绪、幂等，无需额外动作）。
2. M158 内核升级时：先升级、再跑 `apply` 脚本，按告警复核 DoH 列表锚点。
3. 把 §1 的 QUIC / net 健壮性 flag 纳入 A/B 队列（沿用现有 `ab_flags.py` 框架：单变量、同机成对、运行时回显证明），目标场景=混合网络：
   - **M158 新增**：`QuicAlwaysCancelPreExistingProbingOnMigration`（官方 `net/base/features.cc:875`）、`HttpChunkedDecoderInRust`（:1127）；
   - **旧候选复核**：`QuicUseReadMultiple`（M155 已存在，非新增）；
   - 三者均须先过 `guard_audit.py` 判 Windows 有效默认值，再进 A/B，不得直接写进 `mcloud_flags.txt`。
4. 维持「内核最新」为最高优先级安全/稳定性收益，不把 TLS 握手续航当作独立优化项。
5. 0-RTT 保持默认关闭（安全决策），不反向开启。
