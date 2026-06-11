import json
from pathlib import Path

from attbacktrader.cli import single_factor_attribution as single_factor_attribution_cli
from attbacktrader.reports import (
    build_single_factor_attribution_report,
    render_single_factor_attribution_markdown_zh,
    write_single_factor_attribution_report,
)


def test_single_factor_attribution_splits_entry_and_post_trade_fields(tmp_path: Path) -> None:
    report = build_single_factor_attribution_report(_wide_samples(), min_bucket_sample_count=2)
    markdown = render_single_factor_attribution_markdown_zh(report, ranking_limit=5)
    json_path, markdown_path = write_single_factor_attribution_report(report, output_dir=tmp_path)

    assert report["schema"] == "attbacktrader.single_factor_attribution.v1"
    assert report["entry_factor_count"] == 2
    assert report["post_trade_stat_count"] == 1
    assert report["excluded_field_count"] == 2
    assert json_path.exists()
    assert markdown_path.exists()
    assert "## 按胜率排序" in markdown
    assert "## 持仓后统计" in markdown

    entry_values = {
        (summary["field_key"], summary["value"])
        for summary in report["entry_single_factor_summaries"]
    }
    assert ("entry.foo_bucket", "low") in entry_values
    assert ("entry.foo_bucket", 0.1) not in entry_values
    assert any(summary["field_key"] == "trade.path.holding_days_bucket" for summary in report["post_trade_summaries"])
    assert any(field["field_key"] == "trade.exit.reason" for field in report["excluded_fields"])


def test_single_factor_attribution_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    wide_path = tmp_path / "attribution_wide_samples.json"
    field_index_path = tmp_path / "attribution_field_index.json"
    payload = _wide_samples()
    wide_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    field_index_path.write_text(json.dumps(payload["field_index"], ensure_ascii=False), encoding="utf-8")

    exit_code = single_factor_attribution_cli.main(
        [
            "--wide-samples",
            str(wide_path),
            "--field-index",
            str(field_index_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--min-bucket-sample-count",
            "2",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.single_factor_attribution.v1"
    assert stdout["entry_factor_count"] == 2
    assert (tmp_path / "out" / "single_factor_attribution.json").exists()
    assert (tmp_path / "out" / "single_factor_attribution.zh.md").exists()


def _wide_samples() -> dict:
    fields = [
        {
            "field_key": "entry.foo_bucket",
            "label_zh": "入场测试桶",
            "timing": "entry",
            "scope": "test",
            "value_type": "bucket",
        },
        {
            "field_key": "entry.source",
            "label_zh": "入场来源",
            "timing": "entry",
            "scope": "test",
            "value_type": "category",
        },
        {
            "field_key": "trade.path.holding_days_bucket",
            "label_zh": "持仓天数桶",
            "timing": "post_trade",
            "scope": "path",
            "value_type": "bucket",
        },
        {
            "field_key": "trade.exit.reason",
            "label_zh": "退出原因",
            "timing": "exit",
            "scope": "exit",
            "value_type": "category",
        },
        {
            "field_key": "symbol.close",
            "label_zh": "旧版收盘价",
            "timing": "symbol",
            "scope": "symbol",
            "value_type": "value",
        },
    ]
    return {
        "schema": "attbacktrader.attribution_wide_samples.v1",
        "run_id": "single-factor-test",
        "source_dir": "reports/single-factor-test",
        "reference_path": "reference",
        "field_index": {
            "schema": "attbacktrader.attribution_field_index.v1",
            "fields": fields,
        },
        "samples": [
            _sample(1, -0.02, "low", "HS300", "d4_10", "BAOMA_MA60_STOP_TRIGGERED"),
            _sample(2, 0.05, "low", "HS300", "d11_20", "BAOMA_MA25_PROFIT_EXIT_TRIGGERED"),
            _sample(3, 0.01, None, "CSI500", "d4_10", "BAOMA_MA25_PROFIT_EXIT_TRIGGERED"),
        ],
    }


def _sample(
    trade_index: int,
    return_pct: float,
    foo_bucket: str | None,
    source: str,
    holding_bucket: str,
    exit_reason: str,
) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": "000001.SZ",
        "entry_date": "2024-01-02",
        "exit_date": "2024-01-05",
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "profit_contribution": {
            "contribution_available": True,
            "entry_gross_value": 1000.0,
            "net_pnl": return_pct * 1000.0,
        },
        "field_values": {
            "entry.foo_bucket": {"raw": 0.1 + trade_index, "bucket": foo_bucket, "exception_codes": []},
            "entry.source": {"raw": source, "bucket": source, "exception_codes": []},
            "trade.path.holding_days_bucket": {"raw": trade_index, "bucket": holding_bucket, "exception_codes": []},
            "trade.exit.reason": {"raw": exit_reason, "bucket": exit_reason, "exception_codes": []},
            "symbol.close": {"raw": 10.0 + trade_index, "bucket": None, "exception_codes": []},
        },
    }
