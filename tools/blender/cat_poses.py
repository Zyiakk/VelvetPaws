"""Base postures of the cat (cat_motion channels). STAND is the rig's rest. Start values: refined visually in the animation tasks
(contact sheets of build/velvetpaws/review/anim), every change with a before/after sheet."""
import math

import cat_motion as M
import cat_rig


# ------------------------------------------------------------------------------------------------ body frame (plain Python FK)
def _rot(axis, deg):
    """3x3 rotation about an armature axis (0 x, 1 y, 2 z), degrees, right-handed like mathutils."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == 0: return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == 1: return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def _mul(a, b): return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _app(m, v): return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def _head(bone):
    _, _, (x, y, z), _ = next(b for b in cat_rig.BONES if b[0] == bone)
    return (x * 100, y * 100, z * 100)          # armature space, cm


def ypr(y, p, r):
    """Rz(y) Rx(p) Ry(r) as cat_animlib.ypr, a 3x3 matrix."""
    return _mul(_mul(_rot(2, y), _rot(0, p)), _rot(1, r))


def _frame(pose, leg):
    """(origin, rotation) of the body part a leg rides on, armature space cm: the pelvis for hind legs, spine_03 for fore legs;
    leg "head": the head bone (neck and head turned as cat_animlib.CatRig.solve does)."""
    q = ypr(pose["pel_y"], pose["pel_p"], pose["pel_r"])
    o = _head("pelvis"); pos = (o[0] + pose["pel_x"], o[1] - pose["pel_f"], o[2] + pose["pel_z"]); prev = o

    def _to(name, pos, q, prev):
        h = _head(name); d = _app(q, tuple(h[j] - prev[j] for j in range(3))); return tuple(pos[k] + d[k] for k in range(3)), h
    if leg[0] == "h" and leg != "head": return pos, q, prev
    for i, name in enumerate(("spine_01", "spine_02", "spine_03")):
        pos, prev = _to(name, pos, q, prev)
        q = _mul(_mul(_mul(q, _rot(2, pose["sp%d_y" % (i + 1)])), _rot(0, pose["sp%d_p" % (i + 1)])), _rot(1, pose["sp_r"] / 3.0))
    if leg != "head": return pos, q, prev
    for i, name in enumerate(("neck_01", "neck_02")):
        pos, prev = _to(name, pos, q, prev); q = _mul(_mul(q, _rot(2, pose["nk_y"] / 2.0)), _rot(0, -pose["nk%d_p" % (i + 1)]))
    pos, prev = _to("head", pos, q, prev)
    return pos, _mul(_mul(_mul(q, _rot(2, pose["hd_y"])), _rot(0, pose["hd_p"])), _rot(1, pose["hd_r"])), prev


def body_local(pose, leg, world):
    """Inverse of body_point: the rest-pose point that rides to `world` (anim space cm) in `pose`."""
    pos, q, ref = _frame(pose, leg); qt = tuple(zip(*q))
    d = _app(qt, (world[0] - pos[0], -world[1] - pos[1], world[2] - pos[2]))
    return (ref[0] + d[0], -(ref[1] + d[1]), ref[2] + d[2])


def body_point(pose, leg, local):
    """Where a point that rides with the trunk goes in `pose`, in anim space cm (x left, f forward, z up). local: the point in the
    rest (STAND) anim space. Hind legs ride on the pelvis (rotated by ypr(pel_y, pel_p, pel_r) about its head, plus the pelvis shift);
    fore legs also on the spine (each of spine_01..03 turned about its own head as cat_animlib.CatRig.solve does). Used to author
    paw targets of lying postures in the frame of the body part they belong to. leg "head": a point that rides with the head
    (head_point)."""
    pos, q, ref = _frame(pose, leg)
    d = _app(q, (local[0] - ref[0], -local[1] - ref[1], local[2] - ref[2])); w = tuple(pos[i] + d[i] for i in range(3))
    return (w[0], -w[1], w[2])

def head_point(pose, local):
    """Where a point of the head (rest anim space cm, e.g. MOUTH) goes in `pose`."""
    return body_point(pose, "head", local)


def head_local(pose, world): return body_local(pose, "head", world)


# points of the head in the rest (STAND) anim space, cm (cat_model head: nose tip at f 30, z 25, head-local scaled by HEAD_SCALE): the mouth (lips, just in front of
# the mouth line), the middle of the skull (halfway nose tip - occiput), the right cheek's surface and the base of the right ear
def _head_anim(x, y, z):
    """Head-local cm (cat_model) -> rest anim space cm (x, f = forward, z), with the head's scale (cat_rig.head_pt)."""
    p = cat_rig.head_pt(x, y, z); return (round(p[0] * 100, 3), round(-p[1] * 100, 3), round(p[2] * 100, 3))


