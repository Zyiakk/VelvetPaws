"""One-shot actions of the cat (Task 6), each from the posture it belongs to and back into it, so a montage plays it from there:
Groom (sit: licks the right fore paw, wipes it over the right ear and cheek), Stretch (stand: fore paws forward, chest down, rump up,
then the weight forward and the right hind leg stretched back), Yawn (sit: head up, ears back, jaw wide) and Hiss (stand: arched back,
tail up and bristling, ears flat, jaw open, head thrust forward).

The grooming paw is authored in the frame of the head (cat_poses.head_point): while it licks or wipes, its tip is a point of the head
(near the mouth, over the ear, over the cheek), so the head can nod and turn into the paw and the paw stays on the face. measure()
checks it through Seq.touch (the paw tip near the mouth while licking, over cheek and ear while wiping, never inside the head).

Times are frames / 30 (F); plant spans lie on frames."""
import math

import cat_motion as M
import cat_poses as P


F, _paw, _chan = M.F, M.paw_keys, M.chan


def _step(m, leg, a, b, to, lift):
    """The paw (planted until frame a) steps to `to` (its _x/_f/_z/... channels), landing at frame b: z keyed per frame on the step
    arc (cat_motion.step_arc), so it leaves the floor at once."""
    m.add(F(a), **{leg + c: m.value(leg + c, F(a)) for c in ("_x", "_f", "_z")}).add(F(b), **to)
    M.key_step_arc(m, leg, a, b, lift)


def _add(a, b): return tuple(a[i] + b[i] for i in range(3))


NECK = ("nk1_p", "nk2_p", "nk_y", "hd_p", "hd_y", "hd_r")
EARS = ("earl_p", "earl_y", "earr_p", "earr_y")
SPINE = ("sp1_p", "sp2_p", "sp3_p", "sp_r")


class Action(M.Seq):
    """A one-shot. touch: head-contact checks for measure(): {"clear": cm (both fore paw tips stay this far from P.HEAD_C),
    "near": [(leg, point, t0, t1, "max" | "min", cm)]}: over [t0, t1] the tip's largest ("max") or smallest ("min") distance to the
    head point (P.MOUTH, P.CHEEK_R, P.EAR_R) is at most cm."""

    def __init__(self, name, frames, pose_fn, posture, plants, touch=None):
        super().__init__(name, frames, pose_fn, start=posture, end=posture, plants=plants, group="action")
        self.touch = touch


# ------------------------------------------------------------------------------------------------------------------------ groom
# lick: neck lowered, head bowed and turned a little to the raised right paw; the paw curled (wrist 60) under the chin
LICK = dict(nk1_p=-18.0, nk2_p=-8.0, hd_p=51.0, hd_y=-15.0, hd_r=0.0, sp_r=3.0, pel_x=0.5)
LICK_AT = _add(P.MOUTH, (0.0, 0.6, -1.4))         # paw tip just in front of and below the lips (head frame)
# wipe: neck low, head bowed and turned to the paw with the right ear down into it; the right ear flat
WIPE = dict(nk1_p=-30.0, nk2_p=-14.0, hd_p=57.0, hd_y=-25.0, hd_r=-22.0, sp_r=-1.0, sp3_p=-4.0, pel_x=0.5)
# one stroke of the paw tip over the right side of the head (head frame, from P.EAR_R / P.CHEEK_R): behind the ear, over it, over the
# brow, down the cheek to the whisker pad; then out and back up off the face for the next stroke
STROKE = [(0.0, _add(P.EAR_R, (-1.8, -0.4, 0.5)), 95.0), (0.25, _add(P.EAR_R, (-1.6, 0.9, 0.8)), 95.0),
          (0.45, _add(P.CHEEK_R, (-1.4, 0.4, 2.2)), 85.0), (0.65, _add(P.CHEEK_R, (-1.3, 2.0, 0.0)), 75.0),
          (0.78, _add(P.CHEEK_R, (-2.2, 3.0, -0.6)), 70.0)]
