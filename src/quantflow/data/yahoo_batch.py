"""Run Yahoo SDK calls behind an interruptible, wall-clock deadline.

The SDKs may perform multiple HTTP requests inside one history call. Using a
short-lived spawned process lets cancellation and failover interrupt those calls
without leaving a downloader running against the next run's state.
"""

import logging
import multiprocessing
import random
import time
from dataclasses import dataclass, field

from quantflow.control import check_cancelled

logger = logging.getLogger(__name__)

BATCH_SECONDS = 240
PRIMARY_SECONDS = 160
COOLDOWN_SECONDS = 90
FAILURE_THRESHOLD = 3


@dataclass
class Download:
    frames: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    outage: bool = False


def _fetch_chunk(source, adapter, chunk, args):
    if source == "yahooquery":
        code = chunk[0]
        frame = adapter.fetch_ohlcv(code, *args)
        return {code.standard: frame} if not frame.empty else {}
    return adapter.download_once(chunk, *args)


def _download(sender, source, settings, codes, args, probe):
    from quantflow.data.adapters import YahooQueryDataSource, YFinanceDataSource

    try:
        if source == "yahooquery":
            adapter = YahooQueryDataSource(**settings)
            chunk_size = 1
        else:
            adapter = YFinanceDataSource(**settings)
            chunk_size = adapter._chunk_size
        from quantflow.data import StockCode

        # Distinguish an upstream outage from several delisted/illiquid symbols.
        reference = {"US": "SPY", "HK": "00700", "T": "7203", "KS": "005930"}

        misses = offset = 0
        while offset < len(codes):
            size = min(chunk_size, FAILURE_THRESHOLD) if probe and not offset else chunk_size
            chunk = codes[offset : offset + size]
            errors = {}
            try:
                frames = _fetch_chunk(source, adapter, chunk, args)
            except Exception as exc:
                frames = {}
                errors = {c.standard: f"{type(exc).__name__}: {exc}" for c in chunk}
            for code in chunk:
                if code.standard not in frames:
                    errors.setdefault(code.standard, "Provider returned no usable quotes")
            misses = 0 if frames else misses + len(chunk)
            offset += len(chunk)
            outage = False
            if misses >= FAILURE_THRESHOLD:
                market = chunk[-1].exchange
                control = StockCode(reference[market], market)
                try:
                    outage = not _fetch_chunk(source, adapter, [control], args)
                except Exception:
                    outage = True
                misses = 0
            sender.send((frames, errors, offset, chunk[-1].standard, outage))
            if outage or offset == len(codes):
                break
            time.sleep(random.uniform(adapter._sleep_min, adapter._sleep_max))
    finally:
        sender.close()


def download(
    source, settings, codes, args, deadline, progress=None, *, probe=False, worker=_download
):
    result = Download()
    reason = "Network unavailable; pending symbols can be retried with Resume"
    if time.monotonic() < deadline:
        ctx = multiprocessing.get_context("spawn")
        reader, writer = ctx.Pipe(duplex=False)
        process = ctx.Process(target=worker, args=(writer, source, settings, codes, args, probe))
        try:
            process.start()
            writer.close()
            while True:
                check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "Provider deadline reached; retry pending symbols with Resume"
                    result.outage = not result.frames
                    break
                if not reader.poll(min(0.1, remaining)):
                    continue
                try:
                    frames, errors, offset, last, outage = reader.recv()
                except EOFError:
                    result.outage = True
                    break
                result.frames.update(frames)
                result.errors.update(errors)
                logger.info(
                    "%s [%d/%d] %s: %d received, %d unresolved",
                    source,
                    offset,
                    len(codes),
                    last,
                    len(frames),
                    len(errors),
                )
                for code, error in errors.items():
                    logger.warning("%s %s: %s", source, code, error)
                if progress:
                    progress(offset, len(codes), last)
                result.outage = outage
                if outage or offset == len(codes):
                    break
        finally:
            writer.close()
            reader.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()
    else:
        reason = "Batch deadline reached; retry pending symbols with Resume"
    for code in codes:
        if code.standard not in result.frames:
            result.errors.setdefault(code.standard, reason)
    return result