MOUTH, HEAD_C, CHEEK_R, EAR_R = _head_anim(0, 0.4, -1.2), _head_anim(0, 5.0, 1.0), _head_anim(-3.9, 4.6, 0.3), _head_anim(-2.6, 6.0, 2.7)

STAND = M.zero_pose()

# Hind legs folded under the haunches of the sit, hocks flat on the floor (_ank -75: the metatarsus lies along the floor), the hind
# paws 10 cm ahead of their stand place (LIE has its own: the level pelvis puts the hips 4 cm further back).
_FOLD = dict(hl_f=3.5, hr_f=3.5, hl_x=4.6, hr_x=-4.6, hl_ank=-75.0, hr_ank=-75.0)   # look pass: 1 cm further in and forward
# SIT: the rump on the floor (pelvis down 12 cm) and the spine in an S as a sitting cat's: the pelvis tipped steeply tail-down (-54),
# the lumbar spine curled forward over it (spine_01 +26: the rounded back above the haunches), the thoracic spine nearly straight
# on that (spine_02/03 -4/-8), so the ribcage stands at 40 deg with the sternum high and the chest front upright. The leg lengths
# keep the hip-to-shoulder chord at about 30 deg; the curve is what reads as sitting. The scapulae turn top-forward (_scap -12):
# the shoulder joints come back and down over the wrists, the fore legs stand straight and vertical under them, the paws together
# (x +-3, a step in from the stand). The neck rises upright (nk +10/+3) and the head is carried high and level (hd_p 58 against
# the chest's and neck's tilt). The tail drops to the floor and lies round her left side towards the paws.
SIT = dict(STAND, pel_f=5.0, pel_z=-12.0, pel_p=-54.0, sp1_p=26.0, sp2_p=-4.0, sp3_p=-8.0, nk1_p=4.0, nk2_p=1.0, hd_p=51.0,
           fl_x=3.0, fr_x=-3.0, fl_scap=-12.0, fr_scap=-12.0, **_FOLD,
           tl_lift=-30.0, tl_side=100.0, tl_wrap=150.0, tl_curl=-10.0)
# look pass: the neck carried lower (nk 4/1, hd_p 51: the head stays level; a shorter, fuller neck over the chest); the hind paws
# (_FOLD) 1 cm further in and forward: beside the fore paws, not poking out sideways
# LIE (sphinx): the trunk low (belly on the floor), the ribcage raised a little on the fore legs (spine pitched front up, the head
# pitched down against it: carried level). Fore legs as a real cat's in the sphinx: the upper arm runs back and down from the shoulder
# to the elbow beside the chest, the forearm lies forward along the floor, the metacarpus flat (_ank -58: the wrist extended, its rest
# tilt of 61 deg taken out) and the digits on their pads (_toe -5), the paws 3.6 cm out from the middle and 19.5 cm forward: ahead of
# the chest, under the chin, so the forearm lies on the floor up to the elbow (paws at 17.5 left the elbow folded up 1.5 cm higher,
# a crumpled flap beside the chest). Hind legs folded flat beside the haunches: the hock straight under the hip (so the knee folds forward
# beside the belly, not up or out), metatarsus flat along the floor (_ank -75), the paws forward under the knees (f -1.6) and only
# 0.4 cm wider than in the sit. The hind paws are not the sit's (_FOLD): LieEnter and LieExit step them. Head up, tail round the side.
_LIE_HIND = dict(hl_f=-1.6, hr_f=-1.6, hl_x=5.0, hr_x=-5.0, hl_ank=-75.0, hr_ank=-75.0)
LIE = dict(STAND, **_LIE_HIND, pel_f=2.0, pel_z=-11.6, pel_p=0.0, sp1_p=-3.0, sp2_p=-6.0, sp3_p=-9.0, nk1_p=0.0, nk2_p=2.0, hd_p=24.0,
           fl_f=19.5, fr_f=19.5, fl_z=0.0, fr_z=0.0, fl_x=3.6, fr_x=-3.6,
           fl_ank=-58.0, fr_ank=-58.0, fl_toe=-5.0, fr_toe=-5.0, tl_lift=-35.0, tl_side=90.0, tl_wrap=120.0, tl_curl=0.0)
