# CI/CD 工作流设计（简化版）

> 日期：2026-06-20
> 状态：已批准

## 概述

简化 CI/CD 工作流，只负责打包上传安装包到 GitHub Release，不参与编译。

## 设计目标

- 工作流只做打包上传，不编译
- 避免 CI 超时问题
- 本地编译完成后，推送 tag 即可自动发布

## 架构

```
本地编译完成 → mini_installer.exe
      ↓
推送 tag (v150.0.7871.37)
      ↓
GitHub Actions 自动触发
      ↓
上传安装包到 GitHub Release
```

## 文件结构

```
.github/workflows/
└── release.yml    # 只做打包上传（简化版）
```

## release.yml 设计

### 触发条件

```yaml
on:
  push:
    tags: ['v*']
```

### 工作流步骤

1. **检出仓库**
   - 使用 `actions/checkout@v6`
   - 获取完整历史（用于读取 Release Notes）

2. **读取 Release Notes**
   - 从 `docs/superpowers/specs/` 读取最新 Release Notes
   - 支持动态版本号

3. **创建 GitHub Release**
   - 使用 `softprops/action-gh-release@v2`
   - 设置 Release 标题和描述
   - 上传安装包

4. **上传安装包**
   - 从 `mini_installer.exe` 上传
   - 设置文件名为 `MCloud-Browser-{version}-Setup.exe`

### 环境变量

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
```

### 权限

```yaml
permissions:
  contents: write
```

## 本地工作流

### 编译步骤

```bash
# 1. 复制 MCloud 覆盖文件
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

# 5. 打包安装包
autoninja -C out/mcloud mini_installer
```

### 发布步骤

```bash
# 1. 提交更改
git add -A
git commit -m "M150: Chromium 150.0.7871.37"

# 2. 创建 tag
git tag -a v150.0.7871.37 -m "M150: Chromium 150.0.7871.37"

# 3. 推送
git push origin main
git push origin v150.0.7871.37

# 4. 工作流自动触发，上传安装包到 Release
```

## 优势

| 项目 | 改进 |
|------|------|
| CI 时间 | 从 3+ 小时 → 几秒钟 |
| 磁盘空间 | 不需要 60+ GB |
| 网络流量 | 不需要下载 Chromium 源码 |
| 维护成本 | 极低，只需维护一个简单工作流 |
| 可靠性 | 极高，没有编译失败风险 |

## 限制

- 安装包需要本地编译后手动推送到 GitHub
- CI 不参与编译，无法自动验证代码变更
- 需要本地环境配置完整（VS2026、depot_tools 等）

## 未来改进

如果需要 CI 参与编译，可以：
1. 使用自建 Runner（需要服务器）
2. 上传预编译工具链包（需要维护）
3. 使用 GitHub Actions 缓存（需要优化）
