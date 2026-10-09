# MCloud Browser 151.0.7922.99（r2 修复版）Release Notes

内核：Chromium M151 (151.0.7922.99) ｜ 平台：Windows x64（AVX2 + FMA3 基线）
发布日期：2026-10-09 ｜ 本包 SHA256：`054efb37c8018feda5ba06842e39269908e438f27ae873b0bb670bfc05ab389f`

这是一个**稳定性/安全修复版**：内核版本不变，修复的是我们自己的定制层。适合直接从
上一版（v151.0.7922.99）覆盖安装，用户数据与扩展不受影响。

---

## 本版重点

### 1. 启动标志加载器的运行时内存安全加固
MCloud 在进程启动早期读取 `mcloud_flags.txt` 并把优化标志注入命令行，而这些标志会被所有
子进程继承。上一版对畸形或超大的标志文件没有长度约束，会导致浏览器**自身**崩溃：

- 超大的 `--enable-features` 合并值会撑破 Windows 子进程命令行上限（32767 字符），GPU 进程
  无法创建 → 浏览器直接退出。现已改为**命令行字节预算**机制（总量 24KiB，普通开关子预算 12KiB），
  超预算条目跳过并降级，浏览器照常启动。
- 同型路径的第二条（单条超长值，例如体积异常的 `--js-flags`）也一并封住。
- 标志文件读取改为强制 1MiB 上限并逐行有界解析，解析代码去掉裸指针运算，编译告警清零。

现有优化标志不受影响：当前标志文件只占用预算的约 8%（1.9KB / 24KB），全部 60 项 feature
与 3 项普通开关照常生效。

### 2. 窗口缩小播放视频时整浏览器冻结的缓解配置固化
经实验确认有效后，4 项与软挂起相关的标志已在标志文件中固化为禁用
（`ThrottleUnimportantFrameRate`、`ReduceHardwareVideoDecoderBuffers`、
`SkiaGraphite`、`SkiaGraphitePrecompilation`），拖拽/缩小窗口播放视频时不再复现整浏览器无响应。

### 3. 核显视频开头绿屏修复随包携带
Intel 核显（Raptor Lake / UHD 770）的 D3D12 视频解码器首帧输出缺陷，通过运行时
`--disable-features=D3D12VideoDecoder` 回退 D3D11 解决（硬解能力不受影响）。本包的
`mcloud_flags.txt` 已确认打包在内（安装后无需再手工放置）。

### 4. .pak 资源工具（pak_src）内存安全修复
面向开发者的命令行 pak 打包/解包工具重写了解析与写回路径：头部与表范围校验、条目偏移单调性
校验、64 位尺寸累加并拒绝 >4GB 输出、所有错误路径补齐资源释放、有界字符串读取与路径拼接越界防护。

### 5. 构建与发布工程修正
- 破坏性升级入口（含 `gclient sync --force --reset --delete_unversioned_trees` 的旧脚本）改为拒绝执行，
  避免误删定制与工具链二进制。
- 含中文的 `.ps1` 批量补 UTF-8 BOM，修复 Windows PowerShell 5.1 解析失败。
- `copy_essentials.py` 增加白名单断言，防止旧内核基线副本被重新覆盖到新源码树。
- 源码验证脚本接入 CI（push 到 main / PR 自动运行）。

---

## 验证情况

- 连续五轮回归（静态门 / pak ASan 套件 / 变异模糊 450 例 / 结构化溢出探针 23 例 / 部署幂等 /
  内置标志生效 / feature 存活 / 加载器边界 11 例）全部通过，零新缺陷。
- 冷启动基准 K1 中位数 54ms（5 次样本），相对修复前无性能回归。
- 安装包内容做了载荷级核验（确认 `mcloud_flags.txt` 与其当前版本标记都在包内）。

## 校验方法

安装前后都可以核对包体完整性：

```powershell
certutil -hashfile mcloud_151.0.7922.99_win64_mini_installer.exe SHA256
# 期望：054efb37c8018feda5ba06842e39269908e438f27ae873b0bb670bfc05ab389f
```

安装后打开 `chrome://version`，命令行一栏应能看到内置优化标志已被注入；`chrome://gpu` 可确认
视频硬解走 D3D11 路径。

## 已知限制

- 仅发布 Windows x64（AVX2+FMA3 基线，较老 CPU 无法运行）。
- 若你自己编辑 `mcloud_flags.txt` 并塞入异常超长的条目，加载器会跳过内置合并并在日志降级，
  而不是崩溃；这是本版新增的保护，不是配置丢失。
