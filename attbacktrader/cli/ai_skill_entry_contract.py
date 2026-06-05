"""Write the ATTbacktrader AI Skill entry contract."""

from __future__ import annotations

import argparse
import json
from datetime import date

from attbacktrader.reports import (
    DEFAULT_AI_SKILL_CONTRACT_DOC_PATH,
    DEFAULT_AI_SKILL_CONTRACT_PATH,
    build_ai_skill_entry_contract,
    render_ai_skill_entry_contract_markdown_zh,
    write_ai_skill_entry_contract,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    contract = build_ai_skill_entry_contract(
        generated_on=args.generated_on,
        source_workbench_closure=args.source_workbench_closure,
        skill_name=args.skill_name,
        skill_doc_path=args.skill_doc_path,
    )
    json_path, markdown_path = write_ai_skill_entry_contract(
        contract,
        output_path=args.output,
        doc_output_path=args.doc_output,
    )
    payload = {
        "schema": contract["schema"],
        "generated_on": contract["generated_on"],
        "skill_name": contract["skill_name"],
        "entry_step_count": len(contract["entry_read_order"]),
        "mode_count": len(contract["interaction_modes"]),
        "artifacts": {
            "ai_skill_entry_contract_json_path": str(json_path),
            "ai_skill_entry_contract_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_ai_skill_entry_contract_markdown_zh(contract))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write the ATTbacktrader AI Skill entry contract")
    parser.add_argument("--generated-on", default=date.today().isoformat())
    parser.add_argument("--source-workbench-closure", default="examples/backtest-workbench-v1-baseline.json")
    parser.add_argument("--skill-name", default="attbacktrader-ai-review")
    parser.add_argument("--skill-doc-path", default=None)
    parser.add_argument("--output", default=str(DEFAULT_AI_SKILL_CONTRACT_PATH))
    parser.add_argument("--doc-output", default=str(DEFAULT_AI_SKILL_CONTRACT_DOC_PATH))
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
