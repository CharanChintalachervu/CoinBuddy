# Installation

Coin Buddy runs on Windows, macOS and Linux. You need nothing except Python and an internet connection: no exchange account, no API keys.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or newer | Tested on 3.10 and 3.12. Check with `python --version`. |
| Internet | Any | Market data comes from public exchange endpoints. |
| Browser | Any modern browser | For the web dashboard (Chrome, Edge, Firefox, Safari). |
| Disk | ~400 MB | For the virtual environment. The optional FinBERT model adds ~1.5 GB. |

## 1. Get the code

=== "Git"

    ```bash
    git clone https://github.com/<your-username>/coin-buddy.git
    cd coin-buddy
    ```

=== "Zip download"

    Download the project zip, extract it, and open a terminal in the extracted folder.

## 2. Create a virtual environment

A virtual environment keeps Coin Buddy's libraries separate from anything else on your machine.

=== "Windows"

    ```powershell
    python -m venv .venv
    .venv\Scripts\activate
    ```

=== "macOS / Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

Your prompt now starts with `(.venv)`. Run the activate command again whenever you open a new terminal.

## 3. Install Coin Buddy

```bash
pip install -e ".[dev]"
```

This installs the app plus the test tools, and registers the `coin-buddy` command. The `-e` (editable) flag means code changes take effect without reinstalling.

??? info "Optional extras"
    | Extra | Install | What it adds |
    |---|---|---|
    | `reddit` | `pip install -e ".[reddit]"` | Official Reddit API client (praw), for higher rate limits. Needs credentials. |
    | `finbert` | `pip install -e ".[finbert]"` | FinBERT, a stronger finance-specific sentiment model (~1.5 GB, runs on CPU). |
    | `docs` | `pip install -e ".[docs]"` | Tools to build this documentation site locally. |

    Combine them: `pip install -e ".[dev,docs]"`.

??? tip "Exact versions"
    `requirements.txt` pins the exact versions the project was tested with. Use `pip install -r requirements.txt` if you want an identical environment.

## 4. Check it works

```bash
coin-buddy --version
coin-buddy snapshot
```

You should see the latest BTC/USDT price, a sentiment score, and a signal with its reasoning. If you do, you're ready: continue with the [Quickstart tour](quickstart.md).

!!! warning "In the United States?"
    Binance blocks US IP addresses, so the default exchange will fail with a "451" or "restricted location" error. Use Coinbase instead (Kraken also works for live prices, but only serves about a month of candles, too little for backtests):

    ```bash
    coin-buddy snapshot --exchange coinbase --symbol BTC/USD
    ```

    To make it permanent, set `exchange: coinbase` and `symbol: BTC/USD` in `config.yaml` (see [Configuration](configuration.md)). Also replace the `web.watchlist` entries with `/USD` pairs.

## 5. (Optional) Run the tests

```bash
pytest
```

All 61 tests run offline in about 25 seconds. See [Testing](../development/testing.md) for what they cover.

## Uninstalling

Delete the project folder. Everything, including the virtual environment, the SQLite history in `data/` and trained models in `models/`, lives inside it.
