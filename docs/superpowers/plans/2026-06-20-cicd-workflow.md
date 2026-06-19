# CI/CD 简化工作流实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 简化 CI/CD 工作流，只负责打包上传安装包到 GitHub Release，不参与编译。

**Architecture:** 推送 v* tag 时，工作流自动读取 Release Notes 并上传安装包到 GitHub Release。本地完成编译后，只需推送 tag 即可自动发布。

**Tech Stack:** GitHub Actions, softprops/action-gh-release, YAML

## Global Constraints

- 安装包路径：`mini_installer.exe`（本地编译产物）
- Tag 格式：`v*`（如 `v150.0.7871.37`）
- Release Notes 路径：`docs/superpowers/specs/YYYY-MM-DD-release-notes-m150.md`
- 权限：`contents: write`

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/release.yml` | 修改 | 简化为只做打包上传 |
| `.github/workflows/build.yml` | 删除 | 不再需要 CI 编译 |

---

### Task 1: 简化 release.yml

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Produces: 简化后的 release.yml，只做打包上传

- [ ] **Step 1: 备份现有 release.yml**

```bash
cp .github/workflows/release.yml .github/workflows/release.yml.bak
```

- [ ] **Step 2: 写入简化后的 release.yml**

```yaml
name: MCloud Browser Release

on:
  push:
    tags: ['v*']

permissions:
  contents: write

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

jobs:
  release:
    name: Upload Release
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/v}" >> $GITHUB_OUTPUT

      - name: Find release notes
        id: notes
        run: |
          # Find the latest release notes file
          NOTES_FILE=$(ls -t docs/superpowers/specs/*release-notes*.md 2>/dev/null | head -1)
          if [ -f "$NOTES_FILE" ]; then
            echo "NOTES_FILE=$NOTES_FILE" >> $GITHUB_OUTPUT
            echo "Found release notes: $NOTES_FILE"
          else
            echo "No release notes file found, using default"
            echo "NOTES_FILE=" >> $GITHUB_OUTPUT
          fi

      - name: Read release notes
        id: content
        run: |
          if [ -n "${{ steps.notes.outputs.NOTES_FILE }}" ]; then
            # Read the release notes file
            CONTENT=$(cat "${{ steps.notes.outputs.NOTES_FILE }}")
            # Set as output (handle multiline)
            echo "NOTES<<EOF" >> $GITHUB_OUTPUT
            echo "$CONTENT" >> $GITHUB_OUTPUT
            echo "EOF" >> $GITHUB_OUTPUT
          else
            echo "NOTES<<EOF" >> $GITHUB_OUTPUT
            echo "## MCloud Browser v${{ steps.version.outputs.VERSION }}" >> $GITHUB_OUTPUT
            echo "" >> $GITHUB_OUTPUT
            echo "Chromium ${{ steps.version.outputs.VERSION }} | AVX2 + FMA3" >> $GITHUB_OUTPUT
            echo "EOF" >> $GITHUB_OUTPUT
          fi

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: "MCloud Browser v${{ steps.version.outputs.VERSION }}"
          body: ${{ steps.content.outputs.NOTES }}
          files: mini_installer.exe
          draft: false
          prerelease: false
```

- [ ] **Step 3: 验证 YAML 语法**

```bash
# 检查 YAML 语法
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

预期输出：无错误

- [ ] **Step 4: 提交更改**

```bash
git add .github/workflows/release.yml
git commit -m "ci: simplify release workflow to only upload installer"
```

---

### Task 2: 删除 build.yml

**Files:**
- Delete: `.github/workflows/build.yml`

**Interfaces:**
- Produces: 移除不需要的 CI 编译工作流

- [ ] **Step 1: 删除 build.yml**

```bash
rm .github/workflows/build.yml
```

- [ ] **Step 2: 提交更改**

```bash
git add -A
git commit -m "ci: remove build.yml (no longer needed)"
```

---

### Task 3: 验证工作流

**Files:**
- None (验证)

**Interfaces:**
- Consumes: Task 1-2 的修改结果
- Produces: 验证报告

- [ ] **Step 1: 检查工作流文件**

```bash
ls -la .github/workflows/
```

预期输出：
```
total 8
drwxr-xr-x 1 user group  200 Jun 20 10:00 ./
drwxr-xr-x 1 user group  200 Jun 20 10:00 ../
-rw-r--r-- 1 user group 1500 Jun 20 10:00 release.yml
```

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"
```

预期输出：无错误

- [ ] **Step 3: 检查触发条件**

```bash
grep -A2 "on:" .github/workflows/release.yml
```

预期输出：
```yaml
on:
  push:
    tags: ['v*']
```

- [ ] **Step 4: 检查权限**

```bash
grep "permissions:" .github/workflows/release.yml
```

预期输出：
```yaml
permissions:
  contents: write
```

---

## 验收标准

| 指标 | 目标 |
|------|------|
| release.yml 语法 | 无错误 |
| 触发条件 | 推送 v* tag 时触发 |
| 权限 | contents: write |
| 安装包上传 | mini_installer.exe 上传到 Release |
| Release Notes | 自动读取 docs/superpowers/specs/ 中的文件 |
| CI 时间 | < 10 分钟 |
| build.yml | 已删除 |

---

## 使用流程

### 本地编译

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

### 发布

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
