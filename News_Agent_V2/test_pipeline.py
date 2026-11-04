"""Offline tests: no internet, no API keys. Run with: python test_pipeline.py"""
import json
import os
import pathlib
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")

import anchor
import captions
import config
import fetch
import graphics
import httpx
import image
import media
import news_llm as llm
import overlays
import rank
import script
import video
import visuals
import voice
from models import Article, ScriptDraft, Story, VisualPlan

DAY = "2026-10-15"


# ------------------------------------------------------------------ helpers
def make(title, hours_ago=1, region="india"):
    return Article(title=title, link=f"https://example.com/{abs(hash(title))}", source="Test",
                   published=datetime.now(timezone.utc) - timedelta(hours=hours_ago), region=region)


def make_story(rank_, region, headline=None):
    return Story(rank=rank_, region=region, headline=headline or f"{region} headline {rank_}",
                 summary="A fact.", score=8, source="The Hindu", link=f"https://x.com/{region}{rank_}")


def all_stories():
    return [make_story(i, r) for r in ("tamilnadu", "india") for i in range(1, 6)]


def draft_json(story_words, n_stories=10):
    scenes = [{"kind": "story", "story_index": i, "narration": " ".join(["word"] * story_words),
               "on_screen": f"STORY {i}"} for i in range(n_stories)]
    return json.dumps({"scenes": scenes, "caption_intro": "Your daily news in a minute.",
                       "hashtags": ["TamilNadu", "#IndiaNews", "india news", "#tamilnadu"]})


# ------------------------------------------------------------------ stage 1-2
def test_dedupe():
    arts = [make("Chennai floods: schools closed in four districts"),
            make("Schools closed in four districts as Chennai floods"), make("RBI keeps repo rate unchanged")]
    assert len(fetch.dedupe(arts)) == 2


def test_clean_source():
    assert fetch.clean_source("India Latest News: Top National Headlines Today | The Hindu") == "The Hindu"


def test_recent_filter():
    assert [a.title for a in fetch.filter_recent([make("fresh", 2), make("stale", 48)])] == ["fresh"]


def _picks(n):
    return [{"index": i, "headline": f"H{i}", "summary": f"S{i}", "score": 8} for i in range(n)]


def test_rank_retry_and_bare_list():
    cands = [make(f"Story number {i} about topic {i * 7}") for i in range(6)]
    replies = ["not json at all", json.dumps({"picks": _picks(5)})]
    with patch.object(llm, "call_llm", side_effect=lambda *_: replies.pop(0)):
        assert len(rank.rank_region(cands, "india")) == 5
    with patch.object(llm, "call_llm", return_value=json.dumps(_picks(5))):
        assert len(rank.rank_region(cands, "india")) == 5


def test_llm_skips_failed_model():
    from google.genai import errors

    llm._skip_models.clear()
    calls = []

    class Boom(errors.APIError):
        def __init__(self):
            self.code = 503

    class FakeModels:
        def generate_content(self, model, **_):
            calls.append(model)
            if model == config.MODEL:
                raise Boom()
            from types import SimpleNamespace
            return SimpleNamespace(text="{}")

    class FakeClient:
        models = FakeModels()

    with patch.object(llm, "_get_client", return_value=FakeClient()), patch.object(llm.time, "sleep"):
        llm.call_llm("p", "s")
        first = len(calls)
        llm.call_llm("p", "s")
    assert config.MODEL in llm._skip_models and calls[first:] == [config.FALLBACK_MODELS[0]]
    llm._skip_models.clear()


# ------------------------------------------------------------------ stage 3: script
def test_script_limits_and_selection():
    chosen = script.pick_for_video(all_stories())
    assert [s.region for s in chosen] == ["tamilnadu"] * 5 + ["india"] * 5
    lo, hi = script.word_limits(len(chosen))
    assert 70 < lo < hi < 130, (lo, hi)


def test_script_rejects_long_and_short_then_fits():
    stories = all_stories()
    chosen = script.pick_for_video(stories)
    lo, hi = script.word_limits(len(chosen))
    replies = [draft_json(14), draft_json(5), draft_json(10)]  # too long, too short, fits
    with patch.object(llm, "call_llm", side_effect=lambda *_: replies.pop(0)):
        draft = llm.generate_json("p", "s", ScriptDraft, validate=script.make_checker(chosen, lo, hi))
    result = script.build_script(DAY, stories, draft)
    assert [s.kind for s in result.scenes] == ["hook"] + ["story"] * 10 + ["outro"]
    assert result.scenes[0].narration == config.HOOK_TEXT and result.scenes[-1].narration == config.OUTRO_TEXT
    assert config.MIN_VIDEO_SECONDS <= result.total_seconds <= config.VIDEO_SECONDS, result.total_seconds
    assert result.hashtags == ["#TamilNadu", "#IndiaNews"]
    assert "Sources: The Hindu" in result.caption and result.caption.count("headline") == 10


