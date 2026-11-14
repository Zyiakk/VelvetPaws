"""Bones of the VelvetPaws cat in Blender space (metres, cat faces -Y, floor at z=0) and the skin radii of the body
loft (head and ears are modelled separately). Plain Python: cat_model.py builds the armature and body from it, tests
check the proportions.
Head-body ~46 cm (nose to rump), shoulder ~25 cm, tail ~29 cm."""

NOSE_Y = -0.30        # tip of the nose
NOSE_Z = 0.25         # height of the nose tip (cat_model.HEAD_AT)
HEAD_SCALE = 1.10     # the head (cat_model: head field, ears, eyes, mouth) is modelled in head-local cm and scaled about the nose tip


def head_pt(x, y, z):
    """Head-local cm (x lateral, y back from the nose tip, z up) -> armature metres, with HEAD_SCALE about the nose tip."""
    return (round(HEAD_SCALE * x / 100, 5), round(NOSE_Y + HEAD_SCALE * y / 100, 5), round(NOSE_Z + HEAD_SCALE * z / 100, 5))


# (name, parent, head, tail)
_CENTRE = [
    ("root", None, (0, 0, 0), (0, -0.05, 0)),
    ("pelvis", "root", (0, 0.11, 0.165), (0, 0.06, 0.175)),
    ("spine_01", "pelvis", (0, 0.06, 0.175), (0, -0.01, 0.182)),
    ("spine_02", "spine_01", (0, -0.01, 0.182), (0, -0.07, 0.185)),
    ("spine_03", "spine_02", (0, -0.07, 0.185), (0, -0.13, 0.188)),
    ("neck_01", "spine_03", (0, -0.13, 0.188), (0, -0.165, 0.225)),
    ("neck_02", "neck_01", (0, -0.165, 0.225), (0, -0.19, 0.255)),
    ("head", "neck_02", (0, -0.19, 0.255), (0, -0.28, 0.25)),
    ("jaw", "head", head_pt(0, 6.3, -1.25), head_pt(0, 2.5, -2.8)),     # hinge under the back of the cheek (was y 8.5: a boxy gape)
]
# the tail hangs: down and back from the rump, steepest in the middle, the tip curling back up above the floor
# (segment angles below horizontal, degrees; 8 segments of 3.6 cm)
_TAIL_DROP = (25, 40, 55, 60, 50, 30, 5, -20)


def _tail():
    import math
    out, p = [], (0, 0.14, 0.165)
    for i, a in enumerate(_TAIL_DROP):
        r = math.radians(a); q = (0, round(p[1] + 0.036 * math.cos(r), 4), round(p[2] - 0.036 * math.sin(r), 4))
        out.append(("tail_%02d" % (i + 1), "pelvis" if i == 0 else "tail_%02d" % i, p, q)); p = q
    return out


_TAIL = _tail()
# left side (x > 0); right side mirrored below. ear_l: head = modelled ear base (cat_model.EAR["base"], head-local),
# tail 4 cm along the ear axis (out 28 deg, forward tilt 8 deg)
_LEFT = [
    ("ear_l", "head", head_pt(2.6, 6.0, 2.7), head_pt(4.5, 5.4, 6.2)),
    ("thigh_l", "pelvis", (0.045, 0.10, 0.15), (0.05, 0.06, 0.10)),
    ("calf_l", "thigh_l", (0.05, 0.06, 0.10), (0.05, 0.105, 0.045)),
    ("foot_l", "calf_l", (0.05, 0.105, 0.045), (0.05, 0.095, 0.012)),
    ("toe_l", "foot_l", (0.05, 0.095, 0.012), (0.05, 0.065, 0.0)),
    ("scapula_l", "spine_03", (0.04, -0.095, 0.195), (0.045, -0.12, 0.14)),
    ("upperarm_l", "scapula_l", (0.045, -0.12, 0.14), (0.045, -0.11, 0.08)),
    ("lowerarm_l", "upperarm_l", (0.045, -0.11, 0.08), (0.045, -0.12, 0.03)),
    ("hand_l", "lowerarm_l", (0.045, -0.12, 0.03), (0.045, -0.13, 0.012)),
    ("finger_l", "hand_l", (0.045, -0.13, 0.012), (0.045, -0.155, 0.0)),
]


