#!/usr/bin/env python3
"""flag_stability.py - 证明 r3 的 flags 清理不改变当前版本行为，且升级后语义保持稳定。

断言：
  A r3 活动条目集合 ⊆ r2（HEAD 版）活动条目集合   → 没有新增任何开启项
  B r2 中被移除的每一条，在 M151 上都非 OK        → 移除的都是"本就无操作"的条目
  C r3 每条 feature 在 151/155/156 三版均为 OK    → 升级后不会静默丢效果
    （唯一例外：文件内带 [升级期处置] 标记的条目，要求它在 151 OK 且 155/156 非 OK）
  D 普通开关（非 feature）在三版均以字符串常量存在
退出码 0 = 全部通过。
"""
import json
import re
import subprocess
import sys

REPO = r"d:\wxmuma\thorium"
TREE = r"D:\wxmuma\chromium-src\src"
PY = sys.executable
# 版本集合可被命令行覆盖：flag_stability.py 155.0.8059.40 156.0.8078.12 157.x
# 语义 = 基线版 + 两个目标版；升级后必须用新的基线复跑本断言。
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
REV151, REV155, REV156 = (_ARGS + ["151.0.7922.99", "155.0.8059.40", "156.0.8078.12"])[:3]
UPGRADE_MARKER = "FlingSchedulingImprovements"


def _line_action(text, name):
    """在文件里查该 feature 是 enable 还是 disable 方向。"""
    for raw in text.splitlines():
        ln = raw.strip()
        if ln.startswith("#") or not ln:
            continue
        m = re.match(r"^--(enable|disable)-features=", ln)
        if m and re.search(r"=%s($|[,::])" % re.escape(name), ln):
            return m.group(1)
    return "enable"


def entries(text):
    """返回 (feature 条目集合, 普通开关集合)，注释行不计入。"""
    feats, switches = set(), set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^--(enable|disable)-features=(.+)$", line)
        if m:
            for item in m.group(2).split(","):
                name = item.strip().split(":")[0].strip()
                if name:
                    feats.add(name)
            continue
        m = re.match(r"^--([a-z0-9][a-z0-9-]*)", line)
        if m and m.group(1) != "js-flags":
            switches.add(m.group(1))
    return feats, switches


def run_check(rev, json_out):
    subprocess.run([PY, REPO + r"\.bugreview\survival_check.py", rev,
                    "--json", json_out], capture_output=True, text=True,
                   errors="replace")
    d = json.load(open(json_out, encoding="utf-8"))
    return {f["name"]: f for f in d["features"]}, d


def git_show_head(path):
    return subprocess.run(["git", "-C", REPO, "show", "HEAD:%s" % path],
                          capture_output=True, text=True, errors="replace", timeout=600).stdout


fails = []
cur = open(REPO + r"\mcloud_flags.txt", encoding="utf-8").read()
old = git_show_head("mcloud_flags.txt")
if not old:
    fails.append("A/B 前置失败：取不到 HEAD 版 mcloud_flags.txt")

cur_f, cur_s = entries(cur)
old_f, old_s = entries(old)

# A 方向敏感的"不得新增"：开启项一律禁止；禁用项只允许带文档说明的例外
added = sorted(cur_f - old_f)
# 例外表：条目 -> 理由（必须是「恢复既有定案」而非「引入新行为」）
DISABLE_EXCEPTIONS = {
    "SkiaGraphite": "151/155/156 上游默认启用，而窗口拖拽冻结缓解定案要求它禁用；"
                    "显式 --disable-features 是纠正此前「注释掉启用行」并不等于禁用的误解"
                    "（155 升级期发现，需构建后同方法 A/B 复核）",
}
added_enable = [n for n in added if (old_f and True) and n not in DISABLE_EXCEPTIONS
                and _line_action(cur, n) == "enable"]
added_disable_ok = [n for n in added if n in DISABLE_EXCEPTIONS and _line_action(cur, n) == "disable"]
added_disable_bad = [n for n in added if n not in DISABLE_EXCEPTIONS and _line_action(cur, n) == "disable"]
if added_enable:
    fails.append("A 新增了未经验证的开启项: %s" % added_enable)
if added_disable_bad:
    fails.append("A 新增了无例外登记的禁用项: %s" % added_disable_bad)
print("A 活动 feature 条目 基线=%d 当前=%d；新增开启项=%s；已登记例外的禁用项=%s"
      % (len(old_f), len(cur_f), added_enable or "无", added_disable_ok or "无"))

# B 移除项必须都是 151 上的非 OK 条目
removed = sorted(old_f - cur_f)
s151, d151 = run_check(REV151, REPO + r"\.bugreview\stab_151.json")
bad_removals = [n for n in removed if s151.get(n, {}).get("state") == "OK"]
if bad_removals:
    fails.append("B 移除了在 M151 上真实生效的条目（会改变当前行为）: %s" % bad_removals)
print("B 移除 %d 条：%s" % (len(removed), ", ".join(removed) or "无"))
print("   其中在 M151 上曾生效的（必须为 0）: %d" % len(bad_removals))

