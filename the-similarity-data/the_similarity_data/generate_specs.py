"""Programmatic dataset spec generator.

Generates the full datasets.json config from curated symbol universes.
Run directly to regenerate:
    python -m the_similarity_data.generate_specs > config/datasets.json

Design principles:
  - Each asset class has a curated symbol universe (top by market cap / volume)
  - Each symbol gets multiple timeframes based on source capabilities
  - Lookback days scale with timeframe (1m=21d, 15m=120d, 1h=730d, 4h+=3650d)
  - Sources chosen for reliability: CCXT for crypto, Stooq for US equities,
    Twelve Data for forex/commodities, yfinance as fallback
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Timeframe → lookback mapping
# ---------------------------------------------------------------------------
LOOKBACK = {
    "1m": 21,
    "5m": 60,
    "15m": 120,
    "1h": 730,
    "4h": 3650,
    "1d": 3650,
}

# ---------------------------------------------------------------------------
# Crypto — Top 50 by market cap, via CCXT (Binance)
# ---------------------------------------------------------------------------
CRYPTO_SYMBOLS = [
    ("btc_usdt", "BTC/USDT"),
    ("eth_usdt", "ETH/USDT"),
    ("bnb_usdt", "BNB/USDT"),
    ("sol_usdt", "SOL/USDT"),
    ("xrp_usdt", "XRP/USDT"),
    ("ada_usdt", "ADA/USDT"),
    ("doge_usdt", "DOGE/USDT"),
    ("avax_usdt", "AVAX/USDT"),
    ("dot_usdt", "DOT/USDT"),
    ("link_usdt", "LINK/USDT"),
    ("matic_usdt", "MATIC/USDT"),
    ("uni_usdt", "UNI/USDT"),
    ("shib_usdt", "SHIB/USDT"),
    ("ltc_usdt", "LTC/USDT"),
    ("atom_usdt", "ATOM/USDT"),
    ("xlm_usdt", "XLM/USDT"),
    ("etc_usdt", "ETC/USDT"),
    ("near_usdt", "NEAR/USDT"),
    ("apt_usdt", "APT/USDT"),
    ("fil_usdt", "FIL/USDT"),
    ("arb_usdt", "ARB/USDT"),
    ("op_usdt", "OP/USDT"),
    ("sui_usdt", "SUI/USDT"),
    ("sei_usdt", "SEI/USDT"),
    ("inj_usdt", "INJ/USDT"),
    ("imx_usdt", "IMX/USDT"),
    ("vet_usdt", "VET/USDT"),
    ("algo_usdt", "ALGO/USDT"),
    ("ftm_usdt", "FTM/USDT"),
    ("aave_usdt", "AAVE/USDT"),
    ("mkr_usdt", "MKR/USDT"),
    ("grt_usdt", "GRT/USDT"),
    ("snx_usdt", "SNX/USDT"),
    ("crv_usdt", "CRV/USDT"),
    ("ldo_usdt", "LDO/USDT"),
    ("rune_usdt", "RUNE/USDT"),
    ("sand_usdt", "SAND/USDT"),
    ("mana_usdt", "MANA/USDT"),
    ("axs_usdt", "AXS/USDT"),
    ("enj_usdt", "ENJ/USDT"),
    ("1inch_usdt", "1INCH/USDT"),
    ("comp_usdt", "COMP/USDT"),
    ("sushi_usdt", "SUSHI/USDT"),
    ("yfi_usdt", "YFI/USDT"),
    ("bal_usdt", "BAL/USDT"),
    ("zrx_usdt", "ZRX/USDT"),
    ("bat_usdt", "BAT/USDT"),
    ("ens_usdt", "ENS/USDT"),
    ("ren_usdt", "REN/USDT"),
    ("perp_usdt", "PERP/USDT"),
]

CRYPTO_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# ---------------------------------------------------------------------------
# US Stocks — S&P 100 + major ETFs, via Stooq (daily only)
# ---------------------------------------------------------------------------
STOCK_SYMBOLS_STOOQ = [
    # Mega-cap tech
    "aapl", "msft", "amzn", "goog", "googl", "meta", "nvda", "tsla",
    # Semiconductors
    "avgo", "amd", "intc", "qcom", "txn", "mu", "mrvl", "on", "nxpi", "klac",
    "lrcx", "amat", "asml",
    # Software & cloud
    "crm", "adbe", "orcl", "now", "snow", "pltr", "panw", "ftnt", "zs",
    "crwd", "ddog", "net", "mdb",
    # Consumer & retail
    "wmt", "cost", "hd", "tgt", "low", "amzn", "sbux", "mcd", "nke", "lulu",
    # Finance
    "jpm", "bac", "wfc", "gs", "ms", "schw", "bx", "kkr", "c", "usb",
    "axp", "v", "ma", "pypl", "sq",
    # Healthcare & biotech
    "unh", "jnj", "pfe", "mrk", "abbv", "lly", "tmo", "dhr", "bmy", "amgn",
    "gild", "isrg", "vrtx", "regn", "mrna",
    # Energy
    "xom", "cvx", "cop", "slb", "eog", "psx", "vlo", "mpc", "oxy", "dvn",
    # Industrial
    "cat", "de", "hon", "ge", "mmm", "ba", "rtx", "lmt", "noc", "gd",
    # Telecom & media
    "dis", "cmcsa", "nflx", "t", "vz", "tmus",
    # Real estate
    "amt", "pld", "eqr", "avb", "o",
    # ETFs
    "spy", "qqq", "dia", "iwm", "vti", "voo", "arkk", "xlf", "xlk", "xle",
    "xli", "xlv", "xlc", "xly", "xlp", "xlu", "xlb", "tlt", "hyg", "lqd",
    "gld", "slv", "uso", "ung", "eem", "efa", "vwo", "vea", "agg", "bnd",
    "smh", "soxx", "kweb", "fxi",
]

# Deduplicate
STOCK_SYMBOLS_STOOQ = list(dict.fromkeys(STOCK_SYMBOLS_STOOQ))

# ---------------------------------------------------------------------------
# Forex — Major, minor, and exotic pairs, via Twelve Data
# ---------------------------------------------------------------------------
FOREX_SYMBOLS = [
    # Majors
    ("eurusd", "EUR/USD"), ("gbpusd", "GBP/USD"), ("usdjpy", "USD/JPY"),
    ("usdchf", "USD/CHF"), ("audusd", "AUD/USD"), ("usdcad", "USD/CAD"),
    ("nzdusd", "NZD/USD"),
    # Crosses
    ("eurgbp", "EUR/GBP"), ("eurjpy", "EUR/JPY"), ("eurchf", "EUR/CHF"),
    ("euraud", "EUR/AUD"), ("eurcad", "EUR/CAD"), ("eurnzd", "EUR/NZD"),
    ("gbpjpy", "GBP/JPY"), ("gbpchf", "GBP/CHF"), ("gbpaud", "GBP/AUD"),
    ("gbpcad", "GBP/CAD"), ("gbpnzd", "GBP/NZD"),
    ("audjpy", "AUD/JPY"), ("audchf", "AUD/CHF"), ("audcad", "AUD/CAD"),
    ("audnzd", "AUD/NZD"),
    ("nzdjpy", "NZD/JPY"), ("nzdcad", "NZD/CAD"), ("nzdchf", "NZD/CHF"),
    ("cadjpy", "CAD/JPY"), ("cadchf", "CAD/CHF"), ("chfjpy", "CHF/JPY"),
    # Exotics
    ("usdtry", "USD/TRY"), ("usdmxn", "USD/MXN"), ("usdzar", "USD/ZAR"),
    ("usdsgd", "USD/SGD"), ("usdhkd", "USD/HKD"), ("usdnok", "USD/NOK"),
    ("usdsek", "USD/SEK"), ("usddkk", "USD/DKK"), ("usdpln", "USD/PLN"),
    ("usdczk", "USD/CZK"), ("usdhuf", "USD/HUF"),
]

FOREX_TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# ---------------------------------------------------------------------------
# Commodities — via Twelve Data (intraday) + Stooq (daily ETFs)
# ---------------------------------------------------------------------------
COMMODITIES_TWELVEDATA = [
    ("gold", "XAU/USD"),
    ("silver", "XAG/USD"),
    ("oil_wti", "CL"),
    ("oil_brent", "BZ"),
    ("natural_gas", "NG"),
    ("copper", "HG"),
    ("platinum", "PL"),
    ("palladium", "PA"),
    ("wheat", "ZW"),
    ("corn", "ZC"),
    ("soybean", "ZS"),
    ("cotton", "CT"),
    ("sugar", "SB"),
    ("coffee", "KC"),
]

COMMODITIES_TWELVEDATA_TIMEFRAMES = ["1h", "4h", "1d"]

# ---------------------------------------------------------------------------
# Indices — via Twelve Data
# ---------------------------------------------------------------------------
INDEX_SYMBOLS = [
    ("sp500", "SPX"),
    ("nasdaq", "IXIC"),
    ("dowjones", "DJI"),
    ("russell2000", "RUT"),
    ("vix", "VIX"),
    ("ftse100", "UKX"),
    ("dax", "DAX"),
    ("nikkei225", "NI225"),
    ("hang_seng", "HSI"),
    ("shanghai", "SSEC"),
    ("kospi", "KS11"),
    ("asx200", "AXJO"),
    ("cac40", "FCHI"),
    ("stoxx50", "STOXX50E"),
]

INDEX_TIMEFRAMES = ["1h", "4h", "1d"]

# ---------------------------------------------------------------------------
# Bonds & Rates — via Twelve Data
# ---------------------------------------------------------------------------
RATES_SYMBOLS = [
    ("us_10y", "US10Y"),
    ("us_2y", "US02Y"),
    ("us_30y", "US30Y"),
    ("us_5y", "US05Y"),
    ("de_10y", "DE10Y"),
    ("uk_10y", "GB10Y"),
    ("jp_10y", "JP10Y"),
]

RATES_TIMEFRAMES = ["1d"]


def _generate_crypto_specs() -> list[dict]:
    specs = []
    for symbol, source_symbol in CRYPTO_SYMBOLS:
        for tf in CRYPTO_TIMEFRAMES:
            specs.append({
                "asset_class": "crypto",
                "symbol": symbol,
                "timeframe": tf,
                "source": "ccxt",
                "source_symbol": source_symbol,
                "exchange": "binanceus",
                "lookback_days": LOOKBACK[tf],
                "enabled": True,
            })
    return specs


def _generate_stock_specs() -> list[dict]:
    specs = []
    for symbol in STOCK_SYMBOLS_STOOQ:
        specs.append({
            "asset_class": "stocks",
            "symbol": symbol,
            "timeframe": "1d",
            "source": "stooq",
            "source_symbol": f"{symbol}.us",
            "lookback_days": 3650,
            "enabled": True,
        })
    return specs


def _generate_forex_specs() -> list[dict]:
    specs = []
    for symbol, source_symbol in FOREX_SYMBOLS:
        for tf in FOREX_TIMEFRAMES:
            specs.append({
                "asset_class": "forex",
                "symbol": symbol,
                "timeframe": tf,
                "source": "twelvedata",
                "source_symbol": source_symbol,
                "lookback_days": LOOKBACK[tf],
                "enabled": True,
            })
    return specs


def _generate_commodity_specs() -> list[dict]:
    specs = []
    for symbol, source_symbol in COMMODITIES_TWELVEDATA:
        for tf in COMMODITIES_TWELVEDATA_TIMEFRAMES:
            specs.append({
                "asset_class": "commodities",
                "symbol": symbol,
                "timeframe": tf,
                "source": "twelvedata",
                "source_symbol": source_symbol,
                "lookback_days": LOOKBACK[tf],
                "enabled": True,
            })
    return specs


def _generate_index_specs() -> list[dict]:
    specs = []
    for symbol, source_symbol in INDEX_SYMBOLS:
        for tf in INDEX_TIMEFRAMES:
            specs.append({
                "asset_class": "indices",
                "symbol": symbol,
                "timeframe": tf,
                "source": "twelvedata",
                "source_symbol": source_symbol,
                "lookback_days": LOOKBACK[tf],
                "enabled": True,
            })
    return specs


def _generate_rates_specs() -> list[dict]:
    specs = []
    for symbol, source_symbol in RATES_SYMBOLS:
        for tf in RATES_TIMEFRAMES:
            specs.append({
                "asset_class": "rates",
                "symbol": symbol,
                "timeframe": tf,
                "source": "twelvedata",
                "source_symbol": source_symbol,
                "lookback_days": LOOKBACK[tf],
                "enabled": True,
            })
    return specs


def generate_all_specs() -> list[dict]:
    """Generate the full dataset specification universe."""
    specs = []
    specs.extend(_generate_crypto_specs())
    specs.extend(_generate_stock_specs())
    specs.extend(_generate_forex_specs())
    specs.extend(_generate_commodity_specs())
    specs.extend(_generate_index_specs())
    specs.extend(_generate_rates_specs())
    return specs


def summary(specs: list[dict]) -> dict:
    """Return coverage summary stats."""
    by_class: dict[str, int] = {}
    by_source: dict[str, int] = {}
    symbols: set[str] = set()
    for spec in specs:
        by_class[spec["asset_class"]] = by_class.get(spec["asset_class"], 0) + 1
        by_source[spec["source"]] = by_source.get(spec["source"], 0) + 1
        symbols.add(f"{spec['asset_class']}/{spec['symbol']}")
    return {
        "total_specs": len(specs),
        "unique_symbols": len(symbols),
        "by_asset_class": by_class,
        "by_source": by_source,
    }


if __name__ == "__main__":
    all_specs = generate_all_specs()
    print(json.dumps(all_specs, indent=2))
    import sys
    stats = summary(all_specs)
    print(f"\n--- Coverage Summary ---", file=sys.stderr)
    print(f"Total specs: {stats['total_specs']}", file=sys.stderr)
    print(f"Unique symbols: {stats['unique_symbols']}", file=sys.stderr)
    for cls, count in sorted(stats["by_asset_class"].items()):
        print(f"  {cls}: {count} specs", file=sys.stderr)
    for src, count in sorted(stats["by_source"].items()):
        print(f"  {src}: {count} specs", file=sys.stderr)
