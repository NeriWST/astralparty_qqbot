"""Query orchestration: protocol adapters -> report model -> text/image."""
from dataclasses import dataclass
from datetime import datetime
import bot_ext
from stats_report import build_report, format_report, BEIJING


@dataclass(frozen=True)
class QueryResult:
    text: str
    image: bytes | None = None


class StatsQuery:
    def __init__(self, manager, images=False):
        self.manager = manager
        self.images = images

    def mine(self, openid, view='overview', hero='', battle_type='pve'):
        profile, error = self.manager.get_profile(openid)
        if profile is None:
            return QueryResult(error)
        return self.present(profile, view, hero, battle_type)

    def player(self, uid, requester=None, view='overview', hero='', battle_type='pve'):
        if view == 'recent':
            return QueryResult('公开 UID 查询没有对局时间，无法查询今日战绩。请登录自己的账号后使用 /atp me recent。')
        result = bot_ext.query_uid(self.manager, uid, prefer_uid=requester)
        if not result.get('ok'):
            return QueryResult(result.get('msg') or '查询失败')
        return self.present(bot_ext.public_profile(uid, result), view, hero, battle_type)

    def present(self, profile, view='overview', hero='', battle_type='pve'):
        # Text and image use exactly the same sample and missing-data policy.
        rows = profile.get('recent', [])[:10]
        now = datetime.now(BEIJING)
        report = build_report(profile, rows, view, hero, battle_type, now=now)
        if self.images:
            enriched = bot_ext.replay_rows(dict(profile, recent=report.rows))
            enriched_report = build_report(profile, enriched, view, hero, battle_type, now=now)
            enriched_report.sample_count = report.sample_count
            enriched_report.missing_time = report.missing_time
            report = enriched_report
        text = format_report(report)
        image = None
        if self.images:
            try:
                from bot_viz import render_report_png
                image = render_report_png(report)
            except Exception as error:
                print('[stats] 图片生成失败，回退文字:', type(error).__name__)
        return QueryResult(text, image)
