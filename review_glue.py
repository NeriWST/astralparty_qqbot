# -*- coding: utf-8 -*-
"""星趴复盘插件（正式功能，独立于 minimap 租户）。
/复盘 16位回放号 → 每玩家一张长图（至多 4 张）。
自包含：不 import replay_glue / bot_minimap / bot_replayupload，
将来移除 minimap 三件套不影响本插件。REVIEW_PLUGIN=0 可禁用。"""
import asyncio
import json
import os
import re
import time
import urllib.request
import shutil
import uuid
from dataclasses import dataclass

_LOADED = False
_ImagesReply = None
API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_TOKEN_CACHE = {"v": None, "ts": 0.0}
REVIEW_KEEP = int(os.environ.get("REVIEW_KEEP", "10"))


def _resolve_qb():
    import sys
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "handle_group") and hasattr(main, "MyClient"):
        return main
    return sys.modules["qq_bot"]


def _qq_token():
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
        raise RuntimeError("获取 access_token 失败: %r" % (d,))
    _TOKEN_CACHE["v"] = tok
    _TOKEN_CACHE["ts"] = now
    return tok


def _upload_media_file(group, target, url, file_type):
    scope = "groups" if group else "users"
    endpoint = "%s/v2/%s/%s/files" % (API_BASE, scope, target)
    body = json.dumps({"file_type": file_type, "url": url, "srv_send_msg": False}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "QQBot " + _qq_token()})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    fi = d.get("file_info")
    if not fi:
        raise RuntimeError("上传未返回 file_info: %r" % (d,))
    return fi


def _save_tmp_png(png):
    qb = _resolve_qb()
    tdir = os.path.join(qb.CARD_DIR, "tmp")
    os.makedirs(tdir, exist_ok=True)
    now = time.time()
    for n in os.listdir(tdir):
        p = os.path.join(tdir, n)
        try:
            if now - os.path.getmtime(p) > 3600:
                os.remove(p)
        except OSError:
            pass
    name = "t_%d_%s.png" % (int(now * 1000), uuid.uuid4().hex[:8])
    with open(os.path.join(tdir, name), "wb") as f:
        f.write(png)
    return (qb.CARD_BASE or "").rstrip("/") + "/tmp/" + name


def _png_size(b):
    import struct
    return struct.unpack(">II", b[16:24])


def _upload_markdown_image(png):
    """素材管理三步：prepare → PUT 直传 → complete，返回 qqbot-media:// 引用与 image_id。"""
    import hashlib
    md5 = hashlib.md5(png).hexdigest()
    sha1 = hashlib.sha1(png).hexdigest()
    headers = {"Content-Type": "application/json", "Authorization": "QQBot " + _qq_token()}

    def post(path, payload):
        req = urllib.request.Request(API_BASE + path, data=json.dumps(payload).encode(),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    prep = post("/v2/media-images/prepare", {
        "file_name": "review.png", "file_size": len(png),
        "content_type": "image/png", "md5": md5, "sha1": sha1})
    put_req = urllib.request.Request(prep["presigned_url"], data=png, method="PUT",
                                     headers={"Content-Type": "image/png"})
    with urllib.request.urlopen(put_req, timeout=60) as r:
        r.read()
    done = post("/v2/media-images/complete", {"upload_id": prep["upload_id"], "md5": md5})
    return done["url"], done.get("image_id")


def _delete_markdown_image(image_id):
    try:
        req = urllib.request.Request(
            API_BASE + "/v2/media-images/" + str(image_id), method="DELETE",
            headers={"Authorization": "QQBot " + _qq_token()})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception:
        pass


def _send_markdown_message(group, target, content, msg_id, seq):
    scope = "groups" if group else "users"
    endpoint = "%s/v2/%s/%s/messages" % (API_BASE, scope, target)
    body = json.dumps({"msg_type": 2, "markdown": {"content": content},
                       "msg_id": msg_id, "msg_seq": seq}).encode()
    req = urllib.request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json", "Authorization": "QQBot " + _qq_token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


async def _send_images(self, message, target, images, group):
    """首选：Markdown 一条消息内嵌全部图片；失败回退逐张富媒体。"""
    try:
        lines = ["# 对局复盘"]
        ids = []
        for idx2, img in enumerate(images[:5]):
            url, iid = await asyncio.to_thread(_upload_markdown_image, img)
            ids.append(iid)
            w, h = _png_size(img)
            lines.append("![复盘图%d #%dpx #%dpx](%s)" % (idx2 + 1, w, h, url))
        await asyncio.to_thread(_send_markdown_message, group, target,
                                "\n".join(lines), message.id, 1)
        for iid in ids:
            await asyncio.to_thread(_delete_markdown_image, iid)
        print("[review] 复盘图已按 Markdown 单条消息发送 %d 张" % min(len(images), 5))
        return
    except Exception as e:
        print("[review] Markdown 发送失败，回退逐张发送:", e)
    send = (self.api.post_group_message if group else self.api.post_c2c_message)
    scope = {"group_openid": target} if group else {"openid": target}
    payload = list(images)
    if len(payload) > 4:   # 被动回复上限 4 条：总览单独 + 其余拼长图
        from PIL import Image as _Image
        import io as _io
        import review_viz
        parts = [_Image.open(_io.BytesIO(b)) for b in payload[1:]]
        merged = review_viz.stack_images(parts)
        def _to_png(im):
            buf = _io.BytesIO()
            im.save(buf, "PNG")
            return buf.getvalue()
        payload = [payload[0]] + [_to_png(im) for im in merged]
    n = min(len(payload), 4)
    for i2 in range(n):
        url = await asyncio.to_thread(_save_tmp_png, payload[i2])
        fi = await asyncio.to_thread(_upload_media_file, group, target, url, 1)
        await send(msg_type=7, media={"file_info": fi},
                   msg_id=message.id, msg_seq=i2 + 1, **scope)
    print("[review] 复盘图已回退发送 %d 条消息" % n)


def _load_hero_names():
    """character_ids.json 是 [{id,name,...}] 列表格式（35 位角色）。"""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "data", "character_ids.json")
        raw = json.loads(open(p, encoding="utf-8").read())
        if isinstance(raw, list):
            return {int(c["id"]): c["name"] for c in raw if "id" in c and "name" in c}
        return {int(k): v for k, v in raw.items()}
    except Exception:
        return {}


