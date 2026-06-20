import json
from pathlib import Path

from attbacktrader.cli import entry_single_factor_candidate_screening as screening_cli
from attbacktrader.reports import (
    ENTRY_SINGLE_FACTOR_CANDIDATE_SCREENING_SCHEMA,
    build_entry_single_factor_candidate_screening_report,
    render_entry_single_factor_candidate_screening_markdown_zh,
    write_entry_single_factor_candidate_screening_report,
)


def test_entry_single_factor_candidate_screening_classifies_rows() -> None:
    report = build_entry_single_factor_candidate_screening_report(
        _single_factor_report(),
        reverse_filter_candidate_summary=_reverse_filter_summary(),
    )

    assert report["schema"] == ENTRY_SINGLE_FACTOR_CANDIDATE_SCREENING_SCHEMA
    assert report["screening_mode"] == "research_only_not_strategy_validation"
    assert report["category_counts"]["keep_candidates"] == 2
    assert report["category_counts"]["exclude_candidates"] == 1
    assert report["category_counts"]["keep_watchlist"] == 1
    assert report["category_counts"]["exclude_watchlist"] == 1
    assert report["category_counts"]["exposure_watchlist"] == 1

    keep_keys = _row_keys(report["keep_candidates"])
    assert ("entry.alpha_bucket", "good") in keep_keys
    assert ("entry.execution.signal_to_entry_return_bucket", "gap_down_2_5pct") in keep_keys
    assert ("industry.sw_l1.code", "801770.SI") not in keep_keys

    exclude_keys = _row_keys(report["exclude_candidates"])
    assert ("entry.beta_bucket", "bad") in exclude_keys

    assert _row_keys(report["keep_watchlist"]) == {("entry.gamma_bucket", "watch_keep")}
    assert _row_keys(report["exclude_watchlist"]) == {("entry.delta_bucket", "watch_exclude")}

    execution = report["entry_execution_factors"][0]
    assert execution["field_key"] == "entry.execution.signal_to_entry_return_bucket"
    assert execution["factor_kind"] == "entry_execution"
    assert execution["primary_category"] == "keep_candidates"

    exposure = report["exposure_watchlist"][0]
    assert exposure["field_key"] == "industry.sw_l1.code"
    assert exposure["direction"] == "keep"
    assert exposure["primary_category"] == "exposure_watchlist"

    all_keys = _row_keys(report["screened_rows"])
    assert ("entry.low_sample_bucket", "too_small") not in all_keys
    assert ("entry.high_missing_bucket", "missing") not in all_keys


def test_entry_single_factor_candidate_screening_renders_and_writes(tmp_path: Path) -> None:
    report = build_entry_single_factor_candidate_screening_report(
        _single_factor_report(source_dir=str(tmp_path)),
        reverse_filter_candidate_summary=_reverse_filter_summary(),
    )
    markdown = render_entry_single_factor_candidate_screening_markdown_zh(report, limit=20)
    json_path, markdown_path, csv_path = write_entry_single_factor_candidate_screening_report(
        report,
        output_dir=tmp_path / "screening",
    )

    assert "入场单因子候选筛选报告" in markdown
    assert "不是策略规则" in markdown
    assert "## Keep Candidates" in markdown
    assert "## Exposure Watchlist" in markdown
    assert json_path.exists()
    assert markdown_path.exists()
    assert csv_path.exists()
    assert "primary_category" in csv_path.read_text(encoding="utf-8").splitlines()[0]


