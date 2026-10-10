#!/usr/bin/env python3
"""d47_probe.py - 验证 apply_installer_payload.py（D47 修复）而不触碰真实构建树。

四例 + 一条字节等价断言：
  A 上游 M155 的 chrome.release  → 首次注入成功，条目紧随 chrome.exe 行
  B 对 A 的结果再跑一次         → 幂等（already present，文件不变）
  C 当前 151 树里的该文件        → 判定为已存在（说明脚本产出 == 手工状态）
  D 去掉锚点的文件              → 明确报错、退出码 1、不写文件
  E 断言：上游 M151 干净文件 + 注入器 == 当前树文件（逐字节）
"""
import hashlib
import os
import shutil
import subprocess
import sys

REPO = r"d:\wxmuma\thorium"
TREE = r"D:\wxmuma\chromium-src\src"
INJ = os.path.join(REPO, "win_scripts", "apply_installer_payload.py")
REL = os.path.join("chrome", "installer", "mini_installer", "chrome.release")
# git 的 rev:path 只认正斜杠，Windows 的 os.path.join 会给出反斜杠（首轮探针即栽在此）
REL_GIT = "chrome/installer/mini_installer/chrome.release"
PROBE = os.path.join(REPO, ".bugreview", "d47_probe")
ENTRY = 'mcloud_flags.txt: %(ChromeDir)s\\\n'
ANCHOR = 'chrome.exe: %(ChromeDir)s\\\n'
PY = sys.executable

fails = []


def git_show(rev, path=REL_GIT):
    return subprocess.run(["git", "-C", TREE, "show", "%s:%s" % (rev, path)],
                          capture_output=True, text=True, errors="replace", timeout=900).stdout


def fake_tree(name, content):
    d = os.path.join(PROBE, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    full = os.path.join(d, REL)
    os.makedirs(os.path.dirname(full))
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return d, full


def run_inject(cr_dir):
    env = dict(os.environ, CR_DIR=cr_dir)
    p = subprocess.run([PY, INJ], capture_output=True, text=True, env=env,
                       errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def sha_lf(path):
    """与换行风格无关的正文指纹（工作树文件可能被 checkout 成 CRLF）。"""
    body = open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


shutil.rmtree(PROBE, ignore_errors=True)
os.makedirs(PROBE, exist_ok=True)
up151 = git_show("151.0.7922.99")
assert up151, "取不到 M151 上游的 chrome.release"

# --- A: 上游 M155 文件首次注入 -------------------------------------------
up155 = git_show("155.0.8059.40")
assert up155, "取不到 M155 的 chrome.release（tag 对象不在本地？）"
dA, fA = fake_tree("m155_fresh", up155)
rc, out = run_inject(dA)
if rc != 0 or ENTRY not in open(fA, encoding="utf-8").read():
    fails.append("A 首次注入失败 rc=%s out=%s" % (rc, out))
else:
    txt = open(fA, encoding="utf-8").read()
    ok_order = txt.index(ANCHOR) < txt.index(ENTRY) <= txt.index(ANCHOR) + len(ANCHOR) + len(ENTRY)
    if not ok_order:
        fails.append("A 条目位置不在 chrome.exe 行之后")
print("A 上游 M155 首次注入        : rc=%s %s" % (rc, out))

# --- B: 幂等 -------------------------------------------------------------
before = sha(fA)
rc, out = run_inject(dA)
if rc != 0 or "already present" not in out or sha(fA) != before:
    fails.append("B 幂等失败 rc=%s out=%s" % (rc, out))
print("B 重复运行幂等              : rc=%s %s" % (rc, out))

# --- C: 当前树状态等价 ---------------------------------------------------
cur = open(os.path.join(TREE, REL), encoding="utf-8", errors="replace").read()
if ENTRY not in cur:
    fails.append("C 预期失败：当前树竟不含该条目（D47 事实需重新核实）")
dC, fC = fake_tree("m151_current", cur)
rc, out = run_inject(dC)
if rc != 0 or "already present" not in out:
    fails.append("C 当前树等价判定失败 rc=%s out=%s" % (rc, out))
print("C 当前 151 树状态判定        : rc=%s %s" % (rc, out))

# --- D: 无锚点必须报错且不写（用干净上游文件构造，避免已含条目的当前树） ---
broken = up151.replace(ANCHOR, "")
if ANCHOR in broken or ENTRY in broken:
    fails.append("D 构造失败：未能去掉锚点")
dD, fD = fake_tree("no_anchor", broken)
before = sha(fD)
rc, out = run_inject(dD)
if rc != 1 or "anchor" not in out.lower() or sha(fD) != before:
    fails.append("D 无锚点未正确报错 rc=%s out=%s" % (rc, out))
print("D 缺锚点报错且不写文件       : rc=%s %s" % (rc, out))

# --- E: 干净上游 151 文件 + 注入器 == 当前树文件（逐字节） ----------------
up151 = git_show("151.0.7922.99")
dE, fE = fake_tree("m151_clean_then_inject", up151)
rc, out = run_inject(dE)
if rc != 0 or sha_lf(fE) != sha_lf(os.path.join(TREE, REL)):
    fails.append("E 注入器无法复现当前树的字节级状态 rc=%s" % rc)
print("E 干净151+注入器 == 当前树   : rc=%s sha_lf=%s" %
      (rc, sha_lf(fE)[:16] if os.path.exists(fE) else "NA"))

print("\nD47 探针结果: %s" % ("全部通过" if not fails else "存在失败"))
for f in fails:
    print("  FAIL:", f)
sys.exit(1 if fails else 0)
