# 策略接入模板

这个模板用于接入未来的新策略。当前 KDJ/MA 策略只是框架验收
fixture，不是后续策略方向。

目标是让新策略只关心三件事：

```text
声明指标需求 -> 输出 TradeIntent -> 通过验收测试
```

只要新策略满足 `docs/architecture/strategy-output-contract.md`，下游的
`signal_audit`、`trade_lifecycle`、`trade_review`、`environment_fit`、
`strategy_adaptation_matrix` 和 AI review packet 都应继续可用。

## 接入边界

策略方法可以做：

- 读取已经准备好的 `MarketFeatureRow`、指标值、持仓状态和价格。
- 计算买入、卖出、止损、加仓的决策判断。
- 输出 `TradeIntent`。
- 在 `signal_values` 里记录 `checks`、`attribution.checks`、
  `attribution.values` 和 `attribution.categories`。

策略方法不能做：

- 拉取行情。
- 重新计算可复用指标。
- 写报告或写 run artifact。
- 把报告层归因结论直接变成交易规则。
- 用默认值填充缺失指标或 warmup 不足的结果。

## 需要修改的文件

| 文件 | 作用 |
|---|---|
| `attbacktrader/strategies/methods/entry.py` | 新增买入方法。 |
| `attbacktrader/strategies/methods/profit_taking.py` | 新增止盈/退出方法。 |
| `attbacktrader/strategies/methods/stop_loss.py` | 新增止损方法。 |
| `attbacktrader/strategies/methods/add_on.py` | 新增加仓方法。 |
| `attbacktrader/strategies/methods/__init__.py` | 导出新方法。 |
| `attbacktrader/strategies/bindings.py` | 把方法名绑定到 `trend_template_v1`。 |
| `tests/test_strategy_methods.py` | 测触发、不触发、指标缺失、reason code 和 checks。 |
| `tests/test_strategy_bindings.py` | 测配置绑定、参数校验和 required indicators。 |
| `tests/test_strategy_output_contract.py` | 测新方法输出契约。 |
| `examples/<strategy-run>.yaml` | 给新策略一个可运行 RunPlan。 |

## Entry 方法骨架

```python
from dataclasses import dataclass
from datetime import date

from attbacktrader.features import IndicatorRequirement, MarketFeatureRow
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


@dataclass(frozen=True)
class MyEntryMethod:
    threshold: float = 0.0
    method_name: str = "my_entry_method"

    @property
    def required_indicators(self) -> frozenset[IndicatorRequirement]:
        return frozenset({
            IndicatorRequirement("macd", "D"),
        })

    def evaluate(
        self,
        *,
        symbol: str,
        trade_date: date,
        row: MarketFeatureRow | None = None,
        previous_row: MarketFeatureRow | None = None,
    ) -> TradeIntent:
        if row is None:
            return TradeIntent(
                TradeIntentType.HOLD,
                symbol,
                trade_date,
                self.method_name,
                "MY_ENTRY_UNAVAILABLE",
                signal_values={"checks": {"required_values_available": False}},
            )

        try:
            macd = row.indicators.macd_at("D")
        except KeyError:
            return TradeIntent(
                TradeIntentType.HOLD,
                symbol,
                trade_date,
                self.method_name,
                "MY_ENTRY_UNAVAILABLE",
                signal_values={"checks": {"required_values_available": False}},
            )

        triggered = macd.histogram > self.threshold
        signal_values = {
            "macd_histogram": macd.histogram,
            "threshold": self.threshold,
            "checks": {
                "required_values_available": True,
                "macd_histogram_above_threshold": triggered,
            },
            "attribution": entry_attribution_payload(
                checks={"symbol.macd.histogram_above_threshold": triggered},
                values={
                    "symbol.macd.histogram": macd.histogram,
                    "symbol.macd.threshold": self.threshold,
                },
            ),
        }

        if triggered:
            return TradeIntent(
                TradeIntentType.ENTER,
                symbol,
                trade_date,
                self.method_name,
                "MY_ENTRY_TRIGGERED",
                signal_values=signal_values,
            )

        return TradeIntent(
            TradeIntentType.HOLD,
            symbol,
            trade_date,
            self.method_name,
            "MY_ENTRY_NOT_TRIGGERED",
            signal_values=signal_values,
        )
```

## Exit 方法骨架

退出方法结构和 entry 一样，差别是触发时返回：

```python
TradeIntentType.EXIT_PROFIT
```

止损方法触发时返回：

```python
TradeIntentType.EXIT_LOSS
```

退出和止损也要记录 `checks`，例如：

```python
"checks": {
    "required_values_available": True,
    "price_below_stop": price_below_stop,
}
```

## Add-On 方法骨架

加仓方法必须额外接收持仓状态：

```python
def evaluate(
    self,
    *,
    symbol: str,
    trade_date: date,
    current_quantity: int,
    entry_price: float,
    current_price: float,
    add_on_count: int,
    row: MarketFeatureRow | None = None,
    previous_row: MarketFeatureRow | None = None,
) -> TradeIntent:
    ...
```

触发时返回：

```python
TradeIntentType.ADD_ON
```

未触发返回 `HOLD`，并记录原因，例如：

```text
MY_ADD_ON_NOT_TRIGGERED
```

## Binding 模板

在 `attbacktrader/strategies/methods/__init__.py` 导出：

```python
from .entry import MyEntryMethod
```

在 `attbacktrader/strategies/bindings.py` 注册：

```python
_ENTRY_METHODS = {
    ...
    "my_entry_method": MyEntryMethod,
}
```

不要允许 RunPlan 覆盖 `method_name`。当前绑定层已经会拒绝
`entry_params.method_name`。

## RunPlan 模板

```yaml
strategy:
  template: trend_template_v1
  entry_method: my_entry_method
  entry_params:
    threshold: 0.0
  profit_taking_method: my_exit_method
  stop_loss_method: fixed_percent_stop
  add_on_method: none
  sizing_rule: equal_weight
```

## 验收测试

接入或修改策略后，先跑静态接入校验：

```text
python -m attbacktrader.cli.strategy_integration_validation --config examples/<strategy-run>.yaml --json
```

这个命令只加载 RunPlan、绑定策略组件、构造最小样本调用各买卖方法，并校验 `TradeIntent` 输出契约；它不拉行情、不跑完整回测、不评价策略优劣。包入口刷新后也可以使用短命令 `att-validate-strategy-integration`。

最小验收：

```text
python -m pytest tests/test_strategy_methods.py tests/test_strategy_bindings.py tests/test_strategy_output_contract.py tests/test_strategy_integration_validation.py -q
```

接入回测链路后再跑：

```text
python -m pytest tests/test_run_plan_executor.py tests/test_report_writer.py tests/test_evidence_validation.py -q
```

封板前跑：

```text
python scripts/acceptance_smoke.py
python -m pytest -q
```

## 完成标准

一个新策略接入完成，需要满足：

- 方法触发和不触发路径都有稳定 `reason_code`。
- 指标缺失时不默认填充，返回 unavailable/hold 证据。
- `required_indicators` 能覆盖所有需要预热的指标。
- `TradeIntent` 通过策略输出契约。
- `trade_lifecycle.json` 能反查入场、退出和加仓事件。
- `environment_fit.json` 和 `strategy_adaptation_matrix.json` 可以继续消费入场证据。
- AI review 可以从 persisted artifacts 复盘，不需要知道具体策略代码。
