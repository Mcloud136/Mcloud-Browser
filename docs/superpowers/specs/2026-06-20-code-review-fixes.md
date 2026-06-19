# 代码审查修复记录

> 日期：2026-06-20
> 状态：已修复，待下次编译生效

## 已修复问题

### 不需要重编（已生效）

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 4 | PauseMutedBackgroundAudio 暂停后台视频 | 移除 | mcloud_flags.txt |
| 5 | SyncPointGraphValidation GPU 调试开销 | 移除 | mcloud_flags.txt |
| 14 | AggressiveShaderCacheLimits 缓存抖动 | 移除 | mcloud_flags.txt |
| 8 | EnableAdpfEfficiencyMode Android-only | 移除 | mcloud_flags.txt |

### 需要下次编译生效

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | win/BUILD.gn AVX2 无条件注入 | 移除重复块，由 thorium_simd_optimization 统一处理 | src/build/config/win/BUILD.gn |
| 2 | PGO 路径硬编码 | 移除 pgo_data_path，让 Chromium 自动查找 | win_args_mcloud.gn |
| 3 | AVX2/FMA 标志重复 | 移除 win/BUILD.gn 中的重复块 | src/build/config/win/BUILD.gn |
| 6 | enable_vr 无效参数 | 移除 | win_args_mcloud.gn |
| 7 | 三重 -O3 指定 | 简化为 /clang:-O3 | src/build/config/compiler/BUILD.gn |
| 9 | enable_stripping 无效参数 | 移除 | win_args_mcloud.gn |
| 10 | enable_rust 冗余 | 移除 | win_args_mcloud.gn |
| 11 | enable_rlz 隐私问题 | 改为 false | win_args_mcloud.gn |
| 12 | use_text_section_splitting Windows 无效 | 移除 | win_args_mcloud.gn |
| 13 | AVX-512 rustflags 缺少 +bmi | 添加 +bmi | src/build/config/compiler/BUILD.gn |

## 下次编译命令

```bash
cd /d/wxmuma/chromium-src/src

# 1. 同步覆盖文件
export THOR_DIR="/d/wxmuma/thorium"
export CR_DIR="/d/wxmuma/chromium-src/src"
python3 $THOR_DIR/win_scripts/copy_essentials.py

# 2. 复制 args.gn
cp $THOR_DIR/win_args_mcloud.gn out/mcloud/args.gn

# 3. 生成构建文件
export PATH="/d/wxmuma/depot_tools:$PATH"
export DEPOT_TOOLS_WIN_TOOLCHAIN=0
export vs2026_install="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools"
export INCLUDE="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/14.51.36231/atlmfc/include;$INCLUDE"
gn gen out/mcloud --check

# 4. 编译
autoninja -C out/mcloud chrome
```

## 编译后验证

- `chrome://flags` — 检查标志状态
- `chrome://media-internals` — 验证视频解码器类型（实际为 D3D11，D3D12 不可用）
- B 站/YouTube — 视频播放测试
- HTTP 网站 — 确认不断流

## D3D12 视频解码测试结果

| 测试项 | 结果 |
|--------|------|
| 编译时配置 | ✅ `kD3D12VideoDecoder = ENABLED_BY_DEFAULT` |
| 命令行强制启用 | ❌ 仍回退到 D3D11 |
| 独显测试 | ❌ 显示 D3D11VideoDecoder |
| 核显测试 | ❌ 显示 D3D11VideoDecoder |

**结论**：D3D12 视频解码在当前硬件/驱动上不可用，保持 D3D11。
