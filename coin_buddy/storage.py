# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""SQLite storage (built into Python): every snapshot is saved so sentiment builds a history you can backtest later."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at        TEXT NOT NULL,           -- ISO-8601 UTC
    exchange        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    price           REAL NOT NULL,
    rsi             REAL,
    macd            REAL,
    macd_signal     REAL,
    bb_upper        REAL,
    bb_lower        REAL,
    sentiment       REAL,                    -- NULL when sentiment was unavailable
    sentiment_posts INTEGER,
    ml_p_up         REAL,                    -- NULL when no model is trained
    action          TEXT NOT NULL,
    votes           TEXT NOT NULL            -- JSON: {"RSI": 1, "MACD": -1, ...}
);
CREATE TABLE IF NOT EXISTS posts (
    id          TEXT PRIMARY KEY,            -- Reddit post id, so re-fetched posts aren't duplicated
    subreddit   TEXT NOT NULL,
    created_utc REAL NOT NULL,
    title       TEXT NOT NULL,
    upvotes     INTEGER,
    sentiment   REAL NOT NULL,
    model       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON snapshots(taken_at);
CREATE INDEX IF NOT EXISTS idx_posts_time ON posts(created_utc);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save_snapshot(self, row: dict) -> None:
        row = {**row, "votes": json.dumps(row["votes"])}
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        with closing(self._connect()) as conn, conn:
            conn.execute(f"INSERT INTO snapshots ({cols}) VALUES ({marks})", row)

    def save_posts(self, posts, scores: list[float], model: str) -> None:
        rows = [
            (p.id, p.subreddit, p.created_utc, p.title, p.upvotes, s, model) for p, s in zip(posts, scores, strict=True)
        ]
        with closing(self._connect()) as conn, conn:
            conn.executemany("INSERT OR IGNORE INTO posts VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    def snapshots(self, limit: int = 500) -> pd.DataFrame:
        with closing(self._connect()) as conn:
            df = pd.read_sql_query("SELECT * FROM snapshots ORDER BY taken_at DESC LIMIT ?", conn, params=(limit,))
        df["taken_at"] = pd.to_datetime(df["taken_at"], utc=True)
        return df.sort_values("taken_at")

    def sentiment_history(self, freq: str = "1h") -> pd.Series:
        """Average post sentiment per time bucket, ready to pass into signals.vote_frame()."""
        with closing(self._connect()) as conn:
            df = pd.read_sql_query("SELECT created_utc, sentiment FROM posts", conn)
        if df.empty:
            return pd.Series(dtype=float, name="sentiment")
        df["t"] = pd.to_datetime(df["created_utc"], unit="s", utc=True).dt.floor(freq)
        return df.groupby("t")["sentiment"].mean().rename("sentiment")
