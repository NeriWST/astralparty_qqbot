# -*- coding: utf-8 -*-
"""网页登录：群聊 /登录 -> 一次性链接 -> 浏览器完成手机号+验证码。
解决"陌生人无法私聊个人认证 bot 导致无法登录"的问题；手机号不经由 QQ 传输。
票直接存入发言者群身份（member_openid）的槽位，无需私聊、无需绑定码。"""
import json
import time
import uuid
import threading
from html import escape
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from bot_core import DATA_DIR
from astral.sdk_login import request_code, phone_login

_TTL = 600      # 链接 10 分钟有效
_MAX_SEND = 3   # 每条链接最多发 3 次验证码
_MAX_TRY = 5    # 每条链接最多试 5 次验证码

_store_file = DATA_DIR / 'weblogin_tokens.json'
_lock = threading.Lock()


def _load():
    try:
        return json.loads(_store_file.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save(d):
    try:
        _store_file.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def issue_token(member_openid):
    """群聊 /登录 时调用：发一次性链接令牌。"""
    t = uuid.uuid4().hex
    with _lock:
        d = _load()
        d[t] = {'member': member_openid, 'ts': time.time(), 'phone': '',
                'sends': 0, 'tries': 0, 'done': False}
        _save(d)
    return t


def _take(t):
    with _lock:
        d = _load()
        item = d.get(t)
        if not item:
            return None, '链接无效，请在群里重新 /登录'
        if time.time() - item['ts'] > _TTL:
            d.pop(t, None)
            _save(d)
            return None, '链接已过期（10分钟有效），请在群里重新 /登录'
        if item.get('done'):
            return None, '该链接已完成登录'
        return item, None


def _put(t, item):
    with _lock:
        d = _load()
        if t in d:
            d[t] = item
            _save(d)


def _page(t, msg1='', msg2=''):
    return _HTML.replace('{t}', t).replace('{msg1}', msg1).replace('{msg2}', msg2)


_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星趴机器人 · 登录</title>
<style>
body{font-family:sans-serif;max-width:420px;margin:40px auto;padding:0 16px;color:#222}
input,button{width:100%;padding:12px;margin:6px 0;font-size:16px;box-sizing:border-box}
button{background:#5a48b8;color:#fff;border:0;border-radius:8px}
.msg{color:#c00} .ok{color:#080}
</style></head><body>
<h3>星趴机器人 · 游戏账号登录</h3>
<form method="post" action="/login/send">
<input type="hidden" name="t" value="{t}">
<input name="phone" placeholder="手机号" inputmode="numeric" required>
<button>发送短信验证码</button>
</form>
{msg1}
<form method="post" action="/login/do">
<input type="hidden" name="t" value="{t}">
<input name="code" placeholder="短信验证码" inputmode="numeric" required>
<button>登录</button>
</form>
{msg2}
<p style="color:#888;font-size:13px">手机号仅用于游戏官方短信登录，不经过 QQ，机器人不会保存手机号明文。</p>
</body></html>"""


def make_handler(card_dir, manager):
    """给 qq_bot 的图片服务挂 /login 路由；其余请求照旧当静态文件服务。"""
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=card_dir, **kw)

        def log_message(self, fmt, *args):
            pass    # 静音 404 噪音

        def do_GET(self):
            p = urlparse(self.path)
            if p.path == '/login':
                t = (parse_qs(p.query).get('t') or [''])[0]
                item, err = _take(t)
                if err:
                    self._html('星趴机器人', '<p class="msg">%s</p>' % escape(err))
                    return
                self._html('星趴机器人 · 登录', _page(t))
                return
            super().do_GET()

        def do_POST(self):
            p = urlparse(self.path)
            if p.path not in ('/login/send', '/login/do'):
                self.send_error(404)
                return
            length = int(self.headers.get('Content-Length') or 0)
            form = parse_qs(self.rfile.read(length).decode('utf-8', 'replace'))
            t = (form.get('t') or [''])[0]
            item, err = _take(t)
            if err:
                self._html('星趴机器人 · 登录', _page('', msg2='<p class="msg">%s</p>' % escape(err)))
                return
            phone = (form.get('phone') or [''])[0].strip()
            code = (form.get('code') or [''])[0].strip()
            if p.path == '/login/send':
                if not (phone.isdigit() and len(phone) == 11):
                    self._html('星趴机器人 · 登录', _page(t, msg1='<p class="msg">手机号应为 11 位数字</p>'))
                    return
                if item['sends'] >= _MAX_SEND:
                    self._html('星趴机器人 · 登录', _page(t, msg1='<p class="msg">发送次数过多，请回群里重新 /登录</p>'))
                    return
                try:
                    request_code(phone)
                except Exception as e:
                    self._html('星趴机器人 · 登录', _page(t, msg1='<p class="msg">发送失败：%s</p>' % escape(str(e))))
                    return
                item['phone'] = phone
                item['sends'] += 1
                _put(t, item)
                print('[weblogin] 验证码已发送: %s****%s' % (phone[:3], phone[-4:]))
                self._html('星趴机器人 · 登录', _page(t, msg1='<p class="ok">验证码已发送，请在下方输入</p>'))
                return
            # /login/do
            if not item.get('phone'):
                self._html('星趴机器人 · 登录', _page(t, msg1='<p class="msg">请先获取验证码</p>'))
                return
            if item['tries'] >= _MAX_TRY:
                self._html('星趴机器人 · 登录', _page(t, msg2='<p class="msg">尝试次数过多，请回群里重新 /登录</p>'))
                return
            item['tries'] += 1
            _put(t, item)
            try:
                sid, resp = phone_login(item['phone'], code)
            except Exception as e:
                self._html('星趴机器人 · 登录', _page(t, msg2='<p class="msg">登录失败：%s</p>' % escape(str(e))))
                return
            if not manager._save_token(item['member'], resp, item['phone']):
                self._html('星趴机器人 · 登录', _page(t, msg2='<p class="msg">登录响应异常，请稍后再试</p>'))
                return
            item['done'] = True
            _put(t, item)
            try:
                manager.get_profile(item['member'])   # 顺手上线，/我的 秒回
            except Exception as e:
                print('[weblogin] 预上线失败（不影响登录）:', type(e).__name__)
            print('[weblogin] 登录成功 ->', item['member'][:8])
            self._html('登录成功', '<h3>✅ 登录成功</h3><p>回群里 @机器人 发 /我的 查战绩吧。</p>')

        def _html(self, title, body):
            data = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>%s</title></head><body>%s</body></html>' % (title, body)).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler
