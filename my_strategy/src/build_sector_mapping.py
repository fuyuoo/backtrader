"""构建 ts_code → sw_index_code 映射，写回 stock_sector.csv 新增列。

用法：
    python -m my_strategy.src.build_sector_mapping
"""
import json
import sys
from pathlib import Path

import pandas as pd
import tushare as ts


def fetch_mapping(pro, sw_codes):
    """对每个 SW 一级行业拉成分股清单，构建 ts_code → sw_code 单值映射。

    只取 out_date IS NULL 的当前成分（非时变映射）。
    一对多冲突时 raise。
    """
    mapping = {}
    for sw_code in sw_codes:
        members = pro.index_member(index_code=sw_code)
        if members is None or members.empty:
            print(f"  {sw_code}: 无成分数据，跳过")
            continue
        current = members[members['out_date'].isna()]
        for ts_code in current['con_code'].unique():
            if ts_code in mapping and mapping[ts_code] != sw_code:
                raise ValueError(
                    f"{ts_code} 同时属于 {mapping[ts_code]} 和 {sw_code}，"
                    f"无法构建单值映射")
            mapping[ts_code] = sw_code
    return mapping


def merge_to_csv(stock_sector_csv, mapping, min_coverage=0.0):
    """读取 stock_sector.csv，新增 sw_index_code 列写回。

    覆盖率 < min_coverage 抛 ValueError；95-100% 打印未映射股票数；100% 静默通过。
    返回实际覆盖率（float, 0~1）。
    """
    df = pd.read_csv(stock_sector_csv)
    if 'sw_index_code' in df.columns:
        df = df.drop(columns=['sw_index_code'])
    df['sw_index_code'] = df['ts_code'].map(mapping)

    n_total = len(df)
    n_mapped = df['sw_index_code'].notna().sum()
    coverage = n_mapped / n_total if n_total else 1.0

    if coverage < min_coverage:
        unmapped = df[df['sw_index_code'].isna()]['ts_code'].head(20).tolist()
        raise ValueError(
            f"覆盖率 {coverage:.2%} 低于阈值 {min_coverage:.2%}，"
            f"未映射股票示例（前 20）: {unmapped}")

    if coverage < 1.0:
        unmapped = df[df['sw_index_code'].isna()]['ts_code'].tolist()
        print(f"覆盖率 {coverage:.2%}，未映射 {len(unmapped)} 只股票")

    df.to_csv(stock_sector_csv, index=False)
    return coverage


def main():
    project_root = Path(__file__).resolve().parents[2]
    cfg = json.loads((project_root / 'my_strategy' / 'config.json').read_text(encoding='utf-8'))
    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    mapping = fetch_mapping(pro, cfg['sw_index_codes'])
    print(f"映射构建完成：{len(mapping)} 只股票")

    stock_sector_csv = project_root / 'my_strategy' / cfg['data_paths']['stock_sector_csv']
    coverage = merge_to_csv(stock_sector_csv, mapping)
    print(f"已写回 {stock_sector_csv}，覆盖率 {coverage:.2%}")


if __name__ == '__main__':
    main()
