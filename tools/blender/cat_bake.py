"""Bakes the cat's pattern masks and fur normal map into its UVs, and paints the card and eye textures.
Reads build/velvetpaws/cat.blend, writes build/velvetpaws/tex/*.png and regions.json (placement statistics for
the tests), prints BAKE OK 5.

The masks are 3D patterns, so stripes run on across UV seams. Cycles bakes the geometry of every texel of the Fur slot
(object-space position, normal and per-vertex frames taken from the rig: distance along the spine, along each leg and
along the tail, and how much of the texel belongs to the head, a leg, the tail or an ear, from the bone weights). The
patterns are then evaluated per texel in numpy from those buffers. Regions come from the model itself (cat_model:
nose leather SDF, whisker pad and chin masses, ear frames; cat_rig: bone chains), not from fixed coordinates.

Channel layout (the interface of the UE material M_VP_CatFur):
  mask_a.png  R tabby (mackerel), G brindle, B spots, A tricolour patches (weight of the third colour: a calico is a
              black base with an orange third colour)
  mask_b.png  R white markings (chest, belly, paws, muzzle), G pink skin (nose leather, inner ears), B ticking
              (agouti grain), A fur depth (0 between the strands, 1 on their tops; the material darkens the roots)
  fur_n.png   tangent-space normal map (OpenGL) of the same strands: locks, strands and a micro layer flowing along the
              hair (body: back to the tail, legs: down, tail: to the tip, face: radiating from the nose)
  card.png    RGBA strands for the fur cards, alpha = coverage
  eye.png     R iris brightness, G pupil field (names.PUPIL_*), B highlight, A iris radius; laid out for the eyes' UV-sphere mapping
Usage: blender -b --factory-startup --python-exit-code 1 --python tools/blender/cat_bake.py -- <out_dir>"""
import json, math, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_model, cat_rig
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from velvetpaws import names as vpnames

SIZE = 2048
SMALL = 512
MARGIN = 24                 # px, bake margin into the neighbouring faces; beyond it the masks are filled pull-push
CM = 100.0                  # patterns work in centimetres

# ---------------------------------------------------------------------------------------------------------------------
# Rig frames: bone chains as polylines (metres)


def _b(name):
    for b in cat_rig.BONES:
        if b[0] == name: return b
    raise KeyError("cat_rig has no bone %r (the bake's bone chains are out of date)" % name)


# spine from the head joint backwards; segment k carries the weights of SPINE_BONES[k]. The last segment runs along the
# first tail bone (pelvis joint -> tail_01's tail), so the rump stripes continue into the tail root.
SPINE = [_b("head")[2], _b("neck_02")[2], _b("neck_01")[2], _b("spine_03")[2], _b("spine_02")[2], _b("spine_01")[2],
         _b("pelvis")[2], _b("tail_01")[3]]
SPINE_BONES = [("neck_02", "head", "jaw"), ("neck_01",), ("spine_03", "scapula_l", "scapula_r"), ("spine_02",),
               ("spine_01",), ("pelvis", "thigh_l", "thigh_r"), ("tail_01",)]
LEG_BONES = {s: (("finger", "hand", "lowerarm", "upperarm"), ("toe", "foot", "calf", "thigh")) for s in "lr"}
TAIL = [_b("tail_01")[2]] + [_b("tail_%02d" % i)[3] for i in range(1, 9)]


def _leg_chain(bones, side):
    """Paw tip upwards: the first bone's tail, then every bone's head (the arc length starts at the toe tip)."""
    names = [n + "_" + side for n in bones]
    return [_b(names[0])[3]] + [_b(n)[2] for n in names]


LEGS = [_leg_chain(LEG_BONES[s][k], s) for s in "lr" for k in (0, 1)]          # fore l, hind l, fore r, hind r
HEAD_W = ("head", "jaw", "ear_l", "ear_r")
EAR_W = ("ear_l", "ear_r")
LEG_W = tuple(n + "_" + s for s in "lr" for n in LEG_BONES[s][0] + LEG_BONES[s][1])
TAIL_W = tuple("tail_%02d" % i for i in range(1, 9))
REQUIRED_GROUPS = sorted({n for bones in SPINE_BONES for n in bones} | set(HEAD_W) | set(LEG_W) | set(TAIL_W))


def _arc(chain):
    """Cumulative arc length (cm) at every point of a polyline (metres)."""
    C = np.asarray(chain, np.float64)
    return np.concatenate([[0], np.cumsum(np.linalg.norm(C[1:] - C[:-1], axis=1))]) * CM


SHOULDER_ARC = _arc(SPINE)[SPINE.index(_b("spine_03")[2])]     # spine arc (cm) at the withers
TAIL_LEN = _arc(TAIL)[-1]                                       # tail arc (cm) at the tip
FORE_Y, FORE_Z = _b("upperarm_l")[2][1] * CM, _b("upperarm_l")[2][2] * CM   # shoulder joint (cm): front of the chest


def _project(P, chain, clamp=True):
    """Arc length (from the first point) and distance of P (n, 3) to a polyline; per segment, or nearest if clamp."""
    C = np.asarray(chain, np.float64); seg = C[1:] - C[:-1]; L = np.linalg.norm(seg, axis=1)
    cum = np.concatenate([[0], np.cumsum(L)])
    t = np.einsum("nkj,kj->nk", P[:, None, :] - C[None, :-1], seg) / (L * L)
    tc = np.clip(t, 0, 1)
    d = np.linalg.norm(P[:, None, :] - (C[None, :-1] + tc[..., None] * seg[None]), axis=-1)
    s = cum[None, :-1] + (tc if clamp else t) * L[None]
    return s, d


