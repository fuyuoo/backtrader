import json
from pathlib import Path

from attbacktrader.cli import run_catalog as run_catalog_cli
from attbacktrader.reports import (
    build_run_catalog,
    render_run_catalog_markdown_zh,
    write_run_catalog,
)


def test_run_catalog_indexes_manifest_roles_and_artifact_presence(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    baseline = _write_run(report_root, "segment-baseline", cumulative_return=0.12, trade_count=8)
    variant = _write_run(
        report_root,
        "segment-baseline__variant__let_winners_run",
        cumulative_return=0.05,
        trade_count=18,
        omit=("trade_review.json",),
    )
    manifest = _write_strategy_variant_manifest(tmp_path, baseline.name, variant.name)

    catalog = build_run_catalog(report_root=report_root, manifests=[manifest])
    markdown = render_run_catalog_markdown_zh(catalog)
    json_path, markdown_path = write_run_catalog(catalog, output_dir=tmp_path / "catalog")

    assert catalog["schema"] == "attbacktrader.run_catalog.v1"
    assert catalog["run_count"] == 2
    assert catalog["group_count"] == 1
    assert catalog["missing_required_artifact_run_count"] == 1
    rows = {row["run_id"]: row for row in catalog["runs"]}
    assert rows["segment-baseline"]["role"] == "market_segment_baseline"
    assert rows["segment-baseline"]["metrics"]["cumulative_return"] == 0.12
    assert rows["segment-baseline"]["comparable_run_ids"] == ["segment-baseline__variant__let_winners_run"]
    assert rows["segment-baseline__variant__let_winners_run"]["role"] == "strategy_variant_segment"
    assert "trade_review" in rows["segment-baseline__variant__let_winners_run"]["missing_required_artifacts"]
    assert catalog["comparison_groups"][0]["baseline_run_id"] == "segment-baseline"
    assert catalog["comparison_groups"][0]["variant_run_ids"] == ["segment-baseline__variant__let_winners_run"]
    assert "回测 Run Catalog" in markdown
    assert "策略变体市场段 run" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_catalog_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    report_root = tmp_path / "reports"
    _write_run(report_root, "segment-baseline", cumulative_return=0.12, trade_count=8)
    _write_run(report_root, "segment-baseline__variant__let_winners_run", cumulative_return=0.05, trade_count=18)
    manifest = _write_strategy_variant_manifest(
        tmp_path,
        "segment-baseline",
        "segment-baseline__variant__let_winners_run",
    )
    output_dir = tmp_path / "catalog"

    exit_code = run_catalog_cli.main(
        [
            "--report-root",
            str(report_root),
            "--manifest",
            str(manifest),
            "--no-default-manifests",
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.run_catalog.v1"
    assert stdout["run_count"] == 2
    assert stdout["group_count"] == 1
    assert stdout["artifacts"]["run_catalog_json_path"] == str(output_dir / "run_catalog.json")
    assert (output_dir / "run_catalog.zh.md").exists()


def _write_strategy_variant_manifest(root: Path, baseline_run_id: str, variant_run_id: str) -> Path:
    path = root / "strategy_variant_run_manifest.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.strategy_variant_run_manifest.v1",
            "segments": [
                {
                    "segment_id": "test_bull_segment",
                    "segment_label_zh": "测试牛市段",
                    "market_type_id": "bull_market",
                    "market_type_label_zh": "牛市",
                    "baseline_run_id": baseline_run_id,
                    "draft_id": "let_winners_run",
                    "run_id": variant_run_id,
                }
            ],
        },
    )
    return path


def _write_run(
    report_root: Path,
    run_id: str,
    *,
    cumulative_return: float,
    trade_count: int,
    omit: tuple[str, ...] = (),
) -> Path:
    run_dir = report_root / run_id
    run_dir.mkdir(parents=True)
    payloads = {
        "run_plan.json": {
            "run": {"id": run_id, "from_date": "2024-01-01", "to_date": "2024-03-31"},
            "data": {"provider": "fake", "symbols": ["000001.SZ", "600519.SH"]},
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "kdj_oversold_entry",
                "profit_taking_method": "kdj_overheated_exit",
                "stop_loss_method": "fixed_percent_stop",
                "add_on_method": "none",
                "sizing_rule": "equal_weight",
            },
        },
        "report.json": {
            "returns": {"final_equity": 1000000 * (1 + cumulative_return), "cumulative_return": cumulative_return},
            "risk": {"max_drawdown": 0.03},
            "trade_quality": {"trade_count": trade_count, "win_rate": 0.5, "average_win": 0.04},
        },
        "evidence_validation.json": {"status": "ok", "error_count": 0, "warning_count": 0},
        "trades.json": {"closed_trades": [{"symbol": "000001.SZ"} for _ in range(trade_count)]},
        "signal_audit.json": [],
        "sizing_audit.json": [],
        "execution_audit.json": [],
        "trade_lifecycle.json": {"lifecycles": []},
        "trade_review.json": {"trades": [], "opportunities": [], "add_on_entry_points": []},
        "post_exit_analysis.json": {"observations": []},
    }
    for filename, payload in payloads.items():
        if filename not in omit:
            _write_json(run_dir / filename, payload)
    return run_dir


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
