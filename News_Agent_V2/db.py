"""SQLite history so a story is never used twice (idempotency)."""
from __future__ import annotations
import hashlib
import sqlite3
from datetime import date

import config
from models import Article


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS used_stories (
               link_hash TEXT PRIMARY KEY,
               title TEXT,
               used_on TEXT
           )"""
    )
    return conn


def _hash(link: str) -> str:
    return hashlib.sha256(link.encode()).hexdigest()


def filter_unused(articles: list[Article]) -> list[Article]:
    with _conn() as conn:
        used = {r[0] for r in conn.execute("SELECT link_hash FROM used_stories")}
    return [a for a in articles if _hash(a.link) not in used]


def mark_used(articles: list[Article]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO used_stories VALUES (?, ?, ?)",
            [(_hash(a.link), a.title, date.today().isoformat()) for a in articles],
        )
