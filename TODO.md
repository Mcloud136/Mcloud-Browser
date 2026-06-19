# TODO — MCloud Browser

## 已完成 ✅

- [x] 升级到 Chromium M150 (150.0.7871.37)
- [x] 实现 51 项运行时性能优化
- [x] 实现编译时优化栈（AVX2 + O3 + Polly + BOLT + ThinLTO + PGO）
- [x] 修复 HTTP 断流问题（DNS-over-HTTPS 模式）
- [x] 修复后台应用默认行为（默认关闭）
- [x] 修复 Google API 密钥配置
- [x] 简化 CI/CD 工作流（只做打包上传）
- [x] 代码审查修复（14 个问题）
- [x] 发布 M150 Release (v150.0.7871.37)

## 待完成 📋

### CI/CD
- [ ] 上传预编译源码包到 GitHub Release（可选）
- [ ] 配置自建 Runner（需要服务器）

### 功能
- [ ] Widevine DRM 支持（需下载 CDM）
- [ ] 核显视频绿屏问题修复（需调试驱动兼容性）
- [ ] 品牌重命名（用户决定暂不处理）

### 优化
- [ ] 测试 D3D12 视频解码在新驱动上的支持
- [ ] 优化 V8 JIT 阈值参数
- [ ] 测试更多编译时优化选项

## 技术债务

- [ ] 更新 BUILDING_WIN.md 文档（VS2026 指南）
- [ ] 更新 FAQ.md（添加常见问题）
- [ ] 清理 TODO.md 中的过时内容

## 参考链接

- [Thorium 项目](https://github.com/Alex313031/thorium)
- [Chromium 官方文档](https://www.chromium.org/)
- [Chromium 性能优化指南](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/speed/)
