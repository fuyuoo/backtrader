import json
from pathlib import Path

import pytest
import yaml

from attbacktrader.cli import market_segment_runs as market_segment_runs_cli
from attbacktrader.cli.market_segment_runs import generate_market_segment_run_configs
from attbacktrader.config import RunPlan


def test_market_segment_run_generator_writes_legal_run_plans(tmp_path: Path) -> None:
    base_config_path = tmp_path / "base.yaml"
    catalog_path = tmp_path / "segments.yaml"
    base_config_path.write_text(yaml.safe_dump(_base_config(), sort_keys=False), encoding="utf-8")
    catalog_path.write_text(yaml.safe_dump(_catalog(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    output_dir = tmp_path / "generated"
    stale_generated = output_dir / "old-market-segment.run.yaml"
    unrelated = output_dir / "manual.run.yaml"
    output_dir.mkdir()
    stale_generated.write_text(
        "# Generated from a manually curated market segment.\nrun:\n  id: old\n",
        encoding="utf-8",
    )
    unrelated.write_text("run:\n  id: manual\n", encoding="utf-8")

    manifest_path, markdown_path, yaml_paths = generate_market_segment_run_configs(
        catalog_path=catalog_path,
        base_config_path=base_config_path,
        output_dir=output_dir,
        run_id_prefix="manual-validation",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_config = yaml.safe_load(yaml_paths[0].read_text(encoding="utf-8"))
    first_plan = RunPlan.from_mapping(first_config)

    assert manifest["schema"] == "attbacktrader.market_segment_run_manifest.v1"
    assert manifest["generated_count"] == 3
    assert manifest["market_types"][0]["market_type_id"] == "bull_market"
    assert manifest["segments"][0]["market_type_id"] == "bull_market"
    assert manifest["segments"][0]["market_type_label_zh"] == "牛市"
    assert manifest["segments"][0]["source_refs"][0]["url"] == "https://example.com/2019"
    assert "不是代码自动识别" in manifest["ai_usage_rules"][0]
    assert "## 行情类型" in markdown_path.read_text(encoding="utf-8")
    assert markdown_path.exists()
    assert len(yaml_paths) == 3
    assert not stale_generated.exists()
    assert unrelated.exists()
    assert first_plan.run.id == "manual-validation-market-segment-2019_bull_market"
    assert str(first_plan.run.from_date) == "2019-01-04"
    assert str(first_plan.run.to_date) == "2019-04-08"
    assert "manual_market_segment" not in first_config
    first_yaml = yaml_paths[0].read_text(encoding="utf-8")
    assert "# segment_id: 2019_bull_market" in first_yaml
    assert "# market_type_id: bull_market" in first_yaml


def test_market_segment_run_generator_cli(tmp_path: Path, capsys) -> None:
    base_config_path = tmp_path / "base.yaml"
    catalog_path = tmp_path / "segments.yaml"
    output_dir = tmp_path / "generated"
    base_config_path.write_text(yaml.safe_dump(_base_config(), sort_keys=False), encoding="utf-8")
    catalog_path.write_text(yaml.safe_dump(_catalog(), allow_unicode=True, sort_keys=False), encoding="utf-8")

    exit_code = market_segment_runs_cli.main(
        [
            "--catalog",
            str(catalog_path),
            "--base-config",
            str(base_config_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.market_segment_run_manifest.v1"
    assert (output_dir / "market_segment_run_manifest.json").exists()
    assert len(stdout["generated_run_plan_paths"]) == 3


def test_market_segment_run_generator_requires_three_segments_per_type(tmp_path: Path) -> None:
    base_config_path = tmp_path / "base.yaml"
    catalog_path = tmp_path / "segments.yaml"
    catalog = _catalog()
    catalog["segments"] = catalog["segments"][:2]
    base_config_path.write_text(yaml.safe_dump(_base_config(), sort_keys=False), encoding="utf-8")
    catalog_path.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="bull_market must have at least 3 segments"):
        generate_market_segment_run_configs(
            catalog_path=catalog_path,
            base_config_path=base_config_path,
            output_dir=tmp_path / "generated",
        )


def _catalog() -> dict:
    return {
        "schema": "attbacktrader.manual_market_segments.v1",
        "market_types": [
            {
                "market_type_id": "bull_market",
                "label_zh": "牛市",
                "strategy_switching_use_zh": "验证趋势持有类策略。",
                "selection_rule_zh": "指数中期趋势向上。",
            }
        ],
        "segments": [
            {
                "segment_id": "2019_bull_market",
                "market_type_id": "bull_market",
                "label_zh": "2019 年牛市样本",
                "from_date": "2019-01-04",
                "to_date": "2019-04-08",
                "validation_role": "bull_market",
                "manual_similarity_thesis_zh": "人工选择的牛市行情段。",
                "source_refs": [
                    {
                        "title": "2019 source",
                        "url": "https://example.com/2019",
                        "evidence_zh": "source evidence",
                    }
                ],
            },
            {
                "segment_id": "2020_bull_market",
                "market_type_id": "bull_market",
                "label_zh": "2020 年牛市样本",
                "from_date": "2020-03-23",
                "to_date": "2020-07-13",
                "validation_role": "bull_market",
                "manual_similarity_thesis_zh": "人工选择的牛市行情段。",
                "source_refs": [
                    {
                        "title": "2020 source",
                        "url": "https://example.com/2020",
                        "evidence_zh": "source evidence",
                    }
                ],
            },
            {
                "segment_id": "2021_bull_market",
                "market_type_id": "bull_market",
                "label_zh": "2021 年牛市样本",
                "from_date": "2021-01-04",
                "to_date": "2021-02-18",
                "validation_role": "bull_market",
                "manual_similarity_thesis_zh": "人工选择的牛市行情段。",
                "source_refs": [
                    {
                        "title": "2021 source",
                        "url": "https://example.com/2021",
                        "evidence_zh": "source evidence",
                    }
                ],
            },
        ],
    }


def _base_config() -> dict:
    return {
        "run": {
            "id": "base-run",
            "from_date": "2023-01-01",
            "to_date": "2024-12-31",
        },
        "data": {
            "snapshot_root": "data/snapshots",
            "provider": "tushare",
            "price_adjustment": "qfq",
            "refresh_snapshots": True,
            "symbols": ["000001.SZ"],
        },
        "strategy": {
            "template": "trend_template_v1",
            "entry_method": "kdj_oversold_entry",
            "profit_taking_method": "kdj_overheated_exit",
            "stop_loss_method": "fixed_percent_stop",
            "add_on_method": "none",
            "sizing_rule": "equal_weight",
        },
        "broker": {
            "initial_cash": 1000000,
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "transfer_fee_rate": 0.00001,
            "slippage": {"type": "percent", "value": 0.0005},
        },
        "execution": {
            "engine": "business",
            "stake": 100,
        },
    }
