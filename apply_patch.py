# -*- coding: utf-8 -*-
"""网页登录补丁：在 astral-bot-new 目录里运行  python3 apply_patch.py
给 qq_bot.py / bot_core.py 打精确补丁（带唯一性校验，重复执行会安全报错）。"""
import pathlib


def patch(path, pairs):
    p = pathlib.Path(path)
    t = p.read_text(encoding='utf-8')
    for old, new in pairs:
        assert old in t, '未找到目标文本: %r' % old[:60]
        assert t.count(old) == 1, '目标文本不唯一（可能已打过补丁）: %r' % old[:60]
        t = t.replace(old, new)
    p.write_text(t, encoding='utf-8')
    print('patched:', path)


OLD_HELP = ("    '一、登录（每人一次，务必私聊操作）\\n'\n"
            "    '1. 私聊我发：/登录 你的手机号\\n'\n"
            "    '2. 收到短信验证码后私聊发：/验证码 123456\\n'\n"
            "    '⚠️ 不要在群里发手机号和验证码！\\n'")
NEW_HELP = ("    '一、登录（每人一次，群里完成）\\n'\n"
            "    '1. 群里 @我 发：/登录\\n'\n"
            "    '2. 点机器人回复的链接，在网页里完成手机号+验证码\\n'\n"
            "    '⚠️ 不要在群里发手机号！（管理员可私聊 /登录 手机号 → /验证码 码）\\n'")

patch('qq_bot.py', [
    ("import bot_ext\n", "import bot_ext\nimport bot_weblogin\n"),
    (OLD_HELP, NEW_HELP),
    ("    handler = functools.partial(SimpleHTTPRequestHandler, directory=CARD_DIR)",
     "    handler = bot_weblogin.make_handler(CARD_DIR, mgr)"),
    ("    stats = stats_command(text, mgr.resolve_member(member_openid))\n",
     "    if text in ('/登录', '登录'):\n"
     "        if not CARD_BASE:\n"
     "            return '网页登录未配置（缺 CARD_BASE_URL），请联系管理员。'\n"
     "        token = bot_weblogin.issue_token(member_openid)\n"
     "        return '点下面链接登录你的游戏账号（10分钟有效，勿转发他人）：\\n%s/login?t=%s' % (CARD_BASE.rstrip('/'), token)\n"
     "    if re.match(r'^/登录\\s+\\d', text):\n"
     "        return '为保护隐私，请勿在群里发手机号！请发 /登录 获取网页登录链接。'\n"
     "    stats = stats_command(text, mgr.resolve_member(member_openid) or member_openid)\n"),
])

patch('bot_core.py', [
    ("return None, '还没登录。私聊我发：/登录 你的手机号，再发：/验证码 6位数字。'",
     "return None, '还没登录。群里 @我 发 /登录 获取网页登录链接（或私聊 /登录 手机号）。'"),
])



# tests/test_stats.py：把两条断言旧行为的测试更新为新行为（网页登录模型）
patch('tests/test_stats.py', [
    ("        query.assert_called_once_with('1234567', None, 'hero', '芬妮', 'pve')",
     "        query.assert_called_once_with('1234567', 'member', 'hero', '芬妮', 'pve')"),
    ('''    def test_unbound_group_self_query_is_rejected(self):
        with patch.object(bot, 'mgr') as manager, patch.object(bot, 'profile_of') as query:
            manager.resolve_member.return_value = None
            self.assertIn('绑定', bot.handle_group('/我的 近期', 'member'))
        query.assert_not_called()''',
     '''    def test_unbound_group_self_query_uses_member_identity(self):
        # 网页登录模型：未绑定群友用群身份直接查（票存于 member_openid 槽位）
        with patch.object(bot, 'mgr') as manager, patch.object(bot, 'profile_of', return_value='ok') as query:
            manager.resolve_member.return_value = None
            self.assertEqual(bot.handle_group('/我的 近期', 'member'), 'ok')
        query.assert_called_once_with('member', 'recent', '', 'pve')'''),
])

print('全部补丁完成。重启生效：sudo systemctl restart astral-bot')
