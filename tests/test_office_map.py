import math, os, sys, unittest
import numpy as np

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts"))
from velvetpaws import office_map as OM, brain as B

CELL = 5.0


def synthetic():
    """Two rooms (6 x 4 m each, floor z=0) split by a wall at x=600 with a 1 m door gap at y=150..250; in room 1 a sofa block (top 45,
    solid), a table (top 75, floor free under it), a carpet (2 cm) and a narrow shelf top (z 120, 10 cm deep); the player start in room 1."""
    nx, ny, K = 240, 80, 8
    z = np.full((nx, ny, K), np.nan, np.float32); nz = np.full_like(z, np.nan); inst = np.full((nx, ny, K), -1, np.int32)
    def put(x0, x1, y0, y1, h, mi, normal=1.0):
        for i in range(int(x0 / CELL), int(x1 / CELL)):
            for j in range(int(y0 / CELL), int(y1 / CELL)):
                col = [(z[i, j, k], nz[i, j, k], inst[i, j, k]) for k in range(K) if not np.isnan(z[i, j, k])]
                col.append((h, normal, mi)); col.sort(key=lambda c: -c[0])
                for k, (a, b, c) in enumerate(col[:K]): z[i, j, k], nz[i, j, k], inst[i, j, k] = a, b, c
    put(0, 1200, 0, 400, 0.0, 0)                                   # floor
    def solid(x0, x1, y0, y1):                                     # a closed body: nothing under its top surface
        for i in range(int(x0 / CELL), int(x1 / CELL)):
            for j in range(int(y0 / CELL), int(y1 / CELL)): z[i, j, 1:] = np.nan; inst[i, j, 1:] = -1; nz[i, j, 1:] = np.nan
    put(600, 610, 0, 150, 250.0, 1); put(600, 610, 250, 400, 250.0, 1); solid(600, 610, 0, 150); solid(600, 610, 250, 400)   # wall, door gap
    put(100, 300, 300, 390, 45.0, 2); solid(100, 300, 300, 390)   # sofa
    for x0 in (400, 700): put(x0, x0 + 100, 300, 390, 45.0, 2); solid(x0, x0 + 100, 300, 390)   # two more separate cushions of the same instance
    put(350, 470, 50, 130, 75.0, 3); put(350, 470, 50, 130, 72.0, 3, normal=-1.0)   # table top and its underside; floor stays under it
    put(50, 150, 50, 150, 2.0, 4)                                  # carpet
    put(400, 500, 380, 390, 120.0, 5)                              # shelf, 10 cm deep
    meshes = [{"actor": a, "cls": c, "comp": "c", "mesh": "/Game/T/" + m} for a, c, m in
              (("Floor", "StaticMeshActor", "SM_Floor"), ("Wall", "StaticMeshActor", "SM_Wall"), ("Sofa1", "Sofa_C", "SM_Sofa"),
               ("Desk1", "StaticMeshActor", "SM_Desk"), ("Carpet", "StaticMeshActor", "SM_Carpet"), ("Shelf", "StaticMeshActor", "SM_Shelf"))]
    return OM.Scan(z, nz, inst, (0.0, 0.0), CELL, meshes, [[200.0, 200.0, 92.0, 0.0]], [[605.0, 200.0, 0.0, 0.0]])


class MapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.M = OM.build(synthetic())

    def test_one_component_through_the_door(self):
        pts = [w["loc"] for w in self.M["walk"]]
        self.assertTrue(any(p[0] > 650 for p in pts)); self.assertTrue(any(p[0] < 550 for p in pts))
        a = min(range(len(pts)), key=lambda i: (pts[i][0] - 100) ** 2 + (pts[i][1] - 100) ** 2)
        b = min(range(len(pts)), key=lambda i: (pts[i][0] - 1100) ** 2 + (pts[i][1] - 300) ** 2)
        i, path = a, [a]
        for _ in range(len(pts)):
            if i == b: break
            i = B.next_hop(self.M["walk"][i]["next"], b); self.assertGreaterEqual(i, 0); path.append(i)
        self.assertEqual(i, b)
        crossing = [pts[k] for k in path if 580 <= pts[k][0] <= 630]
        self.assertTrue(crossing and all(150 <= p[1] <= 250 for p in crossing))   # through the door gap

    def test_no_walk_point_on_or_under_the_sofa(self):
        for x, y, zz in (w["loc"] for w in self.M["walk"]):
            self.assertFalse(100 - B.CAPSULE_R < x < 300 + B.CAPSULE_R and 300 - B.CAPSULE_R < y < 390, (x, y))
            self.assertAlmostEqual(zz, 0.0, delta=2.5)                          # floor or the 2 cm carpet

    def test_spots(self):
        by = {s["src_debug"].split("/")[0]: s for s in self.M["spots"]}
        self.assertIn("Sofa1", by); self.assertIn("Desk1", by)
        self.assertNotIn("Carpet", by); self.assertNotIn("Shelf", by)                 # too low / too narrow
        self.assertAlmostEqual(by["Sofa1"]["height"], 45.0, delta=0.5)
        self.assertGreaterEqual(by["Sofa1"]["posture"], B.P_LIE); self.assertEqual(by["Sofa1"]["weight"], 3.0)
        fx, fy, fz = by["Desk1"]["from"]; self.assertAlmostEqual(fz, 0.0)
        self.assertLessEqual(((fx - by["Desk1"]["loc"][0]) ** 2 + (fy - by["Desk1"]["loc"][1]) ** 2) ** 0.5, 120.0)

    def test_limits(self):
        self.assertLessEqual(len(self.M["walk"]), OM.MAX_POINTS)
        for w in self.M["walk"]: self.assertEqual(len(w["next"]), 2 * len(self.M["walk"])); self.assertTrue(w["next"].isalnum())

    def test_per_instance_cap_across_regions(self):
        self.assertEqual(len([s for s in self.M["spots"] if s["src_debug"].startswith("Sofa1/")]), OM.PER_INSTANCE)

    def test_labels_are_neutral(self):
        for s in self.M["spots"]: self.assertRegex(s["label"], r"^[a-z]+ \d+$"); self.assertNotIn("SM_", s["label"])
        self.assertTrue(any(s["label"].startswith("sofa ") for s in self.M["spots"]))

    def test_encoding_cap(self):
        self.assertLess(OM.MAX_POINTS, B.HOP_NONE)
        with self.assertRaises(ValueError): B.encode_hops([0] * B.HOP_NONE)

    def test_window_spot_in_front_of_the_pane(self):
        # a 15 cm sill (z 87) in the wall at y 280..295, room at y < 280: the spot moves from the sill's middle line (where the pane
        # stands) to LEDGE_IN inside the room-side edge, and the take-off point lies square in front of it
        nx, ny, K = 80, 64, 8
        z = np.full((nx, ny, K), np.nan, np.float32); nz = np.full_like(z, np.nan); inst = np.full((nx, ny, K), -1, np.int32)
        z[:, :, 0], nz[:, :, 0], inst[:, :, 0] = 0.0, 1.0, 0
        for j in range(int(280 / CELL), int(295 / CELL)):
            for i in range(int(100 / CELL), int(300 / CELL)): z[i, j, :2], nz[i, j, :2], inst[i, j, :2] = (87.0, 0.0), (1.0, 1.0), (1, 0)
        for j in range(int(295 / CELL), ny):
            for i in range(nx): z[i, j, :2], nz[i, j, :2], inst[i, j, :2] = (250.0, 0.0), (1.0, 1.0), (2, 0)
        meshes = [{"actor": a, "cls": "StaticMeshActor", "comp": "c", "mesh": "/Game/T/" + m} for a, m in
                  (("Floor", "SM_Floor"), ("Window_A3", "Window_A"), ("Wall", "SM_Wall"))]
        M = OM.build(OM.Scan(z, nz, inst, (0.0, 0.0), CELL, meshes, [[200.0, 100.0, 92.0, 0.0]], []))
        win = [s for s in M["spots"] if s["label"].startswith("window")]
        self.assertEqual(len(win), 1); x, y, top = win[0]["loc"]; fx, fy, _ = win[0]["from"]
        self.assertAlmostEqual(y, 280.0 + OM.LEDGE_IN, delta=0.3); self.assertAlmostEqual(top, 87.0)
        self.assertAlmostEqual(fx, x, delta=0.01); self.assertLess(fy, 280.0)

    def test_kinds(self):
        m = lambda actor, mesh, cls="StaticMeshActor": {"actor": actor, "mesh": "/G/" + mesh, "cls": cls}
        for a, mesh in (("SM_Printer_33", "SM_Printer"), ("SM_Keyboard_1", "SM_Keyboard"), ("SM_Mousepad_5", "SM_Mousepad"), ("SM_Sink_A_2", "SM_Sink_A")):
            self.assertIsNone(OM.kind_of(m(a, mesh)))
        self.assertEqual(OM.kind_of(m("SM_Modern_Bed_A_Mattress_5", "SM_Modern_Bed_A_Mattress"))[:4:2], ("bed", B.P_SLEEP))
        self.assertEqual(OM.kind_of(m("SM_Bed_Table_8", "SM_Bed_Table"))[:2], ("bedside", 1.0))
        self.assertEqual(OM.kind_of(m("SM_ExecutiveChair_8", "SM_ArmchairA"))[:2], ("chair", 1.0))
        self.assertEqual(OM.kind_of(m("Office_Room_C_35", "Office_Room_C"))[:4:2], ("counter", B.P_LIE))
        self.assertEqual(OM.kind_of(m("Window_A3", "Window_A"))[3], 1)


