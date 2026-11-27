# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Rule-based signal engine: each indicator votes BUY (+1), SELL (-1) or abstains (0).

The same logic runs on a single snapshot (live use) and on a whole DataFrame (backtests),
and the tests check that the two always agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from coin_buddy.config import StrategyConfig


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Vote:
    name: str
    value: int  # +1 BUY, -1 SELL, 0 abstain
    reason: str


@dataclass(frozen=True)
class Signal:
    action: Action
    buy_votes: int
    sell_votes: int
    votes: tuple[Vote, ...]

    def explain(self) -> str:
        lines = [f"{self.action.value}  (buy votes {self.buy_votes}, sell votes {self.sell_votes})"]
        lines += [f"  {v.name:<10} {_label(v.value):<5} {v.reason}" for v in self.votes]
        return "\n".join(lines)


def _label(value: int) -> str:
    return {1: "BUY", -1: "SELL", 0: "-"}[value]


def decide(buy_votes: int, sell_votes: int, min_votes: int) -> Action:
    """A side wins only with enough votes AND a strict majority over the other side. Ties are HOLD."""
    if buy_votes >= min_votes and buy_votes > sell_votes:
        return Action.BUY
    if sell_votes >= min_votes and sell_votes > buy_votes:
        return Action.SELL
    return Action.HOLD


def evaluate(row: pd.Series | dict, sentiment: float | None, cfg: StrategyConfig) -> Signal:
    """Evaluate the latest indicator row. `sentiment=None` means no data, so sentiment abstains."""
    price, rsi_v = row["close"], row["rsi"]
    votes = [
        Vote(
            "RSI",
            _band_vote(rsi_v, cfg.rsi_oversold, cfg.rsi_overbought),
            f"RSI {rsi_v:.1f} (oversold < {cfg.rsi_oversold:g}, overbought > {cfg.rsi_overbought:g})",
        ),
        Vote(
            "MACD",
            int(np.sign(row["macd"] - row["macd_signal"])),
            f"MACD {row['macd']:.2f} vs signal {row['macd_signal']:.2f}",
        ),
        Vote(
            "Bollinger",
            _band_vote(price, row["bb_lower"], row["bb_upper"], inclusive=True),
            f"price {price:,.2f} in band [{row['bb_lower']:,.2f}, {row['bb_upper']:,.2f}]",
        ),
    ]
    if sentiment is None:
        votes.append(Vote("Sentiment", 0, "no data, abstaining"))
    else:
        value = 1 if sentiment > cfg.sentiment_buy else -1 if sentiment < cfg.sentiment_sell else 0
        votes.append(
            Vote(
                "Sentiment",
                value,
                f"score {sentiment:+.3f} (buy > {cfg.sentiment_buy:g}, sell < {cfg.sentiment_sell:g})",
            )
        )
    buys = sum(v.value == 1 for v in votes)
    sells = sum(v.value == -1 for v in votes)
    return Signal(decide(buys, sells, cfg.min_votes), buys, sells, tuple(votes))


def _band_vote(value: float, low: float, high: float, inclusive: bool = False) -> int:
    """Below the band votes BUY (+1), above votes SELL (-1)."""
    if inclusive:
        return 1 if value <= low else -1 if value >= high else 0
    return 1 if value < low else -1 if value > high else 0


def vote_frame(df: pd.DataFrame, cfg: StrategyConfig, sentiment: pd.Series | None = None) -> pd.DataFrame:
    """Vectorised votes for every row of an indicator frame (used by backtests and charts)."""
    votes = pd.DataFrame(index=df.index)
    votes["RSI"] = np.select([df["rsi"] < cfg.rsi_oversold, df["rsi"] > cfg.rsi_overbought], [1, -1], 0)
    votes["MACD"] = np.sign(df["macd"] - df["macd_signal"]).fillna(0).astype(int)
    votes["Bollinger"] = np.select([df["close"] <= df["bb_lower"], df["close"] >= df["bb_upper"]], [1, -1], 0)
    if sentiment is not None:
        s = sentiment.reindex(df.index)
        votes["Sentiment"] = np.select([s > cfg.sentiment_buy, s < cfg.sentiment_sell], [1, -1], 0)
    else:
        votes["Sentiment"] = 0
    # Rows still warming up (indicators NaN) never vote.
    warm = df[["rsi", "macd_signal", "bb_upper"]].notna().all(axis=1)
    votes.loc[~warm] = 0
    return votes


def action_series(df: pd.DataFrame, cfg: StrategyConfig, sentiment: pd.Series | None = None) -> pd.Series:
    votes = vote_frame(df, cfg, sentiment)
    buys = (votes == 1).sum(axis=1)
    sells = (votes == -1).sum(axis=1)
    action = np.where(
        (buys >= cfg.min_votes) & (buys > sells),
        Action.BUY.value,
        np.where((sells >= cfg.min_votes) & (sells > buys), Action.SELL.value, Action.HOLD.value),
    )
    return pd.Series(action, index=df.index, name="action")
