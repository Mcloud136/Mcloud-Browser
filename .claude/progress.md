# MCloud Browser 开发进度文档

> 最后更新：2026-06-20
> Chromium 版本：M150 (150.0.7871.37)
> 本地仓库：D:\wxmuma\thorium
> Chromium 源码树：D:\wxmuma\chromium-src\src

---

## 1. 已完成的工作

### 1.1 Chromium M150 升级
- **状态**：✅ 完成
- **从**：M149 (149.0.7827.53)
- **到**：M150 (150.0.7871.37)
- **完成内容**：
  - 源码拉取（43GB）
  - gclient sync 依赖同步
  - gclient runhooks 工具链配置
  - VS2026 BuildTools 适配

### 1.2 性能优化
- **状态**：✅ 完成（运行时标志），待下次编译（编译时参数）
- **设计文档**：`docs/superpowers/specs/2026-06-19-performance-optimization-design.md`
- **实施计划**：`docs/superpowers/plans/2026-06-19-performance-optimization.md`
- **完成内容**：
  - 51 个运行时标志（mcloud_flags.txt）
  - 72 个编译时参数（args.gn）验证通过
  - D3D12 视频解码默认启用
  - DNS 修复（HTTP 断流问题）
  - AVX2 + FMA3 SIMD 全局注入
  - PGO + ThinLTO + BOLT + Polly + O3 编译优化栈

### 1.3 首次 M150 编译
- **状态**：✅ 成功
- **编译目标**：50,973 个
- **编译时间**：约 2 小时
- **输出**：`D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe` (3.7MB)

### 1.4 代码审查
- **状态**：✅ 完成
- **审查文档**：`docs/superpowers/specs/2026-06-20-code-review-fixes.md`
- **发现问题**：14 个（2 Critical, 5 Important, 7 Minor）
- **已修复**：14/14

---

## 2. 当前配置

### 2.1 编译时参数（args.gn）

| 类别 | 参数 | 值 | 状态 |
|------|------|-----|------|
| SIMD | `use_avx2` | `true` | ✅ |
| SIMD | `use_fma` | `true` | ✅ |
| 编译 | `is_official_build` | `true` | ✅ |
| 编译 | `is_full_optimization_build` | `true` | ✅ |
| 编译 | `use_polly` | `true` | ✅ |
| 编译 | `use_bolt` | `true` | ✅ |
| 编译 | `use_thin_lto` | `true` | ✅ |
| PGO | `chrome_pgo_phase` | `2` | ✅ |
| V8 | `v8_enable_maglev` | `true` | ✅ |
| V8 | `v8_enable_turbofan` | `true` | ✅ |
| 视频 | `enable_platform_hevc` | `true` | ✅ |
| 视频 | `enable_hevc_parser_and_hw_decoder` | `true` | ✅ |
| 视频 | `proprietary_codecs` | `true` | ✅ |
| DRM | `enable_widevine` | `false` | ⚠️ CDM 未下载 |
| GPU | `enable_vulkan` | `false` | ✅ Windows 用 D3D12 |
| 隐私 | `enable_rlz` | `false` | ✅ 禁用 Google 追踪 |

### 2.2 运行时标志（mcloud_flags.txt）

共 51 个标志，分 9 类：
- 启动速度：6 个
- 视频播放：3 个
- 渲染优化：4 个
- 内存优化：11 个
- 网络优化：6 个
- GPU 优化：4 个
- 媒体优化：7 个
- 多线程：5 个
- 存储/服务：5 个

### 2.3 MCloud 覆盖文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `build/config/compiler_opt.gni` | SIMD 变量声明 | ✅ |
| `build/config/compiler/BUILD.gn` | SIMD 注入 + O3 优化 | ✅ |
| `build/config/BUILDCONFIG.gn` | 全局 SIMD 配置注册 | ✅ |
| `build/config/win/BUILD.gn` | Windows 编译配置 | ✅ |
| `media/base/media_switches.cc` | D3D12 默认启用 | ✅ |
| `chrome/browser/net/default_dns_over_https_config_source.cc` | DNS 修复 | ✅ |

---

## 3. 已修复的问题

### 3.1 HTTP 断流问题
- **现象**：MCloud Browser 访问 HTTP 网站被断流，Edge 正常
- **根因**：DNS-over-HTTPS 默认模式设为 `kSecure`（严格模式），只用 DoH 解析 DNS
- **修复**：改为 `kAutomatic`（自动模式，DoH 失败时回退普通 DNS）
- **文件**：`chrome/browser/net/default_dns_over_https_config_source.cc`

### 3.2 代码审查问题（14 个）

**已生效（无需重编）**：
| # | 问题 | 修复 |
|---|------|------|
| 4 | PauseMutedBackgroundAudio 暂停后台视频 | 移除 |
| 5 | SyncPointGraphValidation GPU 调试开销 | 移除 |
| 8 | EnableAdpfEfficiencyMode Android-only | 移除 |
| 14 | AggressiveShaderCacheLimits 缓存抖动 | 移除 |

