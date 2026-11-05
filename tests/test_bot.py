"""No QQ credentials or game service required: python -m unittest discover -s tests -v."""
import asyncio
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Load the real entry point with external services replaced before import.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bot_core
import bot_ext
from astral import sdk_login
spec = importlib.util.spec_from_file_location('bot_under_test', ROOT / 'qq_bot.py')
bot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bot
with patch.dict(sys.modules, {'qqbot': types.SimpleNamespace(Client=object)}), \
        patch.object(bot_core, 'AccountManager', return_value=Mock()):
    spec.loader.exec_module(bot)


def message(uid, text='/我的'):
    return types.SimpleNamespace(author=types.SimpleNamespace(user_openid=uid),
                                 content=text, id=uid, reply=AsyncMock())


class MessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_interleaved_uploads_keep_recipient_and_image(self):
        client = bot.MyClient()
        entered, release = asyncio.Event(), asyncio.Event()

        async def upload(**kw):
            if kw['openid'] == 'alice':
                entered.set()
                await release.wait()
            return kw['url']

        client.api = types.SimpleNamespace(post_c2c_file=AsyncMock(side_effect=upload),
                                           post_c2c_message=AsyncMock())
        def handle(text, uid):
            return bot.Reply(uid, uid.encode())
        with patch.object(bot, 'handle_private', side_effect=handle), \
                patch.object(bot, 'CARD_BASE', 'https://cards.invalid'), \
                patch.object(bot, 'save_card', side_effect=lambda png: png.decode()):
            first = asyncio.create_task(client.on_c2c_message_create(message('alice')))
            await asyncio.wait_for(entered.wait(), 2)
            await client.on_c2c_message_create(message('bob'))
            release.set()
            await first
        pairs = [(c.kwargs['openid'], c.kwargs['media'])
                 for c in client.api.post_c2c_message.call_args_list]
        self.assertCountEqual(pairs, [('alice', 'alice'), ('bob', 'bob')])

    async def test_busy_limit_and_event_loop_remains_responsive(self):
        client = bot.MyClient()
        release = threading.Event()
        def slow():
            release.wait(3)
            return 'ok'
        tasks = [asyncio.create_task(client._dispatch(slow)) for _ in range(4)]
        try:
            await asyncio.sleep(.05)
            self.assertEqual(client._active_commands, 4)
            self.assertIn('稍后', (await client._dispatch(slow)).text)
        finally:
            release.set()
            await asyncio.gather(*tasks)
        self.assertEqual(client._active_commands, 0)

    async def test_cancel_does_not_free_running_worker_slot(self):
        client = bot.MyClient()
        entered, release = threading.Event(), threading.Event()
        def slow():
            entered.set()
            release.wait(3)
            return 'ok'
        task = asyncio.create_task(client._dispatch(slow))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(client._active_commands, 1)
        finally:
            release.set()
        for _ in range(100):
            if client._active_commands == 0:
                break
            await asyncio.sleep(.01)
        self.assertEqual(client._active_commands, 0)

    async def test_image_failure_falls_back_to_text(self):
        client = bot.MyClient()
        client.api = types.SimpleNamespace(post_c2c_file=AsyncMock(side_effect=OSError('secret')))
        msg = message('alice')
        output = io.StringIO()
        with patch.object(bot, 'CARD_BASE', 'https://cards.invalid'), \
                patch.object(bot, 'save_card', return_value='url'), contextlib.redirect_stdout(output):
            await client._reply(msg, 'alice', bot.Reply('fallback', b'image'))
        msg.reply.assert_awaited_once_with(content='fallback')
        self.assertNotIn('secret', output.getvalue())

    async def test_private_logs_do_not_include_credentials(self):
        client = bot.MyClient()
        msg = message('sensitive-openid', '/验证码 123456')
        output = io.StringIO()
        with patch.object(bot, 'handle_private', return_value='ok') as handle, \
                contextlib.redirect_stdout(output):
            await client.on_c2c_message_create(msg)
        handle.assert_called_once_with('/验证码 123456', 'sensitive-openid')
        self.assertNotIn('123456', output.getvalue())
        self.assertNotIn('sensitive-openid', output.getvalue())

    async def test_missing_identity_is_ignored(self):
        client = bot.MyClient()
        with patch.object(bot, 'handle_private') as handle:
            await client.on_c2c_message_create(message(''))
        handle.assert_not_called()

    async def test_command_exception_releases_capacity(self):
        client = bot.MyClient()
        def fail():
            raise RuntimeError('private details')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            reply = await client._dispatch(fail)
        self.assertIn('处理失败', reply.text)
        self.assertEqual(client._active_commands, 0)
        self.assertNotIn('private details', output.getvalue())


