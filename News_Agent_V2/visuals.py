"""Stage: find footage or photos that relate to each story (stock media from Pexels).

Usage:
    python visuals.py                  # today's runs/<date>/script.json
    python visuals.py --date 2026-10-15

What it does:
1. Asks the AI for 2 neutral search phrases per story (e.g. "rain over city street").
2. Searches Pexels for a portrait video first, then a photo. Picks media not used by another story.
3. Downloads into media_cache/ (reused next time) and writes runs/<date>/visuals.json.
4. If there is no PEXELS_API_KEY, or nothing is found, that story gets an animated branded background.

Honesty note: stock footage is illustrative, not footage of the actual event. The video shows a small
"Representative visual" tag, and caption.txt gets a line saying the visuals are stock.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date
from pathlib import Path

import httpx

import config
from models import Story, VisualPlan
from news_llm import generate_json
from script import load_stories, pick_for_video

log = logging.getLogger(__name__)

PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PEXELS_PHOTOS = "https://api.pexels.com/v1/search"
STOPWORDS = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "at", "by", "with", "from", "over",
             "after", "as", "is", "are", "be", "will", "its", "his", "her"}

SYSTEM = """You choose stock-footage search phrases for a news video.
Rules:
- Phrases describe things a camera can film: places, objects, weather, crowds from far away.
- NEVER include names of people, politicians, parties, religions, companies or brands.
- Avoid depicting accidents, injuries, violence or distress: use neutral b-roll instead
  (for a boat accident: "river boat at dusk"; for a court case: "courtroom gavel").
