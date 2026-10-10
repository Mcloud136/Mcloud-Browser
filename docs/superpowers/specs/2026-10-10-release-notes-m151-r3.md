## MCloud Browser v151.0.7922.99-r3

Chromium M151（151.0.7922.99）| AVX2 + FMA3 | Windows x64

本版为 **发布链路完整性 + 优化清单真实性** 修复版，内核版本与 r2 相同，不改浏览器引擎代码。

### 修复

- **安装包一定带得上启动标志文件（D47）**：新增幂等注入步骤
  `win_scripts/apply_installer_payload.py`，负责把 `mcloud_flags.txt: %(ChromeDir)s\` 写入
  `chrome/installer/mini_installer/chrome.release`，并接入 `deploy_mcloud.py`（现为 7 步）。
  在此之前，这一行只存在于某一台构建机的未提交改动里——换一棵干净的源码树（例如内核升级）
  照样能编译打包成功，但安装包里不含标志文件，全部运行时优化静默失效。
- **优化清单去虚（D48）**：按上游 feature **声明位**逐项核对 M151/M155/M156 三个版本后，
  删除 6 条在上游根本不存在、因此一直被 Chromium 静默忽略的条目
  （`CanvasOopRasterization`、`DirectComposition`、`EarlyData`、`AVIF`、`SpeculationRules`、
  `ServiceWorkerNavigationPreload`）。这 6 条在 r2 上也无操作，**删除不改变任何现有行为**。
- `BestEffortTaskInhibitingPolicy` 上游真名为 `EnableBestEffortTaskInhibitingPolicy`（两版均默认禁用）。
  启用它会改变运行时行为，故本版仅以注释保留修正后的写法，待基准验证后再决定。
- `FlingSchedulingImprovements` 在 M151 上真实生效（本版保留原行为），但 M155 起上游已彻底移除，
  文件内已标注"升级期必须删除并重新评估滚动接替项"。

### 校验方式

下载后核对 SHA256（PowerShell 5.1 亦可 `Get-FileHash`）：

```
certutil -hashfile mcloud_151.0.7922.99_win64_mini_installer.exe SHA256
```

预期值：``393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049``

### 说明

- 本版 flags 条目 53 项 feature + 3 项普通开关；跨版本稳定性由
  `.bugreview/flag_stability.py` 断言（每条须在 151/155/156 三版全部声明存在，唯一例外为上面标注的升级期条目）。
- M155 升级所需的性能新特性候选清单与取舍依据见仓库文档 `docs/tasks/m155-perf-features.md`。
