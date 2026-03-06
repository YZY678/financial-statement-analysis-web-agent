"""
历史财务/行情数据获取，用于绘图与对比。
"""
from typing import Any, Dict, List, Optional

try:
    import yfinance as yf
except ImportError:
    yf = None


def fetch_historical_data(
    ticker: str,
    period: str = "2y",
    interval: str = "1mo",
) -> Dict[str, Any]:
    """
    获取历史数据，用于趋势图。
    ticker: 股票代码，如 AAPL, MSFT；若为 UNKNOWN 或无效则返回空结构。
    """
    if not yf:
        return _empty_history()
    ticker = (ticker or "").strip().upper()
    if not ticker or ticker == "UNKNOWN":
        return _empty_history()
    try:
        obj = yf.Ticker(ticker)
        hist = obj.history(period=period, interval=interval)
        if hist is None or hist.empty:
            return _empty_history()
        return {
            "ticker": ticker,
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "close": hist["Close"].fillna(0).tolist(),
            "volume": hist["Volume"].fillna(0).tolist(),
        }
    except Exception:
        return _empty_history()


def _empty_history() -> Dict[str, Any]:
    return {
        "ticker": "",
        "dates": [],
        "close": [],
        "volume": [],
    }
