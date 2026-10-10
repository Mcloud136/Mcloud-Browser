#!/usr/bin/env python3
"""d49_experiment.py - 运行时判定 V8 --js-flags 的连字符/下划线是否等价（缺陷 D49）。

源码证据（已确认）：v8/src/flags/flags-impl.h:19
    static constexpr char NormalizeChar(char ch) { return ch == '_' ? '-' : ch; }
标志名比较一律经该归一化（flags.cc 的 EqualNameWithSuffix / 查找路径），因此两种写法应等价。
本脚本给出运行时对照，避免只靠读码下结论：

  A --js-flags=--trace-opt-verbose      （连字符）
  B --js-flags=--trace_opt_verbose      （下划线）
  C --js-flags=--trace-opt-verbos       （故意拼错的对照）

用 --enable-logging=stderr 捕获 V8 优化追踪输出并计数。若 A≈B 且 C 明显更少/为 0，
则"连字符静默失效"的旧文档口径不成立，应更正为"两种写法等价"。
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time

CHROME = r"D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe"
CASES = [("A 连字符", "--trace-opt-verbose"), ("B 下划线", "--trace_opt_verbose"),
         ("C 拼错对照", "--trace-opt-verbos")]
RUN_S = 14
TRACE = re.compile(rb"(optimizing|compiling method|%B? optimize)", re.I)

if not os.path.isfile(CHROME):
    print("chrome.exe 不存在：%s（需在构建完成后运行）" % CHROME)
    sys.exit(2)

results = {}
for label, jsflag in CASES:
    profile = tempfile.mkdtemp(prefix="d49_")
    cmd = [CHROME, "--user-data-dir=" + profile, "--enable-logging=stderr", "--v=0",
           "--no-first-run", "--no-default-browser-check", "--disable-gpu",
           "--disable-extensions", "--js-flags=" + jsflag, "about:blank"]
    env = dict(os.environ)
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, env=env)
    except OSError as e:
        print("启动失败:", e)
        shutil.rmtree(profile, ignore_errors=True)
        sys.exit(2)
    # 读取必须放线程里做：阻塞式 os.read 会让 RUN_S 超时形同虚设（首版就挂在这里）
    chunks = []
    def _reader():
        try:
            while True:
                data = os.read(p.stderr.fileno(), 1 << 16)
                if not data:
                    break
                chunks.append(data)
        except OSError:
            pass
    th = threading.Thread(target=_reader, daemon=True)
    th.start()
    time.sleep(RUN_S)
    try:
        p.terminate()
    except OSError:
        pass
    th.join(timeout=5)
    blob = b"".join(chunks)
    n = len(TRACE.findall(blob))
    hits = [ln.strip()[:80].decode("utf-8", "replace")
            for ln in blob.splitlines() if TRACE.search(ln)][:3]
    try:
        p.kill()
        p.wait(timeout=15)
    except Exception:
        pass
    shutil.rmtree(profile, ignore_errors=True)
    results[label] = {"trace_lines": n, "stderr_bytes": len(blob), "sample": hits}
    print("%-12s js-flags=%-22s V8 追踪命中=%d  stderr=%d B"
          % (label, jsflag, n, len(blob)))
    for h in hits:
        print("      ", h)

a, b, c = (results[k]["trace_lines"] for k, _ in CASES)
print("\n判定：")
if a == 0 and b == 0:
    print("  两种写法都无输出 —— 追踪未生效或日志通道不可用，本轮不作结论（需换 --log-commands 类可观测标志复测）")
elif abs(a - b) <= max(2, int(0.15 * max(a, b))) and c < min(a, b):
    print("  A≈B 且拼错对照 C 明显更低 → **连字符与下划线等价**，旧口径（连字符静默失效）不成立，D49 应按等价更正文档")
else:
    print("  A/B 差异显著（A=%d B=%d C=%d）→ 旧口径可能成立，保留 mcloud_flags.txt 现有下划线写法并复核"
          % (a, b, c))
