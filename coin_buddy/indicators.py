# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Technical indicators implemented directly in pandas, so every formula is visible and testable."""

from __future__ import annotations

import pandas as pd

from coin_buddy.config import IndicatorConfig


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing (the standard definition)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # No losses at all means maximum strength; no movement at all is neutral.
    out = out.where(avg_loss != 0, 100.0)
    out = out.where((avg_gain != 0) | (avg_loss != 0), 50.0)
    return out.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, signal_line, line - signal_line


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Upper band, middle band (SMA) and lower band."""
    mid = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    return mid + num_std * std, mid, mid - num_std * std


def add_indicators(df: pd.DataFrame, cfg: IndicatorConfig | None = None) -> pd.DataFrame:
    """Return a copy of an OHLCV frame with all indicator columns added."""
    cfg = cfg or IndicatorConfig()
    out = df.copy()
    close = out["close"]
    out["rsi"] = rsi(close, cfg.rsi_window)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = bollinger(close, cfg.bb_window, cfg.bb_std)
    band_width = out["bb_upper"] - out["bb_lower"]
    out["bb_pct_b"] = (close - out["bb_lower"]) / band_width.where(band_width != 0)
    return out
