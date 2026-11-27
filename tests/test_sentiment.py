# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
import pytest

from coin_buddy.config import SentimentConfig
from coin_buddy.data import sentiment as s


def test_crypto_slang_is_understood():
    bullish, bearish = s.vader_scorer(["BTC is going to the moon, very bullish", "Got rekt, total rugpull"])
    assert bullish > 0.3
    assert bearish < -0.3


def test_aggregate():
    r = s.aggregate([0.5, -0.5, 0.0, 0.6])
    assert r.score == pytest.approx(0.15)
    assert r.n_posts == 4 and r.positive_share == 0.5 and r.negative_share == 0.25
    assert s.aggregate([]) == s.SentimentResult.empty()


def test_post_text_respects_include_body():
    post = s.Post("1", "bitcoin", 0.0, "Title", "Body text", 3)
    assert "Body" in s.post_text(post, include_body=True)
    assert "Body" not in s.post_text(post, include_body=False)


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        s.get_scorer("gpt")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def get(self, url, **kwargs):
        children = [{"data": {"id": "a1", "created_utc": 1.0, "title": "Bitcoin rally", "selftext": "", "score": 5}}]
        return FakeResponse({"data": {"children": children}})


def test_public_json_source(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    posts = s.fetch_reddit_posts("bitcoin", 5, session=FakeSession())
    assert posts == [s.Post("a1", "bitcoin", 1.0, "Bitcoin rally", "", 5)]


def test_source_failure_degrades_to_neutral(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(s, "fetch_reddit_posts", boom)
    result, posts, scores = s.fetch_sentiment(SentimentConfig(subreddits=["bitcoin"]))
    assert result.n_posts == 0 and posts == [] and scores == []
