"""Artwork for the news presenter: a young professional woman, drawn in code with soft shading.

Two pieces:
- draw_figure():  hair behind her, shoulders, blazer, blouse, neck and necklace (drawn once)
- build_head():   face, features, hair in front, earrings, for one mouth shape and eye state

Everything is drawn at high resolution and shrunk for smooth edges. Shading is done with blurred,
clipped layers, which gives the soft, realistic look instead of flat cartoon colours.
"""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 1080, 1920

# ---- colours
SKIN = (203, 151, 113)
SKIN_SHADOW = (148, 96, 70)
SKIN_LIGHT = (232, 184, 146)
HAIR = (27, 20, 24)
HAIR_MID = (52, 38, 40)
HAIR_LIGHT = (104, 76, 66)
BROW = (40, 28, 30)
LIP_UPPER = (170, 50, 72)
LIP_LOWER = (190, 66, 88)
LIP_LINE = (112, 26, 44)
MOUTH_DARK = (66, 16, 28)
TEETH = (248, 245, 240)
BLAZER = (150, 30, 66)
BLAZER_DARK = (104, 18, 46)
BLAZER_LIGHT = (196, 62, 100)
BLOUSE = (246, 238, 228)
BLOUSE_SHADOW = (206, 190, 178)
GOLD = (234, 188, 76)
PEARL = (244, 240, 234)

FIG_K = 1.16          # whole figure drawn this much bigger, around the head
PIVOT = (540, 800)


def fig(x: float, y: float) -> tuple[int, int]:
    return (round(PIVOT[0] + (x - PIVOT[0]) * FIG_K), round(PIVOT[1] + (y - PIVOT[1]) * FIG_K))


HEAD_BOX = (*fig(318, 540), *fig(762, 1200))


def mirror(points):
    """Mirror points across the centre line x=540 (used to make the right side from the left)."""
    return [(1080 - x, y) for x, y in points]


def chaikin(points, closed=True, iterations=3):
    """Corner cutting: turns a rough outline into a smooth curve."""
    pts = list(points)
    for _ in range(iterations):
        new = []
        n = len(pts)
        rng = range(n) if closed else range(n - 1)
        if not closed:
            new.append(pts[0])
        for i in rng:
            p, q = pts[i], pts[(i + 1) % n]
            new.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            new.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        if not closed:
            new.append(pts[-1])
        pts = new
    return pts


class Pen:
    """Draws in normal (1x) coordinates onto a high-resolution canvas, relative to an origin."""

    def __init__(self, size, origin=(0, 0), k=1.0, scale=3):
        self.size, self.origin, self.k, self.S = size, origin, k, scale
        self.img = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def layer(self) -> "Pen":
        return Pen(self.size, self.origin, self.k, self.S)

    def _p(self, x, y):
        if self.k != 1.0:
            x = PIVOT[0] + (x - PIVOT[0]) * self.k
            y = PIVOT[1] + (y - PIVOT[1]) * self.k
        return ((x - self.origin[0]) * self.S, (y - self.origin[1]) * self.S)

    def _box(self, b):
        x0, y0 = self._p(b[0], b[1])
        x1, y1 = self._p(b[2], b[3])
        return [x0, y0, x1, y1]

    def ellipse(self, box, fill):
        self.d.ellipse(self._box(box), fill=fill)

    def rect(self, box, fill, radius=0):
        if radius:
            self.d.rounded_rectangle(self._box(box), radius=radius * self.S * self.k, fill=fill)
        else:
            self.d.rectangle(self._box(box), fill=fill)

    def poly(self, pts, fill, smooth=0, closed=True):
        if smooth:
            pts = chaikin(pts, closed=True, iterations=smooth)
        self.d.polygon([self._p(x, y) for x, y in pts], fill=fill)

    def line(self, pts, fill, width, smooth=0):
        if smooth:
            pts = chaikin(pts, closed=False, iterations=smooth)
        self.d.line([self._p(x, y) for x, y in pts], fill=fill, width=max(int(width * self.S * self.k), 1), joint="curve")

    def arc(self, box, start, end, fill, width):
        self.d.arc(self._box(box), start, end, fill=fill, width=max(int(width * self.S * self.k), 1))

    def alpha(self) -> Image.Image:
        return self.img.getchannel("A")

    def paint(self, top: "Pen", mask: "Pen | None" = None, blur: float = 0.0, opacity: float = 1.0):
        """Lay another layer over this one, optionally softened (blur) and clipped to a mask's shape."""
        layer = top.img
        if blur:
            layer = layer.filter(ImageFilter.GaussianBlur(blur * self.S))
        a = layer.getchannel("A")
        if mask is not None:
            a = ImageChops.multiply(a, mask.alpha())
        if opacity < 1.0:
            a = a.point(lambda v: int(v * opacity))
        layer = layer.copy()
        layer.putalpha(a)
        self.img = Image.alpha_composite(self.img, layer)
        self.d = ImageDraw.Draw(self.img)

    def result(self) -> Image.Image:
        return self.img.resize(self.size, Image.Resampling.LANCZOS)


