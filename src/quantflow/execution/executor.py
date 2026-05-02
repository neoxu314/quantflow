"""Stock Executor for processing execution jobs."""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from quantflow.config.loader import ConfigLoader
from quantflow.data import DataSourceFactory, StockCode
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.standard import KDJIndicator, MACDIndicator
from quantflow.indicators.custom import DualLineIndicator
from quantflow.execution.storage import Storage, ExecutionResultItem
from .job import ExecutionJob

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self):
        config = ConfigLoader()
        self.factory = DataSourceFactory(
            tushare_token=config.get_tushare_token(),
            yfinance_config=config.get_yfinance_config(),
        )
        self.storage = Storage()
        self.composer = IndicatorComposer([
            KDJIndicator(),
            MACDIndicator(),
            DualLineIndicator()
        ])

    def _process_single(
        self, item, code: StockCode, df: pd.DataFrame, job
    ) -> Optional[ExecutionResultItem]:
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

    def execute(self, job: ExecutionJob) -> List[ExecutionResultItem]:
        total = len(job.items)
        logger.info(f"Starting execution: {job.name} ({total} items)")
        results = []
        start_date = (datetime.now() - timedelta(days=job.days_back)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

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

        for item, code in yfinance_items:
            df = yf_data.get(code.standard)
            if df is None or df.empty:
                logger.warning(f"No data for {item.code}")
                continue
            result = self._process_single(item, code, df, job)
            if result:
                results.append(result)

        for idx, (item, code) in enumerate(other_items, 1):
            try:
                logger.info(f"Processing [{idx}/{total}]: {item.code}")
                df, _ = self.factory.fetch_ohlcv(
                    code, start_date=start_date, end_date=end_date
                )
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