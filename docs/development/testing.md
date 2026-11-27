# Testing

```bash
pytest                                 # 61 tests, ~25 s, fully offline
ruff check . && ruff format --check .  # lint + formatting
```

No test touches the network. Exchanges are replaced by a `FakeExchange`, prices by synthetic random walks, and Reddit by fake responses, so tests are fast, free and give the same result every time.

## What's covered

| File | Covers |
|---|---|
| `test_indicators.py` | RSI bounds and edge cases, MACD identity, Bollinger symmetry, no input mutation, **agreement with the `ta` library** |
| `test_signals.py` | Every vote rule, ties are HOLD, missing sentiment abstains, explanations, **vectorised = single-row**, warm-up rows never vote |
| `test_backtest.py` | Always-long tracks the asset, never-in-market returns 0, exact per-side costs, **next-open fills (no lookahead)**, position state, round-trip accounting |
| `test_ml.py` | Labels leave the future empty, label definition, **features never use the future**, walk-forward only predicts out of sample, save/load round trip, **one model per market** |
| `test_sentiment.py` | Crypto slang is understood, aggregation, body toggle, unknown model rejected, public-JSON parsing, **network failure degrades to neutral** |
| `test_market_storage_config.py` | Candle pagination, **forming candle dropped**, config typos rejected, partial overrides, SQLite round trip with de-duplication, per-market model paths |
| `test_web.py` | Every API endpoint, security headers, spot-only market list, markers only on closed candles, signals saved to history, validation errors (400/422), no `NaN` in JSON |

## The tests that guard against lookahead

Lookahead bias is the most common way backtests lie, so three tests attack it from different angles:

1. **`test_no_lookahead_signal_fills_next_open`**: a target set at candle 10 isn't held during candle 10 and fills at candle 11's open.
2. **`test_features_have_no_lookahead`**: doubling the last close changes no feature at any earlier time.
3. **`test_walk_forward_only_predicts_out_of_sample`**: the first prediction comes after a full training window plus the gap.

## Fixtures

Defined in `tests/conftest.py`:

| Fixture / helper | Purpose |
|---|---|
| `make_ohlcv(n, seed, drift)` | Synthetic hourly candles from a geometric random walk |
| `ohlcv` | 600 synthetic candles |
| `FakeExchange` | Implements the ccxt methods Coin Buddy uses (`fetch_ohlcv`, `parse_timeframe`, `milliseconds`), serving pages of a DataFrame. You control "now" to test the forming candle. |

`tests/test_web.py` extends it with `load_markets` and `fetch_tickers`, and injects it via `create_app(exchange_factory=...)`.

## Continuous integration

`.github/workflows/ci.yml` runs lint, formatting and the full test suite on **Python 3.10 and 3.12** for every push to `main` and every pull request. GitHub Actions is free for public repositories.

## Manual UI checks

The UI was verified in a real browser (Microsoft Edge via [Playwright](https://playwright.dev/python/)): switching symbols, timeframes, chart types and indicators, the theme toggle, search, running backtests, the History page and the phone layout. The checks also confirmed there were no console errors, no Content-Security-Policy violations and no horizontal overflow on mobile.

To repeat such checks:

```bash
pip install playwright        # uses your installed Edge or Chrome, no browser download needed
```

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")  # or channel="chrome"
    page = browser.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto("http://127.0.0.1:8000")
    page.wait_for_selector(".verdict-pill")
    page.screenshot(path="markets.png")
    print(errors or "no console errors")
```

## Writing a new test

- Keep it offline: use `make_ohlcv` and `FakeExchange`.
- Test **behaviour**, not implementation: "a tie is HOLD", not "this list has 4 items".
- For anything touching time or future data, add a lookahead check.
