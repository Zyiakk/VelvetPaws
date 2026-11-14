"""Jumps of the cat (Task 5), all in place: stage 3 moves the capsule with LaunchCharacter (the arc and the height) while the montage
plays. JumpTakeoff (stand -> air): eyes on the target, the weight goes back, the haunches sink into the crouch (CROUCH at 0.45 s) with a
short wiggle of the rear end, then the explosive extension: the chest rises, the fore paws leave first (wrist first) and reach forward and up, the
hind legs straighten up onto the toes and leave the floor in the last frame (the launch, cat_seqs.launch_time). JumpAir (air loop):
the flight pose held, fore legs reaching forward, hind legs drawn in, the tail as a rudder; little movement so the montage can leave it
at any frame. JumpLand (air -> stand): fore paws reach down and land first, the chest dips into the elbows, the hind paws land under
the hips, the whole body absorbs and rises back into the stand. JumpDownStart (stand -> air): head and chest go down over the edge,
the fore paws leave and reach forward and low, the hind legs push off; then the same JumpAir and JumpLand.

Times are frames / 30 (F); plant spans lie on frames, so a paw is on the floor exactly on its planted frames and off it (above 0.5 cm)
on every other frame."""
import cat_motion as M
import cat_poses as P


F, _paw, _chan = M.F, M.paw_keys, M.chan


TRUNK = ("pel_x", "pel_f", "pel_z", "pel_y", "pel_p", "sp1_p", "sp2_p", "sp3_p", "sp1_y")
NECK = ("nk1_p", "nk2_p", "hd_p")
EARS = ("earl_p", "earr_p")
TAIL = ("tl_lift", "tl_curl", "tl_side")
FORE, HIND = ("fl", "fr"), ("hl", "hr")


def _legs(m, t, pose, legs):
    for leg in legs: m.add(t, **_paw(pose, leg))


# ------------------------------------------------------------------------------------------------------------------- takeoff
def _takeoff():
    """stand -> air (0.8 s). f0-7: the head lifts and looks up at the target, ears forward; the weight goes back onto the hind legs.
    f4-13.5: the haunches sink, hocks lower, elbows bend: CROUCH at 0.45 s. f10-17: the rear end wiggles (pelvis yaw, the chest held
    still by spine_01 turning back). f16-23: extension: the trunk pitches nose up and rises, the fore paws leave at f18 and reach
    forward and up, the hind legs straighten up onto the toes (heels high); the hind paws leave the floor after f23 (the launch,
    cat_seqs.launch_time), stay extended behind the rising trunk and draw in towards f27 (= AIR)."""
    S, C, X, A = P.STAND, P.CROUCH, P.EXTEND, P.AIR; m = M.Tracks(S)
    m.add(F(2), _chan(S, *NECK, *EARS)).add(F(7), nk1_p=14.0, nk2_p=7.0, hd_p=-6.0, earl_p=-6.0, earr_p=-6.0)
    m.add(F(3), pel_f=0.0).add(F(8), pel_f=-1.5)
    m.add(F(4), _chan(S, "pel_z", "pel_p", "sp1_p", "sp2_p", "sp3_p", "tl_lift", "tl_curl"))
    m.add(F(4), hl_ank=0.0, hr_ank=0.0, fl_ank=0.0, fr_ank=0.0)
    m.add(F(13.5), _chan(C, "pel_z", "pel_f", "pel_p", "sp1_p", "sp2_p", "sp3_p", *NECK, *EARS, "tl_lift", "tl_curl", "hl_ank", "hr_ank",
                         "fl_ank", "fr_ank"))
    # rear-end wiggle: the pelvis yaws, spine_01 turns it back so the chest and the gaze stay on the target
    for f, y in ((10, 0.0), (11.5, 3.5), (13.5, -3.5), (15, 2.0), (16.5, 0.0)): m.add(F(f), pel_y=y, sp1_y=-y)
    m.add(F(10), pel_x=0.0).add(F(11.5), pel_x=0.5).add(F(13.5), pel_x=-0.5).add(F(15), pel_x=0.3).add(F(16.5), pel_x=0.0)
    m.add(F(16), pel_z=C["pel_z"] - 0.5, pel_p=C["pel_p"], pel_f=C["pel_f"] + 0.5, hl_ank=C["hl_ank"] - 4, hr_ank=C["hr_ank"] - 4)
    # extension
    m.add(F(19.5), pel_z=-2.5, pel_p=-11.0, pel_f=2.5)
    m.add(F(23), _chan(X, "pel_z", "pel_p", "pel_f", "sp1_p", "sp2_p", "sp3_p", *NECK, "tl_lift", "tl_curl", "hl_ank", "hr_ank", "hl_toe", "hr_toe"))
    for leg in FORE:                       # planted until f18, then lifted and reaching forward and up
        m.add(F(18), **_paw(dict(S, **{leg + "_ank": C[leg + "_ank"]}), leg))
        m.add(F(20), **{leg + "_ank": 60.0, leg + "_toe": 35.0})          # the paw peels off the floor wrist first
        m.add(F(23), **{k: v for k, v in _paw(X, leg).items() if not k.endswith("_ank")}).add(F(24), **{leg + "_ank": X[leg + "_ank"]})
    for leg in HIND: m.add(F(23), **_paw(X, leg))       # on their toes, still on the stand's places: the last planted frame
    _lift_off(m, X, A, 23)
    return m


