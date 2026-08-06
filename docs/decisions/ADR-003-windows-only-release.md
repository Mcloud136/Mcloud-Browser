# ADR-003：仅发布 Windows 平台

- **状态**：已采纳
- **日期**：2026-08-06
- **决策人**：项目方

## 背景

项目历史继承自 Thorium，仓库中保留 Linux（deb/rpm/AppImage/Flatpak/portable）、macOS（dmg）、Android（APK）、ARM/树莓派等多平台构建脚本与配置。多平台维护成本高（每次内核升级需为各平台验证兼容性、各自打包发布），与项目聚焦高性能 Windows 浏览器的定位不符。

## 决策

1. **仅发布 Windows x64 平台**（mini_installer），其他平台不再发布；
2. 其他平台的构建脚本与配置（`build.sh`/`build_mac.sh`/`build_android.sh`、`infra/`、`arm/` 等）保留在仓库供参考，但：
   - 内核升级流程（规范第 9/11 章）不再为其做兼容性验证；
   - 不承诺其可构建性；
3. 发布产物命名与校验和仅面向 Windows（如 `mcloud_{版本}_win64_mini_installer.exe` + `.sha256`）；
4. 如未来恢复任一平台发布，须新开 ADR 并重新纳入技术规范验证范围。

## 后果与约束

- M150→M151 及后续升级：profdata 仅下载 win64；基准测试仅在 Windows 执行；
- 规范 6.2 打包矩阵已按本决策更新（其他平台标记为"遗留（不发布）"）；
- 已废弃的 SSE2~SSE4.2 梯度清理（A7）与本决策一致：指令集与平台均收敛到 AVX2+FMA3 / Windows x64。
