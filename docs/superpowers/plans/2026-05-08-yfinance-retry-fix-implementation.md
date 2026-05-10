# YFinance Retry Mechanism Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix yfinance retry mechanism to handle rate limits by checking success rate instead of catching exceptions, and fix DataSourceFactory initialization in run_engine.

**Architecture:** Replace exception-based retry with loop-based success rate check (50% threshold), fix factory initialization to pass yfinance_config from ConfigLoader.

**Tech Stack:** Python 3.9+, yfinance 1.2.0, pandas, exponential backoff retry

---

## Problem Analysis

**Current Issue:**
- yfinance.download() doesn't raise exceptions on rate limit - returns empty DataFrame with error logs
- Current retry mechanism (exception-based) never triggers
- DataSourceFactory in run_engine.py stock_scan/watchlist_run created without yfinance_config

**Root Cause:**
```python
# yfinance behavior on rate limit:
ERROR:yfinance: Failed downloads: YFRateLimitError(...)
Returned DataFrame: empty (0 rows)
No exception raised!  # Retry wrapper cannot catch
```

---

## File Structure

**Modify:**
- `src/quantflow/data/adapters/yfinance.py:165-240` - Replace retry logic with success rate check
- `src/quantflow/web/engine/run_engine.py:120-148` - Fix DataSourceFactory initialization

**Test:**
- `tests/data/test_yfinance_batch.py` - Add success rate retry tests

**Docs:**
- `docs/superpowers/specs/2026-05-08-yfinance-retry-fix-design.md` (spec already written)

---

## Implementation Tasks

### Task 1: Replace _download_chunk retry logic with success rate check

**Files:**
- Modify: `src/quantflow/data/adapters/yfinance.py:165-240`

**Goal:** Replace exception-based retry with loop-based success rate check

- [ ] **Step 1: Read current _download_chunk implementation**

Read file to understand existing structure:
- Lines 165-240 contain _download_chunk method
- Current retry uses `_retry_with_backoff` exception wrapper
- Need to replace with loop-based approach

- [ ] **Step 2: Replace retry wrapper with loop-based implementation**

Replace `_download_chunk` method (lines 165-240):

```python
def _download_chunk(
    self, yf_symbols: List[str], start_date: str, end_date: str, interval: str
) -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    
    max_attempts = self._retry_max_attempts
    base_delay = self._retry_base_delay
    
    df_multi = None
    for attempt in range(1, max_attempts + 1):
        logger.info(f"  Download attempt {attempt}/{max_attempts}: {len(yf_symbols)} tickers")
        
        df_multi = yf.download(
            tickers=yf_symbols,
            start=start_date,
            end=end_date,
            interval=interval,
            group_by="ticker",
            threads=True,
            session=self._session,
            progress=False,
            timeout=30,
        )
        
        if df_multi is None or df_multi.empty:
            logger.warning(f"  Empty DataFrame returned")
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(f"  Retry in {delay:.0f}s...")
                time.sleep(delay)
            continue
        
        success_count = sum(
            1 for sym in yf_symbols 
            if sym in df_multi.columns.levels[0] if hasattr(df_multi.columns, 'levels') else sym in df_multi 
            and not df_multi[sym].empty
        )
        success_rate = success_count / len(yf_symbols)
        
        if success_rate >= 0.5:
            logger.info(f"  Success rate {success_rate:.0%} >= 50% - accepted")
            break
        elif attempt == max_attempts:
            logger.warning(f"  Success rate {success_rate:.0%} < 50% but max attempts reached")
            break
        else:
            logger.warning(f"  Success rate {success_rate:.0%} < 50% - retrying...")
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(f"  Retry in {delay:.0f}s...")
            time.sleep(delay)
    
    if df_multi is None or df_multi.empty:
        logger.warning(
            f"Chunk returned empty data after {max_attempts} attempts "
            f"(symbols: {', '.join(yf_symbols[:5])}...)"
        )
        return {}
    
    chunk_results: Dict[str, pd.DataFrame] = {}
    failed_symbols: List[str] = []
    
    for yf_sym in yf_symbols:
        try:
            raw = df_multi[yf_sym]
        except KeyError:
            failed_symbols.append(yf_sym)
            logger.warning(f"  Symbol not in response: {yf_sym}")
            continue
            
        if raw is None or raw.empty:
            failed_symbols.append(yf_sym)
            logger.warning(f"  Empty data for: {yf_sym}")
            continue
            
        single = _unstack_ticker(raw, self._COL_MAP)
        if single.empty:
            failed_symbols.append(yf_sym)
            logger.warning(f"  Parse failed for: {yf_sym}")
            continue
            
        chunk_results[yf_sym] = single
        logger.info(f"  ✓ {yf_sym}: {len(single)} rows")
    
    if failed_symbols:
        logger.warning(
            f"  Failed symbols in chunk ({len(failed_symbols)}/{len(yf_symbols)}): "
            f"{', '.join(failed_symbols[:10])}"
        )
    
    return chunk_results
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/data/test_yfinance_batch.py -v`
Expected: All tests pass (retry mechanism tests should still work)

- [ ] **Step 4: Manual test retry behavior**

Run small batch to observe retry logs:
```bash
python3 -c "
from quantflow.data.adapters.yfinance import YFinanceDataSource
from quantflow.data.base import StockCode
adapter = YFinanceDataSource(chunk_size=10, retry_max_attempts=2, retry_base_delay=5)
codes = [StockCode.from_standard('AAPL.US')]
results = adapter.fetch_batch_ohlcv(codes, '2026-05-01', '2026-05-08')
print(f'Results: {len(results)}')
" 2>&1 | grep -E "Download attempt|Success rate|Retry"
```

