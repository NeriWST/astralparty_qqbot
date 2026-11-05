# -*- coding: utf-8 -*-
"""QQ 接入层。私聊登录，群聊查战绩；/回放 回放号免登录战报。"""
import os, re

try:
    import qqbot
except ImportError:
    import botpy as qqbot

from bot_core import AccountManager, format_profile
import bot_ext

APP_ID = os.environ['QQ_APPID']
SECRET = os.environ['QQ_SECRET']

HELP_TEXT = (
    '【星趴战绩机器人 · 使用帮助】\n'
    '\n'
    '一、登录（每人一次，务必私聊操作）\n'
    '1. 私聊我发：/登录 你的手机号\n'
    '2. 收到短信验证码后私聊发：/验证码 123456\n'
    '⚠️ 不要在群里发手机号和验证码！\n'
    '\n'
    '二、绑定群身份（登录后做一次）\n'
    '1. 群里 @我 发：/绑定，会给你一个 6 位绑定码\n'
    '2. 私聊我发：/绑定 123456（10分钟内有效）\n'
    '\n'
    '三、查战绩\n'
    '· 群里：@我 发 /我的\n'
    '· 私聊：直接发 /我的\n'
    '· 查单局详细战报（免登录）：/回放 16位回放号\n'
    '· 查任意玩家（基础信息）：/查 游戏UID（6~7位数字）\n'
    '· 看队友实时手牌（仅PVE）：/手牌 观战码\n'    '\n'
    '⚠️ 重要提醒：机器人登录的是你的游戏账号，同账号同时只能\n'
    '一处在线——查战绩和玩游戏请错开，否则会把游戏顶下线！'
)

mgr = AccountManager()


CARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cards')
CARD_BASE = os.environ.get('CARD_BASE_URL', '')   # 开源版：必填，例 http://你的服务器IP:8420
CARD_PORT = int(os.environ.get('CARD_PORT', '8420'))


def _start_card_server():
    """内置迷你 HTTP 服务：把生成的卡片 PNG 暴露成公网 URL 供 QQ 平台抓图"""
    import threading
    import functools
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    os.makedirs(CARD_DIR, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=CARD_DIR)

    def run():
        try:
            httpd = ThreadingHTTPServer(('0.0.0.0', CARD_PORT), handler)
            print('[cards] 卡片图片服务已启动 :%d（目录 %s）' % (CARD_PORT, CARD_DIR))
            httpd.serve_forever()
        except Exception as e:
            print('[cards] 图片服务启动失败（将回退纯文字）:', e)

    threading.Thread(target=run, daemon=True).start()


def save_card(png: bytes) -> str:
    """保存卡片并返回公网 URL（文件名带时间戳，避免 QQ 缓存旧图）"""
    import time as _time
    os.makedirs(CARD_DIR, exist_ok=True)
    name = 'card_%d.png' % int(_time.time() * 1000)
    with open(os.path.join(CARD_DIR, name), 'wb') as f:
        f.write(png)
    try:
        files = sorted(os.listdir(CARD_DIR))
        for old_f in files[:-50]:
            os.remove(os.path.join(CARD_DIR, old_f))
    except Exception:
        pass
    return CARD_BASE.rstrip('/') + '/' + name


IMG_PAYLOAD = [None]   # /我的 时暂存卡片 PNG bytes（list 技巧免 global）


def _attach_card(p):
    try:
        IMG_PAYLOAD[0] = bot_ext.card_from_profile(p)
    except Exception as e:
        print('[card] 卡片生成失败（回退纯文字）:', e)
        IMG_PAYLOAD[0] = None


def profile_of(qq_uid):
    p, err = mgr.get_profile(qq_uid)
    if p is None:
        return err
    _attach_card(p)
    return format_profile(p)



def do_query(arg, requester=None):
    m = re.match(r'^(\d{5,10})$', arg)
    if not m:
        return '用法：/查 游戏UID（6~7 位数字，游戏内个人资料页可见）'
    try:
        res = bot_ext.query_uid(mgr, m.group(1), prefer_uid=requester)
        return bot_ext.format_uid_profile(m.group(1), res)
    except Exception as e:
        return '查询出错：%s' % e


def do_watch(arg):
    code = arg.strip()
    if not code:
        return '用法：/手牌 观战码（游戏内 PVE 房间界面的观战码）'
    try:
        res = bot_ext.watch_hands(mgr, code)
        return bot_ext.format_watch_hands(res)
    except Exception as e:
        return '观战出错：%s' % e


def do_replay(arg):
    m = re.match(r'^(\d{16})$', arg)
    if not m:
        return '用法：/回放 16位回放号（从游戏内对局记录复制）'
    return bot_ext.format_replay_stats(m.group(1))


