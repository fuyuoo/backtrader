"""Experiment decision records for closing bounded backtest experiments."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPERIMENT_DECISIONS_SCHEMA = "attbacktrader.experiment_decisions.v1"
EXPERIMENT_DECISION_VALUES = ("accepted", "rejected", "parked")


def build_experiment_decisions(
    *,
    lifecycle: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    source_lifecycle: str | Path | None = None,
    source_decisions: str | Path | None = None,
) -> dict[str, Any]:
    """Build a decision log from explicit decision inputs and lifecycle chains."""

    chains = {str(chain.get("chain_id")): _as_mapping(chain) for chain in _as_sequence(lifecycle.get("chains"))}
    records = [
        _decision_record(
            decision,
            chains=chains,
        )
        for decision in decisions
    ]
    invalid_count = sum(1 for record in records if record.get("status") != "recorded")
    decided_chain_ids = {
        str(record.get("chain_id"))
        for record in records
        if record.get("status") == "recorded" and record.get("decision") in EXPERIMENT_DECISION_VALUES
    }
    chains_waiting_decision = [
        str(chain.get("chain_id"))
        for chain in _as_sequence(lifecycle.get("chains"))
        if "decision" in _as_sequence(_as_mapping(chain).get("missing_stages"))
        and str(_as_mapping(chain).get("chain_id")) not in decided_chain_ids
    ]
    return {
        "schema": EXPERIMENT_DECISIONS_SCHEMA,
        "source_lifecycle": _source_ref(source_lifecycle, payload=lifecycle),
        "source_decisions": _source_ref(source_decisions, payload={"schema": "attbacktrader.experiment_decision_inputs.v1"}),
        "decision_count": len(records),
        "recorded_decision_count": len(records) - invalid_count,
        "invalid_decision_count": invalid_count,
        "decision_counts": _count_rows(Counter(str(record.get("decision")) for record in records)),
        "open_decision_gap_count": len(chains_waiting_decision),
        "chains_waiting_decision": chains_waiting_decision,
        "records": records,
        "rules": [
            "Experiment Decision Records 只记录显式输入的 accepted/rejected/parked，不根据收益自动判定。",
            "decision 必须引用 lifecycle chain_id；找不到 chain 时记录为 unknown_chain。",
            "accepted/rejected/parked 是实验治理状态，不等于上线策略、自动调参或自动切换。",
            "rejected 表示不沿该实验方向继续优化；parked 表示证据不足或非当前优先级。",
            "每条 decision 必须保留 reason_zh、evidence_refs 和 next_allowed_action_zh。",
        ],
    }


def build_experiment_decisions_from_files(
    *,
    lifecycle_path: str | Path,
    decision_file: str | Path,
) -> dict[str, Any]:
    """Build a decision log from lifecycle and decision JSON files."""

    lifecycle = _as_mapping(_load_json_if_exists(Path(lifecycle_path)))
    decision_payload = _as_mapping(_load_json_if_exists(Path(decision_file)))
    return build_experiment_decisions(
        lifecycle=lifecycle,
        decisions=[_as_mapping(item) for item in _as_sequence(decision_payload.get("decisions"))],
        source_lifecycle=lifecycle_path,
        source_decisions=decision_file,
    )


def render_experiment_decisions_markdown_zh(decision_log: Mapping[str, Any]) -> str:
    """Render experiment decisions as Chinese Markdown."""

    lines = [
        "# 实验 Decision Records",
        "",
        f"- schema: `{decision_log.get('schema')}`",
        f"- decision_count: `{decision_log.get('decision_count')}`",
        f"- recorded_decision_count: `{decision_log.get('recorded_decision_count')}`",
        f"- open_decision_gap_count: `{decision_log.get('open_decision_gap_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(decision_log.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(["", "## 决策分布", "", "| decision | count |", "|---|---:|"])
    for row in _as_sequence(decision_log.get("decision_counts")):
        row_map = _as_mapping(row)
        lines.append(f"| `{row_map.get('key')}` | {row_map.get('count')} |")

    lines.extend(
        [
            "",
            "## Decisions",
            "",
            "| decision | status | chain_id | current_stage | reason | next_allowed_action |",
            "|---|---|---|---|---|---|",
        ]
    )
    for record in _as_sequence(decision_log.get("records")):
        record_map = _as_mapping(record)
        chain = _as_mapping(record_map.get("chain_snapshot"))
        lines.append(
            "| "
            f"`{_markdown_value(record_map.get('decision'))}` | "
            f"`{_markdown_value(record_map.get('status'))}` | "
            f"`{_markdown_value(record_map.get('chain_id'))}` | "
            f"{_markdown_value(chain.get('current_stage'))} | "
            f"{_markdown_value(record_map.get('reason_zh'))} | "
            f"{_markdown_value(record_map.get('next_allowed_action_zh'))} |"
        )

    lines.extend(["", "## 仍缺决策的链", ""])
    waiting = _as_sequence(decision_log.get("chains_waiting_decision"))
    if waiting:
        for chain_id in waiting:
            lines.append(f"- `{chain_id}`")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def write_experiment_decisions(
    decision_log: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write experiment decisions JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "experiment_decisions.json"
    markdown_path = output_path / "experiment_decisions.zh.md"
    json_path.write_text(_to_pretty_json(decision_log), encoding="utf-8")
    markdown_path.write_text(render_experiment_decisions_markdown_zh(decision_log), encoding="utf-8")
    return json_path, markdown_path


def safe_experiment_decisions_dir_name() -> str:
    return "experiment-decisions"


def _decision_record(decision: Mapping[str, Any], *, chains: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    chain_id = str(decision.get("chain_id") or "")
    decision_value = str(decision.get("decision") or "")
    chain = _as_mapping(chains.get(chain_id))
    issues = []
    if not chain_id:
        issues.append("missing_chain_id")
    elif not chain:
        issues.append("unknown_chain")
    if decision_value not in EXPERIMENT_DECISION_VALUES:
        issues.append("invalid_decision")
    if not decision.get("reason_zh"):
        issues.append("missing_reason_zh")
    if not _as_sequence(decision.get("evidence_refs")):
        issues.append("missing_evidence_refs")
    if not decision.get("next_allowed_action_zh"):
        issues.append("missing_next_allowed_action_zh")
    status = "recorded" if not issues else "invalid"
    return {
        "decision_id": str(decision.get("decision_id") or _decision_id(chain_id, decision_value)),
        "status": status,
        "issues": issues,
        "chain_id": chain_id or None,
        "decision": decision_value or None,
        "decided_on": decision.get("decided_on"),
        "decided_by": decision.get("decided_by"),
        "reason_zh": decision.get("reason_zh"),
        "evidence_refs": list(_as_sequence(decision.get("evidence_refs"))),
        "next_allowed_action_zh": decision.get("next_allowed_action_zh"),
        "notes_zh": decision.get("notes_zh"),
        "chain_snapshot": _chain_snapshot(chain),
    }


def _chain_snapshot(chain: Mapping[str, Any]) -> dict[str, Any]:
    if not chain:
        return {}
    return {
        "lineage_type": chain.get("lineage_type"),
        "title_zh": chain.get("title_zh"),
        "current_stage": chain.get("current_stage"),
        "status": chain.get("status"),
        "missing_stages_before_decision": list(_as_sequence(chain.get("missing_stages"))),
        "run_ids": list(_as_sequence(chain.get("run_ids"))),
        "executed_run_ids": list(_as_sequence(chain.get("executed_run_ids"))),
        "market_type_id": chain.get("market_type_id"),
    }


def _decision_id(chain_id: str, decision: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{chain_id}.{decision}".strip())
    return f"decision:{safe or 'unknown'}"


def _source_ref(path: str | Path | None, *, payload: Mapping[str, Any]) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "schema": None}
    source_path = Path(path)
    return {
        "path": str(source_path),
        "exists": source_path.exists(),
        "schema": payload.get("schema") if payload else None,
    }


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _count_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in sorted(counter.items())]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _markdown_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
