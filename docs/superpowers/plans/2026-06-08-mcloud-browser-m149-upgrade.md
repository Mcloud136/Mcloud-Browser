# MCloud Browser M144 → M149 升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MCloud Browser 从 Chromium 144.0.7559.254 升级到 149.0.7827.53，使用纯 AVX2 编译优化，并增加 Bilibili 专项优化和 GitHub Actions CI/CD。

**Architecture:** 基于 Thorium 的文件覆盖 + git apply 补丁机制。M149 源码独立拉取后，将 MCloud Browser 的 `src/` 目录文件覆盖到 Chromium 源码树上，然后逐个应用补丁。AVX2 通过 GN 参数 `use_avx2 = true` 全局启用。

**Tech Stack:** Chromium M149, GN (构建系统), Ninja, Clang, FFmpeg, V8, GitHub Actions

**平台:** Windows x64

**构建系统:** WSL2 (Linux 环境) + 交叉编译到 Windows，或原生 Windows (depot_tools)

---

## 文件结构

### 核心构建配置
- `win_args_mcloud.gn` — MCloud Browser 的 GN 构建参数（已创建，需适配 M149）
- `win_scripts/setup.py` — Windows 构建脚本，负责复制源码和应用补丁
- `win_scripts/build_win.py` — Windows 构建脚本
- `win_scripts/version.py` — 版本管理脚本

### 品牌/字符串资源
- `src/chrome/app/chromium_strings.grd` — 主品牌字符串（已完成重命名）
- `src/chrome/app/settings_chromium_strings.grdp` — 设置页面字符串
- `src/chrome/app/shared_settings_strings.grdp` — 共享设置字符串
- `src/chrome/app/mcloud_strings.grdp` — 自定义字符串

### 补丁文件
- `other/ftp-support-mcloud.patch` — FTP 支持
- `other/mcloud-2024-ui.patch` — 经典 UI
- `other/mcloud_webui.patch` — WebUI 定制
- `other/GPC.patch` — Global Privacy Control
- `other/disable-privacy-sandbox.patch` — 禁用 Privacy Sandbox
- `other/mini_installer.patch` — Windows 安装程序
- `other/restore_download_shelf.patch` — 下载栏
- `other/allow_manifest_v2_extensions.patch` — MV2 扩展支持
- `other/keyboard_shortcuts.patch` — 键盘快捷键
- `other/fix_dangling_pointer_tooltip.patch` — M145 起可移除
- `other/fix_deb_dependency_generation.patch` — M149 起可移除
- `other/fix_disable_aero_crash.patch` — Aero 崩溃修复
- `other/fix-policy-templates.patch` — 策略模板修复

### CI/CD
- `.github/workflows/build.yml` — GitHub Actions 构建工作流
- `.github/workflows/release.yml` — 发布工作流

---

## 阶段一：M149 基础构建

### Task 1: 拉取 Chromium M149 源码

**目标:** 获取 Chromium 149.0.7827.53 完整源码

- [ ] **Step 1: 创建工作目录并拉取 Chromium**

```bash
mkdir -p ~/chromium && cd ~/chromium
fetch --nohooks chromium
```

预计耗时：20-60 分钟（取决于网络速度）

- [ ] **Step 2: 切换到 M149 tag**

```bash
cd ~/chromium/src
git checkout tags/149.0.7827.53
```

- [ ] **Step 3: 同步依赖**

```bash
gclient sync --with_branch_heads --with_tags --force --reset --nohooks --delete_unversioned_trees
gclient runhooks
```

预计耗时：30-60 分钟

- [ ] **Step 4: 下载 PGO profiles**

```bash
cd ~/chromium/src
python3 tools/update_pgo_profiles.py --target=win64 update --gs-url-base=chromium-optimization-profiles/pgo_profiles
```

- [ ] **Step 5: 验证源码完整性**

```bash
cd ~/chromium/src
git log --oneline -1
# 预期输出包含 149.0.7778.xxx 或 149.0.7827.53
```

- [ ] **Step 6: 记录 PGO profile 路径**

```bash
ls ~/chromium/src/chrome/build/pgo_profiles/ | grep win64
# 记录输出的 .profdata 文件名，用于更新 win_args_mcloud.gn 中的 pgo_data_path
```

