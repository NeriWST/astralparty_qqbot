# -*- coding: utf-8 -*-
"""回放插件挂载补丁：在 astral-bot-new 目录运行 python3 apply_replay_glue.py
qq_bot.py 仅增加一段容错挂载代码（本文件是唯一改动点）。"""
import pathlib

p = pathlib.Path("qq_bot.py")
t = p.read_text(encoding="utf-8")
OLD = "if __name__ == '__main__':"
assert t.count(OLD) == 1, "锚点缺失或不唯一（可能已打过）"
BLOCK = "# ===== 回放小地图视频插件（可拔插；REPLAY_PLUGIN=0 可禁用）=====\ntry:\n    import replay_glue\n    replay_glue.mount()\nexcept Exception as e:\n    print('[replay] 插件加载失败（主功能不受影响）:', e)\n# ===== 插件挂载结束 =====\n\nif __name__ == '__main__':"
t = t.replace(OLD, BLOCK, 1)
p.write_text(t, encoding="utf-8")
print("patched: qq_bot.py（1 处挂载段，仅此一处改动）")