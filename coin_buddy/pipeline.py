# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""One place that wires data -> indicators -> signals -> storage, shared by the CLI and the dashboard."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from coin_buddy import ml
from coin_buddy.backtest import BacktestResult, actions_to_target, run_backtest
from coin_buddy.config import Config
from coin_buddy.data.market import fetch_candles, fetch_history, make_exchange
from coin_buddy.data.sentiment import Post, SentimentResult, fetch_sentiment
from coin_buddy.indicators import add_indicators
from coin_buddy.signals import Signal, action_series, evaluate
from coin_buddy.storage import Store

log = logging.getLogger(__name__)


@dataclass
class Snapshot:
    taken_at: datetime
    candles: pd.DataFrame  # OHLCV + indicators
    sentiment: SentimentResult
    posts: list[Post]
    post_scores: list[float]
    signal: Signal
    ml_p_up: float | None

    @property
    def latest(self) -> pd.Series:
        return self.candles.iloc[-1]


SentimentBundle = tuple[SentimentResult, list[Post], list[float]]


def take_snapshot(
    cfg: Config,
    exchange: Any | None = None,
    store: Store | None = None,
    sentiment_data: SentimentBundle | None = None,
) -> Snapshot:
    """Compute the current signal. Pass `sentiment_data` to reuse a cached sentiment fetch."""
    m = cfg.market
    candles = fetch_candles(m.symbol, m.timeframe, m.lookback_candles, exchange=exchange or make_exchange(m.exchange))
    candles = add_indicators(candles, cfg.indicators)
    sentiment, posts, scores = sentiment_data or fetch_sentiment(cfg.sentiment)
    signal = evaluate(candles.iloc[-1], sentiment.score if sentiment.n_posts else None, cfg.strategy)
    market = {"exchange": m.exchange, "symbol": m.symbol, "timeframe": m.timeframe}
    p_up = ml.predict_latest(candles, cfg.model_file(), market)
    snap = Snapshot(datetime.now(timezone.utc), candles, sentiment, posts, scores, signal, p_up)
    if store is not None:
        _persist(snap, cfg, store)
    return snap


def _persist(snap: Snapshot, cfg: Config, store: Store) -> None:
    row = snap.latest
    store.save_snapshot(
        {
            "taken_at": snap.taken_at.isoformat(),
            "exchange": cfg.market.exchange,
            "symbol": cfg.market.symbol,
            "timeframe": cfg.market.timeframe,
            "price": float(row["close"]),
            "rsi": float(row["rsi"]),
            "macd": float(row["macd"]),
            "macd_signal": float(row["macd_signal"]),
            "bb_upper": float(row["bb_upper"]),
            "bb_lower": float(row["bb_lower"]),
            "sentiment": snap.sentiment.score if snap.sentiment.n_posts else None,
            "sentiment_posts": snap.sentiment.n_posts,
            "ml_p_up": snap.ml_p_up,
            "action": snap.signal.action.value,
            "votes": {v.name: v.value for v in snap.signal.votes},
        }
    )
    if snap.posts:
        store.save_posts(snap.posts, snap.post_scores, cfg.sentiment.model)


@dataclass
class BacktestReport:
    candles: pd.DataFrame
    results: dict[str, BacktestResult]
    walk_forward: ml.WalkForwardResult | None


def backtest(
    cfg: Config,
    days: int,
    strategies: tuple[str, ...] = ("rules", "ml"),
    exchange: Any | None = None,
    candles: pd.DataFrame | None = None,
) -> BacktestReport:
    """Backtest the rule engine and/or the walk-forward ML model on real history.

    Sentiment is excluded from rule backtests unless stored history exists, because past Reddit
    data can't be fetched for free. Run `coin-buddy watch` for a while to build that history.
    """
    m = cfg.market
    if candles is None:
        candles = fetch_history(m.symbol, m.timeframe, days, exchange=exchange or make_exchange(m.exchange))
    candles = add_indicators(candles, cfg.indicators)
    results: dict[str, BacktestResult] = {}
    wf = None

    if "rules" in strategies:
        actions = action_series(candles, cfg.strategy)
        results["rules"] = run_backtest(candles, actions_to_target(actions), cfg.backtest)

    if "ml" in strategies:
        wf = ml.walk_forward(candles, cfg.ml, cfg.backtest)
        tested = wf.probabilities.notna()
        if tested.any():
            window = candles[tested]
            actions = ml.probabilities_to_actions(wf.probabilities[tested], cfg.ml.probability_threshold)
            results["ml"] = run_backtest(window, actions_to_target(actions), cfg.backtest)
            # Compare rules on the same out-of-sample window so the comparison is fair.
            if "rules" in results:
                rule_actions = action_series(candles, cfg.strategy)[tested]
                results["rules (ML test window)"] = run_backtest(window, actions_to_target(rule_actions), cfg.backtest)
        else:
            log.warning(
                "Not enough history for walk-forward ML: need > %d candles.",
                cfg.ml.train_candles + cfg.ml.horizon_candles,
            )
    return BacktestReport(candles, results, wf)