---

### Task 2: 验证 M149 GN 参数兼容性

**目标:** 确保 `win_args_mcloud.gn` 中的所有参数在 M149 中有效

- [ ] **Step 1: 复制 GN 参数到 M149 构建目录**

```bash
mkdir -p ~/chromium/src/out/mcloud
cp ~/mcloud-browser/win_args_mcloud.gn ~/chromium/src/out/mcloud/args.gn
```

- [ ] **Step 2: 更新 PGO profile 路径**

编辑 `win_args_mcloud.gn`，将 `pgo_data_path` 更新为 M149 的实际 profile 文件路径：

```gn
pgo_data_path = "C:/src/chromium/src/chrome/build/pgo_profiles/<实际的M149 .profdata 文件名>"
```

- [ ] **Step 3: 运行 GN 检查参数**

```bash
cd ~/chromium/src
gn gen out/mcloud --check
```

- [ ] **Step 4: 处理参数错误**

如果 GN 报错某个参数不存在或已废弃：
1. 在 `~/chromium/src/build/config/` 中搜索该参数的定义
2. 查找 M149 中的替代参数
3. 更新 `win_args_mcloud.gn`
4. 重新运行 `gn gen`

记录所有需要修改的参数。

- [ ] **Step 5: 验证 GN 生成成功**

```bash
gn args out/mcloud --list --short | grep -E "use_avx2|use_fma|v8_enable_wasm_simd256"
```

确认 AVX2 相关参数已正确设置。

- [ ] **Step 6: 提交参数更新**

```bash
git add win_args_mcloud.gn
git commit -m "build: update GN args for M149 compatibility"
```

---

### Task 3: 无补丁最小化构建测试

**目标:** 验证纯 Chromium M149 + GN 参数能在 Windows 上编译成功

- [ ] **Step 1: 启动最小化构建**

```bash
cd ~/chromium/src
gn gen out/mcloud --args="$(cat ~/mcloud-browser/win_args_mcloud.gn)"
autoninja -C out/mcloud chrome
```

预计耗时：2-6 小时（取决于硬件）

- [ ] **Step 2: 处理编译错误**

如果编译失败：
1. 记录错误信息
2. 检查是否是 GN 参数问题
3. 如果是 FFmpeg 相关错误，检查 M149 的 ffmpeg 版本
4. 如果是 V8 相关错误，检查 V8 参数兼容性
5. 修复后重新编译

- [ ] **Step 3: 验证构建产物**

```bash
ls -la out/mcloud/chrome.exe
# 确认 chrome.exe 存在且大小合理（通常 200MB+）
```

- [ ] **Step 4: 运行基本功能测试**

```bash
out/mcloud/chrome.exe --no-first-run --user-data-dir=/tmp/mcloud-test
# 确认浏览器能启动并加载页面
```

- [ ] **Step 5: 记录构建结果**

记录：
- 编译是否成功
- 遇到的错误及修复方法
- 构建产物大小
- 启动是否正常

---

## 阶段二：AVX2 原生编译验证

### Task 4: 验证 AVX2 编译生效

**目标:** 确认 AVX2 指令在编译产物中实际使用

- [ ] **Step 1: 检查编译器标志**

```bash
# 在构建日志中搜索 AVX2 相关编译标志
grep -r "mavx2\|/arch:AVX2\|mavx\|mfma" out/mcloud/build.ninja | head -20
```

确认至少部分源文件使用了 AVX2 编译标志。

- [ ] **Step 2: 检查二进制中的 AVX2 指令**

```bash
# 使用 dumpbin (Windows) 或 objdump 检查
dumpbin /disasm out/mcloud/chrome.exe | grep -i "vmov\|vadd\|vmul\|vfma" | head -20
```

确认二进制中包含 AVX2 指令（vmovdqu, vpaddd 等）。

- [ ] **Step 3: 验证 V8 SIMD256**

```bash
# 检查 V8 的 WASM SIMD256 支持
grep -r "wasm_simd256" out/mcloud/v8/ | head -10
```

- [ ] **Step 4: 运行性能基准测试（可选）**

