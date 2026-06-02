# Model Trading Constraints in the Business Layer

China A-share trading constraints will be modeled and tested in the business layer rather than treated as hidden behavior inside backtrader. This includes T+1 selling, limit-up and limit-down behavior, suspension, board-lot sizing, fees, slippage, and cash checks.

Backtrader remains responsible for engine execution details such as order processing, fills, portfolio state, and broker notifications through the engine adapter. Keeping market-specific constraints in the business layer makes those rules testable and keeps the future path open to replace the backtest engine.