**待下次编译生效**：
| # | 问题 | 修复 |
|---|------|------|
| 1 | win/BUILD.gn AVX2 无条件注入 | 移除重复块 |
| 2 | PGO 路径硬编码 | 移除，让 Chromium 自动查找 |
| 3 | AVX2/FMA 标志重复 | 统一由 thorium_simd_optimization 处理 |
| 6 | enable_vr 无效参数 | 移除 |
| 7 | 三重 -O3 指定 | 简化为 /clang:-O3 |
| 9 | enable_stripping 无效参数 | 移除 |
| 10 | enable_rust 冗余 | 移除 |
| 11 | enable_rlz 隐私问题 | 改为 false |
| 12 | use_text_section_splitting Windows 无效 | 移除 |
| 13 | AVX-512 rustflags 缺少 +bmi | 添加 +bmi |

---

## 4. 未完成的工作

### 4.1 GitHub Actions CI/CD
- **状态**：未解决
- **Blocker**：Chromium 源码 60+ GB，GitHub Actions 免费 Runner 无法完成 `gclient sync`
- **下一步**：预构建 Chromium 源码包，或使用自建 Runner

### 4.2 Widevine DRM 支持
- **状态**：暂时禁用
- **原因**：Widevine CDM 二进制文件需要单独下载（专有软件）
- **下一步**：如需 DRM 支持，运行 `build/download_widevine_cdm.py` 下载 CDM

### 4.3 品牌重命名
- **状态**：已放弃
- **原因**：用户决定使用 Chromium 默认品牌名

### 4.4 D3D12 视频解码
- **状态**：不可用（硬件/驱动限制）
- **现象**：即使设置 `kD3D12VideoDecoder = ENABLED_BY_DEFAULT` 并命令行强制启用，仍回退到 D3D11
- **原因**：
  - 显卡驱动版本可能不支持 D3D12 视频解码
  - 显卡硬件可能不支持
  - Chromium M150 的 D3D12 视频解码实现可能有限制
- **影响**：无，D3D11 是成熟的硬件解码方案，性能足够
- **结论**：保持 D3D11，D3D12 配置保留但不强制启用

### 4.5 核显视频绿屏问题
- **状态**：未解决
- **现象**：切换到核显播放视频时，前几秒画面绿屏/花屏，过后恢复
- **可能原因**：
  - D3D11 解码器在核显上初始化延迟
  - 视频帧池预热不足
  - Intel 核显驱动兼容性问题
- **下一步**：需要进一步调试，或更新显卡驱动

---

## 5. 下次编译更新内核时的操作

### 5.1 编译命令
```bash
cd /d/wxmuma/chromium-src/src

# 同步覆盖文件
export THOR_DIR="/d/wxmuma/thorium"
export CR_DIR="/d/wxmuma/chromium-src/src"
python3 $THOR_DIR/win_scripts/copy_essentials.py

# 复制 args.gn
cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn

# 生成构建文件
export PATH="/d/wxmuma/depot_tools:$PATH"
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"
gn gen out/mcloud --check

# 编译
autoninja -C out/mcloud chrome
```

### 5.2 启动浏览器
```bash
# 使用启动脚本（自动设置 Google API 密钥）
D:\wxmuma\thorium\launch_browser.bat

# 或手动设置环境变量
set GOOGLE_API_KEY=AIzaSyCgcLY25b1jTb6Z1_8VA2hjX9HGPuYwmJY
set GOOGLE_DEFAULT_CLIENT_ID=77185425430.apps.googleusercontent.com
set GOOGLE_DEFAULT_CLIENT_SECRET=OTJgU3nD3q0q0q0q0q0q0q0q
cd /d/wxmuma/chromium-src/src/out/mcloud
start chrome.exe
```

### 5.3 编译后验证
- `chrome://flags` — 检查标志状态
- `chrome://media-internals` — 验证 D3D12 视频解码
- B 站/YouTube — 视频播放测试
- HTTP 网站 — 确认不断流

### 5.3 VS2026 注意事项
- ATL 头文件需要手动添加到 INCLUDE 路径
- 路径：`C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include`

---

## 6. 铁律约束

- **绝对不能动的**：不要修改 Chromium 核心渲染引擎代码（Blink 布局、CSS 解析等），风险太高
- **必须遵循的**：
  - 修改 `build/` 目录前必须备份 `compiler_opt.gni` 等自定义文件
  - 不要用 `git checkout -- build/` 这种批量回退命令
  - 每次修改 GN 参数后必须重新 `gn gen`
  - AVX2 编译必须保持 `use_avx2 = true` + `use_fma = true`
  - 品牌名称使用 Chromium 默认（不修改）
  - VS2026 编译必须设置 `DEPOT_TOOLS_WIN_TOOLCHAIN=0` 和 ATL INCLUDE 路径

---

## 7. 文件结构

```
D:\wxmuma\
├── thorium\                          # MCloud Browser 项目
│   ├── .claude\progress.md           # 本文件
│   ├── CLAUDE.md                     # 项目指南
│   ├── mcloud_flags.txt              # 运行时标志（51 个）
│   ├── win_args_mcloud.gn            # 编译时参数
│   ├── win_scripts\copy_essentials.py # 覆盖文件复制脚本
│   ├── src\build\config\             # MCloud 构建配置
│   ├── src\media\base\               # D3D12 视频解码
│   ├── src\chrome\browser\net\       # DNS 修复
│   └── docs\superpowers\             # 设计文档和实施计划
│       ├── specs\                    # 设计规格
│       └── plans\                    # 实施计划
│
└── chromium-src\                     # Chromium M150 源码
    └── src\                          # 源码根目录
        └── out\mcloud\               # 构建输出
            └── chrome.exe            # 编译产物
```
