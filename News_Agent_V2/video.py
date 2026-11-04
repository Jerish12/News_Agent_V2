"""Stage 5 (V2): compose the 1080x1920 news video.

Usage:
    python video.py --preview            # draw one preview image per scene (no audio or internet needed)
    python video.py                      # full video for today
    python video.py --date 2026-10-15

What each scene looks like:
- Story scenes: related footage or a photo (from visuals.py) filling the screen, slowly moving, with the
  header, a region tag, a sliding headline banner and word-by-word captions at the bottom.
- Presenter scenes (opening and closing): the animated news presenter in the studio, lip-synced to the
  voice, with a welcome / thank-you banner and the same captions.

Output (in runs/<date>/):
    video.mp4        H.264 + AAC, 1080x1920, ready for Instagram Reels
    frames/          preview images (only when you use --preview)
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

import anchor
import captions
import config
import graphics
import overlays
from media import ffmpeg_exe, has_audio, mean_volume, probe, run_ffmpeg  # noqa: F401  (re-exported for checkers)
from models import VideoScript
from script import load_stories, pick_for_video

log = logging.getLogger(__name__)

W, H = config.VIDEO_SIZE
COVER_SIZE = (1620, 2880)  # 1.5x the video, so slow zooms stay sharp


# ------------------------------------------------------------------ backgrounds
def cover_image(src: Path, out: Path) -> Path:
    """Centre-crop any photo to 9:16 and save it large enough for a slow zoom."""
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    target = 9 / 16
    if img.width / img.height > target:  # too wide: crop the sides
        new_w = int(img.height * target)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:  # too tall: crop top and bottom
        new_h = int(img.width / target)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    img.resize(COVER_SIZE, Image.Resampling.LANCZOS).save(out, quality=92)
    return out


def fallback_image(accent, seed: int, out: Path) -> Path:
    """Branded abstract background (gradient with soft shapes) when no footage is available."""
    import numpy as np

    img = graphics.gradient_background(accent, size=COVER_SIZE).convert("RGBA")
    rng = np.random.default_rng(seed)
    layer = Image.new("RGBA", COVER_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(9):
        cx, cy = int(rng.integers(0, COVER_SIZE[0])), int(rng.integers(300, COVER_SIZE[1] - 300))
        r = int(rng.integers(160, 520))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*accent, int(rng.integers(34, 72))))
    img = Image.alpha_composite(img, layer).convert("RGB")
    img.save(out, quality=92)
    return out


def motion_filter(mode: int, frames: int) -> str:
    """Slow Ken Burns move on a still image: zoom in, zoom out, pan right, pan left."""
    centre_x, centre_y = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    z, x = {
        0: (f"1+0.14*on/{frames}", centre_x),
        1: (f"1.14-0.14*on/{frames}", centre_x),
        2: ("1.12", f"(iw-iw/zoom)*on/{frames}"),
        3: ("1.12", f"(iw-iw/zoom)*(1-on/{frames})"),
    }[mode % 4]
    return f"zoompan=z='{z}':x='{x}':y='{centre_y}':d={frames}:s={W}x{H}:fps={config.FPS}"


# ------------------------------------------------------------------ one scene
@dataclass
class Layer:
    """An overlay. kind="still": one image, held for the whole scene. kind="sequence": a list file that
    shows different images at different times (used for the captions)."""
    src: Path
    x: str = "0"
    y: str = "0"
    kind: str = "still"


def caption_timeline(states: list[dict], total: float) -> list[tuple[int | None, float]]:
    """[(state index or None for 'nothing shown', seconds), ...] covering 0..total with no overlaps."""
    out, t = [], 0.0
    for k, st in enumerate(states):
        start = max(st["start"], t)
        if start - t > 1e-3:
            out.append((None, start - t))
        end = max(st["end"], start + 0.04)
        out.append((k, end - start))
        t = start + (end - start)
    if total - t > 1e-3:
        out.append((None, total - t))
    return out


def write_caption_sequence(states: list[dict], total: float, folder: Path, tag: str) -> Path:
    """Save the caption images and a concat list that plays them at the right moments."""
    blank = folder / f"blank_{tag}.png"
    Image.new("RGBA", (W, config.CAPTION_AREA_HEIGHT), (0, 0, 0, 0)).save(blank)
    paths = []
    for k, st in enumerate(states):
        p = folder / f"cap_{tag}_{k:02d}.png"
        st["image"].save(p)
        paths.append(p)
    lines = ["ffconcat version 1.0"]
    last = blank
    for idx, seconds in caption_timeline(states, total):
        last = paths[idx] if idx is not None else blank
        lines += [f"file '{last.resolve().as_posix()}'", f"duration {seconds:.3f}"]
    lines.append(f"file '{last.resolve().as_posix()}'")  # the concat demuxer ignores the last duration
    listing = folder / f"captions_{tag}.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing


def compose_scene(*, bg: dict, audio: Path, duration: float, layers: list[Layer], out: Path) -> None:
    """One ffmpeg pass: background + overlay layers + the scene's audio -> a short mp4."""
    fps = config.FPS
    frames = max(int(round(duration * fps)), 1)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    if bg["kind"] == "video":
        cmd += ["-stream_loop", "-1", "-i", str(bg["path"])]
    elif bg["kind"] == "image":
        cmd += ["-i", str(bg["path"])]
    else:  # "clip": a ready-made 1080x1920 video (the presenter)
        cmd += ["-i", str(bg["path"])]
    for layer in layers:
        if layer.kind == "sequence":
            cmd += ["-f", "concat", "-safe", "0", "-i", str(layer.src)]
        else:  # one frame; the overlay filter repeats it, so almost no memory is used
            cmd += ["-i", str(layer.src)]
    cmd += ["-i", str(audio)]
    audio_idx = 1 + len(layers)

    fade = "fade=t=in:st=0:d=0.12"
    if bg["kind"] == "video":
        first = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                 f"fps={fps},eq=saturation=1.12:contrast=1.04,{fade}[bg]")
    elif bg["kind"] == "image":
        first = f"[0:v]{motion_filter(bg.get('motion', 0), frames)},setsar=1,fps={fps},{fade}[bg]"
    else:  # clip
        first = f"[0:v]{fade}[bg]"
    filters, last = [first], "bg"
    for i, layer in enumerate(layers):
        source = f"{i + 1}:v"
        if layer.kind == "sequence":
            filters.append(f"[{i + 1}:v]fps={fps},format=rgba[seq{i}]")
            source = f"seq{i}"
        filters.append(f"[{last}][{source}]overlay=x='{layer.x}':y='{layer.y}':format=auto[v{i}]")
        last = f"v{i}"
    filters.append(f"[{last}]format=yuv420p[vout]")
    filters.append(f"[{audio_idx}:a]apad=pad_dur={config.SCENE_PAUSE},aresample=44100[aout]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", config.VIDEO_PRESET, "-crf", "20", "-r", str(fps),
            "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(out)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (exit code {result.returncode}):\n{result.stderr[-1800:]}")