# (before 2026-11-14 the loaf tucked the fore paws under the chest, wrist curled back 125 and digits 140: in the game the paws pointed
# back into the floor and vanished, the calf stood up beside the haunch and the hind paw poked out sideways)


def _sleep():
    """SLEEP: rolled onto her right side (pel_r -80), the spine curled (16 deg per bone: the C of a sleeping cat), the head resting on
    the floor turned back up a little (hd_r), ears relaxed; the tail lies on the floor curling round towards the hind paws. The paws
    are authored in the frame of the body part they belong to (body_point of an offset from REST_PAW, cm in the rest pose): the lower
    right legs lie half stretched on the floor (paw tip 1.3 cm up: the side of the paw rests on the floor), the upper left legs are drawn
    in towards the body (x -6/-8: across onto the lower legs) and a little bent. The paws roll with the body (_roll = pel_r)."""
    d = dict(STAND, pel_f=2.0, pel_z=-9.6, pel_r=-80.0, sp1_p=16.0, sp2_p=16.0, sp3_p=16.0, nk1_p=-18.0, nk2_p=-10.0, hd_p=20.0,
             hd_r=28.0, earl_p=15.0, earr_p=15.0, tl_side=-100.0, tl_wrap=180.0, tl_curl=-15.0)
    legs = {"hr": (0.0, 4.0, 3.0, 15.0, 0.0), "fr": (0.0, 5.0, 3.0, 10.0, 0.0),            # (dx, df, dz) from REST_PAW, _ank, _toe
            "hl": (-8.0, 6.0, 6.0, 30.0, 10.0), "fl": (-6.0, 1.0, 6.0, 40.0, 15.0)}
    for leg, (dx, df, dz, ank, toe) in legs.items():
        x, f, z = body_point(d, leg, (M.REST_PAW[leg][0] + dx, M.REST_PAW[leg][1] + df, M.REST_PAW[leg][2] + dz))
        d.update({leg + "_x": round(x, 3), leg + "_f": round(f, 3), leg + "_z": 1.3 if leg[1] == "r" else round(max(z, 2.5), 3),
                  leg + "_ank": ank, leg + "_toe": toe, leg + "_roll": d["pel_r"]})
    return d


SLEEP = _sleep()
def _sym(**kw):
    """h_<c> / f_<c> set both hind / fore legs (x mirrored for the right)."""
    d = {}
    for k, v in kw.items():
        if k[:2] in ("h_", "f_"):
            for s in "lr": d[k[0] + s + k[1:]] = -v if s == "r" and k.endswith("_x") else v
        else: d[k] = v
    return d


# Jumps (cat_anim_jump.py). CROUCH: loaded for the jump at 0.45 s: the haunches low (pelvis -6.5 cm), the front a little higher
# (nose up 4), hocks lowered (_ank -40), elbows bent, the neck raised and the head tipped up: the eyes on the target; tail low.
CROUCH = dict(STAND, **_sym(pel_z=-6.5, pel_p=-4.0, pel_f=-1.0, sp1_p=3.0, sp2_p=1.0, nk1_p=16.0, nk2_p=8.0, hd_p=-8.0,
                            earl_p=-6.0, earr_p=-6.0, h_ank=-40.0, f_ank=-15.0, tl_lift=5.0, tl_curl=15.0))
