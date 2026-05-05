import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_config_has_atr_params():
    cfg = json.loads((Path(__file__).parent.parent / 'config.json').read_text())
    assert 'atr_period' in cfg
    assert 'atr_multiplier' in cfg
    assert 'take_profit_min_pct' in cfg
    assert 'take_profit_max_pct' in cfg
    assert cfg['atr_period'] == 20
    assert cfg['atr_multiplier'] == 1.5
    assert cfg['take_profit_min_pct'] == 0.03
    assert cfg['take_profit_max_pct'] == 0.12
