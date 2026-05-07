"""用现有的 trade_summary.csv + signals_log.csv 跑一遍归因，验证 5 份报告全部产出。

不依赖 pytest，直接运行即可：
    python my_strategy/tests/test_attribution_run.py
"""
import sys
import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import attribution


EXPECTED_FILES = [
    'trade_profile.csv',
    'top_trades.csv',
    'bottom_trades.csv',
    'sector_winrate.csv',
    'factor_alpha.csv',
    'exit_reason_stats.csv',
    'add_count_stats.csv',
    'entry_condition_stats.csv',
    'yearly_stats.csv',
    'first_buy_size_stats.csv',
    'add_block_stats.csv',
    'mfe_mae_by_exit.csv',
    'mfe_distribution.csv',
    'dea_lookback_stats.csv',
    'monthly_stats.csv',
    'hs300_dif_stats.csv',
    'hs300_bull_align_stats.csv',
    'stock_bull_align_stats.csv',
    'stock_above_ma25_stats.csv',
    'regime_combo_stats.csv',
]


def main():
    cfg = json.loads((PROJECT_ROOT / 'config.json').read_text(encoding='utf-8'))

    sig_path = PROJECT_ROOT / cfg['signals_log_path']
    trade_path = PROJECT_ROOT / 'results' / 'trade_summary.csv'
    out_dir = PROJECT_ROOT / cfg['attribution_report_dir']

    print(f"[input] signals_log: {sig_path} (exists={sig_path.exists()})")
    print(f"[input] trade_summary: {trade_path} (exists={trade_path.exists()})")
    print(f"[output] report dir: {out_dir}")
    assert sig_path.exists(), "signals_log.csv 不存在，先跑回测"
    assert trade_path.exists(), "trade_summary.csv 不存在，先跑回测"

    sig_df = pd.read_csv(sig_path)
    trade_df = pd.read_csv(trade_path)
    print(f"\n[stats] signals rows = {len(sig_df)}, trade rows = {len(trade_df)}")
    print(f"[stats] signals cols = {list(sig_df.columns)}")
    factor_cols = [c for c in sig_df.columns if c.startswith('factor_')]
    pct_cols = [c for c in sig_df.columns if c.startswith('pct_')]
    print(f"[stats] factor_* 列 ({len(factor_cols)}): {factor_cols}")
    print(f"[stats] pct_* 列 ({len(pct_cols)}): {pct_cols}")
    sector_filled = sig_df['sector'].notna().sum() if 'sector' in sig_df.columns else 0
    print(f"[stats] signals 中有 sector 值的行数: {sector_filled} / {len(sig_df)}")

    print("\n=== 调用 attribution.run() ===")
    attribution.run(PROJECT_ROOT, cfg)

    print("\n=== 校验产物 ===")
    all_ok = True
    for fname in EXPECTED_FILES:
        fp = out_dir / fname
        if fp.exists():
            df = pd.read_csv(fp)
            print(f"  [OK] {fname}: {len(df)} 行, 列={list(df.columns)}")
        else:
            print(f"  [MISSING] {fname}")
            all_ok = False

    if all_ok:
        print("\n所有归因报告产出成功。")
        return 0
    print("\n部分报告缺失，请检查上面输出。")
    return 1


if __name__ == '__main__':
    sys.exit(main())
