# -*- coding: utf-8 -*-
"""build_features.py - 特征工程：rounds.csv + players.csv → features.csv（全向量化版，秒级）
每行 = 一名玩家的一局，列 = 基础总计 + 率指标 + 窗口指标 + 曲线特征 + 结果变量
用法：python build_features.py     （放在 data_pack_* 上级文件夹运行）
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
KEY = ['replay_id', 'uid']
WMAX = 10   # 窗口阶梯上限：1_1 ~ 1_10 全档
COLS = ['kill', 'dmg', 'inj', 'gold', 'transfer', 'tret', 'move']


def pack_dirs():
    """pack 目录列表：先找脚本同级，再找上级（11.22 工作区布局：pack 在 实验数据集 根）"""
    return sorted(ROOT.glob('data_pack_*')) or sorted(ROOT.parent.glob('data_pack_*'))


def read_csv_robust(path):
    """编码回退读取：utf-8-sig → gbk → latin-1（防 Excel 重存改编码）"""
    for enc in ('utf-8-sig', 'gbk', 'latin-1'):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    sys.exit(f'无法读取 {path}：三种编码都失败，文件可能已损坏')


def load(name):
    files = [d / name for d in pack_dirs() if (d / name).exists()]
    if not files:
        files = sorted(glob.glob(str(ROOT / 'data' / name)))
    if not files:
        sys.exit(f'找不到 {name}，请确认本脚本与 data_pack_XX 文件夹同级')
    df = pd.concat([read_csv_robust(f) for f in files], ignore_index=True)
    print(f'{name}: {len(df)} 行 ← {len(files)} 个文件', flush=True)
    return df


def compute_features(pl, rd):
    """players.csv + rounds.csv → 特征宽表（供 build_features 与 validate 共用）"""
    g = rd.groupby(KEY)

    # 1) 窗口累计阶梯：1_1 ~ 1_10 全档（向量化：先筛回合再 groupby 求和）
    parts = []
    for w in range(1, WMAX + 1):
        sub = (rd[rd['round'] <= w]
               .groupby(KEY)[COLS].sum().reset_index())
        sub.columns = [c if c in KEY else f'{c}_1_{w}' for c in sub.columns]
        parts.append(sub)
    feat = parts[0]
    for p in parts[1:]:
        feat = feat.merge(p, on=KEY, how='outer')

    # 2) 伤害转化率全阶梯 conv_1_1 ~ conv_1_10
    for w in range(1, WMAX + 1):
        feat[f'conv_1_{w}'] = feat[f'dmg_1_{w}'] / (feat[f'gold_1_{w}'] + 1)

    # 3) 曲线特征（全部 groupby 向量化）
    rd2 = rd.assign(rmax=g['round'].transform('max'))
    rd2 = rd2.assign(boss_dmg=rd2['dmg'] * (rd2['boss'] == 1),
                     early_dmg=rd2['dmg'] * (rd2['round'] <= 3),
                     late_dmg=rd2['dmg'] * (rd2['round'] >= rd2['rmax'] - 2))
    cv = rd2.groupby(KEY)[['dmg', 'boss_dmg', 'early_dmg', 'late_dmg']].sum().reset_index()
    tot = cv['dmg'].replace(0, np.nan)
    cv['boss_share'] = cv['boss_dmg'] / tot
    cv['early_share'] = cv['early_dmg'] / tot
    cv['late_share'] = cv['late_dmg'] / tot
    st = g['dmg'].agg(dmg_max_round='max', dmg_std='std', dmg_mean='mean').reset_index()
    st['dmg_cv'] = st['dmg_std'] / st['dmg_mean'].replace(0, np.nan)
    # 曲线斜率用最小二乘闭式解（Σxy 公式，向量化）
    rd2 = rd2.assign(xy=rd2['round'] * rd2['dmg'], x2=rd2['round'] ** 2)
    s = (rd2.groupby(KEY)
            .agg(n=('dmg', 'size'), sx=('round', 'sum'), sy=('dmg', 'sum'),
                 sxy=('xy', 'sum'), sx2=('x2', 'sum')).reset_index())
    denom = s['n'] * s['sx2'] - s['sx'] ** 2
    s['dmg_slope'] = (s['n'] * s['sxy'] - s['sx'] * s['sy']) / denom.replace(0, np.nan)
    gg = (rd2.groupby(KEY)[['dmg', 'gold']].sum().reset_index()
            .rename(columns={'dmg': '_td', 'gold': '_tg'}))
    gg['total_dmg_per_gold'] = gg['_td'] / (gg['_tg'] + 1)

    for p in (cv[KEY + ['boss_share', 'early_share', 'late_share']],
              st[KEY + ['dmg_max_round', 'dmg_cv']],
              s[KEY + ['dmg_slope']],
              gg[KEY + ['total_dmg_per_gold']]):
        feat = feat.merge(p, on=KEY, how='left')

    return pl.merge(feat, on=KEY, how='inner')


def main():
    pl = load('players.csv').drop_duplicates(subset=KEY)
    rd = load('rounds.csv')
    out = compute_features(pl, rd)
    out.to_csv(ROOT / 'features.csv', index=False, encoding='utf-8-sig')
    print(f'\nfeatures.csv: {len(out)} 行 × {out.shape[1]} 列', flush=True)


if __name__ == '__main__':
    main()
