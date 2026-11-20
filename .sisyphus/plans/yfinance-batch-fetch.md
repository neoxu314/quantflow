# YFinance Batch Fetch Implementation Plan

> **历史计划。** 此处记录初期 YFinance 批量拉取设计。实际主备源、批次和失败恢复见 [运行契约](../../docs/reliability-and-data-contracts.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-stock sequential yfinance API calls with `yf.download()` batch fetching, reducing network requests from N to 1 per task run.

**Architecture:** Add `fetch_batch_ohlcv()` to `YFinanceDataSource`, wire it through `DataSourceFactory`, and modify `Executor.execute()` to detect all-yFinance tasks and route them to the batch path. The batch output is "unstacked" back into individual `{code: DataFrame}` entries, keeping the downstream Indicator/Strategy pipeline completely unchanged.

**Tech Stack:** Python, yfinance (≥0.2.30), pandas MultiIndex, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/quantflow/data/adapters/yfinance.py` | Modify | Add `fetch_batch_ohlcv()` method with yf.download + unstacking logic |
| `src/quantflow/data/adapters/base.py` | Modify | Add `check_version()` static method to `YFinanceDataSource` (version guard for session support) |
| `src/quantflow/data/factory.py` | Modify | Add `fetch_batch_ohlcv()` that dispatches to yFinance batch adapter |
| `src/quantflow/execution/executor.py` | Modify | Add dispatch logic: partition items by market → yFinance → batch, BaoStock → serial |
| `tests/data/test_yfinance_batch.py` | Create | Unit tests: batch fetch mock, unstacking, empty ticker handling, single-item edge case |
| `pyproject.toml` | Modify | Bump yfinance minimum from `>=0.2.0` to `>=0.2.30` |

---

### Task 1: Update yfinance version requirement

**Files:**
- Modify: `pyproject.toml:18`

- [ ] **Step 1: Bump yfinance minimum version**

Current line 18:
```toml
    "yfinance>=0.2.0",
```
Change to:
```toml
    "yfinance>=0.2.30",
```

Rationale: yfinance ≥ 0.2.30 supports `session` parameter in `yf.download()`, which is needed to reuse our `curl_cffi` Chrome impersonation session.

- [ ] **Step 2: Verify change**

Run:
```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow && pip show yfinance
```
Expected: Version >= 0.2.30. If installed version is older, run `pip install -e .` to upgrade.

---

### Task 2: Implement `fetch_batch_ohlcv` in YFinanceDataSource

**Files:**
- Modify: `src/quantflow/data/adapters/yfinance.py`

- [ ] **Step 1: Add version check method to YFinanceDataSource class**

Add after line 61 (after `get_name`):

```python
    @staticmethod
    def check_version() -> bool:
        """Check if yfinance version supports batch download with session parameter.
        
        Returns True if version >= 0.2.30.
        """
        try:
            import yfinance as yf
            version = tuple(int(x) for x in yf.__version__.split("."))
            return version >= (0, 2, 30)
        except Exception:
            return False
```

- [ ] **Step 2: Add `fetch_batch_ohlcv` method to YFinanceDataSource class**

Add after `fetch_fundamental` (end of file, line 142):

```python
    def fetch_batch_ohlcv(
        self,
        codes: List["StockCode"],
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """Fetch OHLCV data for multiple stocks in a single batch call.
        
        Args:
            codes: List of StockCode objects to fetch.
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            period: d/w/m
            adjust: Ignored (yfinance uses market-specific adjustment).
        
        Returns:
            Dict mapping standard code string (e.g., "AAPL.US") to DataFrame
            with same column structure as fetch_ohlcv:
            [date, open, high, low, close, volume].
            Stocks with no data are excluded from the dict.
        
        Raises:
            RuntimeError: If yfinance version < 0.2.30.
        """
        if not self.check_version():
            raise RuntimeError(
                "Batch OHLCV fetch requires yfinance >= 0.2.30. "
                f"Installed version may not support session parameter in yf.download()."
            )
        
        import yfinance as yf
        
        if not codes:
            return {}
        
        interval = self.PERIOD_INTERVAL.get(period, "1d")
        
        # Build ticker list: [yf_symbol, ...] and a parallel mapping back to StockCode
        symbol_to_code: Dict[str, str] = {}
        yf_symbols: List[str] = []
        for code_obj in codes:
            yf_sym = self._get_yfinance_symbol(code_obj)
            std_key = code_obj.standard  # e.g., "AAPL.US"
            symbol_to_code[yf_sym] = std_key
            yf_symbols.append(yf_sym)
        
        logger.info(
            f"Batch fetching {len(yf_symbols)} tickers via YFinance download: "
            f"{', '.join(yf_symbols[:5])}{'...' if len(yf_symbols) > 5 else ''}"
        )
        
        try:
            df_multi = yf.download(
                tickers=yf_symbols,
                start=start_date,
                end=end_date,
                interval=interval,
                group_by="ticker",
                threads=True,
                session=self._session,
                progress=False,
            )
        except Exception as e:
            logger.error(f"Batch yfinance download failed: {e}")
            return {}
        
        if df_multi is None or df_multi.empty:
            logger.warning("Batch download returned empty result")
            return {}
        
        # Unstack MultiIndex DataFrame into per-ticker DataFrames
        result: Dict[str, pd.DataFrame] = {}
        
        for yf_sym in yf_symbols:
            try:
                # group_by='ticker' → columns are (Ticker, OHLCV_column)
                single = df_multi[yf_sym]
            except KeyError:
                # This ticker had no data at all
                continue
            
            if single.empty:
                continue
            
            single = single.reset_index()
            single = single.rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            
            # Same column selection as single-stock fetch_ohlcv
            cols = ["date", "open", "high", "low", "close", "volume"]
            single = single[[c for c in cols if c in single.columns]]
            
            if single.empty:
                continue
            
            std_key = symbol_to_code.get(yf_sym, yf_sym)
            result[std_key] = single.reset_index(drop=True)
        
        logger.info(f"Batch complete: {len(result)}/{len(yf_symbols)} tickers with data")
        return result
```

- [ ] **Step 3: Add `List` and `Dict` imports if not already present**

Verify the top of `yfinance.py` has:
```python
from typing import Optional, List, Dict
```

If not, change line 22 from:
```python
from typing import Optional
```
to:
```python
from typing import Optional, List, Dict
```

---

### Task 3: Add `fetch_batch_ohlcv` to DataSourceFactory

**Files:**
- Modify: `src/quantflow/data/factory.py`

- [ ] **Step 1: Add `fetch_batch_ohlcv` method to DataSourceFactory**

Add after `fetch_fundamental` (after line 109), before `get_sector_source` (line 111):

```python
    def fetch_batch_ohlcv(
        self,
        codes: List[StockCode],
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: str = "qfq",
    ) -> Dict[str, tuple[pd.DataFrame, Optional[str]]]:
        """Fetch OHLCV for multiple stocks from yFinance in one batch call.
        
        Only stocks with yFinance as their primary source are fetched via batch.
        Stocks with other primary sources (e.g., BaoStock) are excluded from
        the result and should be fetched via the regular fetch_ohlcv path.
        
        Args:
            codes: List of StockCode objects.
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            period: d/w/m
            adjust: Adjustment type (passed through, yfinance ignores this).
        
        Returns:
            Dict mapping standard code string to (DataFrame, source_name).
            Only includes stocks successfully fetched via yFinance.
        """
        if not codes:
            return {}
        
        yf_codes: List[StockCode] = []
        yf_adapter = self._get_adapter("yfinance")
        
        for code_obj in codes:
            market = self._detect_market(code_obj)
            primary = self.config.get_primary(market)
            if primary == "yfinance" and yf_adapter.supports_market(market):
                yf_codes.append(code_obj)
        
        if not yf_codes:
            return {}
        
        batch_result = yf_adapter.fetch_batch_ohlcv(
            yf_codes, start_date, end_date, period, adjust
        )
        
        return {code_str: (df, "yfinance") for code_str, df in batch_result.items()}
```

- [ ] **Step 2: Add `List` and `Dict` imports if needed**

Verify line 5 imports:
```python
from typing import Optional, Dict, Any, List
```

If `List` is not there, add it.

---

### Task 4: Modify Executor to use batch fetch for yFinance stocks

**Files:**
- Modify: `src/quantflow/execution/executor.py`

- [ ] **Step 1: Modify `execute()` method to partition items by market and use batch path for yFinance**

Replace the entire `execute` method (lines 28-98) with:

```python
    def execute(self, job: ExecutionJob) -> List[ExecutionResultItem]:
        total = len(job.items)
        logger.info(f"Starting execution: {job.name} ({total} items)")
        results = []
        start_date = (datetime.now() - timedelta(days=job.days_back)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        # Partition items by data source
        yfinance_items: List[tuple] = []
        other_items: List[tuple] = []

        for item in job.items:
            code = item.code
            if isinstance(code, str):
                code = StockCode.from_standard(code)
            market = self.factory._detect_market(code)
            primary = self.factory.config.get_primary(market)
            if primary == "yfinance":
                yfinance_items.append((item, code))
            else:
                other_items.append((item, code))

        # Batch fetch yFinance stocks
        yf_data: Dict[str, pd.DataFrame] = {}
        if yfinance_items:
            yf_codes = [code for _, code in yfinance_items]
            batch_result = self.factory.fetch_batch_ohlcv(
                yf_codes, start_date, end_date
            )
            for code_str, (df, _src) in batch_result.items():
                yf_data[code_str] = df
            logger.info(
                f"yFinance batch complete: {len(yf_data)}/{len(yfinance_items)} stocks"
            )

        # Process yFinance batch results
        for item, code in yfinance_items:
            df = yf_data.get(code.standard)
            if df is None or df.empty:
                logger.warning(f"No data for {item.code}")
                continue
            result = self._process_single(item, code, df, job)
            if result:
                results.append(result)

        # Sequential fetch for non-yFinance stocks
        for idx, (item, code) in enumerate(other_items, 1):
            try:
                logger.info(f"Processing [{idx}/{total}]: {item.code}")
                df, _ = self.factory.fetch_ohlcv(code, start_date=start_date, end_date=end_date)
                if df.empty:
                    logger.warning(f"No data for {item.code}")
                    continue
                result = self._process_single(item, code, df, job)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed {item.code}: {e}")

        # Save results
        path = f"{job.output_dir}/{job.name}.json"
        if results:
            self.storage.save_results(path, results)
            logger.info(f"Saved results to {path}")

        return results
```

- [ ] **Step 2: Extract signal processing into `_process_single` helper**

Add after `execute` method (at end of class) or just before it:

```python
    def _process_single(
        self,
        item,
        code: StockCode,
        df: pd.DataFrame,
        job,
    ) -> Optional[ExecutionResultItem]:
        """Process a single stock's DataFrame through indicators and strategies.
        
        Returns ExecutionResultItem if signals found, None otherwise.
        """
        df = self.composer.compose(df)

        buy_signals = 0
        sell_signals = 0
        signal_reasons = []
        matched_buy_strategies = []
        matched_sell_strategies = []

        for strategy in job.strategies:
            df = strategy.generate_signals(df)
            latest_day = df.iloc[-1]
            s_name = strategy.name

            if latest_day.get("buy_signal", False):
                buy_signals += 1
                reason = latest_day.get("signal_reason", "Triggered")
                if pd.notna(reason) and str(reason):
                    signal_reasons.append(str(reason))
                matched_buy_strategies.append(s_name)

            if latest_day.get("sell_signal", False):
                sell_signals += 1
                reason = latest_day.get("signal_reason", "Triggered")
                if pd.notna(reason) and str(reason):
                    signal_reasons.append(str(reason))
                matched_sell_strategies.append(s_name)

        if buy_signals > 0 or sell_signals > 0:
            return ExecutionResultItem(
                code=item.code.standard if hasattr(item.code, "standard") else item.code,
                name=getattr(item, "name", ""),
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                reasons=signal_reasons[:5],
                matched_buy_strategies=matched_buy_strategies,
                matched_sell_strategies=matched_sell_strategies,
            )
        return None
```

- [ ] **Step 3: Add missing imports**

Verify imports at top of executor.py include:
```python
from typing import List, Dict, Optional
```

And also add at the top if not present:
```python
from quantflow.data.base import StockCode
```

(Currently imports `StockCode` from `quantflow.data` — verify that `from quantflow.data import DataSourceFactory, StockCode` already exists on line 7.)

---

### Task 5: Write unit tests for batch fetch

**Files:**
- Create: `tests/data/test_yfinance_batch.py`

- [ ] **Step 1: Create test file with mocked batch fetch tests**

Create the complete test file:

```python
"""Tests for YFinance batch OHLCV fetching."""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


class MockMultiIndexDataFrame:
    """Helper to create mock MultiIndex DataFrames for yfinance batch responses."""

    @staticmethod
    def create_batch(tickers_data: dict[str, list[dict]], columns=None):
        """Create a mock yfinance batch download DataFrame.
        
        Args:
            tickers_data: {"AAPL": [{"date": ..., "open": ..., ...}], ...}
            columns: OHLCV columns to include (default: all 6)
        """
        if columns is None:
            columns = ["open", "high", "low", "close", "volume"]

        frames = {}
        for ticker, rows in tickers_data.items():
            df = pd.DataFrame(rows)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            for col in columns:
                if col not in df.columns:
                    df[col] = 0.0
            frames[ticker] = df

        return pd.concat(frames, axis=1, keys=frames.keys())


class TestYFinanceBatchFetch:
    """Unit tests for YFinanceDataSource.fetch_batch_ohlcv."""

    @pytest.fixture
    def sample_codes(self):
        """Sample stock codes for testing."""
        from quantflow.data.base import StockCode
        return [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
            StockCode(code="GOOG", exchange="US"),
        ]

    def test_empty_input_returns_empty_dict(self):
        """Batch with no codes should return empty dict."""
        from quantflow.data.adapters.yfinance import YFinanceDataSource
        source = YFinanceDataSource()
        result = source.fetch_batch_ohlcv([], "2025-01-01", "2025-12-31")
        assert result == {}

    @patch("quantflow.data.adapters.yfinance.yf")
    def test_batch_returns_correct_shape(self, mock_yf, sample_codes):
        """Batch fetch should return dict of DataFrames with correct columns."""
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        mock_multi = MockMultiIndexDataFrame.create_batch({
            "AAPL": [
                {"date": "2025-01-02", "open": 100.0, "high": 105.0,
                 "low": 99.0, "close": 103.0, "volume": 1000000},
            ],
            "MSFT": [
                {"date": "2025-01-02", "open": 200.0, "high": 210.0,
                 "low": 198.0, "close": 205.0, "volume": 2000000},
            ],
        })
        mock_yf.download.return_value = mock_multi
        mock_yf.__version__ = "0.2.40"

        source = YFinanceDataSource()
        result = source.fetch_batch_ohlcv(
            sample_codes, "2025-01-01", "2025-12-31"
        )

        assert "AAPL.US" in result
        assert "MSFT.US" in result
        assert "GOOG.US" not in result  # No data for GOOG

        for key, df in result.items():
            assert "date" in df.columns
            assert "open" in df.columns
            assert pd.api.types.is_datetime64_any_dtype(df["date"])

    @patch("quantflow.data.adapters.yfinance.yf")
    def test_batch_skips_empty_tickers(self, mock_yf, sample_codes):
        """Tickers with no data should be excluded from result."""
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        mock_multi = MockMultiIndexDataFrame.create_batch({
            "AAPL": [
                {"date": "2025-01-02", "open": 100.0, "high": 105.0,
                 "low": 99.0, "close": 103.0, "volume": 1000000},
            ],
        })
        mock_yf.download.return_value = mock_multi
        mock_yf.__version__ = "0.2.40"

        source = YFinanceDataSource()
        result = source.fetch_batch_ohlcv(
            sample_codes, "2025-01-01", "2025-12-31"
        )

        assert len(result) == 1
        assert "AAPL.US" in result

    @patch("quantflow.data.adapters.yfinance.yf")
    def test_batch_handles_download_failure(self, mock_yf, sample_codes):
        """If yf.download raises exception, should return empty dict."""
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        mock_yf.download.side_effect = Exception("Network error")
        mock_yf.__version__ = "0.2.40"

        source = YFinanceDataSource()
        result = source.fetch_batch_ohlcv(
            sample_codes, "2025-01-01", "2025-12-31"
        )

        assert result == {}


class TestExecutordispatch:
    """Unit tests for Executor dispatch logic."""

    def test_yfinance_items_partitioned(self):
        """Executor should partition yFinance vs other items correctly."""
        from quantflow.data.base import StockCode
        from quantflow.data.config import MarketDataSourceConfig

        config = MarketDataSourceConfig()
        items_with_codes = [
            (StockCode(code="AAPL", exchange="US"), "yfinance"),
            (StockCode(code="MSFT", exchange="US"), "yfinance"),
            (StockCode(code="600000", exchange="SH"), "baostock"),
        ]

        yf_items = [ic for ic in items_with_codes if config.get_primary(
            "us" if ic[0].exchange == "US" else "cn"
        ) == "yfinance"]
        other_items = [ic for ic in items_with_codes if config.get_primary(
            "us" if ic[0].exchange == "US" else "cn"
        ) != "yfinance"]

        assert len(yf_items) == 2
        assert len(other_items) == 1

    def test_empty_yfinance_group(self):
        """If no yFinance items, batch path should not be triggered."""
        from quantflow.data.base import StockCode
        from quantflow.data.config import MarketDataSourceConfig

        config = MarketDataSourceConfig()
        cn_codes = [StockCode(code="600000", exchange="SH")]

        for code in cn_codes:
            market = "cn" if code.exchange in ["SH", "SZ"] else "us"
            primary = config.get_primary(market)
            assert primary == "baostock"
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow && pytest tests/data/test_yfinance_batch.py -v
```

Expected: All tests pass.

---

### Task 6: Verify existing tests still pass

**Files:**
- All existing test files

- [ ] **Step 1: Run full test suite (skip integration)**

```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow && pytest tests/ -m "not integration" -v
```

Expected: All pre-existing tests pass (no regressions from our changes).

- [ ] **Step 2: Run lint check**

```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow && ruff check src/quantflow/data/adapters/yfinance.py src/quantflow/data/factory.py src/quantflow/execution/executor.py
```

Expected: Clean output, no errors.

---

### Task 7: Integration verification (optional, requires network)

**Files:**
- None

- [ ] **Step 1: Verify batch fetch works with real data**

Run a quick manual test:
```python
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow
python -c "
from quantflow.data.base import StockCode
from quantflow.data.adapters.yfinance import YFinanceDataSource

codes = [
    StockCode(code='AAPL', exchange='US'),
    StockCode(code='MSFT', exchange='US'),
    StockCode(code='GOOG', exchange='US'),
]
source = YFinanceDataSource()
result = source.fetch_batch_ohlcv(codes, '2026-04-01', '2026-05-01')
print(f'Fetched {len(result)} tickers:')
for key, df in result.items():
    print(f'  {key}: {len(df)} rows, columns={list(df.columns)}')
"
```

Expected:
```
Fetched 3 tickers:
  AAPL.US: ~22 rows, columns=['date', 'open', 'high', 'low', 'close', 'volume']
  MSFT.US: ~22 rows, columns=['date', 'open', 'high', 'low', 'close', 'volume']
  GOOG.US: ~22 rows, columns=['date', 'open', 'high', 'low', 'close', 'volume']
```

---

## Self-Review

### 1. Spec coverage

| Requirement | Task |
|------------|------|
| `fetch_batch_ohlcv` in YFinanceDataSource using `yf.download()` | Task 2 |
| `group_by='ticker'`, `threads=True`, `session` passed | Task 2 |
| Unstack MultiIndex → `Dict[ticker, DataFrame]` | Task 2 |
| Same OHLCV column structure as single fetch | Task 2 (same rename + column selection logic) |
| Exclude empty/failed tickers from result dict | Task 2 (KeyError skip + empty check) |
| Executor dispatch: yFinance → batch, BaoStock → serial | Task 4 |
| `yf.download` handles `len(items) == 1` correctly | Task 4 (batch path works for any N ≥ 1) |
| Version check for yfinance >= 0.2.30 | Task 1 + Task 2 |
| All tests pass, no regressions | Task 5 + Task 6 |

### 2. Placeholder scan

No placeholders found. All code is concrete with actual implementations.

### 3. Type consistency

- `StockCode` is imported consistently from `quantflow.data.base`
- Return types: `Dict[str, pd.DataFrame]` (adapter) → `Dict[str, tuple[pd.DataFrame, str]]` (factory)
- Column names: `date, open, high, low, close, volume` match exactly between single and batch paths
- `symbol_to_code` mapping uses `code_obj.standard` which is `f"{code}.{exchange}"` — matches the key format used in `execute()` via `code.standard`