- Prefer Indian or Tamil Nadu settings when they help (e.g. "Chennai beach", "Indian classroom").
- Reply with JSON only, no markdown fences, no commentary."""


# ---------- planning ----------
def build_prompt(chosen: list[Story]) -> str:
    lines = [f"[{i}] {s.headline}. {s.summary}" for i, s in enumerate(chosen)]
    return (
        "Stories:\n" + "\n".join(lines) + "\n\n"
        'Return JSON exactly like: {"items": [{"index": 0, "queries": ["specific phrase", "simpler fallback phrase"]}]}\n'
        f"- Exactly {len(chosen)} items, index 0 to {len(chosen) - 1}.\n"
        "- 2 queries per story, 2 to 5 words each, in English. The first is specific, the second more generic."
    )


def make_checker(n: int):
    def check(plan: VisualPlan) -> None:
        if sorted(i.index for i in plan.items) != list(range(n)):
            raise ValueError(f"need exactly one item for each index 0 to {n - 1}")
        for item in plan.items:
            if not 1 <= len(item.queries) <= 3:
                raise ValueError(f"item {item.index} needs 1 to 3 queries")
            for q in item.queries:
                if not 1 <= len(q.split()) <= 6:
                    raise ValueError(f"query '{q}' must be 1 to 6 words")
    return check


def headline_queries(story: Story) -> list[str]:
    """Plain fallback if the AI step fails: key words of the headline."""
    words = [w for w in re.findall(r"[A-Za-z]+", story.headline) if w.lower() not in STOPWORDS]
    return [" ".join(words[:3]) or "india news", "india city"]


def plan_queries(chosen: list[Story]) -> list[list[str]]:
    try:
        plan = generate_json(build_prompt(chosen), SYSTEM, VisualPlan, list_key="items",
                             validate=make_checker(len(chosen)))
        by_index = {item.index: item.queries for item in plan.items}
        return [by_index[i] for i in range(len(chosen))]
    except RuntimeError as exc:
        log.warning("Could not plan visuals with the AI (%s). Using headline words instead.", exc)
        return [headline_queries(s) for s in chosen]


# ---------- Pexels ----------
def _search(client: httpx.Client, url: str, query: str, orientation: str | None) -> dict:
    params = {"query": query, "per_page": 15}
    if orientation:
        params["orientation"] = orientation
    resp = client.get(url, params=params, headers={"Authorization": config.PEXELS_API_KEY})
    resp.raise_for_status()
    return resp.json()


def pick_video(videos: list[dict], used: set) -> tuple[dict, dict] | None:
    for v in videos:
        if v.get("id") in used or (v.get("duration") or 0) < 3:
            continue
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
        files = [f for f in files if min(f.get("width") or 0, f.get("height") or 0) >= 540]
        if not files:
            continue

        def score(f):  # prefer portrait files whose short side is close to 1080
            w, h = f.get("width") or 0, f.get("height") or 0
            return (0 if h >= w else 1, abs(min(w, h) - 1080))

        return v, sorted(files, key=score)[0]
    return None


def pick_photo(photos: list[dict], used: set) -> tuple[dict, str] | None:
    for p in photos:
        if p.get("id") in used:
            continue
        src = p.get("src", {})
        link = src.get("large2x") or src.get("original") or src.get("portrait")
        if link:
            return p, link
    return None


def download(client: httpx.Client, url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    tmp.replace(dest)
    return dest


def find_media(client: httpx.Client, queries: list[str], used_videos: set, used_photos: set) -> dict | None:
    """First usable portrait video, then photo, for each query in turn. At most ~5 requests."""

    def try_video(q, orientation):
        data = _search(client, PEXELS_VIDEOS, q, orientation)
        hit = pick_video(data.get("videos", []), used_videos)
        if not hit:
            return None
        v, f = hit
        dest = config.MEDIA_CACHE / f"pexels_video_{v['id']}_{f.get('width')}x{f.get('height')}.mp4"
        download(client, f["link"], dest)
        used_videos.add(v["id"])
        user = v.get("user", {})
        return {"type": "video", "path": str(dest), "query": q, "media_id": v["id"],
                "credit": f"{user.get('name', 'Pexels contributor')} on Pexels", "source_url": v.get("url", "")}

    def try_photo(q, orientation):
        data = _search(client, PEXELS_PHOTOS, q, orientation)
        hit = pick_photo(data.get("photos", []), used_photos)
        if not hit:
            return None
        p, link = hit
        dest = config.MEDIA_CACHE / f"pexels_photo_{p['id']}.jpg"
        download(client, link, dest)
        used_photos.add(p["id"])
        return {"type": "photo", "path": str(dest), "query": q, "media_id": p["id"],
                "credit": f"{p.get('photographer', 'Pexels contributor')} on Pexels", "source_url": p.get("url", "")}

    attempts = [(q, fn) for q in queries for fn in (try_video, try_photo)]
    attempts.append((queries[0], try_video))  # last chance: any orientation, cropped to portrait
    for i, (q, fn) in enumerate(attempts):
        try:
            hit = fn(q, None if i == len(attempts) - 1 else "portrait")
        except httpx.HTTPError as exc:
            log.warning("Pexels request failed for '%s': %s", q, exc)
            continue
        if hit:
            return hit
    return None


# ---------- run ----------
def run(day: str, client: httpx.Client | None = None) -> list[dict]:
    run_dir = config.RUNS_DIR / day
    stories = load_stories(day)
    chosen = pick_for_video(stories)
    n_scenes = len(chosen) + 2  # presenter opening + stories + presenter closing

    plans = plan_queries(chosen)
    key = config.PEXELS_API_KEY
    if not key:
        log.warning("No PEXELS_API_KEY in .env: using animated branded backgrounds instead of footage. "
                    "Get a free key at https://www.pexels.com/api/")

    own_client = client is None
    client = client or httpx.Client(timeout=30)
    used_videos, used_photos = set(), set()
    items = [{"scene_index": 0, "type": "presenter"}]
    try:
        for i, queries in enumerate(plans):
            media = find_media(client, queries, used_videos, used_photos) if key else None
            if media is None:
                if key:
                    log.warning("No media found for story %d (%s). Using a branded background.", i, queries)
                media = {"type": "fallback", "query": queries[0]}
            items.append({"scene_index": i + 1, "story_index": i, **media})
            log.info("Story %d: %s (%s)", i, media["type"], media.get("query"))
    finally:
        if own_client:
            client.close()
    items.append({"scene_index": n_scenes - 1, "type": "presenter"})

    (run_dir / "visuals.json").write_text(json.dumps({"date": day, "items": items}, indent=2), encoding="utf-8")

    # honest labelling in the caption
    caption_path = run_dir / "caption.txt"
    if caption_path.exists() and any(it["type"] in ("video", "photo") for it in items):
        text = caption_path.read_text(encoding="utf-8")
        if "Visuals:" not in text:
            note = "Visuals: representative stock footage and photos from Pexels."
            caption_path.write_text(text.replace("\n\n#", f"\n{note}\n\n#", 1) if "\n\n#" in text else f"{text}\n{note}",
                                    encoding="utf-8")
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    result = run(parser.parse_args().date)
    print()
    for it in result:
        print(f"scene {it['scene_index']:>2}: {it['type']:9} {it.get('query', '')}  {it.get('credit', '')}")
