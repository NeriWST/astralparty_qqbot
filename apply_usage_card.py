# -*- coding: utf-8 -*-
"""角色使用排行卡片补丁：在 astral-bot-new 目录运行 python3 apply_usage_card.py
/我的 配图从"最近10场"换成"角色使用次数排行"（生涯 usage，格式与战绩卡片一致）。
有 usage 用新卡；公开查询等无 usage 场景自动回退原卡片。唯一性校验防重复打。"""
import pathlib


def patch(path, pairs):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in t, "未找到目标文本: %r" % old[:60]
        assert t.count(old) == 1, "目标文本不唯一（可能已打过补丁）: %r" % old[:60]
        t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("patched:", path)


patch("stats_query.py", [
    ("        image = None\n"
     "        if self.images:\n"
     "            try:\n"
     "                from bot_viz import render_report_png\n"
     "                image = render_report_png(report)\n",
     "        image = None\n"
     "        if self.images:\n"
     "            try:\n"
     "                if profile.get(\"usage\"):\n"
     "                    from bot_usage import render_usage_card_png\n"
     "                    image = render_usage_card_png(profile)\n"
     "                else:\n"
     "                    from bot_viz import render_report_png\n"
     "                    image = render_report_png(report)\n"),
])

print("角色排行卡片补丁完成。重启生效：sudo systemctl restart astral-bot")
