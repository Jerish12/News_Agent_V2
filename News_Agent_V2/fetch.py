"""Stage 1: fetch RSS feeds, keep recent items, remove near-duplicates."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import httpx
from rapidfuzz import fuzz

import config
from models import Article, Region

log = logging.getLogger(__name__)


def _clean_title(title: str) -> str:
    # Google News appends " - Publisher" to titles
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title).strip()


def clean_source(name: str) -> str:
    """Feed titles like 'Top Headlines | The Hindu' -> 'The Hindu'."""
    return name.split("|")[-1].strip()[:40]


def _parse_date(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)


def fetch_feed(url: str, region: Region) -> list[Article]:
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=15,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # One broken feed must not kill the whole run
        log.warning("Feed failed (%s): %s", url, exc)
        return []

    feed = feedparser.parse(resp.content)
    source_default = feed.feed.get("title", "")
    articles = []
    for entry in feed.entries:
        title = _clean_title(entry.get("title", ""))
        link = entry.get("link", "")
        if not title or not link:
            continue
        source = clean_source(entry.get("source", {}).get("title", "") or source_default)
        articles.append(
            Article(
                title=title,
                link=link,
                source=source,
                published=_parse_date(entry),
                summary=re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:300],
                region=region,
            )
        )
    log.info("Fetched %d items from %s", len(articles), url)
    return articles


def filter_recent(articles: list[Article]) -> list[Article]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.MAX_AGE_HOURS)
    # Items without a date are kept; the LLM step can still judge them
    return [a for a in articles if a.published is None or a.published >= cutoff]


def dedupe(articles: list[Article]) -> list[Article]:
    """Greedy fuzzy dedupe on titles. Newest first, so we keep the freshest copy."""
    ordered = sorted(
        articles,
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    kept: list[Article] = []
    for art in ordered:
        if any(
            fuzz.token_set_ratio(art.title.lower(), k.title.lower())
            >= config.DEDUPE_THRESHOLD
            for k in kept
        ):
            continue
        kept.append(art)
    return kept


def fetch_region(region: Region) -> list[Article]:
    collected: list[Article] = []
    for url in config.FEEDS[region]:
        collected.extend(fetch_feed(url, region))
    return dedupe(filter_recent(collected))
