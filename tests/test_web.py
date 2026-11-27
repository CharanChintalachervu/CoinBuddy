# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""API tests with a fake exchange and fake sentiment: no network needed."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from coin_buddy.config import Config
from coin_buddy.data.sentiment import Post, SentimentResult
from coin_buddy.web.server import create_app
from tests.conftest import FakeExchange, make_ohlcv


class WebFakeExchange(FakeExchange):
    """Adds the ticker and market methods the web API uses."""

    def load_markets(self):
        return {
            "BTC/USDT": {"spot": True, "active": True},
            "ETH/USDT": {"spot": True, "active": True},
            "BTC/EUR": {"spot": True, "active": True},
            "BTC/USDT:USDT": {"spot": False, "active": True},
        }

    def fetch_tickers(self, symbols):
        last = self.rows[-1][4]
        return {
            s: {"last": last, "percentage": 1.5, "high": last * 1.02, "low": last * 0.98, "quoteVolume": 1e9}
            for s in symbols
        }


@pytest.fixture
def client(tmp_path):
    df = make_ohlcv(1200)
    now = int(df.index[-1].value // 1_000_000 + 30 * 60_000)  # 30 minutes into the last (forming) candle
    exchange = WebFakeExchange(df, now_ms=now, page=1000)
    cfg = Config()
    cfg.storage.database = str(tmp_path / "web.db")
    cfg.ml.model_path = str(tmp_path / "missing.joblib")
    cfg.ml.train_candles, cfg.ml.test_candles = 400, 200
    sentiment = (
        SentimentResult(0.3, 2, 0.5, 0.0),
        [Post("a", "bitcoin", 0.0, "<script>alert(1)</script> moon", "", 3, "https://www.reddit.com/r/bitcoin/a")],
        [0.6],
    )
    app = create_app(cfg, exchange_factory=lambda _id: exchange, sentiment_fetcher=lambda _cfg: sentiment)
    return TestClient(app)


def test_index_and_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200 and "Coin Buddy" in res.text
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/app.js").status_code == 200


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["symbol"] and "1h" in meta["timeframes"] and meta["thresholds"]["sentiment_buy"] == 0.2


def test_markets_are_spot_only_and_usdt_first(client):
    markets = client.get("/api/markets").json()
    assert "BTC/USDT:USDT" not in markets
    assert markets.index("BTC/USDT") < markets.index("BTC/EUR")


def test_candles_include_forming_candle_and_markers(client):
    data = client.get("/api/candles", params={"symbol": "BTC/USDT", "timeframe": "1h", "limit": 300}).json()
    assert data["forming"] is True
    assert len(data["candles"]) == 300
    first = data["candles"][0]
    assert {"time", "open", "close", "rsi", "bb_upper", "macd_hist"} <= set(first)
    times = [c["time"] for c in data["candles"]]
    assert times == sorted(times)
    assert all(m["action"] in ("BUY", "SELL") for m in data["markers"])
    # Markers only on closed candles: never on the forming one.
    assert all(m["time"] < times[-1] for m in data["markers"])


def test_signal_is_explained_and_saved(client):
    data = client.get("/api/signal", params={"symbol": "BTC/USDT", "timeframe": "1h"}).json()
    assert data["action"] in ("BUY", "SELL", "HOLD")
    assert [v["name"] for v in data["votes"]] == ["RSI", "MACD", "Bollinger", "Sentiment"]
    assert data["sentiment"]["available"] and data["sentiment"]["score"] == 0.3
    assert data["ml"] is None
    history = client.get("/api/history").json()
    assert len(history) == 1 and history[0]["action"] == data["action"]


def test_tickers(client):
    rows = client.get("/api/tickers", params={"symbols": "BTC/USDT,ETH/USDT"}).json()
    assert [r["symbol"] for r in rows] == ["BTC/USDT", "ETH/USDT"]
    assert rows[0]["change_pct"] == 1.5


def test_backtest_endpoint(client):
    res = client.post("/api/backtest", json={"symbol": "BTC/USDT", "timeframe": "1h", "days": 45, "strategy": "both"})
    assert res.status_code == 200, res.text
    body = res.json()
    names = [r["name"] for r in body["results"]]
    assert names[0] == "rules" and "ml" in names
    rules = body["results"][0]
    assert rules["equity"] and rules["benchmark"]
    assert set(rules["metrics"]) >= {"total_return", "buy_and_hold_return", "sharpe", "max_drawdown"}


def test_validation_errors(client):
    assert client.get("/api/candles", params={"symbol": "BTC/USDT", "timeframe": "7m"}).status_code == 400
    assert client.post("/api/backtest", json={"symbol": "BTC/USDT", "days": 5}).status_code == 422


def test_json_never_contains_nan(client):
    text = client.get("/api/candles", params={"symbol": "BTC/USDT", "timeframe": "1h", "limit": 100}).text
    assert "NaN" not in text and "Infinity" not in text
    assert pd.notna(1)  # keeps pandas import meaningful for readers: NaN is converted server-side
