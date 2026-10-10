#!/usr/bin/env python3
"""refresh_release.py - publish the freshly built mini_installer as the release
artifact, with verification that the shipped binary carries the bounded flags
loader and that the packaging inputs were correct.

Why the gates changed (method defect found 2026-10-09, logged as D43):
the earlier check byte-searched mini_installer.exe for the literal string
"mcloud_flags.txt". The installer payload is compressed - not only
mcloud_flags.txt, but even "chrome.dll" / "resources.pak" are absent as
plaintext - so that gate could never pass and proved nothing in either
direction. Replacement gates inspect the *inputs* the packer consumed:
  1. out/mcloud/chrome.dll contains the loader v4/v5 budget strings
     (proves the linked binary is not a stale object file).
  2. out/mcloud/mcloud_flags.txt exists and is byte-identical to the repo copy
     (the installer packs whatever sits next to chrome.dll).
  3. chrome/installer/mini_installer/chrome.release lists mcloud_flags.txt
     under %(ChromeDir)s (that is what makes the packer include it at all).
  4. installer mtime >= chrome.dll mtime (installer was made from this dll).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

SRC = r"D:\wxmuma\chromium-src\src"
OUT = os.path.join(SRC, "out", "mcloud")
DLL = os.path.join(OUT, "chrome.dll")
INSTALLER = os.path.join(OUT, "mini_installer.exe")
CHROME_7Z = os.path.join(OUT, "chrome.7z")
DEPLOYED_FLAGS = os.path.join(OUT, "mcloud_flags.txt")
REPO_FLAGS = r"D:\wxmuma\thorium\mcloud_flags.txt"
RELEASE_LIST = os.path.join(SRC, "chrome", "installer", "mini_installer",
                            "chrome.release")
RELEASE = r"D:\wxmuma\thorium\mcloud_151.0.7922.99_win64_mini_installer.exe"
CHUNK = 1 << 22

# Why both gates 5 and 6 exist (D43): mini_installer.exe stores its payload
# compressed, so scanning it for file names proves nothing (even "chrome.dll"
# is absent as plaintext). The payload archive the installer embeds,
# chrome.7z, *does* carry the entry name and the uncompressed text of small
# files, so scanning that is the real end-to-end packaging check; installer
# mtime >= chrome.7z mtime then ties the two together.


def find(path, needles):
    """Chunked scan; 64-byte carry-over exceeds every needle length so no match
    is missed at a chunk boundary."""
    hits = {n: False for n in needles}
    with open(path, "rb") as f:
        carry = b""
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            buf = carry + block
            for n in needles:
                if not hits[n] and n in buf:
                    hits[n] = True
            carry = buf[-64:]
    return hits


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def mtime(path):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path)))


for p in (DLL, INSTALLER, DEPLOYED_FLAGS, REPO_FLAGS, RELEASE_LIST, CHROME_7Z):
    if not os.path.exists(p):
        print("FAIL: missing required file " + p)
        sys.exit(2)

print("chrome.dll        : " + mtime(DLL) + "  (%d bytes)" % os.path.getsize(DLL))
print("mini_installer.exe: " + mtime(INSTALLER) + "  (%d bytes)" % os.path.getsize(INSTALLER))
print("")

dll_hits = find(DLL, [b"command-line budget", b"built-in features skipped",
                      b"mcloud_flags.txt", b"bug-review D40"])
for k, v in dll_hits.items():
    print("  chrome.dll contains %-32r : %s" % (k.decode(), v))

deployed_hash = sha256(DEPLOYED_FLAGS)
repo_hash = sha256(REPO_FLAGS)
# The loader edge suite (round gate 7) temporarily replaces out/mcloud's copy and
# restores it on exit, so a mismatch here is usually "a round is running", not a
# stale package. Retry with a delay before declaring failure.
attempts = 1
while deployed_hash != repo_hash and attempts < 6:
    print("  flags identity mismatch (attempt %d) - a verification round may be "
          "swapping out/mcloud/mcloud_flags.txt; retrying in 60s" % attempts)
    time.sleep(60)
    deployed_hash = sha256(DEPLOYED_FLAGS)
    attempts += 1
print("  out/mcloud/mcloud_flags.txt sha256 : " + deployed_hash[:16] + "...")
print("  repo mcloud_flags.txt       sha256 : " + repo_hash[:16] + "...")
print("  flags byte-identical to repo      : " + str(deployed_hash == repo_hash))

with open(RELEASE_LIST, "r", encoding="utf-8", errors="replace") as f:
    rel_txt = f.read()
listed = "mcloud_flags.txt: %(ChromeDir)s\\" in rel_txt
print("  chrome.release lists mcloud_flags.txt under ChromeDir : " + str(listed))

# Payload archive scan: entry name + current-file freshness markers.
z7 = find(CHROME_7Z, [b"mcloud_flags.txt",
                      "用户确认有效，固化为禁用".encode("utf-8"),
                      b"SpareRendererForSitePerProcess"])
for k, v in z7.items():
    print("  chrome.7z contains %-30s : %s" % (repr(k)[2:-1][:30], v))

problems = []
if not dll_hits[b"command-line budget"]:
    problems.append("chrome.dll lacks the loader v4/v5 budget string -> stale binary")
if not dll_hits[b"mcloud_flags.txt"]:
    problems.append("chrome.dll lacks the flags file name -> loader not linked")
if deployed_hash != repo_hash:
    problems.append("out/mcloud/mcloud_flags.txt differs from the repo copy "
                    "-> the installer would ship a stale flag set")
if not listed:
    problems.append("chrome.release does not list mcloud_flags.txt -> installer "
                    "would not pack it (see other/mini_installer.patch)")
if not z7[b"mcloud_flags.txt"]:
    problems.append("chrome.7z (installer payload) has no mcloud_flags.txt entry")
if not z7["用户确认有效，固化为禁用".encode("utf-8")]:
    problems.append("chrome.7z packs a stale mcloud_flags.txt (missing the "
                    "2026-10-08 freeze marker from the current repo file)")
if not z7[b"SpareRendererForSitePerProcess"]:
    problems.append("chrome.7z flags copy lacks a known built-in feature name")
if os.path.getmtime(INSTALLER) < os.path.getmtime(CHROME_7Z):
    problems.append("installer is older than chrome.7z -> installer predates "
                    "the current payload, rebuild mini_installer first")
if os.path.getmtime(INSTALLER) < os.path.getmtime(DLL):
    problems.append("installer is older than chrome.dll -> rebuild installer first")

if problems:
    print("")
    for msg in problems:
        print("FAIL: " + msg)
    sys.exit(1)

shutil.copy2(INSTALLER, RELEASE)
digest = sha256(RELEASE)
# Sidecar checksum must be rewritten in the same step: it was left holding the
# previous artifact's hash after the 15:25 rebuild (2026-10-09), i.e. the release
# published while its own .sha256 still described the old binary.
with open(RELEASE + ".sha256", "w", newline="\n") as f:
    f.write("%s *%s\n" % (digest, os.path.basename(RELEASE)))

print("")
print("published -> " + RELEASE)
print("size      : %d bytes" % os.path.getsize(RELEASE))
print("SHA256    : " + digest)
print("sidecar   : " + RELEASE + ".sha256")
print("mtime     : " + mtime(RELEASE))
