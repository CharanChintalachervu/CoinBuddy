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
- Runs as a **non-root** user (`buddy`).
- Binds to `0.0.0.0:8000` inside the container.
- Has a `HEALTHCHECK` on `/api/health`.
- Excludes `.env`, `data/`, `models/`, tests and docs (see `.dockerignore`).

**Keep history and models across restarts** with volumes:

```bash
docker run -p 8000:8000 \
  -v "$(pwd)/data:/app/data" -v "$(pwd)/models:/app/models" \
  --env-file .env coin-buddy
```

!!! note "Docker Desktop licensing"
    Docker Engine is free and open-source. Docker Desktop is free for personal use, education and small businesses; larger companies need a paid plan. On Linux you can use Docker Engine directly, and Podman is a free drop-in alternative.

## Free hosting

Any host that runs a Docker container works. Two with free tiers:

| Host | Notes |
|---|---|
| **Hugging Face Spaces** (Docker Space) | Free CPU instances. Spaces expect port **7860** by default: set `app_port: 8000` in the Space's README metadata, or change the port in the Dockerfile `CMD`. |
| **Render** (free web service) | Free instances sleep after inactivity, so the first visit after a while is slow. |

!!! warning "US-based hosts and Binance"
    Many free hosts run in the US, where Binance blocks requests. Set `exchange: kraken` with USD pairs in `config.yaml` before deploying.

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
