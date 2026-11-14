import math, os, sys, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts"))
from velvetpaws import brain as B, names


class BrainTest(unittest.TestCase):
    def test_sections_from_cat_seqs(self):
        self.assertEqual(B.section("Sit", "loop"), "Loop"); self.assertEqual(B.section("Sit", "exit"), "Exit")
        self.assertEqual(B.section("JumpDown", "exit"), "Exit")
        with self.assertRaises(KeyError): B.section("Groom", "loop")   # one-section montage

    def test_transitions_chain_and_times(self):
        for (p, q), (ops, t, after) in B.TRANSITIONS.items():
            self.assertEqual(abs(p - q), 1); self.assertGreater(t, 0.2)
            self.assertIn(after, B.AFTER_OPS)
        self.assertEqual(B.TRANSITIONS[(B.P_LIE, B.P_SIT)][2], B.AFTER_SIT_LOOP)
        self.assertAlmostEqual(B.TRANSITIONS[(B.P_STAND, B.P_SIT)][1], B.CS.length("SitEnter"))

    def test_spot_visits_happen_in_a_session(self):
        # a cat lying on the office floor, Jodi idle, a routine pick every 6-14 s: in 20 min she tries a spot in most sessions
        # (with ACT_SPOT only from stand: 0.81 of the sessions had none)
        import random
        def first_attempt(seed):
            rnd = random.Random(seed); p, rest_since, t = B.P_LIE, 0.0, B.ROUTINE_MIN
            while t < 1200.0:
                a = B.pick_routine(p, rnd.uniform(0, 100), t - rest_since, True, False)
                if a == B.ACT_SPOT: return t
                if a in B.ACT_POSTURE: p = B.ACT_POSTURE[a]
                t += rnd.uniform(B.ROUTINE_MIN, B.ROUTINE_MAX)
            return None
        res = [first_attempt(s) for s in range(1000)]
        self.assertLess(sum(1 for r in res if r is None) / len(res), 0.2)

    def test_speed_capped_at_run_sample(self):
        self.assertEqual(B.RUN_ANIM, 300.0)
        self.assertEqual(B.follow_speed(250.0, 0.0), 0.0)
        self.assertAlmostEqual(B.follow_speed(B.FOLLOW_RUN_AT * 3, 900.0), B.MAX_SPEED)
        self.assertGreater(B.follow_speed(500.0, 250.0), 250.0)        # keeps up with Jodi walking
        self.assertAlmostEqual(B.anim_speed(300.0, 1.15), 300.0 / 1.15)
        self.assertAlmostEqual(B.anim_speed(400.0, 0.85), 300.0)
        self.assertAlmostEqual(B.max_speed(0.85), 255.0)

    def test_jump_velocity_lands_on_target(self):
        frm, to, g = (0.0, 0.0, 16.0), (80.0, 30.0, 166.0), 980.0
        vx, vy, vz = B.jump_velocity(frm, to, B.JUMP_CLEAR_UP, g)
        t_up = vz / g; apex = frm[2] + vz * t_up - 0.5 * g * t_up ** 2
        self.assertAlmostEqual(apex, to[2] + B.JUMP_CLEAR_UP, places=3)
        T = t_up + math.sqrt(2 * (apex - to[2]) / g)
        self.assertAlmostEqual(frm[0] + vx * T, to[0], places=3); self.assertAlmostEqual(frm[1] + vy * T, to[1], places=3)
        vx, vy, vz = B.jump_velocity(to, frm, B.JUMP_CLEAR_DOWN, g)     # down: apex = start + clear
        self.assertAlmostEqual(vz, math.sqrt(2 * g * B.JUMP_CLEAR_DOWN))

    def test_posture_next(self):
        self.assertEqual(B.posture_next(B.P_SLEEP, B.P_STAND), B.P_LIE)
        self.assertEqual(B.posture_next(B.P_STAND, B.P_LIE), B.P_SIT)
        self.assertEqual(B.posture_next(B.P_SIT, B.P_SIT), B.P_SIT)

    def test_routine(self):
        self.assertEqual(B.pick_routine(B.P_STAND, 10.0, 0.0, False, False), B.ACT_SIT)
        self.assertEqual(B.pick_routine(B.P_STAND, 70.0, 0.0, False, False), B.ACT_NONE)    # spot not available
        self.assertEqual(B.pick_routine(B.P_STAND, 70.0, 0.0, True, False), B.ACT_SPOT)
        self.assertEqual(B.pick_routine(B.P_SIT, 50.0, 2.0, False, False), B.ACT_NONE)      # lie needs 8 s rest
        self.assertEqual(B.pick_routine(B.P_SIT, 50.0, 9.0, False, False), B.ACT_LIE)
        self.assertEqual(B.pick_routine(B.P_SLEEP, 99.0, 99.0, True, True), B.ACT_NONE)
        # spot visits also from sit (70-80) and lie (35-40), never while on a spot or without a spot
        self.assertEqual(B.pick_routine(B.P_SIT, 72.0, 0.0, True, False), B.ACT_SPOT)
        self.assertEqual(B.pick_routine(B.P_SIT, 72.0, 0.0, True, True), B.ACT_NONE)
        self.assertEqual(B.pick_routine(B.P_SIT, 72.0, 0.0, False, False), B.ACT_NONE)
        self.assertEqual(B.pick_routine(B.P_SIT, 80.0, 0.0, True, False), B.ACT_NONE)
        self.assertEqual(B.pick_routine(B.P_LIE, 37.0, 0.0, True, False), B.ACT_SPOT)
        self.assertEqual(B.pick_routine(B.P_LIE, 40.0, 0.0, True, False), B.ACT_NONE)
        self.assertEqual(B.pick_routine(B.P_SLEEP, 5.0, 99.0, True, False), B.ACT_LIE)       # never straight from sleep
        kc = [c for c in B.kit_cases() if c[0] == "VP_PickRoutine"]
        for p in (B.P_SIT, B.P_LIE): self.assertTrue(any(a[0] == p and e == B.ACT_SPOT for _, a, e in kc), p)
        for p in B.ROUTINE: self.assertLessEqual(sum(w for _, w in B.ROUTINE[p]), 100)

    def test_teleport_and_view(self):
        c = B.teleport_candidate(0, (0.0, 0.0, 0.0), 0.0)                  # camera looks +X: candidate behind it, at -X
        self.assertAlmostEqual(c[0], -B.TELEPORT_DIST); self.assertAlmostEqual(c[1], 0.0, places=6)
        self.assertTrue(B.out_of_view(c, (-200.0, 0.0, 0.0), (1.0, 0.0, 0.0)))   # behind the camera
        self.assertFalse(B.out_of_view((300.0, 0.0, 0.0), (-200.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        self.assertEqual(len(B.TELEPORT_ANGLES), 7)

    def test_flee_and_follow_points(self):
        f = B.flee_goal((0.0, 0.0, 5.0), (300.0, 0.0, 0.0))
        self.assertEqual(f, (-B.FLEE_BEHIND, 0.0, 5.0))
        self.assertEqual(B.flee_goal((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))[0], B.FLEE_BEHIND)   # same place: fallback +X
        p = B.follow_point((0.0, 0.0, 90.0), (0.0, 1000.0, 16.0))
        self.assertEqual(p, (0.0, B.FOLLOW_KEEP, 16.0))

    def test_level_kind(self):
        self.assertEqual(B.level_kind("JodisOffice"), B.LV_OFFICE)
        self.assertEqual(B.level_kind("menu_sitting"), B.LV_NONE)
        self.assertEqual(B.level_kind(""), B.LV_NONE)
        self.assertEqual(B.level_kind("Level_3"), B.LV_MISSION)

    def test_hops_roundtrip(self):
        row = [0, 2, -1, 3, 399, 35, 36, 449, 1294]
        s = B.encode_hops(row)
        self.assertEqual([B.next_hop(s, i) for i in range(len(row))], row)
        self.assertTrue(s.isalnum() and s.isascii() and s == s.upper()); self.assertEqual(len(s), 2 * len(row))

    def test_settings_have_spec_fields(self):
        names_ = [s[0] for s in B.SETTINGS]
        for n in ("Active", "Mode", "TakeAlong", "Pattern", "BaseColor", "SecondColor", "EyeColor", "Size", "Meow", "MeowRate",
                  "Purr", "Volume", "CatName", "RecallKey"):
            self.assertIn(n, names_)
        self.assertEqual(dict((s[0], s[2]) for s in B.SETTINGS)["Mode"], str(B.MODE_FOLLOW))

    def test_kit_cases_match_reference(self):
        cases = B.kit_cases()
        self.assertGreater(len(cases), 150)
        for fn, args, want in cases:
            self.assertIn(fn, B.BP_FUNCS)
            self.assertEqual(len(args), len(B.BP_FUNCS[fn][1]), fn)

    def test_meow_interval(self):
        self.assertAlmostEqual(B.meow_interval(0.0, 0.5), B.MEOW_SLOW)
        self.assertAlmostEqual(B.meow_interval(1.0, 0.5), B.MEOW_FAST)
        self.assertAlmostEqual(B.meow_interval(0.5, 0.5), (B.MEOW_SLOW * B.MEOW_FAST) ** 0.5, places=6)   # about 69 s
        self.assertAlmostEqual(B.meow_interval(2.0, 0.5), B.MEOW_FAST)                                   # clamped
        self.assertAlmostEqual(B.meow_interval(0.5, 0.0) * 3, B.meow_interval(0.5, 1.0))                 # x 0.5 ... 1.5

    def test_sound_pitch(self):
        self.assertAlmostEqual(B.sound_pitch(1.0, 0.5), 1.0)
        self.assertGreater(B.sound_pitch(0.85, 0.5), 1.0); self.assertLess(B.sound_pitch(1.15, 0.5), 1.0)
        self.assertAlmostEqual(B.sound_pitch(1.0, 1.0), 1.0 + B.PITCH_VAR)

    def test_next_variant_never_repeats(self):
        for n in (2, 3, 4):
            for last in range(n):
                got = {B.next_variant(last, r / 100.0, n) for r in range(100)}
                self.assertEqual(got, set(range(n)) - {last})
        self.assertEqual({B.next_variant(-1, r / 100.0, 4) for r in range(100)}, {0, 1, 2, 3})
        self.assertEqual(B.next_variant(0, 0.7, 1), 0)

    def test_purr_want_hysteresis(self):
        self.assertTrue(B.purr_want(B.ST_REST, B.P_LIE, False, 250.0, False))
        self.assertFalse(B.purr_want(B.ST_REST, B.P_LIE, False, 320.0, False))   # not started above 3 m
        self.assertTrue(B.purr_want(B.ST_SPOT, B.P_SLEEP, False, 320.0, True))   # kept up to 3.5 m
        self.assertFalse(B.purr_want(B.ST_REST, B.P_STAND, False, 100.0, False))
        self.assertFalse(B.purr_want(B.ST_MOVE, B.P_SIT, False, 100.0, False))
        self.assertFalse(B.purr_want(B.ST_REST, B.P_SIT, True, 100.0, False))

    def test_cues_from_the_jaw(self):
        f = lambda s: B.CS.SEQS[s].length / B.CS.SEQS[s].frames
        self.assertTrue(0.6 < B.CUE_AT[B.CUE_HISS] < 1.0, B.CUE_AT[B.CUE_HISS])      # cat_anim_action: jaw opens from f24
        self.assertTrue(0.1 < B.CUE_AT[B.CUE_YAWN] < 0.4, B.CUE_AT[B.CUE_YAWN])      # from f6
        self.assertAlmostEqual(B.CUE_AT[B.CUE_HISS] / f("Hiss"), round(B.CUE_AT[B.CUE_HISS] / f("Hiss")))   # on a frame
        self.assertEqual(B.CUE_AT[B.CUE_LAND], 0.0)
        self.assertEqual(set(B.CUE_AT), {B.CUE_HISS, B.CUE_YAWN, B.CUE_LAND, B.CUE_CALLED, B.CUE_ARRIVED, B.CUE_GREET})
        self.assertEqual(B.ACT_CUE, {B.ACT_YAWN: B.CUE_YAWN})

    def test_sound_hooks_and_test_key(self):
        for h in ("Sound Tick", "Cue"): self.assertIn(h, B.HOOKS)
        self.assertEqual(B.TEST_KEYS["Meow"], "F6")
        self.assertNotIn("F7", B.TEST_KEYS.values())       # AridExile's climb diagnostic

    def test_patterns(self):
        self.assertEqual(B.PATTERNS[1], (names.DEF_PATTERN, names.DEF_WHITE))     # tabby = the stage 1 instance defaults
        self.assertEqual(len(B.PATTERNS), 6)
        self.assertEqual(B.pattern_weights(4), (0.0, 0.0, 0.0, 1.0)); self.assertEqual(B.white_marks(4), 1.0)   # calico
        self.assertEqual(B.white_marks(5), 1.0); self.assertEqual(B.pattern_weights(5), (0.0, 0.0, 0.0, 0.0))   # markings
        self.assertEqual(B.pattern_weights(99), B.pattern_weights(0))

    def test_want_here(self):
        self.assertTrue(B.want_here(True, B.LV_OFFICE, False))
        self.assertTrue(B.want_here(True, B.LV_MISSION, True)); self.assertFalse(B.want_here(True, B.LV_MISSION, False))
        self.assertFalse(B.want_here(False, B.LV_OFFICE, True)); self.assertFalse(B.want_here(True, B.LV_NONE, True))


    # ---- round 6 ----
    def test_kitten_scale_and_spot_fit(self):
        self.assertEqual(B.SIZE_MIN, 40.0)
        self.assertEqual(B.jump_reach(1.0), B.JUMP_MAX); self.assertEqual(B.jump_reach(B.KITTEN_FULL), B.JUMP_MAX)
        self.assertAlmostEqual(B.jump_reach(0.4), B.JUMP_MAX * 0.4 / 0.85)                     # 70.6 cm: sofas, beds, the desk
        self.assertTrue(B.spot_fits(70.2, B.OPEN_ROOM, 0.4)); self.assertFalse(B.spot_fits(87.0, B.OPEN_ROOM, 0.4))
        self.assertTrue(B.spot_fits(134.1, B.OPEN_ROOM, 0.85))                                  # what an 85 % cat reached before
        for sc in (0.4, 1.0, 1.15): self.assertTrue(B.spot_fits(3.2, 44.3, sc))                # the office compartments fit every size
        self.assertFalse(B.spot_fits(100.0, 47.5, 0.4)); self.assertTrue(B.spot_fits(100.0, 47.5, 1.15))
        self.assertFalse(B.spot_fits(50.0, 36.0, 1.15)); self.assertTrue(B.spot_fits(50.0, 36.0, 1.0))

    def test_jump_clear_under_a_board(self):
        self.assertEqual(B.jump_clear(B.OPEN_ROOM, 1.0), B.JUMP_CLEAR_UP)
        self.assertAlmostEqual(B.jump_clear(47.5, 1.0), 47.5 - 32.0 - B.ROOM_MARGIN)
        self.assertEqual(B.jump_clear(20.0, 1.15), B.JUMP_CLEAR_MIN)
        for sc in (0.4, 1.0, 1.15):                                             # apex: capsule top stays under the board
            self.assertLessEqual(B.jump_clear(47.5, sc) + 2 * B.CAPSULE_HH * sc, 47.5 - B.ROOM_MARGIN + 1e-6)

    def test_stay_time(self):
        self.assertEqual(B.stay_time(2.0, 10.0, 0.0), 120.0); self.assertEqual(B.stay_time(2.0, 10.0, 1.0), 600.0)
        self.assertEqual(B.stay_time(10.0, 2.0, 0.5), B.stay_time(2.0, 10.0, 0.5))
        self.assertTrue(B.STAY_RANGE[0] <= B.STAY_DEFAULT[0] <= B.STAY_DEFAULT[1] <= B.STAY_RANGE[1])
        self.assertIn(("StayMin", "float", "2.0"), B.SETTINGS); self.assertIn(("StayMax", "float", "10.0"), B.SETTINGS)

    def test_rub_loop_round_the_legs(self):
        j = (100.0, 50.0, 92.0)
        for yaw in (0.0, 90.0, 200.0):
            f = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0)
            for k in range(64):
                t = 2 * math.pi * k / 64; p = B.rub_point(j, f, t); q = B.rub_point(j, f, t + 0.01)
                d = math.hypot(p[0] - j[0], p[1] - j[1]); self.assertTrue(B.RUB_B - 1e-6 <= d <= B.RUB_A + 1e-6); self.assertEqual(p[2], j[2])
                vx, vy = q[0] - p[0], q[1] - p[1]; left = (vy, -vx)                 # Unreal: left = moving direction turned -90 degrees
                self.assertGreater((j[0] - p[0]) * left[0] + (j[1] - p[1]) * left[1], 0.0)   # Jodi always on the cat's left
                self.assertAlmostEqual(math.cos(B.rub_phase(j, f, p)), math.cos(t), places=6); self.assertAlmostEqual(math.sin(B.rub_phase(j, f, p)), math.sin(t), places=6)
        self.assertEqual(B.rub_point(j, (0.0, 0.0, 1.0), 0.0)[:2], (j[0], j[1] + B.RUB_A))   # no forward: +x assumed, right = +y
        self.assertTrue(6.0 < B.RUB_PERIOD < 12.0)

    def test_rub_want(self):
        ok = dict(dist=300.0, jodi_speed=0.0, still_for=3.0, since_rub=100.0, posture=B.P_SIT, r=10.0)
        self.assertTrue(B.rub_want(**ok))
        for k, v in (("dist", 450.0), ("jodi_speed", 30.0), ("still_for", 1.0), ("since_rub", 20.0), ("posture", B.P_LIE), ("r", 50.0)):
            self.assertFalse(B.rub_want(**dict(ok, **{k: v})), k)

    def test_purr_and_pupils_while_rubbing(self):
        self.assertTrue(B.purr_want(B.ST_RUB, B.P_STAND, False, 30.0, False)); self.assertFalse(B.purr_want(B.ST_RUB, B.P_STAND, True, 30.0, False))
        self.assertFalse(B.purr_want(B.ST_MOVE, B.P_STAND, False, 30.0, False))
        self.assertEqual(B.pupil_open(B.ST_RUB, B.P_STAND), B.PUPIL_WIDE); self.assertEqual(B.pupil_open(B.ST_REST, B.P_SLEEP), B.PUPIL_WIDE)
        self.assertEqual(B.pupil_open(B.ST_MOVE, B.P_STAND), B.PUPIL_CALM)
