"""Pure statistics model shared by text and image presentation."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def average(rows, field):
    values = [r[field] for r in rows if r.get(field) is not None]
    return round(sum(values) / len(values)) if values else None


def summarize(rows):
    wins = sum(r.get('win') is True for r in rows)
    losses = sum(r.get('win') is False for r in rows)
    return {'count': len(rows), 'wins': wins, 'losses': losses,
            'unknown': len(rows) - wins - losses,
            'winrate': round(100 * wins / (wins + losses), 1) if wins + losses else None,
            'damage': average(rows, 'damage'), 'transfer': average(rows, 'transfer'),
            'damage_count': sum(r.get('damage') is not None for r in rows),
            'transfer_count': sum(r.get('transfer') is not None for r in rows)}


def normalize_rows(rows):
    result = []
    for row in list(rows)[:10]:
        r = dict(row)
        rank = int(r.get('rank') or 0)
        if 'win' not in r:
            r['win'] = rank == 1 if rank > 0 else None
        r['hero'] = str(r.get('hero') or '未知角色')
        r.setdefault('mode', '未知模式')
        r.setdefault('damage', None)
        r.setdefault('transfer', None)
        result.append(r)
    return result


@dataclass
class StatsReport:
    profile: dict
    rows: list
    summary: dict
    heroes: list
    modes: list
    view: str
    hero: str
    sample_count: int
    battle_type: str
    date_label: str
    missing_time: int

    @property
    def scope(self):
        mode = {'pve': 'PVE', 'pvp': 'PVP', 'all': '全部模式'}[self.battle_type]
        period = f'今日 {self.date_label}（UTC+8）' if self.view == 'recent' else '最近记录'
        return f'{period} · {mode} · 来源最近 {self.sample_count} 条'


def build_report(profile, rows, view='overview', hero='', battle_type='pve', now=None):
    if view not in ('overview', 'recent', 'hero'):
        raise ValueError('未知战绩视图')
    if battle_type not in ('pve', 'pvp', 'all'):
        raise ValueError('未知对局模式')
    normalized = normalize_rows(rows)
    sample_count = len(normalized)
    def matches(row):
        mode_id = row.get('mode_id')
        if mode_id is not None:
            return mode_id in (2, 4) if battle_type == 'pve' else mode_id == 1
        return row['mode'] == ('合作挑战' if battle_type == 'pve' else '标准对战')
    if battle_type != 'all':
        normalized = [row for row in normalized if matches(row)]
    date_label, missing_time = '', 0
    if view == 'recent':
        if now is not None and now.tzinfo is None:
            raise ValueError('筛选日期必须包含时区')
        local_now = now.astimezone(BEIJING) if now is not None else datetime.now(BEIJING)
        start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        date_label = start.strftime('%Y-%m-%d')
        dated = []
        for row in normalized:
            try:
                timestamp = int(row.get('time') or 0)
            except (ValueError, TypeError, OverflowError):
                timestamp = 0
            if timestamp <= 0:
                missing_time += 1
            elif start.timestamp() <= timestamp < end.timestamp():
                dated.append(row)
        normalized = dated
    if view == 'hero':
        if not hero:
            raise ValueError('请指定角色名称')
        normalized = [r for r in normalized if r['hero'] == hero]
    grouped, modes = defaultdict(list), defaultdict(list)
    for row in normalized:
        grouped[row['hero']].append(row)
        modes[row['mode']].append(row)
    hero_stats = [(name, summarize(items)) for name, items in grouped.items()]
    hero_stats.sort(key=lambda item: (-item[1]['count'], item[0]))
    return StatsReport(dict(profile), normalized, summarize(normalized), hero_stats,
                       [(name, summarize(items)) for name, items in modes.items()],
                       view, hero, sample_count, battle_type, date_label, missing_time)


def number(value):
    return '—' if value is None else f'{value:,}' if isinstance(value, int) else str(value)


def percent(value):
    return '—' if value is None else f'{value:.1f}%'


def format_report(report):
    p, s = report.profile, report.summary
    label = {'overview': '战绩总览', 'recent': '今日战绩', 'hero': '角色战绩'}[report.view]
    lines = [f"【{label}】{p.get('nick', '未知玩家')}（UID {p.get('uid', '—')}）"]
    lines.append('范围：' + report.scope)
    lines.append('协议仅提供最近记录，筛选结果不保证覆盖当日全部对局。')
    if report.missing_time:
        lines.append(f'{report.missing_time} 条记录缺少时间，无法归入今日，已排除。')
    if p.get('records_error'):
        lines.append('近期对局获取失败，请稍后重试。')
    if p.get('stale'):
        lines.append('部分资料未能刷新，当前包含缓存数据。')
    if report.hero:
        lines.append(f'角色：{report.hero}（仅统计最近 {report.sample_count} 场内的记录）')
    if report.battle_type == 'all' and report.view == 'overview' and p.get('total') is not None:
        lines.append(f"累计 {number(p['total'])} 场｜胜场 {number(p.get('wins'))}｜胜率 {percent(p.get('winrate'))}")
    elif p.get('source') == 'public':
        lines.append('公开档案：累计数据未提供')
    lines.append(f"匹配 {s['count']} 场｜{s['wins']} 胜 {s['losses']} 负｜胜率 {percent(s['winrate'])}")
    if s['unknown']:
        lines.append(f"其中 {s['unknown']} 场结果未知，不计入胜率")
    lines.append(f"场均伤害 {number(s['damage'])}（{s['damage_count']} 场）｜场均转账 {number(s['transfer'])}（{s['transfer_count']} 场）")
    for row in report.rows:
        outcome = '胜' if row['win'] is True else '负' if row['win'] is False else '未知'
        lines.append(f"· [{row['mode']}] {row['hero']}｜{outcome}｜伤害 {number(row['damage'])}｜转账 {number(row['transfer'])}")
    if not report.rows:
        lines.append('暂无符合条件的对局记录')
    lines.append('— 为未提供数据；场均仅计算对应指标有数据的对局。')
    return '\n'.join(lines)
