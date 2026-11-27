# Design decisions

This document explains *why* Coin Buddy is built the way it is. Each section states the decision, the alternative that was rejected, and the reason.

## 1. Market data: ccxt public endpoints, no API keys

**Decision:** fetch candles through [ccxt](https://github.com/ccxt/ccxt) using public endpoints.
**Rejected:** `python-binance` with API keys (v1).
**Why:** reading prices never needs authentication. Requiring keys adds a security risk (v1 leaked them in source code) and blocks users without an account. ccxt also lets one config line switch between 100+ exchanges, which matters because Binance blocks US users (`exchange: coinbase` with `symbol: BTC/USD` works there, with full history for backtests).

**Detail worth knowing:** `fetch_candles(closed_only=True)` drops the candle that is still forming. Indicators computed on a half-finished candle change until it closes, so a live signal could flip and a backtest would never see that behavior.

## 2. Indicators: written in pandas, cross-checked against `ta`

**Decision:** implement RSI, MACD and Bollinger Bands directly (`coin_buddy/indicators.py`, see the [code reference](reference/analytics.md)).
**Rejected:** depending on the `ta` library at runtime.
**Why:** each indicator is a few lines, and having them visible is the point of a learning project. A test still compares the results against `ta` to prove the formulas are right.
**Subtle point:** `ta` seeds RSI with a fake 0 for the first price change. Our version treats it as missing. Wilder smoothing forgets its seed exponentially, so the two agree after a few hundred candles; the test checks exactly that.

## 3. Signal engine: votes with abstention, ties are HOLD

**Decision:** each indicator votes +1, -1 or 0 (abstain). A side wins only with at least `min_votes` votes **and** a strict majority.
**Rejected:** v1's design, where HOLD was also a "vote" and `max()` picked the first key on a tie.
**Why:** in v1, a 2–2 tie between BUY and SELL always returned BUY because of dictionary order, which is a silent bias. Abstaining also lets missing data (Reddit down) drop out cleanly instead of being treated as neutral evidence.
**Guarantee:** there's a single-row path for live use and a vectorized path for backtests, and `test_vectorised_matches_single_row` proves they always agree.

## 4. Backtesting: next-open execution, costs on every trade, always vs buy-and-hold

| Rule | Why |
|---|---|
| A signal from candle *t*'s close fills at candle *t+1*'s open | You can't trade at a price you only learn after it's printed. Filling at the same close is the most common backtest bug (lookahead bias). |
| Fee + slippage on every position change | Short-timeframe strategies often have a real edge *before* costs and lose money after. Coin Buddy's ML model is an example (see README). |
| Always report buy-and-hold over the same window | "Lost 30%" means nothing on its own; in a market that fell 40%, it might be good. |
| Report exposure (time in market) | A long-only strategy in a falling market looks good just by sitting in cash. Exposure exposes that. |
| Compare strategies on the same window | ML can't trade during its first training window, so the rules are re-run on the ML test window for a fair comparison. |

## 5. Machine learning: real labels, walk-forward, purged gap, naive baseline

**Decision:** label each candle with "did price beat round-trip costs over the next *h* candles?", train a gradient-boosting classifier, and evaluate walk-forward.
**Rejected:** v1's model, trained on random numbers labeled by the rule engine. That can only learn to copy the rules, never to beat them.
**Why each piece exists:**
- **Walk-forward** (train on the past, test on the next unseen window, slide forward) mimics how a model is actually used. A random train/test split on time series leaks the future into training.
- **Purged gap of `horizon + 1` candles** between train and test: the last training labels look *h* candles ahead, so without the gap they'd overlap the test period.
- **Naive baseline** (always predict the training window's majority class): accuracy is meaningless without it. If 62% of hours don't beat costs, a model that always says "no" scores 62%.
- **Scale-free features** (returns, %B, MACD / price): raw prices make a model trained at $30k useless at $90k.
- **Sentiment isn't a feature** because free historical Reddit data doesn't exist. `coin-buddy watch` stores it going forward, so it can be added once enough history builds up.

## 6. Sentiment: VADER plus a crypto lexicon, FinBERT optional

**Decision:** VADER with ~40 crypto slang words added; FinBERT behind an optional install.
**Rejected:** TextBlob (v1), which is tuned for product reviews and scores most headlines as exactly 0.
**Why:** VADER is built for social media (emoji, caps, "!!!"), runs instantly on any CPU, and needs no download. FinBERT is stronger on financial language but pulls in about 1.5 GB of PyTorch, so it stays opt-in. Both return the same −1..+1 scale, so they're interchangeable.
**Failure handling:** if Reddit is unreachable, sentiment returns "no data" and abstains from the vote; the app keeps working.

## 7. Storage: SQLite

**Decision:** SQLite via the standard library.
**Rejected:** CSV (v1), or Postgres.
**Why:** CSV can't de-duplicate re-fetched posts or be queried. Postgres needs a server. SQLite is one file, needs no install, and `INSERT OR IGNORE` on the Reddit post id prevents double counting.

## 8. Configuration: YAML + typed dataclasses + strict keys

Thresholds, symbols and costs live in `config.yaml`, and secrets live in `.env`. Unknown keys raise an error, so a typo like `symbl:` fails loudly instead of being silently ignored.

## 9. Web app: FastAPI + plain JavaScript + Lightweight Charts

**Decision:** a FastAPI JSON API serving a static frontend written in plain HTML, CSS and JavaScript, with charts from TradingView's open-source Lightweight Charts.
**Rejected:** Streamlit (an earlier v2 build), and React with a bundler.
**Why:** Streamlit reruns the whole script on every click and can't do smooth live charts, so it never feels like a trading app. React would look the same but forces every buyer to install Node.js and learn a build tool. Lightweight Charts is the canvas engine real broker and exchange sites use: about 45 KB gzipped, fast with thousands of candles, and it supports multiple panes for RSI and MACD.

Details worth being able to explain:
- **API shape:** the frontend never computes signals. It calls `/api/candles`, `/api/signal` and so on, so the CLI, the web app and the tests all share the same tested Python code.
- **Caching per data type:** prices 4 s, candles 4 s, signals 60 s, sentiment 5 min (Reddit rate limits), backtests 1 h. Ten open tabs cost the exchange the same as one.
- **Markets loaded once, under a lock, at startup:** ccxt downloads the exchange's full market list on first use. Without the lock, concurrent first requests each downloaded it in parallel and the first page took more than 20 s; now it takes about 3 s, and the server warms it up before the first visitor arrives.
- **Chart markers = position changes:** BUY/SELL arrows mark where the backtester would enter or exit, not every candle with a BUY vote, so the chart and the backtest tell the same story. They never appear on the still-forming candle.
- **Incremental live updates:** new candles are applied with `series.update()`, so a user who has zoomed in isn't thrown back to the latest candle every 10 seconds.
- **Security:** a strict Content-Security-Policy (no inline scripts; one inline stylesheet allowed by its hash, for the chart library's attribution logo), framing denied by default (`X-Frame-Options: DENY`; only an explicitly configured host like Hugging Face may embed it), `nosniff`, and Subresource Integrity on the chart library from the CDN. All Reddit text is HTML-escaped and post links are only rendered when they point to reddit.com.
- **Resilience:** polling pauses when the tab is hidden, the status pill shows Live, Delayed or Offline, and failures show retry buttons instead of blank areas.

## Questions to be ready for

- *Why does the rule strategy lose money?* Classic indicators are public, so any edge they had is priced in. And on short timeframes, fees exceed the average move after a signal.
- *The ML model makes money before costs. Why not just trade less?* That's the right next step: raise `probability_threshold`, lengthen `horizon_candles`, or only switch position when the signal changes strongly (hysteresis). Each idea must be re-tested walk-forward. Tuning on the same data you report results on is overfitting.
- *How do you know there's no lookahead?* Three tests: the next-open fill test, the features-don't-change-when-the-future-changes test, and the walk-forward gap test.
- *What would you change for real money?* Use order-book data and funding rates, model realistic slippage per order size, size positions by risk, and paper-trade before going live.
