#!/usr/bin/env python3
# test_5155_paging_v2.py —— 用独立测试小号测 5155 翻页深度，bot 全程无感
import sys, time
sys.path.insert(0, '/home/ubuntu/astral-bot-new')
from bot_core import AccountManager
from astral.sdk_login import request_code, phone_login, LoginError

ALT       = 'ALT_5155_TEST'   # 独立测试号，与 bot 账号池完全隔离
TARGET    = sys.argv[1] if len(sys.argv) > 1 else '2554940'
MAX_INDEX = int(sys.argv[2]) if len(sys.argv) > 2 else 30
OUT       = '/tmp/paging_test.txt'

# ── 1. 测试号 SMS 登录（不落任何持久状态到 bot）──
phone = input('测试小号手机号: ').strip()
try:
    request_code(phone)
    code = input('短信验证码: ').strip()
    sid, resp = phone_login(phone, code)
except LoginError as e:
    sys.exit('登录失败: %s' % e)

# ── 2. 复刻 ensure_service_login 的登录序列（import 复用，不修改 bot）──
mgr = AccountManager()
mgr._save_token(ALT, resp, phone)   # 存档（新建的临时文件，结尾会删）
mgr._load_token(ALT)
try:
    mgr.get_profile(ALT)
except Exception as e:
    sys.exit('建会话失败: %s' % e)
c = (mgr.sessions.get(ALT) or {}).get('client')
if not c:
    sys.exit('建会话失败：sessions 里没有 client')
prof = (mgr.sessions[ALT].get('profile') or {})
print('测试号就绪: %s (uid=%s)' % (prof.get('nick', '?'), prof.get('uid', '?')), flush=True)

# ── 3. 翻页测试（指数退避，连续 5 错即停）──
uid, seen, lines, delay, errs = int(TARGET), set(), [], 5.0, 0
for idx in range(MAX_INDEX + 1):
    t0, err = time.time(), None
    try:
        fr   = c.get_fight_records(uid, index=idx, timeout=15.0)
        recs = list(getattr(fr, 'recordData', []) or [])
    except Exception as e:
        recs, err = [], '%s:%s' % (type(e).__name__, e)
    dt = time.time() - t0
    sample, rids = '', []
    for r in recs:
        rid = str(getattr(r, 'replayId', '') or getattr(r, 'replay_id', '') or '')
        if rid:
            rids.append(rid)
        if idx == 0 and not sample:
            sample = ' | 样本: ' + str(r)[:280]
    new = [x for x in rids if x not in seen]
    seen.update(rids)
    line = 'index=%d %.1fs 记录=%d 新replay=%d%s%s' % (
        idx, dt, len(recs), len(new), (' ERR ' + err) if err else '', sample)
    lines.append(line)
    open(OUT, 'w').write('\n'.join(lines) + '\n')
    print(line, flush=True)
    if err:
        errs += 1
        delay = min(delay * 2, 60)
        if errs >= 5:
            print('连续错误过多，终止', flush=True)
            break
    else:
        delay = 5.0
    time.sleep(delay)
tail = 'DONE 总去重replay=%d 错误=%d' % (len(seen), errs)
open(OUT, 'a').write(tail + '\n')
print(tail, flush=True)

# ── 4. 清理测试号的 token 存档 ──
try:
    mgr._token_file(ALT).unlink()
    print('已清理测试号存档', flush=True)
except Exception:
    pass