# C 三版存活
s155, d155 = run_check(REV155, REPO + r"\.bugreview\stab_155.json")
s156, d156 = run_check(REV156, REPO + r"\.bugreview\stab_156.json")
for name in sorted(cur_f):
    st = {151: s151.get(name, {}).get("state"),
          155: s155.get(name, {}).get("state"),
          156: s156.get(name, {}).get("state")}
    if name == UPGRADE_MARKER:
        if st[151] != "OK" or st[155] == "OK":
            fails.append("C %s 升级期标记不成立：151=%s 155=%s（应 151 OK、155 非 OK）"
                         % (name, st[151], st[155]))
        continue
    if not all(v == "OK" for v in st.values()):
        fails.append("C %s 并非三版全存活：%s" % (name, st))
n_ok_all = sum(1 for n in cur_f
               if all(x.get(n, {}).get("state") == "OK" for x in (s151, s155, s156)))
print("C r3 条目中三版全存活 %d/%d（另有 1 条为升级期标记项）" % (n_ok_all, len(cur_f)))

# D 普通开关在三版存在
for rev, d in ((151, d151), (155, d155), (156, d156)):
    for sw, present in d["plain_switches"].items():
        if not present:
            fails.append("D 普通开关 --%s 在 M%s 未找到字符串常量" % (sw, rev))
print("D 普通开关 %s 在 151/155/156 均存在" % sorted(cur_s))

# E 带参条目：Chromium 的 feature params 语法是 `Feature:param/value/param/value`
# （值是**必需**的）。语法不合法时不会报错，只把参数关联丢掉、全部退回代码内默认值
# （缺陷档案 D51：我们曾写 `InitialWebUI:without_spellcheck/without_translate/…`，
# 三个裸名没有值，恰好因上游默认就是 true 才没暴露）。
# 旧 E 只把每个 '/' 段当参数名去搜，既漏判语法、又会因树上大量 "true" 误判通过，故重写。
def declared_params(rev, feat):
    """返回该 rev 中绑定到 features::k<Feat> 的 BASE_FEATURE_PARAM 参数名集合。"""
    out = subprocess.run(
        ["git", "-C", TREE, "grep", "-I", "-h", "-A6", "-E",
         r"BASE_FEATURE(_PARAM)?\(", rev, "--", "*.cc"],
        capture_output=True, text=True, errors="replace", timeout=600).stdout
    names = set()
    # git grep -A6 的续块以 "--" 行分隔，按此重组
    blocks, cur_blk = [], []
    for ln in out.splitlines():
        if ln.startswith("--"):
            if cur_blk:
                blocks.append("\n".join(cur_blk))
            cur_blk = []
            continue
        cur_blk.append(ln)
    if cur_blk:
        blocks.append("\n".join(cur_blk))
    for blk in blocks:
        if ("&features::k%s," % feat) in blk or ("&k%s," % feat) in blk:
            for mm in re.finditer(r'"([a-z0-9_]+)"', blk):
                names.add(mm.group(1))
    return names


param_entries = []
for raw in cur.splitlines():
    line = raw.strip()
    m = re.match(r"^--(?:enable|disable)-features=([A-Za-z0-9_]+):(.+)$", line)
    if m and not line.startswith("#"):
        toks = [t.strip() for t in m.group(2).split("/") if t.strip()]
        param_entries.append((m.group(1), toks))

for feat, toks in param_entries:
    if len(toks) % 2:
        fails.append("E %s 的 params 段有 %d 个 token（奇数）——语法必须是 param/value 成对"
                     % (feat, len(toks)))
        continue
    for rev in (REV151, REV155, REV156):
        allowed = declared_params(rev, feat)
        for name in toks[0::2]:
            if name not in allowed:
                fails.append("E %s 的参数名 %s 在 %s 未由 BASE_FEATURE_PARAM 绑定到该 feature"
                             % (feat, name, rev))
    print("E %s params=%s（成对校验通过，参数名对三版声明集核对）"
          % (feat, ",".join(toks)))
if not param_entries:
    print("E 无带参条目")

# F 行内注释防护（D59）：加载器只把"整行以 # 开头"当注释；活动行末尾若写了 ` # 备注`，
# 注释文本会被并进 feature 名而被 Chromium 忽略 —— 整条静默失效（与 D48 同族）。
# 运行期解析刻意与 Chromium 保持一致（不多做注释语法），所以在这里静态拦住。
inline_comment = [l.strip() for l in cur.splitlines()
                  if l.strip().startswith("--") and "#" in l]
if inline_comment:
    fails.append("F 活动行含行内 # 注释（该条会被整条忽略）: %s" % inline_comment)
print("F 行内注释检查：%s" % ("未发现" if not inline_comment else inline_comment))
print("\n稳定性结论: %s" % ("PASS — 清理不改变当前行为，且除标记项外全部条目升级后仍生效"
                          if not fails else "FAIL"))
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if fails else 0)
