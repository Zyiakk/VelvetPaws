"""Postures of the cat: Sit, Lie (sphinx) and side Sleep as breathing loops, and the transitions stand -> sit -> lie -> sleep and back
(Task 4). Each transition is a Tracks pose from the posture it starts in to the one it ends in, every channel keyed at its own
times so the body moves in a cat's order; paws that change place do it as a step (a lift arc between two plants) or, where the
body rolls over them, in the frame of the body part they belong to (Move.ride). Loops are the posture plus breathing and small head
or ear movements with whole periods, so the last frame equals the first.

Times are seconds; plant and step times lie on frames (n / 30), so a paw is on the floor exactly on its planted frames."""
import math

import cat_motion as M
import cat_poses as P


RIDE_CLEAR = 1.3      # cm: a riding paw's tip stays at least this high in the middle of its ride (the body may roll it into the floor)


F = M.F


class Move:
    """A transition pose: Tracks plus paw overrides.
    step(leg, t0, t1, lift): the paw's x/f/z channels are keyed at t0 (where the track has it) and t1 (where the caller keys it);
    in between its z gets lift * sin(pi u), so it leaves the floor at once and lands at t1.
    ride(leg, t0, t1, lift): between t0 and t1 the paw moves in the frame of its body part (cat_poses.body_point) from where it is
    at t0 to where it is at t1 (eased), plus lift * sin(pi u) in z, and at least RIDE_CLEAR up in the middle (where the rolling body
    would take it under the floor it slides along it): the paws travel with a body that rolls over them. bump: (x, f, z) cm in the
    body part's rest frame, added times sin(pi u): a detour, e.g. forward out from under a hip that rolls down onto its paw."""

    def __init__(self, base):
        self.T = M.Tracks(base); self.steps, self.rides, self._ends = [], [], {}

    def add(self, t, pose=None, **kw):
        self.T.add(t, pose, **kw); return self

    def _paw_keys(self, leg, t0, t1):
        for c in ("_x", "_f", "_z"): self.T.add(t0, **{leg + c: self.T.value(leg + c, t0)})

    def step(self, leg, t0, t1, lift, to):
        """to: (x, f, z) where the paw lands at t1."""
        self._paw_keys(leg, t0, t1); self.T.add(t1, **{leg + "_x": to[0], leg + "_f": to[1], leg + "_z": to[2]})
        self.steps.append((leg, t0, t1, lift)); return self

    def ride(self, leg, t0, t1, lift, to, bump=(0.0, 0.0, 0.0)):
        self._paw_keys(leg, t0, t1); self.T.add(t1, **{leg + "_x": to[0], leg + "_f": to[1], leg + "_z": to[2]})
        self.rides.append((leg, t0, t1, lift, bump)); return self

    def _local(self, leg, t):
        key = (leg, t)
        if key not in self._ends:
            p = self.T.pose(t); self._ends[key] = P.body_local(p, leg, (p[leg + "_x"], p[leg + "_f"], p[leg + "_z"]))
        return self._ends[key]

    def pose(self, t):
        p = self.T.pose(t)
        for leg, t0, t1, lift in self.steps:
            if t0 < t < t1: p[leg + "_z"] += M.step_arc(lift, t - t0, t1 - t0)
        for leg, t0, t1, lift, bump in self.rides:
            if t0 < t < t1:
                u = (t - t0) / (t1 - t0); s = M.smooth(u); a, b = self._local(leg, t0), self._local(leg, t1); k = math.sin(math.pi * u)
                x, f, z = P.body_point(p, leg, tuple(a[i] + (b[i] - a[i]) * s + bump[i] * k for i in range(3)))
                floor = RIDE_CLEAR * M.smooth(min(u, 1.0 - u) / 0.07)     # off the floor right after leaving it, until it lands
                p[leg + "_x"], p[leg + "_f"], p[leg + "_z"] = x, f, max(z + M.step_arc(lift, u, 1.0), floor)
        return p


_paw_at, _chan = M.paw_xyz, M.chan