# ------------------------------------------------------------------ captions
def test_caption_alignment():
    tokens = [("The", .10, .25), ("D", .30, .40), ("G", .45, .55), ("C", .60, .70), ("A", .75, .85),
              ("banned", .90, 1.20), ("it", 1.25, 1.40)]
    w = captions.align_words("The DGCA banned it", tokens, 1.5)
    assert abs(w[1].start - 0.30) < 0.08 and abs(w[2].start - 0.90) < 0.08  # acronym spoken as 4 tokens
    toks = [("High", .1, .3), ("Court", .35, .7), ("seized", .8, 1.2), ("it", 1.25, 1.4)]
    w = captions.align_words("HC seized it", toks, 1.5, spoken_text="High Court seized it", expansions=[2, 1, 1])
    assert abs(w[1].start - 0.8) < 0.1
    w = captions.align_words("one two three", [], 3.0)  # no timing from the voice
    assert w[0].start < w[1].start < w[2].start and w[-1].end <= 3.0


def test_caption_states_cover_words_without_overlap():
    words = captions.align_words("The monsoon is expected to reach Tamil Nadu on October fifteen.", [], 4.5)
    states = captions.caption_states(words)
    assert len(states) == len(words)
    for a, b in zip(states, states[1:]):
        assert a["start"] <= b["start"] and a["end"] <= b["start"] + 0.2
    img = captions.render_state(words, states[0]["group"], states[0]["active"])
    assert img.size == (graphics.W, config.CAPTION_AREA_HEIGHT) and img.getbbox() is not None
    tl = video.caption_timeline(states, 5.0)
    assert abs(sum(d for _, d in tl) - 5.0) < 0.2 and all(d > 0 for _, d in tl)


# ------------------------------------------------------------------ stage 4: voice
def test_pronunciations_and_spoken_form():
    assert "D G C A" in voice.apply_pronunciations("DGCA banned it")
    assert voice.apply_pronunciations("SEIZED and ED-like") == "SEIZED and E D-like"
    text, exp = voice.spoken_form("The HC asked")
    assert text == "The High Court asked" and exp == [1, 2, 1]


class FakeCommunicate:
    """Pretends to be edge_tts.Communicate, with word timings."""

    def __init__(self, text, voice_name, rate="+0%", boundary=None):
        self.text, self.rate, self.boundary = text, rate, boundary

    async def stream(self):
        yield {"type": "audio", "data": json.dumps({"words": len(self.text.split()), "rate": self.rate}).encode()}
        t = 0.1
        for w in self.text.split():
            yield {"type": "WordBoundary", "offset": t * 1e7, "duration": 0.3 * 1e7, "text": w}
            t += 0.4


def test_voice_speeds_up_and_records_word_timing():
    stories = all_stories()
    draft = ScriptDraft.model_validate_json(draft_json(10))
    video_script = script.build_script(DAY, stories, draft)

    def fake_duration(path):  # slow speaker: 2 words/sec, faster when the rate goes up
        info = json.loads(pathlib.Path(path).read_bytes())
        return info["words"] / 2.0 / (1 + int(info["rate"].rstrip("%")) / 100)

    with tempfile.TemporaryDirectory() as d:
        run_dir = pathlib.Path(d) / DAY
        run_dir.mkdir()
        (run_dir / "script.json").write_text(video_script.model_dump_json())
        with patch.object(config, "RUNS_DIR", pathlib.Path(d)), \
             patch.object(voice.edge_tts, "Communicate", FakeCommunicate), \
             patch.object(voice, "audio_duration", fake_duration):
            manifest = voice.run(DAY)
        assert manifest["rate"] != "+0%" and manifest["total_seconds"] <= config.VIDEO_HARD_MAX_SECONDS
        assert len(manifest["scenes"]) == 12
        first = manifest["scenes"][0]
        assert len(first["words"]) == len(config.HOOK_TEXT.split())
        assert first["words"][0]["start"] < first["words"][1]["start"]  # real timing, in order
        assert (run_dir / "audio_manifest.json").exists()


