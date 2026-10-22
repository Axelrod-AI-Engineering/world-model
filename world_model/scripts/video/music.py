"""An original ambient piece for the demo video: slow pads, a sparse arpeggio, soft bass, a Schroeder reverb."""
import sys
import wave
import numpy as np

SR = 44100
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 64.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)

def hz(m):  # midi -> Hz
    return 440.0 * 2 ** ((m - 69) / 12)

# C major, gently: Cmaj9, Am9, Fmaj9(#11-ish), G6sus -> each 8 s
CHORDS = [[48, 55, 59, 62, 64], [45, 52, 55, 59, 60], [41, 48, 52, 55, 57], [43, 50, 55, 57, 62]]
SEG = 8.0

def env(n, a, r):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, 1, na) ** 2
    e[-nr:] *= np.linspace(1, 0, nr) ** 1.5
    return e

L = np.zeros(N); R = np.zeros(N)
# pads
for k in range(int(np.ceil(DUR / SEG))):
    ch = CHORDS[k % 4]
    s0 = int(k * SEG * SR); s1 = min(N, int((k + 1) * SEG * SR + 2.5 * SR))
    tt = np.arange(s1 - s0) / SR
    e = env(s1 - s0, 2.2, 3.0)
    for j, m in enumerate(ch):
        f = hz(m + 12)
        for side, det in ((L, -0.12), (R, 0.12)):
            ff = f * 2 ** (det / 12 / 4)
            ph = rng.uniform(0, 2 * np.pi)
            w = sum(np.sin(2 * np.pi * ff * h * tt + ph * h) / (h * h) for h in (1, 2, 3, 4))
            trem = 1 + 0.05 * np.sin(2 * np.pi * 0.18 * tt + j)
            side[s0:s1] += 0.045 * w * e * trem
# bass: the root, long and soft
for k in range(int(np.ceil(DUR / SEG))):
    m = CHORDS[k % 4][0] - 12
    s0 = int(k * SEG * SR); s1 = min(N, s0 + int(7.8 * SR))
    tt = np.arange(s1 - s0) / SR
    b = np.sin(2 * np.pi * hz(m) * tt) * np.exp(-tt * 0.35) * env(s1 - s0, 0.08, 1.5)
    L[s0:s1] += 0.10 * b; R[s0:s1] += 0.10 * b
# arpeggio: from 8 s to DUR - 8 s, one note per beat at 66 bpm, rising through the chord
beat = 60.0 / 66
nb = int((DUR - 16) / beat)
for i in range(nb):
    at = 8.0 + i * beat
    k = int(at // SEG) % 4
    ch = CHORDS[k]
    m = ch[[1, 2, 3, 4, 3, 2][i % 6]] + 24
    if i % 8 == 7:
        continue                     # a breath every eighth beat
    s0 = int(at * SR); s1 = min(N, s0 + int(2.6 * SR))
    tt = np.arange(s1 - s0) / SR
    f = hz(m)
    pl = (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 2.4) * np.minimum(1, tt / 0.006)
    pan = 0.5 + 0.35 * np.sin(i * 0.9)
    vel = 0.055 * (0.8 + 0.2 * np.sin(i * 0.37))
    L[s0:s1] += vel * pl * (1 - pan); R[s0:s1] += vel * pl * pan

def onepole(x, a=0.18):
    y = np.empty_like(x); acc = 0.0
    for i in range(0, len(x), 1):
        acc += a * (x[i] - acc); y[i] = acc
    return y

def comb(x, d, g):
    y = np.copy(x)
    for i in range(d, len(x)):
        y[i] += g * y[i - d]
    return y

def allpass(x, d, g):
    y = np.zeros_like(x)
    for i in range(len(x)):
        xd = x[i - d] if i >= d else 0.0
        yd = y[i - d] if i >= d else 0.0
        y[i] = -g * x[i] + xd + g * yd
    return y

def reverb(x):
    # Schroeder: parallel combs then series allpasses, on a downsampled-free path (vectorized by blocks)
    out = np.zeros_like(x)
    for d, g in ((1557, 0.82), (1617, 0.81), (1491, 0.80), (1422, 0.79)):
        out += comb_fast(x, d, g)
    out /= 4
    for d, g in ((225, 0.6), (556, 0.6)):
        out = allpass_fast(out, d, g)
    return out

def comb_fast(x, d, g):
    y = np.copy(x)
    # y[n] = x[n] + g*y[n-d]: process in blocks of d
    for s in range(d, len(x), d):
        e = min(len(x), s + d)
        y[s:e] += g * y[s - d:e - d]
    return y

def allpass_fast(x, d, g):
    y = np.zeros_like(x)
    xpad = np.concatenate([np.zeros(d), x])
    for s in range(0, len(x), d):
        e = min(len(x), s + d)
        yd = y[s - d:e - d] if s >= d else np.zeros(e - s)
        y[s:e] = -g * x[s:e] + xpad[s:e] + g * yd
    return y

wetL, wetR = reverb(L), reverb(R[::-1].copy())[::-1] * 0 + reverb(R)
L = 0.72 * L + 0.55 * wetL
R = 0.72 * R + 0.55 * wetR
# fades
fi, fo = int(2.0 * SR), int(4.5 * SR)
for x in (L, R):
    x[:fi] *= np.linspace(0, 1, fi) ** 2
    x[-fo:] *= np.linspace(1, 0, fo) ** 1.6
peak = max(np.abs(L).max(), np.abs(R).max())
L, R = L / peak * 0.85, R / peak * 0.85
pcm = (np.stack([L, R], axis=1) * 32767).astype(np.int16)
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("wrote", sys.argv[1], DUR, "s")
