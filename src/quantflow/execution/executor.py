"""Stock Executor for processing execution jobs."""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List

from quantflow.data import DataSourceFactory, StockCode
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.standard import KDJIndicator, MACDIndicator
from quantflow.indicators.custom import DualLineIndicator
from quantflow.execution.storage import Storage, ExecutionResultItem
from .job import ExecutionJob

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self):
        self.factory = DataSourceFactory()
        self.storage = Storage()
        self.composer = IndicatorComposer([
            KDJIndicator(),
            MACDIndicator(),
            DualLineIndicator()
        ])

    def execute(self, job: ExecutionJob) -> List[ExecutionResultItem]:
        total = len(job.items)
        logger.info(f"Starting execution: {job.name} ({total} items)")
        results = []
        start_date = (datetime.now() - timedelta(days=job.days_back)).strftime("%Y-%m-%d")

        for idx, item in enumerate(job.items, 1):
            try:
                logger.info(f"Processing [{idx}/{total}]: {item.code}")
                code = item.code
                if isinstance(code, str):
                    code = StockCode.from_standard(code)
                
                end_date = datetime.now().strftime("%Y-%m-%d")
                df, _ = self.factory.fetch_ohlcv(code, start_date=start_date, end_date=end_date)
                if df.empty:
                    logger.warning(f"No data for {item.code}")
                    continue

                df = self.composer.compose(df)

                buy_signals = 0
                sell_signals = 0
                signal_reasons = []
                matched_buy_strategies = []
                matched_sell_strategies = []

                for strategy in job.strategies:
                    df = strategy.generate_signals(df)
                    
                    # Check latest trading day only
                    latest_day = df.iloc[-1]
                    s_name = strategy.name

                    # Buy Signal Check
                    if latest_day.get('buy_signal', False):
                        buy_signals += 1
                        reason = latest_day.get('signal_reason', 'Triggered')
                        if pd.notna(reason) and str(reason):
                            signal_reasons.append(str(reason))
                        matched_buy_strategies.append(s_name)

                    # Sell Signal Check
                    if latest_day.get('sell_signal', False):
                        sell_signals += 1
                        reason = latest_day.get('signal_reason', 'Triggered')
                        if pd.notna(reason) and str(reason):
                            signal_reasons.append(str(reason))
                        matched_sell_strategies.append(s_name)
                
                # 只有当天触发信号才记录结果
                if buy_signals > 0 or sell_signals > 0:
                    results.append(ExecutionResultItem(
                        code=item.code.standard if hasattr(item.code, 'standard') else item.code,
                        name=getattr(item, 'name', ''),
                        buy_signals=buy_signals,
                        sell_signals=sell_signals,
                        reasons=signal_reasons[:5],
                        matched_buy_strategies=matched_buy_strategies,
                        matched_sell_strategies=matched_sell_strategies
                    ))

            except Exception as e:
                logger.error(f"Failed {item.code}: {e}")

        # Save results
        path = f"{job.output_dir}/{job.name}.json"
        if results:
            self.storage.save_results(path, results)
            logger.info(f"Saved results to {path}")
            
        return results