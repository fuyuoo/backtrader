"""幂等地确保 stock_list.csv 含 list_date / delist_date / industry 三列。

用法：
    python -m my_strategy.tools.ensure_stock_list_metadata

- 若三列俱全则不调用 Tushare API，仅打印一行说明
- 否则调用 pro.stock_basic(list_status='L/D/P') 分三次拉取完整元数据
- 与现有 stock_list.csv 做 left join（保留现有 universe）
- 写回 stock_list.csv（原地覆盖；行内备份为 stock_list.csv.bak）

token 读取方式：优先用 config.json['tushare_token']，
fallback 到 data/tushare_token.json['token']。
"""
import json
import shutil
from pathlib import Path

import pandas as pd

REQUIRED_COLS = ('list_date', 'delist_date', 'industry')


def has_required_columns(df: pd.DataFrame) -> bool:
    return all(c in df.columns for c in REQUIRED_COLS)


def merge_metadata(existing: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    """Left-join existing on metadata。existing universe 不变。"""
    cols_to_take = ['ts_code', 'list_date', 'delist_date', 'industry']
    sub = metadata[[c for c in cols_to_take if c in metadata.columns]]
    return existing.merge(sub, on='ts_code', how='left', suffixes=('', '_meta'))


def _load_token(project_root: Path) -> str:
    config_path = project_root / 'config.json'
    if config_path.exists():
        with open(config_path, 'r') as f:
            cfg = json.load(f)
        if 'tushare_token' in cfg:
            return cfg['tushare_token']
    # fallback
    token_path = project_root / 'data' / 'tushare_token.json'
    with open(token_path, 'r') as f:
        return json.load(f)['token']


def fetch_stock_basic_via_tushare(project_root: Path) -> pd.DataFrame:
    """调用 pro.stock_basic 拉取 list_status L/D/P 全量元数据。"""
    import tushare as ts
    token = _load_token(project_root)
    ts.set_token(token)
    pro = ts.pro_api()
    parts = []
    for status in ('L', 'D', 'P'):
        df = pro.stock_basic(
            list_status=status,
            fields='ts_code,name,industry,list_date,delist_date',
        )
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def main(project_root: Path = None) -> None:
    project_root = project_root or Path(__file__).resolve().parent.parent
    list_path = project_root / 'stock_list.csv'

    existing = pd.read_csv(list_path)
    if has_required_columns(existing):
        print(f"[ensure_stock_list_metadata] {list_path} 已含 list_date/delist_date/industry，跳过。")
        return

    print(f"[ensure_stock_list_metadata] 缺少元数据列，调用 Tushare pro.stock_basic ...")
    metadata = fetch_stock_basic_via_tushare(project_root)
    merged = merge_metadata(existing, metadata)

    # 备份原文件
    backup = list_path.with_suffix('.csv.bak')
    shutil.copy(list_path, backup)
    merged.to_csv(list_path, index=False)
    n_with = merged['list_date'].notna().sum()
    n_total = len(merged)
    print(f"[ensure_stock_list_metadata] 写回 {list_path}（备份 {backup}）；"
          f"{n_with}/{n_total} 行成功匹配 list_date。")


if __name__ == '__main__':
    main()