def test_voice_falls_back_without_boundary_support():
    class OldCommunicate:
        def __init__(self, text, voice_name, rate="+0%"):  # no boundary option
            pass

        async def save(self, path):
            pathlib.Path(path).write_bytes(b"x")

    import asyncio
    with tempfile.TemporaryDirectory() as d, patch.object(voice.edge_tts, "Communicate", OldCommunicate):
        tokens = asyncio.run(voice._synthesize("hello there", "v", "+0%", pathlib.Path(d) / "a.mp3"))
    assert tokens == []


# ------------------------------------------------------------------ presenter
def _tone(path, seconds, ffmpeg):
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"aevalsrc=0.6*sin(2*PI*190*t)*(0.5+0.5*sin(2*PI*4.2*t)):s=24000:d={seconds}",
                    "-ac", "1", "-b:a", "48k", str(path)], check=True)


def test_presenter_lipsync_and_clip():
    import numpy as np
    assert anchor.mouth_states(np.array([0.0, 0.05, 0.2, 0.4, 0.9])) == [0, 0, 1, 2, 3]
    ff = media.ffmpeg_exe()
    with tempfile.TemporaryDirectory() as d:
        audio, out = pathlib.Path(d) / "a.mp3", pathlib.Path(d) / "p.mp4"
        _tone(audio, 1.6, ff)
        env = anchor.audio_envelope(audio, 30, 48)
        assert env.max() > 0.5 and env.min() < 0.3  # loud and quiet parts both found
        anchor.render_clip(audio, 1.6, out, anchor.Presenter(), seed=3)
        info = media.probe(out)
        assert "1080x1920" in info and abs(media.duration_seconds(out) - 1.6) < 0.2


def test_presenter_styles_draw_and_change_with_colour():
    import presenter_art
    saree = presenter_art.draw_figure(style="saree", saree_rgb=(16, 128, 96))
    other = presenter_art.draw_figure(style="saree", saree_rgb=(150, 30, 66))
    blazer = presenter_art.draw_figure(style="blazer")
    assert saree.size == other.size == blazer.size == (1080, 1920)
    probe = (800, 1300)  # on the draped saree
    assert saree.getpixel(probe) != other.getpixel(probe)           # the colour setting changes the outfit
    assert saree.getpixel(probe) != blazer.getpixel(probe)          # the two styles really differ


# ------------------------------------------------------------------ visuals (Pexels mocked)
def pexels_transport(video_hits=None, photo_hits=None):
    video_hits = video_hits if video_hits is not None else [
        {"id": 11, "duration": 9, "url": "https://pexels.com/v/11", "user": {"name": "Ann"},
         "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://dl/v11.mp4"},
                         {"file_type": "video/mp4", "width": 540, "height": 960, "link": "https://dl/v11s.mp4"}]},
        {"id": 12, "duration": 9, "url": "https://pexels.com/v/12", "user": {"name": "Bo"},
         "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://dl/v12.mp4"}]}]
    photo_hits = photo_hits if photo_hits is not None else [
        {"id": 21, "url": "https://pexels.com/p/21", "photographer": "Cy", "src": {"large2x": "https://dl/p21.jpg"}}]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if "videos/search" in url or "v1/search" in url:
            assert request.headers.get("Authorization") == "KEY"
            return httpx.Response(200, json={"videos": video_hits} if "videos/search" in url else {"photos": photo_hits})
        assert "Authorization" not in request.headers  # the API key is never sent to the download servers
        return httpx.Response(200, content=b"binary-media")

    transport = httpx.MockTransport(handler)
    transport.seen = seen
    return transport


def test_visuals_pick_prefers_portrait_and_unused():
    hit = visuals.pick_video([{"id": 1, "duration": 8, "video_files": [
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "a"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "b"}]}], set())
    assert hit[1]["link"] == "b"
    assert visuals.pick_video([{"id": 1, "duration": 8, "video_files": [
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "b"}]}], {1}) is None
    assert visuals.pick_video([{"id": 2, "duration": 1, "video_files": [
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "b"}]}], set()) is None  # too short


