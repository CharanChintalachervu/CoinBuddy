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

## Free hosting on Hugging Face Spaces

The live demo runs on a free **Hugging Face Docker Space** (2 vCPU, 16 GB RAM, no credit card). Free Spaces go to sleep after 48 hours without visitors and wake up on the next visit, which takes about a minute.

Deployment is automatic: `.github/workflows/deploy-hf.yml` runs after **CI passes** on `main`. It packages the server code, adds the Space's settings header (`sdk: docker`, `app_port: 8000`), and pushes it to your Space.

### One-time setup

1. **Create the Space.** At <https://huggingface.co/new-space>, give it a name (e.g. `coin-buddy`), choose **Docker** as the SDK with the **Blank** template, **CPU basic (free)** hardware, and **Public** visibility. Click **Create Space**.
2. **Create a token.** Go to <https://huggingface.co/settings/tokens>, then **Create new token**, type **Write**, and copy it.
3. **Give GitHub the token and the Space name.** In the GitHub repo, go to **Settings → Secrets and variables → Actions**:
    - **Secrets** tab, **New repository secret**: name `HF_TOKEN`, value = the token.
    - **Variables** tab, **New repository variable**: name `HF_SPACE`, value = `<your-hf-username>/<space-name>`, e.g. `charanchintalachervu/coin-buddy`.
4. **Deploy.** Go to **Actions → Deploy to Hugging Face → Run workflow**. From then on, every push that passes CI redeploys automatically.

The app is then at `https://huggingface.co/spaces/<user>/<space>`, with a direct full-page URL at `https://<user>-<space>.hf.space`.

### How the hosted copy differs

| | Your computer (`config.yaml`) | Hosted (`config.hosted.yaml`) |
|---|---|---|
| Exchange | Binance, USDT pairs | **Coinbase**, USD pairs. Free hosts mostly run in the US, where Binance is blocked. Kraken works there too, but only serves about a month of candles, which is too little for backtests. |
| Timeframes | 1m · 5m · 15m · 1H · 4H · 1D | 1m · 5m · 15m · 1H · 1D (Coinbase has no 4-hour candles; the app only offers what the exchange supports) |
| Framing | Denied | Allowed for `https://huggingface.co` only, so the Space page can show the app (`web.frame_ancestors`) |
| Backtests | Unlimited | One at a time; others get a "try again in a minute" message. Coinbase serves 300 candles per request, so long backtests take a few minutes the first time (then cached for an hour). |
| Sentiment | Your Reddit credentials if set | Reddit often blocks anonymous requests from cloud servers, so sentiment may abstain. Add `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` as **Space secrets** to enable it. |
| History & models | Kept in `data/`, `models/` | Reset whenever the Space restarts (free Spaces have no persistent disk) |

### Other free hosts

Any Docker host works with the same image, e.g. a free **Render** web service (it sleeps after 15 minutes idle, so first visits are slow). Remove `frame_ancestors` from `config.hosted.yaml` if the host doesn't embed apps in a frame.

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
