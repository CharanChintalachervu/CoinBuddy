# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n: int = 600, seed: int = 7, drift: float = 0.0, start: float = 30_000.0) -> pd.DataFrame:
    """Synthetic hourly candles from a geometric random walk."""
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    open_ = np.concatenate([[start], close[:-1]])
    spread = np.abs(rng.normal(0, 0.004, n)) * close
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=idx,
    )


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return make_ohlcv()


class FakeExchange:
    """Mimics the ccxt methods Coin Buddy uses, serving candles from a frame in pages of `page` rows."""

    def __init__(self, df: pd.DataFrame, now_ms: int, page: int = 100):
        self.rows = [[int(t.value // 1_000_000), *r] for t, r in zip(df.index, df.to_numpy().tolist(), strict=True)]
        self.now = now_ms
        self.page = page
        self.calls = 0

    def parse_timeframe(self, tf: str) -> int:
        return {"1m": 60, "1h": 3600}[tf]

    def milliseconds(self) -> int:
        return self.now

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        self.calls += 1
        rows = [r for r in self.rows if since is None or r[0] >= since]
        return rows[: min(limit, self.page)]


@pytest.fixture
def fake_exchange_factory():
    return FakeExchange