def vertex_frames(obj):
    """Per vertex: (spine arc, leg arc, tail arc) and (head, leg, tail, ear) weights, as float colour attributes.
    Fails loudly if a bone the frames need is missing from the armature or its vertex group from the mesh, or if a
    vertex carries no weight at all (a silent zero would put stripes in the wrong place)."""
    me = obj.data; n = len(me.vertices)
    arm = obj.find_armature()
    if arm is None: raise RuntimeError("%s has no armature" % obj.name)
    missing = [b for b in REQUIRED_GROUPS if b not in arm.data.bones]
    if missing: raise RuntimeError("armature lacks bones %s" % missing)
    names = {g.index: g.name for g in obj.vertex_groups}
    missing = [b for b in REQUIRED_GROUPS if b not in obj.vertex_groups]
    if missing: raise RuntimeError("%s lacks vertex groups %s" % (obj.name, missing))
    P = np.zeros(n * 3); me.vertices.foreach_get("co", P); P = P.reshape(n, 3)
    W = {}
    for v in me.vertices:
        for g in v.groups:
            W.setdefault(names[g.group], np.zeros(n))[v.index] = g.weight
    total = sum(W.values(), np.zeros(n))
    if (total <= 1e-3).any(): raise RuntimeError("%d vertices carry no bone weight" % int((total <= 1e-3).sum()))
    w = lambda bones: sum((W.get(b, np.zeros(n)) for b in bones), np.zeros(n))   # groups checked above; empty = 0
    # spine: per segment unclamped projection, blended by the weights of its bones (smooth around the neck bend).
    # Vertices with no spine weight (head, legs, tail) take the nearest segment; their trunk share is 0, so the
    # body pattern does not use the value, it only keeps the buffer continuous.
    s_seg, _ = _project(P, SPINE, clamp=False)
    ws = np.stack([w(b) for b in SPINE_BONES], 1)
    near = np.argmin(_project(P, SPINE)[1], 1)
    nearest = np.zeros_like(ws); nearest[np.arange(n), near] = 1
    ws = np.where(ws.sum(1, keepdims=True) > 1e-3, ws, nearest)
    spine = (s_seg * ws).sum(1) / ws.sum(1)
    # legs: the leg with the most weight (else the nearest), along it the per-bone projections blended by the bone
    # weights like the spine (a nearest-segment projection jumps at the joints and draws steps into the rings)
    leg_t = np.zeros(n); best = np.full(n, -1.0); near_d = np.full(n, 1e9)
    for k, chain in enumerate(LEGS):
        side, kind = "lr"[k // 2], k % 2
        bones = [b + "_" + side for b in LEG_BONES[side][kind]]
        s_seg, _ = _project(P, chain, clamp=False); s_cl, d = _project(P, chain)
        wl = np.stack([w((b,)) for b in bones], 1); tot = wl.sum(1)
        geo = s_cl[np.arange(n), d.argmin(1)]
        t = np.where(tot > 0.05, (s_seg * wl).sum(1) / np.maximum(tot, 1e-6), geo)
        take = (tot > best + 1e-9) | ((tot <= 1e-6) & (best <= 1e-6) & (d.min(1) < near_d))
        leg_t = np.where(take, t, leg_t); near_d = np.where(take, d.min(1), near_d); best = np.maximum(best, tot)
    # tail: nearest point of the chain (a smooth curve, no steps)
    ts, td = _project(P, TAIL); tail_t = ts[np.arange(n), td.argmin(1)]
    coord = np.stack([spine, leg_t, tail_t, np.ones(n)], 1)
    region = np.stack([w(HEAD_W), w(LEG_W), w(TAIL_W), w(EAR_W)], 1)
    for name, data in (("vp_coord", coord), ("vp_region", region)):
        a = me.color_attributes.new(name, "FLOAT_COLOR", "POINT"); a.data.foreach_set("color", data.astype(np.float32).ravel())


# ---------------------------------------------------------------------------------------------------------------------
# Baking


def _nodes(mat):
    mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear(); return nt


def _sock(node, name, kind):
    """Mix nodes have several sockets of the same name (one per data type)."""
    return next(s for s in node.inputs if s.name == name and s.type == kind and s.enabled)


def _emit_material(name, source):
    """Emission of a vector: 'position' (object space + 1, so it stays positive), 'normal' (* 0.5 + 0.5) or the
    name of a colour attribute."""
    mat = bpy.data.materials.new(name); nt = _nodes(mat)
    if source == "position":
        tc = nt.nodes.new("ShaderNodeTexCoord"); vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "ADD"
        vm.inputs[1].default_value = (1, 1, 1); nt.links.new(tc.outputs["Object"], vm.inputs[0]); out = vm.outputs[0]
    elif source == "normal":
        g = nt.nodes.new("ShaderNodeNewGeometry"); vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "MULTIPLY_ADD"
        vm.inputs[1].default_value = (0.5, 0.5, 0.5); vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(g.outputs["Normal"], vm.inputs[0]); out = vm.outputs[0]
    else:
        at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_type = "GEOMETRY"; at.attribute_name = source; out = at.outputs["Color"]
    em = nt.nodes.new("ShaderNodeEmission"); nt.links.new(out, em.inputs["Color"])
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], o.inputs["Surface"])
    return mat


def _image(name, size, fill, float_buffer):
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color"            # masks, buffers and the normal map are data, not colour
    img.pixels.foreach_set(np.tile(np.asarray(fill, np.float32), size * size))
    return img


def _bake(obj, mat, img, normal=False):
    obj.data.materials.clear(); obj.data.materials.append(mat)
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img; mat.node_tree.nodes.active = tex
    bk = bpy.context.scene.render.bake
    bk.use_clear = False; bk.margin = MARGIN; bk.margin_type = "ADJACENT_FACES"; bk.target = "IMAGE_TEXTURES"
    if normal: bk.normal_space = "TANGENT"
    bpy.ops.object.bake(type="NORMAL" if normal else "EMIT", margin=MARGIN, use_clear=False)
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32); img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)            # row 0 = bottom (v = 0), as Blender stores it


def fur_object(src):
    """A copy of the Fur slot alone (eyes and cards have their own textures and overlapping UVs), unparented."""
    me = src.data.copy(); bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != 0], context="FACES"); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("fur_bake", me); bpy.context.scene.collection.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    return o


