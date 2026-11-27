# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Typed configuration loaded from config.yaml, with secrets from .env."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass
class MarketConfig:
    exchange: str = "binance"
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    lookback_candles: int = 300


@dataclass
class IndicatorConfig:
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_window: int = 20
    bb_std: float = 2.0


@dataclass
class StrategyConfig:
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    sentiment_buy: float = 0.2
    sentiment_sell: float = -0.2
    min_votes: int = 2


@dataclass
class SentimentConfig:
    source: str = "reddit"
    subreddits: list[str] = field(default_factory=lambda: ["cryptocurrency", "bitcoin"])
    posts_per_subreddit: int = 25
    include_body: bool = True
    model: str = "vader"


@dataclass
class BacktestConfig:
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    initial_capital: float = 10_000


@dataclass
class MLConfig:
    horizon_candles: int = 12
    train_candles: int = 2000
    test_candles: int = 250
    probability_threshold: float = 0.55
    model_path: str = "models/{exchange}-{symbol}-{timeframe}.joblib"


@dataclass
class StorageConfig:
    database: str = "data/coin_buddy.db"


@dataclass
class AlertConfig:
    sound: bool = True
    discord_webhook_env: str = "DISCORD_WEBHOOK_URL"


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    watchlist: list[str] = field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
    )
    chart_candles: int = 500
    refresh_seconds: int = 10
    sentiment_cache_seconds: int = 300


@dataclass
class Config:
    market: MarketConfig = field(default_factory=MarketConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def resolve(self, relative: str) -> Path:
        """Resolve a config path relative to the project root."""
        path = Path(relative)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def model_file(self) -> Path:
        """Model file for the current market, e.g. models/binance-BTC-USDT-1h.joblib."""
        m = self.market
        name = self.ml.model_path.format(
            exchange=m.exchange, symbol=m.symbol.replace("/", "-").replace(":", "-"), timeframe=m.timeframe
        )
        return self.resolve(name)


def _build(cls: type, data: dict[str, Any] | None) -> Any:
    """Build a dataclass from a dict, rejecting unknown keys so typos fail loudly."""
    data = data or {}
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} keys in config: {sorted(unknown)}")
    kwargs = {}
    for name, value in data.items():
        default = known[name].default_factory() if callable(known[name].default_factory) else None
        kwargs[name] = _build(type(default), value) if is_dataclass(default) else value
    return cls(**kwargs)


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml (or the given file) and the .env file next to it."""
    load_dotenv(PROJECT_ROOT / ".env")
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return Config()
    with open(config_path, encoding="utf-8") as fh:
        return _build(Config, yaml.safe_load(fh))