def _mirror(b):
    name, parent, (hx, hy, hz), (tx, ty, tz) = b
    return name[:-2] + "_r", parent[:-2] + "_r" if parent.endswith("_l") else parent, (-hx, hy, hz), (-tx, ty, tz)


BONES = _CENTRE + _TAIL + _LEFT + [_mirror(b) for b in _LEFT]

# skin radius at each bone's head (metres); the body is skinned around these, head and ears are built separately
SKIN = {"pelvis": 0.052, "spine_01": 0.058, "spine_02": 0.062, "spine_03": 0.06, "neck_01": 0.045, "neck_02": 0.038,
        "thigh_l": 0.032, "calf_l": 0.02, "foot_l": 0.013, "toe_l": 0.014,
        "scapula_l": 0.03, "upperarm_l": 0.024, "lowerarm_l": 0.016, "hand_l": 0.012, "finger_l": 0.013}
SKIN.update({"tail_%02d" % (i + 1): 0.017 - 0.001 * i for i in range(8)})
SKIN.update({k[:-2] + "_r": v for k, v in list(SKIN.items()) if k.endswith("_l")})
SKIN_TALL = 1.05      # skin is this much taller than wide (only used by shoulder_height)
TAIL_R = (0.0153, 0.0078)    # tail skin radius at the root (tail_01 head) and the tip of the linear profile (metres), before root and tip
TAIL_TAPER = (0.03, 0.25)    # the last 3 cm narrow to 25 % (a pointed dark tip, no blunt club)
# round 6: the root is a little wider and blends into the rump over its first 6 cm (+5 mm radius at tail_01's head, fading
# with (1 - s/len)^2, no edge where it ends); before, the tube met the rump at full thinness and the fillet left a short collar
TAIL_ROOT = (0.005, 0.06)


def tail_radius_at(s):
    """Tail skin radius (metres) at arc length s (metres) from tail_01's head along the chain (s < 0: inside the rump, the root
    radius): linear root -> tip, plus the root flare (TAIL_ROOT), the last TAIL_TAPER[0] narrowing to TAIL_TAPER[1] of that as a
    dome (1 - t^2), so the tip ends in a point."""
    n = tail_length(); f = max(0.0, min(1.0, s / n))
    r = TAIL_R[0] + (TAIL_R[1] - TAIL_R[0]) * f
    r += TAIL_ROOT[0] * max(0.0, 1 - max(s, 0.0) / TAIL_ROOT[1]) ** 2
    t = max(0.0, (s - (n - TAIL_TAPER[0])) / TAIL_TAPER[0])
    return r * (1 - (1 - TAIL_TAPER[1]) * t * t)


def tail_radius(f):
    """tail_radius_at at f = 0 (base) .. 1 (tip) of the chain. cat_model lofts the tail with it, cat_animlib keeps the tail bones this
    far (plus a margin) above the floor."""
    return tail_radius_at(f * tail_length())


def tail_length():
    """Arc length of the tail bone chain (metres)."""
    import math
    return sum(math.dist(b[2], b[3]) for b in _TAIL)


def _bone(name): return next(b for b in BONES if b[0] == name)


def body_length():
    """Nose tip to rump (back of the pelvis skin)."""
    _, _, (_, py, _), _ = _bone("pelvis")
    return (py + SKIN["pelvis"]) - NOSE_Y


def shoulder_height():
    """Withers: highest skin top over the shoulder (bone head z + skin radius, skin taller than wide)."""
    return max(_bone(b)[2][2] + SKIN[b] * SKIN_TALL for b in ("spine_02", "spine_03", "scapula_l"))