def geometry_buffers(obj):
    """Per texel: position (m), normal, vp_coord, vp_region, valid (the texel was baked, incl. the margin)."""
    out = {}
    for key in ("position", "normal", "vp_coord", "vp_region"):
        img = _image("_" + key, SIZE, (0, 0, 0, 0), True)
        out[key] = _bake(obj, _emit_material("_" + key, key), img)
    valid = out["position"][..., 3] > 0.5
    out["position"] = out["position"][..., :3] - 1.0
    # the margin wraps over the image border (rows/columns 0..1) with blended values far outside the cat: drop texels
    # outside the mesh's bounds (+ 1 cm); the pull-push fill covers them like any empty texel
    bb = np.array([c[:] for c in obj.bound_box]); lo, hi = bb.min(0) - 0.01, bb.max(0) + 0.01
    valid &= ((out["position"] >= lo) & (out["position"] <= hi)).all(-1)
    n = out["normal"][..., :3] * 2 - 1; out["normal"] = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    out["vp_coord"] = out["vp_coord"][..., :3]
    out["valid"] = valid
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Procedural noise (numpy): gradient noise, fBm, cellular spots


_RNG = np.random.default_rng(20261114)
_PERM = np.concatenate([_RNG.permutation(256)] * 2)
_GRAD = np.array([(1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0), (1, 0, 1), (-1, 0, 1), (1, 0, -1), (-1, 0, -1),
                  (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1)] * 2, np.float32)[:16]


def _hash(i, j, k):
    return _PERM[_PERM[_PERM[i & 255] + (j & 255)] + (k & 255)]


def noise(p, seed=0):
    """Gradient noise, about -1..1, unit feature size (p in feature units)."""
    p = p + np.float32(seed * 17.31)
    i = np.floor(p).astype(np.int64); f = (p - i).astype(np.float32); u = f * f * f * (f * (f * 6 - 15) + 10)
    res = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                g = _GRAD[_hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz) & 15]
                dot = (g * (f - np.array((dx, dy, dz), np.float32))).sum(1)
                wx = u[:, 0] if dx else 1 - u[:, 0]; wy = u[:, 1] if dy else 1 - u[:, 1]; wz = u[:, 2] if dz else 1 - u[:, 2]
                res = res + dot * wx * wy * wz
    return res * 1.4


def fbm(p, octaves=3, seed=0):
    tot, amp, norm = 0, 1.0, 0
    for o in range(octaves):
        tot = tot + amp * noise(p * (2.0 ** o), seed + o); norm += amp; amp *= 0.5
    return tot / norm


def cells(p, seed=0):
    """Jittered-grid spots: distance to the nearest cell centre divided by that cell's own radius factor (0.7..1.3)."""
    i = np.floor(p).astype(np.int64); best = np.full(len(p), 1e9, np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = i + np.array((dx, dy, dz))
                h = _hash(c[:, 0] + seed, c[:, 1] + 3 * seed, c[:, 2])
                h2 = _hash(c[:, 0] + 101, c[:, 1] + seed, c[:, 2] + 57); h3 = _hash(c[:, 0] + 7, c[:, 1] + 211, c[:, 2] + seed)
                jit = np.stack([h, h2, h3], 1).astype(np.float32) / 255.0
                rad = 0.7 + 0.6 * (_hash(c[:, 0] + 31, c[:, 1] + 17, c[:, 2] + 5 + seed).astype(np.float32) / 255.0)
                best = np.minimum(best, np.linalg.norm(p - (c + 0.15 + 0.7 * jit), axis=1) / rad)
    return best


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)


def _tube(P, pts, r):
    return cat_model._sd_tube(P.astype(np.float32), pts, r)


# ---------------------------------------------------------------------------------------------------------------------
# Patterns. Arguments: g = dict of per-texel arrays (valid texels only): p (cm, object space), h (cm, head-local:
# x lateral, y back from the nose tip, z up), n (normal), spine / leg / tail (arc lengths, cm), w_head / w_leg /
# w_tail / w_ear (bone weight shares), v (trunk height: 0 belly line, 1 top line).


def _mass(name):
    m = next(m for m in cat_model.HEAD_MASSES if m[0] == name); return m


def _streak(g):
    """Hair streaks: noise stretched along the hair (y on body, head and tail, z on the legs), about -1..1."""
    p = g["p"]
    a = fbm(p * np.array((1 / 0.175, 1 / 1.12, 1 / 0.175), np.float32), 2, 61)
    b = fbm(p * np.array((1 / 0.175, 1 / 0.175, 1 / 1.12), np.float32), 2, 62)
    return a * (1 - g["w_leg"]) + b * g["w_leg"]


def trunk_height(p):
    """0 on the trunk's belly line, 1 on its top line, at the texel's y (cat_model.TRUNK, y clamped to the trunk)."""
    T = sorted(cat_model.TRUNK, key=lambda r: r[0]); ys = np.array([r[0] for r in T]) * CM
    top = np.interp(p[:, 1], ys, [r[1] * CM for r in T]); bot = np.interp(p[:, 1], ys, [r[2] * CM for r in T])
    return np.clip((p[:, 2] - bot) / (top - bot), 0, 1)


def _lines(phase, period, width, soft, rag):
    """Soft dark lines across `phase` (cm): one line `width` cm wide every `period` cm, edges `soft` cm, the edge
    shifted by `rag` (cm, per texel). Returns the mask (0..1) and each texel's line index."""
    f = phase / period; k = np.round(f)
    return smooth(soft, -soft, np.abs(f - k) * period - 0.5 * width + rag), k


def _per_line(p, k, scale, seed):
    """Noise that differs from line to line (k) and varies along each line (x, z), about -1..1."""
    return fbm(np.stack([p[:, 0] / scale, k * 2.37, p[:, 2] / scale], 1).astype(np.float32), 2, seed)