TRUNK = ("pel_x", "pel_f", "pel_z", "pel_y", "pel_p", "pel_r", "sp1_p", "sp2_p", "sp3_p", "sp1_y", "sp2_y", "sp3_y", "sp_r")
SPINE = ("sp1_p", "sp2_p", "sp3_p", "sp1_y", "sp2_y", "sp3_y", "sp_r")
NECK = ("nk1_p", "nk2_p", "nk_y", "hd_p", "hd_y", "hd_r")
EARS = ("earl_p", "earl_y", "earr_p", "earr_y")
TAIL = ("tl_lift", "tl_curl", "tl_side", "tl_wrap")


# ------------------------------------------------------------------------------------------------------------------------- sit
def _sit_enter():
    """stand -> sit (0.8 s): a small shift forward, the hind paws step up under the body one after the other (left, then right) while
    the haunches go down first (the pelvis sinks and tips tail-down, the lumbar spine starts to round), heels flatten onto the floor
    as they settle; then the chest rises upright on the straightening fore legs (the scapulae turn into the sit), the head stays
    level all the way; the fore paws, planted, step in together one after the other while the chest rises; the tail lifts a little
    at first, then drops and wraps round."""
    S, E = P.STAND, P.SIT; m = Move(S)
    m.add(F(3), pel_f=1.0, tl_lift=10.0)
    m.step("hl", F(3), F(11), 2.2, _paw_at(E, "hl")).add(F(3), hl_ank=0.0).add(F(11), hl_ank=-25.0)
    m.step("hr", F(7), F(15), 2.2, _paw_at(E, "hr")).add(F(7), hr_ank=0.0).add(F(15), hr_ank=-25.0)
    m.add(F(3), pel_z=0.0, pel_p=0.0).add(F(14), pel_z=-7.5, pel_p=-24.0, pel_f=3.5).add(F(20), pel_z=-11.5, pel_p=-44.0)
    m.add(F(22), hl_ank=-72.0, hr_ank=-72.0)
    m.add(F(8), sp1_p=0.0, sp2_p=0.0, sp3_p=0.0, nk1_p=0.0, nk2_p=0.0, hd_p=0.0)
    m.add(F(14), sp1_p=8.0, nk1_p=0.0, nk2_p=0.0, hd_p=16.0)            # the head stays level while the trunk tips back
    m.add(F(20), sp1_p=20.0, sp2_p=-3.0, sp3_p=-6.0, nk1_p=6.0, nk2_p=2.0, hd_p=44.0)
    m.add(F(12), fl_scap=0.0, fr_scap=0.0).add(F(22), fl_scap=E["fl_scap"], fr_scap=E["fr_scap"])
    m.step("fl", F(16), F(21), 1.2, _paw_at(E, "fl")).step("fr", F(18), F(23), 1.2, _paw_at(E, "fr"))
    m.add(F(12), tl_lift=0.0, tl_side=30.0, tl_wrap=0.0).add(F(18), tl_lift=-20.0, tl_side=70.0, tl_wrap=90.0)
    m.add(F(24), E)
    return m


def _sit_exit():
    """sit -> stand (0.6 s): the fore paws step out to the stand's width (left, then right), the chest leans forward over them (the
    lumbar curl opens), the haunches lift off and the heels come up, the hind paws step back under the hips (left, then right), the
    tail lets go of the paws and rises behind. The head stays level."""
    S, E = P.SIT, P.STAND; m = Move(S)
    m.step("fl", F(1), F(5), 1.0, _paw_at(E, "fl")).step("fr", F(3), F(7), 1.0, _paw_at(E, "fr"))
    m.add(F(2), _chan(S, *SPINE, *NECK, "pel_f", "pel_z", "pel_p", "fl_scap", "fr_scap"))
    m.add(F(5), pel_p=-40.0, sp1_p=18.0, sp2_p=-2.0, sp3_p=-3.0, nk1_p=2.0, nk2_p=0.0, hd_p=30.0)
    m.add(F(9), pel_z=-6.0, pel_p=-12.0, pel_f=3.0, sp1_p=4.0, sp2_p=0.0, sp3_p=0.0, nk1_p=0.0, hd_p=8.0, fl_scap=0.0, fr_scap=0.0)
    m.add(F(2), hl_ank=S["hl_ank"], hr_ank=S["hr_ank"]).add(F(7), hl_ank=-30.0, hr_ank=-30.0)
    m.step("hl", F(6), F(12), 2.2, _paw_at(E, "hl")).add(F(12), hl_ank=0.0)
    m.step("hr", F(9), F(15), 2.2, _paw_at(E, "hr")).add(F(15), hr_ank=0.0)
    m.add(F(2), tl_wrap=S["tl_wrap"], tl_side=S["tl_side"], tl_lift=S["tl_lift"]).add(F(6), tl_wrap=80.0, tl_side=50.0, tl_lift=-5.0)
    m.add(F(10), tl_wrap=10.0, tl_side=20.0, tl_lift=5.0)
    m.add(F(18), E)
    return m


