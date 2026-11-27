# Indicators

Coin Buddy computes three classic technical indicators in plain pandas (`coin_buddy/indicators.py`), so every formula is visible. A test checks the results against the open-source `ta` library.

All indicators use **closing prices** \(C_t\). Window sizes come from the [`indicators` config](../getting-started/configuration.md#indicators).

## RSI: Relative Strength Index

**What it measures:** how strong recent gains are compared with recent losses, on a 0–100 scale. Traders read **above 70 as overbought** (rose too far, too fast) and **below 30 as oversold**.

**Formula** (Wilder's smoothing, window \(n = 14\)):

\[
\Delta_t = C_t - C_{t-1}, \qquad
G_t = \max(\Delta_t, 0), \qquad
L_t = \max(-\Delta_t, 0)
\]

\[
\overline{G}_t = \overline{G}_{t-1} + \tfrac{1}{n}\left(G_t - \overline{G}_{t-1}\right)
\quad\text{(same for } \overline{L}_t\text{)}
\]

\[
RS_t = \frac{\overline{G}_t}{\overline{L}_t}, \qquad RSI_t = 100 - \frac{100}{1 + RS_t}
\]

Wilder's smoothing is an exponential moving average with \(\alpha = 1/n\). Edge cases are handled explicitly: no losses at all gives RSI = 100, and no movement at all gives RSI = 50.

??? note "Why it differs slightly from `ta` at the start"
    The `ta` library treats the first price change (which doesn't exist) as 0 and averages it in. Coin Buddy treats it as missing. Because the smoothing forgets its starting point exponentially, the two agree to 6 significant digits after about 300 candles. `test_matches_reference_ta_library` checks exactly that.

## MACD: Moving Average Convergence Divergence

**What it measures:** momentum, as the gap between a fast and a slow exponential moving average.

\[
\text{EMA}^{(k)}_t = \text{EMA}^{(k)}_{t-1} + \tfrac{2}{k+1}\left(C_t - \text{EMA}^{(k)}_{t-1}\right)
\]

\[
\text{MACD}_t = \text{EMA}^{(12)}_t - \text{EMA}^{(26)}_t, \qquad
\text{Signal}_t = \text{EMA}^{(9)}\left(\text{MACD}\right)_t, \qquad
\text{Hist}_t = \text{MACD}_t - \text{Signal}_t
\]

- **MACD above its signal line** (histogram > 0): upward momentum.
- **MACD below its signal line** (histogram < 0): downward momentum.

In the dashboard's MACD pane, the bars are the histogram, the indigo line is MACD, and the amber line is the signal line.

## Bollinger Bands

**What they measure:** how far price has stretched from its recent average, in units of recent volatility.

\[
\text{Mid}_t = \frac{1}{20}\sum_{i=0}^{19} C_{t-i}, \qquad
\sigma_t = \sqrt{\frac{1}{20}\sum_{i=0}^{19} \left(C_{t-i} - \text{Mid}_t\right)^2}
\]

\[
\text{Upper}_t = \text{Mid}_t + 2\sigma_t, \qquad \text{Lower}_t = \text{Mid}_t - 2\sigma_t
\]

Coin Buddy also computes **%B**, which the ML model uses:

\[
\%B_t = \frac{C_t - \text{Lower}_t}{\text{Upper}_t - \text{Lower}_t}
\]

%B is 0 at the lower band, 0.5 at the middle and 1 at the upper band. It goes below 0 or above 1 when price breaks outside the bands.

## Warm-up

Every indicator needs history before it's defined: RSI 14 candles, Bollinger 20, MACD's signal line about 35. Until then the values are empty (`NaN`). Those rows never vote in the signal engine, and the chart simply starts the lines later. That's why `market.lookback_candles` defaults to 300.

## Columns produced

`add_indicators(df)` returns a copy of the candle table with these extra columns:

| Column | Meaning |
|---|---|
| `rsi` | RSI (0–100) |
| `macd`, `macd_signal`, `macd_hist` | MACD line, signal line, histogram |
| `bb_upper`, `bb_mid`, `bb_lower` | Bollinger Bands |
| `bb_pct_b` | %B |

!!! question "Do these indicators predict price?"
    On their own, not reliably. They're among the most-watched numbers in markets, so any edge they once had is largely priced in. Coin Buddy's backtests show this directly. They're still useful as a *description* of what price has been doing, and as inputs to the [ML model](machine-learning.md).
