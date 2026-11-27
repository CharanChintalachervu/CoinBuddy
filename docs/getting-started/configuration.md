# Configuration

Coin Buddy reads two files from the project folder:

| File | Holds | Committed to git? |
|---|---|---|
| `config.yaml` | Every tunable setting: markets, thresholds, costs, ML, web app | Yes |
| `.env` | Optional secrets (Reddit credentials, Discord webhook) | **Never** (it's in `.gitignore`) |

You only need to edit `config.yaml` when you want different behaviour. Every key has a sensible default, so you can delete any line and the default applies.

!!! tip "Typos fail loudly"
    Unknown keys raise an error at startup. For example, `symbl: ETH/USDT` stops with `Unknown MarketConfig keys in config: ['symbl']` instead of being silently ignored.

## Command-line overrides

Market settings can be overridden per command without editing the file:

```bash
coin-buddy snapshot --exchange kraken --symbol BTC/USD --timeframe 4h
coin-buddy --config my-config.yaml backtest
```

## `market`

| Key | Default | Meaning |
|---|---|---|
| `exchange` | `binance` | Any [ccxt exchange id](https://docs.ccxt.com/#/README?id=supported-cryptocurrency-exchanges): `binance`, `kraken`, `coinbase`, `bybit`, `okx`… |
| `symbol` | `BTC/USDT` | Market in ccxt's unified `BASE/QUOTE` format. Use `BTC/USD` on Kraken or Coinbase. |
| `timeframe` | `1h` | Candle size: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`. |
| `lookback_candles` | `300` | Candles fetched to compute live indicators. Must exceed MACD's warm-up (slow + signal = 35). |

## `indicators`

| Key | Default | Meaning |
|---|---|---|
| `rsi_window` | `14` | RSI lookback (Wilder's standard). |
| `macd_fast` / `macd_slow` / `macd_signal` | `12` / `26` / `9` | MACD EMA spans. |
| `bb_window` | `20` | Bollinger Band moving-average window. |
| `bb_std` | `2.0` | Band width in standard deviations. |

See [Indicators](../concepts/indicators.md) for the formulas.

## `strategy`

| Key | Default | Meaning |
|---|---|---|
| `rsi_oversold` | `30` | RSI below this votes BUY. |
| `rsi_overbought` | `70` | RSI above this votes SELL. |
| `sentiment_buy` | `0.2` | Average sentiment above this votes BUY. |
| `sentiment_sell` | `-0.2` | Average sentiment below this votes SELL. |
| `min_votes` | `2` | A side needs at least this many votes **and** a strict majority. |

See [Signal engine](../concepts/signals.md).

## `sentiment`

| Key | Default | Meaning |
|---|---|---|
| `source` | `reddit` | Only Reddit is supported today. |
| `subreddits` | `[cryptocurrency, bitcoin]` | Subreddits to read. |
| `posts_per_subreddit` | `25` | Newest posts read from each (max 100). |
| `include_body` | `true` | Score the title **and** the first 1,000 characters of the post text. |
| `model` | `vader` | `vader` (fast, built in) or `finbert` (needs the `finbert` extra). |

## `backtest`

| Key | Default | Meaning |
|---|---|---|
| `fee_rate` | `0.001` | Fee per side (0.1% = Binance spot taker). |
| `slippage_rate` | `0.0005` | Assumed execution cost per side (0.05%). |
| `initial_capital` | `10000` | Starting portfolio value for equity curves. |

## `ml`

| Key | Default | Meaning |
|---|---|---|
| `horizon_candles` | `12` | The model predicts the return this many candles ahead. |
| `train_candles` | `2000` | Size of each walk-forward training window. |
| `test_candles` | `250` | Size of each walk-forward test window. |
| `probability_threshold` | `0.55` | Go long at P(up) ≥ 0.55, go flat at P(up) < 0.45, otherwise keep the position. |
| `model_path` | `models/{exchange}-{symbol}-{timeframe}.joblib` | Where models are saved. The placeholders give each market its own file. |

See [Machine learning](../concepts/machine-learning.md).

## `storage`

| Key | Default | Meaning |
|---|---|---|
| `database` | `data/coin_buddy.db` | SQLite file for signal and sentiment history. |

## `alerts`

| Key | Default | Meaning |
|---|---|---|
| `sound` | `true` | Play a sound on BUY/SELL during `coin-buddy watch`. |
| `discord_webhook_env` | `DISCORD_WEBHOOK_URL` | Name of the `.env` variable holding a Discord webhook URL. |

## `web`

| Key | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | Interface the dashboard binds to. `0.0.0.0` lets other devices on your network connect (Docker uses this). |
| `port` | `8000` | Dashboard port. |
| `watchlist` | BTC, ETH, SOL, BNB, XRP, DOGE (USDT pairs) | Default watchlist for new visitors. Each visitor can star more; their list is saved in their own browser. |
| `chart_candles` | `500` | Candles drawn on the chart. |
| `refresh_seconds` | `10` | How often the browser polls for live prices and candles. |
| `sentiment_cache_seconds` | `300` | Reddit is rate-limited, so sentiment is reused for this long. |

## `.env` (optional secrets)

Copy `.env.example` to `.env` and fill in only what you need:

```ini
# Official Reddit API (otherwise the public JSON feed is used)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=coin-buddy/2.0 by your_reddit_username

# Discord alerts
DISCORD_WEBHOOK_URL=
```

!!! danger "Never commit `.env`"
    It's already in `.gitignore`. If a secret ever gets committed, treat it as leaked: revoke it and create a new one. Deleting the file in a later commit doesn't remove it from git history. See [Publishing safely](../development/publishing.md).
