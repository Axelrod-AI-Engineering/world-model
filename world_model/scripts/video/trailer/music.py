"""An original bed for the trailer: soft pads throughout, a low pulse that enters with Import and builds, a sparse
arpeggio from Transmission on, and a stop on the logo with only a reverb tail left.

    python world_model/scripts/video/trailer/music.py OUT.wav
"""
import sys
import wave

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__file__))
from data import VO  # noqa: E402

SR = 44100
DUR = VO["total"]
N = int(SR * DUR)
t = np.arange(N) / SR
STOP = VO["end"]                      # the music stops where the logo comes in
BPM = 96
BEAT = 60 / BPM


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def ramp(x0, x1, y0=0.0, y1=1.0):
    return np.clip((t - x0) / max(1e-6, x1 - x0), 0, 1) * (y1 - y0) + y0


# A minor, open: Am9, Fmaj7, Cadd9, G6 (two bars each)
CHORDS = [[45, 52, 55, 59, 60], [41, 48, 52, 55, 57], [48, 55, 59, 62, 64], [43, 50, 55, 59, 64]]
SEG = 8 * BEAT
L = np.zeros(N)
R = np.zeros(N)

# pads: detuned saws through a soft low-pass (a running mean), slow attack
for k in range(int(np.ceil(DUR / SEG)) + 1):
    s0 = int(k * SEG * SR)
    if s0 >= N:
        break
    s1 = min(N, int((k + 1) * SEG * SR + 2.0 * SR))
    tt = t[s0:s1] - t[s0]
    seg = np.zeros(s1 - s0)
    for m in CHORDS[k % 4]:
        for d in (-0.06, 0.06):
            ph = 2 * np.pi * hz(m) * (1 + d / 100) * tt
            seg += 0.5 * np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.07 * np.sin(3 * ph)
    e = np.minimum(1, tt / 1.6) * np.clip((tt[-1] - tt) / 2.0, 0, 1)
    seg *= e * 0.022
    L[s0:s1] += seg
    R[s0:s1] += np.roll(seg, 180)

# the pulse: a soft low note on every beat, entering with Import and growing toward Scale
pulse_gain = ramp(VO["import"] - 0.5, VO["import"] + 3) * ramp(VO["import"], VO["stack"], 0.35, 1.0)
for b in np.arange(VO["import"] - 0.5, STOP, BEAT):
    i0 = int(b * SR)
    n = int(0.42 * SR)
    if i0 + n > N:
        break
    k = int((b // SEG) % 4)
    tt = np.arange(n) / SR
    note = np.sin(2 * np.pi * hz(CHORDS[k][0] - 12) * tt) * np.exp(-tt * 7.5) * 0.16
    note += np.sin(2 * np.pi * hz(CHORDS[k][0]) * tt) * np.exp(-tt * 11) * 0.05
    L[i0:i0 + n] += note * pulse_gain[i0]
    R[i0:i0 + n] += note * pulse_gain[i0]

# the arpeggio: eighth notes, sparse at first, from Transmission on
rng = np.random.default_rng(11)
arp_gain = ramp(VO["trans"], VO["trans"] + 6, 0, 1) * ramp(VO["trans"], VO["stack"], 0.5, 1.0)
for j, b in enumerate(np.arange(VO["trans"], STOP, BEAT / 2)):
    if rng.random() < 0.35:
        continue
    i0 = int(b * SR)
    n = int(0.5 * SR)
    if i0 + n > N:
        break
    k = int((b // SEG) % 4)
    m = CHORDS[k][j % 5] + 12
    tt = np.arange(n) / SR
    note = (np.sin(2 * np.pi * hz(m) * tt) + 0.25 * np.sin(4 * np.pi * hz(m) * tt)) * np.exp(-tt * 6) * 0.03
    pan = 0.5 + 0.35 * np.sin(j * 0.9)
    L[i0:i0 + n] += note * arp_gain[i0] * (1 - pan) * 2
    R[i0:i0 + n] += note * arp_gain[i0] * pan * 2

# stop on the logo: everything ends at STOP, and a short feedback-delay tail rings out
stop = int(STOP * SR)
tail = int(3.5 * SR)
for ch in (L, R):
    src = ch[max(0, stop - int(0.6 * SR)):stop].copy()
    ch[stop:] = 0
    for k, d in enumerate((0.23, 0.47, 0.71, 0.97, 1.31)):
        i = stop + int(d * SR) - len(src)
        if 0 <= i and i + len(src) <= N:
            ch[i:i + len(src)] += src * 0.45 ** (k + 1)
    ch[stop + tail:] = 0

mix = np.stack([L, R], axis=1)
mix /= max(1e-9, np.abs(mix).max()) / 0.8
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((mix * 32767).astype("<i2").tobytes())
print("wrote", sys.argv[1], f"{DUR:.1f}s")