def tabby(g):
    """Mackerel tabby on an agouti ground. Body: narrow dark lines (0.6-1.0 cm) every 2.6 cm across the spine, wavy,
    broken into segments, here and there a thinner line between them (forks), widest and densest along the back,
    fading out down the flank into a few spots on the belly; a dorsal band of three parallel lines from the nape to
    the tail root; necklaces across the chest. Legs: thin broken bars on the outside, none on the paws. Tail: rings
    and a dark tip. Head: thin lines over the crown, the 'M' with its strokes down to the inner eye corners, dark eye
    rims, two cheek lines. Soft edges, ragged along the hair."""
    p, n, h, v = g["p"], g["n"], g["h"], g["v"]
    st = _streak(g); rag = 0.07 * st
    warp = fbm(p / 6.0, 2, 1) * 1.1 + fbm(p / 2.0, 2, 2) * 0.35
    # body
    s0 = g["spine"] * CM
    s = s0 + warp + (1.1 - 0.5 * v) * fbm(p / 2.8, 2, 9) \
        + 0.45 * np.sin(2 * math.pi * s0 / 7.3 + 2.0 * fbm(p / 8.0, 1, 8))         # uneven spacing, wavy lines
    wid = 0.75 * (0.75 + 0.3 * v) * (1 + 0.3 * fbm(p / 3.0, 1, 10))             # 0.5-1.0 cm, narrower down the flank
    chest = smooth(FORE_Y + 1.0, FORE_Y - 1.5, p[:, 1]) * smooth(0.0, -0.35, n[:, 1])      # front of the chest
    thr = -0.6 + 0.6 * (1 - v) - 0.5 * chest                                     # more gaps lower down
    gate = smooth(thr, thr + 0.3, _per_line(p, np.round(s / 2.6), 1.5, 12))     # segments, tapering at their ends
    line, k = _lines(s, 2.6, wid * gate * (1 - 0.35 * chest), 0.16, rag)       # necklaces thinner
    line = line * smooth(0.0, 0.3, gate)
    fgate = smooth(0.3, 0.55, _per_line(p, np.round((s + 1.3) / 2.6), 1.8, 13))
    fork, _ = _lines(s + 1.3, 2.6, 0.4 * wid * fgate, 0.12, rag)
    fork = fork * smooth(0.0, 0.3, fgate)
    # the nape (top of the neck, up to the withers) has lines running along it instead, five across
    nape = smooth(SHOULDER_ARC - 1.0, SHOULDER_ARC - 3.0, s0) * smooth(2.6, 2.0, np.abs(p[:, 0])) * smooth(0.5, 0.7, v)
    nl, _ = _lines(p[:, 0] + 0.25 * warp, 0.85, 0.32, 0.08, rag)
    body = np.maximum(line, 0.85 * fork) * np.maximum(smooth(0.15, 0.5, v), chest) * (1 - nape) + nl * nape
    q = p + np.stack([fbm(p / 2.0, 2, 24), fbm(p / 2.0, 2, 25), fbm(p / 2.0, 2, 26)], 1) * 0.8
    bs = cells((q / np.array((1.5, 2.3, 1.3), np.float32)).astype(np.float32), 9)
    body = np.maximum(body, 0.7 * smooth(0.34, 0.22, bs + 0.1 * st) * smooth(0.35, 0.12, v) * (1 - chest))  # belly spots
    x = np.abs(p[:, 0] + 0.15 * warp)
    band, _ = _lines(x, 0.95, 0.42, 0.1, rag)
    band = np.maximum(band * smooth(1.55, 1.3, x), 0.55 * smooth(1.3, 0.9, x))
    body = np.maximum(body, band * smooth(0.8, 0.92, v) * smooth(SHOULDER_ARC - 3.0, SHOULDER_ARC - 1.0, s0))
    body = np.maximum(body, 0.18 * smooth(0.6, 0.95, v))                          # the back is darker overall
    # legs: thin bars across, on the outside, broken; none on the paws, fading into the body above
    t = g["leg"] * CM + 0.4 * warp
    outer = smooth(0.0, 0.45, np.sign(p[:, 0]) * n[:, 0] - 0.25 * n[:, 1])
    bar, kb = _lines(t, 1.7, 0.5, 0.1, rag)
    bar = bar * smooth(-0.35, -0.2, _per_line(p, kb, 1.0, 14))
    leg = bar * outer * smooth(3.2, 4.2, t) * smooth(20.0, 15.0, t)
    # tail: rings, a dark tip, a dark line along the top joining the dorsal band
    tt = g["tail"] * CM + 0.4 * warp
    ring, _ = _lines(tt, 2.5, 1.0, 0.15, rag)
    ring = ring * smooth(1.0, 3.0, tt)
    ttop = smooth(0.55, 0.85, n[:, 2]) * smooth(1.0, 0.6, np.abs(p[:, 0]) / 0.7) * smooth(9.0, 5.0, tt)
    tail = np.maximum.reduce([ring, smooth(TAIL_LEN - 3.5, TAIL_LEN - 2.5, tt), ttop])
    # head (head-local cm)
    x, y, z = h[:, 0], h[:, 1], h[:, 2]; hw = fbm(h / 1.2, 2, 5) * 0.08 + 0.04 * st
    ey = cat_model.EYE_AT; inner = ey[0] - cat_model.EYE_OPEN[0]                 # x of the inner eye corner
    lam = 0.5 + 0.1 * np.clip(y - 3.5, 0, None)                                 # lines fan out over the crown
    top = smooth(3.4, 3.8, z + 0.35 * np.clip(3.2 - y, 0, None)) * smooth(-0.2, 0.3, n[:, 2] - 0.3 * n[:, 1])
    lines = smooth(0.35, 0.85, np.cos(2 * math.pi * (x + hw) / lam) + 0.3 * st) * smooth(1.9, 1.4, np.abs(x) - 0.1 * (y - 3)) * top
    m = np.zeros_like(x)
    F = h.copy(); F[:, 1] = 0                                                    # front view (x, z)
    Sd = h.copy(); Sd[:, 0] = 0                                                  # side view (y, z)
    for sx in (1, -1):
        front = smooth(0.0, 0.3, -n[:, 1]) * (np.sign(x) == sx) * smooth(5.0, 4.2, y)
        # the M: up from the inner eye corner to its peak, down into the valley, up to the forehead's middle line
        arc = _tube(F, [(sx * (inner + 0.07), 0, ey[2] + 0.35), (sx * (inner - 0.1), 0, ey[2] + 1.6),
                        (sx * 0.42, 0, ey[2] + 0.95), (sx * 0.12, 0, ey[2] + 1.45), (sx * 0.1, 0, ey[2] + 2.0)], 0.1)
        liner = cat_model._sd_almond(h.astype(np.float32), Vector((sx * ey[0], ey[1], ey[2])),
                                     cat_model._gaze(sx), sx)
        side = smooth(0.1, 0.45, sx * n[:, 0]) * (sx * x > 1.2)
        cheek1 = _tube(Sd, [(0, ey[1] + 0.45, ey[2] + 0.1), (0, ey[1] + 1.2, ey[2] - 0.1), (0, ey[1] + 2.2, ey[2] - 0.25),
                            (0, ey[1] + 2.8, ey[2] - 0.15)], 0.1)
        cheek2 = _tube(Sd, [(0, ey[1] + 0.3, ey[2] - 0.95), (0, ey[1] + 1.1, ey[2] - 1.2), (0, ey[1] + 1.9, ey[2] - 1.1),
                            (0, ey[1] + 2.6, ey[2] - 0.75)], 0.1)
        near_eye = np.linalg.norm(h - np.array((sx * ey[0], ey[1], ey[2]), np.float32), axis=1) < 2.0
        m = np.maximum.reduce([m, smooth(0.12, -0.04, arc + hw) * front,
                               smooth(0.08, -0.04, cheek1 + hw) * side, smooth(0.08, -0.04, cheek2 + hw) * side,
                               0.85 * smooth(0.13, 0.04, liner) * near_eye])          # lid rims: a thin dark line
    head = np.maximum.reduce([lines * smooth(1.6, 2.2, y),                     # nose bridge and muzzle stay plain
                              m, body * smooth(5.5, 7.5, y)])                  # the neck behind the skull: body lines
    return _blend(g, body, leg, tail, head)


def _blend(g, body, leg, tail, head):
    wh, wl, wt = g["w_head"], g["w_leg"], g["w_tail"]
    wb = np.clip(1 - wh - wl - wt, 0, 1)
    return np.clip(wb * body + wl * leg + wt * tail + wh * head, 0, 1)


def brindle(g):
    """Fine streaks along the hair: body, head and tail stretched along y, legs along z."""
    p = g["p"]
    along_y = fbm(p * np.array((1 / 0.35, 1 / 1.6, 1 / 0.35), np.float32), 3, 11)
    along_z = fbm(p * np.array((1 / 0.35, 1 / 0.35, 1 / 1.6), np.float32), 3, 12)
    v = along_y * (1 - g["w_leg"]) + along_z * g["w_leg"] + 0.25 * fbm(p / 4.0, 2, 13)
    return smooth(0.0, 0.12, v)


def spots(g, tabby_mask):
    """Spotted tabby: round to oval spots (1.5-2.5 cm, a little longer along the body) on the trunk, lining up in
    loose rows; head, legs and tail keep the tabby lines and rings."""
    p = g["p"]; q = p + np.stack([fbm(p / 3.0, 2, 21), fbm(p / 3.0, 2, 22), fbm(p / 3.0, 2, 23)], 1) * 0.45
    q = q / np.array((2.3, 3.0, 2.3), np.float32)
    d = cells(q.astype(np.float32), 5)
    body = smooth(0.5, 0.43, d)
    low = smooth(-0.3, -0.7, g["n"][:, 2]); body = body * (1 - 0.5 * low)
    wb = np.clip(1 - g["w_head"] - g["w_leg"] - g["w_tail"], 0, 1)
    return np.clip(wb * body + (1 - wb) * tabby_mask, 0, 1)


def patches(g):
    """Tricolour: large patches (6 cm noise), orange where >= 0.5, black below; the borders slightly ragged."""
    p = g["p"]
    v = fbm(p / 6.0, 3, 31) + 0.12 * fbm(p / 0.9, 2, 32)
    return smooth(-0.03, 0.03, v)


def white_parts(g):
    """White markings by part: belly, chest bib (below and in front of the shoulder joint), throat, paws (socks),
    muzzle (whisker pads and chin from the head masses)."""
    p, n, h = g["p"], g["n"], g["h"]; edge = 0.25 * fbm(p / 1.8, 2, 41)
    wh, wl, wt = g["w_head"], g["w_leg"], g["w_tail"]; trunk = np.clip(1 - wh - wl - wt, 0, 1)
    belly = smooth(-0.25, -0.45, n[:, 2] + edge) * (trunk + wl * smooth(7.0, 5.5, g["leg"] * CM))
    chest = smooth(-0.1, -0.35, n[:, 1] + edge) * smooth(FORE_Z + 1.5, FORE_Z - 0.5, p[:, 2] + 2 * edge) \
        * smooth(FORE_Y + 3.0, FORE_Y + 1.0, p[:, 1]) * (1 - wl)
    throat = smooth(-0.6, -1.0, h[:, 2] + edge * 2) * smooth(9.5, 8.0, h[:, 1]) * wh * smooth(0.0, -0.4, n[:, 2])
    paws = smooth(3.4, 2.8, g["leg"] * CM + 1.5 * edge) * wl
    hf = h.astype(np.float32); muzzle = np.zeros(len(h), np.float32)
    for name in ("pad", "chin", "muzzle"):
        _, c, r, rot, _, pair = _mass(name)
        for sx in ((1, -1) if pair else (1,)):
            sd = cat_model._sd_ellipsoid(hf, (sx * c[0], c[1], c[2]), r, (rot[0], sx * rot[1], sx * rot[2]))
            reach = 0.2 if name != "muzzle" else -0.15
            lower = 1.0 if name != "muzzle" else smooth(0.4, 0.0, h[:, 2])
            muzzle = np.maximum(muzzle, smooth(reach + 0.08, reach - 0.08, sd + 0.3 * edge) * lower)
    muzzle = muzzle * (1 - nose_leather(g)) * wh
    return dict(belly=belly, chest=chest, throat=throat, paws=paws, muzzle=muzzle)


def white(g):
    return np.clip(np.maximum.reduce(list(white_parts(g).values())), 0, 1)


def nose_leather(g):
    sd = cat_model._sd_nose(g["h"].astype(np.float32))
    return smooth(0.09, 0.03, sd) * smooth(1.2, 0.9, g["h"][:, 1])


def ear_cup_centre(side):
    """Head-local cm of the middle of an ear's cup (cat_model.EAR frame): the reference for the placement check."""
    e = cat_model.EAR; up = np.array(cat_model._ear_frame(side)[0])
    return np.array((side * e["base"][0], e["base"][1], e["base"][2])) + up * e["height"] * 0.62


def inner_ear(g, side):
    """The cup of one ear (side 1 = left, x > 0): in the ear frame (cat_model.EAR), above the base, facing the
    opening (forward)."""
    p, n = g["p"] / CM, g["n"]; e = cat_model.EAR
    up, fwd, across = cat_model._ear_frame(side)
    base = np.array(cat_model._hp((side * e["base"][0], e["base"][1], e["base"][2])))
    q = p - base; v = q @ np.array(up) / (e["height"] * cat_model.HS / 100); a = np.abs(q @ np.array(across)) / (e["w"] * cat_model.HS / 100)
    facing = n @ np.array(fwd)
    k = (1 - np.clip(v, 0, 1)) ** e["taper"]
    out = smooth(0.3, 0.42, v) * smooth(0.95, 0.85, v) * smooth(0.25, 0.5, facing) \
        * smooth(0.9, 0.7, a / np.maximum(k, 0.05))
    return out * g["w_ear"].clip(0, 1) ** 0.5


def skin(g):
    return np.maximum.reduce([nose_leather(g), inner_ear(g, 1), inner_ear(g, -1)])


def ticking(g):
    """Agouti grain: banded hairs make the ground a fine salt and pepper. Strands about 1 mm across and 4 mm long along
    the hair (backwards on body, head and tail, down the legs), gathered in loose clumps; 1 = dark hair tips."""
    p = g["p"]
    a = noise((p * np.array((1 / 0.09, 1 / 0.38, 1 / 0.09), np.float32)).astype(np.float32), 51)
    b = noise((p * np.array((1 / 0.09, 1 / 0.09, 1 / 0.38), np.float32)).astype(np.float32), 52)
    hair = a * (1 - g["w_leg"]) + b * g["w_leg"]
    return np.clip(0.5 + 1.2 * hair + 0.45 * fbm(p / 0.6, 2, 53), 0, 1)


# ---------------------------------------------------------------------------------------------------------------------
# Fur: a height field of strands flowing along the hair (numpy, per texel), turned into the tangent-space normal map
# and stored as fur depth in mask_b.A (0 = down between the strands, 1 = strand tops; M_VP_CatFur darkens the roots).

NOSE_ORIGIN = (0.0, 0.6, 0.25)      # head-local cm: the face hair radiates from here (just behind the nose leather)
# (strand width cm, strand length cm, LIC samples, amplitude): clumps (locks of hair), strands, a fine micro layer
FUR_LAYERS = ((0.22, 1.6, 8, 0.85), (0.06, 0.7, 12, 1.0), (0.045, 0.3, 7, 0.45))
FUR_RELIEF = 0.060                  # cm of height for a unit of the summed layers (sets the slope of the strands)


def hair_direction(g):
    """Unit hair direction per texel, in the surface: back along the body (and a little down the flanks), down the legs,
    along the tail towards the tip, radiating from the nose over the face and back over the skull."""
    p, n, h = g["p"], g["n"], g["h"]; N = len(p)
    body = np.stack([np.zeros(N), np.ones(N), -0.25 - 0.35 * (1 - g["v"])], 1)
    leg = np.tile(np.array((0.0, 0.25, -1.0)), (N, 1))
    T = np.asarray(TAIL, np.float64) * CM; seg = T[1:] - T[:-1]; cum = _arc(TAIL)
    k = np.clip(np.searchsorted(cum, g["tail"] * CM) - 1, 0, len(seg) - 1); tail = seg[k]
    face = h - np.asarray(NOSE_ORIGIN, np.float32); face[:, 1] = np.maximum(face[:, 1], 0.4 * np.linalg.norm(face, axis=1))
    face /= np.maximum(np.linalg.norm(face, axis=1, keepdims=True), 1e-6)
    unit = lambda a: a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-6)
    wh, wl, wt = g["w_head"][:, None], g["w_leg"][:, None], g["w_tail"][:, None]
    d = np.clip(1 - wh - wl - wt, 0, 1) * unit(body) + wl * unit(leg) + wt * unit(tail) + wh * face
    d = d - n * (d * n).sum(1, keepdims=True)
    bad = np.linalg.norm(d, axis=1) < 1e-3
    d[bad] = np.cross(n[bad], np.array((1.0, 0, 0)))
    return unit(d).astype(np.float32)


def fur_height(g):
    """Strands as line integral convolution: isotropic noise averaged along the hair direction gives streaks along it;
    three scales (locks, strands, micro). About 0..1, 1 = the tops of the strands."""
    p = g["p"].astype(np.float32); d = hair_direction(g); H = np.zeros(len(p), np.float32)
    for li, (w, L, k, amp) in enumerate(FUR_LAYERS):
        acc = np.zeros(len(p), np.float32)
        for s in np.linspace(-0.5, 0.5, k):
            acc += noise((p + d * np.float32(s * L)) / np.float32(w), 70 + li)
        acc /= k ** 0.5                           # the average of k samples shrinks with sqrt(k): keep unit contrast
        H += amp * np.tanh(1.6 * acc)
    H /= sum(a for *_, a in FUR_LAYERS)
    return np.clip(0.5 + 0.5 * H, 0, 1)


def fur_normal(buf, idx, height):
    """Tangent-space normal map (OpenGL: R along +u, G along +v, as Blender bakes it) from the height field: the slope of
    the height along u and v per texel over the surface distance of a texel (from the baked positions). Neighbours across a
    UV island border (a jump in position) count as missing; such texels take a one-sided slope or none."""
    valid = buf["valid"]; P = buf["position"] * CM
    Hm = np.zeros(valid.shape, np.float32); Hm[idx] = height * FUR_RELIEF / 1.0
    def slope(axis):
        fwd = np.roll(Hm, -1, axis) - Hm; bwd = Hm - np.roll(Hm, 1, axis)
        pf = np.linalg.norm(np.roll(P, -1, axis) - P, axis=-1); pb = np.linalg.norm(P - np.roll(P, 1, axis), axis=-1)
        step = np.median(pf[valid & np.roll(valid, -1, axis)])
        okf = valid & np.roll(valid, -1, axis) & (pf < 4 * step) & (pf > 1e-6)
        okb = valid & np.roll(valid, 1, axis) & (pb < 4 * step) & (pb > 1e-6)
        sf = np.where(okf, fwd / np.maximum(pf, 1e-6), 0); sb = np.where(okb, bwd / np.maximum(pb, 1e-6), 0)
        cnt = okf.astype(np.float32) + okb
        return (sf + sb) / np.maximum(cnt, 1), step
    su, step_u = slope(1); sv, step_v = slope(0)
    print("BAKE fur texel %.3f x %.3f mm" % (step_u * 10, step_v * 10))
    N = np.stack([-su, -sv, np.ones_like(su)], -1); N /= np.linalg.norm(N, axis=-1, keepdims=True)
    img = np.concatenate([N * 0.5 + 0.5, np.ones(valid.shape + (1,), np.float32)], -1)
    flat = np.zeros_like(img); flat[...] = (0.5, 0.5, 1.0, 1.0)
    img = np.where(valid[..., None], img, flat)
    out = _fill(img, valid); n = out[..., :3] * 2 - 1
    out[..., :3] = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6) * 0.5 + 0.5
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Painted textures, filling, saving


def paint_card(path):
    """Strand texture: 70 fine tapered hairs along V (curving a little, of different lengths), loose enough that the fur under
    the card shows between them; alpha = coverage, fading in over the first 6 % (no edge at the skin) and towards each tip;
    colour = the strand shade, a little lighter at the roots (agouti) and darker at the tips."""
    rng = np.random.default_rng(7); img = np.zeros((SMALL, SMALL, 4), np.float32)
    v = np.linspace(0, 1, SMALL)[:, None]; u = np.linspace(0, 1, SMALL)[None, :]
    for _ in range(70):
        u0 = rng.uniform(0.04, 0.96); bend = rng.uniform(-0.12, 0.12); end = rng.uniform(0.5, 1.0)
        width = rng.uniform(0.0025, 0.0055) * (1 - 0.7 * v / end) + 0.0012
        d = np.abs(u - (u0 + bend * v ** 2))
        a = np.clip(1 - d / width, 0, 1) * smooth(end, end * 0.7, v)
        img[..., 3] = np.maximum(img[..., 3], a)
    img[..., 3] *= smooth(0.0, 0.06, v)
    img[..., :3] = (0.95 - 0.25 * v)[..., None]
    _save(img, path)                                  # row 0 = v 0 (Blender's pixel order)


def paint_eye(path):
    """The eyes are UV spheres whose v = 1 pole looks out along the gaze (cat_model.build_eyes): v is the angle from
    the front (v = 1 front, 0 back), u the angle around it with u = 0.75 pointing up. Iris over the front 58 degrees:
    R iris brightness (radial fibres, a little lighter in the outer half, a dark limbal ring at its edge), G the pupil field
    (the opening at which a texel turns pupil, names.PUPIL_*: M_VP_CatEye's PupilOpen draws a slit at 0, a vertical ellipse in
    between, nearly round at 1), B a small highlight up and outwards, A the iris radius (0 centre .. 1 limbus; the material deepens
    the eye colour towards the pupil; 0.05 at the centre, never 0)."""
    v, u = np.mgrid[0:SMALL, 0:SMALL] / (SMALL - 1.0)
    th = (1 - v) * math.pi; ph = 2 * math.pi * (u - 0.75)
    r = np.sin(np.minimum(th, math.pi / 2)) * (th < math.pi / 2) + (th >= math.pi / 2)
    xh, yv = r * np.sin(ph), r * np.cos(ph)                       # horizontal, vertical across the front
    rad = th / math.radians(58)
    fib = 0.5 + 0.5 * np.sin(ph * 46 + 3 * np.sin(ph * 7)) * np.sin(ph * 13 + 1.0)
    fib2 = 0.5 + 0.5 * np.sin(ph * 83 + 2 * np.sin(ph * 11 + 0.7))
    iris = (0.70 + 0.18 * fib * smooth(0.15, 0.5, rad) + 0.08 * fib2 * smooth(0.3, 0.7, rad)) * (0.82 + 0.18 * smooth(0.25, 0.7, rad))
    limbus = 1 - 0.85 * smooth(0.84, 0.97, rad)                   # dark limbal ring (mammal eye: a clear dark edge to the iris)
    iris = np.clip(iris * limbus * smooth(1.06, 0.97, rad), 0, 1)
    W0, W1 = vpnames.PUPIL_W; H = vpnames.PUPIL_H; e0, e1 = vpnames.PUPIL_ENC
    q = np.abs(xh) / np.sqrt(np.clip(1 - (yv / H) ** 2, 1e-6, 1))
    o = np.where((np.abs(yv) < H) & (th < math.pi / 2), (q - W0) / (W1 - W0), 99.0)    # the opening at which this texel is pupil
    pupil = np.clip((o + e0) / e1, 0, 1)
    glint = smooth(0.04, 0.02, np.hypot(xh - 0.22, yv - 0.25)) * (th < math.pi / 2)
    # A never 0: UE's PNG import refills the RGB of fully transparent texels (it would wipe the pupil field at the centre)
    _save(np.dstack([iris, pupil, glint, 0.05 + 0.95 * np.clip(rad, 0, 1)]).astype(np.float32), path)


def _fill(img, valid):
    """Pull-push: empty texels take the average of the nearest baked ones (no seams at low mips). The image must be
    square with a power-of-two side (SIZE), so every level halves exactly down to 1 x 1."""
    assert img.shape[0] == img.shape[1] and img.shape[0] & (img.shape[0] - 1) == 0, img.shape
    levels = [(img * valid[..., None], valid.astype(np.float32))]
    while levels[-1][1].shape[0] > 1:
        c, w = levels[-1]; H = c.shape[0] // 2
        c2 = c.reshape(H, 2, H, 2, -1).sum((1, 3)); w2 = w.reshape(H, 2, H, 2).sum((1, 3)); levels.append((c2, w2))
    up = levels[-1][0] / np.maximum(levels[-1][1], 1e-6)[..., None]
    for c, w in reversed(levels[:-1]):
        up = np.repeat(np.repeat(up, 2, 0), 2, 1)
        own = c / np.maximum(w, 1e-6)[..., None]; up = np.where((w > 0)[..., None], own, up)
    return np.where(valid[..., None], img, up)


