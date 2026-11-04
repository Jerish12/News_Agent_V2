"""Word-synced captions: align each displayed word to the speech, group words, draw each state.

How the timing works:
- The voice stage records when the TTS engine says each token (word or sentence).
- The text on screen (original wording, e.g. "DGCA") can differ from what was sent to the
  voice ("D G C A"), so the two letter sequences are matched and each displayed word is
  mapped to a time on the voice's own timeline.
- If the voice gave no timing at all, words are spread across the audio by their length.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

import config
import graphics

LEAD_SILENCE = 0.05   # assumed silence at the start/end when there is no timing from the voice
HOLD_AFTER_GROUP = 0.18


@dataclass
class Word:
    text: str
    start: float
    end: float


def _letters(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _strictly_increasing(xs: list[float]) -> list[float]:
    out = []
    for i, x in enumerate(xs):
        out.append(x if not out or x > out[-1] else out[-1] + 1e-6)
    return out


def _align_sequence(display_text: str, tokens: list[tuple[str, float, float]], audio_duration: float) -> list[Word]:
    """tokens: (text, start_s, end_s) from the voice, in order. May be empty.

    The displayed text and the spoken text can differ ("DGCA" vs "D G C A", "Rs 2,000" vs
    "Rs two thousand"). We match the two letter sequences, then convert each displayed word's
    position to a position in the spoken text, and from there to a time.
    """
    words = display_text.split()
    if not words:
        return []

    # letter boundaries of each displayed word
    d_counts = [max(len(_letters(w)), 1) for w in words]
    d_bounds, acc = [0], 0
    for n in d_counts:
        acc += n
        d_bounds.append(acc)
    d_str = "".join(_letters(w) or "x" for w in words)

    tokens = [t for t in tokens if _letters(t[0])]
    if not tokens:  # no timing from the voice: spread by letters across the audio
        lo, hi = LEAD_SILENCE, max(audio_duration - LEAD_SILENCE, LEAD_SILENCE + 0.1)
        total = float(d_bounds[-1])
        return [Word(w, round(lo + (hi - lo) * d_bounds[i] / total, 3),
                     round(max(lo + (hi - lo) * d_bounds[i + 1] / total, lo + (hi - lo) * d_bounds[i] / total + 0.05), 3))
                for i, w in enumerate(words)]

    # spoken text: letter boundaries of each token, and the time at each boundary
    t_counts = [len(_letters(t[0])) for t in tokens]
    s_str = "".join(_letters(t[0]) for t in tokens)
    s_bounds, acc = [0], 0
    for n in t_counts:
        acc += n
        s_bounds.append(acc)
    times = [tokens[0][1]]
    for i in range(len(tokens) - 1):
        times.append((tokens[i][2] + tokens[i + 1][1]) / 2)  # middle of the gap between tokens
    times.append(tokens[-1][2])

    # displayed-letter position -> spoken-letter position, via matching blocks
    from difflib import SequenceMatcher

    pts = [(0.0, 0.0)]
    for a, b, size in SequenceMatcher(None, d_str, s_str, autojunk=False).get_matching_blocks():
        if size:
            pts.append((float(a), float(b)))
            pts.append((float(a + size), float(b + size)))
    pts.append((float(len(d_str)), float(len(s_str))))
    pts.sort()
    xs = _strictly_increasing([p[0] for p in pts])
    ys = [p[1] for p in pts]
    ys = [max(ys[:i + 1]) for i in range(len(ys))]  # keep monotonic

    sx = _strictly_increasing([float(b) for b in s_bounds])

    def to_time(d_pos: float) -> float:
        s_pos = float(np.interp(d_pos, xs, ys))
        return float(np.interp(s_pos, sx, times))

    out = []
    for i, w in enumerate(words):
        start, end = to_time(d_bounds[i]), to_time(d_bounds[i + 1])
        out.append(Word(w, round(start, 3), round(max(end, start + 0.05), 3)))
    return out


def align_words(display_text: str, tokens: list[tuple[str, float, float]], audio_duration: float,
                spoken_text: str | None = None, expansions: list[int] | None = None) -> list[Word]:
    """Time window for each displayed word.

    spoken_text / expansions (optional): what was actually sent to the voice, and how many spoken
    words each displayed word became (e.g. "HC" -> "High Court" is 2). With these, acronyms and
    other respelled words line up exactly.
    """
    words = display_text.split()
    if spoken_text and expansions and len(expansions) == len(words) and sum(expansions) == len(spoken_text.split()):
        spoken = _align_sequence(spoken_text, tokens, audio_duration)
        out, k = [], 0
        for w, n in zip(words, expansions):
            chunk = spoken[k:k + n]
            k += n
            out.append(Word(w, chunk[0].start, max(chunk[-1].end, chunk[0].start + 0.05)))
        return out
    return _align_sequence(display_text, tokens, audio_duration)


def make_groups(words: list[Word]) -> list[list[int]]:
    """Split word indexes into short on-screen groups (at most N words / N characters)."""
    groups, cur = [], []
    for i, w in enumerate(words):
        chars = sum(len(words[j].text) + 1 for j in cur) + len(w.text)
        if cur and (len(cur) >= config.CAPTION_MAX_WORDS or chars > config.CAPTION_MAX_CHARS):
            groups.append(cur)
            cur = []
        cur.append(i)
        if w.text[-1] in ".!?;:," and len(cur) >= 2:  # break after punctuation
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def caption_states(words: list[Word]) -> list[dict]:
    """One state per spoken word: which group is visible, which word is highlighted, and when."""
    groups = make_groups(words)
    states = []
    for g, idxs in enumerate(groups):
        next_group_start = words[groups[g + 1][0]].start if g + 1 < len(groups) else None
        for pos, i in enumerate(idxs):
            start = words[i].start
            if pos + 1 < len(idxs):
                end = words[idxs[pos + 1]].start
            else:
                end = words[i].end + HOLD_AFTER_GROUP
                if next_group_start is not None:
                    end = min(end, next_group_start)
            states.append({"group": idxs, "active": i, "start": round(start, 3),
                           "end": round(max(end, start + 0.08), 3)})
    return states


def render_state(words: list[Word], group: list[int], active: int,
                 size: tuple[int, int] | None = None) -> Image.Image:
    """Transparent image with the caption group drawn, the active word highlighted."""
    w_px, h_px = size or (graphics.W, config.CAPTION_AREA_HEIGHT)
    img = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = graphics.load_font(config.FONT_BOLD, config.CAPTION_FONT_SIZE)
    max_w = w_px - graphics.MARGIN_L - graphics.MARGIN_R + 40
    space = d.textlength(" ", font=font)

    # lay out words on lines
    lines, cur, cur_w = [], [], 0.0
    for i in group:
        ww = d.textlength(words[i].text, font=font)
        if cur and cur_w + space + ww > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [], 0.0
        cur_w += (space if cur else 0) + ww
        cur.append(i)
    lines.append((cur, cur_w))

    line_h = int(config.CAPTION_FONT_SIZE * 1.25)
    y = (h_px - line_h * len(lines)) // 2
    cx = (w_px - graphics.MARGIN_R + graphics.MARGIN_L) / 2  # centred inside the safe area
    for idxs, lw in lines:
        x = cx - lw / 2
        for i in idxs:
            colour = config.CAPTION_HIGHLIGHT if i == active else graphics.WHITE
            d.text((x, y), words[i].text, font=font, fill=colour, stroke_width=8, stroke_fill=(0, 0, 0))
            x += d.textlength(words[i].text, font=font) + space
        y += line_h
    return img
