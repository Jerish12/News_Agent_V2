# News Agent V2

Turns the day's top Tamil Nadu and India news into a ~55 second vertical news video, a feed image and a
caption, ready for Instagram. Always watch the video and read `caption.txt` before posting.

## What is new in V2

| Request | What V2 does |
|---|---|
| Not just text slides | Each story shows related **footage or a photo** (stock media from Pexels), slowly moving, with a headline banner that slides in |
| Captions at the bottom | **Word-by-word captions**, the spoken word highlighted, synced to the voice |
| More catchy | TV-style graphics: progress bar, region tags, sliding banners, moving backgrounds, studio set |
| Female presenter at start and end | An **animated news presenter** (illustrated, lip-synced to the voice, blinking) reads the opening and closing |

The presenter is a soft-shaded illustration of a young woman in a silk saree with a gold border (or a blazer, see `PRESENTER_STYLE`), not a real person or a photograph, and the
video labels her "AI NEWS PRESENTER". A photo-realistic talking presenter needs a paid avatar service (for example
D-ID or HeyGen); it can be added as an optional upgrade.
Stock footage is illustrative, not footage of the actual event, so the video shows a small
"Representative visual" tag and `caption.txt` gets a line saying the visuals are stock.

## Setup (Windows, PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then edit .env and add GEMINI_API_KEY and PEXELS_API_KEY
python test_pipeline.py     # offline self-check (needs no internet or keys), takes about 30 seconds
```

If you are moving from V1: copy your old `.env` here and add the line `PEXELS_API_KEY=...`, and copy
your `PAGE_NAME` and `PROFILE_PICTURE` values into the new `config.py`.

Free Pexels key: https://www.pexels.com/api/ (sign up, request a key, it is instant).

## Run

```powershell
python run_all.py --dry-run     # everything for today in one go (--dry-run: do not mark stories as used)
```

Or stage by stage (use the same `--date YYYY-MM-DD` for every stage if you pass one):

```powershell
python main.py --dry-run        # 1-2  fetch news, rank the top 10
python script.py                # 3    story lines + caption
python visuals.py               # 4    find footage / photos for each story
python voice.py                 # 5    English voiceover with word timing (needs internet)
python video.py --preview       # 6a   draw one preview image per scene (no voice needed): check the design
python video.py                 # 6b   build runs\<date>\video.mp4
python image.py                 # 7    1080x1350 feed image (post_image.jpg)
```

Results are in `runs\<date>\`: `video.mp4`, `post_image.jpg`, `caption.txt`, `visuals.json` (credits for every
clip), `script.json`, `stories.json`.

If the video has no sound or looks wrong: `python check_video.py --date <date>`.

## Files

| File | Job |
|---|---|
| `config.py` | All settings in one place (see below) |
| `main.py`, `fetch.py`, `rank.py`, `db.py` | Stages 1-2: RSS news, dedupe, AI ranking, history |
| `script.py` | Stage 3: the 10 story lines (the presenter's opening and closing come from `config.py`) |
| `visuals.py` | Stage 4: AI picks search phrases, Pexels footage/photos downloaded to `media_cache\` |
| `voice.py`, `captions.py` | Stage 5: English voice (Indian female), per-word timing for the captions |
| `anchor.py`, `presenter_art.py` | The animated presenter: studio, her artwork (soft-shaded illustration), blinking, lip-sync |
| `overlays.py`, `graphics.py` | Header, tags, banners, shared drawing helpers |
| `video.py` | Stage 6: puts it all together with ffmpeg (bundled, nothing to install) |
| `image.py` | Stage 7: feed image |
| `media.py`, `check_video.py` | ffmpeg helpers and the diagnostic |
| `news_llm.py` | Shared Gemini helper (model fallback, retries, validated JSON) |

## Customise (all in `config.py`)

- `PAGE_NAME`, `PROFILE_PICTURE`: shown in the header of every frame and on the studio screen.
- `HOOK_TEXT`, `OUTRO_TEXT`, `HOOK_ON_SCREEN`, `OUTRO_ON_SCREEN`: what the presenter says and the banners show.
- `PRESENTER_STYLE` (`"saree"` Tamil news presenter look, or `"blazer"`) and `PRESENTER_SAREE_COLOR` (red, green, blue): her outfit.
- `PRESENTER_LABEL`, `SHOW_PRESENTER_LABEL`: the "AI NEWS PRESENTER" tag. Keeping it is recommended.
- `SHOW_VISUAL_TAG`, `VISUAL_TAG_TEXT`: the "Representative visual" tag on stock footage.
- `CAPTION_FONT_SIZE`, `CAPTION_HIGHLIGHT`, `CAPTION_MAX_WORDS`, `CAPTION_Y`: caption look and position.
  Captions sit above Instagram's own buttons and caption area (roughly the bottom 17% of the screen).
- `VOICE`, `PRONUNCIATIONS`: voice (`python voice.py --list-voices`) and how acronyms are read aloud.
- `VIDEO_SECONDS`, `MIN_VIDEO_SECONDS`: target length (50 to 58 seconds by default).
- `VIDEO_PRESET`: `veryfast` is quick. Use `medium` for smaller files, slower builds.
- Background music: put a file at `assets\music.mp3` (only music you have the rights to).
- Fonts: Segoe UI / Arial are found automatically; add `assets\fonts\bold.ttf` and `regular.ttf` to override.

## Good to know

- **Footage matching:** the AI chooses neutral search phrases (for example "river boat at dusk"), never names
  or sensitive scenes. Stock libraries cannot match every story exactly, so skim the video and, if a clip is a
  poor fit, delete its entry's file from `media_cache\` and run `python visuals.py` again.
- **Pexels** is free to use, with credit appreciated: contributor names are in `visuals.json`. Check Pexels'
  current licence terms for your use.
- **Without a Pexels key** every story gets an animated branded background instead of footage.
- **Timing:** if the voice service does not report word timing, captions fall back to an even spread across
  each sentence, which is a little less exact.
- **Build time:** about 2 minutes for the video. Memory use stays under 1 GB.

## Next stages (not built yet)

- `review.py`: send the video and caption to Telegram for approval.
- `post.py`: Instagram Graph API (Business/Creator account linked to a Facebook Page).
- A daily schedule (Windows Task Scheduler).
