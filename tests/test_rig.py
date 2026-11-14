import importlib.util, os, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("cat_rig", os.path.join(W, "tools", "blender", "cat_rig.py"))
rig = importlib.util.module_from_spec(spec); spec.loader.exec_module(rig)


class RigTest(unittest.TestCase):
    def test_root_first_and_parents_exist(self):
        names = [b[0] for b in rig.BONES]
        self.assertEqual(names[0], "root"); self.assertIsNone(rig.BONES[0][1])
        self.assertEqual(len(names), len(set(names)))
        for name, parent, _, _ in rig.BONES[1:]:
            self.assertIn(parent, names[:names.index(name)], name)

    def test_mirrored_sides(self):
        bones = {b[0]: b for b in rig.BONES}
        for name, (_, parent, head, tail) in bones.items():
            if name.endswith("_l"):
                other = bones[name[:-2] + "_r"]
                self.assertAlmostEqual(head[0], -other[2][0]); self.assertAlmostEqual(head[1], other[2][1]); self.assertAlmostEqual(head[2], other[2][2])
                self.assertAlmostEqual(tail[0], -other[3][0])
                if parent.endswith("_l"):
                    self.assertEqual(bones[name[:-2] + "_r"][1], parent[:-2] + "_r", name)

    def test_proportions(self):
        self.assertAlmostEqual(rig.body_length(), 0.46, delta=0.02)
        self.assertAlmostEqual(rig.shoulder_height(), 0.25, delta=0.02)

    def test_withers_from_skin(self):
        bones = {b[0]: b for b in rig.BONES}
        self.assertGreaterEqual(rig.shoulder_height(), bones["spine_03"][2][2] + rig.SKIN["spine_03"])

    def test_faces_minus_y_and_stands_on_floor(self):
        bones = {b[0]: b for b in rig.BONES}
        self.assertLess(bones["head"][3][1], bones["pelvis"][2][1])
        for side in "lr":
            self.assertAlmostEqual(min(bones["toe_" + side][3][2], bones["finger_" + side][3][2]), 0.0, delta=0.005)

    def test_skin_radii_for_deforming_chain(self):
        for b in ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "thigh_l", "upperarm_l", "tail_01", "tail_08"]:
            self.assertGreater(rig.SKIN[b], 0.0, b)


class TailProfileTest(unittest.TestCase):
    """Round 6: the tail root blends into the rump (a little wider) and tapers evenly; no collar where the flare ends."""

    def test_even_taper(self):
        n = rig.tail_length(); s = [i * n / 200 for i in range(201)]; r = [rig.tail_radius_at(x) for x in s]
        for a, b in zip(r, r[1:]): self.assertLessEqual(b, a + 1e-12)                      # never wider further out
        d = [a - b for a, b in zip(r, r[1:])]
        cut = int(200 * (1 - rig.TAIL_TAPER[0] / n))                                           # before the pointed tip
        self.assertLess(max(d[:cut]) / (min(d[:cut]) + 1e-9), 12.0)                         # no sudden narrowing
        self.assertLess(r[0] / rig.tail_radius_at(0.08), 1.6)                                # root only a little wider
        self.assertGreater(r[0], rig.tail_radius_at(0.08) * 1.3)
