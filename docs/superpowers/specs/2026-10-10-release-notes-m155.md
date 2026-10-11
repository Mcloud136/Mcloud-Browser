# MCloud Browser v155.0.8059.40

基于 Chromium **M155（155.0.8059.40）**，Windows x64。本版是一次内核升级（M151 → M155），保持既有性能取向与
已定案的稳定性禁用项，并在升级过程中修正了两处口径问题。

## 变化

- **内核 M155**：V8 15.5.35.20、clang `llvmorg-24-init-7747`、PGO 使用 8059 系列 profile。
- **定制面更小**：需要重放的上游改动由 7 个文件降到 **6 个文件**——不再翻转 `kD3D12VideoDecoder`
  上游默认（该解码器仍由启动标志显式禁用，以规避 Intel 核显 D3D12 解码绿屏）。
- **冻结缓解真正生效**：`SkiaGraphite` 在上游本就是默认启用，此前仅注释掉启用行并不构成禁用；
  本版改为显式 `--disable-features=SkiaGraphite`（其余 3 项禁用状态不变）。
- **清单去虚**：删除 `FlingSchedulingImprovements`（M155 起上游已彻底移除该 feature）。
- **安装版才真正带上优化清单（r4）**：`mcloud_flags.txt` 改由 VersionDir 投递到 `Application/155.0.8059.40/`，加载器 v8 按 chrome.dll 所在目录（`base::DIR_MODULE`）优先查找，兼容开发树/便携包的扁平布局与安装版的版本子目录布局。此前登记在 Application 根目录的条目会被打包但**不被安装**（setup.exe 对根目录只搬固定三件套），所以 r3 及更早的安装包在干净机器上等于零内置优化（缺陷 D105）。
- **加载器路径优先级修正（r5）**：v7 以 exe 同目录为第一候选，会让一份残留的 `Application\mcloud_flags.txt` 永久静默压掉安装包投递的正式文件（缺陷 D109）。v8 改以 chrome.dll 所在目录为第一候选，与上游 `GetModulePath` 同口径。

## 安装（两个发布物，请用 setup 那个）

| 文件 | 用途 |
|---|---|
| `mcloud_155.0.8059.40_win64_setup.exe` | **推荐**。外层安装包装器：优雅关闭正在运行的本产品实例 → 安装 → **复验根 chrome.exe 确实升到本版本** → 清理临时文件与残留进程 → 自动重启浏览器。默认装到用户级目录（不弹 UAC）；加 `--system-level` 走系统级（自举提权）。 |
| `mcloud_155.0.8059.40_win64_mini_installer.exe` | 上游原生安装器本体。**如果浏览器正在运行，更新会静默不生效**——根启动桩是被锁的映像，上游把它暂存成 `new_chrome.exe` 并把收尾改名委托给 Google Update，而本产品不发布 Google Update（缺陷 D119，已实测）。只在浏览器已完全退出、或你确认自己需要裸安装器时使用。 |

包装器另有 `--list-only`（只报告将关闭哪些实例、不关闭不安装）与 `--no-launch`（装完不重启）两个开关，退出码 0=成功且已复验 / 1=复验未通过 / 2=环境不满足。

## 实测（同一台机器、同一时刻成对测量）

| 指标 | M151-r3 | M155 |
|---|---|---|
| K1 冷启动中位数 | 46 ms | 45 ms |
| K2 50 标签驻留中位数 | 2590 MB | 2563.3 MB（-1.0%） |
| 标签开合后的驻留漂移 | +3.7 MB/轮 | -2.4 MB/轮（无正漂移） |
| GPU 渲染路径 | GPU 进程 + D3D11/D3D12 ANGLE | 同左，gpu-preferences 逐字一致 |

内置启动标志 53 项 feature + 3 项普通开关在 M155 源码树逐项存活（`check_features` 53/53），
并通过子进程命令行验证（A6）确认实际注入。

## 校验

下载后核对 SHA256：

```
certutil -hashfile mcloud_155.0.8059.40_win64_mini_installer.exe SHA256
```

预期值：`17b3151379dfc1091efe10a05825ce433c58895a27f6d925025dfbbd7517f3b7`
