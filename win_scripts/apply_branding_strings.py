#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按用户定案的「层一」改写关于页文案 —— 只动 UI 字符串，不碰安装身份。

边界（务必保持）：
  本脚本**不修改** `chrome/app/theme/chromium/BRANDING`。
  因此下列全部保持不变：安装子目录（Chromium）、注册表键（Software\\Chromium）、
  卸载项（DisplayName/Publisher）、以及安装器对"旧版本"的识别。
  改变 BRANDING 属"层二"，会让新包与已装版本变成两个产品并存，需另立迁移方案。

改三处：
  1. chromium_strings.grd  IDS_PRODUCT_NAME（非 _is_chrome_for_testing_branded 分支）
     Chromium -> Mcloud
  2. chromium_strings.grd  IDS_ABOUT_VERSION_COPYRIGHT（同上分支，原文含
     "The Chromium Authors. All rights reserved."）
     -> Copyright <year> Mcloud. All rights reserved.
  3. chromium_strings_zh-CN.xtb 里那条中文版权
     版权所有<year> The Chromium Authors。保留所有权利。
     -> 版权所有 <year> 狗木马
  IDS_PRODUCT_NAME 是 translateable="false"，只存在于 .grd，不需要动 .xtb。

年份用 grit 的 <ph name="YEAR">{0,date,y}</ph> 运行时占位符（与上游一致）：
今天渲染为 2026，明年自动变 2027。若要写死成年份字面量，改 COPYRIGHT_EN/ZH 即可。

