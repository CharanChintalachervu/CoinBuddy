# Deployment

Coin Buddy is designed to run on your own computer. These options let you run it elsewhere, all with free tiers.

## Docker

```bash
docker build -t coin-buddy .
docker run -p 8000:8000 coin-buddy
```

Open <http://localhost:8000>. What the image does:

- Based on `python:3.12-slim`.
- Installs dependencies in their own layer, so code changes rebuild quickly.
- Runs the app from `/app` with `python -m coin_buddy`, so it finds its config files and writes `data/` and `models/` next to them.
- Runs as a **non-root** user (`buddy`, UID 1000).
- Binds to `0.0.0.0:8000` inside the container.
- Has a `HEALTHCHECK` on `/api/health`.
- Excludes `.env`, `data/`, `models/`, tests and docs (see `.dockerignore`).
- **Uses `config.hosted.yaml`** (Coinbase with USD pairs, which works in the US) via the `COIN_BUDDY_CONFIG` environment variable. To use your normal settings instead:

    ```bash
    docker run -p 8000:8000 -e COIN_BUDDY_CONFIG=/app/config.yaml coin-buddy
    ```

CI builds the image and checks that the running container serves the dashboard and API on every push (the `docker` job in `.github/workflows/ci.yml`).

**Keep history and models across restarts** with volumes:

```bash
docker run -p 8000:8000 \
  -v "$(pwd)/data:/app/data" -v "$(pwd)/models:/app/models" \
  --env-file .env coin-buddy
```

!!! note "Docker Desktop licensing"
    Docker Engine is free and open-source. Docker Desktop is free for personal use, education and small businesses; larger companies need a paid plan. On Linux you can use Docker Engine directly, and Podman is a free drop-in alternative.

## Free hosting on Render

The live demo runs on a free **Render** web service, built straight from the repository's `Dockerfile`. Signing up with GitHub is free.

| Free plan | |
|---|---|
| Resources | 512 MB RAM, 0.1 CPU |
| Sleep | Spins down after **15 minutes** without visitors; the next visit wakes it in about a minute |
| Hours | 750 free instance hours per month, enough for one service running all month |
| Disk | Not persistent: history and models reset on every restart or deploy |

### One-time setup

The repository contains a **Blueprint**, `render.yaml`, which tells Render exactly how to run the app: Docker, free plan, health check on `/api/health`, port 8000.

1. Sign up at <https://render.com> with **GitHub**.
2. In the Render dashboard, click **New → Blueprint**.
3. Connect your GitHub account if asked, then pick the **CoinBuddy** repository.
4. Render shows the `coin-buddy` web service from `render.yaml`. Leave the two optional Reddit values empty (or fill them in to enable sentiment), then click **Apply** / **Deploy Blueprint**.
5. The first build takes a few minutes. The app is then live at `https://coin-buddy-xxxx.onrender.com` (the exact URL is shown on the service page).

From then on, every push to `main` redeploys automatically (`autoDeploy: true`). CI also builds and runs the same Docker image on every push, so a broken image is caught on GitHub too.

### How the hosted copy differs

| | Your computer (`config.yaml`) | Hosted (`config.hosted.yaml`) |
|---|---|---|
| Exchange | Binance, USDT pairs | **Coinbase**, USD pairs. Render's free region here is in the US, where Binance is blocked. Kraken works there too, but only serves about a month of candles, too little for backtests. |
| Timeframes | 1m · 5m · 15m · 1H · 4H · 1D | 1m · 5m · 15m · 1H · 1D (Coinbase has no 4-hour candles; the app only offers what the exchange supports) |
| Backtests | Up to 1,500 days, unlimited concurrency | Up to **365 days** (`web.max_backtest_days`), **one at a time**. With 0.1 CPU and Coinbase's 300 candles per request, a first ML backtest can take several minutes; results are then cached for an hour. |
| Sentiment | Your Reddit credentials if set | Reddit often blocks anonymous requests from cloud servers, so sentiment may abstain. Add `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` in the Render service's **Environment** settings to enable it. |
| History & models | Kept in `data/`, `models/` | Reset on every restart (no persistent disk on the free plan) |

### Other free hosts

Any host that runs a Docker container works with the same image. Free tiers change often; as of late 2026, Hugging Face Docker Spaces and Koyeb require a paid plan or a card, and Google Cloud Run needs a card. If a host shows apps inside its own page (an iframe), add it to `web.frame_ancestors` in `config.hosted.yaml`.

!!! danger "There is no login"
    A public deployment is visible to anyone with the URL. That's fine for this read-only demo (it never trades and stores no personal data), but don't put secrets in `config.yaml`. Use the host's secret settings for anything from `.env`.

## Documentation site (GitHub Pages)

These docs are built with [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

**Preview locally:**

```bash
pip install -e ".[docs]"
mkdocs serve                # http://127.0.0.1:8000, reloads on save
```

(Stop the dashboard first, or use `mkdocs serve -a 127.0.0.1:8001`, since both default to port 8000.)

**Build the static site:**

```bash
mkdocs build                # outputs to site/ (git-ignored)
```

**Publish automatically.** `.github/workflows/docs.yml` builds the site and deploys it to GitHub Pages on every push to `main`. Turn it on once:

1. Push the repository to GitHub.
2. Go to **Settings → Pages**, and under **Build and deployment** choose **Source: GitHub Actions**.
3. Push any commit (or re-run the workflow). The site appears at `https://<username>.github.io/<repo>/`.
4. Set `site_url` and `repo_url` in `mkdocs.yml` to those URLs.

GitHub Pages is free for public repositories.
