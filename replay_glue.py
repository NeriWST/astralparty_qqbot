# -*- coding: utf-8 -*-
"""回放小地图视频插件（可拔插）。
挂载方式：qq_bot.py 底部一行 try/except 调用 replay_glue.mount()。
- 星趴主功能零改动：全部通过"包装"注入（原函数原样保留并先被调用）
- 卸载：删除 qq_bot.py 中 replay 插件段 + 删除本文件与 bot_minimap/bot_replayupload
- 禁用：start.sh 里 export REPLAY_PLUGIN=0 即可，不用改代码
- 插件自身异常被 mount 外层 try 捕获，机器人照常运行
"""
import os
import asyncio
import re
import urllib.request
from dataclasses import dataclass

import bot_minimap

_LOADED = False


def _rep_help_text(card_base):
    base = (card_base or "").rstrip("/")
    return ("【回放小地图视频】\n"
            "1. 打开 %s/upload 上传回放文件\n"
            "2. 把页面给出的指令复制发到群里\n"
            "3. 等 1~7 分钟，视频发到群里\n"
            "说明：仅限 .wowsreplay；超过 10MB 会退回文字；同时只渲染一场。" % base)


def _resolve_qb():
    """取正在运行的 qq_bot 实例：脚本直跑时是 __main__，被导入测试时是 qq_bot。"""
    import sys
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "handle_group") and hasattr(main, "MyClient"):
        return main
    return sys.modules["qq_bot"]


def _route(text):
    """回放插件的指令路由；不认识的返回 None 交给主程序。"""
    t = (text or "").strip()
    if t in ("/rep help", "/rep", "rep help"):
        return _rep_help_text(getattr(_resolve_qb(), "CARD_BASE", ""))
    if t.startswith("/小地图"):
        arg = t[len("/小地图"):].strip()
        if not arg:
            return "用法：先上传回放（%s/upload），再把页面给出的指令发给我" % _base_of()
        ok, res = bot_minimap.render_minimap(arg)
        if not ok:
            return res
        try:
            with open(res, "rb") as f:
                return _VideoReply("小地图视频渲染完成 ✅", video=f.read())
        except Exception as e:
            return "读取视频失败：%s" % e
        finally:
            bot_minimap.cleanup(res)
    return None


def _base_of():
    try:
        return (_resolve_qb().CARD_BASE or "").rstrip("/")
    except Exception:
        return ""


VIDEO_KEEP = int(os.environ.get("MINIMAP_KEEP_VIDEOS", "10"))


def _save_video_fifo(video: bytes) -> str:
    """视频存 <CARD_DIR>/vids/，写入后按修改时间只留最新 VIDEO_KEEP 条（默认 10）。"""
    import time as _time
    import uuid as _uuid
    qb = _resolve_qb()
    vdir = os.path.join(qb.CARD_DIR, "vids")
    os.makedirs(vdir, exist_ok=True)
    name = "v_%d_%s.mp4" % (int(_time.time() * 1000), _uuid.uuid4().hex[:8])
    with open(os.path.join(vdir, name), "wb") as f:
        f.write(video)
    try:
        files = sorted((os.path.join(vdir, n) for n in os.listdir(vdir)),
                       key=os.path.getmtime)
        for old_f in files[:-VIDEO_KEEP]:
            os.remove(old_f)
    except OSError:
        pass
    return (qb.CARD_BASE or "").rstrip("/") + "/vids/" + name


TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = "https://api.sgroup.qq.com"
_TOKEN_CACHE = {"v": None, "ts": 0.0}


def _qq_token():
    """官方接口自取 access_token（5 分钟缓存），不依赖 botpy 内部属性。"""
    import json
    import time
    now = time.time()
    if _TOKEN_CACHE["v"] and now - _TOKEN_CACHE["ts"] < 300:
        return _TOKEN_CACHE["v"]
    body = json.dumps({"appId": os.environ.get("QQ_APPID", ""),
                       "clientSecret": os.environ.get("QQ_SECRET", "")}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    tok = d.get("access_token")
    if not tok:
        raise RuntimeError("获取 access_token 失败: %r" % d)
    _TOKEN_CACHE["v"] = tok
    _TOKEN_CACHE["ts"] = now
    return tok


def _upload_video_file(group, target, url, attempt):
    return _upload_media_file(group, target, url, 2, attempt)


def _upload_media_file(group, target, url, file_type, attempt=1):
    """直传视频文件到 QQ 平台（urllib 同步，超时 120s，绕开 botpy 短超时）。"""
    import json
    scope = "groups" if group else "users"
    endpoint = "%s/v2/%s/%s/files" % (API_BASE, scope, target)
    body = json.dumps({"file_type": file_type, "url": url, "srv_send_msg": False}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "QQBot " + _qq_token()})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    file_info = d.get("file_info")
    if not file_info:
        raise RuntimeError("上传未返回 file_info: %r" % (d,))
    print("[replay] 视频上传成功（第%d次）: file_info=%s..." % (attempt, str(file_info)[:24]))
    return file_info


