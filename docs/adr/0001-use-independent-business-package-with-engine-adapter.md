# Use an Independent Business Package With an Engine Adapter

We will build the quantitative research and backtesting system as an independent business package named `attbacktrader` instead of modifying the backtrader core directly. Backtrader is the current backtest engine, reached through an engine adapter that translates prepared data and strategy definitions into engine-native objects.

This keeps data acquisition, cleaning, feature calculation, strategy definition, risk evaluation, and scenario analysis independent from a single execution engine. The trade-off is an extra adapter layer now, in exchange for testable business logic and a practical path to replace backtrader later without rewriting the research pipeline.
