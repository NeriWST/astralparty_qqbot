# -*- coding: utf-8 -*-
"""回放上传页 /upload：群友手机浏览器打开 -> 选 .wowsreplay -> 页面给出拼好的 /小地图 命令。
文件存到 <card_dir>/rp/，由 8420 静态服务提供下载链接；24h 自动清旧。
/login 路由委托给 bot_weblogin.make_handler 返回的 Handler 类（未绑定方法调用）。"""
import os
import re
import time
import uuid
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse

MAX_UPLOAD = 30 * 1024 * 1024   # 30MB（回放通常 1~5MB）
RETENTION = 24 * 3600

_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>小地图视频 · 上传回放</title>
<style>
body{font-family:sans-serif;max-width:480px;margin:36px auto;padding:0 16px;color:#222}
input,button{width:100%;padding:14px;margin:8px 0;font-size:17px;box-sizing:border-box}
button{background:#318B25;color:#fff;border:0;border-radius:8px}
.cmd{background:#f2f4f6;border-radius:8px;padding:12px;font-size:15px;word-break:break-all}
.tip{color:#888;font-size:13px}
</style></head><body>
<h3>小地图视频 · 上传回放</h3>
@@DONE@@
<form method="post" action="/upload" enctype="multipart/form-data">
<input type="file" name="replay" accept=".wowsreplay" required>
<button>上传并获取指令</button>
</form>
<p class="tip">仅限 .wowsreplay，≤30MB。上传成功后，把页面上生成的指令<b>复制发到群里</b>，机器人渲染小地图视频（约 1~7 分钟）。</p>
</body></html>"""

_DONE = """<div class="cmd">✅ 上传成功！长按复制下面这句，发到群里：<br><br><b>/小地图 {url}</b></div><br>"""


def _clean_old(rp_dir):
    try:
        now = time.time()
        for n in os.listdir(rp_dir):
            p = os.path.join(rp_dir, n)
            if now - os.path.getmtime(p) > RETENTION:
                os.remove(p)
    except Exception:
        pass


def _parse_multipart(body, boundary):
    marker = b"--" + boundary.encode()
    for part in body.split(marker)[1:]:
        if b"\r\n\r\n" not in part:
            continue
        head, _, content = part.partition(b"\r\n\r\n")
        m = re.search(br'filename="([^"]*)"', head)
        if not m or not m.group(1):
            continue
        fname = m.group(1).decode("utf-8", "replace")
        content = content.rstrip(b"\r\n")
        if content.endswith(b"--"):
            content = content[:-2]
        return fname, content
    return None


def make_handler(card_dir, mgr, card_base):
    import bot_weblogin as wl
    wl_handler = wl.make_handler(card_dir, mgr)   # 返回 Handler 类，用于 /login 委托
    rp_dir = os.path.join(card_dir, "rp")
    os.makedirs(rp_dir, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=card_dir, **kw)

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            p = urlparse(self.path)
            if p.path == "/upload":
                self._html(_PAGE.replace("@@DONE@@", ""))
                return
            if p.path == "/login":
                wl_handler.do_GET(self)   # 网页登录页（其内部不会走到 super）
                return
            super().do_GET()   # 静态文件（cards/ 与 rp/）

        def do_POST(self):
            p = urlparse(self.path)
            if p.path.startswith("/login"):
                wl_handler.do_POST(self)
                return
            if p.path != "/upload":
                self.send_error(404)
                return
            try:
                ctype = self.headers.get("Content-Type", "")
                m = re.search(r"boundary=([^;]+)", ctype)
                length = int(self.headers.get("Content-Length") or 0)
                if not m or length <= 0 or length > MAX_UPLOAD + 4096:
                    self._html(_PAGE.replace("@@DONE@@", "<p>请求异常（文件过大？）</p>"))
                    return
                body = self.rfile.read(length)
                parsed = _parse_multipart(body, m.group(1).strip())
                if not parsed:
                    self._html(_PAGE.replace("@@DONE@@", "<p>没有收到文件，请重新选择</p>"))
                    return
                fname, data = parsed
                if not fname.lower().endswith(".wowsreplay"):
                    self._html(_PAGE.replace("@@DONE@@", "<p>只支持 .wowsreplay 回放文件</p>"))
                    return
                if len(data) > MAX_UPLOAD:
                    self._html(_PAGE.replace("@@DONE@@", "<p>文件超过 30MB 上限</p>"))
                    return
                _clean_old(rp_dir)
                name = uuid.uuid4().hex[:16] + ".wowsreplay"
                with open(os.path.join(rp_dir, name), "wb") as f:
                    f.write(data)
                base = (card_base or "").rstrip("/")
                self._html(_PAGE.replace("@@DONE@@", _DONE.replace("{url}", base + "/rp/" + name)))
                print("[upload] 回放已接收:", name, len(data), "bytes")
            except Exception as e:
                print("[upload] 上传处理失败:", type(e).__name__)
                self._html(_PAGE.replace("@@DONE@@", "<p>上传失败，请重试</p>"))

        def _html(self, *args):
            """兼容两种调用：_html(完整HTML文档) 不包壳；_html(标题, 片段) 包壳（bot_weblogin 委托用后者）"""
            if len(args) == 2:
                title, body = args
                data = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width,initial-scale=1">'
                        '<title>%s</title></head><body>%s</body></html>' % (title, body)).encode("utf-8")
            else:
                data = args[0].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler
