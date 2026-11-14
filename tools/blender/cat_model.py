"""Builds the VelvetPaws cat: armature from cat_rig.BONES; trunk, legs, tail and head as lofts of cross-section
profiles, paws, facial features and ears as own shells, all fused through signed distance fields (seams filleted, eye
sockets and lids cut); eyes, fur cards, UVs, weights; exports build/velvetpaws/cat.fbx (+ cat.blend for the bake).
Self-checks and prints CAT OK.
Usage: blender -b --factory-startup --python-exit-code 1 --python tools/blender/cat_model.py -- <out_dir>"""
import math, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(__file__))
import cat_rig

TARGET_TRIS = 12000
MAX_INFLUENCES = 4
ARMATURE_NODE = "Armature"     # FBX name of the armature object; UE skips a null of this name (FbxMainImport.cpp GetRootSkeleton)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def build_armature():
    data = bpy.data.armatures.new("root"); arm = bpy.data.objects.new("root", data)
    bpy.context.scene.collection.objects.link(arm); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail in cat_rig.BONES:
        b = data.edit_bones.new(name); b.head = head; b.tail = tail
        if parent: b.parent = data.edit_bones[parent]; b.use_connect = False
        b.use_deform = name != "root"
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def _new_obj(name, me):
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); return o


def _bone(name):
    return next(b for b in cat_rig.BONES if b[0] == name)


# ---------------------------------------------------------------------------------------------------------------------
# Lofts: a surface through cross-section rings along a centre line. Each ring is a superellipse in the plane across the
# line (x = lateral, u = "up" for the trunk and head, "front" for the legs), with its own half width, upper and lower
# extent, exponents (2 = ellipse, more = boxier), egg (> 0 wider at the top) and bumps (angle from +x towards u,
# angular width, outward push; shoulder blades and the like). Ends get rounded caps.

RING = 48


def _adiff(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _section(p, x, u, w, up, down, n_up=2.0, n_down=2.0, egg=0.0, bumps=(), side=1):
    out = []
    for k in range(RING):
        a = 2 * math.pi * k / RING; c, s = math.cos(a), math.sin(a)
        n, h = (n_up, up) if s >= 0 else (n_down, down)
        px = w * math.copysign(abs(c) ** (2 / n), c)
        pz = h * math.copysign(abs(s) ** (2 / n), s)
        px *= 1 + egg * pz / h
        d = Vector((px, pz)); L = d.length
        for ac, aw, amt in bumps:
            for aa in ((ac, 180 - ac) if side == 0 else (ac,)):
                d += d / L * amt * math.exp(-(_adiff(a, math.radians(aa)) / math.radians(aw)) ** 2)
        out.append(p + x * d.x + u * d.y)
    return out


def _loft(name, stations, frame=None, caps=(0.8, 0.8), side=1):
    """stations: (centre, half width, up, down, options). frame: fixed (x, u) for vertical rings (trunk, head), else
    rings stand across the centre line. caps: depth of the rounded end caps as a fraction of the end ring size."""
    P = [Vector(s[0]) for s in stations]
    rings, frames = [], []
    for i, (c, w, up, down, o) in enumerate(stations):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        if frame: x, u = (Vector(v) for v in frame)
        else:
            x = Vector((1, 0, 0)); x = (x - t * x.dot(t)).normalized(); u = t.cross(x)
        frames.append((t, x, u)); rings.append(_section(P[i], x, u, w, up, down, side=side, **o))
    def cap(i, sign, depth):
        c, w, up, down, o = stations[i]; t, x, u = frames[i]
        depth *= min(w, (up + down) / 2); res = []
        for phi in (15, 30, 45, 60, 75):
            f = math.radians(phi)
            sc = dict(o); sc.pop("bumps", None)
            res.append(_section(P[i] + t * sign * depth * math.sin(f), x, u, w * math.cos(f), up * math.cos(f),
                                down * math.cos(f), side=side, **sc))
        return res, P[i] + t * sign * depth
    head_rings, head_tip = cap(0, -1, caps[0]); tail_rings, tail_tip = cap(len(stations) - 1, 1, caps[1])
    allr = head_rings[::-1] + rings + tail_rings
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in r] for r in allr]
    for a, b in zip(vr, vr[1:]):
        for k in range(RING):
            bm.faces.new((a[k], a[(k + 1) % RING], b[(k + 1) % RING], b[k]))
    t0, t1 = bm.verts.new(head_tip), bm.verts.new(tail_tip)
    for k in range(RING):
        bm.faces.new((t0, vr[0][(k + 1) % RING], vr[0][k])); bm.faces.new((t1, vr[-1][k], vr[-1][(k + 1) % RING]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return _new_obj(name, me)


def _blob(centre, radii, axis=(0, 0, 1), name="blob", segments=32, rings=20):
    """An ellipsoid: radii (x, y, z) in its own frame, its z axis turned onto `axis`; vertices in world space."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=centre)
    o = bpy.context.active_object; o.name = name; o.scale = radii
    o.rotation_mode = "QUATERNION"; o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized())
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def _join(objs, name):
    for o in objs: _apply_all(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]; bpy.ops.object.join(); objs[0].name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return objs[0]


def _mirror(stations):
    return [((-c[0], c[1], c[2]), w, up, down, o) for c, w, up, down, o in stations]


# trunk, vertical rings from the rump to the neck end (inside the head): (y, top z, bottom z, half width, options).
# Deep narrow chest with shoulder-blade tops, ribs, a tucked flank in front of the thighs, hips, rump; the neck rises
# to the back of the head and is as wide there as the skull. Look pass: the chest front deeper and rounder, the neck
# thicker (a sitting cat's chest and neck read as one full mass, not a tube).
_SCAP = ((62, 16, 0.0060),)
TRUNK = [
    (0.134, 0.203, 0.152, 0.029, {"egg": 0.04}),
    (0.122, 0.218, 0.138, 0.040, {"egg": 0.05}),
    (0.108, 0.229, 0.124, 0.046, {"egg": 0.04}),
    (0.075, 0.233, 0.132, 0.047, {}),
    (0.040, 0.233, 0.127, 0.048, {"n_down": 2.2}),
    (0.005, 0.230, 0.112, 0.050, {}),
    (-0.030, 0.232, 0.101, 0.052, {"egg": 0.06, "n_down": 1.9}),
    (-0.062, 0.239, 0.096, 0.052, {"egg": 0.12, "n_down": 1.75, "bumps": _SCAP}),
    (-0.092, 0.245, 0.096, 0.049, {"egg": 0.16, "n_down": 1.7, "bumps": _SCAP}),
    (-0.120, 0.245, 0.098, 0.048, {"egg": 0.08, "n_down": 1.85, "bumps": ((62, 16, 0.003),)}),
    (-0.144, 0.246, 0.107, 0.051, {"egg": -0.04, "n_down": 1.9}),
    (-0.165, 0.253, 0.127, 0.050, {"egg": -0.06}),
    (-0.184, 0.261, 0.150, 0.046, {"egg": -0.04}),
    (-0.202, 0.265, 0.178, 0.037, {}),
]
# legs (left side; rings across the leg; "up" is the front of the leg): (centre, half width, front, back, options).
# The centre line follows the middle of the muscle mass, not the bones. Fore: shoulder and upper arm blend into the
# chest, triceps and elbow point, forearm, slim wrist, carpal bump. Hind: thigh wide from the flank fold to the
# hamstrings, narrowing past the stifle into the calf, a clear hock (heel point), slim metatarsus.
FORELEG = [
    ((0.025, -0.108, 0.192), 0.019, 0.028, 0.028, {}),
    ((0.033, -0.114, 0.150), 0.020, 0.029, 0.031, {}),
    ((0.039, -0.110, 0.116), 0.019, 0.021, 0.029, {}),
    ((0.043, -0.109, 0.088), 0.0160, 0.0160, 0.0215, {}),
    ((0.044, -0.113, 0.062), 0.0138, 0.0140, 0.0140, {}),
    ((0.045, -0.118, 0.038), 0.0115, 0.0112, 0.0112, {}),
    ((0.045, -0.122, 0.023), 0.0122, 0.0118, 0.0132, {}),
    ((0.045, -0.127, 0.014), 0.0128, 0.0120, 0.0120, {}),
]
HINDLEG = [
    ((0.020, 0.102, 0.190), 0.020, 0.038, 0.040, {}),
    ((0.031, 0.096, 0.152), 0.022, 0.044, 0.044, {}),
    ((0.037, 0.091, 0.122), 0.020, 0.037, 0.034, {}),
    ((0.043, 0.092, 0.098), 0.0175, 0.026, 0.030, {}),
    ((0.046, 0.096, 0.077), 0.0150, 0.0135, 0.0225, {}),
    ((0.048, 0.101, 0.060), 0.0125, 0.0105, 0.0150, {}),
    ((0.049, 0.105, 0.045), 0.0110, 0.0098, 0.0130, {}),
    ((0.050, 0.101, 0.030), 0.0105, 0.0100, 0.0100, {}),
    ((0.050, 0.097, 0.017), 0.0112, 0.0110, 0.0100, {}),
]
# paws: (centre, radii) of the pad body, toes in an arc in front
FOREPAW = ((0.045, -0.137, 0.0080), (0.0160, 0.0185, 0.0098))
HINDPAW = ((0.050, 0.082, 0.0080), (0.0148, 0.0175, 0.0095))


def _paw(centre, radii, side):
    c = Vector(centre); c.x *= side; rx, ry, rz = radii
    out = [_blob(c, radii, name="paw")]
    for k, f in enumerate((-1.0, -0.36, 0.36, 1.0)):
        p = c + Vector((f * rx * 0.66, -ry * (0.78 - 0.16 * abs(f)), -rz * 0.30))
        out.append(_blob(p, (rx * 0.37, ry * 0.40, rz * 0.66), name="toe"))
    return out


def _tail():
    """The tail loft along the bone chain; the last bone is sampled every ~6 mm so the tip taper (cat_rig.tail_radius) is
    round, not a few long cones."""
    pts = [Vector((0, 0.104, 0.196))] + [Vector(b[2]) for b in cat_rig.BONES if b[0].startswith("tail_")]
    a, b = Vector(_bone("tail_08")[2]), Vector(_bone("tail_08")[3]); n = 6
    pts += [a + (b - a) * (k / n) for k in range(1, n + 1)]
    lengths = [0.0]
    for p, q in zip(pts, pts[1:]): lengths.append(lengths[-1] + (q - p).length)
    st = []
    for p, l in zip(pts, lengths):
        r = cat_rig.tail_radius_at(l - lengths[1])          # arc length from tail_01's head (the first point is inside the rump)
        st.append((p, r, r, r, {}))
    return _loft("tail", st, caps=(0.5, 1.0))


def build_body(arm):
    """Trunk, legs, paws and tail as lofts of cross-section rings (separate shells, fused in finish())."""
    parts = [_loft("trunk", [((0, y, (t + b) / 2), w, (t - b) / 2, (t - b) / 2, o) for y, t, b, w, o in TRUNK],
                   frame=((1, 0, 0), (0, 0, 1)), caps=(1.0, 0.3), side=0)]   # deep round rump cap (no flat end)
    for side in (1, -1):
        for st, paw in ((FORELEG, FOREPAW), (HINDLEG, HINDPAW)):
            parts.append(_loft("leg", st if side > 0 else _mirror(st), caps=(0.6, 0.6)))
            parts += _paw(*paw, side)
    parts.append(_tail())
    return _join(parts, "body")


# ---------------------------------------------------------------------------------------------------------------------
# Head: anatomical masses as analytic signed distance functions, blended with smooth minimum (each mass with its own
# blend radius, like clay pressed together), grooves, nostrils and the lid openings carved with smooth maximum; the
# field is sampled on a grid (numpy) and turned into a closed mesh by surface nets. Head-local centimetres: x lateral
# (+ = the cat's left), y backwards from the nose tip, z up from the nose tip; HEAD_AT is the nose tip in the world.
# Width across the cheeks about 7.5 cm, nose tip to occiput about 9.3 cm, crown 4.3 cm above the nose tip.
HEAD_AT = (0.0, cat_rig.NOSE_Y, cat_rig.NOSE_Z)
HS = cat_rig.HEAD_SCALE     # head-local cm are scaled by this about the nose tip (_hp, _local)
HEAD_STEP = 0.05           # grid step, cm
HEAD_BOX = ((-4.8, 4.8), (-1.0, 11.2), (-6.4, 5.4))


def _hp(p):
    return Vector((HEAD_AT[0] + HS * p[0] / 100, HEAD_AT[1] + HS * p[1] / 100, HEAD_AT[2] + HS * p[2] / 100))


# masses: (name, centre, (x, front, back, up, down) half extents, rotation (deg about x, y, z), blend radius, pair).
# Rotation about x > 0 lifts the back end. pair = also mirrored to the right side. Blended in this order.
HEAD_MASSES = [
    ("cranium", (0, 6.0, 2.1), (3.0, 2.8, 2.8, 2.2, 2.2), (0, 0, 0), 0, False),
    ("occiput", (0, 7.6, 1.3), (2.85, 1.8, 1.9, 2.2, 2.2), (0, 0, 0), 1.0, False),
    ("forehead", (0, 4.0, 2.05), (2.7, 2.8, 2.4, 1.3, 1.3), (35, 0, 0), 1.0, False),
    ("face", (0, 3.8, 0.4), (2.6, 2.3, 2.5, 1.7, 1.9), (0, 0, 0), 1.0, False),
    ("cheek", (2.45, 4.6, 0.25), (1.45, 1.9, 2.0, 1.5, 1.6), (0, 0, 0), 1.0, True),
    ("jowl", (1.85, 3.3, -0.55), (1.3, 1.4, 1.6, 1.1, 1.1), (0, 0, 0), 1.0, True),
    ("jaw", (0, 5.0, -0.8), (2.3, 3.0, 3.0, 1.4, 1.4), (-8, 0, 0), 1.0, False),
    ("neck", (0, 8.7, -1.2), (2.7, 2.2, 2.4, 2.6, 2.1), (0, 0, 0), 1.4, False),
    ("throat", (0, 7.0, -2.5), (2.2, 3.2, 3.0, 0.9, 0.9), (-36, 0, 0), 1.6, False),
    ("brow", (1.75, 3.05, 2.8), (1.1, 0.85, 1.0, 0.55, 0.5), (0, 0, 0), 0.6, True),
    ("muzzle", (0, 1.95, -0.1), (1.9, 1.45, 1.6, 1.25, 1.1), (0, 0, 0), 0.8, False),
    ("bridge", (0, 1.28, 0.95), (0.7, 0.9, 0.9, 0.5, 0.45), (42, 0, 0), 0.5, False),
    ("pad", (0.72, 0.9, -0.36), (0.72, 0.72, 0.72, 0.72, 0.72), (0, 0, 0), 0.3, True),
    ("chin", (0, 1.85, -1.56), (0.92, 0.80, 2.0, 0.56, 0.70), (0, 0, 0), 0.45, False),    # a round chin, the front of the lower jaw
    # the two halves of the lower jaw (mandible bodies) under the lip line, diverging backwards: the lower jaw is a solid U, not
    # the thin underside of the jowls (open, it read as a plate)
    ("mandible", (1.15, 3.7, -1.78), (0.62, 2.1, 2.5, 0.66, 0.52), (0, 0, -12), 0.5, True),
]
# nose leather: inverted triangle, top corners and bottom tip (x, z), front at y = 0 leaning back to the top, blend
NOSE = dict(top=0.82, half=0.55, tip=0.12, lean=0.32, round=0.07, blend=0.07)
# carved: (points, radius, blend, pair) tubes; nostrils (centre, radii, blend), mirrored
GROOVES = [
    ([(0, 0.15, 0.10), (0, 0.40, -0.50), (0, 0.50, -1.00)], 0.10, 0.12, False),                       # philtrum
    ([(0, 0.55, -1.05), (0.55, 0.90, -1.17), (1.2, 1.55, -1.10), (1.8, 2.45, -0.90)], 0.13, 0.12, True),  # mouth line
]
NOSTRIL = ((0.22, -0.12, 0.30), (0.14, 0.12, 0.09), 0.06)
STOP = ((0, 1.35, 1.95), (1.0, 0.35, 0.35, 0.28, 0.28), 0.45)     # soft notch where the bridge meets the forehead

# Mouth (head-local cm). The fused shell is cut by a closed lens ("cutter"): a thin slit along the mouth plane whose
# middle surface z = MOUTH_Z(y) falls from under the whisker pads to the corners, as wide as MOUTH_W(y) (beyond the skin
# up to the corners, MOUTH_CORNER), bulging into a cavity (MOUTH_CAV ellipse in plan) behind the lips. After the cut the
# slit walls are pressed together (MOUTH_SHUT apart), so the closed mouth shows only the lip line; the cavity stays.
MOUTH_Z = ((-1.0, -1.06), (1.0, -1.08), (1.6, -1.15), (2.0, -1.27), (2.4, -1.40), (2.8, -1.48), (3.3, -1.53),
           (4.5, -1.56), (7.0, -1.60))      # under the whisker pads, then along the underside of the jowls
MOUTH_W = ((-1.0, 1.7), (1.4, 1.7), (2.0, 2.3), (2.4, 2.8), (2.8, 3.2), (3.2, 3.5), (3.7, 3.6), (3.95, 2.95), (4.2, 1.6),
           (4.21, 0.0))               # well outside the skin up to the corners (a thin lens there would not open cleanly)
MOUTH_CORNER = 3.9           # y of the mouth corners (where the outline goes inside the skin), under the eye's rear third
MOUTH_T = 0.06               # half gap of the slit as cut
MOUTH_SHUT = 0.003           # half gap left between the lips after closing
MOUTH_LIP = 0.20             # cut faces this close to the closed skin (cm) are the lip margin (dark, rolling in)
MOUTH_SEEN = 0.09            # and those this close to (or outside) the skin once shut (a slit wall where the cut grazed the
                             # skin lies up to MOUTH_T under it with no skin left over it): they would show at rest
MOUTH_CAV = dict(y=3.9, ax=1.15, ay=2.5, up=0.75, down=0.22, ax_down=0.80, down_u=0.18)
# lower floor: a trough between the lower tooth rows (ax_down wide, down_u deep), the tongue lies in it (the open jaw is a U)
MOUTH_GRID = (44, 22)        # cutter rows along y, columns per side
# Beside the lower jaw the slit turns down (MOUTH_DROP deep from MOUTH_XM(y) outwards): the upper lip (jowl) hangs over the
# outside of the narrower mandible and stays on the head, so the open lower jaw is a narrow U, not a shelf as wide as the cheeks
MOUTH_XM = ((1.4, 0.9), (2.4, 1.35), (3.9, 1.65), (7.0, 1.9))     # (y, x where the turn starts)
MOUTH_DROP = ((1.8, 0.0), (2.6, 0.30), (7.0, 0.32))              # (y, depth of the turn)
MOUTH_DROP_W = 0.55                                               # width of the turn (x)
# teeth: (base, tip, radius, lateral flattening, bend, jaw?) head-local cm, the left ones mirrored. Roots sit in the solid
# or the cavity wall; with the mouth shut every tooth stays inside the closed head (checked).
TEETH = [((0.55, 2.00, -0.98), (0.55, 2.12, -1.72), 0.115, 0.85, (0, -0.06, 0), False),     # upper canine
         ((0.45, 1.68, -1.58), (0.47, 1.64, -0.96), 0.090, 0.85, (0, -0.04, 0), True),      # lower canine
         ((0.95, 2.55, -1.10), (0.97, 2.58, -1.60), 0.075, 0.45, (0, 0, 0), False),         # upper premolars
         ((0.98, 2.95, -1.15), (1.00, 2.98, -1.70), 0.095, 0.40, (0, 0, 0), False),         # upper carnassial
         ((0.86, 2.75, -1.68), (0.86, 2.77, -1.36), 0.070, 0.45, (0, 0, 0), True),          # lower premolar
         ((0.88, 3.20, -1.72), (0.88, 3.22, -1.34), 0.090, 0.40, (0, 0, 0), True)]          # lower carnassial
INCISORS = [((x, 1.36 + 0.25 * x * x, -0.98), (x, 1.40 + 0.25 * x * x, -1.18), 0.045) for x in (0.08, 0.20, 0.32)] + \
           [((x, 1.55 + 0.25 * x * x, -1.40), (x, 1.53 + 0.25 * x * x, -1.12), 0.048) for x in (0.07, 0.19, 0.31)]
TONGUE = dict(y0=2.2, y1=5.3, w=0.62, tip_w=0.40, thick=0.32, top=0.09, groove=0.035, curl=0.03, trough=0.8)
# cheek membranes along the side opening (cm): from y0 to y1, `inset` inside the skin, rows from the upper lip (head)
# to the lower (jaw); `round`: the rows next to the lips sit this far further in (a rounded web, no square corner);
# `recede`: the free front edge lies this far further back at mid height (the commissure curves back to the corner)
# `y1`: back end, where the slit ends (no view through the corners); `xm`: never further out than MOUTH_XM + xm (on the flat
# slit beside the mandible, inside the turn under the upper lip)
CHEEK = dict(y0=2.0, y1=4.12, inset=0.40, round=0.65, recede=0.45, rows=8, cols=12, xm=0.05)
# mouth vertex colours (sRGB): lip edge, gums/palate, throat, tongue
MOUTH_COL = dict(lip=(0.055, 0.048, 0.048), gum=(0.56, 0.30, 0.32), throat=(0.30, 0.12, 0.14), tongue=(0.86, 0.50, 0.52))

EYE_R = 0.0095
EYE_AT = (1.80, 3.2, 2.1)   # left eye centre, head-local cm (3.6 cm apart)
EYE_GAZE = 12               # degrees outward from straight ahead
EYE_LID = 0.08              # lid thickness around the eyeball, cm (look pass 2: thinner, the ball sits nearly flush)
EYE_LID_FWD = 0.04          # the lid sphere sits this far in front of the eye centre (ball slightly recessed), cm
EYE_OPEN = (0.95, 0.47, 0.57, 12)    # almond: half width, upper / lower half height (cm), outer corner up (deg)
EYE_BLEND = (0.25, 0.55, 0.10)       # room in front of the ball, lid, opening


def _gaze(side):
    a = math.radians(EYE_GAZE); return Vector((side * math.sin(a), -math.cos(a), -0.03)).normalized()


def _eye_frame(g, side):
    h = Vector((side, 0, 0)); h = (h - g * h.dot(g)).normalized(); return h, g.cross(h) * side


def _smin(a, b, k):
    if k <= 0: return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0) / k; return np.minimum(a, b) - h * h * k * 0.25


def _smax(a, b, k):
    return -_smin(-a, -b, k)


def _sd_ellipsoid(P, c, r, rot=(0, 0, 0)):
    """Approximate distance to an ellipsoid with its own extent per half (x, front, back, up, down)."""
    M = np.array(Euler([math.radians(a) for a in rot], "XYZ").to_matrix(), dtype=np.float32)
    L = (P - np.asarray(c, np.float32)) @ M                       # into the mass's frame (M^T p)
    rx = np.float32(r[0]); ry = np.where(L[..., 1] < 0, r[1], r[2]).astype(np.float32)
    rz = np.where(L[..., 2] > 0, r[3], r[4]).astype(np.float32)
    k0 = np.sqrt((L[..., 0] / rx) ** 2 + (L[..., 1] / ry) ** 2 + (L[..., 2] / rz) ** 2)
    k1 = np.sqrt((L[..., 0] / rx ** 2) ** 2 + (L[..., 1] / ry ** 2) ** 2 + (L[..., 2] / rz ** 2) ** 2)
    return k0 * (k0 - 1) / np.maximum(k1, 1e-6)


def _sd_tube(P, pts, r):
    d = None
    for a, b in zip(pts, pts[1:]):
        a, b = np.asarray(a, np.float32), np.asarray(b, np.float32); ba = b - a; pa = P - a
        h = np.clip(pa @ ba / ba.dot(ba), 0, 1); e = np.linalg.norm(pa - h[..., None] * ba, axis=-1)
        d = e if d is None else np.minimum(d, e)
    return d - r


def _sd_nose(P):
    """Rounded inverted triangle, front leaning back towards the top, 9 mm deep."""
    n = NOSE; x, y, z = P[..., 0], P[..., 1], P[..., 2]; rd = n["round"]
    s = Vector((n["top"] - n["tip"], -n["half"])).normalized()          # outward normal of the right side (x, z)
    side = np.abs(x) * s.x + (z - n["tip"]) * s.y                       # 0 on the side line through the tip
    tri = np.maximum(np.maximum(z - n["top"], side), n["tip"] - z - 0.3)
    front = (n["lean"] * (z - n["tip"]) / (n["top"] - n["tip"]) + 0.10 * (x / n["half"]) ** 2 + 0.04) - y
    return np.maximum(np.maximum(tri + rd, front + rd), y - 0.9) - rd


def _sd_almond(P, c, g, side):
    """The lid opening: an almond (two circular arcs, the upper one flatter) in front of the eye centre, along the
    gaze; outer corner raised."""
    h, v = _eye_frame(g, side)
    if v.z < 0: v = -v
    a, bt, bb, tilt = EYE_OPEN; t = math.radians(tilt)
    Q = P - np.asarray(c, np.float32)
    u, w, f = Q @ np.asarray(h, np.float32), Q @ np.asarray(v, np.float32), Q @ np.asarray(g, np.float32)
    x = u * math.cos(t) + w * math.sin(t); y = -u * math.sin(t) + w * math.cos(t)
    ru = (a * a + bt * bt) / (2 * bt); rl = (a * a + bb * bb) / (2 * bb)
    up = np.hypot(x, y - (bt - ru)) - ru; lo = np.hypot(x, y - (rl - bb)) - rl
    return np.maximum(np.maximum(up, lo), -f)


def _head_field(P):
    d = None
    for name, c, r, rot, k, pair in HEAD_MASSES:
        for sx in ((1, -1) if pair else (1,)):
            m = _sd_ellipsoid(P, (sx * c[0], c[1], c[2]), r, (rot[0], sx * rot[1], sx * rot[2]))
            d = m if d is None else _smin(d, m, k)
    c, r, k = STOP; d = _smax(d, -_sd_ellipsoid(P, c, r), k)
    d = _smin(d, _sd_nose(P), NOSE["blend"])
    for pts, r, k, pair in GROOVES:
        for sx in ((1, -1) if pair else (1,)):
            d = _smax(d, -_sd_tube(P, [(sx * x, y, z) for x, y, z in pts], r), k)
    (nx, ny, nz), nr, nk = NOSTRIL
    for sx in (1, -1): d = _smax(d, -_sd_ellipsoid(P, (sx * nx, ny, nz), (nr[0], nr[1], nr[1], nr[2], nr[2])), nk)
    R = EYE_R * 100
    for sx in (1, -1):
        c = Vector((sx * EYE_AT[0], EYE_AT[1], EYE_AT[2])); g = _gaze(sx)
        room = _sd_ellipsoid(P - np.asarray(g * R * 0.9, np.float32), c, (R + EYE_LID * 0.9, R * 1.4, R * 1.4, R + EYE_LID * 0.9, R + EYE_LID * 0.9),
                             _look_rot(g))
        d = _smax(d, -room, EYE_BLEND[0])
        lid = np.linalg.norm(P - np.asarray(c + g * EYE_LID_FWD, np.float32), axis=-1) - (R + EYE_LID)
        d = _smin(d, lid, EYE_BLEND[1])
        d = _smax(d, -_sd_almond(P, c, g, sx), EYE_BLEND[2])
    return d


def _look_rot(g):
    """Euler angles (deg) that turn the local -y axis onto g (for masses stretched along a gaze)."""
    q = Vector((0, -1, 0)).rotation_difference(g); e = q.to_euler("XYZ")
    return tuple(math.degrees(a) for a in e)


def _surface_nets(F, origin, step):
    """Closed quad mesh of the zero level of F (negative inside; the box border must be outside)."""
    inside = F < 0; nx, ny, nz = F.shape
    acc = np.zeros((nx - 1, ny - 1, nz - 1, 3), np.float32); cnt = np.zeros((nx - 1, ny - 1, nz - 1), np.float32)
    corner = lambda o: F[o[0]:nx - 1 + o[0], o[1]:ny - 1 + o[1], o[2]:nz - 1 + o[2]]
    for a in range(8):
        for ax in range(3):
            oa = ((a >> 0) & 1, (a >> 1) & 1, (a >> 2) & 1)
            if oa[ax]: continue
            ob = list(oa); ob[ax] = 1; fa, fb = corner(oa), corner(ob)
            m = (fa < 0) != (fb < 0); t = np.where(m, fa / np.where(m, fa - fb, 1), 0)
            for k in range(3):
                acc[..., k] += np.where(m, oa[k] + (t if k == ax else 0), 0)
            cnt += m
    active = cnt > 0; vid = np.full(cnt.shape, -1, np.int64); vid[active] = np.arange(active.sum())
    I = np.argwhere(active)
    verts = (I + acc[active] / cnt[active][:, None]) * step + np.asarray(origin, np.float32)
    quads = []
    for ax in range(3):
        sl_a = [slice(None)] * 3; sl_b = [slice(None)] * 3
        sl_a[ax] = slice(0, -1); sl_b[ax] = slice(1, None)
        for o in range(3):
            if o != ax: sl_a[o] = sl_b[o] = slice(1, -1)
        m = inside[tuple(sl_a)] != inside[tuple(sl_b)]
        idx = np.argwhere(m)
        for o in range(3):
            if o != ax: idx[:, o] += 1
        flip = ~inside[tuple(idx.T)] if ax != 1 else inside[tuple(idx.T)]
        o1, o2 = [o for o in range(3) if o != ax]
        cells = []
        for d1, d2 in ((1, 1), (0, 1), (0, 0), (1, 0)):
            c = idx.copy(); c[:, o1] -= d1; c[:, o2] -= d2; cells.append(vid[tuple(c.T)])
        q = np.stack(cells, 1); q[flip] = q[flip][:, ::-1]; quads.append(q)
    return verts, np.concatenate(quads)


def build_head():
    """Head as one closed shell from the analytic field (masses, nose leather, grooves, nostrils, lids and their
    almond openings); the eyeballs (build_eyes) sit in the openings."""
    (x0, _), (y0, y1), (z0, z1) = HEAD_BOX; s = HEAD_STEP
    xs, ys, zs = (np.arange(a, b + s / 2, s, dtype=np.float32) for a, b in HEAD_BOX)
    P = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1)
    F = _head_field(P)
    F[0], F[-1], F[:, 0], F[:, -1], F[:, :, 0], F[:, :, -1] = (1.0,) * 6        # closed at the box border
    verts, quads = _surface_nets(F, (x0, y0, z0), s)
    verts = verts * HS / 100 + np.asarray(HEAD_AT, np.float32)
    me = bpy.data.meshes.new("head"); me.vertices.add(len(verts)); me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(quads.size); me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
    me.polygons.add(len(quads)); me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    me.update(calc_edges=True); me.validate()
    return _new_obj("head", me)


EAR = dict(base=(2.6, 6.0, 2.7), out=28, fwd_tilt=8, turn=35, height=3.9, w=1.95, back=2.0, front=0.7,
           wall=(0.45, 0.2), sunk=0.85, taper=0.8)


def _ear_frame(side):
    e = EAR; up = Vector((side * math.sin(math.radians(e["out"])), -math.sin(math.radians(e["fwd_tilt"])),
                          math.cos(math.radians(e["out"])))).normalized()
    fwd = Vector((side * math.tan(math.radians(e["turn"])), -1, 0.0)); fwd = (fwd - up * fwd.dot(up)).normalized()
    return up, fwd, up.cross(fwd).normalized() * side


def build_ears():
    """Two ears: a solid half cone (convex back, rounded tip) minus a cavity that opens forward and a little outward,
    as signed distance fields of their own; thick base, walls thinning to the tip, base sunk into the cranium.
    Returns (mesh, [(base, up, fwd, height, side)]) - the frames are for the ear tufts. EAR["base"] is also the pivot of
    the ear bones in cat_rig.py (keep them together)."""
    e = EAR; outer, cavity, ears = [], [], []
    for side in (1, -1):
        up, fwd, across = _ear_frame(side)
        b = _hp((side * e["base"][0], e["base"][1], e["base"][2])); H = e["height"] * HS / 100
        ears.append((b + up * e["sunk"] * HS / 100, up, fwd, H, side))
        so, sc = [], []
        for v in (0.0, 0.12, 0.25, 0.4, 0.55, 0.7, 0.82, 0.92):
            k = (1 - v) ** e["taper"]; w = e["w"] * HS / 100 * k; bk = e["back"] * HS / 100 * k + 0.0015; fr = e["front"] * HS / 100 * k + 0.001
            t = (e["wall"][0] + (e["wall"][1] - e["wall"][0]) * v) * HS / 100
            c = b + up * v * H
            so.append((c, w, fr, bk, {"n_up": 2.0, "n_down": 2.0}))
            if 0.12 <= v <= 0.92:
                sc.append((c, max(w - t, 0.001), fr + 0.02, max(bk - t, 0.0008), {"n_up": 2.4, "n_down": 2.0}))
        outer.append(_loft("ear", so, frame=(across * side, fwd), caps=(0.4, 1.4)))
        cavity.append(_loft("ear_cup", sc, frame=(across * side, fwd), caps=(0.6, 0.9)))
    return _csg([("union", outer), ("diff", cavity), ("mean", 1)], 0.0005, "ears"), ears


def build_eyes():
    """Two eyeballs at EYE_AT, in the lid openings the head field carves."""
    eyes = []
    for side in (1, -1):
        g = _gaze(side); c = _hp((side * EYE_AT[0], EYE_AT[1], EYE_AT[2]))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=16, radius=EYE_R * HS, location=c)
        e = bpy.context.active_object; e.name = "eye_%s" % ("l" if side > 0 else "r"); eyes.append(e)
        e.rotation_mode = "QUATERNION"; e.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(g)   # UV pole looks out
    bpy.ops.object.select_all(action="DESELECT")
    for e in eyes: e.select_set(True)
    bpy.context.view_layer.objects.active = eyes[0]; bpy.ops.object.join(); eyes[0].name = "eyes"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)     # vertices in world space
    return eyes[0]


# ---------------------------------------------------------------------------------------------------------------------
# Mouth: cutter lens, closing the slit, teeth, tongue, jaw weights, colours. All in head-local cm (see MOUTH_*).
MOUTH_Y = (-1.0, MOUTH_CAV["y"] + MOUTH_CAV["ay"])          # front (outside the face) and back end of the cutter


def _mz(y, x=0.0):
    """Middle surface of the mouth slit (z at y, x): MOUTH_Z along the middle, turning down by MOUTH_DROP beside the mandible."""
    x0 = np.interp(y, *zip(*MOUTH_XM)); u = np.clip((np.abs(x) - x0 + 0.1) / MOUTH_DROP_W, 0, 1)
    return np.interp(y, *zip(*MOUTH_Z)) - np.interp(y, *zip(*MOUTH_DROP)) * u * u * (3 - 2 * u)


def _cav_e(x, y, ax=None):
    """Cavity bulge factor 0..1 (an ellipse in plan, half width ax)."""
    c = MOUTH_CAV; return np.sqrt(np.maximum(1 - (x / (ax or c["ax"])) ** 2 - ((y - c["y"]) / c["ay"]) ** 2, 0))


def _floor_d(x, y):
    """How far the cavity floor lies below the slit: the shallow bulge plus the trough between the lower teeth."""
    c = MOUTH_CAV; return c["down"] * _cav_e(x, y) + c["down_u"] * _cav_e(x, y, c["ax_down"])


def _mw(y):
    """Half width of the cutter at y: the lip outline up to the corners, then the cavity."""
    c = MOUTH_CAV; cw = c["ax"] * np.sqrt(np.maximum(1 - ((y - c["y"]) / c["ay"]) ** 2, 0))
    return np.maximum(np.interp(y, *zip(*MOUTH_W)), cw + 0.06)


def _mt(x, y):
    """Half thickness of the slit at (x, y): full inside, falling to 0 at the outline and at both ends."""
    u = np.clip(np.abs(x) / np.maximum(_mw(y), 1e-6), 0, 1); y0, y1 = MOUTH_Y
    ends = np.clip((y - y0) / 0.4, 0, 1) * np.sqrt(np.clip((y1 - y) / 0.4, 0, 1))
    return MOUTH_T * np.sqrt(np.maximum(1 - u ** 12, 0)) * ends


def _local(co):
    """World metres -> head-local cm (array of points)."""
    return (np.asarray(co, np.float64) - np.asarray(HEAD_AT)) * 100 / HS


def build_mouth_cutter():
    """Closed lens: top and bottom sheets over a grid (rows along y, columns across the outline), sharing the outline
    and both end rows; thickness = slit + cavity bulge."""
    rows, n = MOUTH_GRID; bm = bmesh.new(); T, B = [], []
    for i, y in enumerate(np.linspace(*MOUTH_Y, rows + 1)):
        W = float(_mw(y)); tr, br = [], []
        for j in range(2 * n + 1):
            x = (-1 + j / n) * W; t = float(_mt(x, y)); e = float(_cav_e(x, y)); zm = float(_mz(y, x))
            top = bm.verts.new(_hp((x, y, zm + t + MOUTH_CAV["up"] * e)))
            edge = i in (0, rows) or j in (0, 2 * n)
            tr.append(top); br.append(top if edge else bm.verts.new(_hp((x, y, zm - t - float(_floor_d(x, y))))))
        T.append(tr); B.append(br)
    for i in range(rows):
        for j in range(2 * n):
            bm.faces.new((T[i][j], T[i + 1][j], T[i + 1][j + 1], T[i][j + 1]))
            bm.faces.new((B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]))
    bmesh.ops.triangulate(bm, faces=bm.faces); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("mouth_cut"); bm.to_mesh(me); bm.free()
    return _new_obj("mouth_cut", me)


def cut_mouth(shell):
    """The shell minus the cutter (exact boolean); the cut faces take the material Mouth."""
    cutter = build_mouth_cutter(); _slot(shell, "Fur"); _slot(cutter, "Mouth")
    m = shell.modifiers.new("mouth", "BOOLEAN"); m.operation = "DIFFERENCE"; m.solver = "EXACT"; m.object = cutter
    m.material_mode = "TRANSFER"
    _apply_all(shell)
    me = cutter.data; bpy.data.objects.remove(cutter); bpy.data.meshes.remove(me)
    names = [mt.name for mt in shell.data.materials]
    assert names == ["Fur", "Mouth"], names
    assert any(p.material_index == 1 for p in shell.data.polygons), "mouth cut left no faces"


def _close_mouth(shell, closed):
    """Press the slit walls together (the cavity stays); keeps the positions before in the point attribute mouth_pre
    (the jaw weights read which wall a vertex was on)."""
    me = shell.data; n = len(me.vertices)
    co = np.zeros(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
    pre = me.attributes.new("mouth_pre", "FLOAT_VECTOR", "POINT"); pre.data.foreach_set("vector", co.astype(np.float32).ravel())
    pre_np = co.copy()
    idx = sorted({i for p in me.polygons if p.material_index == 1 for i in p.vertices})
    cut = np.zeros(n, np.int32); cut[idx] = 1
    me.attributes.new("mouth_cut", "INT", "POINT").data.foreach_set("value", cut)
    P = _local(co[idx]); zm = _mz(P[:, 1], P[:, 0]); off = P[:, 2] - zm; t = _mt(P[:, 0], P[:, 1])
    P[:, 2] = zm + np.sign(off) * np.maximum(MOUTH_SHUT, np.abs(off) - t)
    co[idx] = P * HS / 100 + np.asarray(HEAD_AT)
    # the lip line (cut vertices on the skin, before closing at the slit's top or bottom face) slides along the closed skin to
    # where the skin meets the slit's middle surface: upper and lower lip edges meet on one line on the skin. Pressed down in z
    # alone they would sink into the head (a groove), and where the slit grazes the skin (under the jowls) leave a gap.
    bvh = BVHTree.FromObject(closed, bpy.context.evaluated_depsgraph_get())
    mat0 = np.zeros(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", mat0)
    skin_v = {i for p in me.polygons if mat0[p.index] == 0 for i in p.vertices}
    line = [i for i in idx if i in skin_v]
    for i in line:
        p0 = Vector(pre_np[i]); p = p0.copy()
        for _ in range(8):
            hit, nrm = bvh.find_nearest(p)[:2]
            if hit is None: break
            hl = _local([hit])[0]; dz = (HEAD_AT[2] + HS * float(_mz(hl[1], hl[0])) / 100) - hit.z
            tz = Vector((0, 0, 1)) - nrm * nrm.z
            if abs(dz) < 1e-6 or tz.z < 0.05: p = hit; break
            p = hit + tz * (dz / tz.z)
            if (p - p0).length > 0.006 * HS: p = p0 + (p - p0).normalized() * 0.006 * HS; break
        hit = bvh.find_nearest(p)[0]
        if hit is not None: co[i] = hit
    me.vertices.foreach_set("co", co.ravel()); me.update()
    lv = np.zeros(n, np.int32); lv[line] = 1; me.attributes.new("mouth_line", "INT", "POINT").data.foreach_set("value", lv)
    me.attributes.new("mouth_cutf", "BOOLEAN", "FACE").data.foreach_set("value", (mat0 == 1).tolist())
    # cut faces next to the skin before closing are the lips: they roll in, keep the Mouth material and are coloured as the dark lip
    # margin (_mouth_colours, face attribute mouth_lipf; shut they show as the thin dark lip line real cats have). Other cut faces at /
    # outside the skin once shut (a slit wall grazing the skin) become fur: they would show at rest. The edge between fur and the mouth inside is sharp; the lip line and the lip margin are smooth and take the
    # skin's normal at the line (_lip_normals): shut the line does not show, open the dark lip rolls into the mouth
    pre_co = pre_np
    mat = mat0.copy(); lipf = np.zeros(len(me.polygons), bool)
    for p in me.polygons:
        if mat[p.index] == 1:
            c = Vector(pre_co[list(p.vertices)].mean(0)); c1 = Vector(co[list(p.vertices)].mean(0))
            hit, _, _, d1 = bvh.find_nearest(c1)
            if bvh.find_nearest(c)[3] * 100 / HS < MOUTH_LIP or d1 * 100 / HS < MOUTH_SEEN or not _inside(bvh, c1, 0.0):
                lipf[p.index] = True           # lip margin and the walls grazing the skin: dark lip skin (also shut)
    me.polygons.foreach_set("material_index", mat)
    owner = {}
    for p in me.polygons:
        for k in p.edge_keys: owner.setdefault(k, set()).add(2 if lipf[p.index] else mat[p.index])
    sharp = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    sharp.data.foreach_set("value", [owner.get(e.key, set()) == {0, 1} for e in me.edges]); me.update()
    me.attributes.new("mouth_lipf", "BOOLEAN", "FACE").data.foreach_set("value", lipf.tolist())


def _lip_normals(mesh):
    """Custom normals on the lip line (point attribute mouth_line): every corner of a line vertex in a fur face takes the
    normal of the skin around it (its faces that were skin before the cut, face attribute mouth_cutf False). Shut, the line
    shades like the uncut skin (no crease); open, the rolled-in lip faces turn smoothly from it into the mouth (a round lip
    edge, no hard rim)."""
    me = mesh.data; n = len(me.vertices)
    line = np.zeros(n, np.int32); me.attributes["mouth_line"].data.foreach_get("value", line)
    cutf = np.zeros(len(me.polygons), bool); me.attributes["mouth_cutf"].data.foreach_get("value", cutf)
    lipf = np.zeros(len(me.polygons), bool); me.attributes["mouth_lipf"].data.foreach_get("value", lipf)
    fur = names_index(mesh, "Fur"); acc = {}
    for p in me.polygons:
        if p.material_index == fur and not cutf[p.index]:
            for v in p.vertices:
                if line[v]: acc[v] = acc.get(v, Vector()) + p.normal * p.area
    normals = [Vector(c.vector) for c in me.corner_normals]
    for p in me.polygons:
        if p.material_index != fur and not lipf[p.index]: continue
        for li, v in zip(p.loop_indices, p.vertices):
            if v in acc and acc[v].length > 0: normals[li] = acc[v].normalized()
    me.normals_split_custom_set([tuple(v) for v in normals])


def _tooth(bm, base, tip, r, flat, bend, n=8, rings=4):
    base, tip, bend = Vector(base), Vector(tip), Vector(bend); ax = (tip - base).normalized()
    side = Vector((1, 0, 0)); side = (side - ax * side.dot(ax)).normalized(); fwd = ax.cross(side)
    vs = []
    for k in range(rings):
        f = k / rings; c = base + (tip - base) * f + bend * math.sin(math.pi * f); rr = r * (1 - f) ** 0.65
        vs.append([bm.verts.new(_hp(c + side * rr * flat * math.cos(2 * math.pi * a / n) + fwd * rr * math.sin(2 * math.pi * a / n)))
                   for a in range(n)])
    tv, bv = bm.verts.new(_hp(tip)), bm.verts.new(_hp(base - ax * r * 0.4))
    for a, b in zip(vs, vs[1:]):
        for k in range(n): bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    for k in range(n):
        bm.faces.new((vs[-1][k], vs[-1][(k + 1) % n], tv)); bm.faces.new((bv, vs[0][(k + 1) % n], vs[0][k]))


def build_teeth():
    """Canines, incisors and cheek teeth as small cones; point attribute rigid: 1 = head, 2 = jaw."""
    up, low = bmesh.new(), bmesh.new()
    for sx in (1, -1):
        for b, t, r, flat, bend, jaw in TEETH:
            m = lambda p: (sx * p[0], p[1], p[2])
            _tooth(low if jaw else up, m(b), m(t), r, flat, m(bend))
        for k, (b, t, r) in enumerate(INCISORS):
            m = lambda p: (sx * p[0], p[1], p[2])
            _tooth(low if k >= 3 else up, m(b), m(t), r, 0.7, (0, 0, 0), n=6, rings=3)
    objs = []
    for bm, bone in ((up, 1), (low, 2)):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new("teeth"); bm.to_mesh(me); bm.free(); o = _new_obj("teeth", me)
        o.data.attributes.new("rigid", "INT", "POINT").data.foreach_set("value", [bone] * len(me.vertices)); objs.append(o)
    return _join(objs, "teeth")


def build_tongue():
    """Tongue on the floor of the cavity: a closed lens (domed top, flat underside sunk into the floor), mid groove,
    tip a little curled; it rides on the jaw."""
    g = TONGUE; rows, n = 18, 4; bm = bmesh.new(); T, B = [], []
    for i in range(rows + 1):
        s = i / rows; y = g["y0"] + (g["y1"] - g["y0"]) * s
        hw = (g["tip_w"] + (g["w"] - g["tip_w"]) * min(1.0, s / 0.35)) * (0.35 + 0.65 * math.sqrt(min(1.0, s / 0.08)))
        hw *= 1 - 0.45 * max(0.0, s - 0.75) / 0.25
        zm = float(_mz(y)); sink = 0.30 * max(0.0, (s - 0.7) / 0.3) ** 1.5
        tr, br = [], []
        for j in range(2 * n + 1):
            u = -1 + j / n; x = u * hw
            top = zm - g["top"] - 0.10 * (1 - math.sqrt(max(0.0, 1 - u * u))) - g["groove"] * math.exp(-(x / 0.12) ** 2) - sink
            top += g["curl"] * max(0.0, 1 - s / 0.2) ** 2
            top -= g["trough"] * MOUTH_CAV["down_u"] * float(_cav_e(x, y, MOUTH_CAV["ax_down"]))   # lies in the lower jaw's trough
            th = g["thick"] * math.sqrt(max(0.0, 1 - u ** 4)) * min(1.0, 0.2 + s / 0.1)
            v = bm.verts.new(_hp((x, y, top))); tr.append(v)
            edge = i in (0, rows) or j in (0, 2 * n)
            floor = zm - float(_floor_d(x, y))                                # underside only just below the cavity floor
            br.append(v if edge else bm.verts.new(_hp((x, y, min(top - 0.03, max(top - th, floor - 0.04))))))
        T.append(tr); B.append(br)
    for i in range(rows):
        for j in range(2 * n):
            bm.faces.new((T[i][j], T[i][j + 1], T[i + 1][j + 1], T[i + 1][j]))
            bm.faces.new((B[i][j], B[i + 1][j], B[i + 1][j + 1], B[i][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("tongue"); bm.to_mesh(me); bm.free(); o = _new_obj("tongue", me)
    o.data.attributes.new("rigid", "INT", "POINT").data.foreach_set("value", [2] * len(me.vertices))
    return o


def build_cheeks(closed):
    """Cheek membranes: per side a web just inside the lips along the side opening (CHEEK y0 to y1, the end of the slit), lying folded in
    the shut slit (top row on the upper wall, bottom row on the lower). Top row on the head, bottom row on the jaw, rows between
    blended (point attributes rigid 3 and jawf), so the open web fans between the lips. Its cross-section is round: the rows
    next to the lips sit `round` further in than the middle ones (rounded corners of the gape seen from the front, no flat
    ruled panel), and its free front edge curves back by `recede` at mid height (seen from the side the lips part in front of
    the commissure). Both faces; open they close the mouth at the sides like a cat's cheeks (no view through the head)."""
    c = CHEEK; bm = bmesh.new(); jawf = []; n = c["rows"]
    bvh = BVHTree.FromObject(closed, bpy.context.evaluated_depsgraph_get())
    for sx in (1, -1):
        grid0 = []
        for i in range(c["cols"] + 1):
            col = []
            for k in range(n + 1):
                a = math.sin(math.pi * k / n)                       # 0 at the lips, 1 at mid height
                yf = c["y0"] + c["recede"] * a ** 1.5; y = yf + (c["y1"] - yf) * i / c["cols"]
                hit = bvh.ray_cast(Vector(_hp((0, y, float(_mz(y))))), Vector((sx, 0, 0)))[0]
                xs = min(abs((hit.x - HEAD_AT[0]) * 100 / HS) - c["inset"], float(np.interp(y, *zip(*MOUTH_XM))) + c["xm"])
                xw = xs - c["round"] * (1 - a) ** 2; zm = float(_mz(y, xw))     # inside the turn: on the flat slit beside the jaw
                col.append((xw, y, zm + MOUTH_SHUT * (1 - 2 * k / n)))
            grid0.append(col)
        for flip in (False, True):
            grid = []
            for col in grid0:
                g = []
                for k, (x, y, z) in enumerate(col):
                    g.append(bm.verts.new(_hp((sx * (x - (0.03 if flip else 0)), y, z)))); jawf.append(k / n)
                grid.append(g)
            for i in range(c["cols"]):
                for k in range(n):
                    q = (grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1])
                    bm.faces.new(q if (sx > 0) == flip else q[::-1])
    me = bpy.data.meshes.new("cheeks"); bm.to_mesh(me); bm.free(); o = _new_obj("cheeks", me)
    o.data.attributes.new("rigid", "INT", "POINT").data.foreach_set("value", [3] * len(me.vertices))
    o.data.attributes.new("jawf", "FLOAT", "POINT").data.foreach_set("value", jawf)
    return o


def _inside(bvh, co, margin):
    hit, normal, _, _ = bvh.find_nearest(co)
    return hit is not None and (co - hit).dot(normal) < -margin


def _check_hidden(closed, objs, margin=0.00005):
    """Teeth and tongue stay inside the closed head (the shell before the cut) with the mouth shut."""
    bvh = BVHTree.FromObject(closed, bpy.context.evaluated_depsgraph_get())
    for o in objs:
        out = [v.co for v in o.data.vertices if not _inside(bvh, o.matrix_world @ v.co, margin)]
        if out:
            p = _local(np.array([out[0]]))[0]
            raise AssertionError("%s: %d vertices outside the shut mouth, e.g. head-local (%.2f, %.2f, %.2f) cm"
                                 % (o.name, len(out), *p))


def _mouth_colours(mesh, closed):
    """Point colours (sRGB) for the Mouth faces: dark lip edge, pink gums and palate (faint ridges), darker throat;
    tongue pink with a darker groove; white elsewhere."""
    me = mesh.data; n = len(me.vertices); col = np.ones((n, 4), np.float32)
    bvh = BVHTree.FromObject(closed, bpy.context.evaluated_depsgraph_get())
    mouth = names_index(mesh, "Mouth")
    pre = np.zeros(n * 3, np.float32); me.attributes["mouth_pre"].data.foreach_get("vector", pre); pre = pre.reshape(n, 3)
    rigid = np.zeros(n, np.int32); me.attributes["rigid"].data.foreach_get("value", rigid)
    idx = sorted({i for p in me.polygons if p.material_index == mouth for i in p.vertices})
    lipf = np.zeros(len(me.polygons), bool); me.attributes["mouth_lipf"].data.foreach_get("value", lipf)
    lipv = {i for p in me.polygons if lipf[p.index] for i in p.vertices}
    C = MOUTH_COL; lip, gum, thr, tng = (np.asarray(C[k], np.float32) for k in ("lip", "gum", "throat", "tongue"))
    for i in idx:
        P = _local(pre[i:i + 1])[0]
        if rigid[i] == 2:                                                      # tongue
            c = tng * (1 - 0.18 * math.exp(-(P[0] / 0.12) ** 2))
        else:
            hit, _, _, d = bvh.find_nearest(Vector(pre[i])); d *= 100 / HS
            ridge = rigid[i] == 0 and P[2] > _mz(P[1]) and abs(P[0]) < 0.75 and 1.5 < P[1] < 4.2   # palate ridges
            c = gum * (1 - 0.12 * ridge * (math.sin(P[1] * 2 * math.pi / 0.42) > 0.55))
            c = c + (thr - c) * float(np.clip((P[1] - 4.3) / 1.6, 0, 1))
            if rigid[i] == 3: c = c * 0.85                                       # cheek membranes: no lip edge
            elif i in lipv: c = lip
            else:
                c = lip + (c - lip) * float(np.clip((d - MOUTH_LIP) / 0.16, 0, 1))
                # the walls beside the mandible (under the overhanging upper lip, the corners): lip skin, dark (open, the
                # commissure curves dark from the upper lip down to the lower one)
                u = float(np.clip((abs(P[0]) - np.interp(P[1], *zip(*MOUTH_XM)) + 0.1) / 0.3, 0, 1))
                c = c + (lip - c) * (u * u * (3 - 2 * u))
        col[i, :3] = c
    a = me.color_attributes.new("Col", "BYTE_COLOR", "POINT"); a.data.foreach_set("color_srgb", col.ravel())
    me.color_attributes.active_color = a


def names_index(mesh, name):
    return [m.name for m in mesh.data.materials].index(name)


def _jaw_share(P):
    """How much of a head vertex follows the jaw (0..1) from its head-local position before the mouth was shut:
    sharp at the lips in front of the corners (each wall to its own side), softer behind them, fading out over the
    cheeks behind the corners and, under the jaw, towards the throat."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]; zm = _mz(y, x)
    w = np.interp(y, (MOUTH_CORNER - 0.1, MOUTH_CORNER + 1.0), (0.05, 0.35))
    s = np.clip((zm + w - z) / (2 * w), 0, 1); side = s * s * (3 - 2 * s)
    lat = np.clip((np.abs(x) - 1.0) / 1.2, 0, 1); lat = lat * lat * (3 - 2 * lat)
    c = MOUTH_CORNER; y0, y1 = 4.4 + (c + 0.1 - 4.4) * lat, 6.6 + (c + 0.8 - 6.6) * lat     # ends near the jaw hinge (y 6.3);
    # at the sides just behind the corners (the cheek behind the commissure stays on the head, no stretched wall)
    b = np.clip((y - y0) / (y1 - y0), 0, 1); back = 1 - b * b * (3 - 2 * b)
    return side * back


def _mouth_weights(mesh):
    """Shell vertices of the head: jaw = J * (head + jaw + neck), head and neck keep the rest (sum unchanged)."""
    me = mesh.data; n = len(me.vertices)
    pre = np.zeros(n * 3, np.float32); me.attributes["mouth_pre"].data.foreach_get("vector", pre); pre = pre.reshape(n, 3)
    shell = np.zeros(len(me.polygons), bool); me.attributes["shell"].data.foreach_get("value", shell)
    idx = sorted({i for p in me.polygons if shell[p.index] for i in p.vertices})
    P = _local(pre[idx]); J = _jaw_share(P)
    cut = np.zeros(n, np.int32); me.attributes["mouth_cut"].data.foreach_get("value", cut); cut = cut[idx] > 0
    off = P[:, 2] - _mz(P[:, 1], P[:, 0]); wall = cut & (np.abs(off) > 1e-5)
    low = P.copy(); low[:, 2] = _mz(P[:, 1], P[:, 0]) - 1.0                     # same place well below the slit: the falloff alone
    J = np.where(wall, _jaw_share(low) * (off < 0), J)  # a cut wall goes wholly to its side (the falloff behind the corners stays)
    G = {g: mesh.vertex_groups[g] for g in ("head", "jaw", "neck_02", "neck_01")}
    gi = {G[k].index: k for k in G}
    for i, j in zip(idx, J):
        w = {gi[g.group]: g.weight for g in me.vertices[i].groups if g.group in gi}
        h, nk = w.get("head", 0) + w.get("jaw", 0), w.get("neck_02", 0) + w.get("neck_01", 0)
        if h + nk <= 1e-4 or j <= 0 and w.get("jaw", 0) <= 0: continue
        G["jaw"].add([i], j * (h + nk), "REPLACE"); G["head"].add([i], (1 - j) * h, "REPLACE")
        for k in ("neck_02", "neck_01"):
            if w.get(k, 0) > 0: G[k].add([i], (1 - j) * w[k], "REPLACE")


VOXEL = 0.0008       # SDF grid of the fused shell
BAND = 8
FILLET = 12          # rounds the concave seams of the body (legs into the trunk)
FILLET_HEAD = 3      # head into neck (the face is shaped in the head field; more would fill its grooves)
FILLET_EARS = 3      # after the ears join (more would fill their cups)
MEAN = 2


def _loose(objs):
    """Each closed shell its own object (overlapping shells in one mesh confuse the inside test)."""
    out = []
    for o in objs:
        _apply_all(o)
        bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.separate(type="LOOSE"); bpy.ops.object.mode_set(mode="OBJECT")
        out += list(bpy.context.selected_objects)
    return out


def _csg(steps, voxel, name):
    """Signed distance fields: steps are ("union", objs), ("diff", objs), ("fillet", n), ("mean", n), applied in
    order to the union of the first step's shells; back to a mesh (the input objects are removed)."""
    host = _new_obj(name, bpy.data.meshes.new(name))
    ng = bpy.data.node_groups.new("csg", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links; used = []
    def sdf(o):
        used.append(o)
        oi = N.new("GeometryNodeObjectInfo"); oi.inputs["Object"].default_value = o
        m = N.new("GeometryNodeMeshToSDFGrid"); m.inputs["Voxel Size"].default_value = voxel; m.inputs["Band Width"].default_value = BAND
        L.new(oi.outputs["Geometry"], m.inputs["Mesh"]); return m.outputs["SDF Grid"]
    g = None
    for op, arg in steps:
        if op in ("union", "diff"):
            objs = _loose(arg) if op == "union" else arg
            b = N.new("GeometryNodeSDFGridBoolean"); b.operation = "UNION" if op == "union" else "DIFFERENCE"
            # union: one multi input (socket 1); difference: base socket 0, subtracted multi input socket 1
            if g is not None: L.new(g, b.inputs[1] if op == "union" else b.inputs[0])
            for o in objs: L.new(sdf(o), b.inputs[1])
            g = b.outputs["Grid"]
        else:
            f = N.new("GeometryNodeSDFGridFillet" if op == "fillet" else "GeometryNodeSDFGridMean")
            f.inputs["Iterations"].default_value = arg; L.new(g, f.inputs["Grid"]); g = f.outputs["Grid"]
    gm = N.new("GeometryNodeGridToMesh"); gm.inputs["Threshold"].default_value = 0.0; L.new(g, gm.inputs["Grid"])
    out = N.new("NodeGroupOutput"); L.new(gm.outputs["Mesh"], out.inputs[0])
    host.modifiers.new("csg", "NODES").node_group = ng
    _apply_all(host)
    for o in used:
        me = o.data; bpy.data.objects.remove(o); bpy.data.meshes.remove(me)
    bpy.data.node_groups.remove(ng)
    if not host.data.polygons: raise RuntimeError("%s: empty shell" % name)
    return host


def _fuse(body, head, ears):
    """The whole shell: body shells united and their concave seams filleted (legs, neck), the head (already blended
    in its own field) and the ears joined with light fillets, the field lightly averaged."""
    return _csg([("union", [body]), ("fillet", FILLET), ("union", [head]), ("fillet", FILLET_HEAD), ("union", [ears]),
                 ("fillet", FILLET_EARS), ("mean", MEAN)], VOXEL, "shell")


def build_cards(body, ears):
    """Fur cards: ear tufts, quads with UV 0..1 (strand texture runs along V). The cheek ruffs and the silhouette cards
    follow the fused surface and are added in finish() (_cheek_ruffs, build_fur_cards)."""
    bm = bmesh.new()
    def card(base, direction, width, length, side=Vector((1, 0, 0))):
        base, d, s = Vector(base), Vector(direction).normalized(), Vector(side).normalized() * width / 2
        q = [bm.verts.new(base - s), bm.verts.new(base + s), bm.verts.new(base + s + d * length), bm.verts.new(base - s + d * length)]
        bm.faces.new(q)
    for base, up, fwd, height, sx in ears:                                                   # ear tufts in the cup
        across = up.cross(fwd).normalized()
        card(base + (up * 0.012 - fwd * 0.008) * HS, up * 0.85 + fwd * 0.5, 0.010 * HS, 0.017 * HS, across)
    me = bpy.data.meshes.new("cards"); bm.to_mesh(me); bm.free(); o = _new_obj("cards", me)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li, (u, v) in zip(poly.loop_indices, [(0, 0), (1, 0), (1, 1), (0, 1)]): uv.data[li].uv = (u, v)
    return o


# cheek ruffs (m): base point on each cheek behind the mouth corner, direction of the strands (back and a little down), width,
# length, segments; the strip lies on the cheek, its height above the skin grows from RUFF_LIFT[0] at the base to [1] at the tip
RUFF = dict(base=(3.6, 5.3, -0.5), dir=(0.25, 1.0, -0.12), width=0.022, length=0.022, segs=3)    # base head-local cm; sizes x HS
RUFF_LIFT = (-0.0003, 0.0012)


def _cheek_ruffs(shell, cards):
    """Cheek ruffs as strips that follow the cheek: each row of the strip is set onto the fused surface (nearest point) and
    lifted along its normal, the base just under the skin, the tips a little off it (fur lying back along the cheek, not a flat
    plate). Joined into `cards` with UVs (V along the strands)."""
    bvh = BVHTree.FromObject(shell, bpy.context.evaluated_depsgraph_get()); r = RUFF; bm = bmesh.new(); uvs = []
    for sx in (1, -1):
        p = bvh.find_nearest(_hp((sx * r["base"][0], r["base"][1], r["base"][2])))[0]
        d0 = Vector((sx * r["dir"][0], r["dir"][1], r["dir"][2])).normalized(); rows = []
        for j in range(r["segs"] + 1):
            hit, nrm, *_ = bvh.find_nearest(p)
            d = (d0 - nrm * d0.dot(nrm)).normalized(); side = nrm.cross(d).normalized()
            lift = RUFF_LIFT[0] + (RUFF_LIFT[1] - RUFF_LIFT[0]) * (j / r["segs"]) ** 1.5; row = []
            for u in (-0.5, 0.5):
                q, qn, *_ = bvh.find_nearest(hit + side * u * r["width"] * HS)
                row.append(bm.verts.new(q + qn * lift)); uvs.append((u + 0.5, j / r["segs"]))
            rows.append(row); p = hit + d * r["length"] * HS / r["segs"]
        for j in range(r["segs"]):
            a, b = rows[j], rows[j + 1]
            bm.faces.new((a[0], a[1], b[1], b[0]) if sx > 0 else (a[1], a[0], b[0], b[1]))
    me = bpy.data.meshes.new("ruffs"); bm.to_mesh(me); bm.free(); o = _new_obj("ruffs", me)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices): uv.data[li].uv = uvs[vi]
    return _join([cards, o], cards.name)


# Silhouette fur (m): strips lying along the hair on the shell, the base just under the skin, the tip lifted off it, so the
# outline is soft (no shell fur). Region: (name, bones whose segment is nearest, normal test, hair direction, width, length,
# tip lift, spacing). The normal test is (axis, sign, threshold): n[axis] * sign > threshold.
FUR_CARDS = [
    ("back", ("spine_01", "spine_02", "spine_03", "pelvis", "neck_01"), (2, 1, 0.72), (0, 1, -0.1), 0.012, 0.017, 0.0020, 0.0085),
    ("chest", ("neck_01", "neck_02", "spine_03", "scapula_l", "scapula_r"), (1, -1, 0.30), (0, -0.1, -1), 0.016, 0.022, 0.0028, 0.0095),
    ("neck", ("neck_01", "neck_02"), (2, -1, -0.55), (0, 0.55, -0.7), 0.015, 0.020, 0.0025, 0.0100),
    ("throat", ("head",), (2, -1, 0.45), (0, 0.6, -0.8), 0.014, 0.018, 0.0022, 0.0095),
    ("belly", ("spine_01", "spine_02", "spine_03", "pelvis"), (2, -1, 0.50), (0, 0.4, -1), 0.014, 0.018, 0.0024, 0.0090),
    ("thigh", ("thigh_l", "thigh_r", "pelvis"), (1, 1, 0.30), (0, 0.4, -1), 0.014, 0.019, 0.0025, 0.0090),
    ("foreleg", ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r"), (1, 1, 0.35), (0, 0.3, -1), 0.010, 0.014, 0.0018, 0.0080),
    ("tail", tuple("tail_%02d" % i for i in range(1, 9)), (2, 1, -2.0), None, 0.010, 0.015, 0.0020, 0.0070),
]
FUR_CARD_MIN_Z = {"thigh": 0.075, "foreleg": 0.035, "chest": 0.10}     # nothing lower (paws, hocks) for these regions
TAIL_TIP_CARDS = dict(n=16, back=0.016, length=0.022, width=0.008, out=-0.16)    # out < 0: the strands close to a point
FUR_CARD_SEED = 20261114


def _seg_dist(P, a, b):
    a, b = np.asarray(a), np.asarray(b); ab = b - a; t = np.clip((P - a) @ ab / ab.dot(ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1), t


def _strip(bm, bvh, p, d0, width, length, lift, segs, rows_out):
    """A strip marched over the surface from p along d0 (re-projected into the surface each row), base -0.3 mm, tip `lift`
    above the skin; appends its vertices with (u, v) and the surface normal at the base to rows_out."""
    rows = []; base_n = None
    for j in range(segs + 1):
        hit, nrm, *_ = bvh.find_nearest(p)
        if base_n is None: base_n = nrm.copy()
        d = (d0 - nrm * d0.dot(nrm))
        if d.length < 1e-6: return None
        d.normalize(); side = nrm.cross(d).normalized()
        lf = -0.0003 + (lift + 0.0003) * (j / segs) ** 1.4; row = []
        for u in (-0.5, 0.5):
            q, qn, *_ = bvh.find_nearest(hit + side * u * width * (1 - 0.25 * j / segs))
            row.append((q + qn * lf, (u + 0.5, j / segs)))
        rows.append(row); p = hit + d * length / segs
    return rows, base_n


def build_fur_cards(shell):
    """Silhouette fur cards on the Fur faces of the final shell (FUR_CARDS) and a soft taper of short cards at the tail tip.
    Returns an object with UVs (V along the strands) and point attributes card_base (the base point on the skin: the card takes
    the bone weights there) and card_n (the skin normal there: the card shades like the fur under it)."""
    me = shell.data; fur = [m.name for m in me.materials].index("Fur")
    bm0 = bmesh.new(); bm0.from_mesh(me)
    bmesh.ops.delete(bm0, geom=[f for f in bm0.faces if f.material_index != fur], context="FACES")
    bmesh.ops.triangulate(bm0, faces=bm0.faces[:]); bvh = BVHTree.FromBMesh(bm0)
    tris = np.array([[v.co[:] for v in f.verts] for f in bm0.faces]); bm0.free()
    area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) / 2
    rng = np.random.default_rng(FUR_CARD_SEED); n = 90000
    ti = rng.choice(len(tris), n, p=area / area.sum()); r1, r2 = rng.random(n), rng.random(n); s1 = np.sqrt(r1)
    P = tris[ti, 0] * (1 - s1)[:, None] + tris[ti, 1] * (s1 * (1 - r2))[:, None] + tris[ti, 2] * (s1 * r2)[:, None]
    nrm = np.cross(tris[ti, 1] - tris[ti, 0], tris[ti, 2] - tris[ti, 0]); nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    segs = [(b[0], b[2], b[3]) for b in cat_rig.BONES if b[0] not in ("root",)]
    D = np.stack([_seg_dist(P, a, b)[0] for _, a, b in segs], 1); near = np.array([segs[k][0] for k in D.argmin(1)])
    tail_tip = np.asarray(_bone("tail_08")[3])
    bm = bmesh.new(); uv, base, bn = [], [], []; counts = {}
    def add(rows, base_n, p):
        vs = []
        for row in rows:
            r = []
            for co, t in row:
                r.append(bm.verts.new(co)); uv.append(t); base.append(tuple(p)); bn.append(tuple(base_n))
            vs.append(r)
        for a, b in zip(vs, vs[1:]):
            q = (a[0], a[1], b[1], b[0])
            if (a[1].co - a[0].co).cross(b[0].co - a[0].co).dot(Vector(base_n)) < 0: q = q[::-1]   # front face out (two-sided
            bm.faces.new(q)                                                         # materials turn the back's normal inwards)
    for name, bones, (ax, sg, th), hair, width, length, lift, spacing in FUR_CARDS:
        sel = np.isin(near, bones) & (nrm[:, ax] * sg > th) & (P[:, 2] > FUR_CARD_MIN_Z.get(name, -1))
        if name == "tail": sel &= np.linalg.norm(P - tail_tip, axis=1) > TAIL_TIP_CARDS["back"] + 0.004
        if name == "back": sel &= np.abs(P[:, 0]) < 0.025
        if name == "chest": sel &= np.abs(P[:, 0]) < 0.035
        kept = []
        for i in np.nonzero(sel)[0]:
            if all(np.linalg.norm(P[i] - P[j]) >= spacing for j in kept[-400:]): kept.append(i)
        for i in kept:
            p = Vector(P[i])
            if hair is None:                                                        # tail: towards the tip along the chain
                k = int(np.argmin([_seg_dist(P[i:i + 1], a, b)[0][0] for nm_, a, b in segs if nm_.startswith("tail_")]))
                a, b = _bone("tail_%02d" % (k + 1))[2:4]; d0 = (Vector(b) - Vector(a)).normalized()
            else: d0 = Vector(hair).normalized()
            ang = math.radians(rng.uniform(-18, 18)); nn = Vector(nrm[i])
            d0 = d0 * math.cos(ang) + nn.cross(d0) * math.sin(ang) + nn * nn.dot(d0) * (1 - math.cos(ang))
            res = _strip(bm, bvh, p, d0, width * rng.uniform(0.85, 1.15), length * rng.uniform(0.8, 1.2), lift, 2, None)
            if res is None: continue
            add(res[0], res[1], p); counts[name] = counts.get(name, 0) + 1
    # tail tip: short cards on the tapering skin before the tip, along the tail and leaning in, reaching about 6 mm past the tip:
    # the strands close to a point over the narrowed end (no brush, no club)
    t = TAIL_TIP_CARDS; a, b = (Vector(v) for v in _bone("tail_08")[2:4]); d = (b - a).normalized()
    ref = Vector((1, 0, 0)); e1 = (ref - d * ref.dot(d)).normalized(); e2 = d.cross(e1)
    for k in range(t["n"]):
        phi = 2 * math.pi * (k + 0.5 * (k % 2)) / t["n"]; radial = e1 * math.cos(phi) + e2 * math.sin(phi)
        c = b - d * (t["back"] * rng.uniform(0.8, 1.2)); hit, hn, *_ = bvh.find_nearest(c + radial * 0.02)
        dd = (d + radial * t["out"]).normalized(); side = radial.cross(dd).normalized(); L = t["length"] * rng.uniform(0.85, 1.15)
        rows = [[(hit - hn * 0.0003 + side * u * t["width"] * w + dd * L * j / 2, (u + 0.5, j / 2)) for u in (-0.5, 0.5)]
                for j, w in ((0, 1.0), (1, 0.8), (2, 0.55))]
        add(rows, hn, hit); counts["tail_tip"] = counts.get("tail_tip", 0) + 1
    print("CAT fur cards %s" % " ".join("%s %d" % kv for kv in counts.items()))
    m = bpy.data.meshes.new("fur_cards"); bm.to_mesh(m); bm.free(); o = _new_obj("fur_cards", m)
    layer = m.uv_layers.new(name="UVMap")
    for poly in m.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices): layer.data[li].uv = uv[vi]
    m.attributes.new("card_base", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", np.asarray(base, np.float32).ravel())
    m.attributes.new("card_n", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", np.asarray(bn, np.float32).ravel())
    return o


def _card_uv1(mesh):
    """Second UV map FurUV: the fur's own UVs on the shell; every fur card vertex takes the fur UV of its base point on the skin
    (M_VP_CatFurCard samples the coat masks there, so a card has the colour of the fur it grows from)."""
    me = mesh.data; uv0 = me.uv_layers["UVMap"]; uv1 = me.uv_layers.new(name="FurUV")
    me.uv_layers.active = uv0; uv0.active_render = True
    n = len(me.loops); a = np.zeros(n * 2, np.float32); uv0.data.foreach_get("uv", a); uv1.data.foreach_set("uv", a)
    base = me.attributes.get("card_base")
    if base is None: return
    B = np.zeros(len(me.vertices) * 3, np.float32); base.data.foreach_get("vector", B); B = B.reshape(-1, 3)
    has = np.zeros(len(me.vertices), bool); fc = me.attributes.get("card_follow")
    if fc is not None:
        f = np.zeros(len(me.vertices), np.int32); fc.data.foreach_get("value", f); has = f > 0
    fur = names_index(mesh, "Fur"); bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != fur], context="FACES")
    bmesh.ops.triangulate(bm, faces=bm.faces[:]); bvh = BVHTree.FromBMesh(bm); bm.faces.ensure_lookup_table()
    ul = bm.loops.layers.uv["UVMap"]
    from mathutils.geometry import barycentric_transform
    cache = {}
    for poly in me.polygons:
        for li, vi in zip(poly.loop_indices, poly.vertices):
            if not has[vi]: continue
            if vi not in cache:
                co, _, fi, _ = bvh.find_nearest(Vector(B[vi])); f = bm.faces[fi]
                (p0, p1, p2), (t0, t1, t2) = [l.vert.co for l in f.loops], [l[ul].uv.to_3d() for l in f.loops]
                cache[vi] = barycentric_transform(co, p0, p1, p2, t0, t1, t2).to_2d()
            uv1.data[li].uv = cache[vi]
    bm.free()


def _card_weights(mesh):
    """Silhouette cards (card_follow) take the bone weights of the skin at their base point (interpolated over the nearest shell
    triangle), so they move with the body; their corners get the skin normal there."""
    me = mesh.data; nv = len(me.vertices)
    f = np.zeros(nv, np.int32); me.attributes["card_follow"].data.foreach_get("value", f)
    B = np.zeros(nv * 3, np.float32); me.attributes["card_base"].data.foreach_get("vector", B); B = B.reshape(-1, 3)
    shell = np.zeros(len(me.polygons), bool); me.attributes["shell"].data.foreach_get("value", shell)
    fur = names_index(mesh, "Fur")
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    vid = bm.verts.layers.int.new("card_vid")
    for v in bm.verts: v[vid] = v.index
    bmesh.ops.delete(bm, geom=[fc for fc in bm.faces if not (shell[fc.index] and fc.material_index == fur)], context="FACES")
    bmesh.ops.triangulate(bm, faces=bm.faces[:]); bvh = BVHTree.FromBMesh(bm); bm.faces.ensure_lookup_table()
    W = [{g.group: g.weight for g in v.groups} for v in me.vertices]
    from mathutils.geometry import barycentric_transform
    groups = mesh.vertex_groups; cache = {}
    for vi in np.nonzero(f > 0)[0].tolist():
        key = tuple(np.round(B[vi], 7))
        if key not in cache:
            co, _, fi, _ = bvh.find_nearest(Vector(B[vi])); tri = bm.faces[fi]
            vs = [l.vert for l in tri.loops]
            bc = barycentric_transform(co, vs[0].co, vs[1].co, vs[2].co, Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
            acc = {}
            for v, w in zip(vs, bc):
                for g, gw in W[v[vid]].items(): acc[g] = acc.get(g, 0) + gw * max(w, 0)
            top = sorted(acc.items(), key=lambda kv: -kv[1])[:MAX_INFLUENCES]; t = sum(w for _, w in top)
            cache[key] = [(g, w / t) for g, w in top if w > 1e-4]
        for g in list(me.vertices[vi].groups): groups[g.group].remove([vi])
        for g, w in cache[key]: groups[g].add([vi], w, "REPLACE")
    bm.free()


def _card_normals(mesh):
    """Corners of the silhouette cards take the skin normal at their base (card_n): they shade like the fur under them."""
    me = mesh.data; nv = len(me.vertices)
    f = np.zeros(nv, np.int32); me.attributes["card_follow"].data.foreach_get("value", f)
    N = np.zeros(nv * 3, np.float32); me.attributes["card_n"].data.foreach_get("vector", N); N = N.reshape(-1, 3)
    normals = [Vector(c.vector) for c in me.corner_normals]
    for p in me.polygons:
        for li, v in zip(p.loop_indices, p.vertices):
            if f[v]: normals[li] = Vector(N[v])
    me.normals_split_custom_set([tuple(v) for v in normals])


def _apply_all(o):
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)


def _slot(o, name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name); o.data.materials.clear(); o.data.materials.append(mat)


SLOTS = ["Fur", "Eye", "FurCard", "Mouth", "Teeth"]      # material slot order of SK_VP_Cat (import_cat, names.SLOTS)
MOUTH_TRIS = 1500          # what the mouth adds to the shell (cut faces) on top of the stage-1 shell budget


def finish(arm, body, head, ears, eyes, cards):
    """Fuse body, head and ears into one shell (signed distance fields, eye sockets and lids cut there), reduce, cut and
    shut the mouth, UV; join eyes, cards, teeth and tongue as own slots; skin to the armature."""
    body = _fuse(body, head, ears)
    cards = _cheek_ruffs(body, cards)
    _floor(body)
    # the mouth is cut into the dense shell (a smooth lip line), then the whole is reduced
    closed = body.copy(); closed.data = body.data.copy(); bpy.context.scene.collection.objects.link(closed)
    cut_mouth(body)
    tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
    dec = body.modifiers.new("dec", "DECIMATE"); dec.ratio = min(1.0, (TARGET_TRIS * 0.85 + MOUTH_TRIS) / max(1, tris)); _apply_all(body)
    _floor(body); _clean(body); _close_mouth(body, closed)
    teeth, tongue = build_teeth(), _join([build_tongue(), build_cheeks(closed)], "tongue")
    _check_hidden(closed, (teeth, tongue))
    fc = build_fur_cards(body)
    fc.data.attributes.new("card_follow", "INT", "POINT").data.foreach_set("value", [1] * len(fc.data.vertices))
    cards = _join([cards, fc], cards.name)
    body.data.attributes.new("shell", "BOOLEAN", "FACE").data.foreach_set("value", [True] * len(body.data.polygons))
    for o in (teeth, tongue):
        co = np.zeros(len(o.data.vertices) * 3, np.float32); o.data.vertices.foreach_get("co", co)
        o.data.attributes.new("mouth_pre", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", co)
    for o in (body, teeth, tongue):
        bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
        for k in range(len(o.data.materials) or 1):          # the shell: fur alone gets the whole texture, mouth its own
            bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="DESELECT")
            if o.data.materials: o.active_material_index = k; bpy.ops.object.material_slot_select()
            else: bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004); bpy.ops.object.mode_set(mode="OBJECT")
    _shrink_uv(body, 1)
    _slot(eyes, "Eye"); _slot(cards, "FurCard"); _slot(teeth, "Teeth"); _slot(tongue, "Mouth")
    for o in (eyes, cards):
        if not o.data.uv_layers: o.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    for o in (body, eyes, cards, teeth, tongue): o.select_set(True)
    bpy.context.view_layer.objects.active = body; bpy.ops.object.join(); body.name = body.data.name = "SK_VP_Cat"
    _order_slots(body, SLOTS)
    _card_uv1(body)
    _mouth_colours(body, closed)
    me = closed.data; bpy.data.objects.remove(closed); bpy.data.meshes.remove(me)
    bpy.ops.object.shade_smooth(keep_sharp_edges=True)
    _lip_normals(body)
    _card_normals(body)
    # weights: heat on the shell, eyes, cards, teeth and tongue rigid, the jaw from the mouth, envelopes for anything empty
    _heat_weights(arm, body)
    _rigid_cards(body)
    _mouth_weights(body)
    _smooth_weights(body)
    _card_weights(body)
    empty = [v.index for v in body.data.vertices if not any(g.weight > 0 for g in v.groups)]
    if empty:
        print("CAT heat left %d vertices empty, envelopes for them" % len(empty))
        _envelope(arm, body, empty)
    bpy.context.view_layer.objects.active = body; bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
    bpy.ops.object.vertex_group_limit_total(limit=MAX_INFLUENCES); bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for a in ("mouth_pre", "shell", "rigid", "jawf", "mouth_cut", "mouth_line", "mouth_cutf", "mouth_lipf", "card_base", "card_n", "card_follow"):
        body.data.attributes.remove(body.data.attributes[a])
    return body


def _shrink_uv(mesh, slot, size=0.05):
    """UVs of one slot squeezed into a corner (the mouth reads point colours, no texture; the fur keeps the space)."""
    me = mesh.data; uv = me.uv_layers.active.data
    for p in me.polygons:
        if p.material_index == slot:
            for li in p.loop_indices: uv[li].uv = uv[li].uv * size + Vector((1 - size, 1 - size))


def _order_slots(mesh, order):
    """Material slots in `order` (a joined mesh lists them as they came); one slot per name."""
    me = mesh.data; old = [m.name for m in me.materials]
    assert sorted(set(old)) == sorted(order), old
    remap = np.array([order.index(n) for n in old], np.int32)
    idx = np.zeros(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    mats = {m.name: m for m in me.materials}; me.materials.clear()
    for n in order: me.materials.append(mats[n])
    me.polygons.foreach_set("material_index", remap[idx]); me.update()


def _clean(o):
    """No coincident vertices or zero-area faces (bone heat finds no solution with them); the shell must be closed."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=2e-5)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    print("CAT clean: %d verts, %d faces, %d non-manifold edges" % (len(bm.verts), len(bm.faces), sum(not e.is_manifold for e in bm.edges)))
    assert not any(not e.is_manifold for e in bm.edges), "cat shell has non-manifold edges"
    bm.to_mesh(o.data); bm.free()


def _floor(o):
    """Paw pads rest flat on the floor: nothing below z = 0 (clamp, not a shift: only the pads reach down there)."""
    for v in o.data.vertices:
        if v.co.z < 0: v.co.z = 0.0


def _rigid_cards(mesh):
    """Fur cards, eyes, teeth and tongue ride on one bone each: ear tufts -> their ear, cheek ruffs and eyes -> head (the
    silhouette cards follow the skin instead, _card_weights); teeth and tongue by their point attribute rigid (1 head, 2 jaw)."""
    rigid = np.zeros(len(mesh.data.vertices), np.int32); mesh.data.attributes["rigid"].data.foreach_get("value", rigid)
    for g in ("head", "jaw"):
        if g not in mesh.vertex_groups: mesh.vertex_groups.new(name=g)
    jawf = np.zeros(len(mesh.data.vertices), np.float32); mesh.data.attributes["jawf"].data.foreach_get("value", jawf)
    for i in np.nonzero(rigid)[0].tolist():
        for g in list(mesh.data.vertices[i].groups): mesh.vertex_groups[g.group].remove([i])
        f = 0.0 if rigid[i] == 1 else 1.0 if rigid[i] == 2 else float(jawf[i])
        if f < 1: mesh.vertex_groups["head"].add([i], 1.0 - f, "REPLACE")
        if f > 0: mesh.vertex_groups["jaw"].add([i], f, "REPLACE")
    names = [m.name for m in mesh.data.materials]; card, eye = names.index("FurCard"), names.index("Eye")
    ear_z = _bone("ear_l")[2][2] - 0.01; tail_y = _bone("tail_08")[2][1]
    follow = np.zeros(len(mesh.data.vertices), np.int32); mesh.data.attributes["card_follow"].data.foreach_get("value", follow)
    for poly in mesh.data.polygons:
        if poly.material_index not in (card, eye) or follow[poly.vertices[0]]: continue   # silhouette cards: _card_weights
        ctr = sum((mesh.data.vertices[i].co for i in poly.vertices), Vector()) / len(poly.vertices)
        bone = "head" if poly.material_index == eye else "tail_08" if ctr.y > tail_y else \
            ("ear_l" if ctr.x > 0 else "ear_r") if ctr.z > ear_z else "head"
        for i in poly.vertices:
            for g in list(mesh.data.vertices[i].groups): mesh.vertex_groups[g.group].remove([i])
            mesh.vertex_groups[bone].add([i], 1.0, "REPLACE")


def _heat_weights(arm, body):
    """Automatic (heat) weights for the fur shell. Bone heat fails at the cat's real size (metres, small distances),
    so the weights are solved on copies scaled x10 and copied back by vertex id; the original is parented with an empty
    armature modifier and receives the groups. Eyes and cards are left out of the solve (separate islands inside or
    beside the shell make it fail as a whole) and get rigid weights afterwards."""
    vid = body.data.attributes.new("vid", "INT", "POINT"); vid.data.foreach_set("value", range(len(body.data.vertices)))
    arm2 = arm.copy(); arm2.data = arm.data.copy(); body2 = body.copy(); body2.data = body.data.copy()
    bm = bmesh.new(); bm.from_mesh(body2.data); shell = bm.faces.layers.bool.get("shell")
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not f[shell]], context="FACES"); bm.to_mesh(body2.data); bm.free()
    for o in (arm2, body2):
        bpy.context.scene.collection.objects.link(o); o.scale = (10, 10, 10)
        bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.select_all(action="DESELECT"); body2.select_set(True); arm2.select_set(True)
    bpy.context.view_layer.objects.active = arm2; bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    bpy.ops.object.select_all(action="DESELECT"); body.select_set(True); arm.select_set(True)
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.parent_set(type="ARMATURE")
    names = {g.index: g.name for g in body2.vertex_groups}
    groups = {}; ids = body2.data.attributes["vid"].data
    for v in body2.data.vertices:
        for g in v.groups:
            if g.weight > 0:
                name = names[g.group]
                grp = groups.get(name) or groups.setdefault(name, body.vertex_groups.get(name) or body.vertex_groups.new(name=name))
                grp.add([ids[v.index].value], g.weight, "REPLACE")
    body.data.attributes.remove(body.data.attributes["vid"])
    for o in (body2, arm2):
        data = o.data; bpy.data.objects.remove(o)
        (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.armatures).remove(data)


# weight smoothing around the shoulder and hip: (bone whose head is the centre, radius m, groups, iterations, strength)
SMOOTH_ZONES = [("upperarm_%s" % s, 0.05, ("scapula_" + s, "upperarm_" + s), 8, 0.5) for s in "lr"] + \
               [("thigh_%s" % s, 0.10, ("thigh_" + s, "pelvis", "spine_01"), 40, 0.9) for s in "lr"]
# look pass 2: the hip zone wider and smoothed harder (thigh, pelvis and the flank in front of it): sitting, the folded thigh
# and the flank read as one round haunch instead of a fold line where they meet


def _smooth_weights(mesh):
    """Laplacian smoothing of the weights of a few groups inside a soft sphere around a joint (shell vertices only);
    each vertex keeps the sum of those groups, the other groups are untouched. The weights are read in a ring beyond the
    sphere too, so the vertices at its edge average with their real neighbours (not with zeros)."""
    me = mesh.data; n = len(me.vertices)
    shell = np.zeros(len(me.polygons), bool); me.attributes["shell"].data.foreach_get("value", shell)
    on = np.zeros(n, bool)
    for p in me.polygons:
        if shell[p.index]: on[list(p.vertices)] = True
    E = np.zeros(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", E); E = E.reshape(-1, 2)
    E = E[on[E[:, 0]] & on[E[:, 1]]]
    deg = np.bincount(E.ravel(), minlength=n).astype(np.float64)
    co = np.zeros(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
    for bone, radius, groups, iters, k in SMOOTH_ZONES:
        c = np.asarray(_bone(bone)[2]); d = np.linalg.norm(co - c, axis=1)
        f = k * np.clip(1 - d / radius, 0, 1) ** 0.5 * on
        gidx = [mesh.vertex_groups[g].index for g in groups]
        W = np.zeros((n, len(groups)))
        for v in np.nonzero((d < radius * 1.5) & on)[0].tolist():     # the sphere and a ring around it: real neighbour weights
            for g in me.vertices[v].groups:
                if g.group in gidx: W[v, gidx.index(g.group)] = g.weight
        tot = W.sum(1)
        for _ in range(iters):
            S = np.zeros_like(W); np.add.at(S, E[:, 0], W[E[:, 1]]); np.add.at(S, E[:, 1], W[E[:, 0]])
            avg = S / np.maximum(deg, 1)[:, None]
            W = W + f[:, None] * (avg - W)
            W *= (tot / np.maximum(W.sum(1), 1e-9))[:, None]
        for v in np.nonzero((f > 0) & (tot > 0))[0].tolist():
            for j, g in enumerate(groups):
                if W[v, j] > 1e-4: mesh.vertex_groups[g].add([v], float(W[v, j]), "REPLACE")
                else: mesh.vertex_groups[g].remove([v])


def _envelope(arm, mesh, indices):
    """Nearest deforming bone segment gets weight 1."""
    segs = [(b.name, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local) for b in arm.data.bones if b.use_deform]
    for i in indices:
        p = mesh.matrix_world @ mesh.data.vertices[i].co
        def dist(s):
            _, a, b = s; ab = b - a; t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared)); return (a + ab * t - p).length
        name = min(segs, key=dist)[0]
        (mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)).add([i], 1.0, "REPLACE")


def check(arm, mesh):
    tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    assert 6000 <= tris <= 30000, "tris %d" % tris                  # shell ~16000 + silhouette fur cards
    assert [m.name for m in mesh.data.materials] == SLOTS, [m.name for m in mesh.data.materials]
    used = {p.material_index for p in mesh.data.polygons}
    assert used == set(range(len(SLOTS))), "unused slots %s" % [SLOTS[i] for i in set(range(len(SLOTS))) - used]
    jaw = mesh.vertex_groups["jaw"].index
    rigid_jaw = sum(1 for v in mesh.data.vertices if any(g.group == jaw and g.weight > 0.99 for g in v.groups))
    print("CAT mouth: %d vertices rigid on jaw" % rigid_jaw)
    assert rigid_jaw > 300, "jaw carries only %d vertices rigidly (lower jaw, lower teeth, tongue)" % rigid_jaw
    unweighted = [v.index for v in mesh.data.vertices if not any(g.weight > 0 for g in v.groups)]
    assert not unweighted, "unweighted %d" % len(unweighted)
    assert all(len([g for g in v.groups if g.weight > 0]) <= MAX_INFLUENCES for v in mesh.data.vertices)
    lo = min((mesh.matrix_world @ v.co).z for v in mesh.data.vertices)
    assert -0.004 <= lo <= 0.006, "floor %.4f" % lo
    ys = [(mesh.matrix_world @ v.co).y for v in mesh.data.vertices]
    zs = [(mesh.matrix_world @ v.co).z for v in mesh.data.vertices if (mesh.matrix_world @ v.co).y < -0.05]
    print("CAT size nose %.3f max-y %.3f height-front %.3f" % (min(ys), max(ys), max(zs)))
    nose = min(ys); assert abs(nose - cat_rig.NOSE_Y) < 0.01, "nose %.3f vs rig %.3f" % (nose, cat_rig.NOSE_Y)
    withers = max((mesh.matrix_world @ v.co).z for v in mesh.data.vertices if -0.13 < (mesh.matrix_world @ v.co).y < -0.07)
    assert abs(withers - cat_rig.shoulder_height()) < 0.015, "withers %.3f vs rig %.3f" % (withers, cat_rig.shoulder_height())
    return tris


def export(arm, mesh, path):
    """Same settings as TKAInfo common.export_fbx: x100 with scale applied, unit scale 0.01, -Z forward, Y up, no leaf
    bones. Only the armature is scaled, the mesh is its child and follows (scaling both made the mesh 100x too big).
    The armature object is exported as 'Armature': UE's FBX import drops a Blender null of that name above the root
    bone, so the bone 'root' is the skeleton's root (named 'root' it became a second bone, root -> root1)."""
    sc = bpy.context.scene; sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
    arm.scale = (100, 100, 100); arm.name = ARMATURE_NODE
    bpy.ops.object.select_all(action="DESELECT")
    for o in (arm, mesh): o.select_set(True)
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_NONE", global_scale=1.0, add_leaf_bones=False, bake_anim=False,
                             use_armature_deform_only=False, primary_bone_axis="Y", secondary_bone_axis="X", mesh_smooth_type="FACE",
                             use_mesh_modifiers=False, axis_forward="-Z", axis_up="Y")


def main(out):
    os.makedirs(out, exist_ok=True); clear()
    arm = build_armature()
    body, head = build_body(arm), build_head()
    ears, ear_frames = build_ears()
    eyes = build_eyes()
    cards = build_cards(body, ear_frames)
    mesh = finish(arm, body, head, ears, eyes, cards)
    tris = check(arm, mesh)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "cat.blend"))   # metres, for the bake
    export(arm, mesh, os.path.join(out, "cat.fbx"))
    print("CAT OK %d %d" % (tris, len(arm.data.bones)))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
