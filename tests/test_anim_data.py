import math, os, sys, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "tools", "blender"))
import cat_motion as M
import cat_poses as P
import cat_seqs as S


def close(a, b, eps=1e-6):
    return all(abs(a[k] - b[k]) <= eps for k in M.CHANNELS if k != "tl_ph")


class AnimDataTest(unittest.TestCase):
    def test_names_unique_and_ordered(self):
        self.assertEqual(len(S.ORDER), len(set(S.ORDER))); self.assertEqual(list(S.SEQS), S.ORDER)

    def test_frames_and_limits(self):
        for name, s in S.SEQS.items():
            self.assertGreater(s.frames, 0, name)
            for f in range(s.frames + 1):
                self.assertEqual(M.check_pose(s.frame_pose(f)), [], "%s frame %d" % (name, f))

    def test_loops_close(self):
        for name, s in S.SEQS.items():
            if s.loop: self.assertTrue(close(s.frame_pose(0), s.frame_pose(s.frames)), name)

    def test_postures_connect(self):
        for name, s in S.SEQS.items():
            if s.start: self.assertTrue(close(s.pose(0.0), P.POSES[s.start]), "%s start %s" % (name, s.start))
            if s.end: self.assertTrue(close(s.pose(s.length), P.POSES[s.end]), "%s end %s" % (name, s.end))

    def test_stand(self):
        s = S.SEQS["Stand"]; self.assertTrue(s.loop); self.assertEqual(s.frames, 120); self.assertEqual(s.start, "stand")


class GaitTest(unittest.TestCase):
    def order(self, s):
        return sorted(M.LEGS, key=lambda l: s.touchdown[l])

    def test_walk_lateral_sequence(self):
        w = S.SEQS["Walk"]; self.assertEqual(self.order(w), ["hl", "fl", "hr", "fr"]); self.assertGreater(w.duty, 0.5)

    def test_trot_diagonal_pairs(self):
        t = S.SEQS["Trot"]
        self.assertLess(abs(t.touchdown["hl"] - t.touchdown["fr"]), 0.05); self.assertLess(abs(t.touchdown["hr"] - t.touchdown["fl"]), 0.05)
        self.assertAlmostEqual((t.touchdown["hr"] - t.touchdown["hl"]) % 1.0, 0.5, delta=0.05); self.assertLess(t.duty, 0.5)

    def test_run_rotary_gallop_with_suspension(self):
        r = S.SEQS["Run"]; self.assertEqual(self.order(r), ["hl", "hr", "fr", "fl"])
        ground = [any(((p - r.touchdown[l]) % 1.0) < r.duty for l in M.LEGS) for p in (i / 100 for i in range(100))]
        self.assertFalse(all(ground))                                          # a flight phase exists

    def test_speeds_ascend_on_grid_and_cycles_start_at_hl(self):
        sp = [S.SEQS[n].speed for n in ("Stand", "Walk", "Trot", "Run")]
        self.assertEqual(sp, sorted(sp)); self.assertLessEqual(sp[-1], S.SPEED_MAX)
        step = S.SPEED_MAX / S.SPEED_GRID
        for v in sp: self.assertAlmostEqual(v / step, round(v / step))
        for n in ("Walk", "Trot", "Run"): self.assertEqual(S.SEQS[n].touchdown["hl"], 0.0)

    def test_stance_moves_back_at_speed(self):
        for n in ("Walk", "Trot", "Run"):
            s = S.SEQS[n]; a, b = s.plants["hl"][0]; t0, t1 = a + 0.01, min(b, s.length) - 0.01
            v = (s.pose(t0)["hl_f"] - s.pose(t1)["hl_f"]) / (t1 - t0)
            self.assertAlmostEqual(v, s.speed, delta=0.5, msg=n)

    def test_hl_planted_at_loop_end_and_swing_clear_of_floor(self):
        for n in ("Walk", "Trot", "Run"):
            s = S.SEQS[n]; self.assertIn((s.length, s.length), s.plants["hl"], n)
            for f in range(s.frames + 1):
                P = s.frame_pose(f); t = f / M.FPS
                for l in M.LEGS:
                    if not any(a - 1e-6 <= t <= b + 1e-6 for a, b in s.plants[l]): self.assertGreater(P[l + "_z"], 0.5, "%s f%d %s" % (n, f, l))


