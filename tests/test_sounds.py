import os, shutil, sys, tempfile, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts")); sys.path.insert(0, os.path.join(W, "tools", "blender"))
from velvetpaws import sounds as SN, names
import cat_seqs as CS


class Catalog(unittest.TestCase):
    def test_spec_sounds(self):
        self.assertEqual([s.name for s in SN.SOUNDS], ["Meow", "Purr", "Hiss", "Yawn", "Land"])
        self.assertGreaterEqual(SN.variants("Meow"), 2)                    # "mehrere Varianten"
        self.assertTrue(SN.by_name("Purr").loop)
        self.assertEqual([s.name for s in SN.SOUNDS if s.loop], ["Purr"])
        for s in SN.SOUNDS: self.assertIn(s.att, SN.ATTENUATION); self.assertIn(s.name, SN.PEAK); self.assertTrue(0 < s.gain <= 1.0)

    def test_asset_names(self):
        a = [x for x, _, _ in SN.assets()]
        self.assertEqual(a[:4], ["S_VP_Meow_1", "S_VP_Meow_2", "S_VP_Meow_3", "S_VP_Meow_4"])
        self.assertIn("S_VP_Purr", a); self.assertIn("S_VP_Land_2", a); self.assertEqual(len(a), len(set(a)))
        self.assertEqual(SN.obj_path("Purr"), "/Game/Mod/VelvetPaws/Sound/S_VP_Purr.S_VP_Purr")
        self.assertEqual(SN.att_asset("Cat"), "ATT_VP_Cat")

    def test_in_the_pak_list(self):
        pak = names.pak_assets(CS.ORDER, [m["name"] for m in CS.MONTAGES])
        for x in SN.pak_assets(): self.assertIn(x, pak)
        self.assertIn("Sound/ATT_VP_Purr", pak); self.assertIn("Sound/S_VP_Meow_1", pak)

    def test_source_prefers_a_recording(self):
        with tempfile.TemporaryDirectory() as w:
            self.assertEqual(SN.source(w, "S_VP_Hiss"), os.path.join(names.build_dir(w), "sound", "S_VP_Hiss.wav"))
            self.assertFalse(SN.is_recording(w, "S_VP_Hiss"))
            os.makedirs(os.path.join(w, SN.RECORDINGS_REL)); rec = os.path.join(w, SN.RECORDINGS_REL, "S_VP_Hiss.wav")
            open(rec, "wb").close()
            self.assertEqual(SN.source(w, "S_VP_Hiss"), rec); self.assertTrue(SN.is_recording(w, "S_VP_Hiss"))


import numpy as np
sys.path.insert(0, os.path.join(W, "scripts", "velvetpaws"))
import sound_synth as SY
import sound_prep as PR

RATE = SN.RATE


def f0(x, a, b):
    """Fundamental by autocorrelation between shares a and b of x (300-1100 Hz)."""
    s = x[int(a * len(x)):int(b * len(x))]; s = s - s.mean(); n = len(s)
    ac = np.fft.irfft(np.abs(np.fft.rfft(s, 2 * n)) ** 2)[:n]
    lo, hi = int(RATE / 1100), int(RATE / 300)
    return RATE / (lo + int(np.argmax(ac[lo:hi])))


def centroid(x):
    p = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / RATE); return float((f * p).sum() / p.sum())


class Synth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x = {a: SY.SYNTH[name](i) for a, name, i in SN.assets()}

    def test_levels_and_dc(self):
        for a, x in self.x.items():
            base = next(n for b, n, _ in SN.assets() if b == a)
            self.assertAlmostEqual(np.abs(x).max(), SN.PEAK[base], places=3, msg=a)
            self.assertLess(abs(x.mean()), 2e-3, a)

    def test_lengths(self):
        want = {"S_VP_Meow_1": 0.36, "S_VP_Meow_2": 0.28, "S_VP_Meow_3": 0.80, "S_VP_Meow_4": 0.45, "S_VP_Purr": 4.6,
                "S_VP_Hiss": 0.72, "S_VP_Yawn": 1.1, "S_VP_Land_1": 0.2, "S_VP_Land_2": 0.2}
        for a, s in want.items(): self.assertAlmostEqual(len(self.x[a]) / RATE, s, places=2, msg=a)

    def test_meows_are_cat_pitched(self):
        for i in range(SN.variants("Meow")):
            x = self.x[SN.asset("Meow", i)]
            self.assertTrue(380 <= f0(x, 0.3, 0.7) <= 1000, (i, f0(x, 0.3, 0.7)))
        x = self.x[SN.asset("Meow", 3)]
        self.assertGreater(f0(x, 0.75, 0.95), f0(x, 0.3, 0.5))          # the questioning one rises

    def test_first_meow_unchanged(self):
        import hashlib
        self.assertEqual(hashlib.sha256(SY.meow(0).tobytes()).hexdigest(), "c2915a8baee39cdacc90885e82ad994ac6ce4a649de6f49394760b504da3bf61")

    def test_noise_sounds(self):
        self.assertGreater(centroid(self.x["S_VP_Hiss"]), 3000.0)
        for a in ("S_VP_Land_1", "S_VP_Land_2"): self.assertLess(centroid(self.x[a]), 800.0)

    def test_purr_pulses_and_loops(self):
        x = self.x["S_VP_Purr"]
        k = int(0.005 * RATE); env = np.convolve(np.abs(x), np.ones(k) / k, "same"); env -= env.mean()
        f = np.fft.rfftfreq(len(env), 1 / RATE); p = np.abs(np.fft.rfft(env)); band = (f > 5) & (f < 60)
        self.assertTrue(18.0 <= f[band][np.argmax(p[band])] <= 30.0)
        d = np.abs(np.diff(x)); self.assertLessEqual(abs(x[0] - x[-1]), d.max())          # no step at the seam
        r = lambda s: np.sqrt((s ** 2).mean()); n = int(0.1 * RATE)
        self.assertTrue(0.5 < r(x[-n:]) / r(x[:n]) < 2.0)

    def test_reproducible_and_written(self):
        self.assertTrue(np.array_equal(SY.meow(1), SY.meow(1)))
        with tempfile.TemporaryDirectory() as d:
            paths = SY.write_all(d)
            self.assertEqual(sorted(os.path.basename(p)[:-4] for p in paths), sorted(a for a, _, _ in SN.assets()))
            x, rate = SY.read_wav(paths[0])
            self.assertEqual(rate, RATE); self.assertGreater(len(x), 1000)


