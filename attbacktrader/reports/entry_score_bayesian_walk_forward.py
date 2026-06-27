"""Bayesian walk-forward tuning for completed-trade entry-score weights."""

from __future__ import annotations

import importlib
import json
import math
import random
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .entry_score_trade_sample_backtest import (
    DEFAULT_ENTRY_SCORE_SCORING_CONFIG,
    _as_mapping,
    _as_sequence,
    _delta,
    _format_money,
    _format_number,
    _format_pct,
    _format_pp,
    _jsonable,
    _load_json_like,
    _normalize_scoring_config,
    _optional_float,
    _ranked_trade_key,
    _score_trade_sample,
    _source_path,
    _stats,
    _trade_samples,
)


ENTRY_SCORE_BAYESIAN_WALK_FORWARD_SCHEMA = "attbacktrader.entry_score_bayesian_walk_forward.v1"

DEFAULT_BAYESIAN_WALK_FORWARD_OBJECTIVE = {
    "name": "roev_avg_win_lift_with_sample_penalty",
    "formula": "roev_lift + 0.5 * average_return_lift + 0.03 * win_rate_lift - sample_penalty - yearly_sample_penalty",
    "sample_penalty_formula": (
        "max(0, min_train_pass_rate - pass_rate) * 0.20 "
        "+ max(0, min_train_sample_count - passed_count) / min_train_sample_count * 0.02"
    ),
    "yearly_sample_penalty_formula": (
        "sum(max(0, min_train_yearly_pass_count - yearly_passed_count) / min_train_yearly_pass_count) * 0.03"
    ),
}


