# Signal engine

The signal engine (`coin_buddy/signals.py`) turns indicator values into a single **BUY**, **SELL** or **HOLD**, with a reason for every part of the decision.

## Step 1: each indicator votes

Each of the four inputs casts one vote: **+1** (BUY), **−1** (SELL) or **0** (abstain).

| Indicator | Votes BUY (+1) when | Votes SELL (−1) when | Otherwise |
|---|---|---|---|
| **RSI** | RSI < `rsi_oversold` (30) | RSI > `rsi_overbought` (70) | abstains |
| **MACD** | MACD > signal line | MACD < signal line | abstains (exactly equal) |
| **Bollinger** | close ≤ lower band | close ≥ upper band | abstains |
| **Sentiment** | score > `sentiment_buy` (+0.2) | score < `sentiment_sell` (−0.2) | abstains |

!!! note "Missing data abstains"
    If Reddit can't be reached, sentiment **abstains**. It isn't counted as neutral evidence, and the app keeps working. Candles still warming up (indicators not yet defined) never vote.

## Step 2: decide

\[
\text{action} =
\begin{cases}
\text{BUY} & \text{if } b \ge m \text{ and } b > s \\
\text{SELL} & \text{if } s \ge m \text{ and } s > b \\
\text{HOLD} & \text{otherwise}
\end{cases}
\]

where \(b\) = BUY votes, \(s\) = SELL votes, and \(m\) = `min_votes` (default 2).

In words: **a side needs at least two votes and a strict majority over the other side.** Ties are always HOLD.

## Worked examples

| RSI | MACD | Bollinger | Sentiment | BUY votes | SELL votes | Result |
|---|---|---|---|---|---|---|
| 25 (BUY) | above (BUY) | inside (–) | +0.1 (–) | 2 | 0 | <span class="tag-buy">BUY</span> |
| 52 (–) | below (SELL) | inside (–) | +0.25 (BUY) | 1 | 1 | <span class="tag-hold">HOLD</span>, tie |
| 75 (SELL) | below (SELL) | above upper (SELL) | +0.3 (BUY) | 1 | 3 | <span class="tag-sell">SELL</span> |
| 50 (–) | above (BUY) | inside (–) | unavailable (–) | 1 | 0 | <span class="tag-hold">HOLD</span>, only one vote |
| 28 (BUY) | below (SELL) | below lower (BUY) | −0.3 (SELL) | 2 | 2 | <span class="tag-hold">HOLD</span>, tie |

## Two implementations, one behaviour

The engine exists twice, for speed:

| Function | Used by | Works on |
|---|---|---|
| `evaluate(row, sentiment, cfg)` | Live signal (CLI, dashboard) | One candle. Returns a `Signal` with every `Vote` and its human-readable reason. |
| `vote_frame(df, cfg)` / `action_series(df, cfg)` | Backtests, chart markers | Every candle at once, vectorised with NumPy. |

`test_vectorised_matches_single_row` checks that both give identical answers on hundreds of candles, so what you see live is exactly what was backtested.

## From actions to positions

A signal is a *view*, not a trade. To trade it, the backtester and the chart convert actions into a **target position**:

- **BUY:** be fully invested.
- **SELL:** be fully in cash.
- **HOLD:** keep whatever you had.

So a long run of BUY signals is **one** entry. The ▲/▼ arrows on the chart mark the moments the target position changes. See [Backtesting](backtesting.md).

## Why a vote and not a weighted score?

A vote is easy to explain (every decision can be read off the vote list), hard to overfit (there are no weights to tune), and gracefully handles missing inputs (abstain). Its weakness is that it treats a barely-oversold RSI of 29.9 the same as an extreme 10. The [ML model](machine-learning.md) is the contrasting approach: it uses the actual values but is harder to explain.