class Prep(unittest.TestCase):
    def test_loop_crossfade_is_seamless(self):
        t = np.arange(int(1.0 * RATE)) / RATE; x = np.sin(2 * np.pi * 101.3 * t)      # no whole number of cycles: a seam
        self.assertGreater(abs(x[-1] - x[0]), 0.05)
        y = PR.loop_xfade(x, int(0.25 * RATE))
        self.assertEqual(len(y), len(x) - int(0.25 * RATE))
        self.assertLess(abs(y[-1] - y[0]), np.abs(np.diff(y)).max() * 1.01)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg missing")
    def test_take_is_cut_levelled_and_placed(self):
        rng = np.random.default_rng(3)
        raw = np.concatenate([np.zeros(int(0.5 * RATE)), SY.meow(1), np.zeros(int(0.6 * RATE))])
        raw = 0.5 * raw + 0.003 * rng.standard_normal(len(raw))                        # quiet room noise
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "take.wav"); SY.write_wav(src, raw)
            out = PR.prepare(src, "S_VP_Meow_2", out_dir=d)
            self.assertEqual(out, os.path.join(d, "S_VP_Meow_2.wav"))
            y, rate = SY.read_wav(out)
            self.assertEqual(rate, RATE)
            self.assertLess(len(y), len(raw) - int(0.8 * RATE))                       # the silence is cut
            self.assertAlmostEqual(np.abs(y).max(), SN.PEAK["Meow"], places=2)
            self.assertLess(max(abs(y[0]), abs(y[-1])), 0.01)                          # faded

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg missing")
    def test_stereo_48k_take_lowpass_and_refusals(self):
        import wave
        def stereo48(path, left, right):
            with wave.open(path, "wb") as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes((np.stack([left, right], 1) * 32767).astype("<i2").tobytes())
        t = np.arange(int(1.5 * 48000)) / 48000.0
        low, high = 0.3 * np.sin(2 * np.pi * 120 * t), 0.3 * np.sin(2 * np.pi * 1000 * t)   # purr band, meow band
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "take.wav"); stereo48(src, low + high, low + high)
            y, rate = SY.read_wav(PR.prepare(src, "S_VP_Purr", out_dir=d, start=0.1, end=1.4, lowpass=400))
            self.assertEqual(rate, RATE); self.assertAlmostEqual(len(y) / RATE, 1.3 - PR.LOOP_XFADE, delta=0.02)
            p = np.abs(np.fft.rfft(y)); f = np.fft.rfftfreq(len(y), 1 / RATE)
            self.assertLess(p[(f > 900) & (f < 1100)].max(), 0.01 * p[(f > 100) & (f < 140)].max())   # the meow band is gone
            stereo48(src, 0 * t, 0 * t)
            with self.assertRaises(ValueError): PR.prepare(src, "S_VP_Meow_1", out_dir=d)                  # silent
            stereo48(src, low + high, low + high)
            with self.assertRaises(ValueError): PR.prepare(src, "S_VP_Purr", out_dir=d, start=0.1, end=0.6)  # loop too short
            with self.assertRaises(ValueError): PR.prepare(src, "S_VP_Meow_1", out_dir=d, start=0.1, end=0.12)

    def test_unknown_asset_refused(self):
        with self.assertRaises(ValueError): PR.prepare("x.wav", "S_VP_Bark")


if __name__ == "__main__":
    unittest.main()
