# MCloud Browser M151 Release Notes

## 内核 Chromium M151 (151.0.7922.99)

---

## 本次升级与优化内容

### 内核升级

- 升级至 Chromium M151（151.0.7922.99），包含上游全部安全修复与新特性
- V8 引擎升级至 15.1（Sparkplug/Maglev/TurboFan 完整分层 JIT）
- PGO 配置文件同步更新（chrome-win64-7922 系列 + V8 builtins profiles 15.1.206.13）

### 性能优化（本版重点）

**编译层（保持）**：AVX2+FMA3 原生编译、-O3 全量优化、ThinLTO、PGO phase=2

**运行时（本次修正与增强）**：
- 修正 V8 JIT 阈值参数命名（旧版参数在 M151 失效）：Maglev 编译阈值 400→200、TurboFan 3000→1500，脚本更早进入优化编译
- 启用 Maglev OSR 升级（osr-from-maglev）与 Sparkplug 动态修补（sparkplug-plus）
- 内置启动标志增至 66 条，全部经源码存活性校验与子进程注入验证

**数据驱动的预载优化取舍**（实测验证）：
- bilibili 页面导航预载命中时提速 5.6%（1434ms vs 1519ms）
- 移除内存代价大而收益不稳定的 3 项预载 feature，真实站点 50 标签内存降低 203MB

### 基准数据（i9-14900HX，对比 M150 同机同方法）

| 指标 | M151 | M150 |
|------|------|------|
| 冷启动时间 | 73ms | 71ms（持平） |
| 内存（50 标签驻留 90s） | 2646MB | 2669MB（-0.9%） |
| 安装包体积 | 117.7MB | 112.3MB（仅观测） |

### 修复

- 内置启动标志加载器首次真实生效（此前从未加载）
- DoH 默认模式（M151 上游已内置 kAutomatic）

### 已知限制

- 仅发布 Windows x64 平台
- Widevine DRM 未包含（需单独获取 CDM）
- 要求 CPU 支持 AVX2+FMA3（2013 年 Haswell / Ryzen 之后）

---

完整记录见 docs/dev-logs/M151-upgrade-report.md 与 docs/CHANGELOG.md。