# =================================================================== the figure (drawn once)
def _hair_back_long(pen: Pen):
    left = [(540, 560), (484, 566), (430, 596), (398, 650), (382, 730), (372, 830), (362, 940), (352, 1030), (350, 1100)]
    outline = left + mirror(left)[::-1]
    mask = pen.layer()
    mask.poly(outline, (255, 255, 255, 255), smooth=3)
    pen.poly(outline, HAIR, smooth=3)
    glow = pen.layer()
    for x0 in (410, 470):
        glow.line([(x0, 640), (x0 - 18, 820), (x0 - 28, 1000)], (*HAIR_LIGHT, 140), 16, smooth=2)
    glow.line([(700, 650), (716, 830), (722, 1010)], (*HAIR_LIGHT, 110), 14, smooth=2)
    pen.paint(glow, mask, blur=7, opacity=0.8)


def _blazer(pen: Pen):
    left = [(486, 1006), (428, 1020), (362, 1044), (306, 1074), (268, 1112), (250, 1170), (244, 1260), (244, 1800)]
    outline = left + mirror(left)[::-1]
    mask = pen.layer()
    mask.poly(outline, (255, 255, 255, 255), smooth=2)
    pen.poly(outline, BLAZER, smooth=2)

    shade = pen.layer()  # darker toward the sides and the arms, lighter on the shoulders
    shade.rect((230, 1060, 330, 1800), (60, 6, 30, 170))
    shade.rect((750, 1060, 850, 1800), (60, 6, 30, 170))
    shade.line([(300, 1090), (400, 1040), (470, 1018)], (255, 130, 160, 150), 12, smooth=2)
    shade.line([(780, 1090), (680, 1040), (610, 1018)], (255, 130, 160, 120), 12, smooth=2)
    pen.paint(shade, mask, blur=18)