def _save(arr, path):
    """arr (h, w, 4) float 0..1, row 0 = bottom (Blender order)."""
    h, w, _ = arr.shape; img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.colorspace_settings.name = "Non-Color"; img.pixels.foreach_set(np.ascontiguousarray(arr, np.float32).ravel())
    img.filepath_raw = path; img.file_format = "PNG"; img.save()


EXPECTED = ("mask_a.png", "mask_b.png", "fur_n.png", "card.png", "eye.png")


def texel_data(buf):
    """The per-texel arrays the patterns take (valid texels only) and their image indices."""
    valid = buf["valid"]; idx = np.nonzero(valid)
    pos = buf["position"][idx].astype(np.float32)
    g = {"p": pos * CM, "n": buf["normal"][idx].astype(np.float32),
         "h": (pos - np.asarray(cat_model.HEAD_AT, np.float32)) * CM / cat_model.HS}
    c, r = buf["vp_coord"][idx], buf["vp_region"][idx]
    g.update(spine=c[:, 0], leg=c[:, 1], tail=c[:, 2], w_head=r[:, 0], w_leg=r[:, 1], w_tail=r[:, 2], w_ear=r[:, 3])
    # up-facing texels count as back too: between the shoulder blades the spine lies below the section's top line
    g["v"] = np.maximum(trunk_height(g["p"]), smooth(0.5, 0.95, g["n"][:, 2]))
    return g, idx


def _region(mask, g):
    """Texels of a region (mask >= 0.5) and their mean position, object and head-local, cm."""
    sel = mask >= 0.5; out = {"texels": int(sel.sum())}
    if sel.any():
        out["mean_cm"] = [round(float(c), 2) for c in g["p"][sel].mean(0)]
        out["mean_head_cm"] = [round(float(c), 2) for c in g["h"][sel].mean(0)]
    return out


def regions(g, tab):
    """Placement statistics for tests/test_textures.py: where the skin, white and tabby regions landed, next to the
    model's own reference points."""
    trunk = np.clip(1 - g["w_head"] - g["w_leg"] - g["w_tail"], 0, 1) > 0.9
    back, belly = trunk & (g["v"] > 0.85), trunk & (g["v"] < 0.15)
    out = {"nose_leather": _region(nose_leather(g), g),
           "inner_ear_l": _region(inner_ear(g, 1), g), "inner_ear_r": _region(inner_ear(g, -1), g)}
    out.update({"white_" + k: _region(m, g) for k, m in white_parts(g).items()})
    out["tabby"] = {"back_mean": round(float(tab[back].mean()), 3), "belly_mean": round(float(tab[belly].mean()), 3),
                    "back_texels": int(back.sum()), "belly_texels": int(belly.sum())}
    out["ref"] = {"ear_cup_l_head_cm": [round(float(c), 2) for c in ear_cup_centre(1)],
                  "ear_cup_r_head_cm": [round(float(c), 2) for c in ear_cup_centre(-1)],
                  "shoulder_joint_cm": [0.0, round(FORE_Y, 2), round(FORE_Z, 2)],
                  "texels": int(len(g["p"]))}
    return out


def lid_margin(g):
    """The lid margins (0..1): a band about 1.2 mm wide just outside each lid opening (cat_model._sd_almond, head-local cm)."""
    h = g["h"]; ey = cat_model.EYE_AT; out = np.zeros(len(h), np.float32)
    for sx in (1, -1):
        c = np.array((sx * ey[0], ey[1], ey[2]), np.float32)
        d = cat_model._sd_almond(h.astype(np.float32), Vector(c), cat_model._gaze(sx), sx)
        out = np.maximum(out, smooth(0.12, 0.05, d) * (np.linalg.norm(h - c, axis=1) < 2.0))
    return out


def masks(buf):
    """mask_a and mask_b (filled images) and the placement statistics."""
    valid = buf["valid"]; g, idx = texel_data(buf)
    t = tabby(g)
    chans_a = [t, brindle(g), spots(g, t), patches(g)]
    fur = fur_height(g)
    # depth with full contrast; at the lid margins down to the roots (dark rim on every coat, not only where the tabby lines are)
    lid = lid_margin(g)
    chans_b = [white(g), skin(g), np.maximum(ticking(g), lid), np.clip(0.5 + 2.2 * (fur - 0.5), 0, 1) * (1 - lid)]
    out = []
    for chans in (chans_a, chans_b):
        img = np.zeros((SIZE, SIZE, 4), np.float32)
        img[idx] = np.stack(chans, 1)
        out.append(np.clip(_fill(img, valid), 0, 1))
    return out[0], out[1], regions(g, t), fur_normal(buf, idx, fur)


def main(out):
    tex = os.path.join(out, "tex"); os.makedirs(tex, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "cat.blend"))
    sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
    src = bpy.data.objects["SK_VP_Cat"]
    vertex_frames(src)
    obj = fur_object(src)
    buf = geometry_buffers(obj)
    print("BAKE texels %.3f of the image" % buf["valid"].mean())
    a, b, reg, nmap = masks(buf)
    _save(a, os.path.join(tex, "mask_a.png")); _save(b, os.path.join(tex, "mask_b.png"))
    with open(os.path.join(tex, "regions.json"), "w") as fh: json.dump(reg, fh, indent=1)
    _save(nmap, os.path.join(tex, "fur_n.png"))
    paint_card(os.path.join(tex, "card.png")); paint_eye(os.path.join(tex, "eye.png"))
    missing = [f for f in EXPECTED if not os.path.isfile(os.path.join(tex, f))]
    if missing: raise RuntimeError("bake did not write %s" % missing)
    print("BAKE OK %d" % len(EXPECTED))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
