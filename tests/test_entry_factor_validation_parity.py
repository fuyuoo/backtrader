from attbacktrader.reports import (
    build_entry_factor_validation_matrix,
    compare_entry_factor_validation_matrix_parity,
)


def test_entry_factor_validation_matrix_parity_accepts_matching_valid_and_invalid_candidates() -> None:
    reference = _matrix(
        [
            _validation_record(1, cumulative_return=0.03, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
            _validation_record(2, cumulative_return=0.0, max_drawdown=0.0, trade_count=0, evidence={"status": "error", "error_count": 1}),
        ]
    )
    candidate = _matrix(
        [
            _validation_record(1, cumulative_return=0.03, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
            _validation_record(2, cumulative_return=0.0, max_drawdown=0.0, trade_count=0, evidence={"status": "error", "error_count": 1}),
        ]
    )

    report = compare_entry_factor_validation_matrix_parity(reference, candidate)

    assert report.equivalent is True
    assert report.mismatches == ()


def test_entry_factor_validation_matrix_parity_reports_core_metric_mismatch_path() -> None:
    reference = _matrix(
        [
            _validation_record(1, cumulative_return=0.03, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
        ]
    )
    candidate = _matrix(
        [
            _validation_record(1, cumulative_return=0.031, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
        ]
    )

    report = compare_entry_factor_validation_matrix_parity(reference, candidate)

    assert report.equivalent is False
    assert any(
        mismatch.candidate_index == 1
        and mismatch.path == "rows[1].metrics.cumulative_return"
        and mismatch.reference == 0.03
        and mismatch.candidate == 0.031
        for mismatch in report.mismatches
    )


def test_entry_factor_validation_matrix_parity_reports_matrix_shape_mismatch() -> None:
    reference = _matrix(
        [
            _validation_record(1, cumulative_return=0.03, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
            _validation_record(2, cumulative_return=0.0, max_drawdown=0.0, trade_count=0, evidence={"status": "error"}),
        ]
    )
    candidate = _matrix(
        [
            _validation_record(1, cumulative_return=0.03, max_drawdown=0.01, trade_count=12, evidence={"status": "ok"}),
        ]
    )

    report = compare_entry_factor_validation_matrix_parity(reference, candidate)

    assert report.equivalent is False
    assert any(
        mismatch.candidate_index is None
        and mismatch.path == "rows.candidate_indexes"
        and mismatch.reference == (1, 2)
        and mismatch.candidate == (1,)
        for mismatch in report.mismatches
    )


def _matrix(records: list[dict]) -> dict:
    return build_entry_factor_validation_matrix(
        records,
        baseline_metrics={
            "cumulative_return": 0.02,
            "max_drawdown": 0.015,
            "trade_count": 20,
            "win_rate": 0.5,
            "profit_loss_ratio": 1.1,
        },
        baseline_run_id="baoma-baseline",
    )


def _validation_record(
    candidate_index: int,
    *,
    cumulative_return: float,
    max_drawdown: float,
    trade_count: int,
    evidence: dict,
) -> dict:
    return {
        "schema": "attbacktrader.entry_factor_validation_run.v1",
        "candidate": {
            "candidate_index": candidate_index,
            "candidate_rank": candidate_index,
            "direction": "positive",
            "action": "keep",
            "field_key": f"symbol.factor_{candidate_index}",
            "value": "x",
            "value_label_zh": "x",
            "sample_count": 100 + candidate_index,
            "factor_quality_score": 1.0,
            "run_id": f"run-{candidate_index}",
        },
        "run": {"id": f"run-{candidate_index}", "from_date": "2023-01-01", "to_date": "2024-12-31"},
        "run_summary": {
            "metrics": {
                "cumulative_return": cumulative_return,
                "max_drawdown": max_drawdown,
                "trade_count": trade_count,
                "win_rate": 0.55,
                "profit_loss_ratio": 1.2,
            },
            "benchmarks": [{"symbol": "000300.SH", "excess_return": cumulative_return - 0.01}],
            "evidence": evidence,
        },
        "artifacts": {"validation_json": f"candidate-{candidate_index}/entry_factor_validation_run.json"},
    }