def _sit_loop(t):
    """Slow breathing (two breaths in 4 s: the ribcage lifts, the scapulae take it, the fore paws stay), the head turns 4 deg to one
    side and back once, the left ear turns out for a moment (listening)."""
    S = P.SIT; b = M.breath(t, 2.0, 1.0)
    ear = 14.0 * M.smooth(min(max((t - 2.4) / 0.25, 0.0), 1.0)) * (1 - M.smooth(min(max((t - 3.0) / 0.35, 0.0), 1.0)))
    return dict(S, sp2_p=S["sp2_p"] - 1.0 * b, sp3_p=S["sp3_p"] - 0.8 * b, hd_y=M.harm(t / 4.0, 4.0, 1, 0.0), earl_y=S["earl_y"] + ear)


# ------------------------------------------------------------------------------------------------------------------------- lie
def _lie_enter():
    """sit -> sphinx (1.0 s): the chest comes down over the planted fore paws (elbows fold back), then the fore paws, left then right,
    step a little forward and lay down flat (the wrist extends, the forearm comes down onto the floor) while the chest settles between
    them; as the pelvis levels the hips go back over the hind paws, which step back under them (left, then right) into the flat fold
    of the lie; the tail follows round the side."""
    S, E = P.SIT, P.LIE; m = Move(S)
    m.add(F(3), _chan(S, *SPINE, *NECK, "pel_f", "pel_z", "pel_p", "fl_scap", "fr_scap"))
    m.add(F(12), pel_p=-46.0, sp1_p=22.0, sp2_p=2.0, sp3_p=4.0, nk1_p=-4.0, nk2_p=0.0, hd_p=20.0, pel_f=3.5, fl_scap=-4.0, fr_scap=-4.0)
    m.add(F(20), pel_p=-24.0, sp1_p=10.0, sp2_p=0.0, sp3_p=0.0).add(F(24), _chan(E, *SPINE))    # the back is level before the belly lands
    m.add(F(12), pel_z=S["pel_z"]).add(F(27), pel_p=E["pel_p"], pel_z=E["pel_z"])
    m.step("fl", F(10), F(18), 1.8, _paw_at(E, "fl")).add(F(10), fl_ank=0.0, fl_toe=0.0).add(F(18), fl_ank=E["fl_ank"], fl_toe=E["fl_toe"])
    m.step("fr", F(15), F(24), 1.8, _paw_at(E, "fr")).add(F(15), fr_ank=0.0, fr_toe=0.0).add(F(24), fr_ank=E["fr_ank"], fr_toe=E["fr_toe"])
    m.step("hl", F(16), F(24), 1.6, _paw_at(E, "hl")).step("hr", F(19), F(27), 1.6, _paw_at(E, "hr"))
    m.add(F(8), _chan(S, *TAIL))
    m.add(F(30), E)
    return m


def _lie_exit():
    """sphinx -> sit (0.8 s): the fore paws, left then right, rise onto their toes and step back under the shoulders (the wrist bends
    back to standing) while the chest lifts a little; then the chest rises on the straightening fore legs and the pelvis tips back into
    the sit, the hind paws stepping forward under the haunches (left, then right); the tail stays round the side."""
    S, E = P.LIE, P.SIT; m = Move(S)
    m.add(F(2), _chan(S, *SPINE, *NECK, "pel_f", "pel_z", "pel_p"))
    m.add(F(9), sp1_p=-4.0, sp2_p=-7.0, sp3_p=-10.0, nk1_p=-6.0, hd_p=28.0, pel_f=3.0, pel_z=-11.2, fl_scap=0.0, fr_scap=0.0)
    m.step("fl", F(1), F(8), 1.4, _paw_at(E, "fl")).add(F(1), fl_ank=S["fl_ank"], fl_toe=S["fl_toe"]).add(F(8), fl_ank=0.0, fl_toe=0.0)
    m.step("fr", F(4), F(11), 1.4, _paw_at(E, "fr")).add(F(4), fr_ank=S["fr_ank"], fr_toe=S["fr_toe"]).add(F(11), fr_ank=0.0, fr_toe=0.0)
    m.add(F(5), pel_p=-4.0)
    m.step("hl", F(8), F(16), 1.6, _paw_at(E, "hl")).step("hr", F(11), F(19), 1.6, _paw_at(E, "hr"))
    m.add(F(4), _chan(S, *TAIL))
    m.add(F(24), E)
    return m


