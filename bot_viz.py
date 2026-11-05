# -*- coding: utf-8 -*-
"""战绩卡片渲染（PIL）。/我的 配图用。
依赖：Pillow + 中文字体（服务器需 apt install fonts-noto-cjk）。"""
import io
import os
from PIL import Image, ImageDraw, ImageFont

_BOLD_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
]
_REG_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
]

def _find(cands):
    for p in cands:
        if os.path.exists(p):
            return p
    return None

_FP_BOLD = _find(_BOLD_CANDIDATES)
_FP_REG = _find(_REG_CANDIDATES)
_FCACHE = {}

def F(size, bold=False):
    key = (size, bold)
    if key not in _FCACHE:
        fp = _FP_BOLD if bold else _FP_REG
        if fp is None:
            raise RuntimeError('找不到中文字体：请 sudo apt install fonts-noto-cjk')
        _FCACHE[key] = ImageFont.truetype(fp, size)
    return _FCACHE[key]

def _vgrad(size, top, bottom):
    w, h = size
    col = Image.new('RGB', (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        col.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return col.resize((w, h))

def _num(v):
    return '-' if v is None else str(v)

def render_stats_card(p, recent):
    """p: dict(nick, uid, level, online, total, wins, winrate, praise, heroes)
    recent: list of dict(hero, damage|None, transfer|None, win: bool)，最多 10 条"""
    W = 1000
    row_h, head_h, strip_h = 56, 150, 120
    n = max(1, len(recent))
    H = 24 + head_h + 26 + strip_h + 8 + 52 + row_h * (n + 1) + 44
    img = _vgrad((W, H), (252, 250, 254), (238, 236, 244)).convert('RGB')
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([24, 24, W-24, H-24], radius=24, fill=(255, 255, 255), outline=(215, 210, 228), width=2)
    d.rounded_rectangle([24, 24, W-24, 24+head_h], radius=24, fill=(126, 96, 191))
    d.rectangle([24, 24+head_h-30, W-24, 24+head_h], fill=(126, 96, 191))
    d.text((64, 70), str(p['nick']), font=F(46, True), fill=(255, 255, 255))
    d.text((64, 128), 'UID %s' % p['uid'], font=F(24), fill=(228, 222, 245))
    d.text((280, 128), 'Lv.%d' % p.get('level', 0), font=F(24), fill=(255, 235, 160))
    if p.get('online'):
        d.ellipse([W-190, 76, W-168, 98], fill=(120, 235, 150))
        d.text((W-156, 87), '在线', font=F(24, True), fill=(255, 255, 255), anchor='lm')
    y0 = 24 + head_h + 26
    cells = [('总场次', p['total']), ('胜率', '%.1f%%' % p['winrate']),
             ('胜场', p['wins']), ('获赞', p['praise']), ('拥有角色', p['heroes'])]
    cw = (W - 48 - 40 - 4 * 16) / 5
    for i, (k, v) in enumerate(cells):
        x = 44 + i * (cw + 16)
        d.rounded_rectangle([x, y0, x + cw, y0 + strip_h - 20], radius=14, fill=(247, 245, 252), outline=(225, 220, 238), width=1)
        d.text((x + cw/2, y0 + 26), k, font=F(22), fill=(120, 112, 145), anchor='mm')
        d.text((x + cw/2, y0 + 68), str(v), font=F(36, True),
               fill=(110, 80, 200) if i == 1 else (45, 42, 60), anchor='mm')
    ty = y0 + strip_h + 8
    d.rectangle([44, ty, 208, ty + 40], fill=(75, 72, 88))
    d.text((60, ty + 20), '近期战绩', font=F(26, True), fill=(255, 255, 255), anchor='lm')
    d.text((W - 56, ty + 20), '最近 %d 场' % len(recent), font=F(22), fill=(140, 134, 158), anchor='rm')
    t_y = ty + 52
    d.text((80, t_y + row_h/2), '角色', font=F(24, True), fill=(95, 90, 115), anchor='lm')
    d.text((430, t_y + row_h/2), '伤害', font=F(24, True), fill=(95, 90, 115), anchor='mm')
    d.text((620, t_y + row_h/2), '转账', font=F(24, True), fill=(95, 90, 115), anchor='mm')
    d.text((W - 80, t_y + row_h/2), '输赢', font=F(24, True), fill=(95, 90, 115), anchor='rm')
    d.line([56, t_y + row_h, W - 56, t_y + row_h], fill=(228, 224, 236), width=2)
    for i, r in enumerate(recent[:10]):
        ry = t_y + row_h * (i + 1)
        if i % 2 == 0:
            d.rectangle([56, ry, W - 56, ry + row_h], fill=(248, 246, 252))
        d.text((80, ry + row_h/2), str(r.get('hero', '?')), font=F(26, True), fill=(52, 48, 70), anchor='lm')
        d.text((430, ry + row_h/2), _num(r.get('damage')), font=F(26), fill=(70, 66, 88), anchor='mm')
        d.text((620, ry + row_h/2), _num(r.get('transfer')), font=F(26), fill=(70, 66, 88), anchor='mm')
        bw = 92
        bx = W - 80 - bw
        if r.get('win'):
            d.rounded_rectangle([bx, ry + 10, bx + bw, ry + row_h - 10], radius=18, fill=(86, 200, 130))
            d.text((bx + bw/2, ry + row_h/2), '胜', font=F(26, True), fill=(255, 255, 255), anchor='mm')
        else:
            d.rounded_rectangle([bx, ry + 10, bx + bw, ry + row_h - 10], radius=18, fill=(196, 198, 210))
            d.text((bx + bw/2, ry + row_h/2), '负', font=F(26, True), fill=(255, 255, 255), anchor='mm')
    d.line([56, t_y + row_h * (n + 1), W - 56, t_y + row_h * (n + 1)], fill=(228, 224, 236), width=2)
    return img

def render_stats_card_png(p, recent):
    img = render_stats_card(p, recent)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
