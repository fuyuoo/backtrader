# Use YAML Configuration Validated Into Run Plans

The first version will use YAML configuration validated into immutable run plans before a backtest starts. A single `run.yaml` will define data scope, the selected strategy template, component bindings, sizing rules, execution rules, trading constraints, benchmark comparison, market regime analysis, and reporting options.

Pydantic-style validation will reject invalid or incomplete configuration before execution. Entry, profit-taking, and stop-loss behavior will be expressed as code-backed methods bound to a fixed strategy template, with configuration selecting one allowed method of each type for a run. If a method needs multiple signal conditions, those conditions are calculated and interpreted inside that method rather than composed globally by the framework.
