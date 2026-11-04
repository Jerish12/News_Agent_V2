"""Stage 3: turn today's ranked stories into a ~55-second narration script + caption.

Usage:
    python script.py                  # uses today's runs/<date>/stories.json
    python script.py --date 2026-10-14

Design notes:
- The video narrates the stories set in config.VIDEO_STORIES (default 5 Tamil Nadu + 5 India)
  in 50-58 seconds. The caption and the image carry the same 10.
- Timing is computed in code from word counts. The LLM's idea of "one minute" is not trusted.
- The presenter's opening and closing lines (config.HOOK_TEXT / OUTRO_TEXT) and the source line are
  added by code, so branding and credits are deterministic. The AI only writes the story lines.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date

import config
from fetch import clean_source
from news_llm import generate_json
from models import Scene, ScriptDraft, Story, VideoScript

log = logging.getLogger(__name__)

STORY_MAX_WORDS = 12
ON_SCREEN_MAX_WORDS = 8
# LLMs are bad at counting words. The prompt asks for HOOK/STORY_MAX_WORDS, but we only
# reject a scene that is clearly over (limit + tolerance). The TOTAL word range is what
# really controls video length, and that is enforced strictly.
WORD_TOLERANCE = 4

SYSTEM = """You write the story lines for a one-minute vertical news video that a TV-style news presenter reads.
Rules:
- Neutral, factual newsreader tone in clear English. No opinions, no hype, no emojis.
- Use ONLY facts present in the stories provided. Do not add names, numbers or details.
- Each story gets one short spoken sentence with a single key fact.
- Keep who-did-what-to-whom exactly as in the source, and keep qualifiers such as
  "linked to", "alleged", "likely", "sought". Never turn "assets linked to X" into "seized from X".
