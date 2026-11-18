# -*- coding: utf-8 -*-
"""小地图视频 v2：下载战舰回放 -> 调用 wows-toolkit 的 minimap_renderer CLI（MIT，预编译二进制）
-> 返回 MP4 路径。外部工具部署在 ~/wows_tools，素材在 ~/wows_assets/extracted。
渲染吃 CPU：全局只允许 1 个渲染任务（2G 服务器防挤爆 bot）。"""
import os
import re
import subprocess
import tempfile
import threading
import urllib.request

RENDERER_BIN = os.environ.get("MINIMAP_BIN",
                              os.path.expanduser("~/wows_tools/minimap_renderer_cpu"))
EXTRACTED_DIR = os.environ.get("MINIMAP_EXTRACTED",
                               os.path.expanduser("~/wows_assets/extracted"))
MAX_BYTES = 60 * 1024 * 1024          # 回放下载上限 60MB
RENDER_TIMEOUT = 420                   # 渲染超时 7 分钟
RENDER_LOCK = threading.Lock()


def _guarded_url(url):
    m = re.match(r"^(https?)://([A-Za-z0-9.\-]+)(:[0-9]+)?(/.*)?$", url.strip(), re.I)
    if not m:
        return None
    host = m.group(2).lower()
    if (host == "localhost" or host.startswith("127.") or host.startswith("10.")
            or host.startswith("192.168.") or host.startswith("172.16.")):
        return None
    return m.group(0)


def render_minimap(url):
    """返回 (ok, mp4_path 或 错误信息)。"""
    url = _guarded_url(url)
    if not url:
        return False, "链接不支持：仅 http/https，且不允许内网地址"
    if not RENDER_LOCK.acquire(blocking=False):
        return False, "正在渲染另一场对局，请几分钟后再发"
    tmp = tempfile.mkdtemp(prefix="minimap_")
    try:
        replay = os.path.join(tmp, "replay.wowsreplay")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(replay, "wb") as f:
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > MAX_BYTES:
                        return False, "回放文件过大（上限 60MB）"
                    f.write(chunk)
        except Exception as e:
            return False, "下载回放失败：" + type(e).__name__
        out_mp4 = os.path.join(tmp, "out.mp4")
        codec = os.environ.get("MINIMAP_CODEC", "h264").strip() or "h264"   # h264 平台兼容性最好
        max_mib = os.environ.get("MINIMAP_MAX_MIB", "3").strip()            # 目标大小，平台拉取不超时
        cmd = [RENDERER_BIN, "--extracted-dir", EXTRACTED_DIR, "-o", out_mp4,
               "--codec", codec, "--cpu"]   # 无显卡服务器必须显式软编（GPU 后端编码列表为空）
        if max_mib:
            cmd += ["--max-size-mib", max_mib]
        cmd.append(replay)
        print("[render] 渲染命令: %s" % " ".join(cmd))
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, "渲染超时（7 分钟），这场对局可能太长"
        except FileNotFoundError:
            return False, "渲染器未部署：先装 ~/wows_tools（见 README 阶段1）"
        if p.returncode != 0:
            return False, "渲染失败：" + (p.stderr.decode("utf-8", "replace")[-200:] or "未知错误")
        if not os.path.exists(out_mp4):
            return False, "渲染结束但没有产出 MP4"
        return True, out_mp4
    finally:
        RENDER_LOCK.release()




UPLOAD_DIR = os.environ.get("MINIMAP_UPLOAD_DIR",
                            os.path.expanduser("~/astral-bot-new/cards"))


def render_minimap_file(path):
    """渲染本地上传的回放（/upload 页的产物，/小地图 6位码 入口）。"""
    if not RENDER_LOCK.acquire(blocking=False):
        return False, "正在渲染另一场对局，请几分钟后再发"
    tmp = tempfile.mkdtemp(prefix="minimap_")
    try:
        if not os.path.exists(path):
            return False, "找不到这个码对应的回放（超过 7 天已被清理），请重新上传"
        out_mp4 = os.path.join(tmp, "out.mp4")
        cmd = [RENDERER_BIN, "--extracted-dir", EXTRACTED_DIR, "-o", out_mp4, path]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False, "渲染超时（7 分钟），这场对局可能太长"
        if p.returncode != 0:
            return False, "渲染失败：" + (p.stderr.decode("utf-8", "replace")[-200:] or "未知错误")
        if not os.path.exists(out_mp4):
            return False, "渲染结束但没有产出 MP4"
        return True, out_mp4
    finally:
        RENDER_LOCK.release()