幂等：按"原文特征串"匹配，已改过则匹配不到、原样跳过；可重复运行。
"""
import os
import re
import sys

CR = os.environ.get("CR_DIR", r"D:\wxmuma\chromium-src\src")
GRD = os.path.join(CR, "chrome", "app", "chromium_strings.grd")
XTB = os.path.join(CR, "chrome", "app", "resources", "chromium_strings_zh-CN.xtb")

PRODUCT_NAME = "Mcloud"
COPYRIGHT_EN = 'Copyright <ph name="YEAR">{0,date,y}<ex>2026</ex></ph> Mcloud. All rights reserved.'
COPYRIGHT_ZH = '版权所有 <ph name="YEAR" /> 狗木马'


def compute_message_id(grd_inner):
    """算出这条 message 在 .xtb 里的数字 ID。

    2026-11-09 实测（这是本脚本的关键，漏了就会静默丢翻译）：
      grit 的 xtb id = tclib.GenerateMessageId(可呈现文本, meaning)。
      - 可呈现文本里，`<ph name="X">…</ph>` 渲染成**占位符名** `X`；
      - meaning 传 None。
      标定：'The Chromium Authors' -> 985602178874221306（与 xtb 一致）；
            'Copyright YEAR The Chromium Authors. All rights reserved.'
              -> 8586442755830160949（与 xtb 一致）。
    **改英文原文 = 改 id**，原先 8586… 那条翻译因此失配、被 grit 丢弃，
    构建与哈希全部正常，只有关于页退回英文——第一次就是这么踩的。
    """
    sys.path.insert(0, os.path.join(CR, "tools", "grit"))
    from grit.extern import tclib  # noqa: E402  (依赖 CR_DIR，必须延迟导入)

    presentable = re.sub(r'<ph name="([^"]+)"[^>]*?/>', r"\1", grd_inner)
    presentable = re.sub(r'<ph name="([^"]+)"[^>]*?>.*?</ph>', r"\1",
                         presentable, flags=re.S)
    presentable = re.sub(r"\s+", " ", presentable).strip()
    return str(tclib.GenerateMessageId(presentable, None)), presentable


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def check_tree(path):
    """拒绝在错误的树上静默成功（与 deploy_mcloud 的 require_tree 同一条纪律）。"""
    if not os.path.isdir(CR):
        print("CR_DIR 不存在: %s" % CR)
        return False
    if not os.path.isfile(path):
        print("目标文件不存在: %s" % path)
        return False
    return True


def patch_message(text, name, contains, new_inner):
    """替换 <message name="..."> 的内容，只命中 body 里含 contains 的那一处。

    保留原有缩进与换行，避免产生无意义的整文件 diff。
    """
    pat = re.compile(r'(<message name="%s"[^>]*>)(.*?)(</message>)'
                     % re.escape(name), re.S)
    state = {"hit": 0, "already": 0}

    def repl(m):
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if contains not in body:
            return m.group(0)
        lead = re.match(r"(\s*)", body).group(1)
        trail = re.search(r"(\s*)$", body).group(1)
        if body.strip() == new_inner.strip():
            state["already"] += 1
            return m.group(0)
        state["hit"] += 1
        return head + lead + new_inner + trail + tail

    return pat.sub(repl, text), state


def patch_translation_by_text(text, needles, new_inner, new_id):
    """把匹配到的 <translation> 整条改写为新的 id 与文案。

    needles 必须**全部**命中才替换。这一点不能省：公司名
    IDS_ABOUT_VERSION_COMPANY_NAME 的中文条目内容就是字面量 "The Chromium Authors"，
    只按它匹配会把公司名条目一并改写（首次实现即踩此坑，误改 id=985602178874221306）。
    版权条目同时含 "The Chromium Authors" 与 "保留所有权利"，两条特征可唯一确定。
    """
    pat = re.compile(r'<translation id="\d+">.*?</translation>', re.S)
    state = {"hit": 0, "already": 0}
    replacement = '<translation id="%s">%s</translation>' % (new_id, new_inner)

    def repl(m):
        whole = m.group(0)
        body = re.sub(r'^<translation id="\d+">|</translation>$', '', whole)
        if not all(n in body for n in needles) and whole != replacement:
            return whole
        if whole == replacement:
            state["already"] += 1
            return whole
        state["hit"] += 1
        return replacement

    return pat.sub(repl, text), state


def main():
    if not check_tree(GRD):
        return 2
    if not check_tree(XTB):
        print("提示：找不到 %s，中文版权将保持上游默认。" % XTB)
        return 2

    grd = read_text(GRD)
    grd, s1 = patch_message(grd, "IDS_PRODUCT_NAME", "Chromium", PRODUCT_NAME)
    grd, s2 = patch_message(grd, "IDS_ABOUT_VERSION_COPYRIGHT",
                            "The Chromium Authors. All rights reserved.",
                            COPYRIGHT_EN)
    write_text(GRD, grd)

    xtb = read_text(XTB)
    new_id, presentable = compute_message_id(COPYRIGHT_EN)
    print("版权消息 xtb id = %s   （可呈现文本：%s）" % (new_id, presentable))
    xtb, s3 = patch_translation_by_text(
        xtb, ("The Chromium Authors", "保留所有权利"), COPYRIGHT_ZH, new_id)
    write_text(XTB, xtb)

    print("GRD  IDS_PRODUCT_NAME            : 改 %d 处 / 已是最新 %d 处" % (s1["hit"], s1["already"]))
    print("GRD  IDS_ABOUT_VERSION_COPYRIGHT : 改 %d 处 / 已是最新 %d 处" % (s2["hit"], s2["already"]))
    print("XTB  zh-CN 版权                  : 改 %d 处 / 已是最新 %d 处" % (s3["hit"], s3["already"]))

    # 收尾自检：三处都必须已经是目标值，否则不算成功
    grd2 = read_text(GRD)
    xtb2 = read_text(XTB)
    ok = True
    bodies = [m.group(1).strip() for m in re.finditer(
        r'<message name="IDS_PRODUCT_NAME"[^>]*>(.*?)</message>', grd2, re.S)]
    if PRODUCT_NAME not in bodies:
        print("FAIL: IDS_PRODUCT_NAME 未写入（现有分支值：%s）" % bodies)
        ok = False
    if "Mcloud. All rights reserved." not in grd2:
        print("FAIL: 英文版权未写入")
        ok = False
    if COPYRIGHT_ZH not in xtb2:
        print("FAIL: 中文版权未写入")
        ok = False
    elif '<translation id="%s">%s</translation>' % (new_id, COPYRIGHT_ZH) not in xtb2:
        print("FAIL: 中文版权条目的 id 与英文原文不匹配（grit 会丢弃该翻译）")
        ok = False
    print("自检: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