```bash
out/mcloud/chrome.exe --no-first-run --enable-precise-memory-info --js-flags="--allow-natives-syntax"
# 在浏览器中运行 Octane 2.0 或 Speedometer 3.0 基准测试
```

记录基准测试分数作为后续对比。

- [ ] **Step 5: 提交 AVX2 验证结果**

```bash
git commit --allow-empty -m "build: AVX2 native compilation verified on M149"
```

---

## 阶段三：媒体编解码器补丁迁移

### Task 5: 迁移 FFmpeg HEVC 补丁

**目标:** 在 M149 的 FFmpeg 中启用 HEVC 解码支持

- [ ] **Step 1: 检查 M149 的 FFmpeg 版本**

```bash
cd ~/chromium/src/third_party/ffmpeg
git log --oneline -5
cat RELEASE
```

- [ ] **Step 2: 检查 M149 是否已原生支持 HEVC**

```bash
grep -r "hevc\|HEVC" ~/chromium/src/third_party/ffmpeg/chromium/config/Chrome/x64/config.h | head -10
```

如果 M149 已原生支持 HEVC，跳过此任务。

- [ ] **Step 3: 对比 FFmpeg 版本差异**

```bash
diff ~/mcloud-browser/other/add-hevc-ffmpeg-decoder-parser.patch ~/chromium/src/third_party/ffmpeg/
```

- [ ] **Step 4: 适配 HEVC 补丁**

如果补丁无法直接应用：
1. 检查 reject 文件：`find ~/chromium/src -name "*.rej" | head -20`
2. 手动解决冲突
3. 重新生成适配 M149 的补丁

- [ ] **Step 5: 应用 HEVC 补丁**

```bash
cd ~/chromium/src/third_party/ffmpeg
git apply ~/mcloud-browser/other/add-hevc-ffmpeg-decoder-parser.patch
git apply ~/mcloud-browser/other/change-libavcodec-header.patch
```

- [ ] **Step 6: 验证 HEVC 编译**

```bash
cd ~/chromium/src
autoninja -C out/mcloud media_unittests
out/mcloud/media_unittests --gtest_filter="*HEVC*"
```

- [ ] **Step 7: 提交 HEVC 补丁更新**

```bash
git add other/add-hevc-ffmpeg-decoder-parser.patch
git commit -m "media: adapt HEVC FFmpeg patch for M149"
```

---

### Task 6: 迁移 JPEG XL 支持

**目标:** 更新 thorium-libjxl 子模块以兼容 M149

- [ ] **Step 1: 检查 mcloud-libjxl 子模块状态**

```bash
cd ~/mcloud-browser/mcloud-libjxl
git log --oneline -5
cat src/DEPS | head -20
```

- [ ] **Step 2: 更新 libjxl DEPS**

对比 M149 的 DEPS 格式，更新 `mcloud-libjxl/src/DEPS` 中的依赖版本。

- [ ] **Step 3: 复制 libjxl 源码到 Chromium**

```bash
cp -r ~/mcloud-browser/mcloud-libjxl/src/. ~/chromium/src/
```

- [ ] **Step 4: 验证 JPEG XL 编译**

```bash
cd ~/chromium/src
autoninja -C out/mcloud chrome
# 在浏览器中访问包含 JPEG XL 图片的测试页面
```

- [ ] **Step 5: 提交 libjxl 更新**

```bash
git add mcloud-libjxl/
git commit -m "media: update libjxl for M149 compatibility"
```

---

### Task 7: 验证 Widevine/AC3/Dolby Vision

**目标:** 确认 DRM 和高级编解码器在 M149 中正常工作

- [ ] **Step 1: 检查 Widevine CDM 集成**

```bash
grep -r "widevine\|WIDEVINE" ~/chromium/src/out/mcloud/args.gn
# 确认 enable_widevine = true, bundle_widevine_cdm = true
```

- [ ] **Step 2: 验证 AC3/E-AC3 支持**

```bash
grep -r "ac3\|eac3\|AC3" ~/chromium/src/media/ | head -10
# 确认 enable_platform_ac3_eac3_audio 参数生效
```

- [ ] **Step 3: 测试 DRM 内容**

在构建的浏览器中访问：
- https://bitmovin.com/demos/drm — 测试 Widevine DRM
- 包含 HEVC 的视频流 — 测试硬件解码