def build_entry_score_bayesian_walk_forward(
    environment_fit: Mapping[str, Any] | str | Path,
    *,
    first_train_year: int = 2015,
    last_test_year: int = 2024,
    train_years: int = 5,
    n_trials: int = 80,
    seed: int = 42,
    min_train_pass_rate: float = 0.20,
    min_train_sample_count: int = 300,
    min_train_yearly_pass_count: int = 0,
    optimizer: str = "optuna",
    sample_limit: int = 30,
) -> dict[str, Any]:
    """Tune entry-score weights with train-only optimization and one-year OOS tests."""

    if optimizer not in {"optuna", "random"}:
        raise ValueError("optimizer must be one of: optuna, random")
    if train_years <= 0:
        raise ValueError("train_years must be positive")
    if n_trials <= 0:
        raise ValueError("n_trials must be positive")
    if sample_limit <= 0:
        raise ValueError("sample_limit must be positive")
    if not 0.0 <= min_train_pass_rate <= 1.0:
        raise ValueError("min_train_pass_rate must be between 0 and 1")
    if min_train_sample_count <= 0:
        raise ValueError("min_train_sample_count must be positive")
    if min_train_yearly_pass_count < 0:
        raise ValueError("min_train_yearly_pass_count cannot be negative")

    folds = _build_walk_forward_year_folds(
        first_train_year=first_train_year,
        last_test_year=last_test_year,
        train_years=train_years,
    )
    if not folds:
        raise ValueError("walk-forward configuration produced no folds")

    base_config = _normalize_scoring_config(DEFAULT_ENTRY_SCORE_SCORING_CONFIG)
    weight_specs = _build_weight_parameter_specs(base_config)
    threshold_spec = {
        "name": "min_entry_score",
        "kind": "threshold",
        "label": "最低入场分数",
        "low": 0.0,
        "high": 8.0,
        "step": 0.5,
        "default": 4.0,
    }

    payload = _load_json_like(environment_fit)
    all_contributions = list(_as_sequence(payload.get("trade_contributions")))
    all_trades = [_as_mapping(row) for row in all_contributions if _as_mapping(_as_mapping(row).get("environment"))]
    if not all_trades:
        raise ValueError("environment_fit must include non-empty trade_contributions with environment fields")

    trades_by_year: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    ignored_missing_year = 0
    for trade in all_trades:
        year = _entry_year(trade)
        if year is None:
            ignored_missing_year += 1
            continue
        trades_by_year[year].append(trade)

    fold_reports: list[dict[str, Any]] = []
    aggregate_all_test_rows: list[Mapping[str, Any]] = []
    aggregate_selected_test_rows: list[Mapping[str, Any]] = []
    aggregate_blocked_test_rows: list[Mapping[str, Any]] = []

    for fold_index, fold in enumerate(folds):
        train_rows = _rows_for_years(trades_by_year, fold["train_years"])
        test_rows = _rows_for_years(trades_by_year, [fold["test_year"]])
        if not train_rows:
            raise ValueError(f"fold {fold['fold_id']} has no training trades")
        if not test_rows:
            raise ValueError(f"fold {fold['fold_id']} has no test trades")

        best_result = _optimize_fold(
            train_rows,
            base_config=base_config,
            weight_specs=weight_specs,
            threshold_spec=threshold_spec,
            n_trials=n_trials,
            seed=seed + fold_index,
            min_train_pass_rate=min_train_pass_rate,
            min_train_sample_count=min_train_sample_count,
            min_train_yearly_pass_count=min_train_yearly_pass_count,
            optimizer=optimizer,
        )
        config = _scoring_config_from_params(base_config, weight_specs, best_result["best_params"])
        min_entry_score = float(best_result["best_params"]["min_entry_score"])
        train_eval = _evaluate_score_gate(train_rows, config, min_entry_score)
        test_eval = _evaluate_score_gate(test_rows, config, min_entry_score)

        test_selected_rows = _tag_rows(test_eval["selected_rows"], fold_id=fold["fold_id"])
        test_blocked_rows = _tag_rows(test_eval["blocked_rows"], fold_id=fold["fold_id"])
        test_all_rows = _tag_rows(test_eval["all_rows"], fold_id=fold["fold_id"])
        aggregate_all_test_rows.extend(test_all_rows)
        aggregate_selected_test_rows.extend(test_selected_rows)
        aggregate_blocked_test_rows.extend(test_blocked_rows)

        fold_reports.append(
            {
                **fold,
                "optimization": {
                    "optimizer": "optuna_tpe" if optimizer == "optuna" else "explicit_random_search",
                    "n_trials": n_trials,
                    "seed": seed + fold_index,
                    "objective_definition": DEFAULT_BAYESIAN_WALK_FORWARD_OBJECTIVE,
                    "best_objective": best_result["best_objective"],
                    "best_params": _jsonable(best_result["best_params"]),
                    "best_scoring_config": _jsonable(config),
                    "top_trials": best_result["top_trials"],
                },
                "train": _evaluation_summary(train_eval),
                "test": _evaluation_summary(test_eval),
                "samples": {
                    "test_top_ranked_trades": _trade_samples(sorted(test_all_rows, key=_ranked_trade_key), limit=sample_limit),
                    "test_worst_score_passed_trades": _trade_samples(
                        sorted(test_selected_rows, key=lambda row: _optional_float(row.get("return_pct")) or math.inf),
                        limit=sample_limit,
                    ),
                    "test_best_score_blocked_winners": _trade_samples(
                        sorted(
                            [row for row in test_blocked_rows if (_optional_float(row.get("return_pct")) or 0.0) > 0],
                            key=lambda row: -(_optional_float(row.get("return_pct")) or -math.inf),
                        ),
                        limit=sample_limit,
                    ),
                },
            }
        )

    aggregate_oos = {
        "all_test_trades": _stats(aggregate_all_test_rows),
        "score_passed": _stats(aggregate_selected_test_rows),
        "score_blocked": _stats(aggregate_blocked_test_rows),
        "delta_vs_all": _delta(_stats(aggregate_selected_test_rows), _stats(aggregate_all_test_rows)),
        "funnel": _funnel(aggregate_all_test_rows, aggregate_selected_test_rows, aggregate_blocked_test_rows),
    }

    return {
        "schema": ENTRY_SCORE_BAYESIAN_WALK_FORWARD_SCHEMA,
        "source_artifacts": {
            "environment_fit": _source_path(environment_fit),
        },
        "run_id": payload.get("run_id"),
        "scope": {
            "kind": "completed_trade_sample_bayesian_score_weight_walk_forward",
            "holding_cap_policy": "none_in_trade_sample",
            "ranking_policy": "each fold tunes weights on training years only; the next test year is scored and sorted after weights are frozen",
            "caveat_zh": "这是已完成交易样本上的贝叶斯权重 walk-forward，不是完整候选级现金组合回测；compact signal_audit 无法重建未成交候选。",
        },
        "data_coverage": {
            "raw_trade_contribution_count": len(all_contributions),
            "usable_trade_count": len(all_trades),
            "ignored_without_environment": len(all_contributions) - len(all_trades),
            "ignored_missing_entry_year": ignored_missing_year,
            "available_years": sorted(trades_by_year),
        },
        "configuration": {
            "first_train_year": first_train_year,
            "last_test_year": last_test_year,
            "train_years": train_years,
            "n_trials": n_trials,
            "seed": seed,
            "min_train_pass_rate": min_train_pass_rate,
            "min_train_sample_count": min_train_sample_count,
            "min_train_yearly_pass_count": min_train_yearly_pass_count,
            "optimizer": "optuna_tpe" if optimizer == "optuna" else "explicit_random_search",
            "objective_definition": DEFAULT_BAYESIAN_WALK_FORWARD_OBJECTIVE,
        },
        "search_space": {
            "weight_parameters": _jsonable(weight_specs),
            "threshold_parameter": _jsonable(threshold_spec),
        },
        "aggregate_oos": aggregate_oos,
        "best_parameter_summary": _summarize_best_parameters(fold_reports, weight_specs, threshold_spec),
        "folds": fold_reports,
        "samples": {
            "oos_top_ranked_trades": _trade_samples(sorted(aggregate_all_test_rows, key=_ranked_trade_key), limit=sample_limit),
            "oos_worst_score_passed_trades": _trade_samples(
                sorted(aggregate_selected_test_rows, key=lambda row: _optional_float(row.get("return_pct")) or math.inf),
                limit=sample_limit,
            ),
            "oos_best_score_blocked_winners": _trade_samples(
                sorted(
                    [row for row in aggregate_blocked_test_rows if (_optional_float(row.get("return_pct")) or 0.0) > 0],
                    key=lambda row: -(_optional_float(row.get("return_pct")) or -math.inf),
                ),
                limit=sample_limit,
            ),
        },
        "ai_usage_rules": [
            "本报告只读取已落盘 completed-trade 归因证据，不重跑策略、不重新计算指标、不联网取数。",
            "每个 fold 只用训练年份调权重和最低入场分，测试年份只评估，不参与参数选择。",
            "该报告是权重寻优和样本外过滤验证，不包含未成交候选、现金竞争、真实持仓上限和每日容量约束。",
            "若要评价真实组合收益，应使用 full signal_audit 或 Strategy Decision Event Table 运行 Scored Portfolio Backtest。",
        ],
    }


