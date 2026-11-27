# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import numpy as np
import pandas as pd
import pytest

from coin_buddy.config import StrategyConfig
from coin_buddy.indicators import add_indicators
from coin_buddy.signals import Action, action_series, decide, evaluate, vote_frame

CFG = StrategyConfig()


@pytest.mark.parametrize(
    "buys, sells, expected",
    [
        (2, 0, Action.BUY),
        (0, 2, Action.SELL),
        (2, 2, Action.HOLD),  # ties are HOLD, not BUY (v1 bug)
        (1, 0, Action.HOLD),
        (3, 1, Action.BUY),
        (1, 3, Action.SELL),
        (0, 0, Action.HOLD),
    ],
)
def test_decide(buys, sells, expected):
    assert decide(buys, sells, min_votes=2) == expected


def _row(**overrides):
    base = {"close": 100.0, "rsi": 50.0, "macd": 0.0, "macd_signal": 0.0, "bb_upper": 110.0, "bb_lower": 90.0}
    return {**base, **overrides}


def test_oversold_below_band_is_buy():
    sig = evaluate(_row(rsi=20, close=85), sentiment=None, cfg=CFG)
    assert sig.action == Action.BUY and sig.buy_votes == 2


def test_missing_sentiment_abstains():
    sig = evaluate(_row(), sentiment=None, cfg=CFG)
    assert next(v for v in sig.votes if v.name == "Sentiment").value == 0


def test_sentiment_votes():
    assert next(v for v in evaluate(_row(), 0.5, CFG).votes if v.name == "Sentiment").value == 1
    assert next(v for v in evaluate(_row(), -0.5, CFG).votes if v.name == "Sentiment").value == -1


def test_explain_mentions_every_indicator():
    text = evaluate(_row(), 0.1, CFG).explain()
    for name in ("RSI", "MACD", "Bollinger", "Sentiment"):
        assert name in text


def test_vectorised_matches_single_row(ohlcv):
    """The backtest (vectorised) and the live path (single row) must always agree."""
    df = add_indicators(ohlcv)
    rng = np.random.default_rng(1)
    sentiment = pd.Series(rng.uniform(-0.5, 0.5, len(df)), index=df.index)
    actions = action_series(df, CFG, sentiment)
    warm = df.dropna().index
    for ts in warm[::7]:
        assert evaluate(df.loc[ts], sentiment[ts], CFG).action.value == actions[ts], ts


def test_warmup_rows_never_vote(ohlcv):
    votes = vote_frame(add_indicators(ohlcv), CFG)
    assert (votes.iloc[:30] == 0).all().all()
