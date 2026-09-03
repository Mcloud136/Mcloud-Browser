---
kind: logging_system
name: Chromium 原生日志系统（logging）与 Mcloud 集成
category: logging_system
scope:
    - '**'
source_files:
    - src/chrome/app/chrome_main_delegate.cc
    - src/chrome/chrome_proxy/chrome_proxy_main_win.cc
    - src/chrome/installer/linux/debian/build.py
    - src/chrome/installer/linux/rpm/build.py
    - src/chrome/installer/linux/common/installer.py
    - infra/google_api_keys-inc.cc
---

## 1. 使用的系统与框架

Mcloud Browser 基于 Chromium 源码，完全沿用 Chromium 的 `base/logging` 日志子系统作为 C++ 代码的统一日志输出机制。所有浏览器进程、组件和第三方子模块通过 `#include "base/logging.h"` 使用 `LOG(INFO|WARNING|ERROR|FATAL)`、`PLOG()`、`DLOG()`、`VLOG(n)`、`DVLOG(n)`、`DCHECK_LOG_IF` 等宏进行结构化/非结构化日志输出。

Python 侧构建/打包脚本（如 `src/chrome/installer/linux/debian/build.py`、`rpm/build.py`、`common/installer.py`）则使用 Python 标准库 `logging` 模块，并通过 `logging.basicConfig(level=..., format="%(message)s")` 统一格式化输出。

## 2. 关键文件与入口

- **日志初始化核心**：`src/chrome/app/chrome_main_delegate.cc`
  - `InitLogging(const std::string& process_type)`（第 678–703 行）：根据进程类型选择 `logging::APPEND_TO_OLD_LOG_FILE` 或 `DELETE_OLD_LOG_FILE`，并调用 `logging::InitChromeLogging(command_line, file_state)` 完成 Chromium 日志子系统初始化。
  - 在非 Android 平台，该函数在 `RunProcess` 路径中于 `PostEarlyInitialization` 后（约第 1402 行）以及 Windows 平台的 `SandboxInitialized`（第 1550 行）被调用；Android 由系统加载库时自行初始化。
  - 启动时会以 `LOG(WARNING)` 级别打印产品名、版本号及一条纪念信息，便于识别构建产物来源。
- **Windows 代理进程**：`src/chrome/chrome_proxy/chrome_proxy_main_win.cc` 直接调用 `logging::InitLogging(logging_settings)` 初始化自身日志。
- **Python 安装器日志**：`src/chrome/installer/linux/debian/build.py`、`src/chrome/installer/linux/rpm/build.py` 通过环境变量 `VERBOSE` 切换 `logging.INFO` / `logging.ERROR`，并以 `%(message)s` 格式输出。

## 3. 架构与约定

- **单点初始化**：所有 C++ 进程的日志均通过 `chrome_main_delegate.cc` 中的 `InitLogging` 集中初始化，避免各模块重复配置。日志目标、目录、轮转策略由 `InitChromeLogging` 依据命令行参数决定。
- **进程类型区分**：主进程（`process_type.empty()`）默认删除旧日志文件，子进程追加到同一日志文件，保证多进程日志顺序性。
- **平台差异**：
  - Android：不在 `ChromeMainDelegate` 中调用 `InitLogging`，由 Android 侧在库加载时初始化（见注释第 1400 行）。
  - Windows：在沙箱初始化之后才调用 `InitLogging`，确保权限正确。
  - Linux/macOS：在早期初始化阶段即完成。
- **调试日志**：广泛使用 `DLOG`/`DVLOG`/`DCHECK_LOG_IF`，仅在 Debug 构建中生效，用于开发期诊断（如历史后端、CDM 注册、Windows 桌面快捷方式管理等）。
- **结构化字段**：项目未引入自定义结构化日志字段层，日志内容以 `<<` 拼接字符串为主；但 Chromium 底层 `logging` 支持结构化字段，可通过扩展实现。
- **崩溃与日志协同**：日志初始化位于 Crashpad 初始化之前，确保崩溃前日志可落盘。

## 4. 约定与约束

- **禁止绕过 InitLogging**：所有非 Android 平台进程必须经由 `chrome_main_delegate.cc` 的 `InitLogging` 初始化日志，以保证日志文件状态一致。
- **日志级别约定**：
  - 启动标识信息使用 `LOG(WARNING)`（因 ChromeOS 最小日志级别为 WARNING），避免被静默过滤。
  - 资源耗尽等致命错误使用 `LOG(ERROR)` 或 `PLOG(FATAL)`。
  - 开发期断言失败使用 `DLOG(ERROR/WARNING)`。
- **Python 构建脚本**：仅当设置 `VERBOSE=1` 时才输出 INFO 级日志，否则仅 ERROR，保持 CI 输出简洁。
- **无独立日志配置文件**：日志行为完全由命令行参数驱动，未在仓库内维护独立的 log config 文件。
- **VLOG/DVLOG 阈值**：通过 `--v=N` 控制 verbose 日志级别，当前代码中多处使用 `VLOG(1)`（如 `infra/google_api_keys-inc.cc` 的 API key 覆盖提示）。

## 5. 相关组件依赖

- 构建系统中显式依赖多个 logging 子模块：`//components/webrtc_logging`、`//components/cross_device/logging`、`//components/peripherals/logging`、`//chrome/browser/nearby_sharing/logging:util`、`//content/browser/notifications/devtools_event_logging` 等，表明这些功能域各自维护专用日志通道。
- V8 引擎自带 `src/logging/*` 日志子系统（code-events、counters、log-file 等），与 Chromium 主日志解耦。

## 总结

Mcloud Browser 的日志系统本质上是 Chromium 原生 `base/logging` + `logging::InitChromeLogging` 的复用，通过 `chrome_main_delegate.cc` 的 `InitLogging` 做单点编排，按进程类型管理日志文件生命周期，配合 `DLOG/VLOG/PLOG` 等宏形成完整的调试/发布日志体系；Python 构建脚本则遵循标准库 `logging` 的 VERBOSE 开关约定。仓库未对日志框架做额外封装，而是严格遵循 Chromium 既定模式。