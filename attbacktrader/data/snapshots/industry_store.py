"""Parquet snapshot helpers for Shenwan industry reference data."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from attbacktrader.data import ShenwanIndustryClassification, StockIndustryMembership


def shenwan_classification_snapshot_path(snapshot_root: str | Path, *, source: str = "SW2021") -> Path:
    return Path(snapshot_root) / "industries" / "sw" / source / "classifications.parquet"


def stock_industry_membership_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    source: str = "SW2021",
) -> Path:
    safe_symbol = symbol.replace(".", "_")
    return Path(snapshot_root) / "industries" / "sw" / source / "memberships" / f"{safe_symbol}.parquet"


def write_shenwan_classifications_parquet(
    classifications: Sequence[ShenwanIndustryClassification],
    path: str | Path,
) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write industry Parquet snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "index_code": classification.index_code,
                "industry_name": classification.industry_name,
                "level": classification.level,
                "industry_code": classification.industry_code,
                "parent_code": classification.parent_code,
                "source": classification.source,
            }
            for classification in classifications
        ]
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def read_shenwan_classifications_parquet(path: str | Path) -> tuple[ShenwanIndustryClassification, ...]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read industry Parquet snapshots") from exc

    frame = pd.read_parquet(Path(path))
    classifications = [
        ShenwanIndustryClassification(
            index_code=str(row.index_code),
            industry_name=str(row.industry_name),
            level=int(row.level),
            industry_code=str(row.industry_code),
            parent_code=str(row.parent_code),
            source=str(row.source),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(classifications, key=lambda item: (item.level, item.index_code)))


def write_stock_industry_memberships_parquet(
    memberships: Sequence[StockIndustryMembership],
    path: str | Path,
) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write industry Parquet snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "symbol": membership.symbol,
                "stock_name": membership.stock_name,
                "level1_code": membership.level1_code,
                "level1_name": membership.level1_name,
                "level2_code": membership.level2_code,
                "level2_name": membership.level2_name,
                "level3_code": membership.level3_code,
                "level3_name": membership.level3_name,
                "in_date": membership.in_date.isoformat(),
                "out_date": membership.out_date.isoformat() if membership.out_date else None,
                "is_new": membership.is_new,
                "source": membership.source,
            }
            for membership in memberships
        ]
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def read_stock_industry_memberships_parquet(path: str | Path) -> tuple[StockIndustryMembership, ...]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read industry Parquet snapshots") from exc

    frame = pd.read_parquet(Path(path))
    memberships = [
        StockIndustryMembership(
            symbol=str(row.symbol),
            stock_name=str(row.stock_name),
            level1_code=str(row.level1_code),
            level1_name=str(row.level1_name),
            level2_code=str(row.level2_code),
            level2_name=str(row.level2_name),
            level3_code=str(row.level3_code),
            level3_name=str(row.level3_name),
            in_date=date.fromisoformat(str(row.in_date)),
            out_date=_optional_iso_date(row.out_date),
            is_new=bool(row.is_new),
            source=str(row.source),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(memberships, key=lambda item: (item.symbol, item.in_date, item.level3_code)))


def _optional_iso_date(value) -> date | None:
    if value is None:
        return None
    text = str(value)
    if text in {"", "None", "NaT", "nan"}:
        return None
    return date.fromisoformat(text)
