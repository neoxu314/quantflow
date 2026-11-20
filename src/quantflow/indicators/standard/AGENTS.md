# Standard indicators

These are constructor defaults. `config/indicators.yaml` may override them when
instances are created through `IndicatorFactory`.

| Name | Parameters | Output columns |
| --- | --- | --- |
| KDJ | `n=9, m1=3, m2=3` | `K`, `D`, `J` |
| MACD | `fast_period=12, slow_period=26, signal_period=9` | `DIF`, `DEA`, `MACD` |
| RSI | `periods=[14]` | `RSI14`. The shipped YAML uses `RSI6`, `RSI12`, `RSI24` |
| BOLL | `period=20, std_dev=2.0` | `BOLL_MID`, `BOLL_UPPER`, `BOLL_LOWER` |
| VOL_MA | `periods=[5, 10, 20]` | `VOL_MA5`, `VOL_MA10`, `VOL_MA20` |

Derive parameterized fields from `get_output_fields()` and compare indicator calculations
without embedding buy/sell rules. KDJ computes RSV internally.