- [ ] **Step 4: 记录测试结果**

记录哪些编解码器工作正常，哪些需要额外修复。

---

## 阶段四：UI/功能补丁迁移

### Task 8: 迁移 FTP 支持补丁

**目标:** 在 M149 中恢复 FTP 协议支持

- [ ] **Step 1: 检查 M149 的 FTP 代码状态**

```bash
ls ~/chromium/src/net/ftp/
# 如果目录不存在，FTP 代码已被完全移除
```

- [ ] **Step 2: 尝试应用 FTP 补丁**

```bash
cd ~/chromium/src
git apply --reject ~/mcloud-browser/other/ftp-support-mcloud.patch
```

- [ ] **Step 3: 处理 reject 文件**

```bash
find . -name "*.rej" | while read f; do
    echo "=== $f ==="
    cat "$f"
done
```

- [ ] **Step 4: 手动适配 FTP 代码**

如果 FTP 代码已被移除：
1. 从 M144 的 Chromium 源码中提取 `net/ftp/` 目录
2. 将其复制到 M149 的源码树中
3. 更新 `BUILD.gn` 以包含 FTP 模块
4. 适配 API 变更

- [ ] **Step 5: 验证 FTP 功能**

```bash
out/mcloud/chrome.exe ftp://test.rebex.net/readme.txt
```

- [ ] **Step 6: 提交 FTP 补丁**

```bash
git add other/ftp-support-mcloud.patch
git commit -m "net: restore FTP support for M149"
```

---

### Task 9: 迁移 Thorium 2024 UI 补丁

**目标:** 恢复经典 UI（标签栏、Omnibox 等）

- [ ] **Step 1: 尝试应用 UI 补丁**

```bash
cd ~/chromium/src
git apply --reject ~/mcloud-browser/other/mcloud-2024-ui.patch
```

- [ ] **Step 2: 分析所有 reject**

```bash
find . -name "*.rej" | wc -l
# 记录 reject 数量
```

- [ ] **Step 3: 逐个解决 UI 冲突**

对于每个 reject 文件：
1. 阅读 reject 内容，理解原始修改意图
2. 在 M149 的对应文件中找到新位置
3. 应用等效的修改
4. 删除 reject 文件

- [ ] **Step 4: 适配 mcloud_flag_entries.h**

检查 `src/chrome/browser/mcloud_flag_entries.h` 中的标志在 M149 中是否仍然有效：
- `thorium-2024` → `mcloud-2024` 标志
- `download-shelf` 标志
- `rectangular-tabs` 标志
- `custom-tab-width` 标志

- [ ] **Step 5: 验证 UI 功能**

```bash
out/mcloud/chrome.exe --enable-features=Mcloud2024
# 检查经典 UI 是否正常显示
```

- [ ] **Step 6: 提交 UI 补丁**

```bash
git add -A
git commit -m "ui: adapt MCloud 2024 UI patch for M149"
```

---

### Task 10: 迁移 Manifest V2 扩展支持

**目标:** 在 M149 中继续支持 MV2 扩展

- [ ] **Step 1: 检查 M149 的 MV2 代码状态**

```bash
ls ~/chromium/src/extensions/browser/manifest_v2/
# 如果目录不存在，MV2 代码已被移除
```

- [ ] **Step 2: 尝试应用 MV2 补丁**

```bash
cd ~/chromium/src
git apply --reject ~/mcloud-browser/other/allow_manifest_v2_extensions.patch
```

- [ ] **Step 3: 处理 MV2 代码移除**

如果 MV2 代码已被移除：
1. 从 M144 提取 MV2 相关代码
2. 在 M149 中重新实现 MV2 支持
3. 可能需要修改 `extensions/browser/manifest_verifier.cc`

- [ ] **Step 4: 测试 MV2 扩展**

安装一个 MV2 扩展（如 uBlock Origin Legacy）验证是否正常工作。

- [ ] **Step 5: 提交 MV2 补丁**

```bash
git add other/allow_manifest_v2_extensions.patch
git commit -m "extensions: restore MV2 extension support for M149"
```

---

### Task 11: 迁移剩余 UI/功能补丁

**目标:** 应用下载栏、搜索引擎、键盘快捷键等补丁

