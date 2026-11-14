#!/usr/bin/env python3
"""Synthetic placeholder sounds of the cat (plan Etappe 4), NumPy only and reproducible (fixed seeds), until the user's own
recordings replace them (sounds.source). Own synthesis, no samples: a harmonic voice through moving formants (meows, the yawn's
squeak), a pulse train through a chest resonance built circularly so the loop has no seam (purr), shaped noise (hiss, landing).
16-bit mono WAV at 44.1 kHz. Usage: sound_synth.py <outdir>  ->  one WAV per sounds.assets() name, then "SOUNDS OK <n>"."""
import os, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from velvetpaws import sounds as SN

RATE = SN.RATE
# vowel -> three formants (centre Hz, bandwidth Hz, gain): a cat's "m-i-a-u" moves through these
VOWELS = {"i": ((350, 120, 1.0), (2300, 250, 0.5), (3300, 350, 0.25)), "e": ((550, 130, 1.0), (1900, 220, 0.55), (2900, 300, 0.25)),
          "a": ((900, 160, 1.0), (1500, 200, 0.7), (2900, 300, 0.3)), "u": ((420, 120, 1.0), (950, 150, 0.45), (2600, 300, 0.15))}
# meow variants, all through the same voice as the first (smooth arc, "m" onset, quiet breath): (seconds, f0 points (share, Hz),
# vowel points (share, vowel), trill Hz (0: none), vibrato depth[, amplitude points (share, level): syllables])
MEOWS = [(0.36, [(0, 700), (0.35, 840), (1, 640)], [(0, "i"), (0.5, "e"), (1, "u")], 0.0, 0.0),             # short mew
         (0.28, [(0, 800), (0.3, 960), (1, 720)], [(0, "i"), (0.5, "e"), (1, "i")], 0.0, 0.0),              # shorter, higher mew
         (0.80, [(0, 580), (0.2, 800), (0.4, 700), (0.5, 640), (0.62, 760), (1, 440)],                       # me-ow: two syllables, falls
          [(0, "i"), (0.2, "e"), (0.42, "e"), (0.55, "a"), (0.75, "a"), (1, "u")], 0.0, 0.0,
          [(0, 1), (0.34, 1), (0.47, 0.45), (0.58, 1), (0.8, 0.9), (1, 1)]),
         (0.45, [(0, 560), (0.3, 600), (0.55, 700), (1, 900)], [(0, "u"), (0.3, "e"), (1, "e")], 30.0, 0.0)]   # mrrp? rolled start, rises


def _n(sec): return int(round(sec * RATE))


def _curve(t, pts):
    T = t[-1] if len(t) > 1 else 1.0
    return np.interp(t / T, [p[0] for p in pts], [float(p[1]) for p in pts])


def _band(x, lo=None, hi=None, order=2):
    """Zero-phase FFT band filter; circular, so a loop stays seamless."""
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / RATE) + 1e-9
    if hi: X *= 1 / np.sqrt(1 + (f / hi) ** (2 * order))
    if lo: X *= 1 / np.sqrt(1 + (lo / f) ** (2 * order))
    return np.fft.irfft(X, len(x))