def _neck_and_blouse(pen: Pen):
    # blouse: only the part visible in the V of the jacket
    blouse = [(466, 1012), (614, 1012), (634, 1070), (540, 1210), (446, 1070)]
    pen.poly(blouse, BLOUSE, smooth=1)

    # neck and V-neckline skin
    skin = [(500, 900), (580, 900), (592, 998), (606, 1030), (540, 1160), (474, 1030), (488, 998)]
    mask = pen.layer()
    mask.poly(skin, (255, 255, 255, 255), smooth=1)
    pen.poly(skin, SKIN, smooth=1)
    shade = pen.layer()
    shade.rect((490, 900, 520, 1050), (*SKIN_SHADOW, 90))       # neck side shadows
    shade.rect((562, 900, 592, 1050), (*SKIN_SHADOW, 90))
    shade.ellipse((486, 880, 594, 975), (*SKIN_SHADOW, 105))    # under the jaw
    shade.ellipse((520, 1060, 560, 1130), (*SKIN_LIGHT, 90))    # collarbone light
    pen.paint(shade, mask, blur=9)

    # the jacket closes below the lapels, with a centre seam and a button
    closure = [(400, 1176), (520, 1304), (540, 1322), (560, 1304), (680, 1176), (684, 1800), (396, 1800)]
    pen.poly(closure, BLAZER, smooth=1)
    seam = pen.layer()
    seam.line([(540, 1322), (540, 1800)], (*BLAZER_DARK, 220), 4)
    seam.line([(402, 1200), (404, 1800)], (*BLAZER_DARK, 140), 6)
    seam.line([(678, 1200), (680, 1800)], (*BLAZER_DARK, 140), 6)
    pen.paint(seam, blur=2)
    pen.ellipse((528, 1384, 552, 1408), (*GOLD, 255))
    pen.ellipse((533, 1389, 547, 1403), (250, 214, 130, 255))

    # lapels
    lapel = [(448, 1008), (486, 1002), (540, 1158), (518, 1300), (404, 1170), (418, 1060)]
    for pts in (lapel, mirror(lapel)):
        pen.poly(pts, BLAZER_DARK, smooth=1)
    edge = pen.layer()
    edge.line([(486, 1004), (540, 1156)], (*BLAZER_LIGHT, 200), 4)
    edge.line([(594, 1004), (540, 1156)], (*BLAZER_LIGHT, 200), 4)
    pen.paint(edge, blur=1.2)

    # necklace with a small pendant, and the lapel microphone
    pen.line([(498, 1008), (516, 1070), (540, 1096), (564, 1070), (582, 1008)], GOLD, 3, smooth=2)
    pen.ellipse((533, 1094, 547, 1114), GOLD)
    pen.ellipse((536, 1098, 544, 1106), (255, 232, 160))
    pen.line([(447, 1078), (455, 1030)], (22, 22, 28), 2)
    pen.rect((444, 1076, 458, 1108), (24, 24, 30), radius=5)


def _figure_blazer(pen: Pen):
    _hair_back_long(pen)
    _blazer(pen)
    _neck_and_blouse(pen)


def draw_figure(canvas_size=(W, H), style: str = "saree", saree_rgb=(16, 128, 96)) -> Image.Image:
    pen = Pen(canvas_size, k=FIG_K, scale=2)
    if style == "blazer":
        _figure_blazer(pen)
    else:
        _figure_saree(pen, saree_rgb)
    return pen.result()


# =================================================================== saree style (Tamil news presenter look)
SAREE_GOLD = (224, 180, 84)
SAREE_GOLD_DARK = (150, 104, 36)


def _shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def _hair_back_bob(pen: Pen):
    """Voluminous, wavy shoulder-length hair behind her head."""
    left = [(540, 558), (468, 572), (414, 614), (384, 688), (372, 770), (376, 850), (364, 922), (380, 984),
            (412, 1000), (440, 1006), (470, 1018)]
    outline = left + mirror(left)[::-1]
    mask = pen.layer()
    mask.poly(outline, (255, 255, 255, 255), smooth=3)
    pen.poly(outline, HAIR, smooth=3)
    curls = pen.layer()
    for x, y in [(412, 680), (398, 780), (394, 880), (400, 950), (668, 690), (682, 790), (686, 890), (680, 955)]:
        curls.arc((x - 26, y - 34, x + 26, y + 34), 200, 340, (*HAIR_LIGHT, 170), 8)
    pen.paint(curls, mask, blur=3)


def _hair_front_bob(pen: Pen):
    """Wavy side locks framing the face and a side-swept crown (soft shapes, curls shown by highlights)."""
    mask = pen.layer()
    left_lock = [(452, 690), (428, 742), (414, 810), (408, 880), (412, 950), (432, 990), (458, 960), (462, 880),
                 (456, 800), (450, 750)]
    right_lock = [(1080 - x + (4 if i % 2 else -2), y + (6 if i % 3 == 0 else 0)) for i, (x, y) in enumerate(left_lock)]
    for lock in (left_lock, right_lock):
        pen.poly(lock, HAIR, smooth=3)
        mask.poly(lock, (255, 255, 255, 255), smooth=3)

    hairline = [(444, 756), (444, 710), (462, 678), (490, 662), (514, 656), (556, 660), (600, 672), (634, 698), (654, 730), (662, 768)]
    dome = [(690, 740), (688, 672), (668, 620), (626, 586), (576, 568), (540, 562), (500, 566), (452, 584), (420, 616), (404, 664), (408, 722)]
    cap = hairline + dome
    pen.poly(cap, HAIR, smooth=3)
    mask.poly(cap, (255, 255, 255, 255), smooth=3)

    shine = pen.layer()
    for cx, cy in [(436, 760), (424, 826), (418, 894), (426, 958), (650, 764), (662, 832), (668, 900), (660, 962)]:
        shine.arc((cx - 18, cy - 28, cx + 18, cy + 28), 200, 340, (*HAIR_LIGHT, 200), 7)
    shine.line([(470, 600), (540, 580), (620, 600), (660, 650)], (*HAIR_LIGHT, 160), 10, smooth=2)
    shine.line([(440, 640), (430, 700)], (*HAIR_LIGHT, 130), 8, smooth=1)
    shine.line([(500, 640), (560, 636), (622, 668)], (*HAIR_MID, 230), 8, smooth=2)
    shine.line([(470, 690), (520, 656)], (*HAIR_LIGHT, 120), 7, smooth=1)
    pen.paint(shine, mask, blur=2.4)


