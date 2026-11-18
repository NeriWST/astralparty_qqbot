# -*- coding: utf-8 -*-
"""复盘单玩家图：每名玩家一张竖版长图；升星/筹码/任务回合的行下方挂动作注解。"""
import io
from PIL import Image, ImageDraw

from bot_viz import (F, _fit, _cell, _section, _table_header, _row,
                     INK, MUTED, GREEN, PURPLE, LINE, RED)

_EVENT_COLOR = {"★": "#B8860B", "◆": GREEN}


def _num(v):
    return "{:,}".format(int(v)) if isinstance(v, (int, float)) else str(v)


def render_player_images(review, hero_names=None, page_h=2800):
    """单玩家一张长图：头部 + 逐回合表（行下事件注解）+ 小计 + 筹码汇总。
    单画布顺序渲染；page_h 仅作高度上限保护。"""
    ps = review["players"]
    out = []
    for idx, p in enumerate(ps):
        hero = (hero_names or {}).get(p.get("hero_id"), "")
        rounds = p["rounds"]
        events = p.get("events", {})
        n_evt = sum(len(v) for v in events.values())
        height = 210 + 40 + (len(rounds) + 1) * 46 + n_evt * 26 + 60
        height = min(height, 40000)   # 用户铁律：宁可图超长也绝不省略回合；此为防失控兜底，正常对局远碰不到
        W = 1200
        img = Image.new("RGB", (W, height), "#F5F6F8")
        d = ImageDraw.Draw(img)
        d.rectangle((24, 24, W - 24, height - 24), fill="white")
        d.text((48, 54), "ASTRAL PARTY  /  对局复盘", font=F(18, True), fill=MUTED, anchor="lm")
        title = "玩家 %d/%d · %s（%s）" % (idx + 1, len(ps), p["nick"], hero)
        d.text((48, 100), title, font=F(34, True), fill=INK, anchor="lm")
        meta = "回放 #%s　Lv.%s　回合 %d" % (
            review.get("replay_id", "?"), p.get("level", "?"),
            review.get("rounds", len(rounds)))
        d.text((48, 148), meta, font=F(22), fill=MUTED, anchor="lm")
        d.line((48, 180, W - 48, 180), fill=LINE, width=2)

        cols = [(56, 130), (130, 245), (245, 405), (405, 565), (565, 695),
                (695, 825), (825, 945), (945, 1060), (1060, 1144)]
        heads = ["回合", "击杀", "伤害", "承伤", "星币", "转账", "治疗", "移动", "死亡"]
        y = 196
        y = _table_header(d, y, cols, heads)
        for i, r in enumerate(rounds):
            died = "×%d" % r["deaths"] if r["deaths"] else "—"
            vals = [str(r["round"]), _num(r["kill"]), _num(r["dmg"]), _num(r["inj"]),
                    _num(r["gold"]), _num(r["transfer"]), _num(r["tret"]),
                    _num(r["move"]), died]
            colors = {8: RED if r["deaths"] else INK}
            if r.get("boss"):
                colors[0] = "#B8860B"
            y = _row(d, y, cols, vals, i, colors)
            for ev in events.get(r["round"], []):
                if isinstance(ev, dict):
                    y = _draw_chip_line(d, cols[0][0] + 16, y, ev)
                else:
                    tag = ev[:1]
                    d.text((cols[0][0] + 16, y + 13), ev, font=F(17),
                           fill=_EVENT_COLOR.get(tag, PURPLE), anchor="lm")
                    y += 26
        t = p["totals"]
        y = _row(d, y, cols, ["小计", _num(t["kill"]), _num(t["dmg"]), _num(t["inj"]),
                              _num(t["gold"]), _num(t["transfer"]), _num(t["tret"]),
                              _num(t["move"]), "×%d" % t.get("died", 0)], 99, {0: PURPLE}, bold=True)
        y += 16
        chips = p.get("chips", [])
        if chips:
            qmap = {"蓝": "#4C7DD9", "紫": "#9C59B6", "金": "#D4A017"}
            segs = [("筹码：", MUTED, False)]
            for i2, c in enumerate(chips[:8]):
                col = qmap.get(str(c.get("quality")), INK)
                segs.append(("%s(%s)" % (c["name"], c["quality"]), col, False))
                if i2 < min(len(chips), 8) - 1:
                    segs.append(("、", MUTED, False))
            y += _draw_segments(d, 56, y + 14, segs, 20) + 14
        out.append((idx, p["nick"], img))
    return out



