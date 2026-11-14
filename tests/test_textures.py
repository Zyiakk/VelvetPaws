import json, math, os, unittest
from PIL import Image, ImageStat

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(W, "build", "velvetpaws", "tex")


def coverage(img, ch, thresh=128):
    band = img.getchannel(ch); hist = band.histogram()
    return sum(hist[thresh:]) / float(sum(hist))


@unittest.skipUnless(os.path.isdir(TEX), "bake first: tools/blender/cat_bake.py")
class TexturesTest(unittest.TestCase):
    def test_sizes(self):
        for name, size in [("mask_a.png", 2048), ("mask_b.png", 2048), ("fur_n.png", 2048), ("card.png", 512), ("eye.png", 512)]:
            self.assertEqual(Image.open(os.path.join(TEX, name)).size, (size, size), name)

    def test_pattern_masks_are_patterns(self):
        a = Image.open(os.path.join(TEX, "mask_a.png")).convert("RGBA")
        # tabby (R): narrow lines (gap:line about 2:1) fading out toward the belly, so less coverage than the others
        # coverage over the whole image (empty texels pull-push filled), so it moves with the UV layout of each model build: spots
        # (B) measured 0.149 .. 0.176 across the round-6 model builds with the same pattern code
        for ch, lo in (("R", 0.08), ("G", 0.15), ("B", 0.12), ("A", 0.15)):
            self.assertTrue(lo < coverage(a, ch) < 0.7, "%s %.2f" % (ch, coverage(a, ch)))

    def test_white_and_skin_are_small(self):
        b = Image.open(os.path.join(TEX, "mask_b.png")).convert("RGB")
        self.assertTrue(0.05 < coverage(b, "R") < 0.4, "R %.3f" % coverage(b, "R"))
        self.assertTrue(0.001 < coverage(b, "G") < 0.06, "G %.4f" % coverage(b, "G"))

    def test_normal_map_is_tangent_space(self):
        n = Image.open(os.path.join(TEX, "fur_n.png")).convert("RGB")
        small = n.resize((64, 64))
        bs = [p[2] for p in small.getdata()]
        self.assertGreater(sum(bs) / len(bs), 200)   # mostly pointing out of the surface
        # real strands, not a flat fill: R and G must vary (a flat (128, 128, 255) map has no variance)
        crop = n.crop((0, 0, 1024, 1024))
        for ch in "RG":
            sd = ImageStat.Stat(crop.getchannel(ch)).stddev[0]
            self.assertGreater(sd, 1.5, "%s std %.2f" % (ch, sd))


