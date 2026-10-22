"""Edit the slow-motion footage: each take back to real speed (S times faster), joined under the paper sheet, a fade
to black over the empty end card, and the voice over a ducked music bed. Then measure the result's frame cadence."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

V = Path(__file__).parent
TAG = sys.argv[1] if len(sys.argv) > 1 else "4"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else V / "axelrod-devlog-2min.mp4"
meta = json.loads((V / f"takes{TAG}.json").read_text())
S = float(meta.get("slow", 1.0))
vid = meta["video"]
TOTAL = 115.6
FPS = 30

# sync: the first black frame of the flash
w, h = 96, 60
lim = meta["flash_wall"] + 8
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", vid, "-t", str(lim), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w)
pts = [float(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "frame=pts_time",
                                         "-read_intervals", f"%+{lim}", "-of", "csv=p=0", vid], capture_output=True, text=True).stdout.split() if x.strip()]
dark = np.where(fr.mean(axis=(1, 2)) < 20)[0]
if len(dark):
    off = pts[int(dark[0])] - meta["flash_wall"]
else:
    # no flash captured (it can fall between captured frames): the title text appearing on the blank sheet is take A's
    # first moment, voiceover 0.0
    ws = takes0 = meta["takes"][0]["wall_start"]
    a0 = ws - 6
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(a0), "-t", "10", "-i", vid, "-vf", "scale=192:120,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    f2 = np.frombuffer(raw, np.uint8).reshape(-1, 120, 192).astype(np.int16)
    dd = np.abs(np.diff(f2, axis=0)).mean(axis=(1, 2))
    near = [i for i, v in enumerate(dd) if v > 0.5 and abs(a0 + (i + 1) / 25 - ws) < 1.0]
    off = a0 + (near[0] + 1) / 25 - ws
print("sync offset", round(off, 3), "slow", S)

parts = []
takes = meta["takes"]
for i, t in enumerate(takes):
    s = t["wall_start"] + off
    d = (t["vo_end"] - t["vo_start"]) * S
    parts.append(f"[0:v]trim=start={s:.3f}:duration={d:.3f},setpts=(PTS-STARTPTS)/{S},fps={FPS},format=yuv420p[v{i}]")
# the end card's text has scaled away by 114.4 s: only the paper fades to black
parts.append("".join(f"[v{i}]" for i in range(len(takes))) + f"concat=n={len(takes)}:v=1:a=0,fade=t=out:st=114.45:d=1.1:color=black[v]")
parts.append(f"[1:a]apad,atrim=0:{TOTAL},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][key]")
parts.append(f"[2:a]atrim=0:{TOTAL},asetpts=PTS-STARTPTS,loudnorm=I=-27:TP=-3,aformat=sample_rates=48000:channel_layouts=stereo,"
             f"afade=t=in:st=0:d=1.5,afade=t=out:st={TOTAL - 3.0:.3f}:d=2.8[mus]")
parts.append("[mus][key]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500:makeup=1[duck]")
parts.append("[vo][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.9[a]")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", str(V / "vo2_clean.wav"), "-i", str(V / "music120.wav"),
                "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", str(TOTAL), str(OUT)],
               check=True)
print("wrote", OUT)

# cadence: in stretches where the picture is moving, how many output frames are new
w, h = 240, 150
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(OUT), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)
diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
changed = diff > 0.02
# a moving stretch: a 1-second window with any change; within those, the share of frames that changed
win = np.convolve(changed.astype(float), np.ones(FPS), "same")
moving = win > 3
print(f"moving frames: {int(moving.sum())} of {len(diff)}; new frames while moving: {changed[moving].mean() * 100:.1f}%")
# the longest run of repeated frames inside a moving stretch
run = best = 0
for c, m in zip(changed, moving):
    run = 0 if (c or not m) else run + 1
    best = max(best, run)
print(f"longest repeat while moving: {best} frames ({best / FPS * 1000:.0f} ms)")
