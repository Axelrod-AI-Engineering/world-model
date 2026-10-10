import json, subprocess, sys
from pathlib import Path
V = Path(__file__).parent
meta = json.loads((V / "segments.json").read_text())
SPEED = {"title": 1.0, "article": 1.25, "review": 1.35, "ripple": 1.35, "checks": 1.45, "structure": 1.55, "open": 1.3, "end": 1.0}
FADE = 0.5
segs = meta["segments"]
durs = [(s["end"] - s["start"]) / SPEED[s["name"]] for s in segs]
total = sum(durs) - FADE * (len(segs) - 1)
print("durations", [round(d, 2) for d in durs], "total", round(total, 2))
parts = []
for i, s in enumerate(segs):
    parts.append(f"[0:v]trim=start={s['start']}:end={s['end']},setpts=(PTS-STARTPTS)/{SPEED[s['name']]},fps=30,format=yuv420p[v{i}]")
cur = "v0"
length = durs[0]
for i in range(1, len(segs)):
    off = length - FADE
    parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={FADE}:offset={off:.3f}[x{i}]")
    cur = f"x{i}"
    length = off + durs[i]
fo = 3.5
parts.append(f"[1:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-18:TP=-2:LRA=7,afade=t=in:st=0:d=1.5,afade=t=out:st={length - fo:.3f}:d={fo}[a]")
fc = ";".join(parts)
out = V / "axelrod-learning-60s.mp4"
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", meta["video"], "-i", str(V / "music.wav"), "-filter_complex", fc,
       "-map", f"[{cur}]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{length:.3f}", str(out)]
subprocess.run(cmd, check=True)
print("wrote", out, round(length, 2))
