"""Configuration validation helpers."""

from __future__ import annotations

from .models import RunPlan


def validate_run_plan(run_plan: RunPlan) -> RunPlan:
    """Return the already-validated run plan.

    This module exists as the extension point for cross-file validation once
    configuration is split beyond the first-version single `run.yaml`.
    """

    return run_plan
