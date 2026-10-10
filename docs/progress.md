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
  - 运行时标志文件 mcloud_flags.txt：63 条生效开关行（60 项 feature + 3 项普通开关，2026-10-09 实测）
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

历史口径为 51 个标志，分 9 类（下表为当时分类；当前文件实测 63 条生效开关行 =
60 项 feature + 3 项普通开关，其中 4 项因窗口拖拽卡顿已固化为注释禁用，见 §4.6）：
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
- **状态**：✅ 已解决（2026-08-21 实测定位并修复）
- **现象**：浏览器运行于核显播放视频时，前几秒画面绿屏/花屏，过后恢复；独显运行完全正常
- **根因**（受控实验定位，T1-T4 + GPU 分配对照）：
  - Intel 核显（UHD 770/Raptor Lake）的 **D3D12 视频解码器首帧输出缺陷**
  - 非驱动版本问题（32.0.101.6314 与最新 32.0.101.7088 均复现）；非 overlay/MPO 层（禁 DComp 视频 overlay 无效）
  - 早期未复现的原因：开发构建默认跑在独显（显示输出 GPU），复现必须显式控制 GPU 分配
- **修复**：`mcloud_flags.txt` 新增 `--disable-features=D3D12VideoDecoder`（回退 D3D11，硬解能力不受影响），实测核显下绿屏消失
- **附带修复**：安装版曾缺失 `mcloud_flags.txt`（旧安装包），已手工部署修正版到 Application 目录；下次用新安装包重装可自动携带
- **遗留**：待上游修复或 GPU 黑名单条目落地后移除该 disable 标志；`src/media/base/media_switches.cc` 的 D3D12 默认启用定制已被上游 M151 吸收，下次升级时可清理

### 4.6 窗口拖拽缩小播放视频时整浏览器冻结（缓解实验，2026-09-22 → 10-08 定案）
- **状态**：✅ 缓解有效，配置已固化（用户 2026-10-08 确认实验期间未复现）
- **现象**：核显环境，播放视频（B 站）时拖拽缩小浏览器窗口，多次卡顿后整个浏览器 UI 无响应
- **排查证据链**（系统层零痕迹）：无崩溃转储（Crashpad/WER 空）、无 TDR（Display 4101）、无内存耗尽事件、GPU 进程未重启 → 判定为 UI 线程在窗口 resize 模态循环中同步等待 GPU/合成器的软挂起；overlay 引擎全程 0%（视频未走硬件覆盖平面，resize 每帧走 3D 重缩放路径）
- **缓解**：`mcloud_flags.txt` 注释 4 项（实验组整组禁用，未二分归因）：
  `ThrottleUnimportantFrameRate`、`ReduceHardwareVideoDecoderBuffers`、`SkiaGraphite`、`SkiaGraphitePrecompilation`；
  同时关闭 GameViewer/MuMu 后台（存在虚拟显示适配器，14:47 有驱动加载失败记录）
- **残留嫌疑**（若未来复发按序排查）：Intel 核显驱动过旧（32.0.101.6790，2025-04）→ 升级驱动；二分定位 4 项中具体元凶；`chrome://gpu` 导出确认实际渲染后端
- **发布影响**：发行包 `mcloud_151.0.7922.99_win64_mini_installer.exe` 于 2026-10-08 以固化后的标志清单重新打包

### 4.7 启动标志加载器的运行时内存安全加固（第2周期专项，2026-10-09）
- **状态**：✅ 已修复并实测（缺陷 D39/D40，档案 `docs/tasks/bug-review-pak-src-defects.md`）
- **现象**：一份超大/畸形的 `mcloud_flags.txt` 会让浏览器**自身**崩溃——合并后的
  `--enable-features` 约 101KB 时 GPU 子进程 `CreateProcessW`（32767 字符上限）创建失败 →
  `FATAL gpu_data_manager_impl_private.cc:417 GPU process isn't usable. Goodbye.`（约 12s 退出）
- **根因**：加载器把文件内容无长度约束地合并进进程命令行，而该命令行会被所有子进程继承；
  1MiB 的读取上限只防"文件过大"，不防"合法大文件合并后超出 OS 命令行上限"
- **修复**（`win_scripts/inject_flags_loader.py` 的 `LOADER` 常量，加载器 v3→v4→v5）：
  - v3：合并后的 feature 列表 >24KiB 时跳过内置合并并 `LOG(WARNING)`，优雅降级
  - v4：把限制扩展为**加载器追加的全部开关共用字节预算**（总 24KiB，普通开关子预算 12KiB），
    堵住单条超长值（如 250KB 的 `--js-flags`）这条同型路径；feature 合并在循环后执行，
    故畸形普通开关不会挤占 feature 预算
  - v5：解析改用 `string_view::substr`，消除 `-Wunsafe-buffer-usage` 裸指针告警；
    注入器的"是否需替换"判定由版本号标记改为**正文比对**（正文与标记可能不同步）