def _reviews_dir():
    return os.path.join(_resolve_qb().CARD_DIR, "reviews")


def _purge_reviews():
    d = _reviews_dir()
    try:
        subs = sorted((os.path.join(d, n) for n in os.listdir(d)
                       if os.path.isdir(os.path.join(d, n))),
                      key=os.path.getmtime)
        for old in subs[:-REVIEW_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass


def _do_review(rid):
    import review_plugin
    import review_viz
    rdir = os.path.join(_reviews_dir(), rid)
    pages = []
    if os.path.isdir(rdir) and os.path.exists(os.path.join(rdir, "ok.v7")):
        names = sorted(n for n in os.listdir(rdir) if n.startswith("p") and n.endswith(".png"))
        pages = [open(os.path.join(rdir, n), "rb").read() for n in names]
    if not pages:
        try:
            review = review_plugin.build_full(rid, rdir)
        except Exception as e:
            return "复盘解析失败：%s" % e
        try:
            pages = review_viz.render_parts_png(review, _load_hero_names())
        except Exception as e:
            return "复盘渲染失败：%s" % e
        if not pages:
            return "复盘渲染失败：无玩家数据"
        os.makedirs(rdir, exist_ok=True)
        for i, pg in enumerate(pages):
            with open(os.path.join(rdir, "p%d.png" % (i + 1)), "wb") as f:
                f.write(pg)
        open(os.path.join(rdir, "ok.v7"), "w").write("v2")
        _purge_reviews()
    return _ImagesReply("复盘 #%s" % rid, images=tuple(pages[:6]))


def _route_review(text):
    t = (text or "").strip()
    if not t.startswith("/复盘"):
        return None
    arg = t[3:].strip()
    if not re.fullmatch(r"\d{16}", arg or ""):
        return "用法：/复盘 16位回放号"
    return _do_review(arg)


def mount():
    global _LOADED, _ImagesReply
    if _LOADED:
        return
    if os.environ.get("REVIEW_PLUGIN", "1") != "1":
        print("[review] 插件已通过 REVIEW_PLUGIN=0 禁用")
        return
    qb = _resolve_qb()

    @dataclass(frozen=True)
    class ImagesReply(qb.Reply):
        images: tuple = ()
    _ImagesReply = ImagesReply

    _orig_priv = qb.handle_private
    _orig_grp = qb.handle_group

    def _priv(text, uid):
        r = _route_review(text)
        return r if r is not None else _orig_priv(text, uid)

    def _grp(text, mo):
        r = _route_review(text)
        return r if r is not None else _orig_grp(text, mo)

    qb.handle_private = _priv
    qb.handle_group = _grp

    _orig_reply = qb.MyClient._reply

    async def _reply(self, message, target, result, group=False):
        images = getattr(result, "images", None)
        if images and getattr(qb, "CARD_BASE", ""):
            try:
                await _send_images(self, message, target, images, group)
                return
            except Exception as e:
                print("[review] 复盘图发送失败，回退纯文字:", e)
        await _orig_reply(self, message, target, result, group=group)

    qb.MyClient._reply = _reply

    _LOADED = True
    print("[review] 星趴复盘插件已挂载（/复盘）")