def cleanup(tmp_path):
    import shutil
    try:
        shutil.rmtree(os.path.dirname(tmp_path), ignore_errors=True)
    except Exception:
        pass


# ── 上传页：浏览器直传回放到机器人（免网盘）────────────────
UPLOAD_TTL = 7200   # 上传的回放保留 2 小时


def upload_page():
    return UPLOAD_HTML


def _upload_dir():
    from bot_core import DATA_DIR
    return DATA_DIR.parent / "cards"   # 与卡片图同一静态目录，URL 直接可达


def handle_upload(h):
    """POST /upload?name=xxx.wowsreplay，body 为原始文件字节（页面用 fetch 直传）。"""
    import time
    import uuid
    from urllib.parse import urlparse, parse_qs
    try:
        length = int(h.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BYTES:
            _respond(h, False, "文件为空或超过 60MB 上限")
            return
        name = (parse_qs(urlparse(h.path).query).get("name") or ["replay.wowsreplay"])[0]
        if not name.lower().endswith(".wowsreplay"):
            _respond(h, False, "只接受 .wowsreplay 回放文件")
            return
        up_dir = _upload_dir()
        up_dir.mkdir(parents=True, exist_ok=True)
        # 清理 2 小时前的旧上传
        now = time.time()
        for f in up_dir.glob("card_up_*.wowsreplay"):
            try:
                if now - f.stat().st_mtime > UPLOAD_TTL:
                    f.unlink()
            except OSError:
                pass
        fname = "card_up_" + uuid.uuid4().hex[:10] + ".wowsreplay"
        data = h.rfile.read(length)
        if not data.startswith(b"PK") and b"wowsreplay" not in data[:4096]:
            _respond(h, False, "文件内容不像回放文件")
            return
        (up_dir / fname).write_bytes(data)
        host = h.headers.get("Host") or "localhost"
        url = "http://" + host + "/" + fname
        _respond(h, True, "", url)
    except Exception as e:
        _respond(h, False, "上传失败：" + type(e).__name__)


def _respond(h, ok, msg, url=""):
    body = ("<!doctype html><html lang=zh><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>小地图上传</title><style>body{font-family:sans-serif;max-width:460px;"
            "margin:40px auto;padding:0 16px}button{width:100%;padding:12px;margin:8px 0;"
            "font-size:16px;background:#318B25;color:#fff;border:0;border-radius:8px}"
            ".ok{color:#27851E}.err{color:#B84A4A}textarea{width:100%;font-size:15px}</style>"
            "</head><body>")
    if ok:
        body += ("<h3 class=ok>✅ 上传成功</h3><p>复制下面这行，<b>回群里发给机器人</b>：</p>"
                 "<textarea rows=2 readonly>/小地图 " + url + "</textarea>"
                 "<p style='color:#888;font-size:13px'>之后等 1~7 分钟收视频；文件 2 小时后自动清理。</p>")
    else:
        body += "<h3 class=err>❌ " + msg + "</h3><p><a href='/upload'>返回重试</a></p>"
    body += "</body></html>"
    data = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)


UPLOAD_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>小地图回放上传</title>
<style>body{font-family:sans-serif;max-width:460px;margin:40px auto;padding:0 16px}
button{width:100%;padding:12px;margin:8px 0;font-size:16px;background:#318B25;color:#fff;
border:0;border-radius:8px}#st{color:#888;font-size:14px}</style></head><body>
<h3>上传战舰回放（.wowsreplay）</h3>
<input type="file" id="f" accept=".wowsreplay" style="width:100%;margin:8px 0">
<button onclick="up()">上传</button>
<p id="st"></p>
<script>
function up(){
  var f=document.getElementById('f').files[0];
  var st=document.getElementById('st');
  if(!f){st.textContent='请先选择回放文件';return;}
  if(f.size>60*1024*1024){st.textContent='文件超过 60MB';return;}
  st.textContent='上传中…';
  fetch('/upload?name='+encodeURIComponent(f.name),{method:'POST',body:f})
    .then(function(r){return r.text();})
    .then(function(t){document.open();document.write(t);document.close();})
    .catch(function(){st.textContent='上传失败，请重试';});
}
</script>
<p style="color:#888;font-size:13px">文件直传本服务器，不经任何第三方。
传完按页面提示回群里发指令即可。</p>
</body></html>"""
