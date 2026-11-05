# -*- coding: utf-8 -*-
"""解绑补丁：在 astral-bot-new 目录运行  python3 apply_unbind.py
（需先打完网页登录补丁）新增群指令 /解绑：删除 member->user 绑定，
user 名下的游戏票保留，可随时重新绑定找回。"""
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


patch('bot_core.py', [
    ("    def resolve_member(self, member_openid):\n"
     "        return self.bindings.get(member_openid)\n",
     "    def resolve_member(self, member_openid):\n"
     "        return self.bindings.get(member_openid)\n"
     "\n"
     "    @synchronized\n"
     "    def unbind_member(self, member_openid):\n"
     "        \"\"\"解除群身份绑定（/解绑）：删除 member->user 映射；user 名下的票保留，可重新绑定找回。\"\"\"\n"
     "        if member_openid not in self.bindings:\n"
     "            return False\n"
     "        self.bindings.pop(member_openid, None)\n"
     "        self._save_bindings()\n"
     "        return True\n"),
])

patch('qq_bot.py', [
    ("    if text in ('/绑定', '绑定'):\n"
     "        code = mgr.make_bind_code(member_openid)\n"
     "        return '你的绑定码：%s\\n私聊我发：/绑定 %s（10分钟内有效）' % (code, code)\n",
     "    if text in ('/绑定', '绑定'):\n"
     "        code = mgr.make_bind_code(member_openid)\n"
     "        return '你的绑定码：%s\\n私聊我发：/绑定 %s（10分钟内有效）' % (code, code)\n"
     "    if text in ('/解绑', '解绑'):\n"
     "        if mgr.unbind_member(member_openid):\n"
     "            return '已解绑 ✅ 之后 /我的 将使用你本人在本群网页登录（/登录）的账号。'\n"
     "        return '你当前没有绑定关系，无需解绑。'\n"),
    ("    '2. 私聊我发：/绑定 123456（10分钟内有效）\\n'\n"
     "    '\\n'",
     "    '2. 私聊我发：/绑定 123456（10分钟内有效）\\n'\n"
     "    '· 解除绑定：群里 @我 发 /解绑（/我的 将改用你群身份网页登录的号）\\n'\n"
     "    '\\n'"),
])

patch('tests/test_stats.py', [
    ("        query.assert_called_once_with('member', 'recent', '', 'pve')\n"
     "\n"
     "    def test_invalid_selector_provides_usage(self):",
     "        query.assert_called_once_with('member', 'recent', '', 'pve')\n"
     "\n"
     "    def test_group_unbind_removes_binding(self):\n"
     "        with patch.object(bot, 'mgr') as manager:\n"
     "            manager.unbind_member.return_value = True\n"
     "            self.assertIn('已解绑', bot.handle_group('/解绑', 'member'))\n"
     "        manager.unbind_member.assert_called_once_with('member')\n"
     "\n"
     "    def test_group_unbind_without_binding(self):\n"
     "        with patch.object(bot, 'mgr') as manager:\n"
     "            manager.unbind_member.return_value = False\n"
     "            self.assertIn('无需解绑', bot.handle_group('/解绑', 'member'))\n"
     "\n"
     "    def test_invalid_selector_provides_usage(self):"),
])

print('解绑补丁完成。重启生效：sudo systemctl restart astral-bot')
