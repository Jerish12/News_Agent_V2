"""Shared drawing helpers (fonts, text wrapping, backgrounds, profile picture, header).

Used by the video overlays, the presenter studio and the feed image, so they all look consistent.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config

log = logging.getLogger(__name__)

W, H = config.VIDEO_SIZE
NAVY = (11, 18, 32)
WHITE = (255, 255, 255)
MUTED = (170, 180, 200)
NEUTRAL_ACCENT = (45, 212, 191)
ACCENTS = {"tamilnadu": (251, 146, 60), "india": (56, 189, 248)}
REGION_LABEL = {"tamilnadu": "TAMIL NADU", "india": "INDIA"}

AVATAR_SIZE = 108
_AVATAR_CACHE: dict = {}

# Safe area: Instagram covers the bottom ~15-20% and a strip on the right with buttons
MARGIN_L, MARGIN_R = 80, 150


def load_font(candidates: list[str], size: int):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    log.warning("No TrueType font found, using Pillow's default. Add assets/fonts/bold.ttf and regular.ttf")
    return ImageFont.load_default(size)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, candidates, max_w, max_h, max_size, min_size, spacing=1.18):
    """Largest font size where the wrapped text fits inside max_w x max_h."""
    size = max_size
    while True:
        font = load_font(candidates, size)
        lines = wrap(draw, text, font, max_w)
        line_h = int(size * spacing)
        if len(lines) * line_h <= max_h or size <= min_size:
            return font, lines, line_h
        size -= 4


def draw_lines(draw, lines, font, x, y, line_h, fill, center_x=None):
    for line in lines:
        if center_x is not None:
            x = center_x - draw.textlength(line, font=font) / 2
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def gradient_background(accent, size=None) -> Image.Image:
    w, h = size or (W, H)
    img = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(img)
    top = lerp(NAVY, accent, 0.28)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, NAVY, min(1.0, y / (h * 0.75))))
    return img


def pretty_date(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.day} {d:%B %Y}"


def get_avatar(size: int):
    """The profile picture as a circular RGBA image, or None if it can't be used."""
    raw = getattr(config, "PROFILE_PICTURE", "")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = config.BASE_DIR / path
    key = (str(path), size, path.stat().st_mtime if path.exists() else None)
    if key in _AVATAR_CACHE:
        return _AVATAR_CACHE[key]

    avatar = None
    if not path.exists():
        log.warning("Profile picture not found at %s. Check PROFILE_PICTURE in config.py. "
                    "Continuing without it.", path)
    else:
        try:
            img = Image.open(path).convert("RGB")
            side = min(img.size)  # centre-crop to a square
            left, top = (img.width - side) // 2, (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize(
                (size, size), Image.Resampling.LANCZOS)
            scale = 4  # draw the circle bigger, then shrink, for smooth edges
            mask = Image.new("L", (size * scale, size * scale), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, size * scale - 1, size * scale - 1], fill=255)
            avatar = img.convert("RGBA")
            avatar.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
        except OSError as exc:
            log.warning("Could not read the profile picture %s (%s). Continuing without it.", path, exc)
    _AVATAR_CACHE[key] = avatar
    return avatar


def draw_header(img: Image.Image, d: ImageDraw.ImageDraw, accent, date_label: str, *,
                left: int, right_margin: int, top: int, avatar_size: int) -> int:
    """Profile picture (circle with accent ring) + page name + date."""
    text_x = left
    avatar = get_avatar(avatar_size)
    if avatar:
        d.ellipse([left - 6, top - 6, left + avatar_size + 5, top + avatar_size + 5], fill=accent)
        img.paste(avatar, (left, top), avatar)
        text_x = left + avatar_size + 28
    name = config.PAGE_NAME.upper()
    name_size, avail = 38, img.width - right_margin - text_x
    while name_size > 24 and d.textlength(name, font=load_font(config.FONT_BOLD, name_size)) > avail:
        name_size -= 2
    d.text((text_x, top + 20), name, font=load_font(config.FONT_BOLD, name_size), fill=WHITE)
    d.text((text_x, top + 72), date_label, font=load_font(config.FONT_REGULAR, 34), fill=MUTED)
    return text_x
