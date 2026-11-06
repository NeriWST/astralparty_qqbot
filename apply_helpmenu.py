# -*- coding: utf-8 -*-
"""帮助菜单补丁（中文指令版）：python3 apply_helpmenu.py
只重写 /帮助（HELP_TEXT，中文指令部分）；/atp help 由协作者维护，本补丁不碰。
前置：已打网页登录补丁(apply_patch.py)与解绑补丁(apply_unbind.py)。
用括号配对定位 HELP_TEXT 整块替换，与文件上下文无关。"""
import pathlib


def replace_block(path, start_marker, new_block):
    p = pathlib.Path(path)
    t = p.read_text(encoding="utf-8")
    assert t.count(start_marker) == 1, "起点缺失或不唯一: %r" % start_marker
    i = t.find(start_marker)
    k = i + len(start_marker)
    depth = 1
    while depth:
        ch = t[k]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        k += 1
    p.write_text(t[:i] + new_block + t[k:], encoding="utf-8")
    print("patched:", path)

ESC = chr(92)   # 反斜杠
LF = chr(10)    # 换行
LINES = [
    "【星趴战绩机器人】",
    "星引擎 Party（吉星派对）战绩查询。",
    "",
    "登录系（需要你的游戏账号）",
    "· /登录 — 首次使用：群里 @我 发 /登录，点链接在网页完成手机号+验证码",
    "· /我的 — 我的近10场PVE战绩卡片",
    "· /解绑 — 解除当前绑定关系",
    "· /atp help — 更多战绩查询指令",
    "",
    "查询系（无需登录）",
    "· /查 游戏UID — 查任意玩家公开战绩",
    "· /回放 16位回放号 — 单局四人详细战报",
    "· /手牌 观战码 — PVE 对局实时手牌快照",
    "",
    "⚠️⚠️ 顶号警告 ⚠️⚠️",
    "/我的 会登录你的游戏账号——查询瞬间",
    "如果你正在游戏里，会被当场踢下线！",
    "千万不要边玩边查，打完这局再查！",
]
parts = []
for idx, line in enumerate(LINES):
    tail = ESC + "n" if idx < len(LINES) - 1 else ""
    parts.append("    " + chr(39) + line + tail + chr(39))
HELP_NEW = "HELP_TEXT = (" + LF + LF.join(parts) + LF + ")"

replace_block("qq_bot.py", "HELP_TEXT = (", HELP_NEW)
print("帮助菜单补丁完成（未触碰 /atp help）。重启生效：sudo systemctl restart astral-bot")