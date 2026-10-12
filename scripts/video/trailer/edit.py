"""Cut the trailer: each shot from its magenta sync flash, for its span of the voiceover, back to real speed; the
shots joined at 1080p; the voice over the music bed, ducked under speech.

    python scripts/video/trailer/edit.py TAKE_DIR VOICE.m4a MUSIC.wav OUT.mp4
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import VO  # noqa: E402

TAKE, VOICE, MUSIC, OUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
FPS = 30
meta = json.loads((TAKE / "shots.json").read_text())
S = float(meta["slow"])
ORDER = ["open", "title", "old", "import", "learn", "ask", "meta", "stack", "end"]


def flash_end(video: str) -> float:
    """The first frame after the magenta flash, in the recording's seconds."""
    w, h = 64, 36
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", video, "-t", "40", "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3).astype(int)
    pts = [float(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "frame=pts_time",
                                             "-read_intervals", "%+40", "-of", "csv=p=0", video], capture_output=True, text=True,
                                            check=True).stdout.split() if x.strip()]
    mag = (fr[..., 0] > 200) & (fr[..., 1] < 70) & (fr[..., 2] > 200)
    on = np.where(mag.mean(axis=(1, 2)) > 0.9)[0]
    if not len(on):
        raise SystemExit(f"no sync flash in {video}")
    last = int(on[-1])
    return pts[last + 1] if last + 1 < len(pts) else pts[last] + 1 / 25


parts, labels = [], []
inputs = []
for i, name in enumerate(ORDER):
    sh = meta["shots"][name]
    v = sh["video"]
    s0 = flash_end(v)
    d = (sh["vo_end"] - sh["vo_start"]) * S
    inputs += ["-i", v]
    parts.append(f"[{i}:v]trim=start={s0:.3f}:duration={d:.3f},setpts=(PTS-STARTPTS)/{S},fps={FPS},"
                 f"scale=1920:1080:flags=lanczos,setsar=1,format=yuv420p[v{i}]")
    labels.append(f"[v{i}]")
    print(f"{name:7s} flash ends {s0:6.2f}s, {d / S:5.2f}s of voiceover")
n = len(ORDER)
parts.append("".join(labels) + f"concat=n={n}:v=1:a=0,fade=t=in:st=0:d=0.5,fade=t=out:st={VO['total'] - 1.0:.2f}:d=1.0[v]")
total = VO["total"]
parts.append(f"[{n}:a]apad,atrim=0:{total},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
             "highpass=f=70,acompressor=threshold=0.1:ratio=3:attack=10:release=200,loudnorm=I=-16:TP=-1.5,asplit=2[vo][key]")
parts.append(f"[{n + 1}:a]atrim=0:{total},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,volume=0.55[mus]")
parts.append("[mus][key]sidechaincompress=threshold=0.05:ratio=5:attack=40:release=600:makeup=1[duck]")
parts.append("[vo][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", VOICE, "-i", MUSIC, "-filter_complex", ";".join(parts),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", str(total), str(OUT)], check=True)
print("wrote", OUT)
