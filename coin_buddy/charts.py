# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Plotly figures shared by the Streamlit dashboard and the HTML backtest reports."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from coin_buddy.backtest import BacktestResult

BUY_COLOR, SELL_COLOR = "#16a34a", "#dc2626"


def price_chart(df: pd.DataFrame, actions: pd.Series | None = None, title: str = "") -> go.Figure:
    """Candles + Bollinger Bands, with RSI and MACD panels and optional BUY/SELL markers."""
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(title, "RSI", "MACD"),
    )
    fig.add_trace(
        go.Candlestick(x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"], name="Price"),
        row=1,
        col=1,
    )
    for col, dash in (("bb_upper", "dot"), ("bb_mid", "solid"), ("bb_lower", "dot")):
        fig.add_trace(
            go.Scatter(x=df.index, y=df[col], name=col, line={"width": 1, "dash": dash, "color": "#64748b"}),
            row=1,
            col=1,
        )
    if actions is not None:
        for action, color, symbol in (("BUY", BUY_COLOR, "triangle-up"), ("SELL", SELL_COLOR, "triangle-down")):
            hits = actions[actions == action].index.intersection(df.index)
            fig.add_trace(
                go.Scatter(
                    x=hits,
                    y=df.loc[hits, "close"],
                    mode="markers",
                    name=action,
                    marker={"color": color, "symbol": symbol, "size": 9},
                ),
                row=1,
                col=1,
            )
    fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], name="RSI", line={"color": "#7c3aed"}), row=2, col=1)
    for level in (30, 70):
        fig.add_hline(y=level, line={"dash": "dash", "width": 1, "color": "#94a3b8"}, row=2, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df["macd_hist"], name="MACD hist", marker_color="#94a3b8"), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd"], name="MACD", line={"color": "#2563eb"}), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], name="Signal", line={"color": "#f59e0b"}), row=3, col=1)
    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": -0.08},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
    )
    return fig


def equity_chart(results: dict[str, BacktestResult], title: str = "Equity curve") -> go.Figure:
    fig = go.Figure()
    benchmark_drawn = False
    for name, res in results.items():
        fig.add_trace(go.Scatter(x=res.equity.index, y=res.equity, name=name))
        if not benchmark_drawn:
            fig.add_trace(
                go.Scatter(
                    x=res.benchmark.index, y=res.benchmark, name="buy & hold", line={"dash": "dash", "color": "#64748b"}
                )
            )
            benchmark_drawn = True
    fig.update_layout(
        title=title,
        yaxis_title="Portfolio value",
        height=450,
        legend={"orientation": "h", "y": -0.15},
        margin={"t": 50, "l": 40, "r": 20},
    )
    return fig
