from the_similarity_data.fetchers.crypto_ccxt import CryptoCcxtFetcher
from the_similarity_data.fetchers.forex_twelvedata import ForexTwelveDataFetcher
from the_similarity_data.fetchers.stooq_daily import StooqDailyFetcher

try:
    from the_similarity_data.fetchers.market_yfinance import MarketYFinanceFetcher
except ImportError:
    MarketYFinanceFetcher = None  # type: ignore[assignment,misc]

__all__ = [
    "CryptoCcxtFetcher",
    "ForexTwelveDataFetcher",
    "MarketYFinanceFetcher",
    "StooqDailyFetcher",
]