PLAYER_COLORS = ("#4C7DD9", "#D96B4C", "#4CAF7D", "#B07CD9")


def _num0(v):
    v = int(v)
    return "{:,}".format(v) if v >= 10000 else str(v)


def _line_chart(d, box, title, xs, series, colors, names):
    """单张折线小图：box=(x,y,w,h)；series=[每玩家累计值列表]。"""
    x, y, w, h = box
    d.rectangle((x, y, x + w, y + h), fill="white", outline=LINE)
    d.text((x + 14, y + 8), title, font=F(20, True), fill=INK)
    pl, pr, pt, pb = 52, 84, 36, 26
    cw, ch = w - pl - pr, h - pt - pb
    n = max(len(xs), 2)
    maxv = max((max(s) for s in series if s), default=1) or 1
    for gi in range(4):
        gv = maxv * gi / 3.0
        gy = y + pt + ch - (gv / maxv) * ch
        d.line((x + pl, gy, x + pl + cw, gy), fill="#EFEFEF")
        d.text((x + pl - 6, gy), _num0(gv), font=F(13), fill=MUTED, anchor="rm")
    for pi, s in enumerate(series):
        if not s:
            continue
        pts = [(x + pl + (i / (n - 1)) * cw, y + pt + ch - (v / maxv) * ch)
               for i, v in enumerate(s)]
        d.line(pts, fill=colors[pi], width=3)
        d.text((x + pl + cw + 6, pts[-1][1]), _num0(s[-1]), font=F(15, True),
               fill=colors[pi], anchor="lm")
    step = max(1, (n - 1) // 6)
    for i in range(0, n, step):
        xx = x + pl + (i / (n - 1)) * cw
        d.text((xx, y + pt + ch + 12), str(xs[i]), font=F(12), fill=MUTED, anchor="ma")
    for ni, nm in enumerate(names):
        d.text((x + 14 + ni * 150, y + h - 20), nm, font=F(13),
               fill=colors[ni] if ni < len(colors) else MUTED, anchor="lm")


def render_overview(review, hero_names=None):
    """总览图：4 玩家 × 6 项累计指标折线（2列×3行）。"""
    ps = review["players"]
    names = []
    series_map = {"dmg": [], "deaths": [], "gold": [], "tret": [], "kill": [], "move": []}
    for idx, p in enumerate(ps):
        hero = (hero_names or {}).get(p.get("hero_id"), "")
        names.append("%s%s" % (p["nick"], "(%s)" % hero if hero else ""))
        rounds = p["rounds"]
        xs = [r["round"] for r in rounds]
        for key in series_map:
            acc, total = [], 0
            for r in rounds:
                total += r.get(key, 0) or 0
                acc.append(total)
            series_map[key].append(acc)
    W, H = 1200, 1240
    img = Image.new("RGB", (W, H), "#F5F6F8")
    d = ImageDraw.Draw(img)
    d.rectangle((24, 24, W - 24, H - 24), fill="white")
    d.text((48, 58), "ASTRAL PARTY  /  对局复盘 · 总览", font=F(18, True), fill=MUTED, anchor="lm")
    d.text((48, 104), "回放 #%s" % review.get("replay_id", "?"), font=F(34, True), fill=INK, anchor="lm")
    # 图例
    lx = 48
    for ni, nm in enumerate(names):
        d.rectangle((lx, 150, lx + 16, 166), fill=PLAYER_COLORS[ni % 4])
        d.text((lx + 24, 158), nm, font=F(18), fill=INK, anchor="lm")
        lx += 24 + d.textlength(nm, font=F(18)) + 36
    titles = [("dmg", "累计伤害"), ("deaths", "累计死亡"), ("gold", "累计星币"),
              ("tret", "累计治疗"), ("kill", "累计击杀"), ("move", "累计步数")]
    bw, bh = 560, 300
    for i, (key, title) in enumerate(titles):
        cx = 48 + (i % 2) * (bw + 24)
        cy = 196 + (i // 2) * (bh + 20)
        _line_chart(d, (cx, cy, bw, bh), title, xs, series_map[key], PLAYER_COLORS, names)
    return img


def stack_images(imgs, gap=36, max_h=12000):
    """竖向拼接；总高超 max_h 时在整图边界处断开（返回 1~2 张）。"""
    outs, cur, cur_h = [], None, 0
    for im in imgs:
        if cur is not None and cur_h + gap + im.height > max_h:
            outs.append(cur)
            cur, cur_h = None, 0
        if cur is None:
            cur = Image.new("RGB", (1200, 0), "#F5F6F8")
            cur_h = 0
        new = Image.new("RGB", (1200, cur_h + gap + im.height), "#F5F6F8")
        new.paste(cur, (0, 0))
        new.paste(im, (0, cur_h + gap))
        cur = new
        cur_h = new.height
    if cur is not None:
        outs.append(cur)
    return outs


def render_all_png(review, hero_names=None):
    """总览 + 4 玩家拼接 → 1~2 张 PNG（一条/两条消息发完）。"""
    parts = [render_overview(review, hero_names)]
    for _, _, im in render_player_images(review, hero_names):
        parts.append(im)
    finals = stack_images(parts)
    out = []
    for im in finals:
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out.append(buf.getvalue())
    return out

def render_parts_png(review, hero_names=None):
    """散图输出：[总览, 玩家1, 玩家2, 玩家3, 玩家4]（markdown 一条多图用）。"""
    out = []
    for im in [render_overview(review, hero_names)] + [
            im for _, _, im in render_player_images(review, hero_names)]:
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out.append(buf.getvalue())
    return out

def _draw_segments(d, x, y_mid, segs, size=17):
    """segs=[(text, color, bold), ...] 逐段绘制并自动截断。返回占用的 y 增量。"""
    cx = x
    limit = 1136
    for text, color, bold in segs:
        font = F(size, bold)
        w = d.textlength(text, font=font)
        if cx + w > limit:
            d.text((cx, y_mid), "…", font=font, fill=MUTED, anchor="lm")
            break
        d.text((cx, y_mid), text, font=font, fill=color, anchor="lm")
        cx += w
    return 26


def _draw_chip_line(d, x, y, ev):
    """筹码事件行：来源(紫) 候选1 候选2 候选3(各自品质色) → 选中(品质色加粗) ·价格 ·换N批"""
    segs = [(ev["src"] + "：", PURPLE, False)]
    for i2, (nm, col) in enumerate(ev["cands"]):
        segs.append((nm, col, False))
        if i2 < len(ev["cands"]) - 1:
            segs.append((" ", MUTED, False))
    segs.append((" → ", MUTED, False))
    if ev["chosen"]:
        segs.append((ev["chosen"][0], ev["chosen"][1], True))
    else:
        segs.append(("未选", MUTED, False))
    if ev["price"]:
        segs.append((" · %d币" % ev["price"], MUTED, False))
    if ev["refresh"]:
        segs.append(("（换%d批）" % ev["refresh"], MUTED, False))
    _draw_segments(d, x, y + 13, segs, 17)
    return y + 26   # 返回推进后的新 y（调用方是 y = ... 赋值）

