"""Pull frames from the edited video at given voiceover times and tile them into labelled sheets."""
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw
V = Path(__file__).parent
vid = sys.argv[1]
name = sys.argv[2]
times = [float(t) for t in sys.argv[3:]]
W, H = 960, 600
cols = 2
frames = []
for t in times:
    out = V / f"_f{t:.2f}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", vid, "-frames:v", "1", str(out)], check=True)
    im = Image.open(out).convert("RGB").resize((W, H))
    ImageDraw.Draw(im).rectangle([0, 0, 70, 22], fill="black")
    ImageDraw.Draw(im).text((6, 5), f"{t:.2f}s", fill="white")
    frames.append(im)
rows = (len(frames) + cols - 1) // cols
sheet = Image.new("RGB", (W * cols, H * rows), "white")
for i, im in enumerate(frames):
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(V / f"{name}.png")
print("wrote", name)