STROKE_T = 0.9                                  # s per stroke (the last 0.12 s: off the face, back up behind the ear)
LICK_T = F(16)                                  # one lick
LICKS = (F(16), F(32), F(48))                   # start of each lick: 0.53 .. 2.13 s
WIPES = (F(76), F(103))                         # start of each stroke: 2.53 .. 4.33 s


class _Groom:
    """sit -> sit (5 s). f0-18: the weight goes onto the left fore leg, the right fore paw lifts (f3) and rises to the chin while the
    head bows to meet it; f16-64: three licks (the head strokes up the paw: nod 8 deg, jaw 0-10, the paw turns in the wrist 40-70);
    f76-130: two wipes over the right ear and cheek (head turned and tipped into the paw, the right ear flat); f130-147 the paw goes
    back to the floor (planted from f147 = 4.9 s), the head comes up into the sit."""

    def __init__(self):
        S = P.SIT; m = M.Tracks(S); self.S = S
        m.add(F(2), _chan(S, *NECK, *SPINE, "pel_x")).add(F(14), LICK)
        m.add(F(64), LICK).add(F(74), WIPE).add(F(128), WIPE).add(F(142), _chan(S, *NECK, *SPINE, "pel_x"))
        m.add(F(70), _chan(S, *EARS)).add(F(78), earr_p=60.0, earr_y=10.0).add(F(128), earr_p=60.0, earr_y=10.0)
        m.add(F(138), _chan(S, *EARS))
        m.add(F(3), **_paw(S, "fr")).add(F(4), fr_z=1.0).add(F(6), fr_z=2.5, fr_f=S["fr_f"] + 0.5, fr_ank=30.0, fr_toe=15.0)
        m.add(F(10), fr_x=-2.5, fr_f=18.0, fr_z=10.0)
        m.add(F(130), fr_ank=70.0, fr_toe=30.0).add(F(138), fr_x=-3.5, fr_f=17.5, fr_z=7.0, fr_ank=45.0, fr_toe=20.0)
        m.add(F(143), fr_z=2.0, fr_f=S["fr_f"] + 0.5, fr_ank=10.0, fr_toe=5.0).add(F(146), fr_z=0.7).add(F(147), _paw(S, "fr")).add(F(150), S)
        self.T = m
        # the paw in the head frame: w = share of the head-frame path in the paw target, (lx, lf, lz) the point on the head
        h = M.Tracks(dict(w=0.0, lx=LICK_AT[0], lf=LICK_AT[1], lz=LICK_AT[2], ank=60.0))
        h.add(F(6), w=0.0).add(F(16), w=1.0).add(F(129), w=1.0).add(F(138), w=0.0)
        h.add(F(64), lx=LICK_AT[0], lf=LICK_AT[1], lz=LICK_AT[2], ank=60.0)
        side = _add(P.CHEEK_R, (-3.0, 1.5, -0.5))          # out at the side of the face between the licks and the wipes
        h.add(F(69), lx=side[0], lf=side[1], lz=side[2], ank=80.0)
        for t0 in WIPES:
            for u, p, a in STROKE: h.add(t0 + u, lx=p[0], lf=p[1], lz=p[2], ank=a)
        h.add(WIPES[-1] + STROKE_T, lx=side[0], lf=side[1], lz=side[2], ank=70.0)
        self.H = h

    def pose(self, t):
        p = self.T.pose(t); h = self.H.pose(t)
        lick = 0.0
        for t0 in LICKS:                               # each lick: the head dips 8 deg along the paw and comes back, jaw 0-10
            u = (t - t0) / LICK_T
            if 0.0 <= u <= 1.0: lick = math.sin(math.pi * u) ** 2
        w = h["w"]
        if w > 0.0:
            x, f, z = P.head_point(p, (h["lx"], h["lf"], h["lz"]))       # the paw rides on the head (before the lick's nod)
            for c, v in (("_x", x), ("_f", f), ("_z", z)): p["fr" + c] += (v - p["fr" + c]) * w
            p["fr_ank"] += (h["ank"] - p["fr_ank"]) * w
        p["hd_p"] += 8.0 * lick; p["jaw"] = 10.0 * lick
        if LICKS[0] <= t <= LICKS[-1] + LICK_T: p["fr_ank"] = 40.0 + 30.0 * (1.0 - lick)
        return p