def _lie_loop(t):
    """Breathing (two breaths in 4 s; the back rises), the head turns 3 deg to one side and back once."""
    S = P.LIE; b = M.breath(t, 2.0, 1.0)
    return dict(S, sp2_p=S["sp2_p"] - 0.9 * b, sp3_p=S["sp3_p"] - 0.6 * b, hd_y=M.harm(t / 4.0, 3.0, 1, 0.0))


# ----------------------------------------------------------------------------------------------------------------------- sleep
def _sleep_enter():
    """sphinx -> side sleep (1.2 s): the hind quarters tip over first (pelvis rolls onto the right side, the body lifts a little as it
    rolls over the folded legs), the chest follows; the legs travel with the rolling body out from under it (ride) and relax; the
    spine curls in, the head sinks to the floor last and turns back up; the ears relax; the tail curls round."""
    S, E = P.LIE, P.SLEEP; m = Move(S)
    m.add(F(6), pel_r=0.0, pel_z=S["pel_z"], pel_f=S["pel_f"]).add(F(20), pel_r=-50.0, pel_z=-8.2).add(F(25), pel_z=-8.5).add(F(30), pel_r=E["pel_r"], pel_z=E["pel_z"])
    m.add(F(8), _chan(S, *SPINE[:3])).add(F(32), _chan(E, *SPINE[:3]))
    m.add(F(12), _chan(S, *NECK)).add(F(20), nk1_p=-6.0, nk2_p=-2.0, hd_p=12.0, hd_r=38.0)      # the head stays upright while the body rolls
    m.add(F(28), nk1_p=-14.0, nk2_p=-8.0, hd_p=18.0, hd_r=32.0).add(F(36), _chan(E, *NECK))   # then sinks to the floor
    m.add(F(16), _chan(S, *EARS)).add(F(34), _chan(E, *EARS))
    # the right hip rolls down onto the folded right hind paw: that paw slides forward out from under it on the way (bump)
    for leg, a, b, lift, bump in (("hr", 6, 26, 1.2, (0.0, 4.0, 0.0)), ("hl", 8, 28, 1.5, None), ("fr", 10, 30, 1.0, None),
                                  ("fl", 12, 32, 1.5, None)):
        m.ride(leg, F(a), F(b), lift, _paw_at(E, leg), bump or (0.0, 0.0, 0.0))
        m.add(F(a), **_chan(S, leg + "_ank", leg + "_toe", leg + "_roll")).add(F(b), **_chan(E, leg + "_ank", leg + "_toe", leg + "_roll"))
    m.add(F(8), _chan(S, *TAIL)).add(F(36), _chan(E, *TAIL))
    m.add(F(36), E)
    return m


def _sleep_exit():
    """side sleep -> sphinx (1.0 s): the head lifts first, the chest rolls up onto the sternum, the pelvis follows; the legs fold back
    under the body as it rolls onto them (ride) and the hind paws are planted again before the end; the tail draws round the side."""
    S, E = P.SLEEP, P.LIE; m = Move(S)
    m.add(F(1), _chan(S, *NECK)).add(F(8), nk1_p=-4.0, nk2_p=0.0, hd_p=12.0, hd_r=45.0)       # the head lifts and rights itself first
    m.add(F(16), hd_r=20.0).add(F(24), _chan(E, *NECK))
    m.add(F(2), _chan(S, *EARS)).add(F(8), _chan(E, *EARS))
    m.add(F(4), pel_r=S["pel_r"], pel_z=S["pel_z"], pel_f=S["pel_f"]).add(F(9), pel_z=-8.0).add(F(14), pel_r=-40.0, pel_z=-7.9).add(F(24), pel_r=0.0, pel_z=E["pel_z"])
    m.add(F(4), _chan(S, *SPINE[:3])).add(F(22), _chan(E, *SPINE[:3]))
    # the right hind paw comes back in under the hip from in front (bump), not through the hip rolling up off it
    for leg, a, b, lift, bump in (("fl", 4, 18, 1.5, None), ("fr", 6, 20, 1.0, None), ("hl", 6, 22, 1.5, None),
                                  ("hr", 8, 24, 1.2, (0.0, 4.0, 0.0))):
        m.ride(leg, F(a), F(b), lift, _paw_at(E, leg), bump or (0.0, 0.0, 0.0))
        m.add(F(a), **_chan(S, leg + "_ank", leg + "_toe", leg + "_roll")).add(F(b), **_chan(E, leg + "_ank", leg + "_toe", leg + "_roll"))
    m.add(F(4), _chan(S, *TAIL)).add(F(26), _chan(E, *TAIL))
    m.add(F(30), E)
    return m


