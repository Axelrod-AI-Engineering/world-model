"""Edit the devlog: cut the takes on the voiceover's clock, dip to paper between takes, fade to black at the end, and
mix the voice over a ducked music bed."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

V = Path(__file__).parent
meta = json.loads((V / "takes3.json").read_text())
vid = meta["video"]
TOTAL = 115.6
DIP = 0.3
PAPER = "0xFBF8F2"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else V / "axelrod-devlog-2min.mp4"

# the sync flash: the first black frame after the start
w, h = 96, 60
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", vid, "-t", str(meta["flash_wall"] + 6), "-vf",
                      f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
pts = [float(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "frame=pts_time",
                                         "-read_intervals", f"%+{meta['flash_wall'] + 6}", "-of", "csv=p=0", vid],
                                        capture_output=True, text=True).stdout.split() if x.strip()]
dark = np.where(fr.mean(axis=(1, 2)) < 20)[0]
off = pts[int(dark[0])] - meta["flash_wall"]
print("sync offset", round(off, 3))

parts = []
takes = meta["takes"]
for i, t in enumerate(takes):
    s = t["wall_start"] + off
    d = t["vo_end"] - t["vo_start"]
    f = [f"[0:v]trim=start={s:.3f}:duration={d:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p"]
    if i > 0:
        f.append(f"fade=t=in:st=0:d={DIP}:color={PAPER}")
    if i < len(takes) - 1:
        f.append(f"fade=t=out:st={d - DIP:.3f}:d={DIP}:color={PAPER}")
    parts.append(",".join(f) + f"[v{i}]")
parts.append("".join(f"[v{i}]" for i in range(len(takes))) + f"concat=n={len(takes)}:v=1:a=0,fade=t=out:st={TOTAL - 2.0:.3f}:d=1.8:color=black[v]")
# audio: the voice from 0, the music bed under it, ducked while the voice speaks
parts.append(f"[1:a]apad,atrim=0:{TOTAL},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key]")
parts.append(f"[2:a]atrim=0:{TOTAL},asetpts=PTS-STARTPTS,loudnorm=I=-27:TP=-3,aformat=sample_rates=48000:channel_layouts=stereo,"
             f"afade=t=in:st=0:d=1.5,afade=t=out:st={TOTAL - 3.0:.3f}:d=2.8[mus]")
parts.append("[mus][key]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500:makeup=1[duck]")
parts.append("[vo][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.9[a]")
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", str(V / "vo2_clean.wav"), "-i", str(V / "music120.wav"),
       "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", str(TOTAL), str(OUT)]
subprocess.run(cmd, check=True)
print("wrote", OUT)
