import pandas as pd
from pathlib import Path

# (源列, 目标分位列, 反向排名)
PCT_FACTORS = [
    ('factor_momentum_60d',      'pct_momentum_60d',       False),
    ('factor_ma60_dist',         'pct_ma60_dist',          False),
    ('factor_macd_strength',     'pct_macd_strength',      False),
    ('roe',                      'pct_roe',                False),
    ('pe_ttm',                   'pct_pe',                 True),   # 低 PE → 高分位
    ('netprofit_yoy',            'pct_netprofit_yoy',      False),
    ('factor_sector_momentum_60d', 'pct_sector_momentum_60d', False),
]


def compute_cross_section_pct(df: pd.DataFrame) -> pd.DataFrame:
    """对长表（多股票多日）计算每日横截面百分位排名（0~1）。"""
    out = df.copy()
    for src, dst, reverse in PCT_FACTORS:
        if src not in out.columns:
            out[dst] = pd.NA
            continue
        ranks = out.groupby('trade_date')[src].rank(pct=True, na_option='keep')
        if reverse:
            ranks = 1.0 - ranks
        out[dst] = ranks.round(6)
    return out


def process_indicators_dir(indicators_dir):
    """读取 indicators 目录所有 CSV，计算横截面分位数后写回。"""
    indicators_dir = Path(indicators_dir)
    files = sorted(indicators_dir.glob('*.csv'))
    if not files:
        return

    print(f"reading {len(files)} indicator files...")
    parts = []
    for f in files:
        df = pd.read_csv(f, parse_dates=['trade_date'])
        df['_ts_code'] = f.stem
        parts.append(df)
    big = pd.concat(parts, ignore_index=True)
    big = compute_cross_section_pct(big)

    for f in files:
        ts_code = f.stem
        sub = big[big['_ts_code'] == ts_code].drop(columns=['_ts_code'])
        sub.to_csv(f, index=False)


def main():
    import json
    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())
    data_dir = project_root / cfg['data_dir']
    process_indicators_dir(data_dir / 'indicators')
    print("cross-section pct done")


if __name__ == '__main__':
    main()
