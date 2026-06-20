"""Load run configuration files into validated run plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import RunPlan


class ConfigLoadError(ValueError):
    """Raised when a configuration file cannot be loaded as a mapping."""


def load_run_plan(path: str | Path) -> RunPlan:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config: Any = yaml.safe_load(config_file)

    if not isinstance(raw_config, dict):
        raise ConfigLoadError(f"{config_path} must contain a YAML mapping")

    return RunPlan.from_mapping(raw_config)
