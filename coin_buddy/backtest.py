# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Long-only spot backtester with realistic costs and no lookahead.

Timing model: a signal computed from candle t's CLOSE is executed at candle t+1's OPEN.
Every change in position pays fee + slippage. Results are always compared against
buy-and-hold over the exact same period.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from coin_buddy.config import BacktestConfig


@dataclass
class BacktestResult:
    equity: pd.Series  # strategy equity curve
    benchmark: pd.Series  # buy-and-hold equity curve
    position: pd.Series  # 1 = in the market, 0 = in cash, per candle
    trades: pd.DataFrame  # one row per round trip
    metrics: dict[str, float]


def actions_to_target(actions: pd.Series) -> pd.Series:
    """BUY -> want to be long, SELL -> want to be flat, HOLD -> keep the previous target."""
    target = actions.map({"BUY": 1.0, "SELL": 0.0})
    return target.ffill().fillna(0.0)


def periods_per_year(index: pd.DatetimeIndex) -> float:
    step = pd.Series(index).diff().median()
    return pd.Timedelta(days=365) / step if pd.notna(step) and step > pd.Timedelta(0) else 365.0


def run_backtest(df: pd.DataFrame, target: pd.Series, cfg: BacktestConfig | None = None) -> BacktestResult:
    """Simulate holding `target` (0..1 fraction long, decided at each close) on candles `df`."""
    cfg = cfg or BacktestConfig()
    cost = cfg.fee_rate + cfg.slippage_rate
    opens = df["open"]
    # Return earned by whoever holds the asset from this open to the next open.
    bar_ret = (opens.shift(-1) / opens - 1).iloc[:-1]
    held = target.reindex(df.index).shift(1).fillna(0.0).iloc[:-1]  # filled at this bar's open
    turnover = held.diff().abs().fillna(held.abs())  # entering on bar 0 also costs
    # Costs come off capital at the open, then the bar's return applies to what's left.
    strat_ret = (1 - turnover * cost) * (1 + held * bar_ret) - 1

    equity = cfg.initial_capital * (1 + strat_ret).cumprod()
    benchmark = cfg.initial_capital * (1 + bar_ret).cumprod()
    trades = _round_trips(held, opens, cost)
    metrics = _metrics(strat_ret, bar_ret, equity, benchmark, held, trades, turnover, cost, df.index)
    return BacktestResult(equity, benchmark, held, trades, metrics)


def _round_trips(held: pd.Series, opens: pd.Series, cost: float) -> pd.DataFrame:
    """List each entry -> exit, closing any open position at the final open."""
    change = held.diff().fillna(held)
    entries = list(held.index[change > 0])
    exits = list(held.index[change < 0])
    if len(exits) < len(entries):
        exits.append(opens.index[len(held)])  # mark-to-market at the last available open
    rows = []
    for entry, exit_ in zip(entries, exits, strict=True):
        gross = opens[exit_] / opens[entry] - 1
        net = (opens[exit_] / opens[entry]) * (1 - cost) ** 2 - 1
        rows.append(
            {
                "entry_time": entry,
                "exit_time": exit_,
                "entry_price": opens[entry],
                "exit_price": opens[exit_],
                "gross_return": gross,
                "net_return": net,
            }
        )
    return pd.DataFrame(
        rows, columns=["entry_time", "exit_time", "entry_price", "exit_price", "gross_return", "net_return"]
    )


def _max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1).min()) if len(equity) else 0.0


def _metrics(strat_ret, bar_ret, equity, benchmark, held, trades, turnover, cost, index) -> dict[str, float]:
    ppy = periods_per_year(index)
    vol = strat_ret.std()
    gross_ret = (1 + held * bar_ret).prod() - 1
    return {
        "total_return": float((1 + strat_ret).prod() - 1),
        "return_before_costs": float(gross_ret),
        "buy_and_hold_return": float((1 + bar_ret).prod() - 1),
        "sharpe": float(strat_ret.mean() / vol * np.sqrt(ppy)) if vol > 0 else 0.0,
        "buy_and_hold_sharpe": float(bar_ret.mean() / bar_ret.std() * np.sqrt(ppy)) if bar_ret.std() > 0 else 0.0,
        "max_drawdown": _max_drawdown(equity),
        "buy_and_hold_max_drawdown": _max_drawdown(benchmark),
        "exposure": float(held.mean()),
        "round_trips": float(len(trades)),
        "win_rate": float((trades["net_return"] > 0).mean()) if len(trades) else 0.0,
        "avg_trade_return": float(trades["net_return"].mean()) if len(trades) else 0.0,
        "costs_paid": float(turnover.sum() * cost),  # simple sum, ignores compounding
    }


def format_metrics(m: dict[str, float]) -> str:
    pct = lambda v: f"{v * 100:+.2f}%"  # noqa: E731
    rows = [
        ("Strategy return (after costs)", pct(m["total_return"])),
        ("Strategy return (before costs)", pct(m["return_before_costs"])),
        ("Buy & hold return", pct(m["buy_and_hold_return"])),
        ("Sharpe (strategy / buy & hold)", f"{m['sharpe']:.2f} / {m['buy_and_hold_sharpe']:.2f}"),
        ("Max drawdown (strategy / B&H)", f"{pct(m['max_drawdown'])} / {pct(m['buy_and_hold_max_drawdown'])}"),
        ("Time in market", f"{m['exposure'] * 100:.1f}%"),
        ("Round trips", f"{int(m['round_trips'])}"),
        ("Win rate (after costs)", f"{m['win_rate'] * 100:.1f}%"),
        ("Average trade (after costs)", pct(m["avg_trade_return"])),
        ("Costs paid (fraction of capital)", pct(-m["costs_paid"])),
    ]
    width = max(len(r[0]) for r in rows)
    return "\n".join(f"  {k:<{width}}  {v}" for k, v in rows)
