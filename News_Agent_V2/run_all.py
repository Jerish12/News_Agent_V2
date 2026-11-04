"""Run the whole pipeline for today: fetch -> rank -> script -> visuals -> voice -> video -> image.

Usage:
    python run_all.py              # real run (marks the chosen stories as used)
    python run_all.py --dry-run    # same, but does not mark stories as used (good for testing)

Each stage is also runnable on its own (main.py, script.py, voice.py, video.py).
Always watch the video and read caption.txt before posting.
"""
import argparse
import logging
from datetime import date

import image
import main as fetch_and_rank
import script
import video
import visuals
import voice

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    day = date.today().isoformat()

    fetch_and_rank.run(dry_run=args.dry_run)
    script.run(day)
    visuals.run(day)
    voice.run(day)
    out = video.run(day)
    pic = image.run(day)
    print(f"\nDone.\nVideo:   {out}\nImage:   {pic}\nCaption: {out.parent / 'caption.txt'}\nReview all three before posting.")
