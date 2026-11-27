# Command line

Everything the dashboard does is also available from the terminal through the `coin-buddy` command. `python -m coin_buddy` works too.

```text
coin-buddy [--config FILE] [-v] [--version] <command> [options]
```

| Global option | Meaning |
|---|---|
| `--config FILE` | Use a different YAML config instead of `config.yaml`. |
| `-v`, `--verbose` | Show debug logging (requests, retries, cache misses). |
| `--version` | Print the version. |

**Market options.** `snapshot`, `watch`, `backtest` and `train` accept `--exchange`, `--symbol` and `--timeframe`, which override `config.yaml` for that run.

---

## `snapshot`

Prints the current signal with a full explanation, and saves it to history.

```console
$ coin-buddy snapshot --symbol ETH/USDT --timeframe 4h

ETH/USDT on binance (4h)  candle closed 2026-11-26 16:00 UTC
  Price      1,692.54
  Sentiment  +0.255 from 50 posts (58% positive, 22% negative, model: vader)

Signal: BUY  (buy votes 2, sell votes 0)
  RSI        -     RSI 49.6 (oversold < 30, overbought > 70)
  MACD       BUY   MACD -6.90 vs signal -11.32
  Bollinger  -     price 1,692.54 in band [1,629.66, 1,752.42]
  Sentiment  BUY   score +0.255 (buy > 0.2, sell < -0.2)
```

If a model exists for this market, a line like `ML model   P(up over next 12 candles) = 42.2%` appears.

## `watch`

Re-checks on an interval, saves each result, and alerts when the signal changes.

```bash
coin-buddy watch --interval 300
```

| Option | Default | Meaning |
|---|---|---|
| `--interval` | `300` | Seconds between checks. |

- It alerts on **changes** only. Seeing BUY twice in a row alerts once.
- Only BUY and SELL alert; a change to HOLD is printed but silent.
- Network errors are logged and the loop keeps going.
- Stop with ++ctrl+c++.

See [Alerts](alerts.md) for Discord notifications.

## `backtest`

Tests strategies on real history with fees and slippage.

```bash
coin-buddy backtest --days 730 --strategy both --report
```

| Option | Default | Meaning |
|---|---|---|
| `--days` | `365` | History to replay. |
| `--strategy` | `both` | `rules`, `ml`, or `both`. |
| `--report [PATH]` | off | Write an interactive HTML report. Without a path: `reports/backtest.html`. |

Example output (abridged):

```text
[rules]  2024-11-26 to 2026-11-26
  Strategy return (after costs)     -36.99%
  Strategy return (before costs)    -23.18%
  Buy & hold return                 -34.29%
  Sharpe (strategy / buy & hold)    -0.51 / -0.25
  Max drawdown (strategy / B&H)     -53.40% / -55.72%
  Time in market                    52.4%
  Round trips                       66
  ...
ML walk-forward: 62 folds, out-of-sample accuracy 58.0% vs naive baseline 61.9% (-3.9%)
```

Every metric is defined in [Backtesting](../concepts/backtesting.md#metrics).

## `train`

Trains the ML model on real history and saves it for the market you name.

```bash
coin-buddy train --days 730                                  # BTC/USDT 1h (config defaults)
coin-buddy train --symbol ETH/USDT --timeframe 4h --days 1000
```

| Option | Default | Meaning |
|---|---|---|
| `--days` | `730` | History to train on. |

The model is saved to `models/<exchange>-<symbol>-<timeframe>.joblib`, for example `models/binance-ETH-USDT-4h.joblib`. Training always uses **all** the history. To measure how good the model is, run `coin-buddy backtest --strategy ml`, which trains and tests walk-forward instead.

## `dashboard`

Starts the web app.

```bash
coin-buddy dashboard --open
coin-buddy dashboard --host 0.0.0.0 --port 9000
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `web.host` (`127.0.0.1`) | `0.0.0.0` makes it reachable from other devices on your network. |
| `--port` | `web.port` (`8000`) | Port to listen on. |
| `--open` | off | Open the dashboard in your default browser. |

Stop with ++ctrl+c++. Interactive API docs are at `/api/docs` while it runs.

## Exit codes

`0` on success. Errors such as an unknown exchange or symbol print a message and exit with a non-zero code.
