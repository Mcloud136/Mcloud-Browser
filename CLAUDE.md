# CLAUDE.md — MCloud Browser 项目指南

## 项目简介

MCloud Browser 是基于 Chromium 的高性能 Windows 浏览器，通过 AVX2 原生编译和 52 项运行时优化标志（`mcloud_flags.txt`，启动时内置加载）+ 编译时优化栈提供极致流畅体验。

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Chromium | 150.0.7871.37 | 浏览器内核 |
| GN + Ninja | Chromium 内置 | 构建系统 |
| Clang | Chromium 内置 (LLVM) | 编译器 |
| depot_tools | latest | Google 构建工具链 |
| Python | 3.8+ | 构建脚本 |
| Git | latest | 版本控制 |
| GitHub Actions | latest | CI/CD |

## 目录结构

```
Mcloud-Browser/                      # 项目根目录
├── .github/workflows/               # CI/CD 工作流
│   ├── build.yml                    # 构建工作流（Linux → Windows 交叉编译）
│   └── release.yml                  # 发布工作流
├── src/                             # Chromium 源码覆盖文件（品牌、UI、功能）
│   ├── chrome/app/                  # 品牌字符串 (chromium_strings.grd 等)
│   ├── chrome/browser/              # 浏览器功能 (flags, UI)
│   ├── chrome/common/               # 通用定义
│   ├── build/config/                # 构建配置 (compiler_opt.gni)
│   ├── components/                  # 组件覆盖
│   ├── extensions/common/           # 扩展商店 URL
│   ├── media/                       # 媒体优化
│   └── third_party/                 # 第三方库覆盖
├── other/                           # 补丁文件 (.patch)
├── win_scripts/                     # Windows 构建脚本 (Python)
│   ├── setup.py                     # 复制源码到 Chromium 树（M144 版本）
│   ├── copy_essentials.py           # 选择性文件复制（M149 兼容）
│   └── build_win.py                 # 构建脚本
├── mcloud-libjxl/                   # JPEG XL 子模块
├── mcloud_shell/                    # Content Shell
├── logos/                           # 品牌图标资源
├── docs/                            # 文档
│   ├── superpowers/specs/           # 设计规格文档
│   └── superpowers/plans/           # 实施计划文档
├── win_args_mcloud.gn               # Windows AVX2 构建配置
├── mcloud_flags.txt                 # 启动标志配置（由 chrome_main_delegate.cc 内置加载，见规范 4.1）
├── README.md                        # 项目说明
├── LICENSE.md                       # MIT 许可证
└── .claude/                         # Claude 开发辅助
    └── progress.md                  # 当前开发进度
```

## 构建命令

### 环境变量（必须设置）

```bash
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
# VS2026 ATL 头文件路径（必须添加）
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"
```

### Google API 密钥（运行时需要）

启动浏览器前必须设置 Google API 密钥，否则会提示缺少密钥。使用 `launch_browser.bat` 启动可自动设置。

```bash
# 环境变量方式
set GOOGLE_API_KEY=AIzaSyCgcLY25b1jTb6Z1_8VA2hjX9HGPuYwmJY
set GOOGLE_DEFAULT_CLIENT_ID=77185425430.apps.googleusercontent.com
set GOOGLE_DEFAULT_CLIENT_SECRET=OTJgU3nD3q0q0q0q0q0q0q0q
```

参考：https://www.chromium.org/developers/how-tos/api-keys/

### 完整构建流程

```bash
# 1. 拉取 Chromium M150 源码
mkdir -p /d/wxmuma/chromium-src && cd /d/wxmuma/chromium-src
fetch --nohooks chromium
cd src && git checkout tags/150.0.7871.37
gclient sync --shallow --jobs=16 --with_branch_heads --with_tags --force --reset --delete_unversioned_trees
gclient runhooks

# 2. 复制 MCloud Browser 源码
cd /d/wxmuma/chromium-src/src
export THOR_DIR="/d/wxmuma/thorium"
export CR_DIR="/d/wxmuma/chromium-src/src"
python3 $THOR_DIR/win_scripts/copy_essentials.py

# 3. 复制构建配置
mkdir -p out/mcloud
cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn

# 4. 生成构建文件
gn gen out/mcloud --check

# 5. 编译
autoninja -C out/mcloud chrome

# 6. 构建安装包
autoninja -C out/mcloud mini_installer
```

### 增量编译（修改源码后）

```bash
cd ~/chromium/src
autoninja -C out/mcloud chrome
```

### 重新生成 GN 配置（修改 args.gn 后）

```bash
cd ~/chromium/src
gn gen out/mcloud --check
autoninja -C out/mcloud chrome
```

## 编码规范

- **品牌名称**：使用 Chromium 默认品牌名（不修改）
- **文件命名**：使用小写加下划线（`mcloud_flag_entries.h`）
- **构建目录**：始终使用 `out/mcloud`
- **修改 build/ 目录前**：必须备份 `compiler_opt.gni` 等自定义文件
- **禁止**：不要用 `git checkout -- build/` 批量回退（会删除自定义文件）
- **GN 参数修改后**：必须重新 `gn gen out/mcloud --check`
- **补丁文件**：放在 `other/` 目录，命名格式 `feature-name.patch`

## 关键构建参数

```gn
# SIMD
use_avx2 = true
use_fma = true

# 编译器优化
is_full_optimization_build = true   # -O3
use_polly = false                   # 接线已修复但需先自建含 Polly 的 clang（规范 2.6）
use_bolt = false                    # 接线已修复但 BOLT 后链接流程未落地（规范 10.1）
use_thin_lto = true                 # ThinLTO

# V8 优化
v8_enable_maglev = true
v8_enable_turbofan = true
v8_enable_wasm_simd256_revec = true

# 媒体
proprietary_codecs = true
ffmpeg_branding = "Chrome"
enable_platform_hevc = true
enable_widevine = false             # CDM 未下载时禁用

# GPU
enable_vulkan = false               # Windows 使用 D3D12

# Windows
win_enable_cfg_guards = true
enable_rlz = true                   # 与 win_args_mcloud.gn 口径一致，决策见 docs/decisions/ADR-001
```

## GitHub 仓库

- **仓库**：https://github.com/Mcloud136/Mcloud-Browser
- **默认分支**：main
- **许可证**：MIT
- **触发 CI**：push 到 main 或推送 v* tag

## 性能优化参考

- 设计文档：`docs/superpowers/specs/2026-06-19-performance-optimization-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-19-performance-optimization.md`
- 代码审查修复：`docs/superpowers/specs/2026-06-20-code-review-fixes.md`
- 开发进度：`.claude/progress.md`
