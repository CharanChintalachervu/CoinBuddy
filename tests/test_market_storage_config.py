# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import pytest

from coin_buddy.config import Config, load_config
from coin_buddy.data.market import fetch_candles
from coin_buddy.storage import Store
from tests.conftest import make_ohlcv


def _now_after(df, hours_into_last_candle: float) -> int:
    return int(df.index[-1].value // 1_000_000 + hours_into_last_candle * 3_600_000)


def test_fetch_candles_paginates(fake_exchange_factory):
    df = make_ohlcv(450)
    ex = fake_exchange_factory(df, now_ms=_now_after(df, 1.0), page=100)
    out = fetch_candles("BTC/USDT", "1h", 300, exchange=ex)
    assert len(out) == 300
    assert ex.calls >= 3
    assert out.index.is_monotonic_increasing


def test_fetch_candles_drops_forming_candle(fake_exchange_factory):
    df = make_ohlcv(200)
    ex = fake_exchange_factory(df, now_ms=_now_after(df, 0.5))  # last candle only half done
    out = fetch_candles("BTC/USDT", "1h", 50, exchange=ex)
    assert out.index[-1] == df.index[-2]


def test_config_rejects_typos(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("market:\n  symbl: ETH/USDT\n", encoding="utf-8")
    with pytest.raises(ValueError, match="symbl"):
        load_config(path)


def test_config_partial_override(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("market:\n  symbol: ETH/USDT\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.market.symbol == "ETH/USDT"
    assert cfg.market.timeframe == Config().market.timeframe


def test_project_config_loads():
    assert load_config().market.symbol


def test_store_roundtrip(tmp_path):
    from coin_buddy.data.sentiment import Post

    store = Store(tmp_path / "db.sqlite")
    store.save_snapshot(
        {
            "taken_at": "2026-01-01T00:00:00+00:00",
            "exchange": "binance",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "price": 1.0,
            "rsi": 50.0,
            "macd": 0.0,
            "macd_signal": 0.0,
            "bb_upper": 2.0,
            "bb_lower": 0.5,
            "sentiment": None,
            "sentiment_posts": 0,
            "ml_p_up": None,
            "action": "HOLD",
            "votes": {"RSI": 0},
        }
    )
    posts = [Post("p1", "bitcoin", 1_700_000_000.0, "t", "", 1)]
    store.save_posts(posts, [0.4], "vader")
    store.save_posts(posts, [0.4], "vader")  # duplicates are ignored
    assert len(store.snapshots()) == 1
    hist = store.sentiment_history()
    assert len(hist) == 1 and hist.iloc[0] == pytest.approx(0.4)


def test_model_file_is_per_market():
    cfg = Config()
    cfg.market.exchange, cfg.market.symbol, cfg.market.timeframe = "kraken", "BTC/USD", "4h"
    assert cfg.model_file().name == "kraken-BTC-USD-4h.joblib"