_G = _Groom()
GROOM = Action("Groom", 150, _G.pose, "sit",
               plants={"hl": [(0.0, F(150))], "hr": [(0.0, F(150))], "fl": [(0.0, F(150))], "fr": [(0.0, F(3)), (F(147), F(150))]},
               touch={"clear": 3.5, "near": [("fr", "MOUTH", t0 + F(2), t0 + F(14), "max", 2.0) for t0 in LICKS]
                      + [("fr", pt, t0, t0 + STROKE_T, "min", 2.5) for t0 in WIPES for pt in ("EAR_R", "CHEEK_R")]})


# ---------------------------------------------------------------------------------------------------------------------- stretch
# BOW: the fore paws 10 cm ahead, the chest down between the elbows, the rump high (pelvis nose down 25), head up and forward
BOW = dict(pel_z=0.5, pel_f=0.5, pel_p=25.0, sp1_p=4.0, sp2_p=2.0, sp3_p=-6.0, nk1_p=24.0, nk2_p=8.0, hd_p=-14.0,
           fl_f=P.STAND["fl_f"] + 9.0, fr_f=P.STAND["fr_f"] + 9.0, fl_ank=-20.0, fr_ank=-20.0, fl_pole=10.0, fr_pole=10.0,
           earl_p=15.0, earr_p=15.0, tl_lift=45.0, tl_curl=25.0, hl_ank=10.0, hr_ank=10.0)
# REACH: weight forward over the fore paws, back level, the right hind leg stretched out behind (heel up, toes back)
REACH = dict(pel_z=-1.5, pel_f=3.0, pel_p=6.0, sp1_p=0.0, sp2_p=0.0, sp3_p=-3.0, nk1_p=12.0, nk2_p=4.0, hd_p=-4.0,
             hr_x=-4.5, hr_f=-18.0, hr_z=3.0, hr_ank=60.0, hr_toe=20.0, hl_ank=25.0, fl_ank=-10.0, fr_ank=-10.0,
             earl_p=5.0, earr_p=5.0, tl_lift=30.0, tl_curl=15.0)


