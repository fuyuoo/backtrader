"""BigQuant DAI provider for A-share industry reference data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from attbacktrader.data import ShenwanIndustryClassification, StockIndustryMembership

BIGQUANT_INDUSTRY_COMPONENT_TABLE = "cn_stock_industry_component"
BIGQUANT_INDUSTRY_CLASSIFICATION_TABLE = "cn_stock_industry"
DEFAULT_BIGQUANT_START_DATE = date(1990, 1, 1)

_SOURCE_ALIASES = {
    "SW2014": "sw2014",
    "SW2021": "sw2021",
    "CS": "cs",
}
_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SZ|SH|BJ)$")


@dataclass(frozen=True)
class BigQuantIndustryQueryWindow:
    start_date: date = DEFAULT_BIGQUANT_START_DATE
    end_date: date = date.today()

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")


class BigQuantIndustryProvider:
    """Fetch Shenwan industry definitions and memberships from BigQuant DAI."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        config_path: str | None = None,
        window: BigQuantIndustryQueryWindow | None = None,
        dai_module: Any | None = None,
        bigquant_module: Any | None = None,
    ) -> None:
        self._window = window or BigQuantIndustryQueryWindow()
        if dai_module is not None:
            self._dai = dai_module
            return
        try:
            import bigquant
        except ImportError as exc:
            raise RuntimeError(
                "bigquant is required to use BigQuantIndustryProvider. "
                "Install it with: pip install bigquant -i https://pypi.bigquant.com/simple/"
            ) from exc

        client = bigquant_module or bigquant
        try:
            if api_key is not None:
                client.init_from_token(api_key)
            elif config_path is not None:
                client.init_from_config(config_path)
            else:
                client.init_from_config(None)
        except Exception as exc:
            raise RuntimeError(
                "BigQuant authentication failed. Run `bq auth configure` or pass api_key explicitly."
            ) from exc
        self._dai = client.dai

    @property
    def window(self) -> BigQuantIndustryQueryWindow:
        return self._window

    def fetch_shenwan_industry_classifications(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[ShenwanIndustryClassification, ...]:
        bigquant_source = _bigquant_source(source)
        sql = f"""
SELECT
  industry_level1_name,
  industry_level1_code,
  industry_level2_name,
  industry_level2_code,
  industry_level3_name,
  industry_level3_code
FROM {BIGQUANT_INDUSTRY_CLASSIFICATION_TABLE}
WHERE industry = {_sql_literal(bigquant_source)}
"""
        frame = self._query_frame(sql)
        return bigquant_classifications_from_frame(frame, source=_project_source(source))

    def fetch_stock_industry_memberships(
        self,
        *,
        symbol: str,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        memberships = self.fetch_stock_industry_memberships_for_symbols([symbol], source=source)
        return memberships.get(symbol, ())

    def fetch_all_stock_industry_memberships(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        frame = self._fetch_component_frame(symbols=None, source=source)
        return bigquant_memberships_from_component_frame(frame, source=_project_source(source))

    def fetch_stock_industry_memberships_for_symbols(
        self,
        symbols: Sequence[str],
        *,
        source: str = "SW2021",
    ) -> dict[str, tuple[StockIndustryMembership, ...]]:
        normalized_symbols = _dedupe_symbols(symbols)
        if not normalized_symbols:
            return {}
        frame = self._fetch_component_frame(symbols=normalized_symbols, source=source)
        memberships = bigquant_memberships_from_component_frame(frame, source=_project_source(source))
        result = {symbol: () for symbol in normalized_symbols}
        for symbol, items in _group_memberships_by_symbol(memberships).items():
            result[symbol] = items
        return result

    def _fetch_component_frame(
        self,
        *,
        symbols: Sequence[str] | None,
        source: str,
    ) -> Any:
        bigquant_source = _bigquant_source(source)
        where_parts = [f"industry = {_sql_literal(bigquant_source)}"]
        if symbols is not None:
            where_parts.append(f"instrument IN ({', '.join(_sql_literal(symbol) for symbol in symbols)})")
        sql = f"""
SELECT
  date,
  industry,
  instrument,
  industry_name,
  industry_instrument,
  industry_level1_code,
  industry_level1_name,
  industry_level2_code,
  industry_level2_name,
  industry_level3_code,
  industry_level3_name
FROM {BIGQUANT_INDUSTRY_COMPONENT_TABLE}
WHERE {' AND '.join(where_parts)}
ORDER BY instrument, date
"""
        filters = {"date": [self._window.start_date.isoformat(), self._window.end_date.isoformat()]}
        return self._query_frame(sql, filters=filters)

    def _query_frame(
        self,
        sql: str,
        *,
        filters: Mapping[str, list[Any]] | None = None,
    ) -> Any:
        try:
            result = self._dai.query(sql, filters=dict(filters) if filters is not None else None)
            return result.df()
        except Exception as exc:
            raise RuntimeError(f"BigQuant DAI query failed: {exc}") from exc


def bigquant_classifications_from_frame(frame: Any, *, source: str) -> tuple[ShenwanIndustryClassification, ...]:
    _require_columns(
        frame,
        (
            "industry_level1_name",
            "industry_level1_code",
            "industry_level2_name",
            "industry_level2_code",
            "industry_level3_name",
            "industry_level3_code",
        ),
    )
    classifications: dict[tuple[int, str], ShenwanIndustryClassification] = {}
    for row in frame.itertuples(index=False):
        level1_code = _normalize_industry_code(row.industry_level1_code)
        level2_code = _normalize_industry_code(row.industry_level2_code)
        level3_code = _normalize_industry_code(row.industry_level3_code)
        _put_classification(
            classifications,
            index_code=level1_code,
            industry_name=row.industry_level1_name,
            level=1,
            parent_code="0",
            source=source,
        )
        _put_classification(
            classifications,
            index_code=level2_code,
            industry_name=row.industry_level2_name,
            level=2,
            parent_code=level1_code,
            source=source,
        )
        _put_classification(
            classifications,
            index_code=level3_code,
            industry_name=row.industry_level3_name,
            level=3,
            parent_code=level2_code,
            source=source,
        )
    return tuple(sorted(classifications.values(), key=lambda item: (item.level, item.index_code)))


def bigquant_memberships_from_component_frame(frame: Any, *, source: str) -> tuple[StockIndustryMembership, ...]:
    _require_columns(
        frame,
        (
            "date",
            "instrument",
            "industry_level1_code",
            "industry_level1_name",
            "industry_level2_code",
            "industry_level2_name",
            "industry_level3_code",
            "industry_level3_name",
        ),
    )
    rows = sorted(
        (_component_row(row, source=source) for row in frame.itertuples(index=False)),
        key=lambda item: (item["symbol"], item["trade_date"], item["level3_code"]),
    )
    memberships: list[StockIndustryMembership] = []
    current: dict[str, Any] | None = None
    previous_date_by_symbol: dict[str, date] = {}

    for row in rows:
        previous_date = previous_date_by_symbol.get(row["symbol"])
        if current is not None and row["symbol"] == current["symbol"] and _same_membership(row, current):
            previous_date_by_symbol[row["symbol"]] = row["trade_date"]
            continue
        if current is not None:
            close_date = previous_date_by_symbol[current["symbol"]]
            memberships.append(_membership_from_state(current, out_date=close_date))
        current = row
        previous_date_by_symbol[row["symbol"]] = row["trade_date"]

    if current is not None:
        memberships.append(_membership_from_state(current, out_date=None))

    return tuple(sorted(memberships, key=lambda item: (item.symbol, item.in_date, item.level3_code)))


def _component_row(row: Any, *, source: str) -> dict[str, Any]:
    symbol = str(row.instrument)
    if not _SYMBOL_PATTERN.match(symbol):
        raise ValueError(f"unsupported BigQuant stock instrument format: {symbol}")
    return {
        "symbol": symbol,
        # cn_stock_industry_component has no stock name field; membership joins consume symbol and industry fields.
        "stock_name": symbol,
        "trade_date": _parse_date(row.date),
        "level1_code": _normalize_industry_code(row.industry_level1_code),
        "level1_name": _clean_text(row.industry_level1_name),
        "level2_code": _normalize_industry_code(row.industry_level2_code),
        "level2_name": _clean_text(row.industry_level2_name),
        "level3_code": _normalize_industry_code(row.industry_level3_code),
        "level3_name": _clean_text(row.industry_level3_name),
        "source": source,
    }


def _membership_from_state(state: Mapping[str, Any], *, out_date: date | None) -> StockIndustryMembership:
    return StockIndustryMembership(
        symbol=str(state["symbol"]),
        stock_name=str(state["stock_name"]),
        level1_code=str(state["level1_code"]),
        level1_name=str(state["level1_name"]),
        level2_code=str(state["level2_code"]),
        level2_name=str(state["level2_name"]),
        level3_code=str(state["level3_code"]),
        level3_name=str(state["level3_name"]),
        in_date=state["trade_date"],
        out_date=out_date,
        is_new=True,
        source=str(state.get("source") or "SW2021"),
    )


def _same_membership(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(
        left[key] == right[key]
        for key in (
            "level1_code",
            "level1_name",
            "level2_code",
            "level2_name",
            "level3_code",
            "level3_name",
        )
    )


def _group_memberships_by_symbol(
    memberships: Iterable[StockIndustryMembership],
) -> dict[str, tuple[StockIndustryMembership, ...]]:
    grouped: dict[str, list[StockIndustryMembership]] = {}
    for membership in memberships:
        grouped.setdefault(membership.symbol, []).append(membership)
    return {
        symbol: tuple(sorted(items, key=lambda item: (item.in_date, item.level3_code)))
        for symbol, items in grouped.items()
    }


def _put_classification(
    classifications: dict[tuple[int, str], ShenwanIndustryClassification],
    *,
    index_code: str,
    industry_name: Any,
    level: int,
    parent_code: str,
    source: str,
) -> None:
    if not index_code:
        return
    classifications[(level, index_code)] = ShenwanIndustryClassification(
        index_code=index_code,
        industry_name=_clean_text(industry_name),
        level=level,
        industry_code=index_code,
        parent_code=parent_code,
        source=source,
    )


def _normalize_industry_code(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if "." in text:
        return text
    if text.isdigit():
        return f"{text}.SI"
    return text


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text = str(value)
    if " " in text:
        text = text.split(" ", 1)[0]
    if "T" in text:
        text = text.split("T", 1)[0]
    return date.fromisoformat(text)


def _bigquant_source(source: str) -> str:
    normalized = _project_source(source)
    try:
        return _SOURCE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported BigQuant industry source: {source}") from exc


def _project_source(source: str) -> str:
    return str(source).strip().upper()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _dedupe_symbols(symbols: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip()
        if not symbol:
            continue
        if not _SYMBOL_PATTERN.match(symbol):
            raise ValueError(f"unsupported stock symbol format: {symbol}")
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return result


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text in {"None", "nan", "NaT"}:
        return ""
    return text.strip()


def _require_columns(frame: Any, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"BigQuant frame missing required columns: {', '.join(missing)}")