def _earrings_gold(pen: Pen):
    """Small gold jhumka-style drops."""
    for x in (438, 642):
        pen.ellipse((x - 6, 868, x + 6, 880), SAREE_GOLD)
        pen.poly([(x - 8, 884), (x + 8, 884), (x + 12, 904), (x - 12, 904)], SAREE_GOLD, smooth=1)
        pen.ellipse((x - 3, 904, x + 3, 910), SAREE_GOLD)
        pen.ellipse((x - 5, 888, x - 1, 892), (255, 238, 170))


def _bindi(pen: Pen):
    pen.ellipse((534, 716, 546, 728), (176, 22, 44))
    pen.ellipse((537, 718, 541, 722), (230, 90, 100))


def _blouse_and_saree(pen: Pen, rgb):
    base, dark, light = rgb, _shade(rgb, 0.58), _shade(rgb, 1.35)
    blouse = _shade(rgb, 0.82)

    # blouse: shoulders and sleeves
    left = [(486, 1006), (428, 1020), (362, 1044), (306, 1074), (268, 1112), (250, 1170), (244, 1260), (244, 1800)]
    outline = left + mirror(left)[::-1]
    body_mask = pen.layer()
    body_mask.poly(outline, (255, 255, 255, 255), smooth=2)
    pen.poly(outline, blouse, smooth=2)
    shade = pen.layer()
    shade.rect((230, 1060, 330, 1800), (*_shade(rgb, 0.3), 170))
    shade.rect((750, 1060, 850, 1800), (*_shade(rgb, 0.3), 170))
    pen.paint(shade, body_mask, blur=18)

    # neck and V-neckline skin, gold piping on the blouse neckline, necklace
    skin = [(500, 900), (580, 900), (594, 998), (556, 1006), (522, 1092), (478, 1010), (488, 998)]
    skin_mask = pen.layer()
    skin_mask.poly(skin, (255, 255, 255, 255), smooth=1)
    pen.poly(skin, SKIN, smooth=1)
    sh = pen.layer()
    sh.rect((490, 900, 520, 1050), (*SKIN_SHADOW, 90))
    sh.rect((562, 900, 592, 1050), (*SKIN_SHADOW, 90))
    sh.ellipse((486, 880, 594, 975), (*SKIN_SHADOW, 105))
    sh.ellipse((510, 1040, 556, 1100), (*SKIN_LIGHT, 80))
    pen.paint(sh, skin_mask, blur=9)
    pen.line([(478, 1010), (522, 1092)], SAREE_GOLD, 4)
    pen.line([(496, 1006), (506, 1040), (524, 1070), (546, 1050), (566, 1010)], SAREE_GOLD, 2, smooth=2)
    pen.ellipse((519, 1066, 531, 1082), SAREE_GOLD)

    # the saree: pallu draped over her shoulder and across the chest
    edge = [(392 + 160 * t, 1400 - 398 * t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]  # diagonal edge, bottom to top
    pallu = [(552, 1002), (640, 1010), (738, 1044), (802, 1094), (826, 1170), (832, 1400), (392, 1400)] + edge[1:4]
    pallu_mask = pen.layer()
    pallu_mask.poly(pallu, (255, 255, 255, 255), smooth=1)
    pen.poly(pallu, base, smooth=1)

    folds = pen.layer()  # pleats on the shoulder and soft folds across the chest
    for i, x in enumerate((620, 650, 680, 710, 740, 770)):
        colour = (*dark, 150) if i % 2 == 0 else (*light, 110)
        folds.line([(x, 1012 + i * 3), (x - 60, 1180), (x - 92, 1380)], colour, 14, smooth=2)
    for off in (120, 190, 260):
        folds.line([(560 + off * 0.25, 1060 + off * 0.9), (700, 1130 + off * 0.9), (830, 1180 + off * 0.9)], (*dark, 90), 12, smooth=2)
    folds.ellipse((470, 1300, 840, 1440), (*dark, 70))
    pen.paint(folds, pallu_mask, blur=6)

    # gold zari border along the diagonal edge, with a woven pattern
    nx, ny = 0.927, 0.373
    outer = [(x + 46 * nx, y + 46 * ny) for x, y in edge]
    band = edge + outer[::-1]
    band_mask = pen.layer()
    band_mask.poly(band, (255, 255, 255, 255))
    pen.poly(band, SAREE_GOLD)
    band_fx = pen.layer()
    band_fx.line([(x + 6 * nx, y + 6 * ny) for x, y in edge], (*SAREE_GOLD_DARK, 230), 3)
    band_fx.line([(x + 40 * nx, y + 40 * ny) for x, y in edge], (*SAREE_GOLD_DARK, 230), 3)
    band_fx.line([(x + 22 * nx, y + 22 * ny) for x, y in edge], (255, 240, 190, 120), 14, smooth=1)
    for i in range(12):  # little woven motifs
        t = i / 11
        cx = edge[0][0] + (edge[-1][0] - edge[0][0]) * t + 23 * nx
        cy = edge[0][1] + (edge[-1][1] - edge[0][1]) * t + 23 * ny
        band_fx.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), (*SAREE_GOLD_DARK, 220))
        band_fx.ellipse((cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5), (255, 236, 170, 255))
    pen.paint(band_fx, band_mask, blur=0.6)
    soft = pen.layer()  # shadow cast by the draped fabric onto the blouse
    soft.line([(x - 6 * nx, y - 6 * ny) for x, y in edge], (0, 0, 0, 90), 10, smooth=1)
    pen.paint(soft, blur=5, opacity=0.8)

    # lapel microphone clipped to the blouse
    pen.line([(468, 1082), (474, 1036)], (22, 22, 28), 2)
    pen.rect((462, 1080, 476, 1112), (24, 24, 30), radius=5)


