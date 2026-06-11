"""Prepare attribution reference snapshots from all-A daily feature rows."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from attbacktrader.cli.tushare_options import add_tushare_rate_limit_args, tushare_rate_limit_config_from_args
from attbacktrader.data.providers import TushareProvider, read_tushare_token
from attbacktrader.data.snapshots import (
    DEFAULT_REFERENCE_UNIVERSE,
    apply_industry_memberships_to_frame,
    attribution_reference_snapshot_dir,
    build_attribution_reference_snapshot_from_frame,
    load_or_fetch_all_industry_memberships,
    load_or_fetch_industry_memberships_for_symbols,
    write_attribution_reference_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_defaults = _run_defaults_from_args(args)
    start_date = date.fromisoformat(args.start_date or run_defaults["start_date"])
    end_date = date.fromisoformat(args.end_date or run_defaults["end_date"])
    frame = _load_input_frame(Path(args.input)) if args.input is not None else _fetch_provider_frame(args, start_date, end_date)
    emit_scope = _run_entry_scope(args.run_dir) if args.emit_run_entry_scope else {"symbols": [], "dates": [], "pairs": []}
    snapshot = build_attribution_reference_snapshot_from_frame(
        frame,
        start_date=start_date,
        end_date=end_date,
        reference_universe=args.reference_universe,
        min_reference_count=args.min_reference_count,
        emit_symbols=emit_scope["symbols"],
        emit_dates=emit_scope["dates"],
        emit_symbol_date_pairs=emit_scope["pairs"],
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else attribution_reference_snapshot_dir(
            args.snapshot_root,
            reference_universe=args.reference_universe,
            start_date=start_date,
            end_date=end_date,
        )
    )
    metadata_path, reference_json_path, values_path = write_attribution_reference_snapshot(snapshot, output_dir)
    print(
        json.dumps(
            {
                "schema": snapshot["metadata"]["schema"],
                "reference_universe": args.reference_universe,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "requested_start_date": args.start_date,
                "requested_end_date": args.end_date,
                "effective_start_date": start_date.isoformat(),
                "effective_end_date": end_date.isoformat(),
                "run_dir": args.run_dir,
                "reference_fetch_scope": args.reference_fetch_scope,
                "symbol_count": len(_symbols_from_args(args, run_defaults=run_defaults)),
                "emit_run_entry_scope": args.emit_run_entry_scope,
                "emit_symbol_count": len(emit_scope["symbols"]),
                "emit_date_count": len(emit_scope["dates"]),
                "emit_pair_count": len(emit_scope["pairs"]),
                "row_count": snapshot["row_count"],
                "exception_count": snapshot["metadata"]["exception_count"],
                "artifacts": {
                    "metadata_path": str(metadata_path),
                    "reference_json_path": str(reference_json_path),
                    "reference_values_parquet_path": str(values_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare attribution reference snapshots")
    parser.add_argument("--input", default=None, help="All-A daily feature CSV/Parquet input")
    parser.add_argument("--provider", choices=["tushare"], default=None, help="Fetch all-A reference input from a provider")
    parser.add_argument("--run-dir", default=None, help="Run artifact directory used to infer symbols and dates")
    parser.add_argument(
        "--run-warmup-trading-days",
        type=int,
        default=90,
        help="When --run-dir supplies start date, fetch this many business days before run.from_date.",
    )
    parser.add_argument(
        "--emit-run-entry-scope",
        action="store_true",
        help="With --run-dir, write reference rows only for completed trade entry symbol/date pairs.",
    )
    parser.add_argument("--symbol", action="append", default=[], help="Repeatable symbol whitelist for provider fetch")
    parser.add_argument("--symbol-file", default=None, help="Text file with one symbol per line for provider fetch")
    parser.add_argument(
        "--reference-fetch-scope",
        choices=["run_symbols", "all"],
        default="run_symbols",
        help="Provider fetch universe: run_symbols keeps the existing whitelist behavior; all fetches all-A rows for cross-section reference.",
    )
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--snapshot-root", default="data/snapshots")
    parser.add_argument("--reference-universe", default=DEFAULT_REFERENCE_UNIVERSE)
    parser.add_argument("--industry-source", default="SW2021")
    parser.add_argument(
        "--fetch-industry-memberships",
        action="store_true",
        help="With --provider tushare, fetch/cache per-symbol SW industry memberships and merge by effective interval.",
    )
    parser.add_argument(
        "--refresh-industry-memberships",
        action="store_true",
        help="Refresh industry membership snapshots even when cached files exist.",
    )
    parser.add_argument("--min-reference-count", type=int, default=100)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--raw-cache-dir",
        default=None,
        help="Optional parquet cache directory for per-trade-date raw Tushare reference API responses.",
    )
    add_tushare_rate_limit_args(parser)
    args = parser.parse_args(argv)
    if args.input is None and args.provider is None:
        parser.error("--input or --provider is required")
    if args.input is not None and args.provider is not None:
        parser.error("--input and --provider are mutually exclusive")
    if (args.start_date is None or args.end_date is None) and args.run_dir is None:
        parser.error("--start-date/--end-date are required unless --run-dir is provided")
    if args.emit_run_entry_scope and args.run_dir is None:
        parser.error("--emit-run-entry-scope requires --run-dir")
    if args.run_warmup_trading_days < 0:
        parser.error("--run-warmup-trading-days must be greater than or equal to 0")
    return args


def _load_input_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"input does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported input extension: {suffix}")


def _fetch_provider_frame(args: argparse.Namespace, start_date: date, end_date: date) -> pd.DataFrame:
    if args.provider != "tushare":
        raise ValueError(f"unsupported provider: {args.provider}")
    provider = TushareProvider(
        read_tushare_token(args.token_file),
        rate_limit=tushare_rate_limit_config_from_args(args),
    )
    symbols = _symbols_from_args(args, run_defaults=_run_defaults_from_args(args))
    fetch_symbols = None if args.reference_fetch_scope == "all" else symbols or None
    fetch_kwargs = {
        "start_date": start_date,
        "end_date": end_date,
        "symbols": fetch_symbols,
    }
    if args.raw_cache_dir is not None:
        fetch_kwargs["raw_cache_dir"] = args.raw_cache_dir
    frame = provider.fetch_attribution_reference_frame_for_symbols(**fetch_kwargs)
    if not args.fetch_industry_memberships:
        return frame
    symbols = sorted(str(symbol) for symbol in frame["symbol"].dropna().unique())
    if args.reference_fetch_scope == "all":
        memberships = load_or_fetch_all_industry_memberships(
            snapshot_root=args.snapshot_root,
            provider=provider,
            source=args.industry_source,
            refresh=args.refresh_industry_memberships,
        )
        if not memberships:
            memberships = load_or_fetch_industry_memberships_for_symbols(
                symbols,
                snapshot_root=args.snapshot_root,
                provider=provider,
                source=args.industry_source,
                refresh=args.refresh_industry_memberships,
            )
    else:
        memberships = load_or_fetch_industry_memberships_for_symbols(
            symbols,
            snapshot_root=args.snapshot_root,
            provider=provider,
            source=args.industry_source,
            refresh=args.refresh_industry_memberships,
        )
    return apply_industry_memberships_to_frame(frame, memberships)


def _run_defaults_from_args(args: argparse.Namespace) -> dict[str, object]:
    if args.run_dir is None:
        return {"symbols": [], "start_date": None, "end_date": None}
    run_dir = Path(args.run_dir)
    run_plan_path = run_dir / "run_plan.json"
    if not run_plan_path.exists():
        raise FileNotFoundError(f"run_plan.json does not exist under run dir: {run_dir}")
    run_plan = json.loads(run_plan_path.read_text(encoding="utf-8"))
    run = run_plan.get("run") if isinstance(run_plan.get("run"), dict) else {}
    data = run_plan.get("data") if isinstance(run_plan.get("data"), dict) else {}
    run_start = str(run.get("from_date") or "")
    run_end = str(run.get("to_date") or "")
    if not run_start or not run_end:
        raise ValueError(f"run_plan.json must contain run.from_date and run.to_date: {run_plan_path}")
    symbols = _symbols_from_run_data(data, run_plan_path=run_plan_path)
    start = _business_days_before(date.fromisoformat(run_start), args.run_warmup_trading_days).isoformat()
    return {"symbols": symbols, "start_date": start, "end_date": run_end}


def _symbols_from_run_data(data: dict[str, object], *, run_plan_path: Path) -> list[str]:
    symbols: list[str] = []
    for item in data.get("tradable_series") or []:
        if isinstance(item, dict):
            symbol = item.get("symbol")
            if symbol:
                symbols.append(str(symbol))
        elif item:
            symbols.append(str(item))
    for item in data.get("symbols") or []:
        if item:
            symbols.append(str(item))
    stock_pool_file = data.get("stock_pool_file")
    if stock_pool_file:
        symbols.extend(_symbols_from_stock_pool_file(str(stock_pool_file), run_plan_path=run_plan_path))
    return _dedupe_symbols(symbols)


def _symbols_from_stock_pool_file(path_text: str, *, run_plan_path: Path) -> list[str]:
    candidates = []
    raw_path = Path(path_text)
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.extend([
            Path.cwd() / raw_path,
            run_plan_path.parent / raw_path,
            run_plan_path.parent.parent / raw_path,
        ])
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"stock pool file does not exist: {path_text}")
    frame = pd.read_csv(path)
    for column in ("ts_code", "symbol", "code"):
        if column in frame.columns:
            return [str(item).strip() for item in frame[column].dropna().tolist() if str(item).strip()]
    raise ValueError(f"stock pool file must contain ts_code, symbol, or code column: {path}")


def _business_days_before(value: date, trading_days: int) -> date:
    if trading_days == 0:
        return value
    days = pd.bdate_range(end=value, periods=trading_days + 1)
    return days[0].date()


def _run_entry_scope(run_dir: str | None) -> dict[str, list[str]]:
    if run_dir is None:
        return {"symbols": [], "dates": [], "pairs": []}
    path = Path(run_dir) / "trade_attribution.json"
    if not path.exists():
        raise FileNotFoundError(f"trade_attribution.json does not exist under run dir: {run_dir}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    signal_dates = _signal_dates_by_trade_index(Path(run_dir))
    symbols = []
    dates = []
    pairs = []
    for item in payload.get("attributions") or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        entry_date = item.get("entry_date")
        if symbol and entry_date:
            symbols.append(str(symbol))
            dates.append(str(entry_date))
            pairs.append((str(symbol), str(entry_date)))
        trade_index = _optional_int(item.get("trade_index"))
        signal_date = signal_dates.get(trade_index) if trade_index is not None else None
        if symbol and signal_date:
            symbols.append(str(symbol))
            dates.append(str(signal_date))
            pairs.append((str(symbol), str(signal_date)))
    return {"symbols": _dedupe_symbols(symbols), "dates": _dedupe_symbols(dates), "pairs": _dedupe_pairs(pairs)}


def _signal_dates_by_trade_index(run_dir: Path) -> dict[int, str]:
    path = run_dir / "trade_lifecycle.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[int, str] = {}
    for lifecycle in payload.get("lifecycles") or []:
        if not isinstance(lifecycle, dict):
            continue
        trade_index = _optional_int(lifecycle.get("trade_index"))
        if trade_index is None:
            continue
        for event in lifecycle.get("events") or []:
            if not isinstance(event, dict) or str(event.get("event_type")) != "entry":
                continue
            values = event.get("values") if isinstance(event.get("values"), dict) else {}
            signal_date = values.get("signal_trade_date")
            if signal_date:
                result[trade_index] = str(signal_date)
                break
    return result


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _symbols_from_args(args: argparse.Namespace, *, run_defaults: dict[str, object] | None = None) -> list[str]:
    symbols = [str(symbol).strip() for symbol in args.symbol if str(symbol).strip()]
    symbols.extend(str(symbol).strip() for symbol in (run_defaults or {}).get("symbols", []) if str(symbol).strip())
    if args.symbol_file is not None:
        path = Path(args.symbol_file)
        if not path.exists():
            raise FileNotFoundError(f"symbol file does not exist: {path}")
        symbols.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return _dedupe_symbols(symbols)


def _dedupe_symbols(symbols: list[str]) -> list[str]:
    result = []
    seen = set()
    for symbol in symbols:
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def _dedupe_pairs(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result = []
    seen = set()
    for pair in pairs:
        if pair in seen:
            continue
        seen.add(pair)
        result.append(pair)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
