# -*- coding: utf-8 -*-
"""评分插件挂载补丁：在 astral-bot-new 目录运行 python3 apply_rate.py
qq_bot.py 仅两处改动：插件挂载元组 +rate_glue；帮助文本加一行 /评分。
带唯一性校验，重复执行会安全报错。本文件是唯一改动点。"""
import pathlib

p = pathlib.Path("qq_bot.py")
t = p.read_text(encoding="utf-8")

OLD_PLUG = 'for _plug in ("review_glue", "replay_glue"):'
NEW_PLUG = 'for _plug in ("review_glue", "replay_glue", "rate_glue"):'
assert t.count(OLD_PLUG) == 1, "挂载锚点缺失或不唯一（可能已打过）"
t = t.replace(OLD_PLUG, NEW_PLUG, 1)

OLD_HELP = "    '· /回放 16位回放号 — 单局四人详细战报\\n'"
NEW_HELP = ("    '· /回放 16位回放号 — 单局四人详细战报\\n'\n"
            "    '· /评分 16位回放号 — 四人表现评分（试运营）\\n'")
assert t.count(OLD_HELP) == 1, "帮助锚点缺失或不唯一（可能已打过）"
t = t.replace(OLD_HELP, NEW_HELP, 1)

p.write_text(t, encoding="utf-8")
print("patched: qq_bot.py（挂载元组 +rate_glue；帮助 +/评分，共两处）")
