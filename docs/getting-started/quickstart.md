# Quickstart tour

A 5-minute tour of everything Coin Buddy can do. It assumes you finished [Installation](installation.md) and your virtual environment is active.

## 1. Get a signal in the terminal

```console
$ coin-buddy snapshot

BTC/USDT on binance (1h)  candle closed 2026-11-26 18:00 UTC
  Price      60,480.01
  Sentiment  +0.252 from 50 posts (56% positive, 24% negative, model: vader)

Signal: HOLD  (buy votes 1, sell votes 1)
  RSI        -     RSI 51.6 (oversold < 30, overbought > 70)
  MACD       SELL  MACD 182.60 vs signal 253.15
  Bollinger  -     price 60,480.01 in band [60,358.97, 61,028.52]
  Sentiment  BUY   score +0.252 (buy > 0.2, sell < -0.2)
```

Each line is one **vote**. Here MACD says SELL and sentiment says BUY, so the votes tie and the result is HOLD. The [Signal engine](../concepts/signals.md) page explains the rules.

## 2. Open the dashboard

```bash
coin-buddy dashboard --open
```

Your browser opens at <http://127.0.0.1:8000>. Things to try:

- [x] Click **ETH** in the watchlist to switch markets.
- [x] Press ++slash++ and type `sol`, then ++enter++, to search.
- [x] Click **4H** to change the timeframe.
- [x] Hover the chart to read each candle's open, high, low and close.
- [x] Toggle **MACD** on, and switch to the line chart.
- [x] Click the ☆ next to a market name to add it to your watchlist.
- [x] Use the ☀/☾ button to switch theme.

Every part of the screen is explained in [Markets dashboard](../user-guide/dashboard.md).

## 3. Run a backtest

In the dashboard, open **Backtest**, keep the defaults (BTC/USDT, 1H, 1Y, Compare) and click **Run backtest**. In under a minute you'll see whether the strategies beat simply holding BTC.

The same backtest from the terminal, with an interactive HTML report:

```bash
coin-buddy backtest --days 365 --report
```

## 4. Train the ML model

```bash
coin-buddy train --days 730
```

This trains on two years of real hourly BTC/USDT history and saves `models/binance-BTC-USDT-1h.joblib`. The dashboard's **Model outlook** card now shows a probability for BTC/USDT 1H.

!!! note "One model per market"
    A model only predicts for the exchange, symbol and timeframe it was trained on. To get a model for ETH on 4-hour candles:
    `coin-buddy train --symbol ETH/USDT --timeframe 4h`

## 5. Keep watching

```bash
coin-buddy watch --interval 300
```

This checks every 5 minutes, saves each signal to the local database, and plays a sound when the signal changes to BUY or SELL. Leave it running for a few weeks and you'll have your own sentiment history to backtest. See [Alerts](../user-guide/alerts.md) for Discord notifications.

## Where next?

- Change markets, thresholds or costs: [Configuration](configuration.md)
- Understand the numbers: [How it works](../concepts/indicators.md)
- Understand the code: [Architecture overview](../architecture/overview.md)
