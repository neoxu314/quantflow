# STRATEGIES - QUANTFLOW

**Scope:** `src/quantflow/strategies/`

## OVERVIEW

Trading signal generation layer. Buy strategies (golden cross, bull channel) + sell strategies (dead cross, bear zone) + composite (all/any mode).

## STRUCTURE

```
strategies/
├── base.py            # StrategyBase abstract class (BuyStrategy, SellStrategy)
├── buy/               # Entry signal generators
│   ├── kdj_golden_cross.py    # KDJ Golden Cross Buy Strategy
│   ├── dual_line_bull.py      # Daily Bullish Mid-Range Buy Strategy
│   └── oversold_rebound.py    # Daily Bullish Oversold Buy Strategy
├── sell/              # Exit signal generators
│   ├── kdj_dead_cross.py      # KDJ Dead Cross Sell Strategy
│   ├── dual_line_bear.py      # DualLine Bear Zone Sell Strategy
│   └── stop_loss.py           # Stop Loss Sell Strategy
├── composite.py       # CompositeStrategy - combine strategies (mode="any"|"all")
└── __init__.py
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Strategy interface | `base.py` | `StrategyBase.generate_signals(df)`, `get_conditions()` |
| Buy signals | `buy/` | KDJGoldenCrossBuy, DailyBullishMidRangeBuy, DailyBullishOversoldBuy |
| Sell signals | `sell/` | KDJDeadCrossSell, DualLineBearZoneSell, StopLossSell |
| Composition | `composite.py` | `mode="any"` (OR logic) or `"all"` (AND logic) |

## CONVENTIONS

- **Pattern**: All strategies inherit `StrategyBase(ABC)`
- **Input**: Augmented `DataFrame` with indicator columns
- **Output**: DataFrame with `buy_signal` or `sell_signal` boolean columns
- **Conditions**: `get_conditions()` returns dict of condition descriptions
- **Lookback**: Strategies MUST correctly implement `get_required_indicators()` so the system can auto-calculate data fetch range. `StrategyBase.get_lookback_bars()` aggregates from indicator `lookback_bars`.

## ANTI-PATTERNS

- Do NOT mix indicator calculation with strategy logic
- Do NOT hardcode signal column names - use consistent naming
- Do NOT bypass composite strategy - use it for multi-condition signals
- Do NOT forget to list ALL used indicators in `get_required_indicators()` — this determines how much data the system fetches
