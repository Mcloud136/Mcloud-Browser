<p align="center">
  <img src="https://raw.githubusercontent.com/Mcloud136/Mcloud-Browser/refs/heads/main/logos/NEW/mcloud.svg" width="200">
</p>

<h1 align="center">MCloud Browser</h1>

<p align="center">
  基于 Chromium M151 的高性能浏览器，AVX2 原生编译，66 项运行时优化标志
</p>

<p align="center">
  <a href="https://github.com/Mcloud136/Mcloud-Browser/releases"><img src="https://img.shields.io/github/v/release/Mcloud136/Mcloud-Browser?label=Latest" /></a>
  <a href="https://github.com/Mcloud136/Mcloud-Browser/blob/main/LICENSE.md"><img src="https://img.shields.io/github/license/Mcloud136/Mcloud-Browser?color=green" /></a>
</p>

---

## 📖 简介

MCloud Browser 是基于 [Chromium M151 (151.0.7922.99)](https://www.chromium.org/) 的高性能浏览器，通过 **AVX2 原生编译**、**-O3 + ThinLTO + PGO 三重编译器优化** 和 **66 项运行时优化标志**（见 [mcloud_flags.txt](mcloud_flags.txt)，浏览器启动时由内置加载器自动注入），为用户提供极致流畅的浏览体验。

> 仅发布 **Windows x64** 平台（见 [ADR-003](docs/decisions/ADR-003-windows-only-release.md)）。

### 🎯 核心特性

- **AVX2 + FMA3 原生编译** — 充分利用现代 CPU 的 SIMD 指令集（项目硬件基线，见技术规范 1.5）
- **-O3 + ThinLTO + PGO 编译器优化** — 三重编译器优化已生效（Polly/BOLT 接线已修复，待前置工具链就绪后启用）
- **66 项运行时优化标志** — 覆盖启动、V8 脚本加速、页面加载、内存、多线程、渲染、MSE 视频缓冲等全链路，全部经源码存活性校验与子进程注入验证
- **硬件视频解码** — HEVC/VP9/AV1/D3D12 硬件解码（D3D12 解码器默认启用）
- **Bilibili & YouTube 优化** — MSE 缓冲优化（实测 B 站导航提速 5.6%）、硬件解码链路
- **完整编解码器支持** — HEVC、AC3、Dolby Vision、DTS
- **Chrome Web Store** — 完整的扩展商店支持

---

## 🚀 下载

从 [GitHub Releases](https://github.com/Mcloud136/Mcloud-Browser/releases) 下载最新版本（产物命名：`mcloud_{版本}_win64_mini_installer.exe`，附 `.sha256` 校验文件）。

```powershell
# 安装前验证完整性（可选）
(Get-FileHash .\mcloud_151.0.7922.99_win64_mini_installer.exe -Algorithm SHA256).Hash
```

### 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 x64 |
| **CPU** | 支持 AVX2 的处理器（2013 年后） |
| **内存** | 8 GB 以上（推荐 16 GB） |
| **磁盘** | 500 MB 可用空间 |

### 支持的 CPU

- **Intel**: Haswell (2013) 及以后所有型号
- **AMD**: Excavator (2015) / Ryzen (2017) 及以后所有型号

---

## ⚡ 性能优化

### 编译器优化栈（3 项已生效）

| 优化 | 效果 | 状态 |
|------|------|------|
| AVX2 + FMA3 原生编译 | SIMD 指令集全面加速 | 已生效 |
| -O3 极致优化 | 全局性能提升 5-15% | 已生效 |
| ThinLTO + PGO | 跨文件优化 + 热点路径优化 | 已生效 |
| Polly 循环优化 | 密集计算提升 5-10% | 待自建含 Polly 的 clang（规范 2.6） |
| BOLT 二进制布局 | 启动速度提升 3-8% | 待后链接流程落地（规范 10.1） |

### 启动速度优化（+11）

| 标志 | 效果 |
|------|------|
| `SendGPUChannelEarly` | 首屏渲染加速 |
| `DeferSpeculativeRFHCreation` | 减少启动阻塞 |
| `InitialWebUI` | 启动阶段 WebUI 精简与优先级提升 |
| `TransientKeepAlivePolicy` | 减少进程创建开销 |
| `SpareRendererForSitePerProcess` | 预热渲染进程 |
| `BrowserProcessAboveNormalPriority` | 浏览器进程高优先级 |
| `Prerender2WarmUpCompositorForNewTabPage` | 新标签页预热合成器 |
| `Prerender2WarmUpCompositorForBookmarkBar` | 书签栏预热合成器 |
| `LoadingPreconnectToRedirectTarget` | 重定向目标预连接 |
| `PreloadTopChromeWebUI` | 预载 Top Chrome WebUI |
| `BookmarkTriggerForPreconnect` | 书签触发预连接 |

### V8 脚本执行加速

| 优化 | 效果 |
|------|------|
| `--invocation_count_for_maglev=200` | Maglev 编译阈值减半（默认 400），脚本更早进入优化编译 |
| `--invocation_count_for_turbofan=1500` | TurboFan 编译阈值减半（默认 3000） |
| `--osr-from-maglev` | 支持从 Maglev OSR 升级到 TurboFan |
| `--sparkplug-plus` | Sparkplug 基线代码动态修补 |

### 页面加载加速（+6）

| 标志 | 效果 |
|------|------|
| `ThreadedPreloadScanner` | 线程化 preload 扫描 |
| `ConsumeCodeCacheOffThread` | 代码缓存离线程消费 |
| `InlineScriptCache` | 内联脚本缓存 |
| `PreloadSystemFonts` | 系统字体预载 |
| `HttpDiskCachePrewarming` | HTTP 磁盘缓存预热 |
| `LCPPAutoPreconnectLcpOrigin` | LCP 源自动预连接 |

### MSE/视频缓冲优化（+3，Bilibili/YouTube）

| 标志 | 效果 |
|------|------|
| `RevokeMediaSourceObjectURLOnAttach` | MSE ObjectURL 及时回收，降内存 |
| `ReduceHardwareVideoDecoderBuffers` | 减少硬解缓冲 |
| `BackForwardCacheDWCOnJavaScriptExecution` | BFCache 媒体优化 |

> 预载类优化经实测取舍：保留低内存代价项；移除 3 项高内存低收益项（真实站点 50 标签内存节省 203MB），详见 [M151-opt 基准报告](docs/dev-logs/M151-opt-benchmark.md)。

### 内存优化（+11）

| 标志 | 效果 |
|------|------|
| `DiscardOnCommitLimit` | 内存 <10% 丢弃标签页，防 OOM |
| `SustainedPMUrgentDiscarding` | 持续压力紧急回收 |
| `PartitionAllocSortActiveSlotSpans` | 减少内存碎片 |
| `PartitionAllocUsePriorityInheritanceLocks` | 减少锁竞争 |
| `LowerPAMemoryLimitForNonMainRenderers` | 多标签内存降低 10-20% |
| `ReclaimOldPrepaintTiles` | 30 秒回收预绘制瓦片 |
| `PruneOldTransferCacheEntries` | 清理旧传输缓存 |
| `InfiniteTabsFreezing` | 标签页冻结 |
| `InfiniteTabsFreezingOnMemoryPressure` | 内存压力下冻结标签页 |
| `PartitionAllocEventuallyZeroFreedMemory` | 释放内存清零 |
| `PartitionAllocMemoryReclaimer` | 内存回收器 |

### 多线程优化（+5）

| 标志 | 效果 |
|------|------|
| `IOThreadInteractiveThreadType` | IO 响应性提升 |
| `MojoDedicatedThread` | IPC 隔离，减少阻塞 |
| `BaseLockTrySpin` | 用户态自旋锁 |
| `BoostClosingTabs` | 关闭标签更快 |
| `UnimportantFramesPriority` | 关键框架更多资源 |

### 视频/媒体优化（+7）

| 标志 | 效果 |
|------|------|
| `DedicatedMediaServiceThread` | 视频更流畅 |
| `DirectOpusAudioDecoding` | 音频效率提升 |
| `EncryptedMediaOcclusionTracking` | 跳过不必要解码 |
| `MediaFoundationBatchRead` | 视频加载更快 |
| `MediaFoundationD3D11VideoCaptureZeroCopy` | 减少内存拷贝 |
| `PlatformHEVCDecoderSupport` | HEVC 硬件解码 |
| `HardwareSecureDecryptionAv1` | AV1 硬件安全解密 |

### GPU/渲染优化（+4）

| 标志 | 效果 |
|------|------|
| `IncreasedCmdBufferParseSlice` | 减少上下文切换 |
| `SkiaGraphitePrecompilation` | 消除着色器编译卡顿 |
| `ResourcePoolPreferExactSizeReuse` | 减少 GPU 内存碎片 |
| `HighFramerateRequestFromClient` | 支持高刷显示器 |

### 网络优化（+6）

| 标志 | 效果 |
|------|------|
| `BackForwardCache` | 页面瞬间恢复 |
| `AsyncDns` | 异步 DNS 解析 |
| `EarlyData` | TLS 1.3 早期数据 (0-RTT) |
| `BookmarkTriggerForPrefetch` | 书签触发预取 |
| `NewTabPageTriggerForPrefetch` | 新标签页预取 |
| `CacheControlNoStoreEnterBackForwardCache` | 更多页面可快速恢复 |

---

## 🎬 编解码器支持

| 编解码器 | 软解 | 硬解 | 说明 |
|---------|------|------|------|
| H.264/AVC | ✅ | ✅ DXVA2/D3D11 | 所有 GPU 支持 |
| VP9 | ✅ | ✅ DXVA2/D3D11 | 现代 GPU 支持 |
| AV1 | ✅ | ✅ D3D11 | RTX 30+ / RX 6000+ / Arc |
| HEVC/H.265 | ✅ | ✅ D3D11 | 需要 GPU 支持 |
| Dolby Vision | ✅ | ✅ | 需要显示设备支持 |
| AC3/E-AC3 | ✅ | — | 杜比音频 |
| DTS | ✅ | — | DTS 音频 |
| MPEG-H | ✅ | — | MPEG-H 音频 |

---

## 🛠️ 从源码构建

### 前置条件

- Windows 10/11 x64
- Visual Studio 2026 Build Tools（或 2022）
- Git
- Python 3.8+
- 至少 100 GB 可用磁盘空间
- 至少 16 GB 内存

### 环境变量

```bash
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
# VS2026 ATL 头文件路径（必须添加）
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"
```

### 构建步骤

```bash
# 1. 克隆 MCloud Browser 仓库
git clone --branch main https://github.com/Mcloud136/Mcloud-Browser.git
cd Mcloud-Browser

# 2. 安装 depot_tools
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH="$PWD/depot_tools:$PATH"

# 3. 拉取 Chromium M151 源码（定向浅拉取目标 tag，避免全量枚举）
mkdir -p ~/chromium && cd ~/chromium
git init src && cd src
git remote add origin https://chromium.googlesource.com/chromium/src.git
git fetch --depth 1 origin tag 151.0.7922.99
git checkout 151.0.7922.99
cd ..
# .gclient 放 chromium 根目录（勿放 src 内），然后同步依赖：
gclient sync --nohooks --jobs 8 --revision src@151.0.7922.99
gclient runhooks
# ⚠ 禁用 --force --reset --delete_unversioned_trees（会清除定制与 CIPD 二进制）

# 4. 部署 MCloud 定制（统一部署入口，全部定点幂等，可重复运行）
cd ~/chromium/src
export THOR_DIR="/path/to/Mcloud-Browser"
export CR_DIR="$HOME/chromium/src"
python3 $THOR_DIR/win_scripts/deploy_mcloud.py
# 内部按序：compiler_opt.gni 复制 → Polly 接线/定义 → AVX2 基线 →
# D3D12/后台模式默认值 → flags 加载器注入 → mcloud_flags.txt 复制到 out/mcloud

# 5. 下载 PGO profdata（版本必须与内核匹配：M151=7922 系列）
python3 tools/update_pgo_profiles.py --target=win64 update \
  --gs-url-base=chromium-optimization-profiles/pgo_profiles
# V8 builtins profiles（mksnapshot 依赖，版本不匹配会拒绝）：
python3 v8/tools/builtins-pgo/download_profiles.py --depot-tools=third_party/depot_tools --force download

# 6. 配置构建参数
mkdir -p out/mcloud
cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn
# 注意核对 args.gn 中 pgo_data_path 指向已下载的 7922 系列 profdata 文件名

# 7. 生成构建文件并校验
gn gen out/mcloud --check

# 8. 编译 + 打包（flags 文件已随 chrome.release 清单打入安装包）
autoninja -C out/mcloud chrome mini_installer

# 9. 验证内置标志注入（可选）
pwsh $THOR_DIR/benchmark/tools/verify_builtin_flags.ps1
```

---

## 📦 GitHub Actions CI/CD

项目配置了简化的 GitHub Actions 工作流：

- **release.yml** — 推送 tag 时创建 GitHub Release 并生成发布说明

### 发布流程（实际执行方式）

安装包约 118MB，超过 GitHub 单文件 100MB 限制且被 .gitignore 排除，因此产物不入 git，直接上传到 Release：

```bash
# 1. 本地编译 + 打包 + 验证
autoninja -C out/mcloud mini_installer
pwsh benchmark/tools/verify_builtin_flags.ps1

# 2. 提交代码变更并打 tag
git add -A
git commit -m "M151: Chromium 151.0.7922.99"
git tag -a v151.0.7922.99 -m "MCloud Browser M151 (151.0.7922.99)"
git push origin main && git push origin v151.0.7922.99

# 3. 生成校验和并以 ADR-003 命名上传到 Release
# （注意：gh 的 file#newname 重命名语法不可靠，先本地重命名再上传）
cp mini_installer.exe mcloud_151.0.7922.99_win64_mini_installer.exe
sha256sum mcloud_151.0.7922.99_win64_mini_installer.exe > mcloud_151.0.7922.99_win64_mini_installer.exe.sha256
gh release create v151.0.7922.99 \
  mcloud_151.0.7922.99_win64_mini_installer.exe \
  mcloud_151.0.7922.99_win64_mini_installer.exe.sha256 \
  --title "MCloud Browser v151.0.7922.99" \
  --notes-file docs/superpowers/specs/2026-08-06-release-notes-m151.md
```

---

## 🔧 性能调优

### 启动参数

以下参数已通过 `mcloud_flags.txt` 内置到浏览器中（随安装包分发，启动时自动注入），无需手动设置；用户命令行参数优先级更高（同名开关跳过、enable/disable-features 合并）：

```ini
# GPU 光栅化
--enable-gpu-rasterization

# Canvas GPU 加速
--enable-features=CanvasOopRasterization

# 后台媒体不暂停
--disable-background-media-suspend

# 标签页冻结
--enable-features=InfiniteTabsFreezing,InfiniteTabsFreezingOnMemoryPressure

# V8 快速编译（注意：V8 flag 必须用下划线命名，连字符写法在 M151 不生效）
--js-flags="--invocation_count_for_maglev=200 --invocation_count_for_turbofan=1500 --osr-from-maglev --sparkplug-plus"
```

### chrome://flags 推荐设置

| 标志 | 推荐值 | 效果 |
|------|--------|------|
| #enable-gpu-rasterization | Enabled | GPU 光栅化 |
| #enable-zero-copy | Enabled | 零拷贝渲染 |
| #enable-parallel-downloading | Enabled | 并行下载 |
| #smooth-scrolling | Enabled | 平滑滚动 |

---

## 📊 实测基准（i9-14900HX，同机同方法）

### 内核升级对比（自动化 K1/K2/K7）

| 指标 | M151 | M150 | 变化 |
|------|------|------|------|
| K1 冷启动（中位数） | 73ms | 71ms | 持平（噪声内） |
| K2 内存（50 标签驻留 90s） | 2646MB | 2669MB | **-0.9%** |
| 安装包体积（仅观测） | 117.7MB | 112.3MB | +4.9% |

### 预载优化实测（M151-opt）

| 场景 | 结果 |
|------|------|
| B 站页面导航（预载命中） | **-5.6%**（1434ms vs 1519ms） |
| 真实站点 50 标签内存（取舍后） | **-203MB**（移除 3 项高内存低收益项） |

完整数据：[M150 基线](docs/dev-logs/M150-benchmark.md)、[M151 基线](docs/dev-logs/M151-benchmark.md)、[M151-opt 优化验证](docs/dev-logs/M151-opt-benchmark.md)。

---

## 🧪 基准测试体系

`benchmark/` 目录提供全套可复现基准工具：

| 工具 | 用途 |
|------|------|
| `run_baseline.ps1` | 一键采集 K1/K2/K7 基线并生成报告 |
| `bench_startup.ps1` / `bench_memory.ps1` / `bench_size.ps1` | 单项基准（支持 -ChromeExe/-ExtraFlags/-UrlsFile） |
| `bench_navigation.ps1` | 导航响应测试（预载收益验证，预载开/关对比） |
| `tools/verify_builtin_flags.ps1` | A6 验证：子进程命令行探测内置标志注入 |
| `tools/check_features.py` | 内核升级后 feature 存活性校验（防无效标志） |

```powershell
# 示例：采集基线并验证注入
pwsh benchmark\run_baseline.ps1 -Version M151
pwsh benchmark\tools\verify_builtin_flags.ps1
```

K3-K6（页面加载/JS/滚动/视频解码）为手工流程，见 `benchmark/README.md`。

---

## 🤝 贡献

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目基于 MIT 许可证开源。详见 [LICENSE.md](LICENSE.md)。

---

## 🙏 致谢

- [Thorium](https://github.com/Alex313031/thorium) — 原始项目基础
- [Chromium](https://www.chromium.org/) — 浏览器引擎
- [gz83/thorium](https://github.com/gz83/thorium) — API 密钥参考

---

<p align="center">
  Made with ❤️ by MCloud
</p>
