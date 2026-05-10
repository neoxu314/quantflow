# YFinance Retry Mechanism Fix Design

**Date:** 2026-05-08
**Priority:** High

## Problem

YFinance rate limit handling broken:
1. **Retry mechanism ineffective**: yfinance.download() doesn't raise exceptions on rate limit, returns empty DataFrame with error logs
2. **Factory initialization error**: run_engine.py stock_scan/watchlist_run creates DataSourceFactory without yfinance_config

## Solution

### Fix 1: Replace Exception-based Retry with Loop-based Success Rate Check

**File**: `src/quantflow/data/adapters/yfinance.py`

**Changes to `_download_chunk` method**:
- Remove exception-catching retry wrapper
- Add loop-based retry with success rate threshold
- Success rate = successful_tickers / requested_tickers
- Retry if success_rate < 0.5 AND attempt < max_attempts
- Sleep before retry: base_delay * 2^(attempt-1)

**Implementation**:
```python
def _download_chunk(...):
    for attempt in range(1, self._retry_max_attempts + 1):
        df_multi = yf.download(...)
        
        if df_multi is None or df_multi.empty:
            logger.warning(f"Empty DataFrame - attempt {attempt}/{max_attempts}")
            if attempt < max_attempts:
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                logger.warning(f"  Retry in {delay:.0f}s...")
                time.sleep(delay)
            continue
        
        # Calculate success rate
        success_count = sum(1 for sym in yf_symbols 
                          if sym in df_multi and not df_multi[sym].empty)
        success_rate = success_count / len(yf_symbols)
        
        if success_rate >= 0.5 or attempt == max_attempts:
            logger.info(f"  Success rate {success_rate:.0%} - accepted")
            break
        else:
            logger.warning(f"  Success rate {success_rate:.0%} < 50% - retrying...")
            if attempt < max_attempts:
                delay = self._retry_base_delay * (2 ** (attempt - 1))
                time.sleep(delay)
    
    # Process results (same as before)
    ...
```

### Fix 2: Pass yfinance_config to DataSourceFactory in run_engine

**File**: `src/quantflow/web/engine/run_engine.py`

**Changes**:
- Import ConfigLoader in run_engine.py
- Load yfinance_config from ConfigLoader
- Pass yfinance_config to DataSourceFactory constructor

**Implementation**:
```python
# Line ~120 (stock_scan)
from quantflow.config.loader import ConfigLoader
config_loader = ConfigLoader()
factory = DataSourceFactory(
    yfinance_config=config_loader.get_yfinance_config()
)

# Line ~288 (watchlist_run/task_run)
# Executor already loads ConfigLoader and passes yfinance_config (no change needed)
```

## Testing

- Manual test: Run task_run via Web UI, observe retry logs
- Expected: "Success rate 0% < 50% - retrying..." + "Retry in 30s..."
- Integration test: Mock yfinance to return empty DataFrame, verify retry triggers

## Files Modified

1. `src/quantflow/data/adapters/yfinance.py` - retry logic
2. `src/quantflow/web/engine/run_engine.py` - factory initialization

## Success Criteria

- Retry logs appear when rate limit hits
- Success rate threshold (50%) prevents partial success over-retry
- Exponential backoff delays visible in logs
- Factory receives retry config from YAML