def _door_scan(hinge_y=250.0):
    """synthetic() with the door actor's root at the gap's +Y end (the hinge; the leaf spans local -Y like DoorWood_Office)."""
    S = synthetic(); S.doors = [[605.0, hinge_y, 0.0, 0.0]]; return S


class DoorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.M = OM.build(_door_scan())

    def test_doorway_point_and_probes(self):
        d = [w for w in self.M["walk"] if w["door"] >= 0]
        self.assertEqual(len(d), 1); x, y, _ = d[0]["loc"]
        self.assertAlmostEqual(x, 605.0, delta=8.0); self.assertAlmostEqual(y, 200.0, delta=8.0)    # the gap's centre, not the hinge
        a, b = d[0]["door_a"], d[0]["door_b"]
        self.assertAlmostEqual(abs(a[0] - b[0]), 2 * OM.DOOR_PROBE[0], delta=0.5); self.assertAlmostEqual(a[1], b[1], delta=0.5)
        self.assertLess(min(a[0], b[0]), 600.0); self.assertGreater(max(a[0], b[0]), 610.0)        # one probe on each side of the wall
        self.assertAlmostEqual(a[2], OM.DOOR_PROBE[1], delta=1.0)
        for w in self.M["walk"]:
            if w["door"] < 0: self.assertEqual(w["door_a"], [0.0, 0.0, 0.0])

    def test_every_way_through_passes_the_doorway_point(self):
        W_ = self.M["walk"]; door = next(i for i, w in enumerate(W_) if w["door"] >= 0)
        for i, w in enumerate(W_):
            for b in range(len(W_)):
                if B.next_hop(w["next"], b) == b and i != b and b != door and i != door:
                    self.assertFalse((w["loc"][0] - 605) * (W_[b]["loc"][0] - 605) < 0, (w["loc"], W_[b]["loc"]))   # no link jumps the wall

    def test_no_doorway_keeps_a_plain_point(self):
        M = OM.build(_door_scan(200.0))            # the hinge in the gap's middle: only 50 cm of gap on its -Y side, no doorway
        self.assertFalse(any(w["door"] >= 0 for w in M["walk"]))
        self.assertTrue(any(w["loc"][0] > 650 for w in M["walk"]))

    def test_spot_walk_index(self):
        for s in self.M["spots"]:
            w = self.M["walk"][s["walk"]]["loc"]
            self.assertLess(((w[0] - s["from"][0]) ** 2 + (w[1] - s["from"][1]) ** 2) ** 0.5, 160.0)