def test_visuals_run_end_to_end_with_mock_pexels():
    stories = all_stories()
    plan_json = json.dumps({"items": [{"index": i, "queries": [f"query {i} specific", f"query {i}"]} for i in range(10)]})
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        run_dir = root / DAY
        run_dir.mkdir()
        (run_dir / "stories.json").write_text(json.dumps([s.model_dump() for s in stories]))
        (run_dir / "caption.txt").write_text("Intro\n\nSources: The Hindu\n\n#TamilNadu #IndiaNews")
        transport = pexels_transport()
        client = httpx.Client(transport=transport)
        with patch.object(config, "RUNS_DIR", root), patch.object(config, "MEDIA_CACHE", root / "cache"), \
             patch.object(config, "PEXELS_API_KEY", "KEY"), \
             patch.object(llm, "call_llm", return_value=plan_json):
            items = visuals.run(DAY, client=client)
        types = [it["type"] for it in items]
        assert types[0] == types[-1] == "presenter" and len(items) == 12
        stories_items = items[1:-1]
        assert stories_items[0]["type"] == "video" and stories_items[1]["type"] == "video"
        assert stories_items[0]["media_id"] != stories_items[1]["media_id"]       # no repeats
        assert stories_items[2]["type"] in ("photo", "fallback")                  # videos ran out
        assert all(pathlib.Path(it["path"]).exists() for it in stories_items if it["type"] in ("video", "photo"))
        saved = json.loads((run_dir / "visuals.json").read_text())
        assert len(saved["items"]) == 12
        caption = (run_dir / "caption.txt").read_text()
        assert "Visuals: representative stock footage" in caption and caption.rstrip().endswith("#IndiaNews")


def test_visuals_without_key_uses_fallback_and_survives_ai_failure():
    stories = all_stories()
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        run_dir = root / DAY
        run_dir.mkdir()
        (run_dir / "stories.json").write_text(json.dumps([s.model_dump() for s in stories]))
        with patch.object(config, "RUNS_DIR", root), patch.object(config, "PEXELS_API_KEY", ""), \
             patch.object(llm, "call_llm", return_value="not json"):
            items = visuals.run(DAY)
        assert [it["type"] for it in items[1:-1]] == ["fallback"] * 10


def test_visuals_plan_validation():
    check = visuals.make_checker(2)
    check(VisualPlan.model_validate({"items": [{"index": 0, "queries": ["a b"]}, {"index": 1, "queries": ["c d"]}]}))
    for bad in ({"items": [{"index": 0, "queries": ["a"]}]},
                {"items": [{"index": 0, "queries": []}, {"index": 1, "queries": ["x"]}]},
                {"items": [{"index": 0, "queries": ["one two three four five six seven"]}, {"index": 1, "queries": ["x"]}]}):
        try:
            check(VisualPlan.model_validate(bad))
            raise AssertionError("should have been rejected")
        except ValueError:
            pass


# ------------------------------------------------------------------ overlays and header
def test_profile_picture_in_header():
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d) / "dp with spaces.jpg"
        Image.new("RGB", (800, 600), (220, 20, 20)).save(dp)
        with patch.object(config, "PROFILE_PICTURE", str(dp)):
            img = overlays.base_overlay("story", "india", 1, 10, "15 October 2026", graphics.ACCENTS["india"], True)
        cx, cy = graphics.MARGIN_L + graphics.AVATAR_SIZE // 2, 96 + graphics.AVATAR_SIZE // 2
        r, g, b, a = img.getpixel((cx, cy))
        assert r > 180 and g < 90 and a == 255
        missing = pathlib.Path(d) / "nope.jpg"
        with patch.object(config, "PROFILE_PICTURE", str(missing)):
            img = overlays.base_overlay("hook", None, 0, 10, "15 October 2026", graphics.NEUTRAL_ACCENT, False)
        assert img.size == (1080, 1920)  # no crash without the picture


def test_banner_fits_in_one_line_for_presenter():
    one = overlays.banner("hook", "TODAY'S TOP 10 HEADLINES", "WELCOME", graphics.NEUTRAL_ACCENT)
    two = overlays.banner("story", "A long story headline that needs two lines to fit", "TOP STORY 1", graphics.ACCENTS["india"])
    assert one.height < two.height
    assert config.PRESENTER_BANNER_Y + one.height < config.CAPTION_Y  # does not touch the captions
    assert config.BANNER_Y + two.height < config.CAPTION_Y