class PostureTest(unittest.TestCase):
    CHAIN = [("SitEnter", "stand", "sit"), ("SitLoop", "sit", "sit"), ("SitExit", "sit", "stand"),
             ("LieEnter", "sit", "lie"), ("LieLoop", "lie", "lie"), ("LieExit", "lie", "sit"),
             ("SleepEnter", "lie", "sleep"), ("SleepLoop", "sleep", "sleep"), ("SleepExit", "sleep", "lie")]

    def test_tags(self):
        for n, a, b in self.CHAIN:
            self.assertEqual((S.SEQS[n].start, S.SEQS[n].end), (a, b), n)

    def test_loops(self):
        for n in ("SitLoop", "LieLoop", "SleepLoop"): self.assertTrue(S.SEQS[n].loop, n)

    def test_montages(self):
        names = {m["name"]: m for m in S.MONTAGES}
        for m in ("Sit", "Lie", "Sleep"):
            secs = S.section_times(names[m])
            self.assertEqual([s[0] for s in secs], ["Enter", "Loop", "Exit"]); self.assertEqual(secs[1][2], "Loop")


class JumpTest(unittest.TestCase):
    def test_jump_chain(self):
        for n, a, b in (("JumpTakeoff", "stand", "air"), ("JumpAir", "air", "air"), ("JumpLand", "air", "stand"),
                        ("JumpDownStart", "stand", "air_down"), ("JumpAirDown", "air_down", "air_down"), ("JumpDownLand", "air_down", "stand")):
            self.assertEqual((S.SEQS[n].start, S.SEQS[n].end), (a, b), n)
        for n in ("JumpAir", "JumpAirDown"): self.assertTrue(S.SEQS[n].loop, n)
        self.assertEqual(S.length("JumpAirDown"), S.length("JumpAir"))

    def test_launch_is_lift_off(self):
        """launch_time = the frame the hind paws leave the floor, LIFT_OFF frames before the end of the Enter section."""
        import cat_anim_jump as J
        for mont, enter in (("Jump", "JumpTakeoff"), ("JumpDown", "JumpDownStart")):
            s = S.SEQS[enter]; t = S.launch_time(mont)
            self.assertAlmostEqual(t, s.length - J.LIFT_OFF / M.FPS, msg=mont)
            for leg in ("hl", "hr"): self.assertAlmostEqual(max(b for _, b in s.plants[leg]), t, msg=mont)
            for f in range(round(t * M.FPS) + 1, s.frames + 1):
                for leg in M.LEGS: self.assertGreater(s.frame_pose(f)[leg + "_z"], 0.5, "%s f%d %s" % (enter, f, leg))

    def test_no_pop_into_flight(self):
        for n in ("JumpTakeoff", "JumpDownStart"):
            (cm, ch1, f1), (deg, ch2, f2) = M.end_jumps(S.SEQS[n])
            self.assertLessEqual(cm, M.END_MAX_CM, "%s %s f%d" % (n, ch1, f1)); self.assertLessEqual(deg, M.END_MAX_DEG, "%s %s f%d" % (n, ch2, f2))

    def test_gate_catches_one_frame_pop(self):
        pop = M.Seq("Pop", 6, lambda t: P.STAND if t < 5.5 / M.FPS else P.AIR)
        (cm, _, _), (deg, _, _) = M.end_jumps(pop)
        self.assertTrue(cm > M.END_MAX_CM or deg > M.END_MAX_DEG)

    def test_jump_down_looks_down(self):
        """The head is pitched further nose down than in AIR through the end of DownStart and in the AirDown loop."""
        def head_pitch(p): return p["pel_p"] + p["sp1_p"] + p["sp2_p"] + p["sp3_p"] - p["nk1_p"] - p["nk2_p"] + p["hd_p"]
        d = S.SEQS["JumpDownStart"]
        for f in range(9, d.frames + 1): self.assertGreater(head_pitch(d.frame_pose(f)), head_pitch(P.AIR) + 15, "f%d" % f)
        self.assertGreater(head_pitch(P.AIR_DOWN), 20.0)

    def test_montage_sections_connect(self):
        """Each section ends where the next starts (Loop: where it starts itself), so a montage never pops at a seam."""
        for m in S.MONTAGES:
            secs = {name: s for name, s, _ in m["sections"]}
            for name, s, nxt in m["sections"]:
                if nxt: self.assertTrue(close(S.SEQS[s].pose(S.length(s)), S.SEQS[secs[nxt]].pose(0.0)), "%s %s -> %s" % (m["name"], name, nxt))
            for (a, sa, _), (b, sb, _) in zip(m["sections"], m["sections"][1:]):
                self.assertTrue(close(S.SEQS[sa].pose(S.length(sa)), S.SEQS[sb].pose(0.0)), "%s %s -> %s" % (m["name"], a, b))


