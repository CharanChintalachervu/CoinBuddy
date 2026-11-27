# Architecture overview

Coin Buddy is one Python package (`coin_buddy`) with three ways in: the **CLI**, the **web API**, and **tests**. All three call the same functions, so behaviour is identical everywhere.

## Components

```mermaid
flowchart TB
    subgraph External["External (free, public)"]
        EX[(Exchange<br/>via ccxt)]
        RD[(Reddit)]
    end

    subgraph Data["coin_buddy.data"]
        M[market.py<br/>candles, pagination,<br/>retries, closed only]
        S[sentiment.py<br/>fetch + VADER/FinBERT]
    end

    subgraph Analytics
        I[indicators.py<br/>RSI · MACD · Bollinger]
        SG[signals.py<br/>voting engine]
        BT[backtest.py<br/>costs, metrics]
        ML[ml.py<br/>features, walk-forward]
    end

    P[pipeline.py<br/>snapshot + backtest<br/>orchestration]
    DB[(SQLite<br/>storage.py)]

    subgraph Interfaces
        CLI[cli.py<br/>coin-buddy]
        API[web/server.py<br/>FastAPI + cache]
        UI[web/static<br/>HTML · CSS · JS]
    end

    EX --> M
    RD --> S
    M --> I --> SG
    S --> SG
    I --> ML
    SG --> P
    ML --> P
    BT --> P
    P --> DB
    P --> CLI
    P --> API --> UI
    CLI --> AL[alerts.py]
```

## Modules at a glance

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | Typed settings from `config.yaml` and `.env`; per-market model paths | PyYAML, python-dotenv |
| `data/market.py` | Fetch OHLCV candles from any exchange, page past request limits, retry network errors, drop the forming candle | ccxt |
| `data/sentiment.py` | Fetch Reddit posts, score them, aggregate | requests, VADER, optional praw/FinBERT |
| `indicators.py` | RSI, MACD, Bollinger, %B | pandas |
| `signals.py` | Votes → BUY/SELL/HOLD (single-row and vectorised) | NumPy, pandas |
| `backtest.py` | Simulate a target position with costs; compute metrics | pandas |
| `ml.py` | Features, labels, walk-forward evaluation, train/save/predict | scikit-learn, joblib |
| `pipeline.py` | `take_snapshot()` and `backtest()`: the two workflows everything uses | all of the above |
| `storage.py` | SQLite history of signals and posts | sqlite3 (standard library) |
| `alerts.py` | Sound and Discord notifications | requests |
| `charts.py` | Plotly figures for the HTML backtest report | Plotly |
| `cli.py` | The `coin-buddy` command | pipeline |
| `web/server.py` | JSON API, caching, security headers, static files | FastAPI, uvicorn |
| `web/static/` | The browser app | Lightweight Charts (CDN) |

## Workflow 1: a live signal

What happens when you run `coin-buddy snapshot` or open the dashboard's Signal card:

```mermaid
sequenceDiagram
    autonumber
    participant Caller as CLI / Web API
    participant P as pipeline.take_snapshot
    participant M as market.fetch_candles
    participant I as indicators
    participant S as sentiment
    participant SG as signals.evaluate
    participant ML as ml.predict_latest
    participant DB as Store
    Caller->>P: config (exchange, symbol, timeframe)
    P->>M: last 300 closed candles
    M-->>P: OHLCV DataFrame
    P->>I: add_indicators()
    P->>S: fetch_sentiment() (or cached bundle)
    S-->>P: score, posts, per-post scores
    P->>SG: evaluate(latest candle, sentiment)
    SG-->>P: Signal (action + votes + reasons)
    P->>ML: predict_latest(candles, model for this market)
    ML-->>P: P(up) or None
    P->>DB: save snapshot + posts
    P-->>Caller: Snapshot
```

## Workflow 2: a backtest

```mermaid
sequenceDiagram
    autonumber
    participant Caller as CLI / Web API
    participant P as pipeline.backtest
    participant M as market.fetch_history
    participant SG as signals.action_series
    participant ML as ml.walk_forward
    participant BT as backtest.run_backtest
    Caller->>P: days, strategies
    P->>M: N days of closed candles
    P->>SG: actions for every candle (rules)
    P->>BT: rules → equity, trades, metrics
    P->>ML: out-of-sample probabilities
    P->>BT: ML → equity, trades, metrics
    P->>BT: rules on ML's test window (fair comparison)
    P-->>Caller: BacktestReport
```

## Workflow 3: the dashboard

The browser never computes signals. It asks the API and draws the answers:

```mermaid
sequenceDiagram
    participant B as Browser (app.js)
    participant A as FastAPI (server.py)
    participant C as TTL cache
    participant X as Exchange / Reddit
    B->>A: GET /api/candles?symbol&timeframe (every 10 s)
    A->>C: fresh within 4 s?
    alt cached
        C-->>A: cached rows
    else expired
        A->>X: fetch candles
        X-->>A: OHLCV
        A->>C: store
    end
    A-->>B: candles + indicators + markers (JSON)
    B->>B: update chart incrementally
    B->>A: GET /api/signal (every 60 s)
    A-->>B: action, votes, sentiment, ML
```

Details: [Web API](web-api.md) · [Frontend](frontend.md).

## Design principles

1. **One source of truth.** Signals, backtests and the UI all run the same functions. A test proves the vectorised and single-row signal paths agree.
2. **No lookahead, anywhere.** Closed candles for signals; next-open fills in backtests; walk-forward with a gap for ML.
3. **Degrade, don't crash.** A Reddit outage makes sentiment abstain; a slow exchange shows "Delayed"; an alert failure logs a warning.
4. **Free and keyless.** Public endpoints only; secrets are optional and live in `.env`.
5. **Explainable.** Every number on screen can be traced to a formula in these docs.

The reasoning behind each choice is in [Design decisions](../DESIGN.md).
