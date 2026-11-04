"""Diagnose a run: are the audio clips and the final video really audible?

Usage:
    python check_video.py --date 2026-10-15
    python check_video.py --all          # summary of every folder in runs/

It tells you which case you are in:
  - audio clips silent       -> the voice stage produced no sound (re-run voice.py)
  - video has no audio track -> the video stage dropped it (send me this output)
  - video audible            -> the file is fine; try another player (VLC / Windows Media Player)
"""
import argparse
from datetime import date, datetime

import config
import media


def fmt(level):
    if level is None:
        return "NO AUDIO TRACK"
    if level == float("-inf") or level < -55:
        return f"SILENT ({level} dB)"
    return f"ok ({level:.1f} dB)"


def check_day(day: str) -> None:
    run_dir = config.RUNS_DIR / day
    print(f"\n=== {day}  ({run_dir}) ===")
    manifest = run_dir / "audio_manifest.json"
    clips = sorted((run_dir / "audio").glob("scene_*.mp3"))
    print(f"voiceover manifest: {'yes' if manifest.exists() else 'NO'}   audio clips: {len(clips)}")
    for clip in clips[:3]:
        print(f"  {clip.name}: {fmt(media.mean_volume(clip))}")
    final = run_dir / "video.mp4"
    if final.exists():
        stamp = datetime.fromtimestamp(final.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        info = media.probe(final)
        streams = [l.strip() for l in info.splitlines() if "Stream #" in l]
        print(f"video.mp4 made {stamp}")
        for line in streams:
            print("  " + line[:110])
        print(f"  loudness: {fmt(media.mean_volume(final))}")
    else:
        print("video.mp4: not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    days = sorted(p.name for p in config.RUNS_DIR.iterdir() if p.is_dir()) if args.all else [args.date]
    for d in days:
        check_day(d)
