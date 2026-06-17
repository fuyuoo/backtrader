import json
from pathlib import Path

from attbacktrader.cli import bayesian_factor_discovery as bayesian_factor_discovery_cli
from attbacktrader.reports import (
    ATTRIBUTION_FIELD_INDEX_SCHEMA,
    ATTRIBUTION_WIDE_SAMPLES_SCHEMA,
    BAYESIAN_FACTOR_DISCOVERY_SCHEMA,
    build_bayesian_factor_discovery_report,
    render_bayesian_factor_discovery_markdown_zh,
)


def test_bayesian_factor_discovery_ranks_buckets_and_guards_future_fields() -> None:
    wide_samples = _wide_samples_fixture()

    report = build_bayesian_factor_discovery_report(
        wide_samples,
        min_bucket_sample_count=2,
        prior_strength=1,
        positive_score_threshold=0.1,
        negative_score_threshold=-0.1,
    )

    assert report["schema"] == BAYESIAN_FACTOR_DISCOVERY_SCHEMA
    assert report["discovery_mode"] == "research_only_not_strategy_optimization"
    assert report["usable_field_counts"]["tradable_pre_entry"] == 2
    assert report["usable_field_counts"]["lifecycle_diagnostic"] == 2

    tradable_rows = _all_ranking_rows(report["rankings"]["tradable_pre_entry"])
    assert any(row["field_key"] == "entry.alpha_bucket" and row["value"] == "good" for row in report["rankings"]["tradable_pre_entry"]["positive"])
    assert any(row["field_key"] == "entry.alpha_bucket" and row["value"] == "bad" for row in report["rankings"]["tradable_pre_entry"]["negative"])
    assert any(row["field_key"] == "symbol.legacy_state" for row in tradable_rows)
    assert not any(row["field_key"].startswith("trade.") for row in tradable_rows)
    assert not any(row["field_key"] == "market.objective.entry_to_exit_stage" for row in tradable_rows)

    lifecycle_rows = _all_ranking_rows(report["rankings"]["lifecycle_diagnostic"])
    assert any(row["field_key"] == "trade.path.reached_10pct_bucket" for row in lifecycle_rows)
    future_stage = next(row for row in lifecycle_rows if row["field_key"] == "market.objective.entry_to_exit_stage")
    assert future_stage["future_function_guard"]["eligible_for_entry_rule_review"] is False

    excluded = {field["field_key"]: field for field in report["excluded_fields"]}
    assert "entry.numeric_raw" in excluded
    assert "no_discrete_bucket" in excluded["entry.numeric_raw"]["flags"]
    assert "symbol.kdj.week.indicator_date" in excluded
    assert "metadata_time_anchor" in excluded["symbol.kdj.week.indicator_date"]["flags"]

    markdown = render_bayesian_factor_discovery_markdown_zh(report)
    assert "贝叶斯因子发现" in markdown
    assert "不是参数优化" in markdown


def test_bayesian_factor_discovery_cli_writes_artifacts(tmp_path: Path) -> None:
    wide_samples = _wide_samples_fixture(source_dir=str(tmp_path))
    wide_path = tmp_path / "attribution_wide_samples.json"
    wide_path.write_text(json.dumps(wide_samples, ensure_ascii=False), encoding="utf-8")

    exit_code = bayesian_factor_discovery_cli.main(
        [
            "--wide-samples",
            str(wide_path),
            "--output-dir",
            str(tmp_path / "discovery"),
            "--min-bucket-sample-count",
            "2",
            "--prior-strength",
            "1",
            "--positive-score-threshold",
            "0.1",
            "--negative-score-threshold",
            "-0.1",
        ]
    )

    assert exit_code == 0
    json_path = tmp_path / "discovery" / "bayesian_factor_discovery.json"
    markdown_path = tmp_path / "discovery" / "bayesian_factor_discovery.zh.md"
    assert json_path.exists()
    assert markdown_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["schema"] == BAYESIAN_FACTOR_DISCOVERY_SCHEMA
    assert report["rankings"]["tradable_pre_entry"]["positive"]


