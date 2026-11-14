"""Rubbing against Jodi's legs (round 6): RubWalk (loop, a slow close walk with the body curved round the leg on her LEFT side, the
flank leaning in, tail up with a hook at the tip) and HeadRub (one-shot from the stand: head and cheek pushed sideways along a leg on
her left, twice, ears flattened on that side, tail up).

The inside is always the cat's left (+x): the behaviour circles Jodi's legs with them on the cat's left, i.e. counter-clockwise seen
from above. Times are frames / 30 (F); plant spans lie on frames."""
import cat_motion as M
import cat_poses as P

F, _chan = M.F, M.chan

# --------------------------------------------------------------------------------------------------------------------- RubWalk
# A slow walk (20 cm/s, 32 frames, lateral footfall like Walk), the body bent into a curve towards the left (hips turned out to the
# right, spine and neck turned left), leaning in (left side down) and shifted 1.2 cm to the left so the left flank is the contact
# side, the head carried up (affectionate, not stalking) and turned in, the tail raised high with the tip hooked over. The trunk's oscillation is half Walk's.
RUB_BEND = dict(pel_y=-8.0, sp1_y=5.5, sp2_y=5.5, sp3_y=5.5, nk_y=14.0, hd_y=6.0, hd_r=4.0,
                pel_r=6.0, sp_r=5.0, pel_x=1.2, pel_z=-0.8, nk1_p=5.0, hd_p=-2.0,
                tl_lift=95.0, tl_curl=45.0, tl_side=8.0, earl_y=8.0, earr_y=5.0)
RUB_WALK = M.Gait(
    "RubWalk", 32, speed=20.0, duty=22 / 32,      # stance ends on a frame
    touchdown={"hl": 0.0, "fl": 7 / 32, "hr": 16 / 32, "fr": 23 / 32},   # on frames, lateral sequence (as Walk)
    lift={"h": 2.4, "f": 2.8},
    home={"hl": (3.4, -7.0), "hr": (-3.0, -7.0), "fl": (4.8, 13.4), "fr": (-1.2, 13.4)},   # fore paws follow the shoulders left
    base=dict(P.GAIT, **RUB_BEND),
    body={
        "pel_z": (0.25, 2, 0.37),
        "pel_r": (1.2, 1, 0.56),
        "pel_y": (2.0, 1, 0.25),
        "sp1_y": (-1.0, 1, 0.25), "sp2_y": (-1.0, 1, 0.25), "sp3_y": (2.0, 1, 0.48),
        "sp1_p": (-0.4, 2, 0.83), "sp2_p": (-0.4, 2, 0.83), "sp3_p": (-0.4, 2, 0.83),
        "sp_r": (1.2, 1, 0.79),
        "tl_side": (6.0, 1, 0.33),     # the raised tail sways a little, lagging the hips
        "tl_curl": (5.0, 1, 0.1),      # the hook opens and closes
    },
    ankle=18.0, wrist=40.0, toe=22.0, tail_wave=(2.0, 1),
    roll={"h": (-8.0, 25.0), "f": (-4.0, 16.0)}, swing_v=(0.3, 0.4), zpeak={"h": 0.4, "f": 0.45},
    tuck_peak={"h": 0.3, "f": 0.4}, shrug=0.4, steady=(0.7, 0.5, 0.6))
RUB_WALK.group = "social"

# --------------------------------------------------------------------------------------------------------------------- HeadRub
NECK = ("nk1_p", "nk2_p", "nk_y", "hd_p", "hd_y", "hd_r")
LEAN = dict(pel_x=1.2, pel_r=5.0, sp_r=4.0, sp3_y=3.0, nk_y=18.0, hd_y=10.0, hd_r=8.0, nk1_p=-4.0, hd_p=3.0,
            earl_p=30.0, earl_y=10.0, tl_lift=75.0, tl_curl=30.0)
# a push: the head turned further in and tipped with the left ear down, the top of the head and the cheek pressed against the leg
# and slid forward and up (chin raised), the weight a little forward
PUSH = dict(LEAN, pel_f=1.0, nk_y=22.0, hd_y=24.0, hd_r=24.0, nk1_p=6.0, nk2_p=3.0, hd_p=-8.0, earl_p=60.0, earl_y=20.0, earr_p=15.0,
            tl_lift=85.0, tl_curl=38.0)
# between the pushes: the head comes back round (cheek leading), the left ear up again
BACK = dict(LEAN, pel_f=0.3, nk_y=16.0, hd_y=4.0, hd_r=6.0, nk1_p=-3.0, nk2_p=0.0, hd_p=5.0, earl_p=25.0, earr_p=5.0,
            tl_lift=80.0, tl_curl=34.0)
BODY = ("pel_x", "pel_f", "pel_r", "sp_r", "sp3_y")
TAIL_EARS = ("tl_lift", "tl_curl", "earl_p", "earl_y", "earr_p")


def _head_rub():
    """stand -> stand (2.5 s), all four paws planted throughout. f0-12 lean in (body left, head and neck turned to the leg, tail up);
    f12-24 push 1; f24-36 back round; f36-48 push 2; f48-58 back; f58-75 into the stand."""
    S = P.STAND; m = M.Tracks(S); keys = list(NECK) + list(BODY) + list(TAIL_EARS)
    for f, pose in ((12, LEAN), (24, PUSH), (36, BACK), (48, PUSH), (58, BACK)):
        m.add(F(f), {k: pose.get(k, S[k]) for k in keys})
    m.add(F(72), _chan(S, *keys)).add(F(75), _chan(S, *keys))
    for f, v in ((24, 0.0), (30, 4.0), (36, -2.0), (42, 4.0), (48, 0.0)): m.add(F(f), tl_side=v)   # the tail tip quivers
    m.add(F(72), tl_side=0.0)
    return m


HEAD_RUB = M.Seq("HeadRub", 75, _head_rub().pose, start="stand", end="stand", group="social",
                 plants={leg: [(0.0, F(75))] for leg in M.LEGS})

SEQS = [RUB_WALK, HEAD_RUB]
