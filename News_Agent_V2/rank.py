"""Stage 2: ask the LLM to pick and rewrite the top stories.

Best practices shown here:
- Candidates are numbered; the model returns indexes, never URLs.
- Output is JSON validated by Pydantic, with retry on failure (see news_llm.py).
- The prompt forbids adding facts that are not in the candidate text.
"""
from __future__ import annotations

import logging

import config
from news_llm import generate_json
from models import Article, RankingResponse, Region, Story

log = logging.getLogger(__name__)

REGION_LABEL = {"tamilnadu": "Tamil Nadu", "india": "India (national)"}

SYSTEM = """You are the news editor for a short-form social media news page.
Rules:
- Pick stories by public significance and impact, not by sensationalism.
- Never pick two items about the same event.
- Prefer verifiable hard news over opinion, gossip, or clickbait.
- Rewrite headlines and summaries in your own words.
- Use ONLY facts present in the provided title and snippet. Do not add details.
- Reply with JSON only, no markdown fences, no commentary."""


def _build_prompt(candidates: list[Article], region: Region, n: int) -> str:
    lines = [
        f"[{i}] {a.title} | {a.source} | {a.summary[:200]}"
        for i, a in enumerate(candidates)
    ]
    return (
        f"Pick the top {n} stories for the region: {REGION_LABEL[region]}.\n\n"
        "Candidates:\n" + "\n".join(lines) + "\n\n"
        'Return JSON exactly like: {"picks": [{"index": 0, "headline": "max 8 words", '
        '"summary": "one factual sentence, max 25 words", "score": 8}]}\n'
        f"Return exactly {n} picks, most important first. score is 1-10."
    )


def rank_region(candidates: list[Article], region: Region) -> list[Story]:
    n = config.TOP_N[region]
    candidates = candidates[: config.MAX_CANDIDATES]
    if not candidates:
        log.warning("No candidates for %s", region)
        return []

    def check(resp: RankingResponse) -> None:
        seen = set()
        for pick in resp.picks:
            if not (0 <= pick.index < len(candidates)) or pick.index in seen:
                raise ValueError(f"Invalid or repeated index {pick.index}")
            seen.add(pick.index)

    parsed = generate_json(
        _build_prompt(candidates, region, n),
        SYSTEM,
        RankingResponse,
        list_key="picks",
        validate=check,
    )
    stories = []
    for pick in parsed.picks[:n]:
        art = candidates[pick.index]
        stories.append(
            Story(
                rank=len(stories) + 1,
                region=region,
                headline=pick.headline,
                summary=pick.summary,
                score=pick.score,
                source=art.source,
                link=art.link,
            )
        )
    return stories
