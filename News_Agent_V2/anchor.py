"""The animated female news presenter (an illustrated virtual presenter, drawn in code).

She sits in a TV-style studio, her mouth opens and closes with the loudness of the voiceover
(lip-sync), she blinks, and she sways a little, so she reads the opening and closing like a news
channel presenter. She is an illustration (see presenter_art.py), and the video labels her
"AI NEWS PRESENTER".

- build_static():  studio + figure + desk (drawn once)
- build_heads():   8 head variants (4 mouth shapes x eyes open/closed)
- Presenter.frame(t, mouth, blink): composes one frame quickly
- render_clip(): audio -> loudness per frame -> frames piped into ffmpeg -> silent mp4
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import config
import graphics
import presenter_art
from media import ffmpeg_exe

log = logging.getLogger(__name__)

W, H = 1080, 1920
DESK_TOP_Y = 1470
HEAD_BOX = presenter_art.HEAD_BOX


# ---------------------------------------------------------------- studio
def build_studio(accent=graphics.NEUTRAL_ACCENT) -> Image.Image:
    img = Image.new("RGB", (W, H), (8, 16, 36))
    d = ImageDraw.Draw(img)
    for y in range(H):  # deep blue gradient
        d.line([(0, y), (W, y)], fill=graphics.lerp((14, 30, 62), (5, 9, 22), y / H))

    # soft light panels and bokeh for depth
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for x0, w in ((40, 120), (250, 70), (770, 70), (920, 120)):
        g.rectangle([x0, 140, x0 + w, 1480], fill=(120, 180, 255, 14))
    rng = np.random.default_rng(7)
    for _ in range(26):
        cx, cy, r = int(rng.integers(0, W)), int(rng.integers(120, 1200)), int(rng.integers(14, 46))
        g.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*accent, int(rng.integers(10, 30))))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)

    # studio screen with the page branding (above her head so nothing is hidden)
    sx0, sy0, sx1, sy1 = 110, 300, 970, 536
    d.rounded_rectangle([sx0 - 8, sy0 - 8, sx1 + 8, sy1 + 8], radius=30, fill=(70, 190, 210))
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=24, fill=(10, 34, 74))
    for y in range(sy0, sy1):
        d.line([(sx0 + 12, y), (sx1 - 12, y)], fill=graphics.lerp((22, 70, 130), (8, 26, 60), (y - sy0) / (sy1 - sy0)))
    avatar = graphics.get_avatar(150)
    text_x = sx0 + 60
    if avatar:
        d.ellipse([sx0 + 44, sy0 + 42, sx0 + 44 + 158, sy0 + 42 + 158], fill=accent)
        img.paste(avatar, (sx0 + 48, sy0 + 46), avatar)
        text_x = sx0 + 250
    d.text((text_x, sy0 + 24), "DAILY BRIEF", font=graphics.load_font(config.FONT_BOLD, 34), fill=accent)
    d.text((text_x, sy0 + 58), "TOP 10", font=graphics.load_font(config.FONT_BOLD, 108), fill=graphics.WHITE)
    d.text((text_x, sy0 + 174), "TAMIL NADU  |  INDIA", font=graphics.load_font(config.FONT_REGULAR, 34), fill=(190, 215, 240))
    return img


# ---------------------------------------------------------------- scene assembly
def build_static(accent=graphics.NEUTRAL_ACCENT) -> Image.Image:
    """Studio + the presenter's figure + desk. Drawn once, reused for every frame."""
    base = build_studio(accent).convert("RGBA")
    base = Image.alpha_composite(base, presenter_art.draw_figure((W, H), config.PRESENTER_STYLE, config.PRESENTER_SAREE_COLOR))

    desk = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(desk)
    for y in range(DESK_TOP_Y, H):
        dd.line([(0, y), (W, y)], fill=(*graphics.lerp((22, 32, 54), (6, 10, 20), (y - DESK_TOP_Y) / (H - DESK_TOP_Y)), 255))
    dd.rectangle([0, DESK_TOP_Y, W, DESK_TOP_Y + 8], fill=(*accent, 255))
    dd.rectangle([0, DESK_TOP_Y + 8, W, DESK_TOP_Y + 40], fill=(255, 255, 255, 18))
    return Image.alpha_composite(base, desk).convert("RGB")


def build_heads() -> dict:
    return presenter_art.build_heads(config.PRESENTER_STYLE)


class Presenter:
    def __init__(self, accent=graphics.NEUTRAL_ACCENT):
        self.static = build_static(accent)
        self.heads = build_heads()

    def frame(self, t: float, mouth: int, blink: bool) -> Image.Image:
        img = self.static.copy()
        # tiny head movement and breathing so she does not look frozen
        dx = round(2.5 * np.sin(2 * np.pi * t / 4.3))
        dy = round(1.5 * np.sin(2 * np.pi * t / 3.1))
        head = self.heads[(mouth, blink)]
        img.paste(head, (HEAD_BOX[0] + dx, HEAD_BOX[1] + dy), head)
        return img


# ---------------------------------------------------------------- lip-sync
def audio_envelope(audio: Path, fps: int, n_frames: int) -> np.ndarray:
    """Loudness (0 to 1) for each video frame, from the voiceover file."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-loglevel", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
    )
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    per = 16000 // fps
    usable = (len(samples) // per) * per
    rms = np.sqrt((samples[:usable].reshape(-1, per) ** 2).mean(axis=1)) if usable else np.zeros(1)
    peak = np.percentile(rms, 95) if len(rms) and rms.max() > 0 else 1.0
    env = np.clip(rms / max(peak, 1e-6), 0, 1)
    env = np.convolve(env, np.ones(3) / 3, mode="same")  # smooth
    out = np.zeros(n_frames, dtype=np.float32)
    out[: min(n_frames, len(env))] = env[:n_frames]
    return out


def mouth_states(env: np.ndarray) -> list[int]:
    raw = np.digitize(env, [0.10, 0.28, 0.55])  # 0 closed .. 3 wide
    out = raw.copy()
    for i in range(1, len(raw) - 1):  # remove one-frame flicker
        if raw[i - 1] == raw[i + 1] != raw[i]:
            out[i] = raw[i - 1]
    return [int(v) for v in out]


def blink_frames(n_frames: int, fps: int, seed: int) -> set[int]:
    rng = np.random.default_rng(seed)
    frames, t = set(), float(rng.uniform(0.9, 1.8))
    while int(t * fps) < n_frames:
        start = int(t * fps)
        frames.update(range(start, start + 4))  # about 0.13 s
        t += float(rng.uniform(2.6, 4.2))
    return frames


def render_clip(audio: Path, seconds: float, out: Path, presenter: Presenter | None = None, seed: int = 1,
                accent=graphics.NEUTRAL_ACCENT) -> None:
    """Silent mp4 of the presenter speaking `audio`, `seconds` long (audio + pause)."""
    fps = config.FPS
    n = max(int(round(seconds * fps)), 1)
    presenter = presenter or Presenter(accent)
    mouths = mouth_states(audio_envelope(audio, fps, n))
    blinks = blink_frames(n, fps, seed)

    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-frames:v", str(n), "-c:v", "libx264", "-preset", config.VIDEO_PRESET, "-crf", "20",
           "-pix_fmt", "yuv420p", "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            proc.stdin.write(presenter.frame(i / fps, mouths[i], i in blinks).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed while drawing the presenter:\n{err[-1200:]}")
    except BrokenPipeError:
        raise RuntimeError(f"ffmpeg stopped early:\n{proc.stderr.read().decode(errors='replace')[-1200:]}")