class ActionTest(unittest.TestCase):
    def test_actions(self):
        for n, tag in (("Groom", "sit"), ("Stretch", "stand"), ("Yawn", "sit"), ("Hiss", "stand")):
            s = S.SEQS[n]; self.assertEqual((s.start, s.end), (tag, tag), n); self.assertFalse(s.loop, n)
        yawn = max(S.SEQS["Yawn"].pose(t / 30)["jaw"] for t in range(61)); hiss = max(S.SEQS["Hiss"].pose(t / 30)["jaw"] for t in range(76))
        self.assertTrue(26.0 <= yawn <= 28.0, yawn); self.assertTrue(20.0 <= hiss <= 28.0, hiss)     # the open mouth reads up to 28 deg
        self.assertGreater(max(S.SEQS["Groom"].pose(t / 10)["fr_z"] for t in range(51)), 8.0)

    def test_unplanted_paws_clear_of_floor(self):
        for n in ("Groom", "Stretch", "Yawn", "Hiss"):
            s = S.SEQS[n]
            for f in range(s.frames + 1):
                P = s.frame_pose(f); t = f / M.FPS
                for l in M.LEGS:
                    if not any(a - 1e-6 <= t <= b + 1e-6 for a, b in s.plants[l]): self.assertGreater(P[l + "_z"], 0.5, "%s f%d %s" % (n, f, l))


class OverlayTest(unittest.TestCase):
    def test_overlay_only_tail_and_ears(self):
        s = S.SEQS["Overlay"]; self.assertTrue(s.overlay and s.loop)
        z = M.zero_pose()
        for f in range(0, s.frames + 1, 5):
            p = s.frame_pose(f)
            for k, v in p.items():
                if not k.startswith(("tl_", "ear")): self.assertEqual(v, z[k], k)
        self.assertEqual(S.ORDER[-1], "Overlay")



class HeadFkTest(unittest.TestCase):
    """cat_poses' plain-Python FK (_frame: pelvis, spine, neck, head) against cat_animlib.CatRig.solve: points that ride with the
    head, spine_03 (fore legs) and the pelvis (hind legs) in two synthetic poses (every trunk, neck and head channel non-zero),
    solved once in Blender on cat.blend (anim space cm). Fails when either side's FK changes alone."""
    POSES = [dict(pel_x=1.2, pel_f=-0.8, pel_z=-2.0, pel_y=12.0, pel_p=-9.0, pel_r=7.0, sp1_p=5.0, sp2_p=-6.0, sp3_p=8.0, sp1_y=4.0,
                  sp2_y=-3.0, sp3_y=6.0, sp_r=10.0, nk1_p=14.0, nk2_p=-5.0, nk_y=20.0, hd_p=22.0, hd_y=-15.0, hd_r=9.0),
             dict(pel_x=-0.5, pel_f=2.5, pel_z=-9.0, pel_y=-25.0, pel_p=30.0, pel_r=-60.0, sp1_p=-12.0, sp2_p=15.0, sp3_p=-4.0, sp1_y=-9.0,
                  sp2_y=7.0, sp3_y=-2.0, sp_r=-18.0, nk1_p=-20.0, nk2_p=12.0, nk_y=-35.0, hd_p=-30.0, hd_y=40.0, hd_r=-25.0)]
    SOLVED = [
        (0, "head", (0.0, 29.6, 23.8), (14.6157, 23.5897, 22.275)),
        (0, "head", (-2.6, 24.0, 27.7), (12.8083, 19.5416, 28.0781)),
        (0, "fl", (4.5, 15.5, 0.0), (6.8721, 13.9972, -0.1584)),
        (0, "hr", (-5.0, -6.5, 0.0), (-4.1843, -3.5899, -0.3696)),
        (1, "head", (0.0, 29.6, 23.8), (-26.3269, 18.3201, -12.361)),
        (1, "head", (-2.6, 24.0, 27.7), (-24.2766, 11.3403, -12.9997)),
        (1, "fl", (4.5, 15.5, 0.0), (3.3761, 19.1959, -5.9046)),
        (1, "hr", (-5.0, -6.5, 0.0), (11.1961, -5.6863, -5.6447)),
    ]

    def test_agrees_with_solver(self):
        for i, leg, local, want in self.SOLVED:
            got = P.body_point(dict(P.STAND, **self.POSES[i]), leg, local)
            self.assertLess(max(abs(a - b) for a, b in zip(got, want)), 1e-3, "pose %d %s %s" % (i, leg, local))

    def test_round_trip(self):
        for i, leg, local, _ in self.SOLVED:
            p = dict(P.STAND, **self.POSES[i]); back = P.body_local(p, leg, P.body_point(p, leg, local))
            self.assertLess(max(abs(a - b) for a, b in zip(back, local)), 1e-9, "pose %d %s" % (i, leg))


