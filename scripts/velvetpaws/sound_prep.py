#!/usr/bin/env python3
"""Prepares the user's own recordings (plan Etappe 4): one take per variant becomes assets/sounds/<asset>.wav, which the build then
uses instead of the synthesis (sounds.source). ffmpeg decodes any format, takes the part --start..--end, mixes to mono 44.1 kHz,
removes rumble (high-pass 60 Hz) and steady noise (afftdn) and cuts the silence (-45 dB) at both ends; NumPy levels to the sound's
peak (sounds.PEAK, as the synthesis), fades in and out (4 / 40 ms), and for a loop (the purr) crossfades its last 0.25 s into the
start instead, so it runs on without a seam. --lowpass HZ keeps only what lies below HZ (48 dB/octave): a purr under a meow.
A take that is silent or shorter than MIN_LEN after trimming (a loop: shorter than 4 crossfades) is refused.
Any rate and channel count works (ffmpeg decodes and resamples; the user's takes are 48 kHz stereo MP3).
Usage: sound_prep.py <take> <asset> [--start S] [--end S] [--lowpass HZ]   (asset: S_VP_Meow_1 ... S_VP_Land_2, see sounds.assets())"""
import argparse, os, subprocess, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from velvetpaws import sounds as SN
from sound_synth import read_wav, write_wav, finish

LOOP_XFADE = 0.25
MIN_LEN, SILENT = 0.05, 10 ** (-60 / 20.0)      # seconds, peak (-60 dBFS) of a usable take
TRIM = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02"


def loop_xfade(x, n):
    """The last n samples faded into the first n: the result ends where it starts."""
    a = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    return np.concatenate([x[-n:] * (1 - a) + x[:n] * a, x[n:-n]])


def _clean(src, dst, start, end, lowpass=None):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None: cmd += ["-ss", str(start)]
    if end is not None: cmd += ["-to", str(end)]
    lp = ",".join(["lowpass=f=%g" % lowpass] * 4) + "," if lowpass else ""
    cmd += ["-i", src, "-ac", "1", "-ar", str(SN.RATE), "-af", "highpass=f=60,%safftdn=nf=-35,%s,areverse,%s,areverse" % (lp, TRIM, TRIM),
            "-c:a", "pcm_s16le", dst]
    subprocess.run(cmd, check=True)


def prepare(src, asset, out_dir=None, start=None, end=None, lowpass=None):
    names_ = {a: n for a, n, _ in SN.assets()}
    if asset not in names_: raise ValueError("%s is no sound asset (%s)" % (asset, ", ".join(sorted(names_))))
    s = SN.by_name(names_[asset]); out_dir = out_dir or os.path.join(W, SN.RECORDINGS_REL); os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "clean.wav"); _clean(src, tmp, start, end, lowpass); x, _ = read_wav(tmp)
    need = 4 * LOOP_XFADE if s.loop else MIN_LEN
    if len(x) < need * SN.RATE or (len(x) and np.abs(x).max() < SILENT):
        raise ValueError("%s: %.3f s left after trimming, peak %.4f: silent or too short (need %.2f s; check --start/--end)"
                         % (src, len(x) / float(SN.RATE), np.abs(x).max() if len(x) else 0.0, need))
    if s.loop:
        x = loop_xfade(x - x.mean(), int(LOOP_XFADE * SN.RATE)); x = x * (SN.PEAK[s.name] / np.abs(x).max())
    else:
        x = finish(x, SN.PEAK[s.name])
    out = os.path.join(out_dir, asset + ".wav"); write_wav(out, x)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("take"); ap.add_argument("asset")
    ap.add_argument("--start", type=float); ap.add_argument("--end", type=float); ap.add_argument("--lowpass", type=float); a = ap.parse_args()
    out = prepare(a.take, a.asset, start=a.start, end=a.end, lowpass=a.lowpass); x, rate = read_wav(out)
    print("PREP OK %s %.2f s" % (out, len(x) / float(rate)))
