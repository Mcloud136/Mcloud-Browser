# MCloud Browser v158.0.8127.30

基于 Chromium **M158（158.0.8127.30，官方 tag `158.0.8127.30` / commit `cb5de443be`）**，Windows x64。
本版为 M155 → M158 内核升级（跨 3 个里程碑）。目标版本取 Chromium 官方 tag 列表中
`158.0.8127.*` 系列的最新补丁 tag；M158 当前仍为 Beta（计划 2026-11-17 转 Stable），
按 2026-11-08 的决策本次破例抢跑，下一次升级锚定 M159/M160 GA。

## 主要变化

- **安全**：一次性带入 Chrome 156 stable 的 354 项安全修复（6 Critical）与
  157 stable 的 213 项（7 Critical）。项目没有自动更新机制，存量用户需手动重装。
- **内核能力**：IndexedDB 后端改 SQLite（156）；HTML-in-Canvas 转正、
  Background Fetch 强制 CORS（157）；Web Install API 与 `<install>` 元素、
  媒体状态伪类、OfflineAudioContext 增量渲染、WebTransport 增强（158）。
- **兼容性回退**：自 Chrome 158 Stable 起 XSLT 停止工作（libxslt 攻击面），
  老 RSS / XML sitemap 页面会显示裸 XML；OT 与企业策略例外到 Chrome 176（2027-08-17）。
- **定制面复核**：8 处注入锚点在官方 `.30` 上逐项一致（加载器、-O3 链路、
  chrome.release、AVX2 基线、后台模式、DoH 校验等）；`-O3` 仍为
  `cflags += ["/clang:-O3"]`，M155 → M158 形态未变。
- **DoH 可信列表**：DNSPod / 阿里云公共 DNS 随 `deploy_mcloud.py` 第 6 步重放；
  两个端点的 POST 与 GET 均实测返回 HTTP 200 / `application/dns-message` / DNS rcode=0。
- **优化清单**：沿用 52 项 feature + 3 项普通开关。M158 上的平台有效默认值、
  pin 集合与运行时回显期望值以 `docs/tasks/m158-upgrade-task.md` 和升级报告为准，
  本说明不写未经实测的数字。
- **新性能 flag**：M158 新增候选（如 `GpuInitOptimization`、
  `ANGLETrimMemoryOnIdle`、`QuicAlwaysCancelPreExistingProbingOnMigration`）仅进入
  A/B 队列，**未写入** `mcloud_flags.txt`。

## 安装（两个发布物，请用 setup 那个）

| 文件 | 用途 |
|---|---|
| `mcloud_158.0.8127.30_win64_setup.exe` | **推荐**。外层安装包装器：优雅关闭正在运行的本产品实例 → 安装 → 复验根 chrome.exe 确实升到本版本 → 清理临时文件与残留进程 → 自动重启浏览器。默认就地更新机器上已存在的那一份；两处都没装过时默认装到用户级目录，显式 `--system-level` 走系统级并自举提权。 |
| `mcloud_158.0.8127.30_win64_mini_installer.exe` | 上游原生安装器本体。浏览器正在运行时更新会静默不生效（缺陷 D119），只在浏览器已完全退出时使用。 |

包装器另有 `--list-only` 与 `--no-launch` 两个开关；退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。

## 已知限制

- **未做代码签名**：从 GitHub 下载后首次运行会有 SmartScreen 警告。
- **打 tag 不会自动带出安装包**：`release.yml` 不在 runner 上编译内核，安装包必须走
  GitHub Release 资产上传（缺陷档案 D45）。
- **M158 为 Beta 抢跑**：11-17 GA 后上游仍会出补丁 tag，本包会随之落后；
  下一次升级锚定 M159/M160 GA。

## 校验

下载后核对 SHA256（两个发布物都要核）：

```
certutil -hashfile mcloud_158.0.8127.30_win64_setup.exe SHA256
certutil -hashfile mcloud_158.0.8127.30_win64_mini_installer.exe SHA256
```

- setup（推荐）预期值：`84a10de7c770b7cf98ea9dc7ec458e8c4fcbcb05d03eb480ac9a6ac4a38ef4a7`
- mini_installer 预期值：`f5f2191159203071f98f2a2fe48b558c1037a1cd3724d648018fb380f77da6a3`

两者都是同一个内核构建（158.0.8127.30）的产物；setup 只是把 mini_installer 内嵌进外层安装程序。
