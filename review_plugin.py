# -*- coding: utf-8 -*-
"""复盘事件挖掘：在原版 review_build 之上补充逐回合事件（升星/筹码候选/购买/任务）。"""
import bisect
import json
import os
import urllib.request

from astral.replay import parse_replay
from bot_viz import INK, MUTED, PURPLE, GREEN
import review_build as rb

ROOT = os.path.dirname(os.path.abspath(__file__))
CHIP_NAME = {}
QUALITY_COLOR = {"蓝": "#4C7DD9", "紫": "#9B59B6", "金": "#D4A017",
                 "R": "#4C7DD9", "SR": "#9B59B6", "SSR": "#D4A017",
                 "初级": "#4C7DD9", "中级": "#9B59B6", "高级": "#D4A017"}


def _quality_color(q):
    return QUALITY_COLOR.get(str(q), MUTED)
try:
    _cs = json.loads(open(os.path.join(ROOT, "assets", "data", "chips.json"),
                          encoding="utf-8").read())
    CHIP_NAME = {int(c["id"]): c["name"] for c in _cs}
except Exception:
    pass


def download_replay(rid, dest_dir):
    """回放原始字节缓存到 dest_dir/replay.bin（重复查询免下载）。"""
    os.makedirs(dest_dir, exist_ok=True)
    p = os.path.join(dest_dir, "replay.bin")
    if not os.path.exists(p):
        url = "https://sereplaycn.feimogames.com/prod/" + rid
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(p, "wb") as f:
            f.write(r.read())
    return open(p, "rb").read()


def _round_of(rp, uid, frame):
    return rb._round_at(rp, uid, frame)


def _names(ids):
    return [CHIP_NAME.get(int(i), "筹码#%s" % i) for i in ids]


def build_full(rid, cache_dir):
    """返回 (review_dict, cache_dir)。players[i]['events'] = {round: [str,...]}"""
    src = download_replay(rid, cache_dir)
    rp = parse_replay(src)
    review = rb.build_review(src, rid)
    review["replay_id"] = rid

    for p in review["players"]:
        uid = p["uid"]
        events = {}
        lv_frames = set()
        mis_frames = set()
        # 升星（帧号留作筹码来源判定）
        mis_frames = set()
        for fr, lv in rb._level_ups(rp, uid).items():
            lv_frames.add(fr)
            r = _round_of(rp, uid, fr)
            events.setdefault(r, []).append("★升星 %d星→%d星" % (lv - 1, lv))
        # 任务完成（复用引擎的 _mission_flips，帧→任务ID）
        for fr, mids in rb._mission_flips(rp).items():
            for mid in mids:
                mis_frames.add(fr)
                events.setdefault(_round_of(rp, uid, fr), []).append("◆完成任务 #%d" % mid)
        # 筹码事件：直接消费原版引擎 chip_events（成员制 picked_index，与原版 100% 一致）
        SRC_LABEL = {"shop": "商店", "star": "升星", "task": "任务", "cycle": "循环", "unknown": "?"}
        for ev in (p.get("chip_events") or []):
            cands = []
            for cid, nm in zip(ev.get("candidates") or [], ev.get("candidates_name") or []):
                try:
                    q = rb.chip_quality(cid)
                except Exception:
                    q = ""
                cands.append((nm, _quality_color(q)))
            entry = {"kind": "chip", "src": SRC_LABEL.get(ev.get("source"), "?"),
                     "cands": cands, "chosen": None,
                     "price": ev.get("price"), "refresh": ev.get("refresh", 0)}
            pi = ev.get("picked_index", -1)
            cands_raw = ev.get("candidates") or []
            names_raw = ev.get("candidates_name") or []
            if 0 <= pi < len(cands_raw):
                q = ""
                try:
                    q = rb.chip_quality(cands_raw[pi])
                except Exception:
                    pass
                entry["chosen"] = (names_raw[pi], _quality_color(q) if q else INK)
            events.setdefault(ev.get("round") or 0, []).append(entry)
        p["events"] = events
    return review