# ------------------------------------------------------------------ graphics for a scene
@dataclass
class SceneGraphics:
    base: Image.Image
    banner: Image.Image
    banner_y: int
    states: list[dict]          # caption states with their images
    words: list[captions.Word]


def scene_words(narration: str, manifest_scene: dict | None, audio_seconds: float) -> list[captions.Word]:
    """Word timing from the voice stage, or an even spread if it is missing or out of date."""
    if manifest_scene and manifest_scene.get("words"):
        words = [captions.Word(w["w"], w["start"], w["end"]) for w in manifest_scene["words"]]
        if len(words) == len(narration.split()):
            return words
        log.warning("Caption timing does not match the script text. Run voice.py again for exact timing.")
    return captions.align_words(narration, [], audio_seconds)


def build_graphics(*, kind: str, narration: str, on_screen: str, region, position: int, total: int,
                   date_label: str, manifest_scene: dict | None, audio_seconds: float,
                   show_tag: bool) -> SceneGraphics:
    accent = graphics.ACCENTS.get(region, graphics.NEUTRAL_ACCENT)
    base = overlays.base_overlay(kind, region, position, total, date_label, accent, show_tag)
    banner = overlays.banner(kind, on_screen, overlays.banner_label(kind, position), accent)
    words = scene_words(narration, manifest_scene, audio_seconds)
    states = [{**s, "image": captions.render_state(words, s["group"], s["active"])}
              for s in captions.caption_states(words)]
    return SceneGraphics(base, banner, overlays.banner_y(kind), states, words)


