# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import pandas as pd
import pytest

from coin_buddy.backtest import actions_to_target, run_backtest
from coin_buddy.config import BacktestConfig

NO_COSTS = BacktestConfig(fee_rate=0.0, slippage_rate=0.0)


def test_always_long_without_costs_tracks_the_asset(ohlcv):
    # The first signal exists only at candle 0's close, so the position starts at candle 1's open.
    res = run_backtest(ohlcv, pd.Series(1.0, index=ohlcv.index), NO_COSTS)
    expected = ohlcv["open"].iloc[-1] / ohlcv["open"].iloc[1] - 1
    assert res.metrics["total_return"] == pytest.approx(expected, rel=1e-9)


def test_never_in_market_returns_zero(ohlcv):
    res = run_backtest(ohlcv, pd.Series(0.0, index=ohlcv.index))
    assert res.metrics["total_return"] == 0
    assert res.metrics["round_trips"] == 0


def test_costs_are_charged_per_side(ohlcv):
    cfg = BacktestConfig(fee_rate=0.001, slippage_rate=0.0)
    target = pd.Series(1.0, index=ohlcv.index)
    with_cost = run_backtest(ohlcv, target, cfg).metrics["total_return"]
    no_cost = run_backtest(ohlcv, target, NO_COSTS).metrics["total_return"]
    # One entry, no exit within the data: exactly one side of fees.
    assert (1 + with_cost) == pytest.approx((1 + no_cost) * (1 - 0.001))


def test_no_lookahead_signal_fills_next_open(ohlcv):
    target = pd.Series(0.0, index=ohlcv.index)
    target.iloc[10:] = 1.0  # decided at the close of candle 10
    res = run_backtest(ohlcv, target, NO_COSTS)
    assert res.position.iloc[10] == 0  # not yet holding during candle 10
    assert res.position.iloc[11] == 1  # filled at candle 11's open
    assert res.trades.iloc[0]["entry_price"] == ohlcv["open"].iloc[11]


def test_actions_to_target_holds_previous_state():
    actions = pd.Series(["HOLD", "BUY", "HOLD", "SELL", "HOLD"])
    assert actions_to_target(actions).tolist() == [0, 1, 1, 0, 0]


def test_round_trip_accounting(ohlcv):
    target = pd.Series(0.0, index=ohlcv.index)
    target.iloc[5:20] = 1.0
    target.iloc[40:60] = 1.0
    res = run_backtest(ohlcv, target, NO_COSTS)
    assert len(res.trades) == 2
    t = res.trades.iloc[0]
    assert t["gross_return"] == pytest.approx(ohlcv["open"].iloc[21] / ohlcv["open"].iloc[6] - 1)
