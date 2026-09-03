---
kind: error_handling
name: 基于 Chromium net::Error 与 neterror 模板的网络错误处理体系
category: error_handling
scope:
    - '**'
source_files:
    - src/components/neterror/README.md
    - src/components/neterror/resources/neterror.html
    - src/chrome/browser/chrome_content_browser_client.cc
    - src/content/browser/file_system_access/file_system_access_safe_move_helper.cc
    - src/net/dns/dns_transaction.cc
---

## 1. 系统/方法概述

本仓库是 MCloud Browser（基于 Chromium M151 的 Thorium 定制分支），其错误处理整体遵循 Chromium 上游约定：网络层统一使用 `net::ErrorCode`（如 `net::ERR_ACCESS_DENIED`、`net::ERR_INTERNET_DISCONNECTED`、`net::ERR_IO_PENDING`）作为错误码，并通过 `components/neterror` 提供的 HTML 模板在 UI 层渲染用户可见的错误页面。仓库未引入自定义的错误类型体系或中间件框架，而是以“复用 Chromium 内核错误模型 + 本地资源替换”的方式实现。

## 2. 关键文件与包

- `src/components/neterror/README.md`：说明该目录包含网络错误时显示的 HTML 模板及资源（Dino 游戏等），并指出同一模板用于桌面和移动端的主帧与 iframe，可通过 `chrome://network-errors` 预览。
- `src/components/neterror/resources/neterror.html`：实际错误页模板。
- `src/chrome/browser/chrome_content_browser_client.cc`：浏览器进程中对 `net::ErrorCode` 的直接消费点，例如将 `net::ERR_ACCESS_DENIED` 包装为 `network::URLLoaderCompletionStatus` 返回给上层，以及在检测到 `net::ERR_INTERNET_DISCONNECTED` 时进行分支处理。
- `src/content/browser/file_system_access/file_system_access_safe_move_helper.cc`：在文件系统访问路径中检查 `net::ERR_IO_PENDING` 异步状态。
- `src/net/dns/dns_transaction.cc`：DNS 事务层对 `net::ERR_IO_PENDING` 的断言与异步读取结果判断。

## 3. 架构与约定

- **错误源**：网络 I/O、DNS、URLLoader 等底层组件通过 `net::ErrorCode` 枚举值上报错误；这些定义来自 Chromium 上游 `net/base/net_errors.h`（本仓库未重新定义）。浏览器侧代码直接引用这些常量。
- **错误传播**：错误以返回值/回调参数形式沿调用栈向上传播，例如 `URLLoaderCompletionStatus` 携带 `net::ErrorCode` 传递给 Chrome 内容客户端；DNS 层通过断言 `DCHECK_NE(net::ERR_IO_PENDING, net_error)` 确保同步路径不会误用异步错误码。
- **UI 呈现**：当网络请求失败时，Chromium 内核会加载 `components/neterror/resources/neterror.html` 模板生成用户可见的错误页面；MCloud 在此目录下保留自己的资源副本，以便替换品牌图标、Dino 游戏等视觉元素。
- **无自定义异常/中间件**：仓库中没有发现自定义的 `*Error` 类、全局错误中间件、panic/recover 机制或统一的错误包装器；C++ 层主要依赖返回值、`net::ErrorCode` 以及 `DCHECK` 断言。

## 4. 约定与约束

- **网络错误码必须使用 `net::ErrorCode`**：所有网络相关错误均以 `net::ERR_*` 常量表示，浏览器侧代码通过直接比较（如 `error_code == net::ERR_INTERNET_DISCONNECTED`）进行分支处理。
- **异步 I/O 需区分 `net::ERR_IO_PENDING`**：在 DNS、文件系统访问等异步场景中，调用方需显式检查返回值是否为 `net::ERR_IO_PENDING`，并在完成回调中再判定最终错误码。
- **错误页模板集中管理**：网络错误页面的 HTML/CSS/JS/Dino 资源统一位于 `src/components/neterror/resources/`，修改错误页展示应优先在此处调整，而非在各业务模块内硬编码错误提示。
- **调试入口**：开发者可通过 `chrome://network-errors` 预览当前构建中的网络错误页面，便于验证模板改动。
- **断言约束**：同步路径中使用 `DCHECK_NE(net::ERR_IO_PENDING, ...)` 强制保证不会把“待完成”状态当作真实错误码传递到同步调用链，这是一种运行时约束而非编译期约束。

综上，本仓库的错误处理体系本质上是“继承 Chromium 的 `net::ErrorCode` + `neterror` 模板”，MCloud 仅在资源层面做品牌化替换，未建立独立的错误抽象层。