def test_entry_single_factor_candidate_screening_cli_writes_artifacts(tmp_path: Path, capsys) -> None:
    single_path = tmp_path / "single_factor_attribution.json"
    reverse_path = tmp_path / "reverse_filter_candidate_summary.json"
    single_path.write_text(json.dumps(_single_factor_report(source_dir=str(tmp_path)), ensure_ascii=False), encoding="utf-8")
    reverse_path.write_text(json.dumps(_reverse_filter_summary(), ensure_ascii=False), encoding="utf-8")

    exit_code = screening_cli.main(
        [
            "--single-factor-attribution",
            str(single_path),
            "--reverse-filter-summary",
            str(reverse_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_SINGLE_FACTOR_CANDIDATE_SCREENING_SCHEMA
    assert stdout["category_counts"]["keep_candidates"] == 2
    assert (tmp_path / "out" / "entry_single_factor_candidate_screening.json").exists()
    assert (tmp_path / "out" / "entry_single_factor_candidate_screening.zh.md").exists()
    assert (tmp_path / "out" / "entry_single_factor_candidate_screening_rows.csv").exists()


def _single_factor_report(*, source_dir: str = "reports/screening-test") -> dict:
    overall = {
        "sample_count": 1000,
        "win_rate": 0.40,
        "average_return_pct": 0.01,
        "median_return_pct": -0.02,
        "return_on_entry_value": 0.005,
        "ma60_stop_exit_rate": 0.55,
        "profit_loss_ratio": 1.3,
        "pnl_path_max_drawdown_on_entry_value": 0.02,
        "return_volatility_pct": 0.10,
    }
    return {
        "schema": "attbacktrader.single_factor_attribution.v1",
        "run_id": "screening-test",
        "source_dir": source_dir,
        "sample_count": 1000,
        "entry_factor_count": 8,
        "overall": overall,
        "entry_single_factor_summaries": [
            _bucket("entry.alpha_bucket", "Alpha", "good", 120, 0.70, 0.050, 0.030, 0.050, 1.8, 0.30),
            _bucket("entry.beta_bucket", "Beta", "bad", 130, 0.20, -0.020, -0.030, -0.020, 0.8, 0.85),
            _bucket("entry.gamma_bucket", "Gamma", "watch_keep", 140, 0.50, 0.025, -0.010, 0.020, 1.4, 0.50),
            _bucket("entry.delta_bucket", "Delta", "watch_exclude", 150, 0.35, 0.002, -0.010, 0.001, 1.0, 0.70),
            _bucket(
                "entry.execution.signal_to_entry_return_bucket",
                "信号日close到入场成交价涨跌桶",
                "gap_down_2_5pct",
                160,
                0.65,
                0.048,
                0.039,
                0.041,
                1.7,
                0.36,
                scope="execution",
            ),
            _bucket("industry.sw_l1.code", "申万一级行业", "801770.SI", 170, 0.56, 0.045, 0.029, 0.034, 1.5, 0.44, scope="industry"),
            _bucket("entry.low_sample_bucket", "Low Sample", "too_small", 20, 0.80, 0.080, 0.040, 0.080, 2.0, 0.20),
            _bucket("entry.high_missing_bucket", "High Missing", "missing", 180, 0.75, 0.070, 0.050, 0.070, 2.0, 0.20, flags=["high_missing"]),
        ],
    }


def _reverse_filter_summary() -> dict:
    return {
        "schema": "attbacktrader.reverse_filter_single_factor_summary.v1",
        "run_id": "screening-test",
        "min_candidate_sample_count": 100,
        "positive_candidate_count": 3,
        "negative_candidate_count": 1,
        "positive_candidates": [
            {"field_key": "entry.alpha_bucket", "value": "good", "value_label_zh": "good", "reverse_filter_positive_reasons": ["avg_above_overall"]},
            {
                "field_key": "entry.execution.signal_to_entry_return_bucket",
                "value": "gap_down_2_5pct",
                "value_label_zh": "gap_down_2_5pct",
                "reverse_filter_positive_reasons": ["avg_above_overall"],
            },
            {"field_key": "industry.sw_l1.code", "value": "801770.SI", "value_label_zh": "801770.SI", "reverse_filter_positive_reasons": ["avg_above_overall"]},
        ],
        "negative_candidates": [
            {"field_key": "entry.beta_bucket", "value": "bad", "value_label_zh": "bad", "reverse_filter_negative_reasons": ["avg_below_overall"]},
        ],
        "rules": [
            "候选桶要求 sample_count >= 100，并排除 high_missing/no_contrast 字段。",
        ],
    }


def _bucket(
    field_key: str,
    label: str,
    value: str,
    sample_count: int,
    win_rate: float,
    average_return: float,
    median_return: float,
    return_on_entry_value: float,
    profit_loss_ratio: float,
    ma60_stop_rate: float,
    *,
    scope: str = "test",
    flags: list[str] | None = None,
) -> dict:
    return {
        "field_key": field_key,
        "field_label_zh": label,
        "timing": "entry",
        "scope": scope,
        "value": value,
        "value_label_zh": value,
        "label_zh": f"{label}={value}",
        "sample_count": sample_count,
        "win_rate": win_rate,
        "average_return_pct": average_return,
        "median_return_pct": median_return,
        "return_on_entry_value": return_on_entry_value,
        "profit_loss_ratio": profit_loss_ratio,
        "pnl_path_max_drawdown_on_entry_value": 0.01,
        "return_path_max_drawdown_pct": 0.20,
        "return_volatility_pct": 0.10,
        "ma60_stop_exit_rate": ma60_stop_rate,
        "flags": flags or [],
        "trade_indexes": [1, 2, 3],
    }


def _row_keys(rows: list[dict]) -> set[tuple[str, str]]:
    return {(row["field_key"], row["value_label_zh"]) for row in rows}
