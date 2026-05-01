# Quantflow V1 Implementation Plan - Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete stock quantitative analysis system with 4 layers: data, indicators, strategies, and monitoring.

**Architecture:** Layered architecture with clear separation of concerns. Data layer provides unified OHLCV data from multiple sources. Indicator layer computes technical indicators. Strategy layer generates buy/sell signals. Monitoring layer orchestrates watchlists and scheduled execution.

**Tech Stack:** Python 3.10+, pandas, numpy, BaoStock, Tushare, yfinance, AKShare (for sector data)

---

## Subsystem Breakdown

This project covers multiple independent subsystems. Each subsystem plan produces working, testable software:

1. **Data Layer Plan** - `2026-04-21-quantflow-data-layer.md`
2. **Indicator Layer Plan** - `2026-04-21-quantflow-indicator-layer.md`
3. **Strategy Layer Plan** - `2026-04-21-quantflow-strategy-layer.md`
4. **Monitoring Layer Plan** - `2026-04-21-quantflow-monitoring-layer.md`

---

## Target Directory Structure

```
quantflow/
├── src/
│   ├── data/                     # 数据层
│   │   ├── __init__.py
│   │   ├── base.py               # DataSourceBase 抽象
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── baostock.py       # A股主数据源
│   │   │   ├── tushare.py        # A股降级 + 基本面数据
│   │   │   ├── yfinance.py       # 港股/美股/日股/韩股
│   │   │   └── sector.py         # 板块数据 (AKShare)
│   │   ├── factory.py            # DataSourceFactory
│   │   └── models.py             # StockCode, OHLCVData 等
│   │
│   ├── indicators/               # 指标层
│   │   ├── __init__.py
│   │   ├── base.py               # IndicatorBase 抽象
│   │   ├── standard/
│   │   │   ├── __init__.py
│   │   │   ├── kdj.py
│   │   │   ├── macd.py
│   │   │   ├── rsi.py
│   │   │   ├── boll.py
│   │   │   └── vol_ma.py
│   │   ├── custom/
│   │   │   ├── __init__.py
│   │   │   ├── dual_line.py
│   │   │   └── brick_chart.py
│   │   └── composer.py           # IndicatorComposer
│   │
│   ├── strategies/               # 策略层
│   │   ├── __init__.py
│   │   ├── base.py               # StrategyBase 抽象
│   │   ├── conditions.py         # Condition 类型定义
│   │   ├── buy/
│   │   │   ├── __init__.py
│   │   │   ├── kdj_golden_cross.py
│   │   │   ├── dual_line_bull.py
│   │   │   └── oversold_rebound.py
│   │   ├── sell/
│   │   │   ├── __init__.py
│   │   │   ├── kdj_dead_cross.py
│   │   │   ├── dual_line_bear.py
│   │   │   └── stop_loss.py
│   │   └── composite.py          # CompositeStrategy
│   │
│   ├── monitoring/               # 监控层
│   │   ├── __init__.py
│   │   ├── watchlist.py          # Watchlist 管理
│   │   ├── task.py               # MonitorTask 定义
│   │   ├── runner.py             # MonitorRunner 执行器
│   │   ├── storage.py            # 结果存储 (文件)
│   │   ├── output.py             # 输出格式化
│   │   └── alerts/
│   │       ├── __init__.py
│   │       └── base.py           # AlertChannel 抽象
│   │
│   ├── backtest/                 # 回测层 (预留)
│   │   └── __init__.py
│   │
│   ├── risk/                     # 风控层 (预留)
│   │   └── __init__.py
│   │
│   └── config/
│   │   ├── __init__.py
│   │   ├── default.yaml          # 默认配置
│   │   └── loader.py             # 配置加载器
│   │
├── scripts/                      # CLI 入口
│   ├── run_scan.py
│   └── run_monitor.py
│
├── tests/                        # 测试
│   ├── data/
│   ├── indicators/
│   ├── strategies/
│   └── monitoring/
│
├── config.yaml                   # 主配置
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Data Source Configuration

| Market | Primary Source | Fallback | Notes |
|--------|----------------|----------|-------|
| A股 (CN) | BaoStock | Tushare | BaoStock 免费，Tushare 需要 token |
| 港股 (HK) | yfinance | - | 无降级 |
| 美股 (US) | yfinance | - | 无降级 |
| 日股 (JP) | yfinance | - | 无降级 |
| 韩股 (KR) | yfinance | - | 无降级 |
| 板块数据 | AKShare (sector module) | - | 行业/概念成分股 |

---

## Execution Order

Recommended execution sequence (each phase produces testable output):

1. **Phase 0**: Create directory structure + config files
2. **Phase 1**: Data layer (can be tested independently)
3. **Phase 2**: Indicator layer (depends on Phase 1, testable)
4. **Phase 3**: Strategy layer (depends on Phase 2, testable)
5. **Phase 4**: Monitoring layer (depends on Phase 1-3)
6. **Phase 5**: Migration of existing code
7. **Phase 6**: Integration tests

---

## Integration Points for Future Layers

### Backtest Layer (预留)
- `DataSourceBase.get_history_range(code) -> (min_date, max_date)`
- `IndicatorBase.calculate()` support batch processing
- `StrategyBase.backtest(df) -> BacktestResult`

### Risk Layer (预留)
- Signal output include `position_size: float`
- `StopLossStrategy`, `TakeProfitStrategy` types

### Storage Layer (预留)
- `DataCache` abstraction (file-based initially, database later)
- `MonitorStorage` abstract class

---

## Next Steps

Execute subsystem plans in order. Each plan is in separate file:

- See `2026-04-21-quantflow-data-layer.md` for Data Layer implementation
- See `2026-04-21-quantflow-indicator-layer.md` for Indicator Layer implementation
- See `2026-04-21-quantflow-strategy-layer.md` for Strategy Layer implementation
- See `2026-04-21-quantflow-monitoring-layer.md` for Monitoring Layer implementation