def _figure_saree(pen: Pen, rgb):
    _hair_back_bob(pen)
    _blouse_and_saree(pen, rgb)


# =================================================================== the head
FACE_RIGHT = [(540, 638), (592, 645), (630, 672), (653, 713), (661, 766), (657, 820), (643, 864), (619, 905), (589, 935), (558, 951), (540, 954)]
FACE = FACE_RIGHT + mirror(FACE_RIGHT)[::-1][1:-1]


def _eye(pen: Pen, face_mask: Pen, cx: float, cy: float, side: int, blink: bool):
    """side: -1 for the viewer's left eye, +1 for the right. The outer corner points away from the nose."""
    def pt(dx, dy):
        return (cx + side * dx, cy + dy)

    outline = [pt(-27, 3), pt(-16, -6), pt(0, -10), pt(16, -9), pt(28, -3), pt(16, 6), pt(0, 8), pt(-15, 6)]
    # soft eyeshadow above the eye
    shadow = pen.layer()
    shadow.ellipse((cx - 36, cy - 30, cx + 36, cy - 2), (146, 88, 84, 120))
    pen.paint(shadow, face_mask, blur=6)

    if blink:
        pen.poly(outline, SKIN, smooth=2)
        lid = [pt(-27, 4), pt(-14, 9), pt(0, 12), pt(15, 10), pt(28, 0)]
        pen.line(lid, (34, 22, 24), 4, smooth=2)
        for i, (dx, dy) in enumerate([(-12, 10), (-2, 13), (9, 12), (19, 8), (26, 3)]):
            pen.line([pt(dx, dy), pt(dx + 1, dy + 8)], (34, 22, 24), 2)
        return

    eye_mask = pen.layer()
    eye_mask.poly(outline, (255, 255, 255, 255), smooth=2)
    pen.poly(outline, (248, 246, 244), smooth=2)
    inner = pen.layer()  # eyeball shading, iris, pupil, catchlight
    inner.rect((cx - 40, cy - 16, cx + 40, cy - 4), (60, 40, 40, 120))
    inner.ellipse((cx - 14, cy - 15, cx + 14, cy + 13), (84, 52, 36, 255))
    inner.ellipse((cx - 10, cy - 11, cx + 10, cy + 9), (132, 88, 54, 255))
    inner.ellipse((cx - 6, cy - 7, cx + 6, cy + 5), (14, 8, 8, 255))
    inner.ellipse((cx + 2, cy - 8, cx + 8, cy - 2), (255, 255, 255, 255))
    pen.paint(inner, eye_mask, blur=0.5)
    ring = pen.layer()
    ring.arc((cx - 14, cy - 15, cx + 14, cy + 13), 0, 360, (30, 18, 14, 200), 2)
    pen.paint(ring, eye_mask)

    # upper lash line with a small wing, eyelashes, and a soft lower lash line
    top = [pt(-27, 3), pt(-16, -6), pt(0, -10), pt(16, -9), pt(28, -3)]
    pen.line(top, (24, 15, 16), 5, smooth=2)
    pen.line([pt(28, -3), pt(37, -9)], (24, 15, 16), 3)
    for dx, dy, ex, ey in [(-18, -7, -22, -14), (-8, -11, -10, -19), (3, -12, 4, -20), (13, -11, 17, -18), (22, -7, 28, -13)]:
        pen.line([pt(dx, dy), pt(ex, ey)], (24, 15, 16), 2)
    pen.line([pt(-14, 8), pt(0, 10), pt(15, 7)], (110, 74, 66), 2, smooth=2)
    crease = pen.layer()
    crease.line([pt(-22, -14), pt(0, -20), pt(24, -14)], (120, 76, 66, 160), 3, smooth=2)
    pen.paint(crease, face_mask, blur=1.2)


