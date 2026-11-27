# Publishing safely

Before pushing Coin Buddy to a public GitHub repository, make sure nothing private goes with it. Once something is pushed publicly, assume it has been copied: bots scan GitHub for keys within minutes.

## What's already protected

`.gitignore` excludes:

| Path | Why |
|---|---|
| `.env` | Reddit credentials, Discord webhook |
| `data/`, `*.db` | Your personal signal history |
| `models/` | Trained models (large, and pickles shouldn't be shared) |
| `reports/` | Generated reports |
| `.venv/`, `venv/`, `build/`, `dist/`, `site/` | Environments and build output |
| `.vscode/`, `.idea/` | Editor settings, which can contain local paths |

## Pre-push checklist

- [ ] `git status` shows no `.env`, `.db`, `.joblib` or editor folders.
- [ ] No secrets in tracked files. Search for them:

    ```bash
    git grep -n -I -E "(api[_-]?key|secret|token|password|webhook)\s*[:=]\s*['\"]?[A-Za-z0-9/_+-]{12,}" -- . ':!docs'
    ```

- [ ] No personal paths or emails in tracked files:

    ```bash
    git grep -n -I -E "C:\\\\Users\\\\|/home/[a-z]+|@gmail\.com"
    ```

- [ ] `archive/v1/` contains no hard-coded keys (v1 once did; they were removed).
- [ ] Screenshots in `docs/images/` show only public market data.
- [ ] Any key that was **ever** committed, even in an old commit or a deleted file, has been **revoked and replaced**. Deleting it in a new commit doesn't remove it from history.

!!! tip "Scan automatically"
    [gitleaks](https://github.com/gitleaks/gitleaks) (MIT) scans a repository and its full history for secrets:

    ```bash
    gitleaks detect --source . -v
    ```

    GitHub also offers free **secret scanning and push protection** for public repositories: **Settings → Code security**.

## If a secret leaks

1. **Revoke it immediately** at the provider (Binance API management, Reddit app settings, Discord webhook settings).
2. Create a new one and put it only in `.env`.
3. Rewriting git history (e.g. with `git filter-repo`) removes it from the repository, but assume it was already copied. Revoking is what actually protects you.

## Licensing

Coin Buddy is **© 2025–2026 Charan Chintalachervu. All rights reserved.** The terms are in the `LICENSE` file at the project root. The copyright notice appears in:

- the `LICENSE` file and `pyproject.toml` (`license` and `authors`)
- a header line at the top of every source file in `coin_buddy/`, `tests/` and the web frontend
- the dashboard footer, `coin-buddy --version` and `coin-buddy --help`
- the README and the footer of this documentation site

The earlier version in `archive/v1/` is kept unchanged for historical reference.

Before publishing, keep in mind that a **public** repository lets anyone read the code, even though the license forbids copying it. To sell the project as a kit, use a **private** repository, or publish only the documentation site.

Third-party components keep their own licenses: TradingView Lightweight Charts (Apache 2.0) requires its attribution, which the chart's logo and the footer link provide.