LIFT_OFF = 4        # frames from the hind paws' lift-off to the end of Takeoff / DownStart (the end tag's flight pose)


def _lift_off(m, X, A, f0):
    """After the last planted frame f0 the hind legs stay extended behind the rising trunk (their paws trail back and up with
    the body, heels still high) and draw in under the hips only towards the end: LIFT_OFF frames from X (last planted pose)
    into A (the flight pose), every channel eased, no single-frame change (gate: cat_motion.end_jumps)."""
    f1 = f0 + LIFT_OFF; mid = f0 + LIFT_OFF / 2.0
    for leg in HIND:
        u = {"_x": 0.5, "_f": 0.5, "_z": 0.5, "_ank": 0.3, "_toe": 0.5}       # the heel stays high longest
        m.add(F(mid), **{leg + c: X[leg + c] + k * (A[leg + c] - X[leg + c]) for c, k in u.items()})
    m.add(F(f1), A)


# ------------------------------------------------------------------------------------------------------------------------ air
def _air(t, A=P.AIR):
    """The flight pose held; one slow cycle over 0.4 s: the tail steers (side and curl), the fore paws reach a little further and
    back, the back breathes with it. Small, so the montage can leave the loop at any frame. A: AIR (jump up) or AIR_DOWN."""
    ph = t / F(12); h = lambda a, off=0.0: M.harm(ph, a, 1, off) - M.harm(0.0, a, 1, off)    # 0 at the loop's ends (= AIR)
    d = dict(A, tl_side=A["tl_side"] + h(7.0), tl_curl=A["tl_curl"] + h(5.0, 0.2), sp1_p=A["sp1_p"] + h(0.6), sp2_p=A["sp2_p"] + h(0.6))
    for leg in FORE: d[leg + "_f"] = A[leg + "_f"] + h(0.7); d[leg + "_z"] = A[leg + "_z"] + h(-0.5)
    for leg in HIND: d[leg + "_f"] = A[leg + "_f"] + h(-0.5, 0.1)
    return d


