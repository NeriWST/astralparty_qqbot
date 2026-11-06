# -*- coding: utf-8 -*-
"""角色使用排行卡片：/我的 配图（生涯 usage 版）。
复用 bot_viz 的字体与绘制助手，视觉风格与战绩卡片完全一致。
数据：profile['usage'] = [(角色名, 使用次数), ...]（bot_core.build_profile 产出生涯数据）。"""
import io
from PIL import Image, ImageDraw

from bot_viz import (F, _fit, _cell, _section, _table_header, _row,
                     INK, MUTED, GREEN, PURPLE, LINE)
from stats_report import number as _num, percent


def render_usage_card(profile):
    usage = sorted(list(profile.get("usage") or []), key=lambda x: -x[1])
    rows_n = max(1, min(len(usage), 10))
    total_use = sum(n for _, n in usage) or 1
    height = 396 + (48 + 40 + rows_n * 46 + 22) + 84
    img = Image.new("RGB", (1200, height), "#F5F6F8")
    d = ImageDraw.Draw(img)
    d.rectangle((24, 24, 1176, height - 24), fill="white")
    d.text((40, 49), "ASTRAL PARTY  /  角色使用排行", font=F(18, True), fill=MUTED, anchor="lm")
    nick, font = _fit(d, profile.get("nick", "未知玩家"), 900, 43, True)
    d.text((40, 96), nick, font=font, fill=INK, anchor="lm")
    meta = "国服 · UID %s · Lv.%s · 账号档案" % (profile.get("uid", "—"), _num(profile.get("level")))
    meta, font = _fit(d, meta, 1100, 21)
    d.text((40, 142), meta, font=font, fill=MUTED, anchor="lm")
    if profile.get("online"):
        d.ellipse((1050, 88, 1062, 100), fill=GREEN)
        d.text((1074, 94), "在线", font=F(21, True), fill=GREEN, anchor="lm")
    d.rectangle((40, 174, 1160, 228), fill="#318B25")
    d.text((56, 201), "HERO USAGE", font=F(27, True), fill="white", anchor="lm")
    d.text((260, 201), "%d 个角色 · 累计使用 %d 次" % (len(usage), total_use),
           font=F(21), fill="white", anchor="lm")
    if usage:
        top_name = _fit(d, usage[0][0], 180, 21)[0]
        d.text((1144, 201), "最多  " + top_name, font=F(21, True), fill="white", anchor="rm")
    metrics = [("累计场次", _num(profile.get("total"))), ("累计胜率", percent(profile.get("winrate"))),
               ("累计胜场", _num(profile.get("wins"))), ("获赞", _num(profile.get("praise"))),
               ("拥有角色", _num(profile.get("heroes")))]
    for i, (label, value) in enumerate(metrics):
        x = 40 + i * 224
        d.rectangle((x, 246, x + 212, 340), fill="#F2F4F6")
        d.text((x + 106, 268), label, font=F(20, True), fill=MUTED, anchor="mm")
        value, font = _fit(d, value, 200, 34, True)
        d.text((x + 106, 309), value, font=font, fill=PURPLE if i == 1 else INK, anchor="mm")
        d.line((x, 340, x + 212, 340), fill="#97BDCF", width=2)
    scope = "范围：全部生涯 · 来源账号档案"
    if profile.get("stale"):
        scope += " · 包含缓存数据"
    scope, font = _fit(d, scope, 1120, 17)
    d.text((40, 362), scope, font=font, fill=MUTED, anchor="lm")
    y = 396
    columns = [(40, 520), (520, 860), (860, 1160)]
    y = _section(d, y, "角色使用排行", "按使用次数排序 · 最多 10 位")
    y = _table_header(d, y, columns, ["角色", "使用次数", "占比"])
    if usage:
        for i, (name, n) in enumerate(usage[:10]):
            pct = "%d%%" % round(100 * n / total_use)
            y = _row(d, y, columns, [name, "%s 次" % _num(n), pct], i)
    else:
        y = _row(d, y, columns, ["暂无角色使用数据", "—", "—"], 0)
    y += 22
    d.text((40, y + 5), "使用次数为生涯累计（不含近 10 场限制）；角色名为游戏内官方名称。",
           font=F(17), fill=MUTED, anchor="lm")
    d.text((40, y + 30), "数据来自登录档案，随账号同步更新。", font=F(17), fill=MUTED, anchor="lm")
    return img


def render_usage_card_png(profile):
    buf = io.BytesIO()
    render_usage_card(profile).save(buf, "PNG")
    return buf.getvalue()
