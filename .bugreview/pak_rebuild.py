#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用修好的源码重建 pak 二进制，并在**真实 Chromium .pak** 上验证后才落盘。

为什么要这一步（第7周期 D196）：构建链里唯一复制 pak 的地方是遗留 setup.sh，
而它复制的是 `pak_src/binaries/` 里的**预编译旧版**（连仓库源码已有的 .gz 魔数都不认）。
所以"源码已加固"从来不等于"二进制已加固"——本脚本把这句话变成可核对的事实。

判据（每条都可能红，实测输出会逐条打印）：
  1. MSVC x64 与 x86 均以 /W4 /utf-8 零警告编译成功；
  2. 对 out/mcloud 里每个真实 .pak：新二进制解包→再打包，**与原文件逐字节相同**；
  3. 同一 index 连打两次**字节一致**（D190），且 v5 头部 padding 全为 0；
  4. 与仓库多文件版 `pak_src/*.c` 编出的参考实现对同一 index 的产物**逐字节相同**
     （证明"单文件重写 == 参考实现"，而不是只跟自己一致）；
  5. x86 与 x64 **编译结果逐字节相同**（32 位路径没有隐藏的尺寸假设）；
  5b. 同一命令连编两次产物**逐字节相同**（`/Brepro`；没有它 cl 每次的 PE 时间戳都不同，
      BUILDINFO 里的哈希就无法核对——同 D130 对 csc `/deterministic+` 的要求）；
  6. 任何一条不成立 ⇒ 不落盘、非 0 退出；取不到真实 .pak ⇒ rc=2（不用合成样本冒充结论）。

写的是发布物，所以只在全部判据通过后才覆盖 binaries/pak-win/ 下的两个 pak_msvc*.exe。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

THOR = Path(__file__).resolve().parent.parent
SRC_SINGLE = THOR / "pak_src_fixed" / "pak.c"
SRC_MULTI = THOR / "pak_src"
BIN_DIR = THOR / "pak_src" / "binaries" / "pak-win"
MANIFEST = THOR / "pak_src" / "binaries" / "BUILDINFO.json"
SCRATCH = THOR / ".cycle7" / "pakbuild"

VC = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools"
          r"\MSVC\14.51.36231")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDKVER = "10.0.26100.0"
# /MT：静态链接 CRT。默认 /MD 会让产物依赖 vcruntime140.dll，而这个二进制是要被
# setup.sh 复制进 out/mcloud 独立使用的（D196），不能假设目标机器装了 VC 运行库。
CL_BASE = ["/nologo", "/W4", "/O2", "/MT", "/Brepro", "/utf-8",
           "/D_CRT_SECURE_NO_WARNINGS"]
MULTI_FILES = ["main.c", "pak_header.c", "pak_file.c", "pak_file_io.c",
               "pak_pack.c", "pak_get_file_type.c"]


def env_for(arch):
    e = dict(os.environ)
    e["INCLUDE"] = ";".join([str(VC / "include")] +
                            [str(SDK / "Include" / SDKVER / s)
                             for s in ("ucrt", "um", "shared")])
    e["LIB"] = ";".join([str(VC / "lib" / arch)] +
                        [str(SDK / "Lib" / SDKVER / s / arch) for s in ("ucrt", "um")])
    e["PATH"] = str(VC / "bin" / "Hostx64" / arch) + os.pathsep + e["PATH"]
    # 清掉可能干扰 cl 的批处理遗留变量
    for k in ("CL", "TMP", "TEMP"):
        e.pop(k, None)
    return e


def cl(arch):
    return VC / "bin" / "Hostx64" / arch / "cl.exe"