def _brow(pen: Pen, side: int):
    def pt(dx, dy):
        return (540 + side * dx, 760 + dy)

    upper = [pt(-96, 3), pt(-80, -6), pt(-58, -14), pt(-34, -13), pt(-10, -5)]
    lower = [pt(-10, 0), pt(-34, -6), pt(-58, -6), pt(-80, 2), pt(-96, 7)]
    shape = chaikin(upper + lower, closed=True, iterations=3)
    layer = pen.layer()
    layer.d.polygon([layer._p(x, y) for x, y in shape], fill=(*BROW, 245))
    pen.paint(layer, blur=0.8)


def _lips(pen: Pen, face_mask: Pen, mouth: int):
    cx, cy = 540, 912
    open_amt = (0.0, 0.22, 0.5, 0.85)[mouth]
    drop = 30 * open_amt

    top_edge = [(cx - 34, cy + 1), (cx - 20, cy - 8), (cx - 9, cy - 13), (cx, cy - 9), (cx + 9, cy - 13), (cx + 20, cy - 8), (cx + 34, cy + 1)]
    mouth_line_up = [(cx + 34, cy + 1), (cx + 18, cy + 3), (cx, cy + 4), (cx - 18, cy + 3), (cx - 34, cy + 1)]
    upper = top_edge + mouth_line_up

    low_top = [(cx - 34, cy + 1 + drop * 0.25), (cx - 18, cy + 4 + drop * 0.8), (cx, cy + 5 + drop), (cx + 18, cy + 4 + drop * 0.8), (cx + 34, cy + 1 + drop * 0.25)]
    low_bottom = [(cx + 30, cy + 10 + drop), (cx + 16, cy + 21 + drop), (cx, cy + 25 + drop), (cx - 16, cy + 21 + drop), (cx - 30, cy + 10 + drop)]
    lower = low_top + low_bottom

    if open_amt > 0:  # inside of the mouth, teeth at the top
        inside = mouth_line_up[::-1] + low_top[::-1]   # upper edge left to right, lower edge right to left
        pen.poly(inside, MOUTH_DARK, smooth=1)
        inside_mask = pen.layer()
        inside_mask.poly(inside, (255, 255, 255, 255), smooth=1)
        teeth = pen.layer()
        teeth.rect((cx - 24, cy, cx + 24, cy + 3 + 0.2 * drop), (*TEETH, 255), radius=3)
        pen.paint(teeth, inside_mask, blur=0.6)
        if mouth == 3:
            tongue = pen.layer()
            tongue.ellipse((cx - 14, cy + drop - 8, cx + 14, cy + drop + 8), (190, 84, 98, 255))
            pen.paint(tongue, inside_mask, blur=1.5)

    pen.poly(lower, LIP_LOWER, smooth=2)
    pen.poly(upper, LIP_UPPER, smooth=2)
    gloss = pen.layer()
    gloss.ellipse((cx - 14, cy + 11 + drop, cx + 12, cy + 18 + drop), (255, 205, 215, 150))
    gloss.ellipse((cx - 22, cy - 9, cx - 8, cy - 5), (255, 200, 210, 90))
    pen.paint(gloss, blur=2.0)
    if open_amt == 0:  # the line where closed lips meet, with slightly lifted corners
        pen.line([(cx - 34, cy), (cx - 18, cy + 4), (cx, cy + 4), (cx + 18, cy + 4), (cx + 34, cy)], LIP_LINE, 2, smooth=2)