class SocialTest(unittest.TestCase):
    """Rubbing round Jodi's legs (round 6): RubWalk loops (a slow lateral walk, curved and leaning in to her left, tail up and hooked),
    HeadRub is a one-shot from the stand with all paws planted (head pushed sideways to her left, twice)."""

    def test_rub_walk(self):
        s = S.SEQS["RubWalk"]; self.assertTrue(s.loop); self.assertEqual(s.group, "social")
        self.assertEqual(sorted(M.LEGS, key=lambda l: s.touchdown[l]), ["hl", "fl", "hr", "fr"]); self.assertEqual(s.touchdown["hl"], 0.0)
        self.assertLess(s.speed, S.SEQS["Walk"].speed); self.assertEqual(S.RUB_SPEED, s.speed)
        a, b = s.plants["hl"][0]; t0, t1 = a + 0.01, b - 0.01
        self.assertAlmostEqual((s.pose(t0)["hl_f"] - s.pose(t1)["hl_f"]) / (t1 - t0), s.speed, delta=0.5)
        for f in range(s.frames + 1):
            p = s.frame_pose(f); t = f / M.FPS
            self.assertGreater(p["pel_r"], 0.0, "f%d leans in (left side down)" % f)
            self.assertGreater(p["sp1_y"] + p["sp2_y"] + p["sp3_y"] + p["nk_y"], 20.0, "f%d curved to the left" % f)
            self.assertGreater(p["tl_lift"], 80.0); self.assertGreater(p["tl_curl"], 30.0)
            for l in M.LEGS:
                if not any(x - 1e-6 <= t <= y + 1e-6 for x, y in s.plants[l]): self.assertGreater(p[l + "_z"], 0.5, "f%d %s" % (f, l))

    def test_head_rub(self):
        s = S.SEQS["HeadRub"]; self.assertFalse(s.loop); self.assertEqual((s.start, s.end), ("stand", "stand"))
        for l in M.LEGS: self.assertEqual(s.plants[l], [(0.0, s.length)])
        turn = [s.frame_pose(f)["nk_y"] + s.frame_pose(f)["hd_y"] for f in range(s.frames + 1)]
        self.assertGreater(max(turn), 40.0)
        pushes = [f for f in range(1, s.frames) if turn[f] > 40 and turn[f] >= turn[f - 1] and turn[f] >= turn[f + 1]]
        self.assertEqual(len(pushes), 2, pushes)
        self.assertGreater(max(s.frame_pose(f)["hd_r"] for f in range(s.frames + 1)), 15.0)    # left ear down into the leg

    def test_montages(self):
        ms = {m["name"]: m for m in S.MONTAGES}
        self.assertEqual(S.section_times(ms["RubWalk"]), [("Loop", 0.0, "Loop")])
        self.assertEqual(S.section_times(ms["HeadRub"]), [("Default", 0.0, None)])

    def test_smooth(self):
        for n in ("RubWalk", "HeadRub"):
            (dg, c1, f1), (cm, c2, f2) = M.body_accel(S.SEQS[n])
            self.assertLessEqual(dg, M.SMOOTH_MAX_DEG, "%s %s f%d" % (n, c1, f1)); self.assertLessEqual(cm, M.SMOOTH_MAX_CM, "%s %s f%d" % (n, c2, f2))

    def test_smooth_gate_catches_a_jerk(self):
        jerk = M.Seq("Jerk", 10, lambda t: dict(P.STAND, hd_y=20.0 if t > 5 / M.FPS else 0.0))
        self.assertGreater(M.body_accel(jerk)[0][0], M.SMOOTH_MAX_DEG)
