# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""FastAPI server: a JSON API over the coin_buddy package plus the static frontend.

Run with `coin-buddy dashboard`, then open http://127.0.0.1:8000
"""

from __future__ import annotations

import copy
import logging
import math
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import ccxt
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coin_buddy import __version__
from coin_buddy.backtest import actions_to_target
from coin_buddy.config import Config, load_config
from coin_buddy.data.market import fetch_candles, make_exchange
from coin_buddy.data.sentiment import fetch_sentiment
from coin_buddy.indicators import add_indicators
from coin_buddy.pipeline import backtest, take_snapshot
from coin_buddy.signals import action_series
from coin_buddy.storage import Store

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
DISCLAIMER = "Educational tool. Not financial advice. Coin Buddy never places trades."
CSP_BASE = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    # The hash allows exactly one inline stylesheet: Lightweight Charts' attribution logo (v5.2.1).
    "style-src 'self' https://fonts.googleapis.com 'sha256-3pRED1tOXas1FXFoPb9TGCjmYe9XQsmO9OV23khV2nY='; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'"
)


def security_headers(frame_ancestors: list[str]) -> dict[str, str]:
    """Security headers for every response.

    By default no other site may show the app in a frame (clickjacking protection). Hosts that
    display apps inside a frame of their own page can be allowed by name via
    `web.frame_ancestors`; X-Frame-Options can't express an allow-list, so it's omitted then.
    """
    headers = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
    if frame_ancestors:
        headers["Content-Security-Policy"] = f"{CSP_BASE}; frame-ancestors 'self' {' '.join(frame_ancestors)}"
    else:
        headers["Content-Security-Policy"] = f"{CSP_BASE}; frame-ancestors 'none'"
        headers["X-Frame-Options"] = "DENY"
    return headers


class TTLCache:
    """Tiny thread-safe time-based cache, so many browser tabs don't multiply exchange requests."""

    def __init__(self) -> None:
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: Any, ttl: float, factory: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
        value = factory()
        with self._lock:
            self._data[key] = (now, value)
        return value


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=30)
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    days: int = Field(365, ge=30, le=1500)
    strategy: Literal["rules", "ml", "both"] = "both"


def _num(value: Any, digits: int = 8) -> float | None:
    """JSON-safe float: NaN/inf become null."""
    if value is None:
        return None
    f = float(value)
    return None if math.isnan(f) or math.isinf(f) else round(f, digits)


def _ts(index_value: pd.Timestamp) -> int:
    return int(index_value.timestamp())


def _downsample(series: pd.Series, max_points: int = 1500) -> list[dict]:
    step = max(1, math.ceil(len(series) / max_points))
    picked = series.iloc[::step]
    if len(series) and picked.index[-1] != series.index[-1]:
        picked = pd.concat([picked, series.iloc[[-1]]])
    return [{"time": _ts(t), "value": _num(v, 2)} for t, v in picked.items()]


