# Copyright (c) 2026 Alex313031 and gz83.

# This file is the equivalent of build_win.sh in the parent directory.

import os
import subprocess
import sys

# Error handling functions


def fail(msg):
    # Print error message and exit
    print(f"{sys.argv[0]}: {msg}", file=sys.stderr)
    sys.exit(111)


def try_run(command):
    if subprocess.call(command, shell=True) != 0:
        fail(f"Failed {command}")


# Help function
def display_help():
    print("\nScript to build Mcloud Browser for Windows.\n")
    print("Usage: python win_scripts\build_win.py # (where # is number of jobs)\n")


if '--help' in sys.argv:
    display_help()
    sys.exit(0)


# Set chromium/src dir from Windows environment variable
cr_src_dir = os.getenv('CR_DIR', r'C:/src/chromium/src')

print("\nBuilding Mcloud Browser for Windows\n")


def read_args_gn(path):
    """把 args.gn 解析成 {key: 字面量文本}，只认顶层 `key = value` 行（够用且不误伤注释）。"""
    values = {}
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or '=' not in stripped:
                    continue
                key, _, val = stripped.partition('=')
                values[key.strip()] = val.strip()
    except OSError:
        return None
    return values


def preflight_args(out_dir, template=None):
    """编译前校验 PGO 配置。缺陷 D144：仓库模板 win_args_mcloud.gn 的 pgo_data_path 曾指向
    M151 回滚树（那里没有 8059 的 profdata），而实际构建树的 args.gn 已被手工改对，两边
    静默漂移。GN 只断言路径非空、不校验存在（build/config/compiler/pgo/BUILD.gn:149），
    于是 `gn gen` 能过、ninja 才在第 156 行 `inputs += [pgo_data_path]` 上报
    "missing and no known rule to make it"——失败信息完全不指向根因。这里提前拦下来。

    template 可显式注入，便于测试；默认按本文件位置推出仓库根的 win_args_mcloud.gn。"""
    args_path = os.path.join(out_dir, 'args.gn')
    args = read_args_gn(args_path)
    if args is None:
        print(f"WARN: 读不到 {args_path}，跳过 PGO 预检（gn gen 还没跑？）")
        return

    phase = args.get('chrome_pgo_phase', '0').strip()
    profdata = args.get('pgo_data_path', '').strip().strip('"')
    if phase.startswith('2') and profdata:
        # GN 里写的是正斜杠绝对路径，转成本地路径再判存在
        local = profdata.replace('/', os.sep)
        if not os.path.isfile(local):
            fail(f"chrome_pgo_phase=2 但 PGO 剖面不存在：{local}\n"
                 f"  来源：{args_path} 的 pgo_data_path\n"
                 f"  常见原因是该路径指向了另一棵源码树（本机同时存在 M151 与 M155 两棵树），\n"
                 f"  或内核升级后没同步更新 profdata 文件名里的 build 号。\n"
                 f"  修法：把 pgo_data_path 指向当前构建树的 chrome/build/pgo_profiles/ 下\n"
                 f"  与内核版本匹配的那份；或临时把 chrome_pgo_phase 设为 0 关闭 PGO。")
        size_mb = os.path.getsize(local) / (1024 * 1024)
        print(f"PGO 预检 OK：phase={phase} 剖面 {size_mb:.0f} MB @ {local}")

    # 漂移检测：仓库模板与实际构建树的 args.gn 必须一致，否则"仓库里的配置"
    # 根本不是"构建出发布物的配置"，发布不可复现（D144 的根因形态）。
    if template is None:
        thor_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template = os.path.join(thor_dir, 'win_args_mcloud.gn')
    tmpl_args = read_args_gn(template)
    if tmpl_args is None:
        print(f"WARN: 读不到仓库模板 {template}，无法做漂移比对")
        return
    drift = []
    for key in sorted(set(tmpl_args) | set(args)):
        tv, av = tmpl_args.get(key), args.get(key)
        if tv is None:
            drift.append(f"  仅构建树有: {key} = {av}")
        elif av is None:
            drift.append(f"  仅模板有:   {key} = {tv}")
        elif tv != av:
            drift.append(f"  取值不同:   {key}\n"
                         f"              模板   = {tv}\n"
                         f"              构建树 = {av}")
    if drift:
        print("WARN: 仓库模板 win_args_mcloud.gn 与构建树 args.gn 存在漂移"
              "（发布将不可复现，请对齐后重新 gn gen）：")
        for line in drift:
            print(line)
    else:
        print("漂移比对 OK：仓库模板与构建树 args.gn 逐项一致")


# Change directory and run build commands
os.chdir(cr_src_dir)
preflight_args(os.path.join(cr_src_dir, 'out', 'mcloud'))
# Determine the number of threads to use
jobs = sys.argv[1] if len(sys.argv) > 1 else str(os.cpu_count())

# D29（2026-10-08 修复）：原脚本引用本项目不存在的 mcloud_all / setup 目标
# （上游 Thorium 专有），永远构建失败。改为与 AGENTS.md 一致的目标集。
try_run(f'autoninja -C out/mcloud chrome -j{jobs}')

try_run(f'autoninja -C out/mcloud mini_installer -j{jobs}')

installer_dest = os.path.normpath(os.path.join(cr_src_dir, 'out', 'mcloud'))

print(f"Build Completed. Installer at '{installer_dest}'")
