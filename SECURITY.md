# 安全策略 · Security Policy

MCloud Browser（基于 Chromium 的 Windows x64 浏览器分支）

| 项 | 信息 |
|---|---|
| 维护者 | 狗木马（微笑木马） |
| 邮箱 | **wxmuma@qq.com** |
| 网站 | <https://www.wxmuma.cn> |
| 仓库 | <https://github.com/Mcloud136/Mcloud-Browser> |
| 当前内核 | Chromium **M158（158.0.8127.30）** |

---

## 支持范围

| 版本 | 是否接收安全修复 |
|---|---|
| 最新发布版（当前 `v158.0.8127.30`） | ✅ 是 |
| 更早的版本 | ❌ 否，请先升级到最新版 |

> ⚠ **本项目没有自动更新机制。** 安全修复只随新版本发布，存量用户**需要手动下载并重装**
> 才能获得。看到新版本发布后请尽快升级。

## 如何报告漏洞

### 1. 本分支自身的问题（推荐：私密报告）

优先使用 GitHub 的私密漏洞报告，内容不会公开可见：

<https://github.com/Mcloud136/Mcloud-Browser/security/advisories/new>

### 2. 邮件（重大漏洞 / 零日 / 不便用 GitHub 时）

发送到 **wxmuma@qq.com**，标题请加前缀 `[SECURITY]`。

建议在报告中包含：受影响版本、复现步骤或 PoC、影响面判断、以及是否希望匿名致谢。
**请勿在公开 Issue 中粘贴可直接利用的细节或 PoC。**

### 3. 一般性问题

非安全敏感的问题（功能异常、兼容性问题）请走 Issues：
<https://github.com/Mcloud136/Mcloud-Browser/issues>

### 4. Chromium 上游漏洞

如果问题出在 Chromium 内核本身，请直接报给上游：
<https://issues.chromium.org/>

本分支**不自研内核安全补丁**，内核层面的修复随内核升级继承。当前版本继承的规模见
[CHANGELOG](docs/CHANGELOG.md)：Chrome 156 stable 的 354 项、157 stable 的 213 项安全修复。
报给上游的同时可以抄送我一份，便于评估本分支的发版节奏。

## 响应预期

本项目为个人维护，按尽力而为（best effort）处理：

| 阶段 | 预期 |
|---|---|
| 收到报告并确认 | 7 天内 |
| 给出初步影响判断 | 14 天内 |
| 修复与发版 | 视严重性，通常随下一次发版 |

## 披露政策

- 修复版本发布后，我会在 CHANGELOG 中说明问题性质与影响范围。
- 致谢署名默认使用报告者 GitHub ID；如需匿名或使用其他署名，请在报告中说明。
- 在修复发布前，请勿公开披露细节。

## 不在范围内的情形

- Chromium 上游内核自身的漏洞（请报上游，见上）
- 第三方扩展、用户脚本、以及用户自行修改的配置引发的问题
- 需要在本机已取得管理员/物理访问权限才能触发的问题
- 依赖已停止维护的旧版本浏览器的问题（请先升级）
- 社会工程、钓鱼站点、以及与本项目分发渠道无关的仿冒站点

## 分发与校验

安装包只从本仓库的 GitHub Releases 发布，每份产物都附 `.sha256`：

<https://github.com/Mcloud136/Mcloud-Browser/releases>

下载后请核对哈希；**从未提供过其他下载渠道**，遇到第三方站点转载请以本仓库的哈希为准。
当前版本未做代码签名，Windows 首次运行会出现 SmartScreen 提示，这是预期行为。

## 其他

- 本项目不提供漏洞赏金。
- 本仓库已启用 secret scanning 与 push protection，请不要在提交中包含密钥或凭据。

---

## English summary

MCloud Browser is a Chromium-based browser fork for Windows x64 maintained by 狗木马
(wxmuma@qq.com). Security fixes ship only with new releases — **there is no auto-update**,
so please upgrade manually. Report issues in this fork via GitHub private vulnerability
reporting (<https://github.com/Mcloud136/Mcloud-Browser/security/advisories/new>) or by
email to wxmuma@qq.com with a `[SECURITY]` subject prefix. Chromium upstream issues should
go to <https://issues.chromium.org/>. Please do not disclose details publicly before a fix
is released.
