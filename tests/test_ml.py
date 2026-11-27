# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import numpy as np

from coin_buddy import ml
from coin_buddy.config import BacktestConfig, MLConfig
from coin_buddy.indicators import add_indicators
from tests.conftest import make_ohlcv


def test_labels_leave_future_unknown():
    df = make_ohlcv(100)
    labels = ml.build_labels(df, horizon=5, cost=0.001)
    assert labels.iloc[-6:].isna().all()
    assert labels.iloc[:-6].notna().all()


def test_label_definition():
    df = make_ohlcv(50)
    labels = ml.build_labels(df, horizon=3, cost=0.0)
    i = 10
    fwd = df["open"].iloc[i + 4] / df["open"].iloc[i + 1] - 1
    assert labels.iloc[i] == float(fwd > 0)


def test_features_have_no_lookahead():
    """Changing a future candle must not change any feature at an earlier time."""
    df = add_indicators(make_ohlcv(300))
    altered = df.copy()
    altered.iloc[-1, altered.columns.get_loc("close")] *= 2
    altered = add_indicators(altered[["open", "high", "low", "close", "volume"]])
    a, b = ml.build_features(df).iloc[:-1], ml.build_features(altered).iloc[:-1]
    np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), equal_nan=True)


def test_walk_forward_only_predicts_out_of_sample():
    df = add_indicators(make_ohlcv(900))
    cfg = MLConfig(horizon_candles=4, train_candles=400, test_candles=100)
    res = ml.walk_forward(df, cfg, BacktestConfig())
    predicted = res.probabilities.dropna()
    assert res.folds >= 3
    first_valid = ml.build_features(df).dropna().index[0]
    first_pred_pos = df.index.get_loc(predicted.index[0]) - df.index.get_loc(first_valid)
    assert first_pred_pos >= cfg.train_candles + cfg.horizon_candles
    assert predicted.between(0, 1).all()


def test_train_save_predict_roundtrip(tmp_path):
    df = add_indicators(make_ohlcv(600))
    path = ml.train_and_save(df, MLConfig(horizon_candles=4), BacktestConfig(), tmp_path / "m.joblib", {})
    p = ml.predict_latest(df, path)
    assert p is not None and 0 <= p <= 1


def test_model_only_predicts_for_its_own_market(tmp_path):
    df = add_indicators(make_ohlcv(600))
    meta = {"exchange": "binance", "symbol": "BTC/USDT", "timeframe": "1h"}
    path = ml.train_and_save(df, MLConfig(horizon_candles=4), BacktestConfig(), tmp_path / "m.joblib", meta)
    assert ml.predict_latest(df, path, meta) is not None
    assert ml.predict_latest(df, path, {**meta, "timeframe": "5m"}) is None
    assert ml.predict_latest(df, path, {**meta, "symbol": "DOGE/USDT"}) is None


def test_predict_without_model_returns_none(tmp_path):
    assert ml.predict_latest(add_indicators(make_ohlcv(200)), tmp_path / "missing.joblib") is None
