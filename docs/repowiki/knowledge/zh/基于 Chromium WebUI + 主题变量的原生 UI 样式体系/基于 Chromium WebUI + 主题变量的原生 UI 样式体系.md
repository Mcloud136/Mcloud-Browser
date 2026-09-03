---
kind: frontend_style
name: 基于 Chromium WebUI + 主题变量的原生 UI 样式体系
category: frontend_style
scope:
    - '**'
source_files:
    - src/ash/webui/help_app_ui/resources/app.html
    - src/components/webui/version/resources/about_version.html
    - src/components/webui/version/resources/about_version.css
    - src/components/neterror/resources/neterror.html
    - other/WIN7/about_version.html
    - src/chrome/browser/resources/new_tab_page/icons/google_logo.svg
    - logos/NEW/webui/icon_arrow_back.svg
    - logos/NEW/webui/incognito_icon.svg
    - logos/NEW/webui/hazard.svg
---

## 1. 系统/方法概述

本仓库是 MCloud Browser（基于 Chromium M151 的 Thorium 定制分支），前端 UI 并非独立的前端工程，而是以 **Chromium WebUI** 为唯一渲染层：HTML 模板通过 `chrome://` 协议加载 CSS、JS 与资源，样式完全依赖 Chromium 内置的 WebUI 组件库与主题变量系统。仓库中不存在独立的 CSS/SCSS/Tailwind 等前端框架代码，所有视觉表现由以下机制构成：

- **WebUI HTML 模板**：位于 `src/components/webui/version/resources/about_version.html`、`src/ash/webui/help_app_ui/resources/app.html`、`src/components/neterror/resources/neterror.html` 等，使用 Chromium 的 `<if expr=...>` 条件编译语法。
- **主题颜色变量**：通过 `<link rel="stylesheet" href="//theme/colors.css?sets=ref&generate_rgb_vars=true">` 注入可被 CSS 使用的 CSS 自定义属性（如 `--color-*`），实现亮/暗色主题切换。
- **全局文本默认样式**：通过 `chrome://resources/css/text_defaults.css` 统一字体、字号、行高。
- **平台/OS Header**：在 ChromeOS 环境下额外引入 `chrome://resources/css/os_header.css`。
- **移动端适配**：通过 `about_version_mobile.css` 与 `prefers-color-scheme` media query 区分桌面/移动布局。
- **图标与图片资源**：通过 `chrome://theme/IDR_*` 主题资源引用品牌 Logo、吉祥物，并使用 `<picture>` + `srcset` + `media="(prefers-color-scheme: dark/light)"` 提供明/暗两套图片。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `src/ash/webui/help_app_ui/resources/app.html` | Ash WebUI 入口，声明 `color-scheme: light dark`，内联基础样式，并引入 `//theme/colors.css` |
| `src/components/webui/version/resources/about_version.html` | `about:version` 页面模板，展示版本信息，使用 `chrome://resources/css/text_defaults.css` 与 `chrome://version/about_version.css` |
| `src/components/webui/version/resources/about_version.css` | 版本页样式，含 `@media (prefers-color-scheme: dark)` 暗色覆盖 |
| `src/components/neterror/resources/neterror.html` | 网络错误页，引入安全插页通用样式 `interstitial_core.css` / `interstitial_common.css` 及自身 `neterror.css` |
| `other/WIN7/about_version.html` | Windows 7 专用版本页，演示 `chrome://theme/IDR_PRODUCT_LOGO_WHITE` 等明暗双图资源 |
| `src/chrome/browser/resources/new_tab_page/icons/google_logo.svg` | 新标签页仅保留一个 SVG 图标 |
| `logos/NEW/webui/` | WebUI 相关 SVG 图标（箭头、扩展、警告、隐身模式等） |

## 3. 架构与约定

### 3.1 样式来源分层
1. **主题层**：`//theme/colors.css` 提供 CSS 变量，是所有 WebUI 颜色的单一来源；修改主题只需调整该变量集。
2. **全局默认层**：`chrome://resources/css/text_defaults.css` 定义全局字体、字号、行高，所有 WebUI 页面必须引入。
3. **组件层**：每个 WebUI 子模块自带 `.css`（如 `about_version.css`、`neterror.css`），复用 Chromium 公共样式（如 `interstitial_core.css`）。
4. **平台适配层**：ChromeOS 引入 `os_header.css`；Android/iOS 引入 `*_mobile.css`。

### 3.2 明暗主题策略
- 所有 WebUI HTML 模板首行声明 `<meta name="color-scheme" content="light dark">`，启用浏览器原生明暗主题。
- 通过 `@media (prefers-color-scheme: dark)` 覆盖特定样式（见 `about_version.css`、`flags/app.css`）。
- 图片资源通过 `<picture><source media="(prefers-color-scheme: dark)">` 提供明暗两套 PNG/SVG。
- 主题 Logo 通过 `chrome://theme/IDR_PRODUCT_LOGO_WHITE`（暗色）与 `IDR_PRODUCT_LOGO`（亮色）自动切换。

### 3.3 图标与资源管理
- 品牌图标集中存放于 `logos/NEW/`，按平台分目录（`android/`、`mac/`、`win/`、`linux/`、`webui/`、`components/`）。
- WebUI 图标以 SVG 形式存放在 `logos/NEW/webui/`，命名采用 `icon_*.svg` 前缀。
- 运行时通过 `chrome://theme/IDR_*` 或 `chrome://resources/...` 协议引用，而非本地路径。

### 3.4 无第三方样式框架
仓库未引入任何外部 CSS 框架（无 Bootstrap、Tailwind、Ant Design、Material Web 等）。所有样式均基于 Chromium 原生 WebUI 能力，遵循 Chromium 内部约定。

## 4. 约定与约束

- **禁止直接硬编码颜色值**：应优先使用 `//theme/colors.css` 提供的 CSS 变量，以保证跟随系统/用户主题。
- **所有 WebUI 页面必须声明 `color-scheme: light dark`**：这是 Chromium WebUI 的标准要求，确保滚动条、表单控件等原生元素正确适配明暗主题。
- **图片资源必须提供明暗两套**：通过 `<picture>` + `media="(prefers-color-scheme: dark/light)"` 分别指定暗/亮版，避免在暗色主题下出现白色 Logo 不可见的问题。
- **文本样式统一来自 `text_defaults.css`**：新增页面不应自行定义全局字体/字号，而应复用 Chromium 默认文本样式。
- **CSS 组织遵循“全局默认 → 组件专属 → 平台适配”三层结构**：新增样式应先判断是否属于通用组件样式，再决定放在组件目录还是平台适配层。
- **WebUI 模板使用 Chromium 条件编译**：通过 `<if expr="is_android or is_ios">` 等平台检测条件控制不同平台的 DOM 与样式加载。
- **图标资源通过 `chrome://theme/IDR_*` 引用**：不要将品牌 Logo 硬编码到页面中，应使用主题资源 ID，以便随主题切换。

## 5. 总结

MCloud Browser 的前端样式体系本质上是 **Chromium WebUI + 主题变量 + 明暗媒体查询** 的组合，没有独立的前端样式工程。所有视觉一致性由 Chromium 内置的 `text_defaults.css`、`colors.css`、`interstitial_core.css` 以及 `chrome://theme/` 资源协议保障。定制工作集中在替换主题资源（Logo、吉祥物）、编写少量组件级 CSS，并通过 `prefers-color-scheme` 与 `<picture>` 实现明暗主题适配。