def _wide_samples_fixture(*, source_dir: str = "reports/test-run") -> dict:
    fields = [
        {
            "field_key": "entry.alpha_bucket",
            "label_zh": "入场Alpha桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "test",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
        {
            "field_key": "symbol.legacy_state",
            "label_zh": "历史个股状态",
            "value_type": "bucket",
            "timing": "symbol",
            "scope": "symbol",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
        {
            "field_key": "trade.path.reached_10pct_bucket",
            "label_zh": "持仓曾到10%",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "trade_path",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
        {
            "field_key": "market.objective.entry_to_exit_stage",
            "label_zh": "入场到出场市场阶段",
            "value_type": "bucket",
            "timing": "market",
            "scope": "market",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
        {
            "field_key": "entry.numeric_raw",
            "label_zh": "连续原始值",
            "value_type": "value",
            "timing": "entry",
            "scope": "test",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
        {
            "field_key": "symbol.kdj.week.indicator_date",
            "label_zh": "周线KDJ锚定日期",
            "value_type": "value",
            "timing": "symbol",
            "scope": "symbol",
            "coverage_stats": {"sample_count": 8, "missing_count": 0, "valid_count": 8, "missing_ratio": 0.0},
        },
    ]
    returns = [0.08, 0.06, 0.04, 0.03, -0.04, -0.03, -0.02, -0.01]
    samples = []
    for index, return_pct in enumerate(returns, start=1):
        positive = return_pct > 0
        samples.append(
            {
                "trade_index": index,
                "symbol": f"00000{index}.SZ",
                "entry_date": f"2024-01-{index:02d}",
                "exit_date": f"2024-01-{index + 5:02d}",
                "exit_reason": "BAOMA_MA25_PROFIT_EXIT_TRIGGERED" if positive else "BAOMA_MA60_STOP_TRIGGERED",
                "return_pct": return_pct,
                "profit_contribution": {
                    "contribution_available": True,
                    "entry_gross_value": 1000.0,
                    "net_pnl": return_pct * 1000.0,
                },
                "field_values": {
                    "entry.alpha_bucket": {
                        "raw": "good" if positive else "bad",
                        "bucket": "good" if positive else "bad",
                        "exception_codes": [],
                    },
                    "symbol.legacy_state": {
                        "raw": "legacy_good" if positive else "legacy_bad",
                        "bucket": "legacy_good" if positive else "legacy_bad",
                        "exception_codes": [],
                    },
                    "trade.path.reached_10pct_bucket": {
                        "raw": positive,
                        "bucket": "reached" if positive else "not_reached",
                        "exception_codes": [],
                    },
                    "market.objective.entry_to_exit_stage": {
                        "raw": "mixed_to_bullish" if positive else "bullish_to_bearish",
                        "bucket": "mixed_to_bullish" if positive else "bullish_to_bearish",
                        "exception_codes": [],
                    },
                    "entry.numeric_raw": {
                        "raw": index * 1.5,
                        "bucket": None,
                        "exception_codes": [],
                    },
                    "symbol.kdj.week.indicator_date": {
                        "raw": "2024-01-05" if positive else "2024-01-12",
                        "bucket": None,
                        "exception_codes": [],
                    },
                },
            }
        )
    return {
        "schema": ATTRIBUTION_WIDE_SAMPLES_SCHEMA,
        "run_id": "bayesian-discovery-test",
        "source_dir": source_dir,
        "reference_path": "reference",
        "sample_count": len(samples),
        "field_count": len(fields),
        "field_index": {
            "schema": ATTRIBUTION_FIELD_INDEX_SCHEMA,
            "run_id": "bayesian-discovery-test",
            "sample_count": len(samples),
            "field_count": len(fields),
            "fields": fields,
        },
        "samples": samples,
    }


def _all_ranking_rows(rankings: dict) -> list[dict]:
    return list(rankings["positive"]) + list(rankings["negative"]) + list(rankings["weak"])