def preview_image(g: SceneGraphics, background: Image.Image) -> Image.Image:
    """Approximation of a mid-scene frame, for checking the design without rendering the video."""
    img = background.convert("RGBA")
    img.alpha_composite(g.base)
    img.alpha_composite(g.banner, (0, g.banner_y))
    if g.states:
        mid = g.states[min(1, len(g.states) - 1)]
        img.alpha_composite(mid["image"], (0, config.CAPTION_Y))
    return img.convert("RGB")


# ------------------------------------------------------------------ whole video
def load_visuals(run_dir: Path) -> dict[int, dict]:
    path = run_dir / "visuals.json"
    if not path.exists():
        log.warning("No visuals.json: run visuals.py first to get footage. Using branded backgrounds.")
        return {}
    return {it["scene_index"]: it for it in json.loads(path.read_text(encoding="utf-8"))["items"]}


def scene_context(sc, chosen) -> dict:
    story = chosen[sc.story_index] if sc.kind == "story" and sc.story_index is not None else None
    return {
        "region": story.region if story else None,
        "position": (sc.story_index + 1) if story else 0,
    }


def concat_clips(clips: list[Path], out: Path) -> None:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    try:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(out)])
    finally:
        listing.unlink(missing_ok=True)


def add_music(video: Path, music: Path, total: float, out: Path) -> None:
    fade_start = max(0.0, total - 1.5)
    run_ffmpeg([
        "-i", str(video), "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        f"[1:a]volume={config.MUSIC_VOLUME},afade=t=out:st={fade_start:.2f}:d=1.5[m];"
        "[0:a][m]amix=inputs=2:duration=first:dropout_transition=0,volume=2[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", str(out),
    ])