class StorageTests(unittest.TestCase):
    def test_private_commands_pass_explicit_identity(self):
        with patch.object(bot, 'mgr') as mgr:
            bot.handle_private('/登录 13800138000', 'alice')
            bot.handle_private('/验证码 123456', 'bob')
            mgr.send_code.assert_called_once_with('alice', '13800138000')
            mgr.login_with_code.assert_called_once_with('bob', '123456')

    def test_no_card_configuration_skips_expensive_render(self):
        with patch.object(bot, 'CARD_BASE', ''), patch.object(bot, 'mgr') as mgr, \
                patch.object(bot, 'format_profile', return_value='text'), \
                patch.object(bot.bot_ext, 'card_from_profile') as render:
            mgr.get_profile.return_value = ({'uid': 1}, '')
            self.assertEqual(bot.profile_of('alice'), bot.Reply('text'))
            render.assert_not_called()

    def test_concurrent_card_files_are_unique(self):
        with tempfile.TemporaryDirectory() as d, patch.object(bot, 'CARD_DIR', d):
            with ThreadPoolExecutor(max_workers=8) as pool:
                urls = list(pool.map(bot.save_card, [str(i).encode() for i in range(40)]))
            self.assertEqual(len(set(urls)), 40)
            self.assertEqual(len(list(Path(d).glob('*.png'))), 40)
            self.assertEqual({p.read_bytes() for p in Path(d).glob('*.png')},
                             {str(i).encode() for i in range(40)})

    def test_sdk_login_archives_exclude_tokens_and_personal_data(self):
        response = {'ret': '1', 'content': {'authorize_code': 'SID_SECRET',
                    'data': {'accessToken': 'TOKEN_SECRET'}, 'phone': '13800138000'}}
        with tempfile.TemporaryDirectory() as d, patch.object(sdk_login, 'SAVE_DIR', Path(d)), \
                patch.object(sdk_login, 'authorize', return_value=response):
            sid, result = sdk_login.phone_login('13800138000', '987654', do_init=False)
            self.assertEqual(sid, 'SID_SECRET')
            self.assertIs(result, response)
            sdk_login.token_login('INPUT_TOKEN_SECRET', do_init=False)
            sdk_login._save('sendCode', 'masked', {'init_resp': response,
                            'tried': [{'resp': response}]})
            archives = ''.join(p.read_text(encoding='utf-8') for p in Path(d).glob('*.json'))
        for secret in ['SID_SECRET', 'TOKEN_SECRET', '13800138000', '987654', 'INPUT_TOKEN_SECRET']:
            self.assertNotIn(secret, archives)
        self.assertIn('has_content', archives)

    def test_account_and_query_operations_share_lock(self):
        mgr = types.SimpleNamespace(_lock=threading.RLock())
        entered, release, queried = threading.Event(), threading.Event(), threading.Event()
        @bot_core.synchronized
        def login(manager):
            entered.set()
            release.wait(3)
        @bot_ext.manager_locked
        def query(manager):
            queried.set()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(login, mgr)
            self.assertTrue(entered.wait(2))
            second = pool.submit(query, mgr)
            try:
                self.assertFalse(queried.wait(.05))
            finally:
                release.set()
            first.result()
            second.result()
        self.assertTrue(queried.is_set())

    def test_replay_cache_access_is_serialized_for_same_id(self):
        entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        count = 0
        def fetch(rid):
            nonlocal count
            count += 1
            if count == 1:
                entered.set()
                release.wait(3)
            else:
                second_entered.set()
            return rid
        with patch.object(bot_ext, 'original', return_value={'fetch_replay_stats': fetch}), \
                ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(bot_ext.fetch_replay_stats, '1234567890123456')
            self.assertTrue(entered.wait(2))
            second = pool.submit(bot_ext.fetch_replay_stats, '1234567890123456')
            try:
                self.assertFalse(second_entered.wait(.05))
            finally:
                release.set()
            self.assertEqual(first.result(), second.result())
        self.assertTrue(second_entered.is_set())

    def test_heartbeat_and_query_send_sequences_match_wire_order(self):
        from astral.client import AstralClient
        from astral import frame
        client = AstralClient('unused', 0)
        client.sock = Mock()
        sequence = []
        client.sock.sendall.side_effect = sequence.append
        with patch.object(frame, 'encode', side_effect=lambda cmd, body, **kw: kw['upsn']), \
                ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: client.send(5003, b''), range(200)))
        self.assertEqual(sequence, list(range(1, 201)))


if __name__ == '__main__':
    unittest.main()
