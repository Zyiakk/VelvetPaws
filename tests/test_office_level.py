import math, os, sys, unittest
import numpy as np

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts"))
from velvetpaws import office_level as O

EXTRACT = os.path.join(W, "build", "velvetpaws", "office", "pak", "TheKillingAntidote", "Content")


class MathTest(unittest.TestCase):
    def test_rotator_axes(self):
        R = O.rot_matrix(0, 90, 0); np.testing.assert_allclose(R @ [1, 0, 0], [0, 1, 0], atol=1e-9)    # yaw: X -> Y
        R = O.rot_matrix(90, 0, 0); np.testing.assert_allclose(R @ [1, 0, 0], [0, 0, 1], atol=1e-9)    # pitch up: X -> Z
        R = O.rot_matrix(10, 20, 30); np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-9)

    def test_affine_and_chain(self):
        parent = O.affine((100, 0, 0), (0, 90, 0), (2, 2, 2)); child = O.affine((10, 0, 5), (0, 0, 0), (1, 1, 1))
        p = (parent @ child) @ [0, 0, 0, 1]
        np.testing.assert_allclose(p[:3], [100, 20, 10], atol=1e-9)


@unittest.skipUnless(os.path.exists(os.path.join(EXTRACT, "Project", "Maps", "JodisOffice.umap")), "run scripts/office_extract.sh --level first")
class LevelFactsTest(unittest.TestCase):
    def setUp(self): self.L = O.read_level(EXTRACT, "Project/Maps/JodisOffice.umap")

    def test_player_starts_on_floor(self):
        self.assertEqual(len(self.L["player_starts"]), 4)
        for x, y, z, yaw in self.L["player_starts"]: self.assertAlmostEqual(z, 92.0, delta=1.0)

    def test_furniture_blueprints_resolved(self):
        sofas = {m["actor"] for m in self.L["meshes"] if m["cls"] == "Sofa_C"}
        self.assertEqual(len(sofas), 3)
        self.assertGreaterEqual(len(self.L["meshes"]), 180)
        self.assertTrue(all(m["mesh"].startswith("/Game/") for m in self.L["meshes"]))

    def test_doors_listed_not_meshed(self):
        self.assertGreaterEqual(len(self.L["doors"]), 4)                       # DoorWood_Office x4 and other door classes
        self.assertFalse([m for m in self.L["meshes"] if "Door" in m["cls"]])