def _stretch():
    """stand -> stand (3 s). f1-14: the fore paws walk forward 10 cm (left, then right) while the chest sinks and the rump stays high;
    f18-42: held, the jaw opens a little (f24-36); f42-66: the weight goes forward, the right hind leg lifts and stretches out behind
    (f44-56) and is held; f62-90: back: the right hind paw steps back (f62-70), the fore paws step back (f66-74, f70-78), stand."""
    S = P.STAND; m = M.Tracks(S)
    body = ("pel_z", "pel_f", "pel_p", "sp1_p", "sp2_p", "sp3_p", "nk1_p", "nk2_p", "hd_p", "earl_p", "earr_p", "tl_lift", "tl_curl")
    m.add(F(2), _chan(S, *body)).add(F(16), _chan(BOW, *body)).add(F(40), _chan(BOW, *body))
    m.add(F(46), pel_z=0.5, pel_p=16.0, pel_f=0.5, sp1_p=1.0, sp2_p=-1.0, sp3_p=-9.0)     # the chest rises off the elbows first
    m.add(F(54), _chan(REACH, *body)).add(F(62), _chan(REACH, *body)).add(F(84), _chan(S, *body))
    m.add(F(22), jaw=0.0).add(F(28), jaw=14.0).add(F(32), jaw=14.0).add(F(37), jaw=0.0)
    arc = lambda leg, a, b, lift: M.key_step_arc(m, leg, a, b, lift)     # leaves the floor at once, lands at b
    for leg, a, b in (("fl", 2, 10), ("fr", 6, 14)):
        m.add(F(a), **_paw(S, leg)).add(F(b), **{leg + "_f": BOW[leg + "_f"], leg + "_x": S[leg + "_x"], leg + "_z": 0.0}); arc(leg, a, b, 2.5)
        m.add(F(b + 2), **{leg + "_ank": BOW[leg + "_ank"], leg + "_pole": BOW[leg + "_pole"]})
        m.add(F(60), **{leg + "_ank": REACH[leg + "_ank"], leg + "_pole": BOW[leg + "_pole"]})
    for leg, a, b in (("fl", 66, 74), ("fr", 70, 78)):
        m.add(F(a), **{leg + "_f": BOW[leg + "_f"], leg + "_x": S[leg + "_x"], leg + "_z": 0.0}).add(F(b), **_paw(S, leg)); arc(leg, a, b, 2.5)
        m.add(F(b), **{leg + "_pole": 0.0})
    m.add(F(16), hl_ank=BOW["hl_ank"], hr_ank=BOW["hr_ank"]).add(F(42), **_paw(dict(S, hr_ank=BOW["hr_ank"]), "hr"))
    m.add(F(50), **_paw(REACH, "hr")).add(F(60), **_paw(REACH, "hr")).add(F(54), hl_ank=REACH["hl_ank"])
    m.add(F(70), **_paw(S, "hr")).add(F(76), hl_ank=0.0).add(F(66), hr_z=1.8).add(F(68), hr_z=1.0).add(F(69), hr_z=0.6)
    for k in range(43, 50): m.add(F(k), hr_z=3.0 * math.sin(0.5 * math.pi * (k - 42) / 8))
    m.add(F(90), S)
    return m


STRETCH = Action("Stretch", 90, _stretch().pose, "stand",
                 plants={"hl": [(0.0, F(90))], "hr": [(0.0, F(42)), (F(70), F(90))],
                         "fl": [(0.0, F(2)), (F(10), F(66)), (F(74), F(90))], "fr": [(0.0, F(6)), (F(14), F(70)), (F(78), F(90))]})


# ------------------------------------------------------------------------------------------------------------------------- yawn
def _yawn():
    """sit -> sit (2 s). f0-15: the head tips up (20 deg), the ears go back, the chest lifts a little; f15-36: the jaw opens wide (28)
    and holds; f36-48: it closes, a small quick head shake; f48-60: back into the sit."""
    S = P.SIT; m = M.Tracks(S)
    m.add(F(2), _chan(S, *NECK, *EARS, "sp2_p", "sp3_p"))
    m.add(F(15), hd_p=S["hd_p"] - 20.0, nk1_p=S["nk1_p"] + 4.0, earl_p=30.0, earr_p=30.0, earl_y=8.0, earr_y=8.0,
          sp2_p=S["sp2_p"] - 2.0, sp3_p=S["sp3_p"] - 1.5)
    m.add(F(33), hd_p=S["hd_p"] - 24.0, nk1_p=S["nk1_p"] + 5.0, earl_p=34.0, earr_p=34.0)
    m.add(F(6), jaw=0.0).add(F(20), jaw=26.0).add(F(31), jaw=28.0).add(F(40), jaw=0.0)     # 28 at most: the rig's hinge sits far back
    m.add(F(40), hd_y=0.0).add(F(42), hd_y=5.0).add(F(44), hd_y=-5.0).add(F(46), hd_y=3.0).add(F(48), hd_y=0.0)
    m.add(F(42), hd_p=S["hd_p"] - 6.0, nk1_p=S["nk1_p"], earl_p=10.0, earr_p=10.0, earl_y=0.0, earr_y=0.0, sp2_p=S["sp2_p"], sp3_p=S["sp3_p"])
    m.add(F(60), S)
    return m


