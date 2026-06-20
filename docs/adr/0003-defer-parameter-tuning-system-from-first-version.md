# Defer the Parameter Tuning System From the First Version

The system is expected to support parameter tuning in a later version, including tuning and test partitions and Bayesian optimization. The first version will not implement this capability.

We are deferring it so the first version can focus on the deterministic research pipeline: provider abstraction, local data snapshots, strategy configuration, engine adaptation, backtesting, and post-run attribution. This avoids mixing optimization concerns into the core framework before the run model and evaluation outputs are stable.