Expected: Retry logs show attempt count and success rate

---

### Task 2: Fix DataSourceFactory initialization in run_engine.py stock_scan

**Files:**
- Modify: `src/quantflow/web/engine/run_engine.py:120-148`

**Goal:** Pass yfinance_config from ConfigLoader to DataSourceFactory

- [ ] **Step 1: Read current run_engine stock_scan implementation**

Read lines 120-148 to understand current DataSourceFactory creation:
- Line 147: `factory = DataSourceFactory()` - missing yfinance_config
- Need to import ConfigLoader and pass config

- [ ] **Step 2: Add ConfigLoader import and pass yfinance_config**

Modify lines 120-148:

```python
# Line 120 (add import at top of _exec_stock_scan)
from quantflow.config.loader import ConfigLoader

# Line 147 (replace factory creation)
config_loader = ConfigLoader()
factory = DataSourceFactory(
    yfinance_config=config_loader.get_yfinance_config()
)
```

- [ ] **Step 3: Test stock_scan via Web UI**

Run stock_scan from Web UI, observe retry params applied:
- Check logs for chunk_size=35 (from config)
- Check retry_max_attempts=3, retry_base_delay=30

Run: Start Web UI and execute stock_scan via `/api/runs`

Expected: Config params from quantflow.yaml used

---

### Task 3: Add test for success rate retry mechanism

**Files:**
- Modify: `tests/data/test_yfinance_batch.py`

**Goal:** Verify success rate check triggers retry correctly

- [ ] **Step 1: Add success rate retry test**

Add new test function:

```python
def test_retry_on_low_success_rate():
    """Test retry triggers when success rate < 50%"""
    from unittest.mock import patch, MagicMock
    import pandas as pd
    
    adapter = YFinanceDataSource(
        chunk_size=5,
        retry_max_attempts=3,
        retry_base_delay=5,
    )
    
    call_count = 0
    def mock_download(**kwargs):
        global call_count
        call_count += 1
        
        if call_count == 1:
            # First call: 2/5 success (40% < 50%)
            df = pd.DataFrame({
                'AAPL': pd.DataFrame({'Close': [100, 101]}),
                'MSFT': pd.DataFrame({'Close': [200, 201]}),
            })
            return df
        else:
            # Second call: all success
            df = pd.DataFrame({
                'AAPL': pd.DataFrame({'Close': [100, 101]}),
                'MSFT': pd.DataFrame({'Close': [200, 201]}),
                'GOOGL': pd.DataFrame({'Close': [150, 151]}),
                'AMZN': pd.DataFrame({'Close': [180, 181]}),
                'NVDA': pd.DataFrame({'Close': [220, 221]}),
            })
            return df
    
    with patch('yfinance.download', side_effect=mock_download):
        with patch('time.sleep'):  # Skip actual sleep
            results = adapter.fetch_batch_ohlcv(
                [StockCode.from_standard('AAPL.US') for _ in range(5)],
                '2026-05-01',
                '2026-05-08',
            )
    
    assert call_count >= 2  # Should retry on low success rate
```

- [ ] **Step 2: Run new test**

Run: `pytest tests/data/test_yfinance_batch.py::test_retry_on_low_success_rate -v`
Expected: Test passes (retry triggered on low success rate)

---

### Task 4: Verify retry logs appear in real scenario

**Files:**
- None (manual verification)

**Goal:** Confirm retry mechanism works in real rate limit scenario

- [ ] **Step 1: Run task_run via Web UI**

Execute task_run with large batch (e.g., sp500 with 503 items):
- Observe logs for retry attempts
- Check success rate messages

- [ ] **Step 2: Verify retry behavior**

Expected log patterns:
```
INFO:  Download attempt 1/3: 35 tickers
WARNING:  Success rate 0% < 50% - retrying...
WARNING:  Retry in 30s...
INFO:  Download attempt 2/3: 35 tickers
INFO:  Success rate 100% >= 50% - accepted
```

If retry logs appear, retry mechanism working correctly.

---

### Task 5: Commit changes

**Files:**
- All modified files

**Goal:** Create atomic commits for retry fix

- [ ] **Step 1: Commit yfinance retry fix**

```bash
git add src/quantflow/data/adapters/yfinance.py tests/data/test_yfinance_batch.py
git commit -m "fix(yfinance): replace exception-based retry with success rate check

- yfinance.download() doesn't raise exceptions on rate limit
- Returns empty DataFrame with error logs instead
- New approach: check success rate >= 50%, retry if below threshold
- Loop-based retry with exponential backoff (30s, 60s)
- Fix DataSourceFactory initialization in run_engine.py

Fixes: Rate limit retry never triggered
Tests: test_retry_on_low_success_rate verifies retry behavior"
```

- [ ] **Step 2: Verify commit**

Run: `git log -1 --stat`
Expected: Shows modified files and commit message

---

## Self-Review Checklist

✓ **Spec coverage:**
- Fix 1 (success rate retry): Task 1 ✓
- Fix 2 (factory initialization): Task 2 ✓
- Testing: Task 3 ✓
- Verification: Task 4 ✓
- Commits: Task 5 ✓

✓ **Placeholder scan:** No TBD, TODO found

✓ **Type consistency:**
- `_download_chunk` returns Dict[str, pd.DataFrame] ✓
- DataSourceFactory signature matches ✓
- Success rate calculation uses same formula ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-yfinance-retry-fix-implementation.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**