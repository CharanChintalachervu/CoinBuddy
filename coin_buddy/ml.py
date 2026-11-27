# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Machine-learning signal trained on REAL price history, evaluated walk-forward.

Label: does price rise by more than the round-trip trading cost over the next `horizon` candles?
Walk-forward: train on a past window, predict the next unseen window, slide forward, repeat.
A gap of `horizon` candles between train and test prevents labels from leaking future prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from coin_buddy.config import BacktestConfig, MLConfig

FEATURES = ["rsi", "macd_hist_pct", "bb_pct_b", "ret_1", "ret_3", "ret_12", "ret_24", "volatility_24", "volume_z"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Scale-free features known at each candle's close (expects add_indicators() output)."""
    f = pd.DataFrame(index=df.index)
    close = df["close"]
    f["rsi"] = df["rsi"]
    f["macd_hist_pct"] = df["macd_hist"] / close
    f["bb_pct_b"] = df["bb_pct_b"]
    for n in (1, 3, 12, 24):
        f[f"ret_{n}"] = close.pct_change(n)
    f["volatility_24"] = close.pct_change().rolling(24).std()
    vol = df["volume"]
    f["volume_z"] = (vol - vol.rolling(48).mean()) / vol.rolling(48).std()
    return f.replace([np.inf, -np.inf], np.nan)


def build_labels(df: pd.DataFrame, horizon: int, cost: float) -> pd.Series:
    """1 if buying at the next open and selling `horizon` candles later beats round-trip costs.

    The last `horizon + 1` rows have no future data and are left as NaN.
    """
    entry = df["open"].shift(-1)
    exit_ = df["open"].shift(-1 - horizon)
    fwd = exit_ / entry - 1
    label = (fwd > 2 * cost).astype(float)
    return label.where(fwd.notna())


def new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, max_depth=3, l2_regularization=1.0, random_state=42
    )


@dataclass
class WalkForwardResult:
    probabilities: pd.Series  # out-of-sample P(up) for every test candle
    accuracy: float
    baseline_accuracy: float  # always predicting the most common class in each training window
    folds: int


def walk_forward(df: pd.DataFrame, ml: MLConfig, bt: BacktestConfig) -> WalkForwardResult:
    cost = bt.fee_rate + bt.slippage_rate
    X = build_features(df)
    y = build_labels(df, ml.horizon_candles, cost)
    valid = X.notna().all(axis=1) & y.notna()
    X, y = X[valid], y[valid]

    probs = pd.Series(np.nan, index=df.index, name="p_up")
    correct = baseline_correct = total = folds = 0
    gap = ml.horizon_candles + 1
    start = ml.train_candles + gap
    while start < len(X):
        train_X = X.iloc[start - gap - ml.train_candles : start - gap]
        train_y = y.iloc[start - gap - ml.train_candles : start - gap]
        test_X = X.iloc[start : start + ml.test_candles]
        test_y = y.iloc[start : start + ml.test_candles]
        if train_y.nunique() < 2:
            start += ml.test_candles
            continue
        model = new_model().fit(train_X, train_y)
        p = model.predict_proba(test_X)[:, 1]
        probs.loc[test_X.index] = p
        majority = float(train_y.mean() >= 0.5)
        correct += int(((p >= 0.5) == test_y.astype(bool)).sum())
        baseline_correct += int((test_y == majority).sum())
        total += len(test_y)
        folds += 1
        start += ml.test_candles

    return WalkForwardResult(
        probabilities=probs,
        accuracy=correct / total if total else float("nan"),
        baseline_accuracy=baseline_correct / total if total else float("nan"),
        folds=folds,
    )


def probabilities_to_actions(probs: pd.Series, threshold: float) -> pd.Series:
    """Go long when P(up) >= threshold, go flat when P(up) < 1 - threshold, otherwise hold."""
    actions = pd.Series("HOLD", index=probs.index)
    actions[probs >= threshold] = "BUY"
    actions[probs < 1 - threshold] = "SELL"
    return actions


def train_and_save(df: pd.DataFrame, ml: MLConfig, bt: BacktestConfig, path: Path, meta: dict) -> Path:
    """Train on all available history and save the model with its metadata."""
    cost = bt.fee_rate + bt.slippage_rate
    X = build_features(df)
    y = build_labels(df, ml.horizon_candles, cost)
    valid = X.notna().all(axis=1) & y.notna()
    model = new_model().fit(X[valid], y[valid])
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "horizon": ml.horizon_candles, **meta}, path)
    return path


MARKET_KEYS = ("exchange", "symbol", "timeframe")


def predict_latest(df: pd.DataFrame, path: Path, market: dict[str, str] | None = None) -> float | None:
    """P(up) for the latest closed candle.

    Returns None when no model exists, or when `market` (exchange/symbol/timeframe) differs from
    what the model was trained on: features and the horizon are measured in candles of the
    training timeframe, so applying a 1h BTC model to 5m DOGE candles would be meaningless.
    """
    if not path.exists():
        return None
    bundle = joblib.load(path)
    if market and any(k in bundle and bundle[k] != market.get(k) for k in MARKET_KEYS):
        return None
    X = build_features(df)[bundle["features"]].dropna()
    if X.empty:
        return None
    return float(bundle["model"].predict_proba(X.iloc[[-1]])[0, 1])