def _hair_front_long(pen: Pen):
    # long locks falling on both sides of the face, over the shoulders
    left_lock = [(452, 662), (420, 706), (396, 782), (386, 880), (394, 980), (378, 1070), (372, 1140), (392, 1186),
                 (424, 1150), (444, 1070), (456, 990), (448, 912), (440, 852), (434, 800), (440, 740)]
    right_lock = mirror(left_lock)
    # top of the head with a side parting, sweeping across the forehead
    hairline = [(438, 750), (441, 706), (458, 674), (484, 656), (508, 649), (548, 653), (590, 665), (622, 686), (644, 714), (655, 752)]
    dome = [(678, 714), (666, 636), (620, 588), (540, 564), (460, 590), (416, 640), (418, 712)]
    cap = hairline + dome
    shapes = [left_lock, right_lock, cap]
    mask = pen.layer()
    for s in shapes:
        mask.poly(s, (255, 255, 255, 255), smooth=3)
        pen.poly(s, HAIR, smooth=3)
    shine = pen.layer()
    shine.line([(500, 612), (570, 606), (636, 640)], (*HAIR_LIGHT, 190), 10, smooth=2)
    shine.line([(430, 760), (408, 900), (402, 1040), (388, 1120)], (*HAIR_LIGHT, 150), 10, smooth=2)
    shine.line([(650, 760), (672, 900), (678, 1040), (692, 1120)], (*HAIR_LIGHT, 130), 10, smooth=2)
    shine.line([(470, 690), (520, 660)], (*HAIR_MID, 220), 8, smooth=1)
    pen.paint(shine, mask, blur=5)


def _earrings_pearl(pen: Pen):
    for x in (438, 642):
        pen.ellipse((x - 5, 866, x + 5, 876), GOLD)
        pen.line([(x, 876), (x, 890)], GOLD, 2)
        pen.ellipse((x - 8, 888, x + 8, 906), PEARL)
        pen.ellipse((x - 4, 891, x + 1, 896), (255, 255, 255))


def _new_head_pen() -> Pen:
    x0, y0, x1, y1 = HEAD_BOX
    return Pen((x1 - x0, y1 - y0), origin=(x0, y0), k=FIG_K, scale=3)


