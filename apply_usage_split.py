# -*- coding: utf-8 -*-
"""区分补丁：apply_usage_card.py 之后运行 python3 apply_usage_split.py
效果：只有中文 /我的（无参数）用角色使用排行卡；/atp me、/我的 近期、/我的 角色 X 均保持原卡。
原理：profile_of 加 usage_card 标记挂到 StatsQuery 实例，present() 用 getattr 守卫。"""
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


patch("qq_bot.py", [
    ("def profile_of(qq_uid, view=\'overview\', hero=\'\', battle_type=\'pve\'):\n"
     "    result = StatsQuery(mgr, images=bool(CARD_BASE)).mine(qq_uid, view, hero, battle_type)\n"
     "    return Reply(result.text, result.image)\n",
     "def profile_of(qq_uid, view=\'overview\', hero=\'\', battle_type=\'pve\', usage_card=False):\n"
     "    query = StatsQuery(mgr, images=bool(CARD_BASE))\n"
     "    query.usage_card = usage_card   # 中文 /我的 专用：角色使用排行卡；/atp me 保持原卡\n"
     "    result = query.mine(qq_uid, view, hero, battle_type)\n"
     "    return Reply(result.text, result.image)\n"),
    ("        return profile_of(requester, view, hero, battle_type)\n"
     "    return do_query(target, requester, view, hero, battle_type)\n",
     "        return profile_of(requester, view, hero, battle_type,\n"
     "                          usage_card=(tokens[0] in (\'/我的\', \'我的\') and view == \'overview\'))\n"
     "    return do_query(target, requester, view, hero, battle_type)\n"),
])

patch("stats_query.py", [
    ("                if profile.get(\"usage\"):\n",
     "                if getattr(self, \'usage_card\', False) and profile.get(\"usage\"):\n"),
])

print("区分补丁完成。重启生效：sudo systemctl restart astral-bot")
