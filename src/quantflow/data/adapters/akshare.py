"""AKShare data source adapter for sector data and HK stocks.

Classification Types:
- EM (东方财富): 行业板块 + 概念板块 + 成分股API (⚠️ 当前网络不可用)
- THS (同花顺): 行业板块 + 概念板块 (无成分股API)
- SW (申万行业): 一级/二级/三级行业分类 + 成分股API (无概念板块) ✅ 推荐

API Limitations:
- EM: AKShare provides full API, but push2.eastmoney.com has network access restrictions
- THS: Only list APIs available (no constituent APIs in AKShare)
- SW: Only industry classification (no concept boards)

Known Issues:
- EM (东方财富): push2.eastmoney.com 存在地区网络访问限制，当前不可用
- THS (同花顺): AKShare 无成分股API，仅能获取板块列表
- 推荐使用 SW (申万) 进行完整板块数据分析

Usage:
    # 申万三级行业 ✅ 推荐
    source = AKShareDataSource(classification="sw_l3")
    industries = source.get_industry_list()
    stocks = source.get_industry_constituents("857371.SI")  # 锂电池板块
    
    # 同花顺行业 (仅列表，无成分股)
    source = AKShareDataSource(classification="ths")
    industries = source.get_industry_list()
    stocks = source.get_industry_constituents("881121")  # Returns []
    
    # 东方财富 (API存在，但可能因网络问题失败)
    source = AKShareDataSource(classification="em")
    industries = source.get_industry_list()  # 可能失败
"""

import pandas as pd
import logging
from typing import Optional, List
from enum import Enum

from quantflow.data.base import DataSourceBase, SectorDataSource, StockCode
from quantflow.data.quality import normalize_ohlcv

logger = logging.getLogger(__name__)


def _akshare_api(module, current, legacy):
    return getattr(module, current, None) or getattr(module, legacy)


class SectorClassification(Enum):
    """板块分类标准类型"""
    EM = "em"           # 东方财富
    THS = "ths"         # 同花顺
    SW = "sw"           # 申万行业 (默认三级)
    SW_L1 = "sw_l1"     # 申万一级行业
    SW_L2 = "sw_l2"     # 申万二级行业
    SW_L3 = "sw_l3"     # 申万三级行业


