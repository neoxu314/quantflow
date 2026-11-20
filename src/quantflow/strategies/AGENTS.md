# Trading strategies

- `get_required_indicators()` declares each input using `IndicatorFactory.create()`.
  Required lookback and output validity depend on the instances resolved from
  `config/indicators.yaml`.
- `get_conditions()` returns `Condition` objects. Strategies receive augmented OHLCV
  and emit boolean `buy_signal` or `sell_signal` columns. Custom strategies can
  implement `generate_signals()` when they need their own signal computation.
- Keep class docstrings current because Web Library displays them. Registered IDs
  and rule definitions are summarized in the [README](../../../README.md#configuration).
- `CompositeStrategy` combines child strategies in Python. It supports nesting
  and evaluates `any` or `all` separately per direction, using only children
  that emit that direction. Task YAML accepts lists of registered strategies and
  runs them independently.
- `StopLossSell.generate_signals_with_entry()` accepts an explicit entry price
  in Python. This strategy is outside the task registry.
- Run `python -m pytest tests/strategies tests/test_rebound_workflows.py`.