def _sleep_loop(t):
    """Slow deep sleep breathing (two breaths in 6 s): the flank rises and falls."""
    S = P.SLEEP; b = M.breath(t, 3.0, 1.0)
    return dict(S, sp2_p=S["sp2_p"] - 1.4 * b, sp3_p=S["sp3_p"] - 1.0 * b)


SIT_ENTER = M.Seq("SitEnter", 24, _sit_enter().pose, start="stand", end="sit", group="posture",
                  plants={"fl": [(0.0, F(16)), (F(21), F(24))], "fr": [(0.0, F(18)), (F(23), F(24))], "hl": [(0.0, F(3)), (F(11), F(24))], "hr": [(0.0, F(7)), (F(15), F(24))]})
SIT_LOOP = M.Seq("SitLoop", 120, _sit_loop, loop=True, start="sit", end="sit", group="posture",
                 plants={leg: [(0.0, F(120))] for leg in M.LEGS})
SIT_EXIT = M.Seq("SitExit", 18, _sit_exit().pose, start="sit", end="stand", group="posture",
                 plants={"fl": [(0.0, F(1)), (F(5), F(18))], "fr": [(0.0, F(3)), (F(7), F(18))], "hl": [(0.0, F(6)), (F(12), F(18))], "hr": [(0.0, F(9)), (F(15), F(18))]})
LIE_ENTER = M.Seq("LieEnter", 30, _lie_enter().pose, start="sit", end="lie", group="posture",
                  plants={"fl": [(0.0, F(10)), (F(18), F(30))], "fr": [(0.0, F(15)), (F(24), F(30))],
                          "hl": [(0.0, F(16)), (F(24), F(30))], "hr": [(0.0, F(19)), (F(27), F(30))]})
LIE_LOOP = M.Seq("LieLoop", 120, _lie_loop, loop=True, start="lie", end="lie", group="posture",
                 plants={leg: [(0.0, F(120))] for leg in M.LEGS})
LIE_EXIT = M.Seq("LieExit", 24, _lie_exit().pose, start="lie", end="sit", group="posture",
                 plants={"fl": [(0.0, F(1)), (F(8), F(24))], "fr": [(0.0, F(4)), (F(11), F(24))],
                         "hl": [(0.0, F(8)), (F(16), F(24))], "hr": [(0.0, F(11)), (F(19), F(24))]})
SLEEP_ENTER = M.Seq("SleepEnter", 36, _sleep_enter().pose, start="lie", end="sleep", group="posture",
                    plants={"hl": [(0.0, F(8))], "hr": [(0.0, F(6))], "fl": [(0.0, F(12))], "fr": [(0.0, F(10))]})
SLEEP_LOOP = M.Seq("SleepLoop", 180, _sleep_loop, loop=True, start="sleep", end="sleep", group="posture")
SLEEP_EXIT = M.Seq("SleepExit", 30, _sleep_exit().pose, start="sleep", end="lie", group="posture",
                   plants={"hl": [(F(22), F(30))], "hr": [(F(24), F(30))], "fl": [(F(18), F(30))], "fr": [(F(20), F(30))]})

SEQS = [SIT_ENTER, SIT_LOOP, SIT_EXIT, LIE_ENTER, LIE_LOOP, LIE_EXIT, SLEEP_ENTER, SLEEP_LOOP, SLEEP_EXIT]
