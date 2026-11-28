# Web API

The dashboard is powered by a small JSON API (`coin_buddy/web/server.py`, built with FastAPI). You can call it from anything: `curl`, Python, or another app. While the server runs, interactive docs (Swagger UI) are at **`/api/docs`**.

Base URL: `http://127.0.0.1:8000` (see [`web` config](../getting-started/configuration.md#web)).

## Conventions

- All endpoints take an optional `exchange` query parameter. It defaults to `market.exchange` from the config.
- Times are **Unix seconds, UTC**.
- Missing numbers (for example RSI during warm-up) are `null`, never `NaN`.
- Symbols use ccxt's unified format: `BTC/USDT`. URL-encode the slash as `%2F` if your client doesn't.

## Endpoints

| Method | Path | Purpose | Cached for |
|---|---|---|---|
| GET | `/api/health` | Liveness check | — |
| GET | `/api/meta` | App settings the frontend needs | — |
| GET | `/api/markets` | All spot symbols on the exchange | 1 hour |
| GET | `/api/tickers` | Last price and 24h stats for several symbols | 4 s |
| GET | `/api/sparklines` | Last 24 hourly closes per symbol | 5 min |
| GET | `/api/candles` | Candles + indicators + BUY/SELL markers | 4 s |
| GET | `/api/signal` | The current signal, explained | 60 s |
| POST | `/api/backtest` | Run a backtest | 1 hour |
| GET | `/api/history` | Saved signals | — |

Caching is per argument combination and shared by everyone using the server, so ten open tabs cost the exchange the same as one. Sentiment has its own 5-minute cache (`web.sentiment_cache_seconds`) shared by every market.

---

### `GET /api/health`

```json
{"status": "ok", "version": "2.0.0"}
```

### `GET /api/meta`

```json
{
  "version": "2.0.0",
  "exchange": "binance",
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
  "watchlist": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"],
  "refresh_seconds": 10,
  "ml_horizon": 12,
  "thresholds": {"sentiment_buy": 0.2, "sentiment_sell": -0.2},
  "costs": {"fee": 0.001, "slippage": 0.0005},
  "max_backtest_days": 1500,
  "disclaimer": "Educational tool. Not financial advice. Coin Buddy never places trades."
}
```

### `GET /api/markets`

Active **spot** symbols, sorted with USDT, then USD, USDC, EUR and BTC quotes first.

```json
["BTC/USDT", "ETH/USDT", "SOL/USDT", "..."]
```

### `GET /api/tickers?symbols=BTC/USDT,ETH/USDT`

| Parameter | Required | Notes |
|---|---|---|
| `symbols` | yes | Comma-separated, up to 20. |

```json
[
  {"symbol": "BTC/USDT", "last": 60750.1, "change_pct": 1.39,
   "high": 61622.38, "low": 59795.23, "quote_volume": 1130000000}
]
```

`change_pct` is in **percent** (1.39 = +1.39%). If the exchange doesn't report it, it's computed from the 24h open. Symbols the exchange can't price are left out.

### `GET /api/sparklines?symbols=BTC/USDT,ETH/USDT`

```json
{"BTC/USDT": [60120.5, 60210.0, "... 24 closes"], "ETH/USDT": ["..."]}
```

A symbol that fails returns an empty list.

### `GET /api/candles`

| Parameter | Default | Notes |
|---|---|---|
| `symbol` | required | |
| `timeframe` | `1h` | One of `1m 5m 15m 1h 4h 1d`. |
| `limit` | `web.chart_candles` (500) | 50–1000. |

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "forming": true,
  "candles": [
    {"time": 1795716000, "open": 60480.0, "high": 60754.01, "low": 60468.63, "close": 60750.1,
     "volume": 186.33, "rsi": 56.9, "macd": 182.6, "macd_signal": 253.15, "macd_hist": -70.55,
     "bb_upper": 61028.52, "bb_mid": 60693.7, "bb_lower": 60358.97}
  ],
  "markers": [{"time": 1795500000, "action": "BUY"}]
}
```

- Unlike signals, the chart **includes the forming candle** (`forming: true`), so it looks live.
- `markers` are **position changes** of the rule strategy (entries and exits), computed on closed candles only.

### `GET /api/signal?symbol=BTC/USDT&timeframe=1h`

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "candle_time": 1795716000,
  "candle_close_time": 1795719600,
  "price": 60480.01,
  "action": "HOLD",
  "buy_votes": 1,
  "sell_votes": 1,
  "votes": [
    {"name": "RSI", "value": 0, "reason": "RSI 51.6 (oversold < 30, overbought > 70)"},
    {"name": "MACD", "value": -1, "reason": "MACD 182.60 vs signal 253.15"},
    {"name": "Bollinger", "value": 0, "reason": "price 60,480.01 in band [60,358.97, 61,028.52]"},
    {"name": "Sentiment", "value": 1, "reason": "score +0.252 (buy > 0.2, sell < -0.2)"}
  ],
  "sentiment": {
    "available": true, "score": 0.252, "posts": 50,
    "positive_share": 0.56, "negative_share": 0.24,
    "model": "vader", "subreddits": ["cryptocurrency", "bitcoin"],
    "top_posts": [
      {"title": "...", "subreddit": "bitcoin", "upvotes": 12, "score": 0.91, "url": "https://www.reddit.com/r/..."}
    ]
  },
  "ml": {"p_up": 0.358, "horizon": 12}
}
```

- `value` is +1 (BUY), −1 (SELL) or 0 (abstain).
- `ml` is `null` when no model exists for this exchange, symbol and timeframe.
- Each fresh computation is saved to history, so at most one row per minute per market and timeframe.

### `POST /api/backtest`

Request body:

```json
{"symbol": "BTC/USDT", "timeframe": "1h", "days": 365, "strategy": "both"}
```

| Field | Rules |
|---|---|
| `symbol` | 3–30 characters |
| `timeframe` | `1m 5m 15m 1h 4h 1d` |
| `days` | 30 up to `web.max_backtest_days` (1500 by default, 365 on the hosted demo) |
| `strategy` | `rules`, `ml` or `both` |

Response (abridged):

```json
{
  "symbol": "BTC/USDT", "timeframe": "1h",
  "start": 1764201600, "end": 1795716000, "candles": 8760,
  "costs": {"fee": 0.001, "slippage": 0.0005},
  "walk_forward": {"folds": 27, "accuracy": 0.576, "baseline": 0.625},
  "results": [
    {
      "name": "rules",
      "metrics": {"total_return": -0.2289, "return_before_costs": -0.1409, "buy_and_hold_return": -0.3285,
                  "sharpe": -0.59, "buy_and_hold_sharpe": -0.70, "max_drawdown": -0.3901,
                  "buy_and_hold_max_drawdown": -0.4287, "exposure": 0.544, "round_trips": 36,
                  "win_rate": 0.667, "avg_trade_return": -0.0048, "costs_paid": 0.108},
      "equity":    [{"time": 1764205200, "value": 10000.0}, "..."],
      "benchmark": [{"time": 1764205200, "value": 10012.3}, "..."],
      "trades":    [{"entry_time": 1793912400, "exit_time": 1795467600, "entry_price": 76029.78,
                     "exit_price": 63840.95, "net_return": -0.1628}]
    }
  ]
}
```

- Metrics are **fractions** (−0.2289 = −22.89%). Definitions: [Backtesting → Metrics](../concepts/backtesting.md#metrics).
- `results[].name` is `rules`, `ml` and/or `rules (ML test window)`.
- Equity curves are downsampled to at most 1,500 points; `trades` holds the 300 most recent, newest first.
- Backtests with ML can take up to a minute. Identical requests within an hour are instant.
- Only one backtest runs at a time; a second concurrent request gets **429** with a "try again in a minute" message.

### `GET /api/history?limit=200`

`limit` is 1–2000. Newest first.

```json
[{"taken_at": "2026-11-27T01:46:00+00:00", "symbol": "BTC/USDT", "timeframe": "1h", "exchange": "binance",
  "price": 60718.59, "rsi": 56.3, "sentiment": 0.256, "ml_p_up": 0.394, "action": "HOLD"}]
```

## Errors

Errors are JSON: `{"detail": "message"}`.

| Status | When |
|---|---|
| 400 | Invalid argument, e.g. an unsupported timeframe or unknown exchange. |
| 404 | The symbol isn't listed on the exchange. |
| 422 | The request body failed validation (e.g. `days: 5`). |
| 502 | The exchange returned an error. |
| 503 | The exchange is unreachable (network error). |

## Security headers

Every response carries:

| Header | Value / purpose |
|---|---|
| `Content-Security-Policy` | Scripts only from this server and `cdn.jsdelivr.net`; styles only from this server and Google Fonts, plus one inline style allowed by hash (the chart library's attribution logo); network calls only to this server. |
| `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` | The app can't be embedded in other sites (clickjacking protection). A host that shows apps in a frame can be allowed by name with `web.frame_ancestors`. |
| `X-Content-Type-Options: nosniff` | Browsers won't guess file types. |
| `Referrer-Policy: no-referrer` | Clicking a Reddit link doesn't leak your dashboard URL. |

The server binds to `127.0.0.1` by default, so only your computer can reach it. There's no login. If you expose it publicly, put it behind a reverse proxy with authentication, or keep it read-only as it is: it never places trades and has no write endpoints except running backtests.

## Using the API from Python

```python
import requests

base = "http://127.0.0.1:8000"
sig = requests.get(f"{base}/api/signal", params={"symbol": "ETH/USDT", "timeframe": "4h"}).json()
print(sig["action"], [(v["name"], v["value"]) for v in sig["votes"]])

bt = requests.post(f"{base}/api/backtest", json={"symbol": "ETH/USDT", "timeframe": "4h", "days": 365}).json()
for r in bt["results"]:
    print(r["name"], round(r["metrics"]["total_return"] * 100, 2), "%")
```
