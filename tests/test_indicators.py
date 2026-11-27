# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import numpy as np
import pandas as pd
import pytest

from coin_buddy.indicators import add_indicators, bollinger, macd, rsi


def test_rsi_is_bounded(ohlcv):
    values = rsi(ohlcv["close"]).dropna()
    assert values.between(0, 100).all()


def test_rsi_extremes():
    rising = pd.Series(np.arange(1.0, 50.0))
    flat = pd.Series(np.full(50, 10.0))
    assert rsi(rising).iloc[-1] == 100
    assert rsi(flat).iloc[-1] == 50


def test_rsi_warmup_is_nan(ohlcv):
    assert rsi(ohlcv["close"], 14).iloc[:14].isna().all()


def test_macd_histogram_is_line_minus_signal(ohlcv):
    line, signal, hist = macd(ohlcv["close"])
    pd.testing.assert_series_equal(hist, line - signal)


def test_bollinger_is_symmetric_around_mid(ohlcv):
    upper, mid, lower = bollinger(ohlcv["close"])
    np.testing.assert_allclose((upper - mid).dropna(), (mid - lower).dropna())


def test_add_indicators_does_not_mutate_input(ohlcv):
    before = ohlcv.copy()
    out = add_indicators(ohlcv)
    pd.testing.assert_frame_equal(ohlcv, before)
    assert {"rsi", "macd", "macd_signal", "macd_hist", "bb_upper", "bb_lower", "bb_pct_b"} <= set(out.columns)


def test_matches_reference_ta_library(ohlcv):
    """Cross-check against the open-source `ta` library (used in v1) when it's installed."""
    ta = pytest.importorskip("ta")
    close = ohlcv["close"]
    ours = add_indicators(ohlcv)
    # `ta` seeds RSI with a fake 0 for the first (undefined) price change, so early values differ
    # slightly. Wilder smoothing forgets the seed exponentially, so the two must converge.
    np.testing.assert_allclose(ours["rsi"].iloc[300:], ta.momentum.RSIIndicator(close).rsi().iloc[300:], rtol=1e-6)
    ref = ta.trend.MACD(close)
    np.testing.assert_allclose(ours["macd"].iloc[50:], ref.macd().iloc[50:], rtol=1e-6)
    np.testing.assert_allclose(ours["macd_signal"].iloc[50:], ref.macd_signal().iloc[50:], rtol=1e-6)
    bb = ta.volatility.BollingerBands(close)
    np.testing.assert_allclose(ours["bb_upper"].iloc[50:], bb.bollinger_hband().iloc[50:], rtol=1e-6)