# EXTEND: the launch (last frame with the hind paws on the floor): the trunk pitched nose up 16, carried forward over the hind paws,
# which stand on their toes (heels high, _ank 55), the fore legs already reaching forward and up, head forward, tail lifted behind.
EXTEND = dict(STAND, **_sym(pel_z=-0.5, pel_p=-16.0, pel_f=5.0, sp1_p=-4.0, sp2_p=-4.0, sp3_p=-3.0, nk1_p=4.0, nk2_p=2.0, hd_p=4.0,
                            h_ank=55.0, h_toe=0.0, f_x=3.5, f_f=23.0, f_z=13.0, f_ank=25.0, f_toe=20.0, tl_lift=50.0, tl_curl=15.0))
# AIR: the flight: trunk a little nose up (9) and stretched, fore legs reaching forward (paws 22.5 cm ahead, wrists soft), hind legs drawn
# in under the hips (heels up, toes pointed), tail straight out behind (the rudder), head level looking ahead.
AIR = dict(STAND, **_sym(pel_z=2.0, pel_p=-9.0, sp1_p=-2.0, sp2_p=-2.0, sp3_p=-1.0, nk1_p=0.0, hd_p=9.0,
                         h_x=4.0, h_f=-11.0, h_z=7.0, h_ank=50.0, h_toe=30.0, f_x=3.5, f_f=22.5, f_z=8.5, f_ank=25.0, f_toe=15.0,
                         tl_lift=50.0, tl_curl=12.0))
# AIR_DOWN: the flight of a jump down: the body as AIR, the neck lowered and the head pitched down (about 30 deg nose down in the
# world) at the landing spot below and ahead, as DROP leaves it; ears forward.
AIR_DOWN = dict(AIR, nk1_p=-10.0, nk2_p=-4.0, hd_p=28.0)
# LANDED: the deepest absorb of a landing (all four paws on the stand's places): body low (-4.5), elbows and hocks bent, head low.
LANDED = dict(STAND, **_sym(pel_z=-4.5, pel_p=1.0, sp1_p=3.0, sp2_p=2.0, sp3_p=1.0, nk1_p=-4.0, hd_p=-2.0, h_ank=-30.0, f_ank=-12.0,
                            tl_lift=15.0))
# DROP: leaning over an edge to jump down: chest down and forward (pelvis nose down 8), the head looking down at the landing spot,
# the fore paws off the floor reaching forward and low, the hind heels up to push.
DROP = dict(STAND, **_sym(pel_z=0.0, pel_p=8.0, pel_f=3.0, sp1_p=1.0, sp2_p=1.0, sp3_p=1.0, nk1_p=-2.0, nk2_p=0.0, hd_p=26.0,
                          h_ank=35.0, h_toe=0.0, f_f=26.0, f_z=4.0, f_ank=15.0, f_toe=5.0, tl_lift=20.0))

# GAIT: base of the gaits (Task 3 builds Walk/Trot/Run on it). The fore body carries 1.25 cm lower than the rest (pelvis -0.5 cm,
# tipped 1.5 deg nose down, ribcage 1 deg), the elbows flex from 159 to 121 deg: the fore legs get the slack a cat walks with; the
# neck lifts back 3 deg so the head only follows the chest. With the scapula of cat_animlib the fore paws reach +-8 cm (cat_probe).
GAIT = dict(STAND, pel_z=-0.5, pel_p=1.5, sp2_p=1.0, nk1_p=3.0, hd_p=-1.0)

POSES = {"stand": STAND, "gait": GAIT, "sit": SIT, "lie": LIE, "sleep": SLEEP, "crouch": CROUCH, "air": AIR, "air_down": AIR_DOWN}