def create_app(
    cfg: Config | None = None,
    exchange_factory: Callable[[str], Any] = make_exchange,
    sentiment_fetcher: Callable = fetch_sentiment,
) -> FastAPI:
    base = cfg or load_config()
    cache = TTLCache()
    exchanges: dict[str, Any] = {}
    exchanges_lock = threading.Lock()
    backtest_slot = threading.Semaphore(1)
    store = Store(base.resolve(base.storage.database))

    # ------------------------------------------------------------ helpers
    def exchange_for(exchange_id: str) -> Any:
        """One shared client per exchange, with markets loaded exactly once.

        Loading markets inside the lock stops concurrent first requests from each downloading
        the full market list in parallel (which made the first page load very slow).
        """
        with exchanges_lock:
            if exchange_id not in exchanges:
                exchange = exchange_factory(exchange_id)
                if hasattr(exchange, "load_markets"):
                    exchange.load_markets()
                exchanges[exchange_id] = exchange
            return exchanges[exchange_id]

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        def warm() -> None:
            try:
                exchange_for(base.market.exchange)
            except Exception as exc:  # noqa: BLE001 - warming is best-effort; requests will retry
                log.warning("Could not pre-load %s markets: %s", base.market.exchange, exc)

        threading.Thread(target=warm, daemon=True).start()
        yield

    app = FastAPI(title="Coin Buddy", version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)

    def supported_timeframes(exchange_id: str) -> list[str]:
        """Our timeframes that this exchange actually offers (Coinbase has no 4h, for example).

        ccxt lists them on the client class, so no network call is needed.
        """

        def load() -> list[str]:
            client = exchanges.get(exchange_id) or exchange_factory(exchange_id)
            offered = getattr(client, "timeframes", None)
            return [t for t in TIMEFRAMES if not isinstance(offered, dict) or t in offered]

        return cache.get_or_set(("timeframes", exchange_id), 86400, load)

    def config_for(exchange_id: str, symbol: str, timeframe: str) -> Config:
        allowed = supported_timeframes(exchange_id)
        if timeframe not in allowed:
            raise ValueError(f"Timeframe '{timeframe}' isn't available on {exchange_id}. Choose from {allowed}.")
        out = copy.deepcopy(base)
        out.market.exchange, out.market.symbol, out.market.timeframe = exchange_id, symbol, timeframe
        return out

    def sentiment_bundle():
        return cache.get_or_set(
            "sentiment", base.web.sentiment_cache_seconds, lambda: sentiment_fetcher(base.sentiment)
        )

    # ------------------------------------------------------------ errors + headers
    @app.exception_handler(ccxt.BadSymbol)
    async def bad_symbol(_: Request, exc: ccxt.BadSymbol) -> JSONResponse:
        return JSONResponse({"detail": "That symbol isn't listed on this exchange."}, status_code=404)

    @app.exception_handler(ccxt.NetworkError)
    async def network_error(_: Request, exc: ccxt.NetworkError) -> JSONResponse:
        return JSONResponse({"detail": "The exchange is unreachable right now. Retrying shortly."}, status_code=503)

    @app.exception_handler(ccxt.BaseError)
    async def exchange_error(_: Request, exc: ccxt.BaseError) -> JSONResponse:
        log.warning("Exchange error: %s", exc)
        return JSONResponse({"detail": f"Exchange error: {str(exc)[:200]}"}, status_code=502)

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    headers_for_every_response = security_headers(base.web.frame_ancestors)

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(headers_for_every_response)
        return response

    # ------------------------------------------------------------ routes
    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "version": __version__,
            "exchange": base.market.exchange,
            "symbol": base.market.symbol,
            "timeframe": base.market.timeframe,
            "timeframes": supported_timeframes(base.market.exchange),
            "watchlist": base.web.watchlist,
            "refresh_seconds": base.web.refresh_seconds,
            "ml_horizon": base.ml.horizon_candles,
            "thresholds": {
                "sentiment_buy": base.strategy.sentiment_buy,
                "sentiment_sell": base.strategy.sentiment_sell,
            },
            "costs": {"fee": base.backtest.fee_rate, "slippage": base.backtest.slippage_rate},
            "max_backtest_days": base.web.max_backtest_days,
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/markets")
    def markets(exchange: str = Query(None)) -> list[str]:
        ex_id = exchange or base.market.exchange

        def load() -> list[str]:
            mkts = exchange_for(ex_id).load_markets()
            spot = [s for s, m in mkts.items() if m.get("spot") and m.get("active") is not False]
            rank = {"USDT": 0, "USD": 1, "USDC": 2, "EUR": 3, "BTC": 4}
            return sorted(spot, key=lambda s: (rank.get(s.split("/")[-1], 9), s))

        return cache.get_or_set(("markets", ex_id), 3600, load)

    @app.get("/api/tickers")
    def tickers(symbols: str = Query(..., max_length=500), exchange: str = Query(None)) -> list[dict]:
        ex_id = exchange or base.market.exchange
        wanted = [s.strip() for s in symbols.split(",") if s.strip()][:20]
        ex = exchange_for(ex_id)

        def load() -> list[dict]:
            try:
                raw = ex.fetch_tickers(wanted)
            except ccxt.BaseError:
                raw = {}
                for s in wanted:
                    try:
                        raw[s] = ex.fetch_ticker(s)
                    except ccxt.BaseError as exc:
                        log.info("Ticker %s unavailable: %s", s, exc)
            out = []
            for s in wanted:
                t = raw.get(s)
                if not t:
                    continue
                pct = t.get("percentage")
                if pct is None and t.get("open") and t.get("last"):
                    pct = (t["last"] / t["open"] - 1) * 100
                out.append(
                    {
                        "symbol": s,
                        "last": _num(t.get("last")),
                        "change_pct": _num(pct, 3),
                        "high": _num(t.get("high")),
                        "low": _num(t.get("low")),
                        "quote_volume": _num(t.get("quoteVolume"), 0),
                    }
                )
            return out

        return cache.get_or_set(("tickers", ex_id, tuple(wanted)), 4, load)

    @app.get("/api/sparklines")
    def sparklines(symbols: str = Query(..., max_length=500), exchange: str = Query(None)) -> dict[str, list[float]]:
        ex_id = exchange or base.market.exchange
        wanted = [s.strip() for s in symbols.split(",") if s.strip()][:20]

        def load_one(sym: str) -> list[float]:
            try:
                df = fetch_candles(sym, "1h", 24, exchange=exchange_for(ex_id), closed_only=False)
                return [_num(v, 8) for v in df["close"]]
            except ccxt.BaseError:
                return []

        return {s: cache.get_or_set(("spark", ex_id, s), 300, lambda s=s: load_one(s)) for s in wanted}

    @app.get("/api/candles")
    def candles(
        symbol: str = Query(..., max_length=30),
        timeframe: str = Query("1h"),
        exchange: str = Query(None),
        limit: int = Query(None, ge=50, le=1000),
    ) -> dict:
        c = config_for(exchange or base.market.exchange, symbol, timeframe)
        n = limit or base.web.chart_candles

        def load() -> dict:
            ex = exchange_for(c.market.exchange)
            df = add_indicators(fetch_candles(symbol, timeframe, n, exchange=ex, closed_only=False), c.indicators)
            tf_ms = ex.parse_timeframe(timeframe) * 1000
            forming = bool(len(df)) and (df.index[-1].value // 1_000_000 + tf_ms > ex.milliseconds())
            closed = df.iloc[:-1] if forming else df
            # Markers show position changes (entries/exits), exactly what the backtester trades.
            target = actions_to_target(action_series(closed, c.strategy))
            change = target.diff().fillna(target)
            markers = [{"time": _ts(t), "action": "BUY" if d > 0 else "SELL"} for t, d in change[change != 0].items()]
            cols = ["open", "high", "low", "close", "volume", "rsi", "macd", "macd_signal", "macd_hist"]
            cols += ["bb_upper", "bb_mid", "bb_lower"]
            rows = [
                {"time": _ts(t), **{k: _num(r[k]) for k in cols}}
                for t, r in zip(df.index, df[cols].to_dict("records"), strict=True)
            ]
            return {"symbol": symbol, "timeframe": timeframe, "forming": forming, "candles": rows, "markers": markers}

        return cache.get_or_set(("candles", c.market.exchange, symbol, timeframe, n), 4, load)

    @app.get("/api/signal")
    def signal(
        symbol: str = Query(..., max_length=30), timeframe: str = Query("1h"), exchange: str = Query(None)
    ) -> dict:
        c = config_for(exchange or base.market.exchange, symbol, timeframe)

        def load() -> dict:
            snap = take_snapshot(
                c, exchange=exchange_for(c.market.exchange), store=store, sentiment_data=sentiment_bundle()
            )
            s, sig = snap.sentiment, snap.signal
            ranked = sorted(zip(snap.posts, snap.post_scores, strict=True), key=lambda ps: -abs(ps[1]))[:8]
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_time": _ts(snap.latest.name),
                "candle_close_time": _ts(snap.latest.name) + exchange_for(c.market.exchange).parse_timeframe(timeframe),
                "price": _num(snap.latest["close"]),
                "action": sig.action.value,
                "buy_votes": sig.buy_votes,
                "sell_votes": sig.sell_votes,
                "votes": [{"name": v.name, "value": v.value, "reason": v.reason} for v in sig.votes],
                "sentiment": {
                    "available": s.n_posts > 0,
                    "score": _num(s.score, 4),
                    "posts": s.n_posts,
                    "positive_share": _num(s.positive_share, 4),
                    "negative_share": _num(s.negative_share, 4),
                    "model": c.sentiment.model,
                    "subreddits": c.sentiment.subreddits,
                    "top_posts": [
                        {
                            "title": p.title,
                            "subreddit": p.subreddit,
                            "upvotes": p.upvotes,
                            "score": _num(sc, 3),
                            "url": p.url,
                        }
                        for p, sc in ranked
                    ],
                },
                "ml": None
                if snap.ml_p_up is None
                else {"p_up": _num(snap.ml_p_up, 4), "horizon": c.ml.horizon_candles},
            }

        return cache.get_or_set(("signal", c.market.exchange, symbol, timeframe), 60, load)

    @app.post("/api/backtest")
    def run_backtest_endpoint(req: BacktestRequest, exchange: str = Query(None)) -> dict:
        c = config_for(exchange or base.market.exchange, req.symbol, req.timeframe)
        if req.days > base.web.max_backtest_days:
            raise ValueError(f"This server allows backtests of up to {base.web.max_backtest_days} days.")
        strategies = ("rules", "ml") if req.strategy == "both" else (req.strategy,)

        def load() -> dict:
            # Backtests are CPU-heavy; on a shared public server, run one at a time.
            if not backtest_slot.acquire(blocking=False):
                raise HTTPException(429, "Another backtest is running. Please try again in a minute.")
            try:
                report = backtest(c, req.days, strategies, exchange=exchange_for(c.market.exchange))
            finally:
                backtest_slot.release()
            wf = report.walk_forward
            return {
                "symbol": req.symbol,
                "timeframe": req.timeframe,
                "start": _ts(report.candles.index[0]),
                "end": _ts(report.candles.index[-1]),
                "candles": len(report.candles),
                "costs": {"fee": c.backtest.fee_rate, "slippage": c.backtest.slippage_rate},
                "walk_forward": None
                if not wf or not wf.folds
                else {"folds": wf.folds, "accuracy": _num(wf.accuracy, 4), "baseline": _num(wf.baseline_accuracy, 4)},
                "results": [
                    {
                        "name": name,
                        "metrics": {k: _num(v, 6) for k, v in res.metrics.items()},
                        "equity": _downsample(res.equity),
                        "benchmark": _downsample(res.benchmark),
                        "trades": [
                            {
                                "entry_time": _ts(t["entry_time"]),
                                "exit_time": _ts(t["exit_time"]),
                                "entry_price": _num(t["entry_price"]),
                                "exit_price": _num(t["exit_price"]),
                                "net_return": _num(t["net_return"], 6),
                            }
                            for t in res.trades.iloc[::-1].head(300).to_dict("records")
                        ],
                    }
                    for name, res in report.results.items()
                ],
            }

        key = ("backtest", c.market.exchange, req.symbol, req.timeframe, req.days, req.strategy)
        return cache.get_or_set(key, 3600, load)

    @app.get("/api/history")
    def history(limit: int = Query(200, ge=1, le=2000)) -> list[dict]:
        df = store.snapshots(limit)
        if df.empty:
            return []
        df = df.iloc[::-1]
        return [
            {
                "taken_at": r["taken_at"].isoformat(),
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "exchange": r["exchange"],
                "price": _num(r["price"]),
                "rsi": _num(r["rsi"], 2),
                "sentiment": _num(r["sentiment"], 3),
                "ml_p_up": _num(r["ml_p_up"], 3),
                "action": r["action"],
            }
            for r in df.to_dict("records")
        ]

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
