#!/usr/bin/env python3
"""Review of the cat's sounds as the build uses them (sounds.source: recording or synthesis): one spectrogram strip per WAV
(0-11 kHz, 70 dB, 10 ms hop) into sounds.png, and every sound in one file all.wav (0.4 s apart) to listen to.
Usage: sound_sheet.py <outdir>  ->  "SOUND SHEET OK <n>"."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); W = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from velvetpaws import sounds as SN
from sound_synth import read_wav, write_wav


def spectrogram(x, rate, hop=441, win=1024, fmax=11000.0):
    pad = np.concatenate([np.zeros(win // 2), x, np.zeros(win // 2)])
    frames = np.stack([pad[i:i + win] * np.hanning(win) for i in range(0, len(pad) - win, hop)])
    m = np.abs(np.fft.rfft(frames, axis=1))[:, :int(fmax / rate * win)]
    db = 20 * np.log10(m + 1e-9); db = np.clip((db - db.max() + 70.0) / 70.0, 0, 1)
    return (255 * db.T[::-1]).astype(np.uint8)


def main(out):
    os.makedirs(out, exist_ok=True); strips, allx = [], []
    for a, _, _ in SN.assets():
        x, rate = read_wav(SN.source(W, a)); s = Image.fromarray(spectrogram(x, rate)).convert("RGB")
        row = Image.new("RGB", (s.width + 170, s.height), (24, 24, 24)); row.paste(s, (170, 0))
        ImageDraw.Draw(row).text((6, 6), a + (" (rec)" if SN.is_recording(W, a) else ""), fill=(235, 235, 235))
        strips.append(row); allx += [x, np.zeros(int(0.4 * rate))]
    sheet = Image.new("RGB", (max(s.width for s in strips), sum(s.height + 6 for s in strips)), (0, 0, 0)); y = 0
    for s in strips: sheet.paste(s, (0, y)); y += s.height + 6
    sheet.save(os.path.join(out, "sounds.png")); write_wav(os.path.join(out, "all.wav"), np.concatenate(allx))
    print("SOUND SHEET OK %d" % len(strips))


if __name__ == "__main__":
    main(sys.argv[1])
