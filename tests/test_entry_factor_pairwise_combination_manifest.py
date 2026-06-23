import json
from pathlib import Path

import yaml

from attbacktrader.cli import entry_factor_pairwise_combination_manifest as pairwise_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    ENTRY_FACTOR_PAIRWISE_COMBINATION_MANIFEST_SCHEMA,
    build_entry_factor_pairwise_combination_manifest,
    write_entry_factor_pairwise_combination_manifest,
)


def test_pairwise_manifest_builds_only_a_anchored_two_factor_combinations() -> None:
    manifest = build_entry_factor_pairwise_combination_manifest(
        _screening_rows_fixture(),
        _baseline_run_plan_fixture(),
        reuse_snapshots=True,
    )

    assert manifest["schema"] == ENTRY_FACTOR_PAIRWISE_COMBINATION_MANIFEST_SCHEMA
    assert manifest["generated_count"] == 5
    assert manifest["pair_kind_counts"] == {"AA": 1, "AB": 2, "AC": 2}
    assert manifest["source_layer_counts"] == {"A": 2, "B": 1, "C": 1}

    for candidate in manifest["candidates"]:
        assert "A" in candidate["screening_layers"]
        assert len(candidate["conditions"]) == 2
        assert candidate["action"] == "entry_filter_pair"
        run_plan = candidate["run_plan"]
        conditions = run_plan["analysis"]["entry_attribution"]["entry_filter"]["conditions"]
        assert conditions == candidate["conditions"]
        for condition in conditions:
            assert condition["field"] in run_plan["analysis"]["entry_attribution"]["factors"]
        RunPlan.from_mapping(run_plan)

    assert manifest["candidates"][0]["combo_kind"] == "AA"
    assert [condition["action"] for condition in manifest["candidates"][0]["conditions"]] == ["exclude", "keep"]
    assert {row["candidate_index"] for row in manifest["skipped_rows"]} == {12, 13}


def test_pairwise_manifest_writer_and_cli_write_run_plans(tmp_path: Path, capsys) -> None:
    screening_path = tmp_path / "layers.json"
    baseline_path = tmp_path / "baseline.yaml"
    output_dir = tmp_path / "pairwise"
    screening_path.write_text(json.dumps(_screening_rows_fixture(), ensure_ascii=False), encoding="utf-8")
    baseline_path.write_text(yaml.safe_dump(_baseline_run_plan_fixture(), allow_unicode=True, sort_keys=False), encoding="utf-8")

    exit_code = pairwise_cli.main(
        [
            "--screening-layers",
            str(screening_path),
            "--baseline-run-plan",
            str(baseline_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["generated_count"] == 5
    assert (output_dir / "entry_factor_pairwise_combination_manifest.json").exists()
    assert (output_dir / "entry_factor_pairwise_combination_manifest.zh.md").exists()
    assert len(list((output_dir / "run-plans").glob("*.run.yaml"))) == 5

    manifest = build_entry_factor_pairwise_combination_manifest(_screening_rows_fixture(), _baseline_run_plan_fixture())
    json_path, markdown_path, run_plan_paths, payload = write_entry_factor_pairwise_combination_manifest(
        manifest,
        output_dir=tmp_path / "writer",
    )
    assert json_path.exists()
    assert markdown_path.exists()
    assert len(run_plan_paths) == 5
    assert payload["artifacts"]["pairwise_manifest_json"].endswith("entry_factor_pairwise_combination_manifest.json")


def _screening_rows_fixture() -> list[dict]:
    return [
        _screening_row(110, "A 核心优先", "negative", "exclude", "market.hs300.return_vol_60d_bucket", "lt_1pct", 8.1, 1796),
        _screening_row(40, "A 核心优先", "positive", "keep", "entry.price_position.signal_close_ma60_atr_multiple_bucket", "above_ma60_gt_2atr", 6.8, 1925),
        _screening_row(91, "B 防守/胜率优先", "positive", "keep", "entry.price_position.near_high_20d_bucket", "at_high", 5.4, 920),
        _screening_row(143, "C 收益放大优先", "negative", "exclude", "market.csi500.return_vol_20d_bucket", "lt_1pct", 4.2, 830),
        _screening_row(12, "D 其他强支持", "positive", "keep", "entry.other", "x", 3.0, 600),
        {
            **_screening_row(13, "A 核心优先", "positive", "keep", "entry.execution.signal_to_entry_return_bucket", "gap_down_2_5pct", 3.0, 500),
            "usability": "U1 入场价依赖",
        },
    ]


def _screening_row(
    index: int,
    layer: str,
    direction: str,
    action: str,
    field_key: str,
    value: str,
    score: float,
    trade_count: int,
) -> dict:
    return {
        "candidate_index": index,
        "status": "supports_candidate",
        "validation_score": score,
        "direction": direction,
        "action": action,
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": value,
        "cumulative_return": 0.02,
        "return_delta": 0.01,
        "max_drawdown": 0.01,
        "drawdown_delta": -0.01,
        "win_rate": 0.56,
        "win_rate_delta": 0.10,
        "profit_loss_ratio": 1.4,
        "profit_loss_ratio_delta": 0.1,
        "trade_count": trade_count,
        "usability": "U0 严格事前可用",
        "scope": "market",
        "screening_layer": layer,
    }


def _baseline_run_plan_fixture() -> dict:
    return {
        "run": {
            "id": "baoma-baseline",
            "from_date": "2023-01-01",
            "to_date": "2024-12-31",
        },
        "data": {
            "snapshot_root": "data/snapshots",
            "refresh_snapshots": True,
            "symbols": ["000001.SZ"],
            "benchmark_series": {"indexes": ["000300.SH"]},
        },
        "strategy": {
            "template": "trend_template_v1",
            "entry_method": "baoma_entry",
            "profit_taking_method": "baoma_ma25_profit_exit",
            "stop_loss_method": "baoma_ma60_stop",
            "add_on_method": "baoma_add_on",
            "sizing_rule": "equal_weight",
            "sizing_params": {"max_holding_count": 800, "min_order_quantity": 100},
        },
        "constraints": {"ashare": {"enabled": True, "board_lot_size": 100}},
        "broker": {
            "initial_cash": 1_200_000,
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "transfer_fee_rate": 0.00001,
            "slippage": {"type": "percent", "value": 0.0005},
        },
        "execution": {
            "engine": "baoma_v1_business",
            "stake": 100,
            "baoma": {
                "buy_slice_fraction": 0.25,
                "first_scale_out_return": 0.04,
                "second_scale_out_return": 0.12,
                "scale_out_mode": "atr_multiple",
                "first_scale_out_atr_multiple": 2.0,
                "second_scale_out_atr_multiple": 4.0,
            },
        },
        "analysis": {
            "industry_attribution": {"enabled": False},
            "market_regime": {"enabled": False},
            "scenario_fit": {"enabled": False},
        },
    }
