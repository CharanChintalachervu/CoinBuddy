# Extending Coin Buddy

Recipes for the most common changes. After any change, run `pytest` and `ruff check .`.

## Switch exchange or coin

No code needed. Edit `config.yaml`:

```yaml
market:
  exchange: kraken
  symbol: ETH/USD
web:
  watchlist: [BTC/USD, ETH/USD, SOL/USD]
```

Any of [ccxt's 100+ exchanges](https://docs.ccxt.com/#/README?id=supported-cryptocurrency-exchanges) works for public data.

## Add a new indicator (end to end)

Example: a 50-period EMA that votes BUY when price is above it.

1. **Compute it** in `coin_buddy/indicators.py`, inside `add_indicators()`:

    ```python
    out["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    ```

2. **Vote with it** in `coin_buddy/signals.py`, in **both** paths:

    ```python
    # evaluate()
    votes.append(Vote("EMA50", int(np.sign(row["close"] - row["ema_50"])), f"price vs EMA50 {row['ema_50']:,.2f}"))

    # vote_frame()
    votes["EMA50"] = np.sign(df["close"] - df["ema_50"]).fillna(0).astype(int)
    ```

    Also add `"ema_50"` to the warm-up check in `vote_frame()`.

3. **Test it.** `test_vectorised_matches_single_row` immediately tells you if the two paths disagree. Add a test for the new rule.

4. **Show it on the chart** (optional):
    - Add `"ema_50"` to `cols` in the `/api/candles` handler (`web/server.py`).
    - In `app.js`, add a toggle chip in `index.html` (`data-ind="ema"`), a `LineSeries` in `buildChart()`, and its data in `seriesPayload()`.

5. **Backtest it**: `coin-buddy backtest --strategy rules`. Did it help after costs?

!!! tip
    The signal card, CLI output and history pick up the new vote automatically. They iterate over `signal.votes`.

## Use a different sentiment model

Write a scorer, a function that takes a list of texts and returns scores from −1 to +1, and register it:

```python
# coin_buddy/data/sentiment.py
def my_scorer(texts: list[str]) -> list[float]: ...


def get_scorer(name: str) -> Scorer:
    scorers = {"vader": vader_scorer, "finbert": finbert_scorer, "mine": my_scorer}
    ...
```

Then set `sentiment.model: mine`.

## Add a new sentiment source

Return a list of `Post` objects from a new fetch function, and call it from `fetch_sentiment()`. Wrap it in `try/except` like the Reddit fetch, so an outage degrades to "no data" instead of crashing.

## Backtest with your sentiment history

After running `coin-buddy watch` for a few weeks:

```python
from coin_buddy.config import load_config
from coin_buddy.data.market import fetch_history
from coin_buddy.indicators import add_indicators
from coin_buddy.signals import action_series
from coin_buddy.backtest import run_backtest, actions_to_target, format_metrics
from coin_buddy.storage import Store

cfg = load_config()
store = Store(cfg.resolve(cfg.storage.database))
sentiment = store.sentiment_history("1h")  # hourly mean sentiment

candles = add_indicators(fetch_history("BTC/USDT", "1h", days=30))
candles = candles[candles.index >= sentiment.index.min()]
actions = action_series(candles, cfg.strategy, sentiment=sentiment)
result = run_backtest(candles, actions_to_target(actions), cfg.backtest)
print(format_metrics(result.metrics))
```

!!! warning "Watch the timing"
    Sentiment bucketed at 14:00 contains posts from 14:00–14:59. To avoid lookahead on 1h candles, shift it by one bucket (`sentiment.shift(1)`) so each candle only sees sentiment from before its close.

## Make the ML model trade less

Try these one at a time, re-running `coin-buddy backtest --strategy ml`:

```yaml
ml:
  probability_threshold: 0.6   # was 0.55: only act on stronger convictions
  horizon_candles: 24          # was 12: predict bigger moves that can pay for costs
```

Then confirm on a **different** market or period. If an improvement only shows up on the data you tuned on, it's overfitting.

## Add an API endpoint

1. Add a function inside `create_app()` in `web/server.py`, decorated with `@app.get(...)` or `@app.post(...)`.
2. Wrap expensive work in `cache.get_or_set(key, ttl_seconds, loader)`.
3. Return plain JSON types. Use `_num()` for floats so `NaN` becomes `null`.
4. Add a test in `tests/test_web.py` using the `client` fixture.

It appears automatically in `/api/docs`.

## Add a CLI command

In `cli.py`, write `cmd_name(cfg, args) -> int`, register a subparser in `build_parser()`, and call `market_opts(sp)` if it takes market options.