def _base_head(style: str = "saree") -> tuple[Pen, Pen]:
    """Everything that never changes while she talks: face, shading, brows, nose, hair, earrings.
    Returns (drawing, face mask)."""
    pen = _new_head_pen()

    # shadow of the jaw on the neck (spills outside the face, so it is drawn before the face)
    jaw_shadow = pen.layer()
    jaw_shadow.ellipse((496, 934, 584, 992), (*SKIN_SHADOW, 85))
    pen.paint(jaw_shadow, blur=8)

    # face base and shading
    face_mask = pen.layer()
    face_mask.poly(FACE, (255, 255, 255, 255), smooth=3)
    pen.poly(FACE, SKIN, smooth=3)
    shade = pen.layer()
    shade.line([(430, 700), (420, 800), (444, 900), (500, 960)], (*SKIN_SHADOW, 190), 26, smooth=2)   # left edge
    shade.line([(650, 700), (660, 800), (636, 900), (580, 960)], (*SKIN_SHADOW, 190), 26, smooth=2)   # right edge
    shade.ellipse((470, 925, 610, 972), (*SKIN_SHADOW, 100))                                             # under the lip, chin
    pen.paint(shade, face_mask, blur=14)
    light = pen.layer()
    light.ellipse((470, 662, 610, 770), (*SKIN_LIGHT, 70))                                               # forehead
    light.line([(540, 790), (540, 850)], (*SKIN_LIGHT, 90), 12)                                          # nose bridge
    light.ellipse((452, 818, 504, 850), (*SKIN_LIGHT, 80))                                               # cheekbones
    light.ellipse((576, 818, 628, 850), (*SKIN_LIGHT, 80))
    light.ellipse((510, 925, 570, 945), (*SKIN_LIGHT, 70))                                               # chin
    pen.paint(light, face_mask, blur=13)
    blush = pen.layer()
    blush.ellipse((446, 842, 512, 892), (226, 104, 104, 105))
    blush.ellipse((568, 842, 634, 892), (226, 104, 104, 105))
    pen.paint(blush, face_mask, blur=14)

    _brow(pen, -1)
    _brow(pen, 1)

    nose = pen.layer()  # soft shading that shapes the nose
    nose.line([(524, 818), (518, 852), (521, 866)], (*SKIN_SHADOW, 70), 6, smooth=1)
    nose.line([(556, 818), (562, 852), (559, 866)], (*SKIN_SHADOW, 70), 6, smooth=1)
    nose.ellipse((520, 868, 560, 882), (*SKIN_SHADOW, 90))
    pen.paint(nose, face_mask, blur=4)
    nostrils = pen.layer()
    nostrils.ellipse((524, 863, 535, 870), (70, 42, 38, 170))
    nostrils.ellipse((545, 863, 556, 870), (70, 42, 38, 170))
    pen.paint(nostrils, blur=1.4)
    tip = pen.layer()
    tip.ellipse((530, 848, 550, 862), (*SKIN_LIGHT, 120))
    pen.paint(tip, face_mask, blur=3)
    philtrum = pen.layer()
    philtrum.line([(535, 884), (535, 898)], (*SKIN_SHADOW, 50), 4)
    philtrum.line([(545, 884), (545, 898)], (*SKIN_SHADOW, 50), 4)
    pen.paint(philtrum, face_mask, blur=3)

    if style == "blazer":
        _hair_front_long(pen)
        _earrings_pearl(pen)
    else:
        _bindi(pen)
        _hair_front_bob(pen)
        _earrings_gold(pen)
    return pen, face_mask


def build_heads(style: str = "saree") -> dict:
    """All 8 head images: 4 mouth shapes x eyes open/closed, keyed (mouth, blink).
    The shared base is drawn once; eyes and lips are small separate layers."""
    base, face_mask = _base_head(style)

    eyes = {}
    for blink in (False, True):
        layer = base.layer()
        _eye(layer, face_mask, 489, 796, -1, blink)
        _eye(layer, face_mask, 591, 796, 1, blink)
        eyes[blink] = Image.alpha_composite(base.img, layer.img)

    heads = {}
    for mouth in range(4):
        layer = base.layer()
        _lips(layer, face_mask, mouth)
        for blink in (False, True):
            img = Image.alpha_composite(eyes[blink], layer.img)
            heads[(mouth, blink)] = img.resize(base.size, Image.Resampling.LANCZOS)
    return heads


def build_head(mouth: int, blink: bool, style: str = "saree") -> Image.Image:
    return build_heads(style)[(mouth, blink)]
