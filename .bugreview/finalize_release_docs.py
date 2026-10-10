#!/usr/bin/env python3
"""finalize_release_docs.py - 把 r3 已发布的事实写回 progress / CHANGELOG / 缺陷档案。"""
import io

REPO = r"d:\wxmuma\thorium"

# ---------- 1) progress.md ----------
p = REPO + r"\docs\progress.md"
s = io.open(p, encoding="utf-8").read()
old = "  r3 的推送/打 tag/资产上传尚未执行（需 L3 安全审查门禁 + 用户授权）。"
new = ("  r3 已对外发布：L3 深度安全审查 findings=0；`main` 推到 `1cd61ff`，标注 tag\n"
       "  `v151.0.7922.99-r3` 指向同一提交；CI 建出的 release 正文为 r3（选择器命中 `-r3` 文件名）；\n"
       "  安装包经 API 作为 Release 资产上传（HTTP 201），GitHub 计算摘要与本地完全一致\n"
       "  （`393456968d948137b362b1a720074ef5e69804856b886ecf7ead937a3abdf049`，123,466,752 B），\n"
       "  公开下载校验 302→206、首字节 4D 5A、总长一致。")
if old in s:
    io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new, 1))
    print("progress.md 已更新发布事实")
else:
    print("progress.md 锚点未命中")

# ---------- 2) CHANGELOG.md ----------
p = REPO + r"\docs\CHANGELOG.md"
t = io.open(p, encoding="utf-8").read()
i = t.find("## M151-r3")
j = t.find("## M151-r2")
seg = t[i:j]
add = ("### 📦 发布状态\n\n"
       "- 发布页：https://github.com/Mcloud136/Mcloud-Browser/releases/tag/v151.0.7922.99-r3\n"
       "- L3 深度安全审查：findings=0；`main` 与 tag `v151.0.7922.99-r3` 均已推送\n"
       "- 安装包已作为 Release 资产上传（HTTP 201），GitHub 计算摘要与本地一致；\n"
       "  公开下载经 302→206 校验，首字节 4D 5A，总长 123,466,752 B\n\n"
       "### 📦 构建产物")
if "### 📦 发布状态" not in seg:
    seg2 = seg.replace("### 📦 发行包", add, 1)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t[:i] + seg2 + t[j:])
    print("CHANGELOG.md 已加发布状态段")
else:
    print("CHANGELOG.md 已含发布状态段")

# ---------- 3) 缺陷档案：D47 / D48 状态 ----------
p = REPO + r"\docs\tasks\bug-review-pak-src-defects.md"
d = io.open(p, encoding="utf-8").read()

d47_old = ("- 待决（owner：项目方）：新增第 7 个幂等注入脚本（锚点 `chrome.exe: %(ChromeDir)s\\` 后插入），\n"
           "  挂入 `deploy_mcloud.py`，并在 `win_scripts/verify_sources.py` 增加存在性检查；文档补步骤。")
d47_new = ("- **已修复并发布（2026-10-10，M151-r3）**：新增第 7 个幂等注入脚本 "
           "`win_scripts/apply_installer_payload.py`（锚点 `chrome.exe: %(ChromeDir)s\\` 后插入），\n"
           "  挂入 `deploy_mcloud.py` STEPS 与 `win_scripts/verify_sources.py` 关键脚本清单；\n"
           "  AGENTS.md 第 7 步与 README 口径同步更正。探针 `.bugreview/d47_probe.py` 五例全过，\n"
           "  含「干净上游 151 文件 + 注入器 == 当前树文件（逐字节）」与「对 M155 的该文件首次注入可用」。")

d48_old = ("- 待决（owner：项目方）：改名 1 条、删除 6+1 条（删前按实测收益逐项判断），\n"
           "  把 `benchmark/tools/check_features.py` 的存活性校验纳入 `verify_sources.py`/CI。")
d48_new = ("- **部分已修复并发布（2026-10-10，M151-r3）**：删除三版均不存在的 6 条；改名条目转注释保留"
           "（启用会改行为，待基准）；`FlingSchedulingImprovements` 保留并标「升级期删除」（M151 上真实生效）。\n"
           "  断言脚本 `.bugreview/flag_stability.py`（A-E）PASS；`check_features.py` 双树验证 "
           "M151 53/53、M155 52/53。**剩余待办**：把存活性校验接入 CI。")

todo47 = "- [ ] D47：补 `apply_installer_payload.py`（chrome.release 单行幂等注入）并挂入 deploy_mcloud.py + verify_sources.py"
todo48 = "- [ ] D48：清理 7+1 条失效 feature，改名 1 条；把 check_features.py 存活性校验接入 CI"
pairs = [
    (d47_old, d47_new),
    (d48_old, d48_new),
    (todo47, todo47.replace("- [ ] ", "- [x] ") + "（r3 已发布）"),
    (todo48, "- [x] D48：清理失效条目（删 6 / 注释改名 1 / 标记升级期 1）已随 r3 发布；剩余待办是把 check_features.py 存活性校验接入 CI"),
]
hit = 0
for a, b in pairs:
    if a in d:
        d = d.replace(a, b, 1)
        hit += 1
    else:
        print("  !! 未命中锚点:", a[:60])
io.open(p, "w", encoding="utf-8", newline="\n").write(d)
print("缺陷档案更新命中 %d/%d" % (hit, len(pairs)))