def sh(cmd, cwd=None, arch="x64"):
    p = subprocess.run(cmd, cwd=cwd, env=env_for(arch),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("gbk", "replace")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_single(out_exe, arch, log):
    out_exe = Path(out_exe)
    objdir = SCRATCH / ("obj_" + arch + "_" + out_exe.stem)
    objdir.mkdir(parents=True, exist_ok=True)
    if out_exe.exists():
        out_exe.unlink()
    rc, o = sh([str(cl(arch))] + CL_BASE + ["/Fo" + str(objdir) + os.sep,
                                       "/Fe" + str(out_exe), str(SRC_SINGLE)],
               arch=arch)
    shutil.rmtree(objdir, ignore_errors=True)
    warns = [ln.strip() for ln in o.splitlines() if "warning" in ln]
    log.append({"step": "build pak.c %s" % arch, "rc": rc, "warnings": warns,
                "artifact": str(out_exe) if out_exe.exists() else None})
    if rc != 0 or not out_exe.exists():
        print(o)
        return None
    if warns:
        for w in warns:
            print("   警告:", w)
    return out_exe


def build_reference(out_exe, log):
    objdir = SCRATCH / "obj_ref"
    objdir.mkdir(parents=True, exist_ok=True)
    if out_exe.exists():
        out_exe.unlink()
    srcs = [str(SRC_MULTI / n) for n in MULTI_FILES]
    # 参考实现同样要 /utf-8（D192：pak_src/*.c 也带中文注释）与 /Brepro
    # （否则清单里这个哈希每轮都变，等于没有可核对依据）
    rc, o = sh([str(cl("x64")), "/nologo", "/W4", "/utf-8", "/Brepro",
                "/D_CRT_SECURE_NO_WARNINGS",
                "/I" + str(SRC_MULTI), "/Fo" + str(objdir) + os.sep,
                "/Fe" + str(out_exe)] + srcs, arch="x64")
    log.append({"step": "build pak_src/*.c (参考实现)", "rc": rc})
    if rc != 0 or not out_exe.exists():
        print(o)
        return None
    return out_exe


def listing(d):
    out = {}
    for root, _, fs in os.walk(str(d)):
        for fn in fs:
            p = Path(root) / fn
            out[str(p.relative_to(d)).replace("\\", "/")] = (p.stat().st_size, sha256(p))
    return out


def run_pak(exe, args, cwd):
    p = subprocess.run([str(exe)] + list(args), cwd=str(cwd),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("gbk", "replace")


def main():
    if not cl("x64").exists() or not cl("x86").exists():
        print("ENV: 找不到 MSVC x64/x86 编译器（%s）" % VC)
        return 2
    SCRATCH.mkdir(parents=True, exist_ok=True)
    fails = []
    log = []
    stage = SCRATCH / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)

    print("== [1] 从 pak_src_fixed/pak.c 编译 x64 / x86（/W4 /utf-8，必须零警告）==")
    x64 = build_single(stage / "pak_msvc64.exe", "x64", log)
    x86 = build_single(stage / "pak_msvc32.exe", "x86", log)
    if not x64 or not x86:
        print("FAIL: 编译失败，不落盘")
        return 1
    for nm, p in (("x64", x64), ("x86", x86)):
        # /MT 生效性检查：这个二进制会被 setup.sh 复制进 out/mcloud 独立使用，
        # 依赖 vcruntime140.dll / api-ms-win-crt* 就等于假设目标机器装了 VC 运行库。
        blob = p.read_bytes()
        dyn = [t for t in (b"VCRUNTIME140", b"api-ms-win-crt") if t.lower() in blob.lower()]
        status = "[OK]  " if not dyn else "[FAIL]"
        if dyn:
            fails.append("%s 依赖动态 CRT（%s）——/MT 没生效" % (nm, dyn))
        print("   %s  %s %s  %d B  sha256=%s  动态CRT依赖=%s"
              % (status, nm, p.name, p.stat().st_size, sha256(p)[:16],
                 dyn or "无"))

    print("== [1b] 复现性：同一命令连编两次必须逐字节相同（/Brepro）==")
    for nm, arch in (("x64", "x64"), ("x86", "x86")):
        again = build_single(stage / ("repro_%s.exe" % arch), arch, log)
        if again is None:
            fails.append("复现性编译失败 (%s)" % nm)
            continue
        first = stage / ("pak_msvc64.exe" if arch == "x64" else "pak_msvc32.exe")
        same = sha256(first) == sha256(again)
        print("   %s %s 两次编译 sha256 %s" % ("[OK]  " if same else "[FAIL]", nm,
                                               "相同" if same else "不同"))
        if not same:
            fails.append("%s 产物不可复现：/Brepro 未生效，BUILDINFO 里的哈希没有意义" % nm)

    print("== [2] 参考实现（仓库多文件版 pak_src/*.c）==")
    ref = build_reference(SCRATCH / "pak_ref.exe", log)
    if not ref:
        print("FAIL: 参考实现编不出来，无法做等价对拍")
        return 1

    out_dir = Path(os.environ.get("MCHROME_OUT") or
                   r"D:\wxmuma\chromium-src-155\src\out\mcloud")
    paks = sorted(out_dir.glob("*.pak"))
    if not paks:
        print("FAIL: 在 %s 下找不到真实 .pak（设 MCHROME_OUT 指向 out/mcloud）" % out_dir)
        return 2
    # 只认 v5：版本字段是头 4 字节小端。语料版本不对时，"逐字节相同"这条判据
    # 测的就不是我们要保证的那个格式，必须当场说清楚而不是默默通过。
    vers = {}
    for p in paks:
        with open(p, "rb") as f:
            head = f.read(8)
        vers[p.name] = (int.from_bytes(head[:4], "little"), head[4])
    bad = {k: v for k, v in vers.items() if v[0] != 5}
    print("   真实语料 %d 个（version, encoding）：%s"
          % (len(paks), ", ".join("%s=%s" % (k, v) for k, v in sorted(vers.items()))))
    if bad:
        print("FAIL: 语料里有非 v5 的 pak：%s —— 判据覆盖面不足，请换语料" % sorted(bad))
        return 2
    del bad

    print("== [3] 真实 .pak 上的往返 / 确定性 / 与参考实现等价 ==")
    work = SCRATCH / "corpus"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for pak in paks:
        tag = pak.stem
        # 工具的 mkdir 不递归（原 B4），父目录必须由调用方先建好——
        # 否则解包会静默写不出任何文件，判据就变成"在空数据上成立"。
        for sub in ("un_new", "un_ref"):
            d = work / sub / tag
            if d.is_dir():
                shutil.rmtree(d)
            d.mkdir(parents=True)
        rc_u, ou = run_pak(x64, ["-u", str(pak), str(work / "un_new" / tag)], work)
        rc_r, orr = run_pak(ref, ["-u", str(pak), str(work / "un_ref" / tag)], work)
        n_new = len(list((work / "un_new" / tag).rglob("*")))
        if rc_u or rc_r or n_new < 2:
            fails.append("%s: 解包 rc=%d/%d，落地 %d 个文件（期望 >=2）；输出=%s"
                         % (tag, rc_u, rc_r, n_new, ou.strip()[:160]))
            continue
        ini_new = work / "un_new" / tag / "pak_index.ini"
        # 用**同一份** index 分别喂新实现与参考实现，产物必须逐字节相同
        outs = {}
        for name, exe in (("new", x64), ("ref", ref), ("x86", x86)):
            o = work / ("%s_%s.pak" % (tag, name))
            if o.exists():
                o.unlink()
            rc_p, _ = run_pak(exe, ["-p", str(ini_new), str(o)], work)
            outs[name] = o if (rc_p == 0 and o.exists()) else None
        o2 = work / ("%s_new2.pak" % tag)
        run_pak(x64, ["-p", str(ini_new), str(o2)], work)
        orig = pak.read_bytes()
        rows = []
        if outs["new"] is None:
            fails.append("%s: 新实现打包失败" % tag)
            continue
        nb = outs["new"].read_bytes()
        det = o2.exists() and o2.read_bytes() == nb
        same_ref = outs["ref"] is not None and outs["ref"].read_bytes() == nb
        same_x86 = outs["x86"] is not None and outs["x86"].read_bytes() == nb
        same_orig = nb == orig
        pad_ok = nb[:4] != b"\x05\x00\x00\x00" or nb[5:8] == b"\x00\x00\x00"
        rows = [("两次一致(D190)", det), ("头部padding为0", pad_ok),
                ("与参考实现字节相同", same_ref), ("x86==x64", same_x86),
                ("与原文件字节相同", same_orig)]
        bad = [k for k, v in rows if not v]
        print("   %s %-32s %d B  %s" % ("[OK]  " if not bad else "[FAIL]", tag, len(nb),
                                        " ".join("%s=%s" % r for r in rows)))
        if bad:
            fails.append("%s: %s" % (tag, "; ".join(bad)))
        if (work / "un_ref" / tag).is_dir():
            lo, ln_ = listing(work / "un_ref" / tag), listing(work / "un_new" / tag)
            if set(lo) != set(ln_):
                miss_new = sorted(set(lo) - set(ln_))[:3]
                print("      注: 解包文件命名与参考实现不同（新: %d 个额外/缺失，例 %s）"
                      % (len(set(lo) ^ set(ln_)), miss_new))

    print("== [3b] 与当前在库的旧二进制对照（说明这次重建改变了什么）==")
    stale = BIN_DIR / "pak_mingw64.exe"
    if stale.exists():
        for pak in paks:
            tag = pak.stem
            d = work / "un_stale" / tag
            if d.is_dir():
                shutil.rmtree(d)
            d.mkdir(parents=True)
            rc_s, _ = run_pak(stale, ["-u", str(pak), str(d)], work)
            o = work / ("%s_stale.pak" % tag)
            if o.exists():
                o.unlink()
            rc_sp, _ = run_pak(stale, ["-p", str(d / "pak_index.ini"), str(o)], work)
            if rc_s or rc_sp or not o.exists():
                print("   %s 旧二进制 rc=%d/%d（无法完成往返）" % (tag, rc_s, rc_sp))
                continue
            olds = set(listing(d))
            news = set(listing(work / "un_new" / tag))
            print("   %-32s 旧产物 %d B / 原文件 %d B  逐字节相同=%s  "
                  "解包命名差异: 旧独有 %d / 新独有 %d（旧二进制缺 .gz 魔数表）"
                  % (tag, o.stat().st_size, pak.stat().st_size,
                     o.read_bytes() == pak.read_bytes(),
                     len(olds - news), len(news - olds)))
    else:
        print("   注: 没找到在库旧二进制，跳过对照")

    print("== [4] 全部判据通过才落盘 ==")
    if fails:
        for f in fails:
            print("   FAIL:", f)
        print("VERDICT: FAIL — 未覆盖 binaries/（保持原样，避免把未验证的二进制当发布物）")
        return 1
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    written = {}
    for p in (x64, x86):
        dst = BIN_DIR / p.name
        shutil.copy2(str(p), str(dst))
        written[p.name] = {"bytes": dst.stat().st_size, "sha256": sha256(dst)}
    manifest = {
        # 故意不写构建时间戳：清单内容只由输入决定，同样输入重建不产生 git 噪声
        # （与 /Brepro 同一理由——哈希要能当真核对依据）。
        "source": {"file": "pak_src_fixed/pak.c", "sha256": sha256(SRC_SINGLE)},
        "reference_source": {"dir": "pak_src/", "sha256_of_build": sha256(ref)},
        "compiler": {"name": "MSVC", "toolset": VC.name, "flags": CL_BASE},
        "artifacts": written,
        "corpus": [{"file": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                   for p in paks],
        # ADR-003：本项目只发布 Windows x64，其它平台的 pak 构建物不在范围内，
        # 因此**不重建**——列在这里是为了让人分清"没做"与"漏了"。
        "out_of_scope_per_adr003": {
            "binaries/pak": "Linux x86-64 ELF：项目不发布 Linux，保持原样不重建",
            "binaries/pak_arm64": "Linux aarch64 ELF：同上",
        },
        "kept_as_fallback_only": {
            "binaries/pak-win/pak_mingw64.exe": "在库 MinGW 构建物，早于仓库源码"
                                                "（不解 .gz 魔数）；包装器已改为首选 "
                                                "pak_msvc64.exe，它只在缺失时回退",
            "binaries/pak-win/pak_mingw32.exe": "同上（32 位回退；Windows x64 才是发布目标）",
        },
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
    for k, v in written.items():
        print("   落盘 %-18s %d B  sha256=%s" % (k, v["bytes"], v["sha256"][:16]))
    print("   清单 %s" % MANIFEST.relative_to(THOR))
    print("VERDICT: PASS — 真实语料上 5 条判据全过，Windows 侧二进制已与源码对齐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