class AKShareDataSource(DataSourceBase, SectorDataSource):
    
    def __init__(self, classification: str = "em"):
        """
        Args:
            classification: 分类标准，可选值：
                - "em": 东方财富 (默认)
                - "ths": 同花顺
                - "sw" / "sw_l3": 申万三级行业
                - "sw_l1": 申万一级行业
                - "sw_l2": 申万二级行业
        """
        self.classification = classification
        
    def get_name(self) -> str:
        return f"AKShare-{self.classification.upper()}"
    
    def supports_market(self, market: str) -> bool:
        return market in ["hk", "港股", "sector", "板块"]
    
    def _normalize_classification(self) -> str:
        """Normalize classification string"""
        clf = self.classification.lower()
        if clf == "sw":
            return "sw_l3"
        return clf
    
    def _is_shenwan(self) -> bool:
        """Check if classification is Shenwan"""
        clf = self._normalize_classification()
        return clf.startswith("sw")
    
    def _get_sw_level(self) -> str:
        """Get Shenwan level (l1, l2, l3)"""
        clf = self._normalize_classification()
        if clf == "sw_l1":
            return "l1"
        elif clf == "sw_l2":
            return "l2"
        else:
            return "l3"

    def get_supported_periods(self) -> List[str]:
        return ["d"]
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        import akshare as ak
        
        if code.exchange != "HK":
            raise ValueError(f"AKShare only supports HK stocks, got {code.exchange}")
        
        if period not in self.get_supported_periods():
            raise ValueError(f"AKShare HK does not support period {period}")
        adjust = adjust or "qfq"
        if adjust not in self.get_supported_adjusts():
            raise ValueError(f"AKShare HK does not support adjustment {adjust}")
        fetch = _akshare_api(ak, "stock_hk_hist_sina", "stock_hk_daily")
        df = fetch(symbol=code.code.zfill(5), adjust="" if adjust == "none" else adjust)
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
            "收盘": "close", "成交量": "volume",
        })
        df = normalize_ohlcv(df, start_date, end_date)
        if df.empty:
            return df
        return df[["date", "open", "high", "low", "close", "volume"]]
    
    def get_industry_list(self) -> pd.DataFrame:
        """Get all industries with codes and names.
        
        Returns:
            DataFrame with columns: code, name
        """
        import akshare as ak
        
        clf = self._normalize_classification()
        
        try:
            if clf == "em":
                df = ak.stock_board_industry_name_em()
                return df.rename(columns={"板块名称": "name", "板块代码": "code"})
            
            elif clf == "ths":
                df = ak.stock_board_industry_name_ths()
                return df.rename(columns={"行业名称": "name", "行业代码": "code"})
            
            elif clf == "sw_l1":
                df = _akshare_api(ak, "index_first_info_sw", "sw_index_first_info")()
                return df.rename(columns={"行业名称": "name", "行业代码": "code"})
            
            elif clf == "sw_l2":
                df = _akshare_api(ak, "index_second_info_sw", "sw_index_second_info")()
                return df.rename(columns={"行业名称": "name", "行业代码": "code"})
            
            elif clf == "sw_l3":
                df = _akshare_api(ak, "index_third_info_sw", "sw_index_third_info")()
                return df.rename(columns={"行业名称": "name", "行业代码": "code"})
            
            else:
                logger.warning(f"Unknown classification: {clf}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Failed to get industry list: {e}")
            return pd.DataFrame()
    
    def get_industry_constituents(self, industry_code: str) -> List[StockCode]:
        """Get constituent stocks of an industry.
        
        Args:
            industry_code: Industry identifier (板块代码 or 行业代码)
        
        Returns:
            List of StockCode objects
        """
        import akshare as ak
        
        clf = self._normalize_classification()
        
        try:
            if clf == "em":
                df = ak.stock_board_industry_cons_em(symbol=industry_code)
            
            elif clf == "ths":
                logger.warning("THS classification does not have industry constituent API in AKShare")
                return []
            
            elif clf in ("sw_l1", "sw_l2"):
                df = ak.index_component_sw(symbol=industry_code.removesuffix(".SI"))
            elif clf == "sw_l3":
                df = _akshare_api(
                    ak, "index_third_cons_sw", "sw_index_third_cons"
                )(symbol=industry_code)
            
            else:
                logger.warning(f"Unknown classification: {clf}")
                return []
            
            codes = []
            for _, row in df.iterrows():
                # Handle different column names across sources
                code_str = str(
                    row.get("代码", row.get("证券代码", row.get("code", row.get("股票代码", ""))))
                )
                if "." in code_str:
                    code, exchange = code_str.split(".")
                    codes.append(StockCode(code=code, exchange=exchange))
                elif code_str:
                    if code_str.startswith("6"):
                        codes.append(StockCode(code=code_str, exchange="SH"))
                    elif code_str.startswith("0") or code_str.startswith("3"):
                        codes.append(StockCode(code=code_str, exchange="SZ"))
            
            return codes
            
        except Exception as e:
            logger.error(f"Failed to get industry constituents for {industry_code}: {e}")
            return []
    
    def get_concept_list(self) -> pd.DataFrame:
        """Get all concepts with codes and names.
        
        Note: Shenwan (SW) classification does not have concept boards.
        
        Returns:
            DataFrame with columns: code, name (empty for SW classification)
        """
        import akshare as ak
        
        clf = self._normalize_classification()
        
        if self._is_shenwan():
            logger.warning("Shenwan classification does not have concept boards")
            return pd.DataFrame(columns=["code", "name"])
        
        try:
            if clf == "em":
                df = ak.stock_board_concept_name_em()
                return df.rename(columns={"板块名称": "name", "板块代码": "code"})
            
            elif clf == "ths":
                df = ak.stock_board_concept_name_ths()
                return df.rename(columns={"概念名称": "name", "概念代码": "code"})
            
            else:
                logger.warning(f"Unknown classification: {clf}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Failed to get concept list: {e}")
            return pd.DataFrame()
    
    def get_concept_constituents(self, concept_code: str) -> List[StockCode]:
        """Get constituent stocks of a concept.
        
        Note: Shenwan (SW) classification does not have concept boards.
        
        Args:
            concept_code: Concept identifier
        
        Returns:
            List of StockCode objects (empty for SW classification)
        """
        import akshare as ak
        
        clf = self._normalize_classification()
        
        if self._is_shenwan():
            logger.warning("Shenwan classification does not have concept boards")
            return []
        
        try:
            if clf == "em":
                df = ak.stock_board_concept_cons_em(symbol=concept_code)
            
            elif clf == "ths":
                logger.warning("THS classification does not have concept constituent API in AKShare")
                return []
            
            else:
                logger.warning(f"Unknown classification: {clf}")
                return []
            
            codes = []
            for _, row in df.iterrows():
                code_str = str(row.get("代码", row.get("code", "")))
                if "." in code_str:
                    code, exchange = code_str.split(".")
                    codes.append(StockCode(code=code, exchange=exchange))
                elif code_str:
                    if code_str.startswith("6"):
                        codes.append(StockCode(code=code_str, exchange="SH"))
                    elif code_str.startswith("0") or code_str.startswith("3"):
                        codes.append(StockCode(code=code_str, exchange="SZ"))
            
            return codes
            
        except Exception as e:
            logger.error(f"Failed to get concept constituents for {concept_code}: {e}")
            return []
    
    def get_classification_info(self) -> dict:
        """Get information about current classification.
        
        Returns:
            dict with classification details
        """
        clf = self._normalize_classification()
        
        info = {
            "classification": clf,
            "has_industry": True,
            "has_concept": not self._is_shenwan(),
            "source": {
                "em": "东方财富",
                "ths": "同花顺",
                "sw_l1": "申万一级",
                "sw_l2": "申万二级",
                "sw_l3": "申万三级",
            }.get(clf, "Unknown")
        }
        
        return info
