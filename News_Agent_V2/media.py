"""Small ffmpeg helpers shared by the video, presenter and checker (no other project imports)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        found = shutil.which("ffmpeg")
        if not found:
            raise SystemExit("ffmpeg not found. Run: pip install -r requirements.txt")
        return found


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-1500:]}")


def probe(path: Path) -> str:
    """ffmpeg's description of a media file (streams, duration)."""
    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


def has_audio(path: Path) -> bool:
    return "Audio:" in probe(path)


def duration_seconds(path: Path) -> float | None:
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe(path))
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def mean_volume(path: Path) -> float | None:
    """Average loudness in dB (about -20 is normal speech, -91 or -inf is silence).
    None if the file has no audio stream."""
    if not has_audio(path):
        return None
    out = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)\s*dB", out)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))