@unittest.skipUnless(os.path.isfile(os.path.join(TEX, "eye.png")), "bake first: tools/blender/cat_bake.py")
class EyeTest(unittest.TestCase):
    """eye.png (round 6): the pupil field in G drawn at PupilOpen as M_VP_CatEye does (names.pupil_cover): a thin slit at 0, a vertical
    ellipse at the default, nearly round at 1; A (iris radius) never 0 (UE's PNG import refills transparent texels)."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, os.path.join(W, "scripts")); from velvetpaws import names
        cls.names = names; im = Image.open(os.path.join(TEX, "eye.png")).convert("RGBA"); cls.n = im.size[0]
        cls.g = im.getchannel("G").load(); cls.a = im.getchannel("A"); cls.r = im.getchannel("R").load()

    def front(self, xh, yv):
        """Pixel of the front point (xh right, yv up on the unit sphere's front) in eye.png (v = 1 at the top row, u = 0.75 up)."""
        th = math.asin(min(1.0, math.hypot(xh, yv))); ph = math.atan2(xh, yv)
        u = (ph / (2 * math.pi) + 0.75) % 1.0; v = 1 - th / math.pi
        return round(u * (self.n - 1)), round((1 - v) * (self.n - 1))

    def extent(self, open_, axis):
        """Half extent of the pupil (coverage >= 0.5) along x (axis 0) or y (1) from the centre, in front units."""
        e = 0.0
        for i in range(1, 80):
            d = i * 0.01; xh, yv = (d, 0.0) if axis == 0 else (0.0, d)
            for sgn in (1, -1):
                px = self.front(sgn * xh, sgn * yv)
                if self.names.pupil_cover(self.g[px] / 255.0, open_) >= 0.5: e = max(e, d)
        return e

    def test_alpha_never_zero(self):
        self.assertGreater(self.a.getextrema()[0], 0)

    def test_pupil_shapes(self):
        N = self.names
        w0, h0 = self.extent(0.0, 0), self.extent(0.0, 1)
        wd, hd = self.extent(N.DEF_PUPIL_OPEN, 0), self.extent(N.DEF_PUPIL_OPEN, 1)
        w1, h1 = self.extent(1.0, 0), self.extent(1.0, 1)
        self.assertLess(w0, 0.09, "slit too wide"); self.assertGreater(h0 / max(w0, 0.01), 5.0, "slit")
        self.assertTrue(1.8 < hd / wd < 3.5, "default: a moderate vertical ellipse, %.2f x %.2f" % (wd, hd))
        self.assertLess(h1 / w1, 1.35, "open: nearly round, %.2f x %.2f" % (w1, h1))
        self.assertTrue(w0 < wd < w1)

    def test_limbal_ring_darker_than_iris(self):
        mid = self.r[self.front(0.0, 0.62)]; edge = self.r[self.front(0.0, math.sin(math.radians(56)))]
        self.assertLess(edge, 0.6 * mid, "limbal ring %d vs iris %d" % (edge, mid))


@unittest.skipUnless(os.path.isfile(os.path.join(TEX, "regions.json")), "bake first: tools/blender/cat_bake.py")
class PlacementTest(unittest.TestCase):
    """Where the masks landed on the cat (regions.json from the bake: texels >= 0.5 per region and their mean
    position, object space and head-local, cm; head-local x lateral, y back from the nose tip, z up)."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(TEX, "regions.json")) as f: cls.r = json.load(f)

    def region(self, name, min_texels=50):
        reg = self.r[name]
        self.assertGreater(reg["texels"], min_texels, name)
        return reg

    def test_nose_leather_front_centre(self):
        x, y, z = self.region("nose_leather")["mean_head_cm"]
        self.assertLess(abs(x), 0.15, "nose leather off centre: x %.2f" % x)
        self.assertLess(y, 1.0, "nose leather not at the front of the head: y %.2f" % y)
        self.assertTrue(0.0 < z < 1.0, "nose leather height %.2f" % z)

    def test_inner_ears_in_the_ear_cups(self):
        for side, sign in (("l", 1), ("r", -1)):
            m = self.region("inner_ear_" + side, 500)["mean_head_cm"]
            ref = self.r["ref"]["ear_cup_%s_head_cm" % side]
            self.assertGreater(sign * m[0], 1.5, "inner ear %s on the wrong side: x %.2f" % (side, m[0]))
            self.assertLess(math.dist(m, ref), 1.0, "inner ear %s %s, cup centre %s" % (side, m, ref))

    def test_white_markings_placed(self):
        chest, belly = self.region("white_chest")["mean_cm"], self.region("white_belly")["mean_cm"]
        paws, muzzle = self.region("white_paws")["mean_cm"], self.region("white_muzzle")["mean_head_cm"]
        shoulder = self.r["ref"]["shoulder_joint_cm"]
        self.assertLess(chest[1], shoulder[1] + 3.0, "chest bib behind the shoulders: y %.1f" % chest[1])
        self.assertLess(chest[1], belly[1], "chest bib behind the belly")
        self.assertLess(paws[2], 4.0, "socks not at the paws: z %.1f" % paws[2])
        self.assertLess(belly[2], 13.0, "belly white too high: z %.1f" % belly[2])
        self.assertLess(abs(muzzle[0]), 0.3, "muzzle white off centre")
        self.assertLess(muzzle[1], 3.0, "muzzle white not on the muzzle: y %.1f" % muzzle[1])
        self.assertLess(muzzle[2], 0.5, "muzzle white too high: z %.1f" % muzzle[2])
        for name in ("white_chest", "white_belly", "white_paws"):
            self.assertLess(abs(self.r[name]["mean_cm"][0]), 1.5, "%s not symmetric" % name)

    def test_tabby_darker_on_the_back_than_the_belly(self):
        t = self.r["tabby"]
        self.assertGreater(t["back_texels"], 1000); self.assertGreater(t["belly_texels"], 1000)
        self.assertGreater(t["back_mean"], t["belly_mean"] + 0.1, t)