- **实测证据**：
  - `probe_huge.py`：3000 条 feature（106,890B）→ 18s 存活、2 个 renderer、
    子进程命令行中探针 feature 出现 **0** 次（合并确被跳过）；对照 v2 同语料 ~12s FATAL
  - `loader_edge_test2.py` 11 例边界语料在 v5 二进制上 **11/11 PASS**
    （含 250KB `--js-flags`、4000 个普通开关两个新增用例）
  - 真实清单占用：63 条开关行合计约 1,886B，仅用掉 24KiB 预算的 8%（余量 13 倍）
  - K1 冷启动中位数 **51ms**（原始 70/48/51/51/45），无性能回归
- **方法学修正（D43）**：installer 负载是压缩的，`mini_installer.exe` 内搜文件明文
  （连 `chrome.dll` 都搜不到）不是有效验证通道；发布脚本改为校验打包输入
  （dll 内加载器字符串 + `out/mcloud/mcloud_flags.txt` 与仓库 SHA256 相同 +
  `chrome.release` 列出该文件 + installer 不早于 dll）
- **发布影响**：发行包已用 v5 构建重新生成
  `mcloud_151.0.7922.99_win64_mini_installer.exe`（123,466,240B，
  SHA256 `054efb37c8018feda5ba06842e39269908e438f27ae873b0bb670bfc05ab389f`，123,448,320B，
  2026-10-09 16:55 构建；同批 `chrome.dll` sha256 `c47b2d91eb77324ad596c5e9a3ea6cdf2f4443efa66e707375d1c5640e491d18`。
  本包为**强制全量重做**产物（touch 加载器源文件 → 重编该 TU → 重链 dll → 重建 chrome.7z → 重打 installer），
  发布判据 11 项全绿，A6 3/3 与 K1=54ms 复验通过
- **遗留**：`LOG(WARNING)` 在 `BasicStartupComplete` 阶段（logging 尚未初始化）不落 stderr，
  降级证据以子进程命令行为准；上游若为 feature 传播加上长度保护，可复核本预算是否仍必要

---

### 4.8 升级预评估与 r3 发布链路修复（第3周期，2026-10-10）

- 上游现状（双源交叉验证）：stable `155.0.8059.40`（10-06）、early stable `156.0.8078.12/.13`（10-07）、
  beta `156.0.8078.17`、canary `157.0.8095.0`、extended `154.0.8037.100`；本仓库基线 151.0.7922.99（上游 2026-07-28），
  落后 4 个里程碑 / 74 天。Chrome 自 2026-09-08 起改**双周发布**，规范 9.1"每个大版本升级一次"的节奏已失效，
  需改为攒批或锚定 extended 线。
- 定制面实测：必须重放的上游改动仅 **7 文件 / 207 行 + 新增 `compiler_opt.gni`**；
  全部注入锚点与加载器依赖的 base API 在 155/156 原样存在（`base::SplitStringPiece` 未改名）。
- D47/D48 修复与验证见 CHANGELOG 的 M151-r3 段；证据脚本 `d47_probe.py`、`flag_stability.py`、
  `api_drift.py`、`survival_check.py` 均在 `.bugreview/`，可重复执行。
- 文档与发布链路：`release.yml` 的 notes 选择器按原文抽出后实测——`v151.0.7922.99-r3` → r3 正文 ✅、
  `-r2` → r2 正文 ✅、无后缀 `v151.0.7922.99` → `…-m151.md` ✅；
  但 `v155.0.8059.40` 目前会退回"最新日期文件"（尚无 `…-m155.md`），升级发布时必须先新建该文件。
- r3 已收尾：全量重编译成功，`package_r3.py` 门禁全绿，发布包 123,466,752 B，
  SHA256 `393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049`（sidecar 同步写盘），
  A6 通过；K1/K2 实测留痕见 `docs/dev-logs/M151-r3-benchmark.md`（K2 因进程数 64≠57 不与档案值直接比）。
- 未收口：D49（V8 连字符与下划线是否等价，源码显示 `flags-impl.h:19 NormalizeChar` 归一化，缺运行时歧义实验）；
  r3 的推送/打 tag/资产上传尚未执行（需 L3 安全审查门禁 + 用户授权）。

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

### 5.4 VS2026 注意事项
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
│   ├── AGENTS.md                     # 项目指南（提供商无关，所有 Agent 共用）
│   ├── mcloud_flags.txt              # 运行时标志（63 条生效行，见 §2.2）
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