- Reply with JSON only, no markdown fences, no commentary."""


def word_count(text: str) -> int:
    return len(text.split())


def scene_seconds(text: str) -> float:
    return word_count(text) / config.WORDS_PER_SECOND + config.SCENE_PAUSE


def word_limits(n_stories: int) -> tuple[int, int]:
    """(min, max) spoken words for the story lines, so the whole video (presenter opening and
    closing, scene pauses included) lands between MIN and MAX seconds."""
    n_scenes = n_stories + 2  # presenter opening + stories + presenter closing
    pauses = n_scenes * config.SCENE_PAUSE
    fixed = word_count(config.HOOK_TEXT) + word_count(config.OUTRO_TEXT)
    max_words = int((config.VIDEO_SECONDS - pauses) * config.WORDS_PER_SECOND) - fixed
    min_words = math.ceil((config.MIN_VIDEO_SECONDS - pauses) * config.WORDS_PER_SECOND) - fixed
    return max(min_words, 0), max_words


def load_stories(day: str) -> list[Story]:
    path = config.RUNS_DIR / day / "stories.json"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run main.py first.")
    return [Story(**s) for s in json.loads(path.read_text(encoding="utf-8"))]


def pick_for_video(stories: list[Story]) -> list[Story]:
    chosen: list[Story] = []
    for region, n in config.VIDEO_STORIES.items():
        regional = sorted((s for s in stories if s.region == region), key=lambda s: s.rank)
        chosen.extend(regional[:n])
    return chosen


def build_prompt(chosen: list[Story], day_label: str, min_words: int, budget: int) -> str:
    lines = [f"[{i}] ({s.region}) {s.headline}. {s.summary}" for i, s in enumerate(chosen)]
    return (
        f"Date: {day_label}\n\n"
        "Stories (use only these facts):\n" + "\n".join(lines) + "\n\n"
        "Return JSON exactly like:\n"
        '{"scenes": [{"kind": "story", "story_index": 0, "narration": "...", "on_screen": "..."}],\n'
        ' "caption_intro": "...", "hashtags": ["#TamilNadu", "#IndiaNews"]}\n\n'
        "Requirements:\n"
        f"- Exactly {len(chosen)} scenes, one per story, in the order listed (story_index 0, 1, 2, ...). "
        "A presenter reads the opening and closing separately, so do NOT write those.\n"
        f"- Each narration: at most {STORY_MAX_WORDS} words, one key fact, spoken newsreader style.\n"
        f"- All narrations together: between {min_words} and {budget} words "
        f"(aim for about {(min_words + budget) // 2}).\n"
        "- on_screen: a punchy headline of at most 6 words, shown as the on-screen banner.\n"
        "- caption_intro: one engaging sentence, at most 20 words, no emojis.\n"
        f"- hashtags: 5 to {config.MAX_HASHTAGS} relevant hashtags."
    )


def make_checker(chosen: list[Story], min_words: int, budget: int):
    def check(draft: ScriptDraft) -> None:
        scenes = draft.scenes
        if len(scenes) != len(chosen):
            raise ValueError(f"need exactly {len(chosen)} scenes, got {len(scenes)}")
        for i, sc in enumerate(scenes):
            if sc.kind != "story" or sc.story_index != i:
                raise ValueError(f"scene {i} must be kind 'story' with story_index {i}")
            n_words = word_count(sc.narration)
            if n_words > STORY_MAX_WORDS + WORD_TOLERANCE:
                raise ValueError(
                    f"story {i} narration has {n_words} words, keep it to {STORY_MAX_WORDS} or fewer"
                )
            if not sc.narration.strip() or not sc.on_screen.strip():
                raise ValueError("narration and on_screen must not be empty")
            if word_count(sc.on_screen) > ON_SCREEN_MAX_WORDS:
                raise ValueError(f"on_screen text is over {ON_SCREEN_MAX_WORDS} words")
        total = sum(word_count(sc.narration) for sc in scenes)
        if total > budget:
            raise ValueError(f"narration has {total} words, the maximum is {budget}. Shorten it")
        if total < min_words:
            raise ValueError(
                f"narration has only {total} words, the minimum is {min_words}. "
                "Add a little more detail to each story"
            )

    return check


def clean_hashtags(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for tag in tags:
        tag = "#" + tag.strip().lstrip("#").replace(" ", "")
        if len(tag) > 1 and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[: config.MAX_HASHTAGS]


def build_caption(intro: str, hashtags: list[str], stories: list[Story]) -> str:
    parts = [intro.strip(), ""]
    for region, label in (("tamilnadu", "Tamil Nadu"), ("india", "India")):
        regional = sorted((s for s in stories if s.region == region), key=lambda s: s.rank)
        if regional:
            parts.append(label)
            parts.extend(f"{i}. {s.headline}" for i, s in enumerate(regional, 1))
            parts.append("")
    sources = sorted({clean_source(s.source) for s in stories if s.source})
    if sources:
        parts.append("Sources: " + ", ".join(sources))
        parts.append("")
    parts.append(" ".join(hashtags))
    return "\n".join(parts).strip()


def build_script(day: str, all_stories: list[Story], draft: ScriptDraft) -> VideoScript:
    hook = Scene(kind="hook", story_index=None, narration=config.HOOK_TEXT, on_screen=config.HOOK_ON_SCREEN)
    outro = Scene(kind="outro", story_index=None, narration=config.OUTRO_TEXT, on_screen=config.OUTRO_ON_SCREEN)
    scenes = [hook] + list(draft.scenes) + [outro]
    for sc in scenes:
        sc.estimated_seconds = round(scene_seconds(sc.narration), 2)
    hashtags = clean_hashtags(draft.hashtags)
    return VideoScript(
        date=day,
        scenes=scenes,
        caption=build_caption(draft.caption_intro, hashtags, all_stories),
        hashtags=hashtags,
        total_seconds=round(sum(sc.estimated_seconds for sc in scenes), 2),
    )


def run(day: str) -> VideoScript:
    stories = load_stories(day)
    chosen = pick_for_video(stories)
    if not chosen:
        raise SystemExit("No stories available for the video.")

    min_words, budget = word_limits(len(chosen))
    if budget < 6 * len(chosen):
        raise SystemExit("Word budget too small. Reduce VIDEO_STORIES or shorten HOOK_TEXT and OUTRO_TEXT.")

    draft = generate_json(
        build_prompt(chosen, date.fromisoformat(day).strftime("%d %B %Y"), min_words, budget),
        SYSTEM,
        ScriptDraft,
        validate=make_checker(chosen, min_words, budget),
    )
    script = build_script(day, stories, draft)

    out_dir = config.RUNS_DIR / day
    (out_dir / "script.json").write_text(
        json.dumps(script.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "caption.txt").write_text(script.caption, encoding="utf-8")
    log.info("Saved script.json and caption.txt in %s", out_dir)
    return script


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    result = run(parser.parse_args().date)

    print(f"\nEstimated length: {result.total_seconds}s\n")
    for sc in result.scenes:
        print(f"[{sc.kind:5}] {sc.estimated_seconds:>4}s  {sc.narration}\n          on screen: {sc.on_screen}")
    print("\n--- Caption ---\n" + result.caption)