def _env(n, attack, release):
    e = np.ones(n); a = max(_n(attack), 1); r = max(_n(release), 1)
    e[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2; e[-r:] *= np.cos(np.linspace(0, np.pi / 2, r)) ** 2
    return e


def _formants(t, vowel_pts):
    return [tuple(_curve(t, [(s, VOWELS[v][k][j]) for s, v in vowel_pts]) for j in range(3)) for k in range(3)]


def _voice(t, f0, forms, tilt=0.7):
    """Harmonics of f0 (below 9 kHz), each weighted by the formant resonances at its frequency."""
    ph = 2 * np.pi * np.cumsum(f0) / RATE; out = np.zeros(len(t))
    for k in range(1, 40):
        fk = k * f0
        if fk.min() > 9000: break
        g = sum(gain / (1 + ((fk - fc) / (bw / 2)) ** 2) for fc, bw, gain in forms)
        out += (fk < 9000) * g * np.sin(k * ph) / k ** tilt
    return out


def finish(x, peak, fade_in=0.004, fade_out=0.04):
    x = x - x.mean(); x = x * _env(len(x), fade_in, fade_out); x = x - x.mean()
    return x * (peak / np.abs(x).max())


def meow(i):
    sec, f0p, vp, trill, vib = MEOWS[i][:5]; rng = np.random.default_rng(100 + i); t = np.arange(_n(sec)) / RATE
    f0 = _curve(t, f0p) * (1 + vib * np.sin(2 * np.pi * 5.5 * t))
    nasal = np.clip(t / 0.07, 0, 1)                                  # "m": the formants open over the first 70 ms
    forms = [(fc, bw, g * (0.25 + 0.75 * nasal)) for fc, bw, g in _formants(t, vp)]
    x = _voice(t, f0, forms)
    if trill: x *= 1 - 0.35 * np.clip(1 - t / 0.2, 0, 1) * (0.5 + 0.5 * np.cos(2 * np.pi * trill * t))   # soft roll fading out
    if len(MEOWS[i]) > 5: x *= _curve(t, MEOWS[i][5])                                              # syllables
    x = x + 0.025 * np.abs(x).max() * _band(rng.standard_normal(len(t)), 500, 6000)       # breath
    return finish(x * _env(len(t), 0.03, 0.12), SN.PEAK["Meow"])


def purr():
    """Two breaths twice (out 1.25 s at 26 Hz, in 1.05 s at 22 Hz): each pulse a short low thump (95 + 190 Hz, 6 ms decay) placed
    and filtered circularly, the breath envelope smoothed circularly: the end runs into the start."""
    rng = np.random.default_rng(7); phases = [(1.25, 26.0, 1.0), (1.05, 22.0, 0.7)] * 2
    n = sum(_n(d) for d, _, _ in phases); train = np.zeros(n); env = np.zeros(n); pos = 0
    for dur, rate, amp in phases:
        m = _n(dur); k = 0.0
        while k < dur - 1e-9:
            train[(pos + _n(k)) % n] += amp * rng.uniform(0.8, 1.0); k += rng.uniform(0.93, 1.07) / rate
        env[pos:pos + m] = amp * (0.35 + 0.65 * np.sin(np.pi * np.arange(m) / m) ** 0.5); pos += m
    env = _band(env, None, 8.0)
    kt = np.arange(_n(0.03)) / RATE
    kern = np.exp(-kt / 0.006) * (np.sin(2 * np.pi * 95 * kt) + 0.5 * np.sin(2 * np.pi * 190 * kt)) + 0.3 * rng.standard_normal(len(kt)) * np.exp(-kt / 0.003)
    kp = np.zeros(n); kp[:len(kern)] = kern
    x = np.fft.irfft(np.fft.rfft(train) * np.fft.rfft(kp), n)                       # circular convolution
    x = _band(x, 35, 900) + 0.08 * np.abs(x).max() * _band(rng.standard_normal(n), 200, 1500) * env / env.max()
    x = x * (0.5 + 0.5 * env / env.max()); x = x - x.mean()
    return x * (SN.PEAK["Purr"] / np.abs(x).max())


def hiss():
    rng = np.random.default_rng(31); t = np.arange(_n(0.72)) / RATE
    x = _band(rng.standard_normal(len(t)), 2200, 10000, order=3) + 0.6 * _band(rng.standard_normal(len(t)), 4200, 5200, order=4)
    return finish(x * np.interp(t, [0, 0.015, 0.08, 0.45, 0.72], [0, 1, 0.85, 0.6, 0]), SN.PEAK["Hiss"])


def yawn():
    rng = np.random.default_rng(41); t = np.arange(_n(1.1)) / RATE
    breath = _band(rng.standard_normal(len(t)), 300, 3500)
    v = _voice(t, _curve(t, [(0, 880), (0.35, 760), (1, 380)]), _formants(t, [(0, "e"), (0.4, "a"), (1, "u")]), tilt=1.0)
    x = breath * np.interp(t, [0, 0.12, 0.6, 1.1], [0, 0.55, 0.4, 0]) / np.abs(breath).max()
    x = x + v * np.interp(t, [0, 0.1, 0.5, 0.75, 1.1], [0, 0, 0.9, 0.3, 0]) / np.abs(v).max()
    return finish(x, SN.PEAK["Yawn"])


def land(i):
    rng = np.random.default_rng(51 + i); n = _n(0.2); t = np.arange(n) / RATE; x = np.zeros(n)
    for at, amp in ((0.0, 1.0), ((0.045, 0.06)[i], 0.75)):                         # front paws, then the hind paws
        on = t >= at; tt = np.clip(t - at, 0, None)
        x += on * amp * np.exp(-tt / 0.022) * _band(rng.standard_normal(n), 40, 320)
        x += on * 0.06 * amp * np.exp(-tt / 0.004) * _band(rng.standard_normal(n), 1200, 3500)
    return finish(x, SN.PEAK["Land"], fade_in=0.001, fade_out=0.03)


SYNTH = {"Meow": meow, "Purr": lambda i: purr(), "Hiss": lambda i: hiss(), "Yawn": lambda i: yawn(), "Land": land}


def write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def read_wav(path):
    with wave.open(path) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2: raise ValueError("%s: want 16-bit mono" % path)
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32767, w.getframerate()


def write_all(outdir):
    os.makedirs(outdir, exist_ok=True); paths = []
    for a, name, i in SN.assets():
        paths.append(os.path.join(outdir, a + ".wav")); write_wav(paths[-1], SYNTH[name](i))
    return paths


if __name__ == "__main__":
    print("SOUNDS OK %d" % len(write_all(sys.argv[1])))
