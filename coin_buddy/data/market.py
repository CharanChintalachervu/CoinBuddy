# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Market data via ccxt: public candles from 100+ exchanges, no API keys required."""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def make_exchange(exchange_id: str) -> Any:
    """Create a ccxt exchange client with built-in rate limiting."""
    import ccxt  # imported lazily so tests and offline tools don't need it loaded

    if exchange_id not in ccxt.exchanges:
        raise ValueError(f"Unknown exchange '{exchange_id}'. See ccxt.exchanges for valid ids.")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    # Coin Buddy only uses spot markets. Skipping futures/options makes market loading much faster
    # on exchanges that support the option (e.g. Binance: ~5s -> ~3s).
    fetch_markets = exchange.options.get("fetchMarkets")
    if isinstance(fetch_markets, dict) and "types" in fetch_markets:
        fetch_markets["types"] = ["spot"]
    return exchange


def candles_to_frame(raw: list[list[float]]) -> pd.DataFrame:
    """Convert ccxt OHLCV rows into a DataFrame indexed by UTC timestamp."""
    df = pd.DataFrame(raw, columns=["timestamp", *OHLCV_COLUMNS])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df.astype(float)


def fetch_candles(
    symbol: str,
    timeframe: str,
    limit: int,
    exchange: Any | None = None,
    exchange_id: str = "binance",
    closed_only: bool = True,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Fetch the most recent `limit` candles, paging backwards past the exchange's per-request cap.

    `closed_only` drops the still-forming current candle so indicators never use partial data.
    """
    exchange = exchange or make_exchange(exchange_id)
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    want = limit + (1 if closed_only else 0)
    since = exchange.milliseconds() - want * tf_ms
    rows: list[list[float]] = []

    while len(rows) < want:
        batch = _with_retries(lambda s=since: exchange.fetch_ohlcv(symbol, timeframe, since=s, limit=1000), max_retries)
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + tf_ms
        if since > exchange.milliseconds():
            break

    df = candles_to_frame(rows)
    if closed_only and len(df):
        now = pd.Timestamp(exchange.milliseconds(), unit="ms", tz="UTC")
        df = df[df.index + pd.Timedelta(milliseconds=tf_ms) <= now]
    log.info("Fetched %d %s candles for %s", len(df), timeframe, symbol)
    return df.tail(limit)


def fetch_history(
    symbol: str, timeframe: str, days: int, exchange: Any | None = None, exchange_id: str = "binance"
) -> pd.DataFrame:
    """Fetch `days` of closed candles for backtesting."""
    exchange = exchange or make_exchange(exchange_id)
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    candles = int(days * 86_400_000 / tf_ms)
    return fetch_candles(symbol, timeframe, candles, exchange=exchange)


def _with_retries(call: Any, max_retries: int) -> Any:
    """Retry transient network errors with exponential backoff."""
    import ccxt

    for attempt in range(max_retries):
        try:
            return call()
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2**attempt
            log.warning("Network error (%s); retrying in %ss", exc, wait)
            time.sleep(wait)
    return None
