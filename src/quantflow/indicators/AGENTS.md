# INDICATORS - QUANTFLOW

**Scope:** `src/quantflow/indicators/`

## OVERVIEW

Technical indicator framework: standard (KDJ/MACD/RSI/BOLL/VOL_MA) + custom (DualLine/BrickChart/Washout) + composition system.

## STRUCTURE

```
indicators/
├── base.py            # IndicatorBase abstract class
├── standard/          # Built-in indicators
│   ├── kdj.py         # Stochastic oscillator (N=9, M1=3, M2=3)
│   ├── macd.py        # Moving Average Convergence Divergence
│   ├── rsi.py         # Relative Strength Index
│   ├── boll.py        # Bollinger Bands
│   └── vol_ma.py      # Volume Moving Average
├── custom/            # Custom indicators
│   ├── dual_line.py   # EMA + MA bull/bear zone detection
│   ├── brick_chart.py # Price-based chart transformation
│   └── washout_short_term.py # Multi-cycle position analysis for washout dips
├── composer.py        # IndicatorComposer - chain multiple indicators
└── __init__.py
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Indicator interface | `base.py` | `IndicatorBase.calculate(df)`, `get_output_fields()` |
| KDJ calculation | `standard/kdj.py` | Stochastic oscillator (n=9, m1=3, m2=3), Wilder EMA for RSI |
| DualLine zones | `custom/dual_line.py` | Bull zone (EMA > MA), bear zone (EMA < MA) |
| Indicator chaining | `composer.py` | `IndicatorComposer([ind1, ind2]).compose(df)` |

## CONVENTIONS

- **Pattern**: All indicators inherit `IndicatorBase(ABC)`
- **Input**: `DataFrame` with OHLCV columns
- **Output**: Augmented `DataFrame` with indicator value columns only
- **Parameters**: Configurable via constructor, sensible defaults provided
- **Lookback**: Every indicator MUST implement `lookback_bars` (minimum bars needed) and may override `required_period` ('d' or 'w')

## ANTI-PATTERNS

- Do NOT mix indicator logic with strategy logic — indicators calculate values, strategies decide signals
- Do NOT hardcode column names — use `get_output_fields()` method
- Do NOT modify input DataFrame in place — return new DataFrame
- Do NOT omit `lookback_bars` property — it is abstract and required for correct data fetching

## NOTES

- **Brick Chart Convergence**: The Brick Chart indicator requires sufficient historical data (recommended >200 bars/1 year) to converge with TDX values. Short data windows will show numerical divergence due to SMA initialization, though trend signals remain accurate.
- **Brick Chart Data Sensitivity**: Numerical values may differ slightly from TDX if the source data (BaoStock vs TDX prices) has minor discrepancies in adjusted prices, but the color/trend logic remains valid.
- KDJ produces `K`, `D`, `J`, `RSV` columns; cross signals built in strategy layer
- **DualLine Strict Mode**:
  - DualLine uses 4 MA periods (14, 28, 57, 114).
  - **Behavior**: Requires minimum ~114 bars of history to calculate `long_short_line`.
  - **New Stocks**: If history < 114 days, returns `NaN` for the line. Strategies will naturally fail to generate signal (Safe).
- Composer applies indicators sequentially, each can depend on previous results
