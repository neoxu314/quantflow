# STANDARD INDICATORS - QUANTFLOW

**Scope:** `src/quantflow/indicators/standard/`

## OVERVIEW

Built-in technical indicators: KDJ, MACD, RSI, BOLL, VOL_MA. All follow `IndicatorBase` pattern.

**Indicator layer only calculates values.** Signal generation (golden/dead cross, overbought, breakout) lives in the strategy layer.

## INDICATORS

| Indicator | File | Parameters | Output Columns |
|---|---|---|---|
| KDJ | `kdj.py` | `n=9, m1=3, m2=3` | K, D, J, RSV |
| MACD | `macd.py` | `fast=12, slow=26, signal=9` | MACD, MACD_SIGNAL, MACD_HIST |
| RSI | `rsi.py` | `period=14` | RSI (Wilder EMA smoothing) |
| BOLL | `boll.py` | `period=20, std_dev=2.0` | BOLL_MID, BOLL_UPPER, BOLL_LOWER |
| VOL_MA | `vol_ma.py` | `periods=[5, 10, 20]` | VOL_MA5, VOL_MA10, VOL_MA20 |

## CONVENTIONS

- **Class naming**: `{Name}Indicator` extends `IndicatorBase`
- **Calculate method**: `calculate(df: DataFrame) -> DataFrame`
- **Output fields**: `get_output_fields() -> list[str]`
- Strategy methods (golden/dead cross, etc.) are NOT in this layer

## ANTI-PATTERNS

- Do NOT use `as any` or suppress type errors
- Do NOT modify input DataFrame - always return new
- Do NOT add indicators without implementing `get_output_fields()`
- Do NOT put signal/strategy logic here (use `strategies/buy/` or `strategies/sell/`)