def render_entry_score_bayesian_walk_forward_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render a Chinese Markdown report for Bayesian score-weight walk-forward."""

    configuration = _as_mapping(report.get("configuration"))
    scope = _as_mapping(report.get("scope"))
    aggregate = _as_mapping(report.get("aggregate_oos"))
    all_stats = _as_mapping(aggregate.get("all_test_trades"))
    selected = _as_mapping(aggregate.get("score_passed"))
    blocked = _as_mapping(aggregate.get("score_blocked"))
    delta = _as_mapping(aggregate.get("delta_vs_all"))
    funnel = _as_mapping(aggregate.get("funnel"))

    lines = [
        "# 贝叶斯因子分数 Walk-Forward",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 优化器 | {configuration.get('optimizer')} |",
        f"| 每个 fold trials | {configuration.get('n_trials')} |",
        f"| 训练窗年数 | {configuration.get('train_years')} |",
        f"| 测试年份范围 | {configuration.get('first_train_year') + configuration.get('train_years')} - {configuration.get('last_test_year')} |",
        f"| OOS 原始交易数 | {all_stats.get('sample_count')} |",
        f"| OOS 分数达标交易数 | {selected.get('sample_count')} |",
        f"| OOS 分数达标比例 | {_format_pct(funnel.get('score_pass_rate'))} |",
        "",
        "## 口径",
        "",
        f"- {scope.get('caveat_zh')}",
        "- `walk-forward` 口径：每个 fold 只用训练年份调权重和最低入场分，下一年只评估。",
        "- `无持仓上限` 在这里表示所有分数达标的已完成交易都保留，不做现金容量或持仓容量拒单。",
        "- 目标函数：`roev_lift + 0.5 * average_return_lift + 0.03 * win_rate_lift - sample_penalty - yearly_sample_penalty`。",
        "",
        "## OOS 汇总",
        "",
        "| 分组 | 样本数 | 平均收益 | 胜率 | 入场金额收益率 | 净PnL | 最大盈利 | 最大亏损 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        _summary_row("OOS 原始样本", all_stats),
        _summary_row("OOS 分数达标", selected),
        _summary_row("OOS 分数未达标", blocked),
        "",
        "## OOS 相对原始变化",
        "",
        "| 指标 | 变化 |",
        "|---|---:|",
        f"| 平均收益 | {_format_pp(delta.get('average_return_pct'))} |",
        f"| 胜率 | {_format_pp(delta.get('win_rate'))} |",
        f"| 入场金额收益率 | {_format_pp(delta.get('return_on_entry_value'))} |",
        f"| 净PnL | {_format_money(delta.get('net_pnl'))} |",
        f"| 样本数变化 | {delta.get('sample_count')} |",
        "",
        "## Fold 结果",
        "",
        "| Fold | Train | Test | 最佳目标 | 最低分 | Test样本 | Test平均收益 | Test胜率 | Test ROEV | ROEV变化 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for fold in _as_sequence(report.get("folds")):
        optimization = _as_mapping(fold.get("optimization"))
        best_params = _as_mapping(optimization.get("best_params"))
        test = _as_mapping(fold.get("test"))
        test_selected = _as_mapping(test.get("score_passed"))
        test_delta = _as_mapping(test.get("delta_vs_all"))
        lines.append(
            f"| {fold.get('fold_id')} | {fold.get('train_start_year')}-{fold.get('train_end_year')} | "
            f"{fold.get('test_year')} | {_format_number(optimization.get('best_objective'))} | "
            f"{_format_number(best_params.get('min_entry_score'))} | {test_selected.get('sample_count')} | "
            f"{_format_pct(test_selected.get('average_return_pct'))} | {_format_pct(test_selected.get('win_rate'))} | "
            f"{_format_pct(test_selected.get('return_on_entry_value'))} | {_format_pp(test_delta.get('return_on_entry_value'))} |"
        )

    lines.extend(
        [
            "",
            "## 最佳参数稳定性",
            "",
            "| 参数 | 默认 | 平均最佳值 | 最小 | 最大 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in _as_sequence(report.get("best_parameter_summary")):
        lines.append(
            f"| {row.get('label')} | {_format_number(row.get('default'))} | {_format_number(row.get('mean_best_value'))} | "
            f"{_format_number(row.get('min_best_value'))} | {_format_number(row.get('max_best_value'))} |"
        )

    lines.extend(_sample_section("OOS 最高分交易样本", _as_sequence(_as_mapping(report.get("samples")).get("oos_top_ranked_trades"))))
    lines.extend(_sample_section("OOS 分数达标后的最差交易", _as_sequence(_as_mapping(report.get("samples")).get("oos_worst_score_passed_trades"))))
    lines.extend(_sample_section("OOS 被分数挡掉的最佳盈利交易", _as_sequence(_as_mapping(report.get("samples")).get("oos_best_score_blocked_winners"))))
    return "\n".join(lines) + "\n"


def write_entry_score_bayesian_walk_forward(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
    artifact_stem: str = "entry_score_bayesian_walk_forward",
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(dict(report))
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    payload["artifacts"] = {
        "walk_forward_json": str(json_path),
        "walk_forward_markdown_zh": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_score_bayesian_walk_forward_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_entry_score_bayesian_walk_forward_dir_name(source_path: str | Path) -> str:
    """Build a stable report directory name from a source artifact path."""

    path = Path(source_path)
    source_name = path.parent.name if path.name.startswith("environment_fit") else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", source_name).strip("-")
    return f"entry-score-bayesian-walk-forward-{safe or 'environment-fit'}"


def require_optuna_for_entry_score_bayesian_walk_forward(*, import_module: Any = importlib.import_module) -> Any:
    """Import Optuna with an explicit tuning dependency error."""

    try:
        return import_module("optuna")
    except ImportError as exc:
        raise ImportError("Optuna is required for Bayesian entry-score tuning. Install with: pip install -e .[tuning]") from exc


def _build_walk_forward_year_folds(*, first_train_year: int, last_test_year: int, train_years: int) -> list[dict[str, Any]]:
    first_test_year = first_train_year + train_years
    if last_test_year < first_test_year:
        return []
    folds: list[dict[str, Any]] = []
    for test_year in range(first_test_year, last_test_year + 1):
        train_start = test_year - train_years
        train_end = test_year - 1
        folds.append(
            {
                "fold_id": f"{train_start}_{train_end}_to_{test_year}",
                "train_start_year": train_start,
                "train_end_year": train_end,
                "train_years": list(range(train_start, train_end + 1)),
                "test_year": test_year,
            }
        )
    return folds


def _build_weight_parameter_specs(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for field, weights in _as_mapping(config.get("factor_weights")).items():
        for value, default in _as_mapping(weights).items():
            low, high, step = _weight_bounds(float(default))
            specs.append(
                {
                    "name": f"factor__{_slug(field)}__{_slug(value)}",
                    "kind": "factor_weight",
                    "field": str(field),
                    "value": str(value),
                    "label": f"{field}={value}",
                    "default": float(default),
                    "low": low,
                    "high": high,
                    "step": step,
                }
            )
    for index, interaction in enumerate(_as_sequence(config.get("interaction_weights"))):
        item = _as_mapping(interaction)
        default = float(_optional_float(item.get("weight")) or 0.0)
        low, high, step = _weight_bounds(default)
        specs.append(
            {
                "name": f"interaction__{index}",
                "kind": "interaction_weight",
                "interaction_index": index,
                "label": f"interaction:{item.get('name')}",
                "default": default,
                "low": low,
                "high": high,
                "step": step,
            }
        )
    return specs


def _weight_bounds(default: float) -> tuple[float, float, float]:
    if default > 0:
        return 0.0, max(2.0, default * 2.0), 0.25
    if default < 0:
        return min(-4.0, default * 1.5), 0.0, 0.25
    return -2.0, 2.0, 0.25


def _optimize_fold(
    train_rows: Sequence[Mapping[str, Any]],
    *,
    base_config: Mapping[str, Any],
    weight_specs: Sequence[Mapping[str, Any]],
    threshold_spec: Mapping[str, Any],
    n_trials: int,
    seed: int,
    min_train_pass_rate: float,
    min_train_sample_count: int,
    min_train_yearly_pass_count: int,
    optimizer: str,
) -> dict[str, Any]:
    if optimizer == "optuna":
        optuna = require_optuna_for_entry_score_bayesian_walk_forward()
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        sampler = optuna.samplers.TPESampler(seed=seed)
        study = optuna.create_study(direction="maximize", sampler=sampler)

        def objective(trial: Any) -> float:
            params = _suggest_optuna_params(trial, weight_specs, threshold_spec)
            value, details = _score_objective(
                train_rows,
                base_config=base_config,
                weight_specs=weight_specs,
                params=params,
                min_train_pass_rate=min_train_pass_rate,
                min_train_sample_count=min_train_sample_count,
                min_train_yearly_pass_count=min_train_yearly_pass_count,
            )
            for key, item in details.items():
                trial.set_user_attr(key, item)
            return value

        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        trials = [
            {
                "trial_number": trial.number,
                "objective": trial.value,
                "params": dict(trial.params),
                "details": dict(trial.user_attrs),
            }
            for trial in study.trials
            if trial.value is not None and math.isfinite(float(trial.value))
        ]
        best_params = dict(study.best_trial.params)
        best_objective = float(study.best_value)
    else:
        rng = random.Random(seed)
        trials = []
        for trial_number in range(n_trials):
            params = _suggest_random_params(rng, weight_specs, threshold_spec)
            value, details = _score_objective(
                train_rows,
                base_config=base_config,
                weight_specs=weight_specs,
                params=params,
                min_train_pass_rate=min_train_pass_rate,
                min_train_sample_count=min_train_sample_count,
                min_train_yearly_pass_count=min_train_yearly_pass_count,
            )
            trials.append(
                {
                    "trial_number": trial_number,
                    "objective": value,
                    "params": params,
                    "details": details,
                }
            )
        best_trial = max(trials, key=lambda row: float(row["objective"]))
        best_params = dict(best_trial["params"])
        best_objective = float(best_trial["objective"])

    top_trials = sorted(trials, key=lambda row: float(row["objective"]), reverse=True)[:10]
    return {
        "best_objective": best_objective,
        "best_params": best_params,
        "top_trials": _jsonable(top_trials),
    }


def _suggest_optuna_params(
    trial: Any,
    weight_specs: Sequence[Mapping[str, Any]],
    threshold_spec: Mapping[str, Any],
) -> dict[str, float]:
    params = {}
    for spec in weight_specs:
        params[str(spec["name"])] = trial.suggest_float(
            str(spec["name"]),
            float(spec["low"]),
            float(spec["high"]),
            step=float(spec["step"]),
        )
    params[str(threshold_spec["name"])] = trial.suggest_float(
        str(threshold_spec["name"]),
        float(threshold_spec["low"]),
        float(threshold_spec["high"]),
        step=float(threshold_spec["step"]),
    )
    return params


def _suggest_random_params(
    rng: random.Random,
    weight_specs: Sequence[Mapping[str, Any]],
    threshold_spec: Mapping[str, Any],
) -> dict[str, float]:
    params = {}
    for spec in [*weight_specs, threshold_spec]:
        params[str(spec["name"])] = _random_stepped_float(
            rng,
            low=float(spec["low"]),
            high=float(spec["high"]),
            step=float(spec["step"]),
        )
    return params


def _random_stepped_float(rng: random.Random, *, low: float, high: float, step: float) -> float:
    steps = int(round((high - low) / step))
    return round(low + rng.randint(0, steps) * step, 10)


def _score_objective(
    train_rows: Sequence[Mapping[str, Any]],
    *,
    base_config: Mapping[str, Any],
    weight_specs: Sequence[Mapping[str, Any]],
    params: Mapping[str, float],
    min_train_pass_rate: float,
    min_train_sample_count: int,
    min_train_yearly_pass_count: int,
) -> tuple[float, dict[str, Any]]:
    config = _scoring_config_from_params(base_config, weight_specs, params)
    eval_result = _evaluate_score_gate_fast(train_rows, config, float(params["min_entry_score"]))
    baseline = _as_mapping(eval_result["all_trades"])
    selected = _as_mapping(eval_result["score_passed"])
    delta = _as_mapping(eval_result["delta_vs_all"])
    pass_rate = float(_as_mapping(eval_result["funnel"]).get("score_pass_rate") or 0.0)
    passed_count = int(selected.get("sample_count") or 0)
    sample_penalty = max(0.0, min_train_pass_rate - pass_rate) * 0.20
    sample_penalty += max(0.0, min_train_sample_count - passed_count) / min_train_sample_count * 0.02
    selected_count_by_year = {
        int(year): int(count)
        for year, count in _as_mapping(eval_result.get("selected_count_by_year")).items()
    }
    yearly_sample_penalty = 0.0
    if min_train_yearly_pass_count:
        yearly_sample_penalty = sum(
            max(0.0, min_train_yearly_pass_count - count) / min_train_yearly_pass_count * 0.03
            for count in selected_count_by_year.values()
        )
    if passed_count == 0:
        objective = -1_000_000.0
    else:
        objective = (
            (_optional_float(delta.get("return_on_entry_value")) or 0.0)
            + 0.5 * (_optional_float(delta.get("average_return_pct")) or 0.0)
            + 0.03 * (_optional_float(delta.get("win_rate")) or 0.0)
            - sample_penalty
            - yearly_sample_penalty
        )
    details = {
        "pass_rate": pass_rate,
        "passed_count": passed_count,
        "baseline_count": baseline.get("sample_count"),
        "sample_penalty": sample_penalty,
        "yearly_sample_penalty": yearly_sample_penalty,
        "selected_count_by_year": selected_count_by_year,
        "min_selected_count_by_year": min(selected_count_by_year.values()) if selected_count_by_year else 0,
        "average_return_lift": delta.get("average_return_pct"),
        "win_rate_lift": delta.get("win_rate"),
        "return_on_entry_value_lift": delta.get("return_on_entry_value"),
    }
    return objective, details


def _evaluate_score_gate_fast(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    min_entry_score: float,
) -> dict[str, Any]:
    selected = []
    blocked = []
    years = sorted({year for row in rows if (year := _entry_year(row)) is not None})
    selected_count_by_year = {year: 0 for year in years}
    for row in rows:
        if _entry_score_value(row, config) >= min_entry_score:
            selected.append(row)
            year = _entry_year(row)
            if year is not None:
                selected_count_by_year[year] += 1
        else:
            blocked.append(row)
    all_stats = _stats(rows)
    selected_stats = _stats(selected)
    blocked_stats = _stats(blocked)
    return {
        "all_trades": all_stats,
        "score_passed": selected_stats,
        "score_blocked": blocked_stats,
        "delta_vs_all": _delta(selected_stats, all_stats),
        "funnel": _funnel(rows, selected, blocked),
        "selected_count_by_year": selected_count_by_year,
    }


def _entry_score_value(trade: Mapping[str, Any], config: Mapping[str, Any]) -> float:
    environment = _as_mapping(trade.get("environment"))
    score = 0.0
    for field, weights in _as_mapping(config.get("factor_weights")).items():
        value = environment.get(str(field))
        score += _optional_float(_as_mapping(weights).get(str(value))) or 0.0
    for item in _as_sequence(config.get("interaction_weights")):
        interaction = _as_mapping(item)
        fields = _as_mapping(interaction.get("fields"))
        if all(environment.get(str(field)) == expected for field, expected in fields.items()):
            score += _optional_float(interaction.get("weight")) or 0.0
    return score


def _scoring_config_from_params(
    base_config: Mapping[str, Any],
    weight_specs: Sequence[Mapping[str, Any]],
    params: Mapping[str, float],
) -> dict[str, Any]:
    config = json.loads(json.dumps(_jsonable(dict(base_config)), ensure_ascii=False))
    config["name"] = "baoma_v1_factor_score_bayesian_tuned"
    config["description_zh"] = "由训练窗口贝叶斯/TPE 优化得到的强趋势阴线回踩因子分数权重。"
    for spec in weight_specs:
        name = str(spec["name"])
        weight = float(params[name])
        if spec.get("kind") == "factor_weight":
            field = str(spec["field"])
            value = str(spec["value"])
            config["factor_weights"][field][value] = weight
        elif spec.get("kind") == "interaction_weight":
            index = int(spec["interaction_index"])
            config["interaction_weights"][index]["weight"] = weight
    return _normalize_scoring_config(config)


def _evaluate_score_gate(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    min_entry_score: float,
) -> dict[str, Any]:
    scored = [_score_trade_sample(row, config) for row in rows]
    selected = [row for row in scored if (_optional_float(row.get("entry_score")) or 0.0) >= min_entry_score]
    blocked = [row for row in scored if (_optional_float(row.get("entry_score")) or 0.0) < min_entry_score]
    return {
        "all_trades": _stats(scored),
        "score_passed": _stats(selected),
        "score_blocked": _stats(blocked),
        "delta_vs_all": _delta(_stats(selected), _stats(scored)),
        "funnel": _funnel(scored, selected, blocked),
        "all_rows": scored,
        "selected_rows": selected,
        "blocked_rows": blocked,
    }


def _evaluation_summary(eval_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "all_trades": _jsonable(_as_mapping(eval_result.get("all_trades"))),
        "score_passed": _jsonable(_as_mapping(eval_result.get("score_passed"))),
        "score_blocked": _jsonable(_as_mapping(eval_result.get("score_blocked"))),
        "delta_vs_all": _jsonable(_as_mapping(eval_result.get("delta_vs_all"))),
        "funnel": _jsonable(_as_mapping(eval_result.get("funnel"))),
    }


def _funnel(
    all_rows: Sequence[Mapping[str, Any]],
    selected_rows: Sequence[Mapping[str, Any]],
    blocked_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "raw_completed_trades": len(all_rows),
        "score_passed_trades": len(selected_rows),
        "score_blocked_trades": len(blocked_rows),
        "score_pass_rate": len(selected_rows) / len(all_rows) if all_rows else 0.0,
        "score_blocked_losses": sum(1 for row in blocked_rows if (_optional_float(row.get("return_pct")) or 0.0) <= 0),
        "score_blocked_winners": sum(1 for row in blocked_rows if (_optional_float(row.get("return_pct")) or 0.0) > 0),
    }


def _summarize_best_parameters(
    fold_reports: Sequence[Mapping[str, Any]],
    weight_specs: Sequence[Mapping[str, Any]],
    threshold_spec: Mapping[str, Any],
) -> list[dict[str, Any]]:
    specs = [*weight_specs, threshold_spec]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        values = [
            float(_as_mapping(_as_mapping(fold.get("optimization")).get("best_params")).get(str(spec["name"])))
            for fold in fold_reports
            if _as_mapping(_as_mapping(fold.get("optimization")).get("best_params")).get(str(spec["name"])) is not None
        ]
        if not values:
            continue
        rows.append(
            {
                "name": spec.get("name"),
                "kind": spec.get("kind"),
                "label": spec.get("label"),
                "default": spec.get("default"),
                "mean_best_value": sum(values) / len(values),
                "min_best_value": min(values),
                "max_best_value": max(values),
                "fold_count": len(values),
            }
        )
    return rows


def _rows_for_years(trades_by_year: Mapping[int, Sequence[Mapping[str, Any]]], years: Sequence[int]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for year in years:
        rows.extend(trades_by_year.get(year, ()))
    return rows


def _entry_year(trade: Mapping[str, Any]) -> int | None:
    entry_date = str(trade.get("entry_date") or "")
    if len(entry_date) < 4:
        return None
    try:
        return int(entry_date[:4])
    except ValueError:
        return None


def _tag_rows(rows: Sequence[Mapping[str, Any]], *, fold_id: str) -> list[dict[str, Any]]:
    tagged = []
    for row in rows:
        item = dict(row)
        item["fold_id"] = fold_id
        tagged.append(item)
    return tagged


def _summary_row(label: str, stats: Mapping[str, Any]) -> str:
    return (
        f"| {label} | {stats.get('sample_count')} | {_format_pct(stats.get('average_return_pct'))} | "
        f"{_format_pct(stats.get('win_rate'))} | {_format_pct(stats.get('return_on_entry_value'))} | "
        f"{_format_money(stats.get('net_pnl'))} | {_format_pct(stats.get('max_return_pct'))} | "
        f"{_format_pct(stats.get('min_return_pct'))} |"
    )


def _sample_section(title: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| fold | trade_index | symbol | entry | exit | score | return | netPnL |",
        "|---|---:|---|---|---|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - |")
        return lines
    for row in rows:
        lines.append(
            f"| {row.get('fold_id', '-')} | {row.get('trade_index')} | `{row.get('symbol')}` | "
            f"{row.get('entry_date')} | {row.get('exit_date')} | {_format_number(row.get('entry_score'))} | "
            f"{_format_pct(row.get('return_pct'))} | {_format_money(row.get('net_pnl'))} |"
        )
    return lines


def _slug(value: Any) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").lower()
    return slug or "value"
