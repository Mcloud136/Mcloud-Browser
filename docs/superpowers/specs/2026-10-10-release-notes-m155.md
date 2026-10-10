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
- **安装版才真正带上优化清单（r4）**：`mcloud_flags.txt` 改由 VersionDir 投递到 `Application/155.0.8059.40/`，加载器 v7 同时支持 exe 同目录（开发树）与版本子目录（安装版）两种位置。此前登记在 Application 根目录的条目会被打包但**不被安装**（setup.exe 对根目录只搬固定三件套），所以 r3 及更早的安装包在干净机器上等于零内置优化（缺陷 D105）。

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

预期值：`54fc59b5ccd3afc43c27f113206ededb8fc0db6c04825f88c53493afd1b228d1`
