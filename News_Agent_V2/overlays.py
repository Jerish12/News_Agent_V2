"""Graphics drawn on top of the footage: header, tags, scrims and the headline banner.

All functions return transparent RGBA images the size of the video (or the banner's own size),
which ffmpeg then lays over the background at the right moment.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

import config
import graphics

W, H = config.VIDEO_SIZE
NAVY = graphics.NAVY


def scrim(y0: int, y1: int, a0: int, a1: int) -> Image.Image:
    """Black vertical gradient (alpha a0 at y0 to a1 at y1), transparent elsewhere."""
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    alphas = np.linspace(a0, a1, max(y1 - y0, 1)).astype(np.uint8)
    arr[y0:y1, :, 3] = alphas[:, None]
    return Image.fromarray(arr, "RGBA")


def _tag(img: Image.Image, x: int, y: int, text: str, size: int, fg, bg_alpha: int = 120) -> int:
    """Small translucent pill with text. Returns the x where it ends."""
    font = graphics.load_font(config.FONT_REGULAR, size)
    d = ImageDraw.Draw(img)
    w = int(d.textlength(text, font=font)) + 36
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([x, y, x + w, y + size + 22], radius=(size + 22) // 2, fill=(0, 0, 0, bg_alpha))
    img.alpha_composite(layer)
    ImageDraw.Draw(img).text((x + 18, y + 9), text, font=font, fill=fg)
    return x + w


def base_overlay(kind: str, region, position: int, total: int, date_label: str, accent, show_tag: bool) -> Image.Image:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if kind == "story":
        img.alpha_composite(scrim(0, 480, 200, 0))
        img.alpha_composite(scrim(900, H, 0, 225))
    else:
        img.alpha_composite(scrim(0, 300, 150, 0))
    d = ImageDraw.Draw(img)

    graphics.draw_header(img, d, accent, date_label, left=graphics.MARGIN_L, right_margin=graphics.MARGIN_R,
                         top=96, avatar_size=graphics.AVATAR_SIZE)

    if kind == "story":
        gap, seg_h, y0 = 8, 10, 236  # progress bar, one segment per story
        text_w = W - graphics.MARGIN_L - graphics.MARGIN_R
        seg_w = (text_w - gap * (total - 1)) / total
        for i in range(total):
            x0 = graphics.MARGIN_L + i * (seg_w + gap)
            colour = accent if i < position else (255, 255, 255, 70)
            d.rounded_rectangle([x0, y0, x0 + seg_w, y0 + seg_h], radius=5, fill=colour)

        pill_font = graphics.load_font(config.FONT_BOLD, 40)
        label = graphics.REGION_LABEL.get(region, "NEWS")
        pw = d.textlength(label, font=pill_font) + 60
        d.rounded_rectangle([graphics.MARGIN_L, 290, graphics.MARGIN_L + pw, 290 + 74], radius=37, fill=accent)
        d.text((graphics.MARGIN_L + 30, 290 + 11), label, font=pill_font, fill=NAVY)
        end = graphics.MARGIN_L + pw + 22
        d.text((end, 290 + 14), f"{position} / {total}", font=graphics.load_font(config.FONT_REGULAR, 42), fill=(235, 240, 250))
        if show_tag:
            x = end + d.textlength(f"{position} / {total}", font=graphics.load_font(config.FONT_REGULAR, 42)) + 26
            _tag(img, int(x), 298, config.VISUAL_TAG_TEXT, 28, (235, 240, 250))
    elif config.SHOW_PRESENTER_LABEL:
        _tag(img, graphics.MARGIN_L, 232, config.PRESENTER_LABEL, 30, (255, 255, 255), bg_alpha=140)
    return img


def banner_y(kind: str) -> int:
    return config.BANNER_Y if kind == "story" else config.PRESENTER_BANNER_Y


def banner(kind: str, text: str, label: str, accent) -> Image.Image:
    """TV-style lower third: a coloured label tab above a dark card with the headline."""
    bw = W - 70
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    text_w = bw - 90
    max_lines = 2 if kind == "story" else 1  # presenter banners stay on one line, clear of the captions
    font, lines, lh = graphics.fit_text(scratch, text.upper() if kind != "story" else text, config.FONT_BOLD,
                                        text_w, max_lines * 82, 74, 40, 1.12)
    card_h = len(lines) * lh + 52
    tab_h = 58
    img = Image.new("RGBA", (bw, tab_h + card_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    tab_font = graphics.load_font(config.FONT_BOLD, 32)
    tab_w = int(d.textlength(label, font=tab_font)) + 56
    d.rounded_rectangle([0, 0, tab_w + 30, tab_h + 20], radius=14, fill=accent)  # bottom corners hidden by the card
    d.rounded_rectangle([0, tab_h, bw, tab_h + card_h], radius=26, fill=(*NAVY, 240))
    d.rectangle([0, tab_h, 26, tab_h + card_h], fill=(*NAVY, 240))
    d.rectangle([0, tab_h, 16, tab_h + card_h], fill=accent)
    d.text((28, 9), label, font=tab_font, fill=NAVY)
    graphics.draw_lines(d, lines, font, 52, tab_h + 26, lh, graphics.WHITE)
    return img


def banner_label(kind: str, position: int) -> str:
    return {"hook": "WELCOME", "outro": "THANK YOU"}.get(kind, f"TOP STORY {position}")