def run(day: str, preview: bool = False) -> Path | None:
    run_dir = config.RUNS_DIR / day
    script_path = run_dir / "script.json"
    if not script_path.exists():
        raise SystemExit(f"{script_path} not found. Run script.py first.")
    script = VideoScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    chosen = pick_for_video(load_stories(day))
    visuals = load_visuals(run_dir)
    date_label = graphics.pretty_date(day)
    work = run_dir / "work"
    work.mkdir(exist_ok=True)

    manifest = None
    if not preview:
        manifest_path = run_dir / "audio_manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"{manifest_path} not found. Run voice.py first.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if len(manifest["scenes"]) != len(script.scenes):
            raise SystemExit("script.json changed after the voiceover was made. Run voice.py again.")
        if script_path.stat().st_mtime > manifest_path.stat().st_mtime:
            log.warning("script.json is newer than the voiceover. The audio may not match the text. "
                        "Run voice.py again for %s if the wording changed.", day)

    presenter = anchor.Presenter()
    clips, frames_dir = [], run_dir / "frames"
    if preview:
        frames_dir.mkdir(exist_ok=True)

    for i, sc in enumerate(script.scenes):
        ctx = scene_context(sc, chosen)
        accent = graphics.ACCENTS.get(ctx["region"], graphics.NEUTRAL_ACCENT)
        item = visuals.get(i, {"type": "presenter" if sc.kind != "story" else "fallback"})
        media = Path(item["path"]) if item.get("type") in ("video", "photo") and Path(item.get("path", "")).exists() else None
        m_scene = manifest["scenes"][i] if manifest else None
        audio_seconds = m_scene["duration"] if m_scene else sc.estimated_seconds
        g = build_graphics(kind=sc.kind, narration=sc.narration, on_screen=sc.on_screen, region=ctx["region"],
                           position=ctx["position"], total=len(chosen), date_label=date_label,
                           manifest_scene=m_scene, audio_seconds=audio_seconds,
                           show_tag=config.SHOW_VISUAL_TAG and media is not None)

        # background spec
        if sc.kind != "story":
            still = presenter.frame(1.0, 2, False)
            if preview:
                bg = {"kind": "clip", "path": None}
            else:
                seconds = m_scene["duration"] + config.SCENE_PAUSE
                presenter_clip = work / f"presenter_{i:02d}.mp4"
                anchor.render_clip(run_dir / m_scene["file"], seconds, presenter_clip, presenter, seed=i + 1)
                bg = {"kind": "clip", "path": presenter_clip}
        elif media and item["type"] == "video":
            bg = {"kind": "video", "path": media}
            still = Image.new("RGB", (W, H), graphics.NAVY)
        else:
            src = (cover_image(media, work / f"cover_{i:02d}.jpg") if media
                   else fallback_image(accent, i, work / f"cover_{i:02d}.jpg"))
            bg = {"kind": "image", "path": src, "motion": i}
            still = Image.open(src).resize((W, H))

        if preview:
            if bg["kind"] == "video":  # grab a frame of the real footage for the preview
                try:
                    shot = work / f"shot_{i:02d}.jpg"
                    run_ffmpeg(["-ss", "1", "-i", str(media), "-frames:v", "1", str(shot)])
                    still = ImageOps.fit(Image.open(shot).convert("RGB"), (W, H))
                except RuntimeError:
                    pass
            preview_image(g, still).save(frames_dir / f"scene_{i:02d}.png")
            continue

        # layers: base graphics, sliding banner, and one caption stream (a different image per spoken word)
        base_png = work / f"base_{i:02d}.png"
        g.base.save(base_png)
        banner_png = work / f"banner_{i:02d}.png"
        g.banner.save(banner_png)
        seconds = m_scene["duration"] + config.SCENE_PAUSE
        caption_list = write_caption_sequence(g.states, seconds, work, f"{i:02d}")
        layers = [
            Layer(base_png),
            Layer(banner_png, x="if(lt(t,0.15),-w,if(lt(t,0.5),-w*pow(1-(t-0.15)/0.35,3),0))", y=str(g.banner_y)),
            Layer(caption_list, y=str(config.CAPTION_Y), kind="sequence"),
        ]

        clip = work / f"clip_{i:02d}.mp4"
        log.info("Scene %d/%d (%s)", i + 1, len(script.scenes), item.get("type", "?"))
        compose_scene(bg=bg, audio=run_dir / m_scene["file"], duration=m_scene["duration"] + config.SCENE_PAUSE,
                      layers=layers, out=clip)
        clips.append(clip)

    if preview:
        shutil.rmtree(work, ignore_errors=True)
        return None

    final = run_dir / "video.mp4"
    total = manifest["total_seconds"]
    if config.MUSIC_FILE.exists():
        silent = run_dir / "video_voice_only.mp4"
        concat_clips(clips, silent)
        add_music(silent, config.MUSIC_FILE, total, final)
        silent.unlink()
        log.info("Added background music from %s", config.MUSIC_FILE)
    else:
        concat_clips(clips, final)
        log.info("No music file at %s, voice only", config.MUSIC_FILE)

    shutil.rmtree(work, ignore_errors=True)
    level = mean_volume(final)
    if level is None or level < -55:
        log.warning("The finished video has NO audible sound (level: %s). Run: python check_video.py --date %s",
                    level, day)
    else:
        log.info("Audio check passed (average level %.1f dB)", level)
    log.info("Video ready: %s (%.1fs)", final, total)
    return final


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--preview", action="store_true", help="draw one preview image per scene, no audio needed")
    args = parser.parse_args()
    out = run(args.date, preview=args.preview)
    if out:
        print(f"\nDone: {out}")
    else:
        print(f"\nPreview images saved in {config.RUNS_DIR / args.date / 'frames'}. Open them to check the look.")
