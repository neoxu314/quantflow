# YFinance Retry & Rate Limit Optimization Implementation Plan

> **历史资料。** 以下内容保留文件名所示日期的方案和假设。当前入口、路径与约束见 [项目文档](../../../README.md) 和 [运行契约](../../reliability-and-data-contracts.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize yfinance batch fetching to handle Yahoo API rate limits with retry mechanism, enhanced logging, and conservative batch settings to minimize failures.

**Architecture:** Add retry logic to `_download_chunk` with exponential backoff for RateLimitError, enhance error classification logging, adjust config defaults for conservative batch sizes and longer sleep intervals, add OpenSSL/LibreSSL detection warnings.

**Tech Stack:** Python 3.9+, yfinance 1.2.0, curl_cffi 0.13.0, pandas, retry logic with exponential backoff

---

## Problem Analysis

Based on task run execution logs (run_id: d10d669c-74b6-4b7f-95ab-a671269f603c), 5 error types observed:

| Error Type | Count | Root Cause | Fix |
|------------|-------|------------|-----|
| `YFRateLimitError` | ~15 times | Yahoo API 60/min, 360/hr, 8000/day limits | Retry with backoff + longer sleep |
| `TypeError: 'NoneType' object is not subscriptable` | ~160 ticker | API returned None (rate limit hit) | Retry mechanism + better logging |
| `TypeError: 'Response' object is not subscriptable` | ~7 ticker | curl_cffi + LibreSSL compatibility | Add OpenSSL detection warning |
| `OperationalError: unable to open database file` | ~15 ticker + API | SQLite cache dir missing | ✓ Already fixed (created dir) |
| `DNSError` | 2 ticker | Network DNS resolution failure | Network issue, retry may help |

---

## File Structure

**Modify:**
- `config/quantflow.yaml` - Adjust batch config defaults
- `src/quantflow/data/adapters/yfinance.py` - Add retry mechanism + enhanced logging + OpenSSL detection
- `src/quantflow/data/factory.py` - Pass retry config to adapter

**Test:**
- `tests/data/test_yfinance_batch.py` - Add retry mechanism tests

**Docs:**
- `docs/superpowers/plans/2026-05-07-yfinance-retry-optimization.md` (this file)

---

## Implementation Tasks

### Task 1: Update yfinance batch configuration defaults

**Files:**
- Modify: `config/quantflow.yaml:29-32`

**Goal:** Conservative batch settings to reduce rate limit triggers

- [ ] **Step 1: Update config values**

```yaml
yfinance:
  batch:
    chunk_size: 35        # 50 → 35 (reduce concurrent requests)
    sleep_min: 10         # 5 → 10 (double minimum sleep)
    sleep_max: 20         # 12 → 20 (increase max sleep for backoff)
    retry_max_attempts: 3 # NEW: retry up to 3 times for RateLimitError
    retry_base_delay: 30  # NEW: base delay 30s, exponential backoff
```

- [ ] **Step 2: Verify config loads correctly**

Run: `python3 -c "from quantflow.config.loader import ConfigLoader; cfg = ConfigLoader.load(); print(cfg.get('yfinance'))"`
Expected: Output shows new values including retry settings

---

### Task 2: Add retry configuration parameters to YFinanceDataSource

**Files:**
- Modify: `src/quantflow/data/adapters/yfinance.py:65-75`

**Goal:** Accept retry config parameters from factory

- [ ] **Step 1: Update __init__ signature**

```python
def __init__(
    self,
    chunk_size: Optional[int] = None,
    sleep_min: Optional[float] = None,
    sleep_max: Optional[float] = None,
    retry_max_attempts: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
):
    if YFinanceDataSource._session is None:
        YFinanceDataSource._session = _get_chrome_session()
    self._chunk_size = chunk_size or 50
    self._sleep_min = sleep_min if sleep_min is not None else 5
    self._sleep_max = sleep_max if sleep_max is not not None else 12
    self._retry_max_attempts = retry_max_attempts if retry_max_attempts is not None else 3
    self._retry_base_delay = retry_base_delay if retry_base_delay is not None else 30
```

- [ ] **Step 2: Run tests to verify signature change**

Run: `pytest tests/data/test_yfinance_batch.py -v -k "test_init"`
Expected: Tests pass (init tests may not exist yet, check test file)

---

### Task 3: Implement retry mechanism in _download_chunk

**Files:**
- Modify: `src/quantflow/data/adapters/yfinance.py:134-170`

**Goal:** Retry on YFRateLimitError with exponential backoff

- [ ] **Step 1: Add helper method for retry with backoff**

Add new method after `_jitter_sleep()` (around line 176):

```python
def _retry_with_backoff(
    self, 
    func, 
    max_attempts: int,
    base_delay: float,
    error_types: List[type],
    *args, 
    **kwargs
) -> tuple:
    """
    Retry function with exponential backoff for specific error types.
    
    Returns: (result, attempts_used, last_error)
    """
    import yfinance as yf
    
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            return (result, attempt, None)
        except Exception as e:
            last_error = e
            # Check if error matches retryable types
            is_retryable = any(
                isinstance(e, etype) or 
                (etype.__name__ in str(e))  # String match for yfinance custom errors
                for etype in error_types
            )
            
            if not is_retryable or attempt == max_attempts:
                break
            
            # Exponential backoff: base_delay * 2^(attempt-1)
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"  Retry attempt {attempt}/{max_attempts} after {delay:.0f}s "
                f"(error: {type(e).__name__}: {e})"
            )
            time.sleep(delay)
    
    return (None, max_attempts, last_error)
```

- [ ] **Step 2: Refactor _download_chunk to use retry**

Replace `_download_chunk` method (lines 134-170):

```python
def _download_chunk(
    self, yf_symbols: List[str], start_date: str, end_date: str, interval: str
) -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    
    # Define retryable error types
    retryable_errors = [
        Exception,  # Broad catch for yfinance custom errors
    ]
    
    # First attempt with retry logic
    def _do_download():
        return yf.download(
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
    
    df_multi, attempts, last_error = self._retry_with_backoff(
        _do_download,
        self._retry_max_attempts,
        self._retry_base_delay,
        retryable_errors,
    )
    
    if last_error and attempts > 1:
        logger.error(
            f"Chunk download failed after {attempts} retries: "
            f"{type(last_error).__name__}: {last_error}"
        )
    
    if df_multi is None or df_multi.empty:
        logger.warning(
            f"Chunk returned empty data (symbols: {', '.join(yf_symbols[:5])}...)"
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

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `pytest tests/data/test_yfinance_batch.py -v`
Expected: All tests pass

---

### Task 4: Add OpenSSL/LibreSSL detection warning

**Files:**
- Modify: `src/quantflow/data/adapters/yfinance.py:26-33`

**Goal:** Detect LibreSSL issue and log warning on initialization

- [ ] **Step 1: Add OpenSSL detection helper**

Insert before `_get_chrome_session()` (around line 26):

```python
def _check_ssl_compatibility() -> Optional[str]:
    """
    Check SSL library compatibility with urllib3 v2.
    
    Returns: Warning message if incompatible, None if OK
    """
    import ssl
    import warnings
    
    # Check if LibreSSL (incompatible with urllib3 v2)
    ssl_version = ssl.OPENSSL_VERSION
    if 'LibreSSL' in ssl_version:
        return (
            f"SSL compatibility issue detected: {ssl_version}. "
            f"urllib3 v2 requires OpenSSL 1.1.1+. "
            f"This may cause 'Response object is not subscriptable' errors. "
            f"Solution: brew install openssl && export PATH=\"/opt/homebrew/opt/openssl/bin:$PATH\""
        )
    return None
```

- [ ] **Step 2: Log warning in __init__**

Modify `__init__` to check SSL compatibility (around line 71):

```python
def __init__(
    self,
    chunk_size: Optional[int] = None,
    sleep_min: Optional[float] = None,
    sleep_max: Optional[float] = None,
    retry_max_attempts: Optional[int] = None,
    retry_base_delay: Optional[float] = None,
):
    if YFinanceDataSource._session is None:
        YFinanceDataSource._session = _get_chrome_session()
        
    # Check SSL compatibility on first init
    ssl_warning = _check_ssl_compatibility()
    if ssl_warning and not hasattr(YFinanceDataSource, '_ssl_warning_logged'):
        logger.warning(ssl_warning)
        YFinanceDataSource._ssl_warning_logged = True
    
    self._chunk_size = chunk_size or 50
    self._sleep_min = sleep_min if sleep_min is not None else 5
    self._sleep_max = sleep_max if sleep_max is not not None else 12
    self._retry_max_attempts = retry_max_attempts if retry_max_attempts is not None else 3
    self._retry_base_delay = retry_base_delay if retry_base_delay is not None else 30
```

- [ ] **Step 3: Test SSL detection**

Run: `python3 -c "from quantflow.data.adapters.yfinance import YFinanceDataSource; YFinanceDataSource()"`
Expected: Warning logged if LibreSSL detected

---

### Task 5: Update DataSourceFactory to pass retry config

**Files:**
- Modify: `src/quantflow/data/factory.py` (locate yfinance instantiation)

**Goal:** Pass retry config from YAML to adapter

- [ ] **Step 1: Find yfinance instantiation in factory**

Run: `grep -n "YFinanceDataSource" src/quantflow/data/factory.py`
Expected: Find instantiation code

- [ ] **Step 2: Update factory to pass retry params**

(Exact code depends on factory structure - read file first)

```python
# In factory's get_yfinance_source() or similar method
yf_config = config.get('yfinance', {}).get('batch', {})
return YFinanceDataSource(
    chunk_size=yf_config.get('chunk_size'),
    sleep_min=yf_config.get('sleep_min'),
    sleep_max=yf_config.get('sleep_max'),
    retry_max_attempts=yf_config.get('retry_max_attempts', 3),
    retry_base_delay=yf_config.get('retry_base_delay', 30),
)
```

- [ ] **Step 3: Test factory integration**

Run: `pytest tests/data/test_factory.py -v -k "yfinance"`
Expected: Tests pass

---

### Task 6: Add test for retry mechanism

**Files:**
- Modify: `tests/data/test_yfinance_batch.py`

**Goal:** Verify retry logic works correctly

- [ ] **Step 1: Add retry mechanism test**

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from quantflow.data.adapters.yfinance import YFinanceDataSource

def test_retry_with_backoff_success_after_retry():
    """Test retry mechanism succeeds on second attempt"""
    adapter = YFinanceDataSource(
        chunk_size=5,
        retry_max_attempts=3,
        retry_base_delay=30,
    )
    
    # Mock function that fails first, succeeds second
    call_count = 0
    def flaky_func():
        call_count += 1
        if call_count == 1:
            raise Exception("YFRateLimitError: Rate limited")
        return "success"
    
    with patch('time.sleep'):  # Skip actual sleep
        result, attempts, error = adapter._retry_with_backoff(
            flaky_func,
            max_attempts=3,
            base_delay=30,
            error_types=[Exception],
        )
    
    assert result == "success"
    assert attempts == 2
    assert error is None

def test_retry_with_backoff_exhausted():
    """Test retry mechanism exhausts attempts and returns error"""
    adapter = YFinanceDataSource(retry_max_attempts=3)
    
    def always_fail():
        raise Exception("YFRateLimitError: Rate limited")
    
    with patch('time.sleep'):
        result, attempts, error = adapter._retry_with_backoff(
            always_fail,
            max_attempts=3,
            base_delay=30,
            error_types=[Exception],
        )
    
    assert result is None
    assert attempts == 3
    assert "RateLimitError" in str(error)

def test_retry_exponential_backoff_timing():
    """Test exponential backoff delays: 30, 60, 120 seconds"""
    adapter = YFinanceDataSource()
    
    sleep_times = []
    def record_sleep(duration):
        sleep_times.append(duration)
    
    def always_fail():
        raise Exception("Rate limited")
    
    with patch('time.sleep', side_effect=record_sleep):
        adapter._retry_with_backoff(
            always_fail,
            max_attempts=3,
            base_delay=30,
            error_types=[Exception],
        )
    
    # Expected: 30, 60, 120 (base * 2^0, base * 2^1, base * 2^2)
    assert sleep_times == [30, 60, 120]
```

- [ ] **Step 2: Run new tests**

Run: `pytest tests/data/test_yfinance_batch.py -v -k "retry"`
Expected: All 3 new tests pass

---

### Task 7: Integration test with real API (optional)

**Files:**
- Modify: `tests/data/test_yfinance_batch.py` (add integration test marker)

**Goal:** Verify retry works against real Yahoo API

- [ ] **Step 1: Add integration test**

```python
@pytest.mark.integration
def test_batch_fetch_with_retry_handles_rate_limit():
    """Integration test: Verify retry handles actual rate limits"""
    from quantflow.data.base import StockCode
    
    adapter = YFinanceDataSource(
        chunk_size=5,
        sleep_min=10,
        sleep_max=20,
        retry_max_attempts=3,
        retry_base_delay=30,
    )
    
    # Small batch to minimize rate limit trigger
    codes = [StockCode.from_standard("AAPL.US"), StockCode.from_standard("MSFT.US")]
    
    results = adapter.fetch_batch_ohlcv(
        codes=codes,
        start_date="2026-04-01",
        end_date="2026-04-30",
        period="d",
    )
    
    # Should succeed even if rate limited
    assert len(results) >= 1
    assert "AAPL.US" in results or "MSFT.US" in results
    assert len(results["AAPL.US"]) > 0 if "AAPL.US" in results else True
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/data/test_yfinance_batch.py -v -m integration -k "retry"`
Expected: Test passes (may take time due to retry delays)

---

### Task 8: Update documentation

**Files:**
- Modify: `src/quantflow/data/AGENTS.md`
- Modify: `src/quantflow/data/adapters/AGENTS.md`

**Goal:** Document retry mechanism and config parameters

- [ ] **Step 1: Update AGENTS.md in data layer**

Add to `YFINANCE SPECIAL` section in `src/quantflow/data/AGENTS.md`:

```markdown
## YFINANCE SPECIAL

- Rate limits: 60/min, 360/hr, 8000/day. **Batch fetch auto-chunks to 35/ticker** (down from 50) with jittered sleep 10-20s to avoid 429.
- `YFinanceDataSource.__init__(chunk_size, sleep_min, sleep_max, retry_max_attempts, retry_base_delay)` — values passed from `DataSourceFactory` via `yfinance_config`.
- **Retry mechanism**: On YFRateLimitError, retries up to `retry_max_attempts` (default 3) with exponential backoff: `base_delay * 2^(attempt-1)` (30s, 60s, 120s).
- **Enhanced logging**: Per-symbol success/failure logging, SSL compatibility warnings for LibreSSL users.
- **SSL compatibility**: LibreSSL 2.8.3 incompatible with urllib3 v2. Solution: `brew install openssl && export PATH="/opt/homebrew/opt/openssl/bin:$PATH"`
- `fetch_batch_ohlcv(codes, ...)` uses `yf.download(tickers, group_by='ticker', threads=True, timeout=30)` with retry wrapper.
```

- [ ] **Step 2: Update AGENTS.md in adapters**

Add to `YFINANCE SPECIAL` section in `src/quantflow/data/adapters/AGENTS.md`:

```markdown
## YFINANCE SPECIAL

- **Retry mechanism**: `_retry_with_backoff()` handles YFRateLimitError with exponential backoff (30s, 60s, 120s for 3 attempts)
- **Config parameters**: `retry_max_attempts` (default 3), `retry_base_delay` (default 30s)
- **SSL detection**: `_check_ssl_compatibility()` logs warning for LibreSSL users
- **Enhanced logging**: Detailed per-symbol failure logging with error classification
```

- [ ] **Step 3: Update config/quantflow.yaml documentation**

Ensure comments explain new parameters (optional, as YAML doesn't support comments in some parsers)

---

### Task 9: Full test suite verification

**Goal:** Verify all tests pass after changes

- [ ] **Step 1: Run full data layer tests**

Run: `pytest tests/data/ -v`
Expected: All tests pass (151 unit tests)

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/data/ -v -m integration`
Expected: Integration tests pass (may be slow due to retry delays)

- [ ] **Step 3: Run linting**

Run: `ruff check src/quantflow/data/`
Expected: No linting errors

---

### Task 10: Commit changes

**Goal:** Create atomic commits for each logical change

- [ ] **Step 1: Commit config changes**

```bash
git add config/quantflow.yaml
git commit -m "config: adjust yfinance batch settings for rate limit optimization

- chunk_size: 50 → 35 (reduce concurrent requests)
- sleep_min: 5 → 10, sleep_max: 12 → 20 (longer intervals)
- add retry_max_attempts: 3, retry_base_delay: 30s
- conservative defaults to minimize Yahoo API rate limits"
```

- [ ] **Step 2: Commit retry mechanism**

```bash
git add src/quantflow/data/adapters/yfinance.py
git commit -m "feat(yfinance): add retry mechanism with exponential backoff

- _retry_with_backoff() handles YFRateLimitError with exponential delay
- Enhanced logging: per-symbol success/failure, error classification
- SSL compatibility detection for LibreSSL users
- Config parameters: retry_max_attempts, retry_base_delay"
```

- [ ] **Step 3: Commit factory integration**

```bash
git add src/quantflow/data/factory.py
git commit -m "feat(factory): pass retry config to YFinanceDataSource

- Extract retry_max_attempts and retry_base_delay from config
- Forward to adapter for retry mechanism activation"
```

- [ ] **Step 4: Commit tests**

```bash
git add tests/data/test_yfinance_batch.py
git commit -m "test(yfinance): add retry mechanism unit tests

- test_retry_with_backoff_success_after_retry
- test_retry_with_backoff_exhausted
- test_retry_exponential_backoff_timing
- integration test for real API retry handling"
```

- [ ] **Step 5: Commit documentation**

```bash
git add src/quantflow/data/AGENTS.md src/quantflow/data/adapters/AGENTS.md
git commit -m "docs: update yfinance retry mechanism documentation

- Document retry config parameters
- Add exponential backoff timing details
- Explain SSL compatibility detection
- Update rate limit handling strategy"
```

---

## OpenSSL Environment Fix (User Action Required)

**Problem:** LibreSSL 2.8.3 incompatible with urllib3 v2 + curl_cffi

**Detection:** Code will log warning on first YFinanceDataSource init

**Solution (user must execute manually):**

```bash
# Install OpenSSL via Homebrew
brew install openssl@3

# Set PATH priority for OpenSSL
export PATH="/opt/homebrew/opt/openssl@3/bin:$PATH"

# Reinstall Python packages with OpenSSL
python3 -m pip install --upgrade --force-reinstall urllib3 curl_cffi

# Verify OpenSSL version
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
# Expected: OpenSSL 3.x.x (not LibreSSL)
```

**Alternative:** Downgrade urllib3 to v1.x (loses HTTP/2 support, may work):

```bash
python3 -m pip install 'urllib3<2.0'
```

---

## Self-Review Checklist

✓ **Spec coverage:**
- Config optimization: Task 1 ✓
- Retry mechanism: Tasks 2-3 ✓
- OpenSSL detection: Task 4 ✓
- Factory integration: Task 5 ✓
- Tests: Task 6-7 ✓
- Documentation: Task 8 ✓
- Verification: Task 9 ✓
- Commits: Task 10 ✓

✓ **Placeholder scan:** No TBD, TODO, "implement later" found

✓ **Type consistency:**
- `_retry_with_backoff` returns `(result, attempts, error)` tuple ✓
- `__init__` signature matches factory call ✓
- All parameter names consistent across tasks ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-07-yfinance-retry-optimization.md`.**

**Two execution options:**

1. **Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**