YAWN = Action("Yawn", 60, _yawn().pose, "sit", plants={leg: [(0.0, F(60))] for leg in M.LEGS})


# ------------------------------------------------------------------------------------------------------------------------- hiss
# ARCH: the paws gathered in (hind 2 cm forward, fore 2 cm back), the back up in a high arch over them (the middle of the back 5 cm
# higher: pelvis tipped tail-down, spine_02/03 bending the front down onto the shoulders, which stay where they were; the shoulder
# blades rise above the back), stiff straight legs, heels up; tail up and bristling (bent back at the tip: bottlebrush), ears flat
# and turned out, head low and drawn in
GATHER = 2.0
ARCH = dict(pel_z=2.2, pel_p=-16.0, pel_f=1.6, sp1_p=2.8, sp2_p=27.5, sp3_p=15.5, nk1_p=22.0, nk2_p=6.0, hd_p=10.0,
            fl_sld=-1.2, fr_sld=-1.2, earl_p=70.0, earr_p=70.0, earl_y=15.0, earr_y=15.0, tl_lift=115.0, tl_curl=30.0,
            hl_ank=12.0, hr_ank=12.0, hl_f=P.STAND["hl_f"] + GATHER, hr_f=P.STAND["hr_f"] + GATHER,
            fl_f=P.STAND["fl_f"] - GATHER, fr_f=P.STAND["fr_f"] - GATHER)


def _hiss():
    """stand -> stand (2.5 s). f0-12: the arch builds (legs straighten, back up, tail up, ears flat, head down); f12-24 held with a
    slight tremble of the tail; f24-42: the hiss: jaw open 24, the head thrusts 2 cm forward and back; f42-75: release into the stand."""
    S = P.STAND; m = M.Tracks(S)
    paws = {k for k in ARCH if k[:2] in M.LEGS and k[2:] in ("_f",)}
    body = {k: v for k, v in ARCH.items() if k not in paws}
    m.add(F(1), _chan(S, *body)).add(F(12), body).add(F(24), body)
    for leg, a, b in (("hl", 1, 5), ("fl", 2, 6), ("hr", 3, 7), ("fr", 4, 8)):        # gather in: four quick small steps
        _step(m, leg, a, b, dict(_paw(S, leg), **{leg + "_f": ARCH[leg + "_f"]}), 1.2)
    for leg, a, b in (("fr", 48, 53), ("hr", 50, 55), ("fl", 52, 57), ("hl", 54, 59)):  # and back out
        _step(m, leg, a, b, _paw(S, leg), 1.2)
    m.add(F(24), jaw=0.0).add(F(29), jaw=24.0).add(F(37), jaw=22.0).add(F(42), jaw=0.0)
    m.add(F(29), nk1_p=ARCH["nk1_p"] - 10.0, hd_p=ARCH["hd_p"] - 8.0, nk2_p=-4.0).add(F(37), nk1_p=ARCH["nk1_p"] - 9.0,
                                                                                    hd_p=ARCH["hd_p"] - 7.0, nk2_p=-4.0)
    m.add(F(44), body).add(F(70), S).add(F(75), S)
    for f, v in ((12, 0.0), (15, 3.0), (18, -3.0), (21, 2.0), (24, 0.0)): m.add(F(f), tl_side=v)
    return m


_HISS_STEPS = {"hl": (1, 5, 54, 59), "fl": (2, 6, 52, 57), "hr": (3, 7, 50, 55), "fr": (4, 8, 48, 53)}
HISS = Action("Hiss", 75, _hiss().pose, "stand",
              plants={leg: [(0.0, F(a)), (F(b), F(c)), (F(d), F(75))] for leg, (a, b, c, d) in _HISS_STEPS.items()})

SEQS = [GROOM, STRETCH, YAWN, HISS]