- [ ] **Step 1: 应用下载栏补丁**

```bash
cd ~/chromium/src
git apply --reject ~/mcloud-browser/other/restore_download_shelf.patch
```

- [ ] **Step 2: 应用 WebUI 补丁**

```bash
git apply --reject ~/mcloud-browser/other/mcloud_webui.patch
```

- [ ] **Step 3: 应用键盘快捷键补丁**

```bash
git apply --reject ~/mcloud-browser/other/keyboard_shortcuts.patch
```

- [ ] **Step 4: 应用 mini_installer 补丁**

```bash
git apply --reject ~/mcloud-browser/other/mini_installer.patch
```

- [ ] **Step 5: 应用 open_in_same_tab 补丁**

```bash
git apply --reject ~/mcloud-browser/other/open_in_same_tab.patch
```

- [ ] **Step 6: 处理所有 reject**

对每个 reject 文件进行手动适配。

- [ ] **Step 7: 验证功能**

测试：
- 下载文件时是否显示经典下载栏
- 新标签页是否正确
- 键盘快捷键是否工作
- 安装程序是否正常生成

- [ ] **Step 8: 提交所有 UI 补丁**

```bash
git add -A
git commit -m "ui: migrate remaining UI patches for M149"
```

---

## 阶段五：隐私/安全补丁迁移

### Task 12: 迁移隐私增强补丁

**目标:** 恢复所有隐私保护功能

- [ ] **Step 1: 应用 GPC 补丁**

```bash
cd ~/chromium/src
git apply --reject ~/mcloud-browser/other/GPC.patch
```

- [ ] **Step 2: 应用 Privacy Sandbox 禁用补丁**

```bash
git apply --reject ~/mcloud-browser/other/disable-privacy-sandbox.patch
```

- [ ] **Step 3: 应用策略模板补丁**

```bash
git apply --reject ~/mcloud-browser/other/fix-policy-templates.patch
```

- [ ] **Step 4: 应用 Aero 崩溃修复补丁**

```bash
git apply --reject ~/mcloud-browser/other/fix_disable_aero_crash.patch
```

- [ ] **Step 5: 处理 M149 可移除的补丁**

以下补丁在 M149 中不再需要（上游已修复）：
- ~~`fix_dangling_pointer_tooltip.patch`~~ — M145 起已修复
- ~~`fix_deb_dependency_generation.patch`~~ — M149 起已修复

确认这些补丁确实不再需要后，从 `setup.py` 中移除相关代码。

- [ ] **Step 6: 更新 setup.py 中的补丁列表**

编辑 `win_scripts/setup.py`，更新补丁应用逻辑：
1. 移除已废弃的补丁
2. 更新补丁文件名（thorium → mcloud）
3. 确保所有补丁路径正确

- [ ] **Step 7: 验证隐私功能**

```bash
out/mcloud/chrome.exe
# 访问 https://privacycheck.sec.in.tum.de/ 验证 GPC
# 检查 chrome://settings/privacy 验证 Privacy Sandbox 已禁用
```

- [ ] **Step 8: 提交隐私补丁**

```bash
git add -A
git commit -m "privacy: migrate privacy patches for M149"
```

---

## 阶段六：视频播放优化 + Bilibili 专项

### Task 13: 视频硬件解码优化

**目标:** 确保 DXVA2/D3D11VA 硬件解码在 M149 中正常工作

- [ ] **Step 1: 验证硬件解码 GN 参数**

```bash
# 在 args.gn 中确认以下参数
grep -E "enable_platform_hevc|enable_hevc_parser|platform_has_optional" out/mcloud/args.gn
```

- [ ] **Step 2: 添加视频优化命令行标志**

编辑 `src/chrome/app/mcloud_strings.grdp` 或创建启动脚本，添加优化标志：

```
--enable-features=PlatformHEVCDecoder,MediaFoundationH265Encoding
--force-video-overlays
```

- [ ] **Step 3: 测试硬件解码**

在构建的浏览器中：
1. 访问 `chrome://gpu/` — 确认 "Video Decode" 显示 "Hardware accelerated"
2. 播放 4K HEVC 视频 — 确认 GPU 解码生效（通过任务管理器查看 GPU Video Decode 使用率）
3. 播放 AV1 视频 — 确认硬件解码正常