class FacingTest(unittest.TestCase):
    def test_spots_face_their_open_side(self):
        M = OM.build(synthetic())
        for s in M["spots"]:
            a = math.radians(s["yaw"]); fx, fy = s["from"][0] - s["loc"][0], s["from"][1] - s["loc"][1]
            self.assertGreater(math.cos(a) * fx + math.sin(a) * fy, 0.0, s["label"])          # faces the take-off side (the room)
            self.assertAlmostEqual(s["yaw"] % 90.0, 0.0, delta=1.0)                          # squared to the (axis-aligned) pieces

    def test_squared_to_the_piece(self):
        self.assertAlmostEqual(OM.facing("sofa", (0.0, 0.0), (-20.0, -75.0), (1.0, 0.0)), -90.0)   # take-off 15 degrees off the front
        self.assertAlmostEqual(OM.facing("sofa", (0.0, 0.0), (-20.0, -75.0)), round(math.degrees(math.atan2(-75.0, -20.0)), 1))

    def test_window_faces_the_pane(self):
        self.assertAlmostEqual(OM.facing("window", (0.0, 281.0), (0.0, 236.0)), 90.0)
        self.assertAlmostEqual(OM.facing("sofa", (0.0, 281.0), (0.0, 236.0)), -90.0)


def _shelf_scan():
    """Floor and a 45 x 60 cm shelf unit (instance "Shelf"): a floor compartment (board at 3, next board's underside at 47), a raised one
    (board at 50, underside at 97), and the open top at 100; side boards closed. The room is at x > 145."""
    nx, ny, K = 80, 60, 8
    z = np.full((nx, ny, K), np.nan, np.float32); nz = np.full_like(z, np.nan); inst = np.full((nx, ny, K), -1, np.int32)
    z[:, :, 0], nz[:, :, 0], inst[:, :, 0] = 0.0, 1.0, 0
    def col(i, j, layers):
        for k, (h, n) in enumerate(sorted(layers, key=lambda c: -c[0])): z[i, j, k], nz[i, j, k], inst[i, j, k] = h, n, 1
        z[i, j, len(layers):] = np.nan; inst[i, j, len(layers):] = -1
    for i in range(int(100 / CELL), int(145 / CELL)):
        for j in range(int(95 / CELL), int(165 / CELL)):
            side = j < int(100 / CELL) or j >= int(160 / CELL)
            col(i, j, [(100.0, 1.0)] if side else [(100.0, 1.0), (97.0, -1.0), (50.0, 1.0), (47.0, -1.0), (3.0, 1.0)])
    meshes = [{"actor": "Floor", "cls": "StaticMeshActor", "comp": "c", "mesh": "/Game/T/SM_Floor"},
              {"actor": "CollectionShelf9", "cls": "CollectionShelf_C", "comp": "c", "mesh": "/Game/T/Bookshelf_A"}]
    return OM.Scan(z, nz, inst, (0.0, 0.0), CELL, meshes, [[300.0, 130.0, 92.0, 0.0]], [])


class CubbyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.M = OM.build(_shelf_scan())

    def test_compartments(self):
        cub = [s for s in self.M["spots"] if s["label"].startswith("cubby")]
        low = [s for s in cub if s["height"] < B.SPOT_MIN]; high = [s for s in cub if s["height"] >= B.SPOT_MIN]
        self.assertEqual(len(low), 1); self.assertEqual(len(high), 1)
        self.assertAlmostEqual(low[0]["loc"][2], 3.0); self.assertAlmostEqual(low[0]["room"], 44.0)
        self.assertAlmostEqual(high[0]["loc"][2], 50.0); self.assertAlmostEqual(high[0]["room"], 47.0)
        for s in cub:
            self.assertEqual(s["weight"], OM.CUBBY_WEIGHT); self.assertAlmostEqual(s["yaw"], 0.0, delta=1.0)    # faces out of the shelf
            self.assertGreater(s["from"][0], 145.0); self.assertGreaterEqual(s["room"], 2 * B.CAPSULE_HH * B.SIZE_MAX / 100.0 + OM.ROOM_MARGIN)
        top = [s for s in self.M["spots"] if s["label"].startswith("shelf")]
        self.assertTrue(top and all(s["room"] == OM.OPEN_ROOM for s in top))

    def test_only_shelves_have_covered_spots(self):
        S = _shelf_scan(); S.meshes[1] = dict(S.meshes[1], actor="Desk9", cls="StaticMeshActor", mesh="/Game/T/SM_Desk")
        self.assertFalse([s for s in OM.build(S)["spots"] if s["room"] < OM.COVERED])
