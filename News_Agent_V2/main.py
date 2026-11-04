"""Run the pipeline: fetch -> dedupe -> skip used -> rank -> save.

Usage:
    python main.py            # normal run, marks stories as used
    python main.py --dry-run  # does not mark stories as used (good for testing)
"""
from __future__ import annotations
import argparse
import json
import logging
from datetime import date

import config
import db
from fetch import fetch_region
from rank import rank_region

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")


def run(dry_run: bool = False) -> None:
    all_stories, used_articles = [], []

    for region in ("tamilnadu", "india"):
        candidates = db.filter_unused(fetch_region(region))
        log.info("%s: %d fresh candidates", region, len(candidates))
        try:
            stories = rank_region(candidates, region)
        except RuntimeError as exc:
            log.error("Skipping %s: %s", region, exc)
            continue
        all_stories.extend(stories)
        by_link = {a.link: a for a in candidates}
        used_articles.extend(by_link[s.link] for s in stories if s.link in by_link)

    if not all_stories:
        raise SystemExit("No stories ranked. Try again in a few minutes.")

    # Save a run record so you can debug and compare days later
    out_dir = config.RUNS_DIR / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "stories.json"
    out_file.write_text(
        json.dumps([s.model_dump() for s in all_stories], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Saved %d stories to %s", len(all_stories), out_file)

    if not dry_run:
        db.mark_used(used_articles)

    for s in all_stories:
        print(f"[{s.region}] #{s.rank} ({s.score}/10) {s.headline}\n    {s.summary}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    run(parser.parse_args().dry_run)
