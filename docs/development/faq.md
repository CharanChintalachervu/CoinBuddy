# Troubleshooting & FAQ

## Errors

??? failure "`Service unavailable from a restricted location` / HTTP 451 from Binance"
    Binance blocks the US (and some other regions). Switch exchange:

    ```bash
    coin-buddy snapshot --exchange kraken --symbol BTC/USD
    ```

    Make it permanent in `config.yaml` (`market.exchange`, `market.symbol`, and `/USD` pairs in `web.watchlist`).

??? failure "`That symbol isn't listed on this exchange.` (404)"
    Symbols differ between exchanges: Binance uses `BTC/USDT`, while Kraken and Coinbase use `BTC/USD`. Start typing in the dashboard search to see valid symbols, or check `GET /api/markets`.

??? failure "Sentiment shows \"Reddit is unreachable\""
    Reddit's public feed rate-limits or sometimes blocks anonymous requests. The app keeps working and sentiment simply abstains. For reliable access, create a free Reddit "script" app at <https://www.reddit.com/prefs/apps>, put its credentials in `.env`, and run `pip install -e ".[reddit]"`.

??? failure "`[Errno 10048]` / `address already in use` when starting the dashboard"
    Something already uses port 8000 (often another dashboard or `mkdocs serve`). Use another port: `coin-buddy dashboard --port 8001`.

??? failure "The dashboard says \"The chart library didn't load\""
    The chart library loads from cdn.jsdelivr.net. Check your internet connection, and whether an ad blocker or corporate proxy blocks that domain.

??? failure "Dashboard status says Delayed or Offline"
    The server can't reach the exchange, or the server stopped. Check the terminal running `coin-buddy dashboard`. Network errors are retried automatically.

??? failure "pytest crashes with `INTERNALERROR ... '_str_cache'`"
    A bug in pytest 9.x on some Python 3.10 builds. The project pins `pytest>=8,<9`; reinstall with `pip install -e ".[dev]"`.

??? failure "`Unknown MarketConfig keys in config: [...]`"
    There's a typo in `config.yaml`. The message names the key. See [Configuration](../getting-started/configuration.md) for valid keys.

## Questions

??? question "Does Coin Buddy trade for me?"
    No. It has no trading code at all, and needs no exchange keys. It's an analysis and learning tool.

??? question "Why does the ML card say \"No model for …\"?"
    Models are tied to the exchange, symbol and timeframe they were trained on. Run the command shown in the card, for example `coin-buddy train --symbol ETH/USDT --timeframe 4h`. [Why one model per market →](../concepts/machine-learning.md#one-model-per-market)

??? question "Why doesn't the backtest include sentiment?"
    Historical Reddit data isn't freely available, so sentiment can't be replayed for past years. Run `coin-buddy watch` to build your own history, then follow [Backtest with your sentiment history](extending.md#backtest-with-your-sentiment-history).

??? question "Why is the signal different from the arrows on the chart?"
    The signal card shows the **current vote**. Arrows mark **position changes**: a BUY arrow appears once, when the strategy would enter, even if BUY votes continue for many candles. The card can also show BUY while the last arrow is BUY, because you'd already be in.

??? question "Why does the latest candle keep changing, while the signal doesn't?"
    The chart shows the forming candle so it looks live. Signals use only **closed** candles, because indicators on a half-finished candle change until it closes.

??? question "How much data does the dashboard use?"
    Roughly one small JSON request every 10 seconds per open tab, and nothing while the tab is hidden. The server caches responses, so multiple tabs don't multiply exchange requests.

??? question "Can I run it 24/7?"
    Yes, `coin-buddy watch` or the dashboard can run indefinitely. Use Docker with volumes (see [Deployment](deployment.md)) so history survives restarts.

??? question "Is any of my data sent anywhere?"
    Only requests for public data: market data to the exchange, and subreddit listings to Reddit. Your preferences stay in your browser, and your history stays in `data/coin_buddy.db`. The docs site and the dashboard load fonts from Google Fonts and the chart library from jsDelivr.