def handle_private(text):
    """私聊指令（user_openid 标识身份）"""
    text = text.strip()
    if text in ('/帮助', '帮助', '/help', 'help'):
        return HELP_TEXT
    if text in ('/我的', '我的'):
        return profile_of(USER)
    m = re.match(r'^/登录\s+(\d{11})$', text)
    if m:
        try:
            return mgr.send_code(USER, m.group(1))
        except Exception as e:
            return '发送验证码失败：%s' % e
    m = re.match(r'^/验证码\s+(\d{4,8})$', text)
    if m:
        try:
            return mgr.login_with_code(USER, m.group(1))
        except Exception as e:
            return '登录失败：%s' % e
    m = re.match(r'^/绑定\s+(\d{6})$', text)
    if m:
        return mgr.bind(USER, m.group(1))
    m = re.match(r'^/回放\s+(\S+)$', text)
    if m:
        return do_replay(m.group(1))
    m = re.match(r'^/查\s+(\S+)$', text)
    if m:
        return do_query(m.group(1), USER)
    m = re.match(r'^/手牌\s+(\S+)$', text)
    if m:
        return do_watch(m.group(1))
    return HELP_TEXT


def handle_group(text, member_openid):
    """群聊指令（member_openid 标识身份，需先绑定）"""
    text = text.strip()
    if text in ('/帮助', '帮助', '/help', 'help'):
        return HELP_TEXT
    if text in ('/绑定', '绑定'):
        code = mgr.make_bind_code(member_openid)
        return '你的绑定码：%s\n私聊我发：/绑定 %s（10分钟内有效）' % (code, code)
    if text in ('/我的', '我的'):
        uid = mgr.resolve_member(member_openid)
        if not uid:
            return '还没绑定。先 @我 发 /绑定 获取绑定码，然后私聊我完成绑定。'
        return profile_of(uid)
    m = re.match(r'^/回放\s+(\S+)$', text)
    if m:
        return do_replay(m.group(1))
    m = re.match(r'^/查\s+(\S+)$', text)
    if m:
        return do_query(m.group(1), mgr.resolve_member(member_openid))
    m = re.match(r'^/手牌\s+(\S+)$', text)
    if m:
        return do_watch(m.group(1))
    return HELP_TEXT


class MyClient(qqbot.Client):
    async def on_ready(self):
        print('[bot] 已上线，等待消息...')

    async def on_group_at_message_create(self, message):
        uid = str(getattr(message.author, 'member_openid', '') or '')
        print('[group]', uid, message.content)
        text = re.sub(r'<@!\d+>', '', message.content).strip()
        reply_text = handle_group(text, uid)[:1900]
        img = IMG_PAYLOAD[0]; IMG_PAYLOAD[0] = None   # 必须在 handle 之后取（图是当前这条消息生成的）
        gid = str(getattr(message, 'group_openid', '') or '')   # 群的 openid，不是发言人的
        try:
            if img:
                try:
                    url = save_card(img)
                    media = await self.api.post_group_file(group_openid=gid, file_type=1, url=url, srv_send_msg=False)
                    await self.api.post_group_message(group_openid=gid, msg_type=7, media=media,
                                                      msg_id=message.id, msg_seq=1)
                    print('[card] 群图片已发送:', url)
                except Exception as e:
                    print('[reply error] 图片发送失败，回退纯文字:', e)
                    await message.reply(content=reply_text)
            else:
                await message.reply(content=reply_text)
        except Exception as e:
            print('[reply error]', e)

    async def on_c2c_message_create(self, message):
        global USER
        USER = str(getattr(message.author, 'user_openid', '') or '')
        print('[c2c]', USER, message.content)
        reply_text = handle_private(message.content.strip())[:1900]
        img = IMG_PAYLOAD[0]; IMG_PAYLOAD[0] = None   # 必须在 handle 之后取
        try:
            if img:
                try:
                    url = save_card(img)
                    media = await self.api.post_c2c_file(openid=USER, file_type=1, url=url, srv_send_msg=False)
                    await self.api.post_c2c_message(openid=USER, msg_type=7, media=media,
                                                    msg_id=message.id, msg_seq=1)
                    print('[card] 私聊图片已发送:', url)
                except Exception as e:
                    print('[reply error] 图片发送失败，回退纯文字:', e)
                    await message.reply(content=reply_text)
            else:
                await message.reply(content=reply_text)
        except Exception as e:
            print('[reply error]', e)


if __name__ == '__main__':
    _start_card_server()
    intents = qqbot.Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=APP_ID, secret=SECRET)
