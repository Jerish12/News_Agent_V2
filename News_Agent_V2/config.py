"""Central configuration. Change feeds and counts here, not in the logic."""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
RUNS_DIR = BASE_DIR / "runs"
DB_PATH = BASE_DIR / "news.db"

# Free-tier model names and limits change; override with GEMINI_MODEL in .env if needed
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# Tried in order if the main model is overloaded (503) or not found (404)
FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite").split(",")
    if m.strip()
]

# How many stories you want from each region (5 + 5 = top 10)
TOP_N = {"tamilnadu": 5, "india": 5}

# Only consider stories published in the last N hours
MAX_AGE_HOURS = 24

# Max candidates sent to the LLM per region (keeps cost and noise down)
MAX_CANDIDATES = 40

# Titles at least this similar (0-100) are treated as the same story
DEDUPE_THRESHOLD = 82

# Verify these URLs in your browser; publishers occasionally change feed paths.
FEEDS = {
    "tamilnadu": [
        "https://news.google.com/rss/search?q=Tamil+Nadu+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss",
    ],
    "india": [
        "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
        "https://www.thehindu.com/news/national/feeder/default.rss",
    ],
}

USER_AGENT = "Mozilla/5.0 (compatible; NewsAgent/0.1)"

# ---- Stage 3: script / video ----
VIDEO_SECONDS = 58        # maximum video length
MIN_VIDEO_SECONDS = 50    # shorter than this is rejected and rewritten
WORDS_PER_SECOND = 2.5   # typical English TTS pace (~150 words per minute)
SCENE_PAUSE = 0.25       # small gap between scenes, in seconds
VIDEO_STORIES = {"tamilnadu": 5, "india": 5}  # stories narrated in the video
MAX_HASHTAGS = 6

# ---- Stage 4: voiceover ----
VOICE = "en-IN-NeerjaNeural"   # Indian English, female. Male: en-IN-PrabhatNeural
VIDEO_HARD_MAX_SECONDS = 60    # if real audio runs longer, speech is sped up a little
MAX_SPEEDUP_PERCENT = 20       # never speed up more than this (it starts to sound rushed)
# Whole-word, case-sensitive replacements so the voice reads acronyms sensibly
PRONUNCIATIONS = {
    "DGCA": "D G C A",
    "ED": "E D",
    "TTD": "T T D",
    "HC": "High Court",
    "PIL": "P I L",
    "RSS": "R S S",
    "LPG": "L P G",
    "FEMA": "Fema",
    "TANGEDCO": "Tangedco",
}

# ---- Stage 5: video ----
PAGE_NAME = "Daily News: Tamil Nadu & India"   # shown at the top of every frame. Put your page name here.
# Your Instagram profile picture, shown (as a circle) before the page name in every frame.
# To change it later, edit only this line. A relative path is read from this project's folder.
# If the file is missing, the video is still made, just without the picture.
PROFILE_PICTURE = r"C:\Users\JERISH\Downloads\Unfilteredminds DP.jpg"
VIDEO_SIZE = (1080, 1920)                      # 9:16 vertical, for Reels
FPS = 30
VIDEO_PRESET = "veryfast"                  # ffmpeg speed/size trade-off (slower = smaller file)
MUSIC_FILE = BASE_DIR / "assets" / "music.mp3"  # optional background music; skipped if missing
MUSIC_VOLUME = 0.10                            # relative to the voice (1.0)
FONT_BOLD = [
    str(BASE_DIR / "assets" / "fonts" / "bold.ttf"),   # drop your own font here to override
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_REGULAR = [
    str(BASE_DIR / "assets" / "fonts" / "regular.ttf"),
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# ---- Stage 6: feed image ----
IMAGE_SIZE = (1080, 1350)   # 4:5 portrait, the largest feed shape Instagram shows without cropping
IMAGE_TITLE = "TODAY'S TOP 10"
IMAGE_FOOTER = "Follow for daily Tamil Nadu and India news"


# =====================  V2 additions  =====================

# ---- V2: presenter. The opening and closing lines are read by the on-screen news presenter ----
HOOK_TEXT = "Hello, and welcome! Here are today's top ten headlines from Tamil Nadu and India."
HOOK_ON_SCREEN = "TODAY'S TOP 10 HEADLINES"
OUTRO_TEXT = "That's all for now. Follow us for your daily news from Tamil Nadu and India."
OUTRO_ON_SCREEN = "FOLLOW FOR DAILY NEWS"
PRESENTER_STYLE = "saree"                # "saree" (Tamil news presenter look) or "blazer"
PRESENTER_SAREE_COLOR = (16, 128, 96)    # saree colour as (red, green, blue): emerald by default
PRESENTER_LABEL = "AI NEWS PRESENTER"   # shown on screen so viewers know she is a virtual presenter
SHOW_PRESENTER_LABEL = True

# ---- V2: visuals (stock footage and photos from Pexels) ----
# Free key: https://www.pexels.com/api/  ->  put PEXELS_API_KEY=... in your .env file.
# Without a key the video still builds, using animated branded backgrounds instead.
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
MEDIA_CACHE = BASE_DIR / "media_cache"   # downloaded media is kept here and reused
SHOW_VISUAL_TAG = True                   # small "Representative visual" tag on stock footage
VISUAL_TAG_TEXT = "Representative visual"

# ---- V2: captions at the bottom, current word highlighted ----
CAPTION_MAX_WORDS = 4
CAPTION_MAX_CHARS = 26
CAPTION_FONT_SIZE = 72
CAPTION_HIGHLIGHT = (255, 214, 10)       # colour of the word being spoken
CAPTION_Y = 1340                          # top of the caption area (video is 1920 tall). Kept above
CAPTION_AREA_HEIGHT = 260                 # Instagram's own bottom buttons/caption zone (about y > 1600)
BANNER_Y = 960                            # top of the headline banner on story scenes
PRESENTER_BANNER_Y = 1130                 # top of the banner on the presenter scenes