# ------------------------------------------------------------------ video (real ffmpeg, small)
def build_fixture(root, n_per_region=1):
    """A fake run folder with stories, script, visuals, audio and timing for the video stage."""
    ff = media.ffmpeg_exe()
    run = root / DAY
    (run / "audio").mkdir(parents=True)
    stories = [make_story(i, r) for r in ("tamilnadu", "india") for i in range(1, 6)]
    (run / "stories.json").write_text(json.dumps([s.model_dump() for s in stories]))
    n = 2 * n_per_region
    narrations = ["The monsoon is expected to reach Tamil Nadu on October fifteen.",
                  "The DGCA banned a specific power bank after a cabin explosion."] + ["More news today."] * 8
    draft = ScriptDraft.model_validate({"scenes": [
        {"kind": "story", "story_index": i, "narration": narrations[i], "on_screen": f"Story number {i}"} for i in range(n)],
        "caption_intro": "Intro", "hashtags": ["#a"]})
    with patch.object(config, "VIDEO_STORIES", {"tamilnadu": n_per_region, "india": n_per_region}):
        vs = script.build_script(DAY, stories, draft)
    (run / "script.json").write_text(vs.model_dump_json())

    mdir = root / "media"
    mdir.mkdir()
    clip, photo = mdir / "clip.mp4", mdir / "photo.jpg"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=2",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    from PIL import Image
    Image.new("RGB", (1600, 900), (40, 90, 60)).save(photo)
    items = [{"scene_index": 0, "type": "presenter"}, {"scene_index": 1, "type": "video", "path": str(clip)}]
    if n >= 2:
        items.append({"scene_index": 2, "type": "photo", "path": str(photo)})
    items.append({"scene_index": len(vs.scenes) - 1, "type": "presenter"})
    (run / "visuals.json").write_text(json.dumps({"date": DAY, "items": items}))

    scenes, start = [], 0.0
    for i, sc in enumerate(vs.scenes):
        dur = 2.2
        f = run / "audio" / f"scene_{i:02d}.mp3"
        _tone(f, dur, ff)
        text, exp = voice.spoken_form(sc.narration)
        words = captions.align_words(sc.narration, [], dur, spoken_text=text, expansions=exp)
        scenes.append({"index": i, "kind": sc.kind, "file": f"audio/scene_{i:02d}.mp3", "spoken_text": text,
                       "on_screen": sc.on_screen, "words": [{"w": w.text, "start": w.start, "end": w.end} for w in words],
                       "start": round(start, 2), "duration": dur})
        start += dur + config.SCENE_PAUSE
    (run / "audio_manifest.json").write_text(json.dumps(
        {"date": DAY, "voice": "fake", "rate": "+0%", "total_seconds": round(start, 2), "scenes": scenes}))
    return run, round(start, 2)


def test_video_preview_and_full_build():
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        with patch.object(config, "VIDEO_STORIES", {"tamilnadu": 1, "india": 1}):
            run, total = build_fixture(root)
            with patch.object(config, "RUNS_DIR", root), patch.object(config, "MUSIC_FILE", root / "none.mp3"):
                assert video.run(DAY, preview=True) is None
                previews = sorted((run / "frames").glob("scene_*.png"))
                assert len(previews) == 4 and Image.open(previews[0]).size == (1080, 1920)

                out = video.run(DAY)
        assert out.exists()
        info = media.probe(out)
        assert "1080x1920" in info and "Audio:" in info
        assert abs(media.duration_seconds(out) - total) < 1.0, (media.duration_seconds(out), total)
        level = media.mean_volume(out)
        assert level is not None and level > -45, level
        assert not (run / "work").exists() and not list(run.glob("*.txt"))  # temporary files cleaned up


def test_video_survives_missing_visuals_file():
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        with patch.object(config, "VIDEO_STORIES", {"tamilnadu": 1, "india": 1}):
            run, _ = build_fixture(root)
            (run / "visuals.json").unlink()
            with patch.object(config, "RUNS_DIR", root), patch.object(config, "MUSIC_FILE", root / "none.mp3"):
                assert video.run(DAY, preview=True) is None  # branded backgrounds, no crash


# ------------------------------------------------------------------ feed image
def test_feed_image():
    from PIL import Image
    stories = all_stories()
    assert image.render_image(stories, "15 October 2026").size == (1080, 1350)
    long = "Chief Minister inaugurates new flyover connecting two major districts after years of delay"
    uneven = [make_story(i + 1, "tamilnadu", long) for i in range(6)] + [make_story(i, "india") for i in range(1, 5)]
    assert image.render_image(uneven, "15 October 2026").size == (1080, 1350)
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / DAY).mkdir()
        (root / DAY / "stories.json").write_text(json.dumps([s.model_dump() for s in stories]))
        with patch.object(config, "RUNS_DIR", root):
            jpg = image.run(DAY)
        with Image.open(jpg) as im:
            assert im.format == "JPEG" and im.size == (1080, 1350)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print("All tests passed")
