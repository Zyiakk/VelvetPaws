import importlib.util, math, os, sys, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "tools", "blender"))
import cat_motion as M
import cat_poses as P


class MotionTest(unittest.TestCase):
    def test_stand_is_rest(self):
        z = M.zero_pose()
        for k, v in P.STAND.items():
            self.assertAlmostEqual(v, z[k], msg=k)
        self.assertEqual((P.STAND["hl_x"], P.STAND["hl_f"], P.STAND["hl_z"]), M.REST_PAW["hl"])

    def test_all_poses_complete_and_in_limits(self):
        for tag, pose in P.POSES.items():
            self.assertEqual(set(pose), set(M.CHANNELS), tag)
            self.assertEqual(M.check_pose(pose), [], tag)

    def test_tracks_hold_and_no_overshoot(self):
        T = M.Tracks({"a": 0.0}).add(1.0, a=10.0).add(2.0, a=10.0).add(3.0, a=0.0)
        self.assertEqual(T.value("a", 1.5), 10.0)                    # held pose holds
        self.assertTrue(all(0.0 <= T.value("a", t / 10) <= 10.0 for t in range(31)))

    def test_paw_cycle_stance_moves_back_linearly(self):
        sweep, duty = 20.0, 0.6
        f0, z0, _, _ = M.paw_cycle(0.0, 0.0, duty, sweep, 3.0)
        f1, z1, _, _ = M.paw_cycle(0.3, 0.0, duty, sweep, 3.0)
        self.assertAlmostEqual(f0, 10.0); self.assertAlmostEqual(f1, 0.0); self.assertEqual((z0, z1), (0.0, 0.0))
        f2, z2, _, sw = M.paw_cycle(0.8, 0.0, duty, sweep, 3.0)
        self.assertIsNotNone(sw); self.assertAlmostEqual(z2, 3.0)  # middle of the swing: highest
        self.assertAlmostEqual(M.paw_cycle(1.0, 0.0, duty, sweep, 3.0)[0], f0)

    def test_harm_closes(self):
        for n in (1, 2, 3):
            self.assertAlmostEqual(M.harm(0.0, 2.0, n, 0.3), M.harm(1.0, 2.0, n, 0.3))
