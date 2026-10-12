#!/bin/sh
# pak_src_fixed 的往返/兼容性判据（POSIX 侧，CI ubuntu 上真跑；
# Windows 本机没有 gcc/clang，请用 build_and_test.bat +
# ../.cycle7/pakverify.py 的 MSVC + ASan 判据）。
#
# 由 REVIEW.md §6 承诺但从未入库的 run_test.sh 补写而成（第7周期 D194）。
set -eu

BIN=${BIN:-./pak}
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"          # 全部改用相对路径：MSVC 版二进制读不懂 MSYS 的 /d/... 形式
WORK=t_out_build
fails=0

[ -x "$BIN" ] || { echo "FAIL: 找不到可执行 $BIN（先 make）"; exit 1; }
rm -rf "$WORK"; mkdir -p "$WORK"

# 1) 两次打包必须字节一致（D190：未初始化头部填充会让产物不可复现）
cp -r "$HERE/t_in" "$WORK/a"
cp -r "$HERE/t_in" "$WORK/b"
"$BIN" -p "$WORK/a/pak_index.ini" "$WORK/a.pak" > /dev/null
"$BIN" -p "$WORK/b/pak_index.ini" "$WORK/b.pak" > /dev/null
if cmp -s "$WORK/a.pak" "$WORK/b.pak"; then
    echo "PASS deterministic-pack"
else
    echo "FAIL deterministic-pack: 同一输入两次打包产物不同"
    fails=$((fails + 1))
fi

# 2) 解包后内容逐字节还原
"$BIN" -u "$WORK/a.pak" "$WORK/un" > /dev/null
for f in 1.html 2.png; do
    if cmp -s "$WORK/a/$f" "$WORK/un/$f"; then
        echo "PASS roundtrip-$f"
    else
        echo "FAIL roundtrip-$f: 内容不等"
        fails=$((fails + 1))
    fi
done
[ -f "$WORK/un/pak_index.ini" ] \
    && echo "PASS index-regenerated" \
    || { echo "FAIL index-regenerated: 未生成 pak_index.ini"; fails=$((fails + 1)); }

# 3) v4 头部（无别名）可用
mkdir -p "$WORK/v4"
cp "$WORK/a/1.html" "$WORK/a/2.png" "$WORK/v4/"
printf '[Global]\nversion=4\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n' \
    > "$WORK/v4/pak_index.ini"
"$BIN" -p "$WORK/v4/pak_index.ini" "$WORK/v4.pak" > /dev/null
"$BIN" -u "$WORK/v4.pak" "$WORK/v4out" > /dev/null
if cmp -s "$WORK/v4/2.png" "$WORK/v4out/2.png"; then
    echo "PASS v4-header"
else
    echo "FAIL v4-header: v4 往返内容不等"
    fails=$((fails + 1))
fi

# 4) D193：v4 声明别名必须被拒绝，不允许静默丢别名还返回 0
mkdir -p "$WORK/v4a"
cp "$WORK/v4/1.html" "$WORK/v4/2.png" "$WORK/v4a/"
printf '[Global]\nversion=4\nencoding=0\n\n[Resources]\n1=1.html\n2=2.png\n\n[Alias]\n10=1\n' \
    > "$WORK/v4a/pak_index.ini"
if "$BIN" -p "$WORK/v4a/pak_index.ini" "$WORK/v4a.pak" > /dev/null 2>&1; then
    echo "FAIL v4-alias-rejected: 工具接受了 v4+别名（会静默丢弃别名表）"
    fails=$((fails + 1))
else
    rm -f "$WORK/v4a.pak"
    echo "PASS v4-alias-rejected"
fi

# 5) 畸形输入必须非 0 退出
head -c 8 "$WORK/a.pak" > "$WORK/trunc.pak"
if "$BIN" -u "$WORK/trunc.pak" "$WORK/bad" > /dev/null 2>&1; then
    echo "FAIL corrupt-rejected: 截断的 .pak 被当成成功"
    fails=$((fails + 1))
else
    echo "PASS corrupt-rejected"
fi

rm -rf "$WORK"
if [ "$fails" -ne 0 ]; then
    echo "RESULT: FAIL ($fails)"
    exit 1
fi
echo "RESULT: PASS"
