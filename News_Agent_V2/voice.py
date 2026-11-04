"""Stage 4: turn script.json into an English voiceover, one audio clip per scene.

Usage:
    python voice.py                       # today's runs/<date>/script.json
    python voice.py --date 2026-10-14
    python voice.py --list-voices         # show English voices you can use

Output (in runs/<date>/):
    audio/scene_00.mp3, scene_01.mp3, ...
    audio_manifest.json   real durations, start times and per-word timing (for the captions)

Design notes:
- Real audio length replaces the word-count estimate from stage 3.
- If the real total is over VIDEO_HARD_MAX_SECONDS, the speech is sped up slightly
  (capped at MAX_SPEEDUP_PERCENT) and re-rendered. If it still does not fit, we warn.
- edge-tts is an unofficial wrapper around Microsoft's online voices. It needs internet and
  occasionally breaks; if it fails with a 403 error, run: pip install -U edge-tts
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import re
from datetime import date
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

import captions
import config
from models import VideoScript

log = logging.getLogger(__name__)


def apply_pronunciations(text: str) -> str:
    """Whole-word, case-sensitive replacements so acronyms are read sensibly."""
    for word, spoken in config.PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", spoken, text)
    return text


def audio_duration(path: Path) -> float:
    return float(MP3(str(path)).info.length)


def rate_string(percent: int) -> str:
    return f"{percent:+d}%"


def total_with_pauses(durations: list[float]) -> float:
    return sum(durations) + config.SCENE_PAUSE * len(durations)


TICKS_PER_SECOND = 10_000_000  # edge-tts reports times in 100-nanosecond ticks


def spoken_form(display_text: str) -> tuple[str, list[int]]:
    """Text sent to the voice (acronyms respelled) and how many spoken words each displayed word became."""
    parts = [apply_pronunciations(w) for w in display_text.split()]
    return " ".join(parts), [max(len(p.split()), 1) for p in parts]


async def _synthesize(text: str, voice: str, rate: str, path: Path, retries: int = 3):
    """Write the audio file and return [(token, start_s, end_s), ...] (may be empty)."""
    for attempt in range(1, retries + 1):
        try:
            words, sentences = [], []
            try:
                comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
            except TypeError:  # older edge-tts without the boundary option: audio only
                await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
                return []
            with open(path, "wb") as f:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        start = chunk["offset"] / TICKS_PER_SECOND
                        item = (chunk["text"], start, start + chunk["duration"] / TICKS_PER_SECOND)
                        (words if chunk["type"] == "WordBoundary" else sentences).append(item)
            return words or sentences  # some voices only report sentences; captions still work
        except Exception as exc:  # edge-tts raises several different error types
            log.warning("TTS attempt %d failed for %s: %s", attempt, path.name, exc)
            if attempt == retries:
                raise
            await asyncio.sleep(2 * attempt)


async def _render_all(script: VideoScript, voice: str, rate: str, audio_dir: Path):
    spoken, durations, all_words = [], [], []
    for i, scene in enumerate(script.scenes):
        text, expansions = spoken_form(scene.narration)
        path = audio_dir / f"scene_{i:02d}.mp3"
        tokens = await _synthesize(text, voice, rate, path)
        duration = audio_duration(path)
        spoken.append(text)
        durations.append(duration)
        words = captions.align_words(scene.narration, tokens, duration, spoken_text=text, expansions=expansions)
        all_words.append([{"w": w.text, "start": round(w.start, 3), "end": round(w.end, 3)} for w in words])
    return spoken, durations, all_words


def load_script(day: str) -> VideoScript:
    path = config.RUNS_DIR / day / "script.json"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run script.py first.")
    return VideoScript.model_validate_json(path.read_text(encoding="utf-8"))


def run(day: str, voice: str = config.VOICE) -> dict:
    script = load_script(day)
    audio_dir = config.RUNS_DIR / day / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    percent = 0
    spoken, durations, words = asyncio.run(_render_all(script, voice, rate_string(percent), audio_dir))
    total = total_with_pauses(durations)
    log.info("Voiceover length at normal speed: %.1fs", total)

    if total > config.VIDEO_HARD_MAX_SECONDS:
        target = config.VIDEO_HARD_MAX_SECONDS - 1  # leave a small safety margin
        percent = min(config.MAX_SPEEDUP_PERCENT, math.ceil((total / target - 1) * 100))
        log.info("Too long. Re-rendering %d%% faster", percent)
        spoken, durations, words = asyncio.run(_render_all(script, voice, rate_string(percent), audio_dir))
        total = total_with_pauses(durations)
        if total > config.VIDEO_HARD_MAX_SECONDS:
            log.warning(
                "Still %.1fs after the maximum speed-up. Shorten the script (fewer words per "
                "story) and run script.py again.",
                total,
            )

    scenes, start = [], 0.0
    for i, (scene, text, dur, scene_words) in enumerate(zip(script.scenes, spoken, durations, words)):
        scenes.append(
            {
                "index": i,
                "kind": scene.kind,
                "file": f"audio/scene_{i:02d}.mp3",
                "spoken_text": text,
                "on_screen": scene.on_screen,
                "words": scene_words,
                "start": round(start, 2),
                "duration": round(dur, 2),
            }
        )
        start += dur + config.SCENE_PAUSE

    manifest = {
        "date": day,
        "voice": voice,
        "rate": rate_string(percent),
        "total_seconds": round(total, 2),
        "scenes": scenes,
    }
    (config.RUNS_DIR / day / "audio_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


async def _list_voices() -> None:
    for v in await edge_tts.list_voices():
        if v["Locale"].startswith("en-"):
            print(f'{v["ShortName"]:32} {v["Gender"]:7} {v["Locale"]}')


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--voice", default=config.VOICE)
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    if args.list_voices:
        asyncio.run(_list_voices())
    else:
        result = run(args.date, args.voice)
        print(f"\nVoice: {result['voice']}  speed: {result['rate']}  total: {result['total_seconds']}s\n")
        for sc in result["scenes"]:
            print(f"{sc['start']:>6}s  +{sc['duration']:>4}s  [{sc['kind']:5}] {sc['spoken_text']}")
        if result["total_seconds"] > config.VIDEO_HARD_MAX_SECONDS:
            print("\nWARNING: longer than the maximum. See the log above.")
