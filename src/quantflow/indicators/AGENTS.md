# Indicators

- Implement `IndicatorBase` with `calculate()`, named output fields and `lookback_bars`.
  Preserve the input frame. Indicators calculate values, while strategies decide signals.
- Resolve instances through `IndicatorFactory` so YAML overrides, disabled indicators,
  and execution snapshots apply consistently. Register exported indicator classes in
  the standard or custom package for Library discovery.
- DualLine combines short EMA smoothing and a mean of four moving averages. With its
  default periods the long/short line needs 114 daily observations. Warm-up rows have
  unavailable values and are excluded by strategy prerequisites.
- BrickChart preserves undefined values and resumes when its inputs are valid. Seed history
  and the price adjustment basis affect comparisons against TongDaXin. Verify convergence
  using the same frozen source data and an explicit tolerance.
- `IndicatorComposer` runs indicators sequentially over the augmented DataFrame.
  Current scan and strategy execution accepts daily input periods.
- See [standard indicator outputs](standard/AGENTS.md). Run
  `python -m pytest tests/indicators` for offline cases.