# ----------------------------------------------------------------------------------------------------------------------- land
def _land(A=P.AIR):
    """air -> stand (0.5 s). f0-3: the trunk pitches nose down, the fore paws reach down and land at f3 (on the stand's places);
    f3-7: the chest dips into the elbows, the hind legs swing forward under the hips and land at f7, heels dropping; f9: the deepest
    absorb (LANDED); f9-15: the body rises into the stand; the tail goes up for balance and settles. A: the flight pose it starts
    from (AIR, or AIR_DOWN for the jump down: the head, looking down already, only follows the trunk)."""
    L, S = P.LANDED, P.STAND; m = M.Tracks(A)
    m.add(F(3), pel_p=7.0, pel_z=-1.5, pel_f=0.0, sp1_p=3.0, sp2_p=3.0, sp3_p=2.0, nk1_p=-4.0, nk2_p=0.0, hd_p=2.0)
    for leg in FORE: m.add(F(3), **_paw(S, leg))
    m.add(F(6), pel_p=6.0, pel_z=-3.5)
    m.add(F(5), fl_ank=-14.0, fr_ank=-14.0)
    for leg in HIND:
        s = 1 if leg == "hl" else -1
        m.add(F(4), **{leg + "_x": 4.6 * s, leg + "_f": -7.5, leg + "_z": 3.0, leg + "_ank": 25.0, leg + "_toe": 10.0})
        m.add(F(7), **_paw(dict(S, **{leg + "_ank": -10.0}), leg))
    m.add(F(9), L).add(F(4), tl_lift=35.0, tl_curl=15.0)
    m.add(F(15), S)
    return m


# ------------------------------------------------------------------------------------------------------------------ jump down
def _down_start():
    """stand -> air (0.5 s). f2-9: head and chest go down and forward over the edge (pelvis nose down, neck lowered, the head looks
    down at the landing spot), weight forward; the fore paws leave at f6 and reach forward and low (f11); the hind heels rise and
    push, the hind paws leave the floor after f14 (the launch), trail behind and draw in towards f18 (= AIR_DOWN); the head looks
    down at the landing spot all the way into the flight."""
    S, D, A = P.STAND, P.DROP, P.AIR_DOWN; m = M.Tracks(S)
    m.add(F(2), _chan(S, *TRUNK, *NECK, "tl_lift"))
    m.add(F(9), _chan(D, "pel_z", "pel_f", "pel_p", "sp1_p", "sp2_p", "sp3_p", *NECK, "tl_lift"))
    m.add(F(14), _chan(D, *NECK))                  # the head keeps looking down over the edge through the push
    for leg in FORE:
        m.add(F(6), **_paw(S, leg))
        m.add(F(8.5), **{leg + "_f": 21.0, leg + "_z": 2.5, leg + "_ank": 20.0})     # peeled off, straight on forward and low
        m.add(F(11), **_paw(D, leg))
    for leg in HIND: m.add(F(5), **{leg + "_ank": 0.0}).add(F(14), **_paw(D, leg))
    _lift_off(m, D, A, 14)
    return m


_LAND_PLANTS = {"fl": [(F(3), F(15))], "fr": [(F(3), F(15))], "hl": [(F(7), F(15))], "hr": [(F(7), F(15))]}
JUMP_TAKEOFF = M.Seq("JumpTakeoff", 23 + LIFT_OFF, _takeoff().pose, start="stand", end="air", group="jump",
                     plants={"fl": [(0.0, F(18))], "fr": [(0.0, F(18))], "hl": [(0.0, F(23))], "hr": [(0.0, F(23))]}, lift_off=F(23))
JUMP_AIR = M.Seq("JumpAir", 12, _air, loop=True, start="air", end="air", group="jump")
JUMP_LAND = M.Seq("JumpLand", 15, _land().pose, start="air", end="stand", group="jump", plants=_LAND_PLANTS)
JUMP_DOWN_START = M.Seq("JumpDownStart", 14 + LIFT_OFF, _down_start().pose, start="stand", end="air_down", group="jump",
                        plants={"fl": [(0.0, F(6))], "fr": [(0.0, F(6))], "hl": [(0.0, F(14))], "hr": [(0.0, F(14))]}, lift_off=F(14))
JUMP_AIR_DOWN = M.Seq("JumpAirDown", 12, lambda t: _air(t, P.AIR_DOWN), loop=True, start="air_down", end="air_down", group="jump")
JUMP_DOWN_LAND = M.Seq("JumpDownLand", 15, _land(P.AIR_DOWN).pose, start="air_down", end="stand", group="jump", plants=_LAND_PLANTS)

SEQS = [JUMP_TAKEOFF, JUMP_AIR, JUMP_LAND, JUMP_DOWN_START, JUMP_AIR_DOWN, JUMP_DOWN_LAND]
