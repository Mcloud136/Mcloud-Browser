#!/usr/bin/env python3
"""upload_r3_asset.py - 用本机 Git 凭据调 GitHub API，把 r3 安装包传成 Release 资产。

安全约束：令牌只在本进程内存中使用，绝不打印、绝不写盘、绝不进入日志；
失败时只输出 HTTP 状态与错误类型。
"""
import hashlib
import http.client
import json
import os
import subprocess
import sys
import urllib.parse

OWNER = "Mcloud136"
REPO = "Mcloud-Browser"
TAG = "v151.0.7922.99-r3"
FILE = r"D:\wxmuma\thorium\mcloud_151.0.7922.99_win64_mini_installer.exe"
NAME = os.path.basename(FILE)


def get_token():
    # 不重构 env：Windows 上重写环境字典会丢掉 GCM 需要的变量（实测 fill 直接失败）
    p = subprocess.run(["git", "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        # 只报错误类别，不回显任何输出内容
        raise RuntimeError("git credential fill 失败（可能需要在终端里完成一次登录）")
    for ln in (p.stdout or "").splitlines():
        if ln.startswith("password="):
            return ln.split("=", 1)[1].strip()
    raise RuntimeError("凭据里未包含令牌")


def api(token, method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    conn = http.client.HTTPSConnection("api.github.com", timeout=60)
    hdr = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28",
           "User-Agent": "mcloud-release-tool"}
    if body:
        hdr["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=hdr)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, (json.loads(data) if data else {})


def upload_asset(token, release_id, size, sha):
    path = f"/repos/{OWNER}/{REPO}/releases/{release_id}/assets?name={urllib.parse.quote(NAME)}"
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=900)
    with open(FILE, "rb") as fh:
        conn.request("POST", path, body=fh, headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(size),
            "User-Agent": "mcloud-release-tool"})
        res = conn.getresponse()
        status, data = res.status, res.read()
    conn.close()
    return status, (json.loads(data) if data else {})


def main():
    if not os.path.isfile(FILE):
        print("FAIL: 找不到安装包", FILE)
        return 1
    size = os.path.getsize(FILE)
    h = hashlib.sha256()
    with open(FILE, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 22), b""):
            h.update(blk)
    sha = h.hexdigest()
    print(f"本地文件 {NAME}  size={size}  sha256={sha}")

    token = get_token()
    st, rel = api(token, "GET", f"/repos/{OWNER}/{REPO}/releases/tags/{TAG}")
    if st != 200:
        print(f"FAIL: 取 release 失败 HTTP {st}: {rel.get('message', '')}")
        return 1
    print(f"release id={rel['id']}  name={rel['name']}  现有资产={len(rel.get('assets', []))}")

    for a in rel.get("assets", []):
        if a["name"] == NAME:
            print(f"已存在同名资产，跳过上传：{a['browser_download_url']}")
            return verify(token, a, size, sha)

    st, asset = upload_asset(token, rel["id"], size, sha)
    if st not in (201, 200):
        print(f"FAIL: 上传失败 HTTP {st}: {asset.get('message', '')}")
        return 1
    print(f"上传完成 HTTP {st}: {asset.get('name')}  size={asset.get('size')}")
    return verify(token, asset, size, sha)


def verify(token, asset, size, sha):
    url = asset.get("url") or ""
    st, fresh = api(token, "GET", urllib.parse.urlparse(url).path) if url else (0, {})
    if st != 200:
        st, fresh = api(token, "GET", f"/repos/{OWNER}/{REPO}/releases/assets/{asset['id']}")
    dig = (fresh.get("digest") or "").replace("sha256:", "")
    print(f"远端 size={fresh.get('size')}  GitHub 计算 sha256={dig or '(未提供)'}")
    ok = fresh.get("size") == size and (not dig or dig == sha)
    print("校验:", "PASS — 远端字节与本地一致" if ok else "FAIL — 需要重传")
    print("下载入口:", fresh.get("browser_download_url") or asset.get("browser_download_url"))
    print("发布页:", f"https://github.com/{OWNER}/{REPO}/releases/tag/{TAG}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
