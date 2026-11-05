import base64
import contextlib
import importlib.util
import io
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

import bot_ext
from stats_query import StatsQuery
from stats_report import build_report, format_report
from qq_media import upload_image, MediaUploadError, error_code
from test_bot import bot, message


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_group_upload_needs_no_public_url(self):
        http = types.SimpleNamespace(request=AsyncMock(return_value={'file_info': 'group-media', 'ttl': 300}))
        media = await upload_image(types.SimpleNamespace(_http=http), 'group', b'png', group=True)
        route = http.request.call_args.args[0]
        payload = http.request.call_args.kwargs['json']
        self.assertEqual(route.path, '/v2/groups/{group_openid}/files')
        self.assertEqual(route.parameters, {'group_openid': 'group'})
        self.assertEqual(payload['file_name'], 'stats.png')
        self.assertEqual(base64.b64decode(payload['file_data']), b'png')
        self.assertFalse(payload['srv_send_msg'])
        self.assertNotIn('url', payload)
        self.assertEqual(media, {'file_info': 'group-media'})

    async def test_url_failure_falls_back_to_direct_c2c_upload(self):
        http = types.SimpleNamespace(request=AsyncMock(return_value={'file_info': 'direct'}))
        api = types.SimpleNamespace(_http=http, post_c2c_file=AsyncMock(side_effect=RuntimeError('secret')))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            media = await upload_image(api, 'user', b'png', url='https://invalid/cards.png')
        self.assertEqual(media, {'file_info': 'direct'})
        self.assertEqual(http.request.call_args.args[0].path, '/v2/users/{openid}/files')
        self.assertNotIn('secret', output.getvalue())

    async def test_url_success_does_not_upload_again(self):
        api = types.SimpleNamespace(post_c2c_file=AsyncMock(return_value={'file_info': 'url-media'}),
                                    _http=types.SimpleNamespace(request=AsyncMock()))
        self.assertEqual(await upload_image(api, 'user', b'png', url='https://cards/image.png'),
                         {'file_info': 'url-media'})
        api._http.request.assert_not_called()

    async def test_missing_file_info_is_not_treated_as_success(self):
        api = types.SimpleNamespace(_http=types.SimpleNamespace(request=AsyncMock(return_value=None)))
        with self.assertRaises(MediaUploadError):
            await upload_image(api, 'user', b'png')

    async def test_direct_upload_size_is_bounded(self):
        api = types.SimpleNamespace(_http=types.SimpleNamespace(request=AsyncMock()))
        with self.assertRaises(MediaUploadError):
            await upload_image(api, 'user', b'x' * (5 * 1024 * 1024))
        api._http.request.assert_not_called()

    async def test_reply_sends_picture_without_card_base(self):
        client = bot.MyClient()
        client.api = types.SimpleNamespace(
            _http=types.SimpleNamespace(request=AsyncMock(return_value={'file_info': 'direct'})),
            post_group_message=AsyncMock(return_value={'id': 'sent'}))
        msg = message('alice')
        with patch.object(bot, 'CARD_BASE', ''), patch.object(bot, 'save_card') as save:
            await client._reply(msg, 'group', bot.Reply('text', b'png'), group=True)
        save.assert_not_called()
        msg.reply.assert_not_called()
        self.assertEqual(client.api.post_group_message.call_args.kwargs['media'], {'file_info': 'direct'})

    async def test_send_failure_uses_new_sequence_for_text(self):
        client = bot.MyClient()
        client.api = types.SimpleNamespace(post_c2c_message=AsyncMock(side_effect=TimeoutError()))
        msg = message('alice')
        with patch.object(bot, 'CARD_BASE', ''), patch.object(bot, 'upload_image', return_value={'file_info':'data'}):
            await client._reply(msg, 'alice', bot.Reply('text', b'png'))
        self.assertEqual(msg.reply.call_args.kwargs['msg_seq'], 2)
        self.assertIn('text', msg.reply.call_args.kwargs['content'])

    def test_error_logging_extracts_only_platform_code(self):
        error = RuntimeError()
        error.msgs = '{"code":850026,"message":"secret","token":"do not print"}'
        self.assertEqual(error_code(error), '850026')


class EnrichmentRegressionTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'uid': 1234567, 'recent': [
            {'hero': '芬妮', 'mode_id': 2, 'rank': 1, 'replay': '1234567890123456'}]}

    def test_text_and_image_both_use_replay_metrics(self):
        with patch.object(bot_ext, 'fetch_replay_stats', return_value={
                '1234567': {'stats': {'伤害':120, '转账':32}}}) as fetch:
            result = StatsQuery(Mock(), images=False).present(self.profile)
        fetch.assert_called_once_with('1234567890123456')
        self.assertIn('场均伤害 120（1 场）', result.text)
        self.assertIn('场均转账 32（1 场）', result.text)
        self.assertIsNone(result.image)

    def test_no_url_still_enriches_and_renders(self):
        with patch.object(bot, 'mgr') as manager, patch.object(bot, 'CARD_BASE', ''), \
                patch.object(bot_ext, 'fetch_replay_stats', return_value={
                    '1234567': {'stats': {'伤害':120, '转账':32}}}), \
                patch('bot_viz.render_report_png', return_value=b'png'):
            manager.get_profile.return_value = (self.profile, '')
            result = bot.profile_of('alice')
        self.assertEqual(result.image, b'png')
        self.assertIn('场均伤害 120（1 场）', result.text)

    def test_missing_replay_id_is_explained(self):
        profile = dict(self.profile, recent=[{'hero': '芬妮', 'mode_id': 2, 'rank': 1}])
        with patch.object(bot_ext, 'fetch_replay_stats') as fetch:
            result = StatsQuery(Mock(), images=False).present(profile)
        fetch.assert_not_called()
        self.assertIn('未提供有效回放号', result.text)

    def test_parse_failure_is_explained_and_does_not_drop_record(self):
        with patch.object(bot_ext, 'fetch_replay_stats', side_effect=ValueError('private details')):
            result = StatsQuery(Mock(), images=False).present(self.profile)
        self.assertIn('回放指标暂不可用', result.text)
        self.assertIn('匹配 1 场', result.text)

    def test_font_failure_preserves_enriched_text(self):
        with patch.object(bot_ext, 'fetch_replay_stats', return_value={
                '1234567': {'stats': {'伤害':120, '转账':32}}}), \
                patch('bot_viz.render_report_png', side_effect=RuntimeError('font missing')):
            result = StatsQuery(Mock(), images=True).present(self.profile)
        self.assertIsNone(result.image)
        self.assertIn('卡片生成失败', result.text)
        self.assertIn('场均伤害 120', result.text)

    def test_diagnostics_never_prints_credentials_or_url(self):
        from tools.diagnose_cards import environment_status
        output = str(environment_status({'QQ_SECRET':'private', 'QQ_APPID':'private-id',
                                        'CARD_BASE_URL':'https://private-domain:8420'}))
        self.assertNotIn('private', output)
        self.assertIn('set', output)

class EndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_and_png_renderer_without_public_url(self):
        import bot_viz
        if not bot_viz._FP_REG or not bot_viz._FP_BOLD:
            self.skipTest('A CJK font is required for the real rendering integration test')
        from botpy.api import BotAPI
        profile = {'uid':1234567, 'nick':'测试玩家', 'level':48, 'recent':[
            {'hero':'芬妮','mode_id':2,'mode':'合作挑战','rank':1,'replay':'1234567890123456'}]}
        requests = []
        async def request(route, **kwargs):
            requests.append((route, kwargs['json']))
            return {'file_info':'real-sdk-media'} if route.path.endswith('/files') else {'id':'sent'}
        client = bot.MyClient()
        client.api = BotAPI(types.SimpleNamespace(request=request))
        with patch.object(bot, 'mgr') as manager, patch.object(bot, 'CARD_BASE', ''), \
                patch.object(bot_ext, 'fetch_replay_stats', return_value={
                    '1234567': {'stats': {'伤害':120,'转账':32}}}):
            manager.resolve_member.return_value = 'alice'
            manager.get_profile.return_value = (profile, '')
            result = await client._dispatch(bot.handle_group, '/atp me', 'member')
            msg = message('alice')
            await client._reply(msg, 'group', result, group=True)
        self.assertEqual(len(requests), 2)
        self.assertTrue(base64.b64decode(requests[0][1]['file_data']).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(requests[1][1]['media'], {'file_info':'real-sdk-media'})
        self.assertEqual(requests[1][1]['group_openid'], 'group')
        self.assertIn('场均伤害 120（1 场）', result.text)
        msg.reply.assert_not_called()

    async def test_missing_render_dependency_still_returns_enriched_text(self):
        import sys
        profile={'uid':1234567,'recent':[{'hero':'芬妮','mode_id':2,'rank':1,'replay':'1234567890123456'}]}
        with patch.object(bot_ext, 'fetch_replay_stats', return_value={
                '1234567': {'stats': {'伤害':120,'转账':32}}}), patch.dict(sys.modules, {'bot_viz': None}):
            result = StatsQuery(Mock(), images=True).present(profile)
        self.assertIsNone(result.image)
        self.assertIn('卡片生成失败', result.text)
        self.assertIn('场均伤害 120（1 场）', result.text)