def _start_card_server_v2():
    """原版 + 上传页：/upload 路由 + /login 与静态文件保持原行为。"""
    import threading
    import bot_weblogin
    import bot_replayupload
    qb = _resolve_qb()

    os.makedirs(qb.CARD_DIR, exist_ok=True)
    handler = bot_replayupload.make_handler(qb.CARD_DIR, qb.mgr, qb.CARD_BASE)

    def run():
        try:
            from http.server import ThreadingHTTPServer
            httpd = ThreadingHTTPServer(("0.0.0.0", qb.CARD_PORT), handler)
            print("[cards] 卡片图片服务已启动 :%d（含回放上传页 /upload）" % qb.CARD_PORT)
            httpd.serve_forever()
        except Exception as e:
            print("[cards] 图片服务启动失败（将回退纯文字）:", e)

    threading.Thread(target=run, daemon=True).start()


def mount():
    """注入全部回放功能；任何一步失败都打印日志但不抛异常。"""
    global _LOADED, _VideoReply
    if _LOADED:
        return
    if os.environ.get("REPLAY_PLUGIN", "1") != "1":
        print("[replay] 插件已通过 REPLAY_PLUGIN=0 禁用")
        return
    qb = _resolve_qb()

    # 1) 视频回复类型（子类化，不动原 Reply 数据类）
    @dataclass(frozen=True)
    class VideoReply(qb.Reply):
        video: bytes | None = None
    _VideoReply = VideoReply

    # 2) 指令包装：先走插件路由，不认识的原样交给主程序
    _orig_priv = qb.handle_private
    _orig_grp = qb.handle_group

    def _priv(text, uid):
        r = _route(text)
        return r if r is not None else _orig_priv(text, uid)

    def _grp(text, mo):
        r = _route(text)
        return r if r is not None else _orig_grp(text, mo)

    qb.handle_private = _priv
    qb.handle_group = _grp

    # 3) 视频发送：包装 MyClient._reply（原版完全保留作为回退）
    _orig_reply = qb.MyClient._reply

    async def _send_video(self, message, target, video, group):
        url = await asyncio.to_thread(_save_video_fifo, video)
        send = (self.api.post_group_message if group else self.api.post_c2c_message)
        scope = {"group_openid": target} if group else {"openid": target}
        last_err = None
        for attempt in (1, 2):
            try:
                file_info = await asyncio.to_thread(
                    _upload_video_file, group, target, url, attempt)
                await send(msg_type=7, media={"file_info": file_info},
                           msg_id=message.id, msg_seq=1, **scope)
                print("[replay] 视频已发送 (%dMB, 第%d次尝试)" % (len(video) // 1048576, attempt))
                return True
            except Exception as e:
                last_err = e
                print("[replay] 视频发送第%d次失败: %s" % (attempt, e))
                await asyncio.sleep(3)
        raise last_err

    async def _reply(self, message, target, result, group=False):
        video = getattr(result, "video", None)
        if video and getattr(qb, "CARD_BASE", ""):
            try:
                if len(video) > 30 * 1024 * 1024:
                    raise ValueError("视频超过 30MB 上限（%dMB），这场对局太长了" % (len(video) // 1048576))
                if await _send_video(self, message, target, video, group):
                    return
            except Exception as e:
                print("[reply error] 视频发送失败，回退纯文字:", e)
        await _orig_reply(self, message, target, result, group=group)

    qb.MyClient._reply = _reply

    # 4) 上传页：替换启动函数（v2 是原版行为的超集：/login、静态文件、/upload）
    qb._start_card_server = _start_card_server_v2

    _LOADED = True
    print("[replay] 回放插件已挂载（/小地图 /rep help /upload）")


_VideoReply = None