- [ ] **Step 4: 测试 MSE 缓冲**

播放 YouTube 4K 视频，观察：
- 缓冲是否频繁中断
- 切换清晰度是否流畅
- 长时间播放是否有内存泄漏

- [ ] **Step 5: 提交视频优化**

```bash
git add -A
git commit -m "media: optimize video hardware decode for M149"
```

---

### Task 14: Bilibili 专项优化

**目标:** 针对 Bilibili 的播放器和弹幕系统进行优化

- [ ] **Step 1: 分析 Bilibili 播放器技术栈**

在浏览器开发者工具中分析 Bilibili 视频页面：
- 确认使用的编解码器（H.264/HEVC）
- 确认流媒体协议（DASH/HTTP-FLV）
- 确认弹幕渲染方式（Canvas/WebGL）

- [ ] **Step 2: 优化 MSE 缓冲策略**

通过 Chromium feature flags 优化 Bilibili DASH 流的缓冲：

编辑 `src/chrome/browser/about_flags.cc`，添加 Bilibili 优化相关标志。

- [ ] **Step 3: 优化弹幕渲染性能**

检查 Skia 的 AVX2 路径是否对 Canvas 2D 渲染生效：
1. 访问 Bilibili 视频页面
2. 开启高密度弹幕
3. 通过 `chrome://tracing/` 记录渲染性能
4. 确认弹幕渲染没有掉帧

- [ ] **Step 4: 测试 HEVC 硬解（Bilibili 大会员）**

如果有 Bilibili 大会员：
1. 播放 HEVC 编码的视频
2. 确认走 D3D11VA 硬解路径
3. 对比软解性能差异

- [ ] **Step 5: 优化长视频内存管理**

播放 Bilibili 长视频（2小时+），监控内存使用：
1. 打开任务管理器
2. 观察内存是否持续增长
3. 确认没有内存泄漏

- [ ] **Step 6: 提交 Bilibili 优化**

```bash
git add -A
git commit -m "media: add Bilibili playback optimizations"
```

---

## 阶段七：CI/CD + GitHub Actions

### Task 15: 创建 GitHub Actions 构建工作流

**目标:** 自动化 MCloud Browser 的构建流程

- [ ] **Step 1: 创建 GitHub 仓库**

在 GitHub 上创建 `Mcloud-Browser` 仓库。

- [ ] **Step 2: 创建构建工作流**

创建 `.github/workflows/build.yml`：

```yaml
name: MCloud Browser Build

on:
  push:
    branches: [main, M149]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: windows-latest
    timeout-minutes: 360  # Chromium builds take 3-6 hours
    steps:
      - name: Checkout MCloud Browser
        uses: actions/checkout@v6

      - name: Cache depot_tools
        uses: actions/cache@v4
        with:
          path: depot_tools
          key: depot-tools-${{ runner.os }}-${{ hashFiles('**/version.sh') }}
          restore-keys: depot-tools-${{ runner.os }}-

      - name: Setup depot_tools
        run: |
          if (-not (Test-Path depot_tools)) {
            git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
          }
          echo "$PWD\depot_tools" | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append

      - name: Fetch Chromium M149
        run: |
          mkdir chromium
          cd chromium
          fetch --nohooks chromium
          cd src
          git checkout tags/149.0.7827.53
          gclient sync --with_branch_heads --with_tags --force --reset --nohooks --delete_unversioned_trees
          gclient runhooks

      - name: Download PGO profiles
        run: |
          cd chromium\src
          python3 tools/update_pgo_profiles.py --target=win64 update --gs-url-base=chromium-optimization-profiles/pgo_profiles

      - name: Apply MCloud Browser patches
        run: |
          cd chromium\src
          python ..\..\..\win_scripts\setup.py

      - name: Build MCloud Browser
        run: |
          cd chromium\src
          gn gen out\mcloud --args="is_official_build=true is_debug=false target_os=\"win\" target_cpu=\"x64\" use_avx2=true use_fma=true is_clang=true use_lld=true use_thin_lto=true"
          autoninja -C out\mcloud chrome

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: mcloud-browser-win64-avx2
          path: chromium\src\out\mcloud\chrome.exe
```

- [ ] **Step 3: 创建发布工作流**

创建 `.github/workflows/release.yml`：

```yaml
name: MCloud Browser Release

on:
  push:
    tags: ['v*']

jobs:
  build-and-release:
    runs-on: windows-latest
    timeout-minutes: 360
    steps:
      - uses: actions/checkout@v6

      # ... (build steps same as above)

      - name: Create installer
        run: |
          cd chromium\src
          autoninja -C out\mcloud mini_installer

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            chromium\src\out\mcloud\mini_installer.exe
          generate_release_notes: true
```

- [ ] **Step 4: 测试 CI 工作流**

```bash
git push origin main
# 在 GitHub Actions 页面查看构建状态
```

- [ ] **Step 5: 优化构建缓存**

添加 Chromium 源码缓存以加速后续构建：

```yaml
- name: Cache Chromium source
  uses: actions/cache@v4
  with:
    path: chromium
    key: chromium-149-${{ runner.os }}
    restore-keys: chromium-149-
```

- [ ] **Step 6: 提交 CI 配置**

```bash
git add .github/
git commit -m "ci: add GitHub Actions build and release workflows"
```

---

## 阶段八：集成测试与发布

### Task 16: 全量构建验证

**目标:** 完整构建并验证所有功能

- [ ] **Step 1: 清理并完整重新构建**

```bash
cd ~/chromium/src
rm -rf out/mcloud
gn gen out/mcloud --args="$(cat ~/mcloud-browser/win_args_mcloud.gn)"
autoninja -C out/mcloud chrome
```

- [ ] **Step 2: 运行功能测试清单**

| 功能 | 测试方法 | 预期结果 |
|------|---------|---------|
| 基本浏览 | 访问多个网站 | 正常加载 |
| AVX2 指令 | dumpbin 检查 | 包含 vmov/vadd 等 |
| HEVC 解码 | 播放 HEVC 视频 | 硬件解码正常 |
| Widevine DRM | 访问 DRM 测试页面 | DRM 正常工作 |
| FTP | 访问 ftp:// 站点 | 正常加载 |
| 经典 UI | 启用 mcloud-2024 标志 | UI 正确显示 |
| 下载栏 | 下载文件 | 显示经典下载栏 |
| GPC | 隐私检测页面 | GPC 头部存在 |
| Bilibili | 播放视频+弹幕 | 流畅无掉帧 |
| MV2 扩展 | 安装 uBlock Origin | 正常工作 |

- [ ] **Step 3: 记录测试结果**

创建测试报告文档。

- [ ] **Step 4: 创建发布 tag**

```bash
git tag v149.0.0
git push origin v149.0.0
```

- [ ] **Step 5: 推送到 GitHub**

```bash
git remote add origin https://github.com/<你的用户名>/Mcloud-Browser.git
git push -u origin main
git push origin v149.0.0
```

---

## 依赖关系

```
Task 1 (拉取源码)
  └─→ Task 2 (验证GN参数)
       └─→ Task 3 (最小化构建)
            ├─→ Task 4 (AVX2验证)
            ├─→ Task 5 (HEVC补丁)
            │    └─→ Task 7 (Widevine/AC3验证)
            ├─→ Task 6 (JPEG XL)
            ├─→ Task 8 (FTP补丁)
            ├─→ Task 9 (UI补丁)
            │    └─→ Task 11 (剩余UI补丁)
            ├─→ Task 10 (MV2扩展)
            ├─→ Task 12 (隐私补丁)
            └─→ Task 13 (视频优化)
                 └─→ Task 14 (Bilibili优化)
                      └─→ Task 15 (CI/CD)
                           └─→ Task 16 (集成测试)
```

## 风险与回退

| 风险 | 回退方案 |
|------|---------|
| GN 参数在 M149 中不兼容 | 查阅 M149 的 `build/config/` 文档，逐参数排查 |
| 补丁冲突过多 | 先只应用核心补丁（HEVC/Widevine/AVX2），其余后续添加 |
| 编译时间过长 | 使用 `ccache` 加速，或分模块编译 |
| GitHub Actions 超时 | 使用 self-hosted runner，或拆分为多个 job |
