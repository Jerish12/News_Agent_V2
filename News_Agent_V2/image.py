"""Stage 6: the 1080x1350 "Top 10" feed image.

Usage:
    python image.py                    # today's runs/<date>/stories.json
    python image.py --date 2026-10-15

Output (in runs/<date>/):
    post_image.jpg    use this one for Instagram (the Graph API only accepts JPEG for images)
    post_image.png    lossless copy

Same look as the video: your profile picture + page name, orange for Tamil Nadu, blue for India.
Row height adapts if a region has more or fewer than 5 stories.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from PIL import Image, ImageDraw

import config
import graphics
from models import Story
from script import load_stories

log = logging.getLogger(__name__)

W, H = config.IMAGE_SIZE
M = 60                       # side margin
NUMBER_D = 52                # diameter of the number badge
SECTIONS = (("tamilnadu", "TAMIL NADU"), ("india", "INDIA"))


def render_image(stories: list[Story], date_label: str) -> Image.Image:
    img = graphics.gradient_background(graphics.NEUTRAL_ACCENT, size=(W, H)).convert("RGB")
    d = ImageDraw.Draw(img)

    # header (shared with the video) and title
    graphics.draw_header(img, d, graphics.NEUTRAL_ACCENT, date_label, left=M, right_margin=M, top=44, avatar_size=92)
    title_font, title_lines, title_lh = graphics.fit_text(d, config.IMAGE_TITLE, config.FONT_BOLD, W - 2 * M, 110, 84, 48)
    graphics.draw_lines(d, title_lines, title_font, M, 168, title_lh, graphics.WHITE)

    # layout: rows share the space between the title and the footer
    groups = [(r, label, sorted((s for s in stories if s.region == r), key=lambda s: s.rank)) for r, label in SECTIONS]
    groups = [g for g in groups if g[2]]
    section_overhead = 58 + 16
    y0, footer_top = 292, H - 92
    n_rows = sum(len(g[2]) for g in groups)
    row_h = min(88, (footer_top - y0 - section_overhead * len(groups)) // max(n_rows, 1))

    # one font size for every row: the largest that fits the longest headline
    text_x = M + NUMBER_D + 24
    text_w = W - M - text_x
    headlines = [s.headline for _, _, items in groups for s in items]
    size = 40
    while size > 24:
        font = graphics.load_font(config.FONT_BOLD, size)
        if all(len(graphics.wrap(d, h, font, text_w)) * int(size * 1.15) <= row_h - 8 for h in headlines):
            break
        size -= 2
    font, lh = graphics.load_font(config.FONT_BOLD, size), int(size * 1.15)

    y = y0
    for region, label, items in groups:
        accent = graphics.ACCENTS[region]
        label_font = graphics.load_font(config.FONT_BOLD, 34)
        d.text((M, y), label, font=label_font, fill=accent)
        line_x = M + d.textlength(label, font=label_font) + 24
        d.line([(line_x, y + 21), (W - M, y + 21)], fill=graphics.lerp(graphics.NAVY, accent, 0.55), width=3)
        y += 58

        for i, story in enumerate(items, 1):
            cy = y + row_h // 2
            d.ellipse([M, cy - NUMBER_D // 2, M + NUMBER_D, cy + NUMBER_D // 2], fill=accent)
            num_font = graphics.load_font(config.FONT_BOLD, 30)
            d.text((M + NUMBER_D / 2 - d.textlength(str(i), font=num_font) / 2, cy - 19), str(i), font=num_font, fill=graphics.NAVY)

            lines = graphics.wrap(d, story.headline, font, text_w)
            block_h = len(lines) * lh
            graphics.draw_lines(d, lines, font, text_x, cy - block_h // 2, lh, graphics.WHITE)
            if i < len(items):
                d.line([(text_x, y + row_h - 1), (W - M, y + row_h - 1)], fill=graphics.lerp(graphics.NAVY, graphics.WHITE, 0.14), width=1)
            y += row_h
        y += 16

    # footer
    foot_font = graphics.load_font(config.FONT_BOLD, 30)
    d.text(((W - d.textlength(config.IMAGE_FOOTER, font=foot_font)) / 2, H - 66), config.IMAGE_FOOTER,
           font=foot_font, fill=graphics.NEUTRAL_ACCENT)
    return img


def run(day: str):
    stories = load_stories(day)
    img = render_image(stories, graphics.pretty_date(day))
    out_dir = config.RUNS_DIR / day
    png, jpg = out_dir / "post_image.png", out_dir / "post_image.jpg"
    img.save(png)
    img.save(jpg, "JPEG", quality=95, subsampling=0)
    log.info("Saved %s and %s", jpg, png)
    return jpg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    out = run(parser.parse_args().date)
    print(f"\nDone: {out}\nOpen it and check it before posting.")
