# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Social sentiment: fetch Reddit posts and score them with VADER (default) or FinBERT (optional)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import requests

from coin_buddy.config import SentimentConfig

log = logging.getLogger(__name__)

USER_AGENT = "coin-buddy/2.0 (open-source crypto sentiment tool)"

# VADER is tuned for social media but doesn't know crypto slang. These additions use
# VADER's own scale (-4 very negative ... +4 very positive).
CRYPTO_LEXICON: dict[str, float] = {
    "moon": 2.5,
    "mooning": 2.8,
    "bullish": 2.5,
    "bull": 1.5,
    "rally": 2.0,
    "breakout": 1.8,
    "pump": 1.2,
    "pumping": 1.5,
    "hodl": 1.5,
    "ath": 2.2,
    "wagmi": 2.0,
    "btfd": 1.5,
    "adoption": 1.5,
    "accumulate": 1.2,
    "accumulating": 1.2,
    "bearish": -2.5,
    "bear": -1.5,
    "dump": -2.0,
    "dumping": -2.3,
    "rekt": -3.0,
    "fud": -2.0,
    "scam": -3.0,
    "rug": -3.0,
    "rugpull": -3.5,
    "rugged": -3.0,
    "ngmi": -2.0,
    "crash": -3.0,
    "crashing": -3.0,
    "capitulation": -2.5,
    "liquidated": -2.5,
    "liquidation": -2.0,
    "hack": -3.0,
    "hacked": -3.2,
    "exploit": -2.5,
    "bagholder": -2.0,
    "dip": -0.8,
}


@dataclass(frozen=True)
class Post:
    id: str
    subreddit: str
    created_utc: float
    title: str
    text: str
    upvotes: int
    url: str = ""


@dataclass(frozen=True)
class SentimentResult:
    score: float  # mean compound score, -1 (very negative) .. +1 (very positive)
    n_posts: int
    positive_share: float  # fraction of posts scoring > +0.05
    negative_share: float  # fraction of posts scoring < -0.05

    @classmethod
    def empty(cls) -> SentimentResult:
        return cls(0.0, 0, 0.0, 0.0)


class Scorer(Protocol):
    def __call__(self, texts: list[str]) -> list[float]: ...


# ---------------------------------------------------------------- sources


def fetch_reddit_posts(subreddit: str, limit: int, session: requests.Session | None = None) -> list[Post]:
    """Fetch newest posts. Uses praw when credentials exist in .env, else Reddit's public JSON feed."""
    if os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"):
        return _fetch_with_praw(subreddit, limit)
    session = session or requests.Session()
    resp = session.get(
        f"https://www.reddit.com/r/{subreddit}/new.json",
        params={"limit": min(limit, 100)},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    return [
        Post(
            id=c["data"]["id"],
            subreddit=subreddit,
            created_utc=float(c["data"]["created_utc"]),
            title=c["data"].get("title", ""),
            text=c["data"].get("selftext", ""),
            upvotes=int(c["data"].get("score", 0)),
            url=_reddit_url(c["data"].get("permalink", "")),
        )
        for c in resp.json()["data"]["children"]
    ]


def _fetch_with_praw(subreddit: str, limit: int) -> list[Post]:
    import praw  # optional dependency: pip install ".[reddit]"

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.getenv("REDDIT_USER_AGENT", USER_AGENT),
    )
    return [
        Post(p.id, subreddit, float(p.created_utc), p.title, p.selftext or "", int(p.score), _reddit_url(p.permalink))
        for p in reddit.subreddit(subreddit).new(limit=limit)
    ]


def _reddit_url(permalink: str) -> str:
    return f"https://www.reddit.com{permalink}" if permalink.startswith("/") else ""


# ---------------------------------------------------------------- scorers


@lru_cache(maxsize=1)
def _vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    analyzer.lexicon.update(CRYPTO_LEXICON)
    return analyzer


def vader_scorer(texts: list[str]) -> list[float]:
    analyzer = _vader()
    return [analyzer.polarity_scores(t)["compound"] for t in texts]


@lru_cache(maxsize=1)
def _finbert():
    from transformers import pipeline  # optional dependency: pip install ".[finbert]"

    return pipeline("text-classification", model="ProsusAI/finbert", top_k=None, truncation=True)


def finbert_scorer(texts: list[str]) -> list[float]:
    """Score = P(positive) - P(negative), on the same -1..+1 scale as VADER."""
    scores = []
    for result in _finbert()(texts):
        probs = {r["label"].lower(): r["score"] for r in result}
        scores.append(probs.get("positive", 0.0) - probs.get("negative", 0.0))
    return scores


def get_scorer(name: str) -> Scorer:
    scorers: dict[str, Scorer] = {"vader": vader_scorer, "finbert": finbert_scorer}
    if name not in scorers:
        raise ValueError(f"Unknown sentiment model '{name}'. Choose from {sorted(scorers)}.")
    return scorers[name]


# ---------------------------------------------------------------- aggregation


def post_text(post: Post, include_body: bool) -> str:
    body = post.text[:1000] if include_body else ""
    return f"{post.title}. {body}".strip()


def aggregate(scores: list[float]) -> SentimentResult:
    if not scores:
        return SentimentResult.empty()
    n = len(scores)
    return SentimentResult(
        score=sum(scores) / n,
        n_posts=n,
        positive_share=sum(s > 0.05 for s in scores) / n,
        negative_share=sum(s < -0.05 for s in scores) / n,
    )


def score_posts(posts: list[Post], cfg: SentimentConfig) -> tuple[SentimentResult, list[float]]:
    texts = [post_text(p, cfg.include_body) for p in posts]
    scores = get_scorer(cfg.model)(texts) if texts else []
    return aggregate(scores), scores


def fetch_sentiment(cfg: SentimentConfig) -> tuple[SentimentResult, list[Post], list[float]]:
    """Fetch and score posts from every configured subreddit.

    Network failures are logged and treated as "no data" (neutral) instead of crashing the app.
    """
    posts: list[Post] = []
    for sub in cfg.subreddits:
        try:
            posts.extend(fetch_reddit_posts(sub, cfg.posts_per_subreddit))
        except Exception as exc:  # noqa: BLE001 - any source failure should degrade gracefully
            log.warning("Could not fetch r/%s: %s", sub, exc)
    result, scores = score_posts(posts, cfg)
    return result, posts, scores
