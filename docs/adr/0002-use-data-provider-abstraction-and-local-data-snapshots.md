# Use Data Provider Abstraction and Local Data Snapshots

We will access market, industry, index, and reference data through a data provider abstraction rather than coupling the research pipeline directly to Tushare. Tushare is the current provider implementation, but strategy research, feature calculation, backtesting, scenario analysis, and tests consume local data snapshots.

Time-series data such as daily bars, industry series, and index series will be stored as Parquet snapshots. Metadata and slowly changing reference data may use SQLite when tabular lookup or relational constraints are useful. This makes backtests reproducible, keeps tests offline, and leaves room to add or replace data providers later.

Stock daily bars default to front-adjusted `qfq` prices when collected from Tushare. Derived indicator snapshots must be stored under the same price-adjustment namespace as the source daily bars, such as `daily_bars/qfq/...` and `indicators/kdj/qfq/...`, so backtests do not accidentally mix raw and derived data calculated from different price bases.
