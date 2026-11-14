"""Blender side of the cat animations: CatRig solves cat_motion poses onto the rig of cat.blend (own IK, every bone keyed every
frame), export with a pinned FBX timestamp and stable ids (byte-identical files), measures and review tiles.

The armature is used as cat_anims.py leaves it: scaled x100 with the scale applied, so armature space is in centimetres (CM = 1),
the cat faces -Y. A pose is a delta rotation in armature space on top of the rest (M = T(p) Q R0), chain by chain; legs by an own
two-bone IK whose pole is the rest bend carried by the body, so the all-zero pose (cat_poses.STAND) gives the rest exactly."""
import math, os, sys
import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_motion as M
import cat_rig
from fbx_stable import fixed_fbx_time   # noqa: F401  (cat_anims calls L.fixed_fbx_time)

CM = 1.0              # armature units per cm (x100 applied: bones in cm)
STRAIGHT = 177.0      # IK stretches a leg to this joint angle at most; the rest goes into CatRig.miss
TAIL = ["tail_%02d" % (i + 1) for i in range(8)]
JOINTS = ("pelvis", "head", "hand_l", "foot_r", "tail_08")     # FBX round trip compares these
REST_FRAME = -1       # export() keys the rest here and exports from it (the exporter writes the current pose as the bones' rest)
SCAP_SWING = 0.4      # share of the fore leg's swing the scapula follows
SCAP_MAX = 20.0       # the scapula's own swing (follow + reach help) about the ribcage stays within +-SCAP_MAX deg (on top of _scap)
SCAP_SLIDE = 1.5      # and it slides at most this far (cm) along its long axis, + down towards the paw
SCAP_SOFT = 172.0     # the scapula helps once the fore leg would open beyond this elbow angle (a cat never locks the elbow)
FLOOR_SINK = 0.5      # the body (any fur vertex, not just the paws) may sink at most this far into the floor (soft fur); lying
                      # loops: lowest fur -FLOOR_SINK .. 1.5 cm (the plan says 0 .. 1.5; SleepLoop rests at about -0.2)
TAIL_CLEAR = 0.15      # a tail bone's end stays this far above the floor plus its skin radius (the tail lies on the floor, not in it)


def _tail_radius(i):
    """Skin radius (cm) at the end of tail bone i (0..7): cat_rig.tail_radius, the formula cat_model lofts the tail with."""
    return cat_rig.tail_radius((i + 1) / 8.0) * 100.0


def V(x, f, z): return Vector((x * CM, -f * CM, z * CM))          # anim space cm -> armature space


def R(axis, deg): return Quaternion(Vector(axis), math.radians(deg))


def Rx(deg): return R((1, 0, 0), deg)


def Ry(deg): return R((0, 1, 0), deg)


def Rz(deg): return R((0, 0, 1), deg)


def ypr(y=0.0, p=0.0, r=0.0): return Rz(y) @ Rx(p) @ Ry(r)


def heading(q):
    """Yaw of the forward direction (-Y) after q, degrees, + to her left: what the paws turn with."""
    fw = q @ Vector((0, -1, 0)); return math.degrees(math.atan2(fw.x, -fw.y)) if fw.xy.length > 1e-9 else 0.0


def reach(l1, l2, deg): return math.sqrt(l1 * l1 + l2 * l2 - 2 * l1 * l2 * math.cos(math.radians(deg)))


def frame(a, h):
    """Orthonormal frame: column 0 along a, column 1 = h made perpendicular to a."""
    a = a.normalized(); h = (h - a * h.dot(a)).normalized()
    return Matrix((a, h, a.cross(h))).transposed()


class CatRig:
    def __init__(self, arm):
        self.arm, self.pbs = arm, arm.pose.bones
        bones = arm.data.bones
        self.h = {b.name: b.head_local.copy() for b in bones}; self.t = {b.name: b.tail_local.copy() for b in bones}
        self.r0 = {b.name: b.matrix_local.to_3x3() for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.rest_local = {b.name: (b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local.copy()) for b in bones}
        self.length = {b.name: (b.tail_local - b.head_local).length for b in bones}
        self.miss = {leg: 0.0 for leg in M.LEGS}
        self.scap_state = {}      # per fore leg of the last solve: scapula swing (deg, without _scap) and slide (cm)
        for pb in self.pbs: pb.rotation_mode = "QUATERNION"
        h, t = self.h, self.t
        self.leg = {}
        for s in "lr":   # (upper, lower, end, digit, parent): the IK runs upper/lower to the head of end; end and digit are hinged
            for leg, (up, lo, end, dig, par) in ((("h" + s), ("thigh_", "calf_", "foot_", "toe_", None)),
                                                 (("f" + s), ("upperarm_", "lowerarm_", "hand_", "finger_", "scapula_"))):
                up, lo, end, dig = up + s, lo + s, end + s, dig + s; par = par + s if par else "pelvis"
                S, J, A, B = h[up], h[lo], h[end], h[dig]
                dn = (A - S).normalized(); bend = ((J - S) - dn * (J - S).dot(dn)).normalized(); hinge = bend.cross(dn).normalized()
                self.leg[leg] = dict(up=up, lo=lo, end=end, dig=dig, par=par, side=1.0 if s == "l" else -1.0,
                                     lens=((J - S).length, (A - J).length), bend0=bend,
                                     f_up=frame(J - S, hinge), f_lo=frame(A - J, hinge),
                                     end_len=(B - A).length, end_dir=(B - A).normalized(),
                                     dig_len=(t[dig] - B).length, dig_dir=(t[dig] - B).normalized())
        for s in "lr":   # long axis of the scapula (head -> shoulder joint): the direction it slides along the ribcage
            self.leg["f" + s]["scap_axis"] = (h["upperarm_" + s] - h["scapula_" + s]).normalized()
        for s in "lr":   # rest swing of the fore leg (shoulder -> wrist against the vertical, in the chest's frame)
            v = h["hand_" + s] - h["upperarm_" + s]; self.leg["f" + s]["swing0"] = math.degrees(math.atan2(-v.y, -v.z))

    def child(self, res, name, parent, q):
        res[name] = (res[parent][0] + res[parent][1] @ (self.h[name] - self.h[parent]), q)

    def _limb(self, res, L, target, body, pole_deg):
        """Two-bone IK of L's upper/lower bone to target: the joint bends towards the rest bend carried by body, turned pole_deg
        outward about the root->target line. Returns the reached end point."""
        up, lo = L["up"], L["lo"]; self.child(res, up, L["par"], Quaternion()); S = res[up][0]; l1, l2 = L["lens"]
        d = target - S; dist = max(min(d.length, reach(l1, l2, STRAIGHT)), abs(l1 - l2) + 1.0 * CM); dn = d.normalized()
        pole = body @ L["bend0"]
        if pole_deg:
            out = body @ Vector((L["side"], 0, 0)); sg = 1.0 if dn.cross(pole).dot(out) >= 0 else -1.0
            pole = Quaternion(dn, math.radians(sg * pole_deg)) @ pole
        bend = (pole - dn * pole.dot(dn)).normalized()
        a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist); hg = math.sqrt(max(l1 * l1 - a * a, 0.0))
        J = S + dn * a + bend * hg; H = S + dn * dist; hinge = bend.cross(dn).normalized()
        res[up] = (S, (frame(J - S, hinge) @ L["f_up"].inverted()).to_quaternion())
        res[lo] = (J, (frame(H - J, hinge) @ L["f_lo"].inverted()).to_quaternion())
        return H

    def _digits(self, res, L, turn, end_deg, dig_deg, T, leg):
        """End bone (foot / hand) and digit (toe / finger) hinged about the transverse axis after turn (_turn); miss = digit tip to target."""
        self.child(res, L["end"], L["lo"], turn @ Rx(end_deg)); self.child(res, L["dig"], L["end"], turn @ Rx(dig_deg))
        p, q = res[L["dig"]]; tip = p + q @ (self.t[L["dig"]] - self.h[L["dig"]])
        self.miss[leg] = (tip - T).length / CM

    def _dirs(self, L, turn, end_deg, dig_deg):
        return turn @ Rx(end_deg) @ L["end_dir"], turn @ Rx(dig_deg) @ L["dig_dir"]

    @staticmethod
    def _turn(yaw, roll):
        """Frame of a paw: the heading of its body part, then _roll about the forward axis (only when set, so unrolled paws keep their
        exact numbers): a paw of a cat lying on its side lies on its side too."""
        return Rz(yaw) @ Ry(roll) if roll else Rz(yaw)

    def _scap_at(self, res, L, chest, deg, slide):
        """Places scapula_<s> rotated by deg (+ top back) about its head and slid by slide cm along its rotated long axis; returns the
        shoulder (upperarm head)."""
        sc = L["par"]; q = chest @ Rx(-deg); par = self.parent[sc]
        head = res[par][0] + res[par][1] @ (self.h[sc] - self.h[par]) + q @ L["scap_axis"] * (slide * CM)
        res[sc] = (head, q); return head + q @ (self.h[L["up"]] - self.h[sc])

    def _scapula(self, res, L, leg, chest, scap, W, sld=0.0):
        """The scapula of a fore leg, like a cat's (no collarbone, free on the ribcage): it follows SCAP_SWING of the leg's swing
        (angle shoulder -> wrist against the vertical in the chest's frame, two passes), then rotates and slides (min-norm Newton
        steps within +-SCAP_MAX deg and +-SCAP_SLIDE cm) until the wrist is within the reach of an elbow at SCAP_SOFT deg. sld: the
        slide the pose asks for (_sld, e.g. the blade rising over a standing leg); the steps start from it."""
        swing = 0.0
        for _ in range(2):
            S = self._scap_at(res, L, chest, scap + max(-SCAP_MAX, min(SCAP_MAX, SCAP_SWING * swing)), sld)
            v = chest.inverted() @ (W - S); swing = math.degrees(math.atan2(-v.y, -v.z)) - L["swing0"]
        a, sl = max(-SCAP_MAX, min(SCAP_MAX, SCAP_SWING * swing)), sld
        R = reach(L["lens"][0], L["lens"][1], SCAP_SOFT)
        f = lambda a_, s_: (W - self._scap_at(res, L, chest, scap + a_, s_)).length - R
        for _ in range(16):
            e = f(a, sl)
            if e <= 1e-5 * CM: break
            free = [(i, lo, hi) for i, x, lo, hi in ((0, a, -SCAP_MAX, SCAP_MAX), (1, sl, -SCAP_SLIDE, SCAP_SLIDE))]
            # scaled gradient: one unit = the whole range of a variable, so swing and slide share the work by their ranges
            g = [(f(a + SCAP_MAX * 1e-3, sl) - e) / 1e-3, (f(a, sl + SCAP_SLIDE * 1e-3) - e) / 1e-3]
            for i, lo, hi in free:   # a variable at its limit that would have to go further drops out
                x = (a, sl)[i]
                if (x >= hi - 1e-9 and g[i] < 0) or (x <= lo + 1e-9 and g[i] > 0): g[i] = 0.0
            n2 = g[0] * g[0] + g[1] * g[1]
            if n2 < 1e-12: break
            a = max(-SCAP_MAX, min(SCAP_MAX, a - e * g[0] / n2 * SCAP_MAX))
            sl = max(-SCAP_SLIDE, min(SCAP_SLIDE, sl - e * g[1] / n2 * SCAP_SLIDE))
        self._scap_at(res, L, chest, scap + a, sl); self.scap_state[leg] = (round(a, 3), round(sl, 3))

    def solve(self, P):
        """Pose dict -> {bone: (armature-space head, delta rotation)} for every bone; fills self.miss (cm per leg)."""
        res = {"root": (self.h["root"].copy(), Quaternion())}
        body = ypr(P["pel_y"], P["pel_p"], P["pel_r"])
        res["pelvis"] = (self.h["pelvis"] + V(P["pel_x"], P["pel_f"], P["pel_z"]), body)
        q, prev = body, "pelvis"
        for i, name in enumerate(("spine_01", "spine_02", "spine_03")):
            q = q @ Rz(P["sp%d_y" % (i + 1)]) @ Rx(P["sp%d_p" % (i + 1)]) @ Ry(P["sp_r"] / 3.0); self.child(res, name, prev, q); prev = name
        chest = q
        for i, name in enumerate(("neck_01", "neck_02")):
            q = q @ Rz(P["nk_y"] / 2.0) @ Rx(-P["nk%d_p" % (i + 1)]); self.child(res, name, prev, q); prev = name
        qh = q @ Rz(P["hd_y"]) @ Rx(P["hd_p"]) @ Ry(P["hd_r"]); self.child(res, "head", prev, qh)
        self.child(res, "jaw", "head", qh @ Rx(P["jaw"]))
        # ears: _p about X (+ back/flat), _y about the forward axis Y (+ tips the ear outward: the tip moves to her side, x)
        self.child(res, "ear_l", "head", qh @ Rx(-P["earl_p"]) @ Ry(P["earl_y"]))
        self.child(res, "ear_r", "head", qh @ Rx(-P["earr_p"]) @ Ry(-P["earr_y"]))
        # tail: lift over 01..03, curl over 04..08, side and travelling wave over all eight; the tail points +Y, so a turn about +Z
        # swings it to her right: negated, "+ to her left" as cat_motion documents
        # floor: a bone whose end would sink below its skin radius is lifted about the horizontal axis across it until it lies on
        # the floor (its heading kept); the lift is that bone's own, the bones after it keep their free directions (a resting tail
        # drapes along the floor and leaves it where its free shape rises)
        q, prev = body, "pelvis"
        for i, name in enumerate(TAIL):
            side = P["tl_side"] / 8.0 + P["tl_wave"] * math.sin(2 * math.pi * (P["tl_ph"] - 0.09 * i))
            q = q @ Rz(-side) @ Rx(P["tl_lift"] / 3.0 if i < 3 else P["tl_curl"] / 5.0)
            if i >= 3 and P["tl_wrap"]: q = Rz(-P["tl_wrap"] / 5.0) @ q     # about the world vertical: the tail curls round on the floor
            self.child(res, name, prev, q); res[name] = (res[name][0], self._tail_floor(res[name][0], name, i, q)); prev = name
        # hind legs: toe and metatarsus directions from the pelvis' heading, ankle A back from the paw target, IK to A
        yaw = heading(body)
        for leg in ("hl", "hr"):
            L = self.leg[leg]; T = V(P[leg + "_x"], P[leg + "_f"], P[leg + "_z"])
            turn = self._turn(yaw, P[leg + "_roll"]); d_end, d_dig = self._dirs(L, turn, P[leg + "_ank"], P[leg + "_toe"])
            A = T - L["dig_len"] * d_dig - L["end_len"] * d_end
            self._limb(res, L, A, body, P[leg + "_pole"]); self._digits(res, L, turn, P[leg + "_ank"], P[leg + "_toe"], T, leg)
        # fore legs: wrist W back from the paw target; the scapula follows the leg's swing (two passes) and then takes what the arm
        # cannot reach (_scapula), IK shoulder -> W
        yaw = heading(chest)
        for leg in ("fl", "fr"):
            L = self.leg[leg]; T = V(P[leg + "_x"], P[leg + "_f"], P[leg + "_z"])
            turn = self._turn(yaw, P[leg + "_roll"]); d_end, d_dig = self._dirs(L, turn, P[leg + "_ank"], P[leg + "_toe"])
            W = T - L["dig_len"] * d_dig - L["end_len"] * d_end
            self._scapula(res, L, leg, chest, P[leg + "_scap"], W, P[leg + "_sld"])
            self._limb(res, L, W, chest, P[leg + "_pole"]); self._digits(res, L, turn, P[leg + "_ank"], P[leg + "_toe"], T, leg)
        return res

    def _tail_floor(self, p, name, i, q):
        """q, or q lifted (about the horizontal axis across the bone) so the bone's end stays _tail_radius + TAIL_CLEAR above z 0."""
        d = q @ (self.t[name] - self.h[name]); lo = (_tail_radius(i) + TAIL_CLEAR) * CM
        if p.z + d.z >= lo: return q
        hz = Vector((d.x, d.y, 0.0))
        if hz.length < 1e-6 * CM: return q          # pointing straight down: no heading to lie along (postures never do this)
        ln = d.length; want = math.asin(max(-1.0, min(1.0, (lo - p.z) / ln))); have = math.asin(max(-1.0, min(1.0, d.z / ln)))
        return Quaternion(hz.normalized().cross(Vector((0, 0, 1))), want - have) @ q

    def matrix(self, res, name):
        p, q = res[name]; return Matrix.Translation(p) @ (q.to_matrix() @ self.r0[name]).to_4x4()

    def _driven(self, res):
        if not hasattr(self, "_ord"):
            order = []

            def walk(b):
                if b.name in res: order.append(b.name)
                for c in b.children: walk(c)
            for b in self.arm.data.bones:
                if b.parent is None: walk(b)
            self._ord = order
        return self._ord

    def key(self, P, f, overlay=False):
        """Keys every bone at frame f (quaternion and location; location only moves the pelvis, root stays at rest). overlay: only
        tail_* and ear_* from the channels, every other bone at rest (the kit makes the sequence additive against the ref pose)."""
        if overlay:
            P = dict(M.zero_pose(), **{k: v for k, v in P.items() if k.startswith(("tl_", "ear"))})
        res = self.solve(P); Mx = {}
        for name in self._driven(res):
            par = self.parent[name]; Mx[name] = self.matrix(res, name)
            basis = self.rest_local[name].inverted() @ (Mx[par].inverted() if par else Matrix.Identity(4)) @ Mx[name]
            pb = self.pbs[name]
            keep = overlay and not (name in TAIL or name.startswith("ear_"))
            pb.rotation_quaternion = Quaternion() if keep or name == "root" else basis.to_quaternion().normalized()
            moves = (name == "pelvis" or name.startswith("scapula_")) and not overlay      # pelvis shift, scapula slide
            loc = basis.to_translation() if moves else Vector()
            pb.location = loc if loc.length > 1e-6 * CM else Vector()    # float noise of an unslid scapula keys an exact 0
            pb.keyframe_insert("rotation_quaternion", frame=f); pb.keyframe_insert("location", frame=f)
        return res

    def tips(self, frame=None):
        """Contact points of the paws (tail of toe_* / finger_*) in anim space cm, from the evaluated pose (at frame if given)."""
        if frame is not None: bpy.context.scene.frame_set(frame)
        out = {}
        for leg, b in M.TIP.items():
            p = self.pbs[b].tail; out[leg] = (p.x / CM, -p.y / CM, p.z / CM)
        return out

    def heads(self, res):
        """Joint points of a solved pose (every bone head plus the paw tips), cm."""
        pts = {n: p / CM for n, (p, _) in res.items()}
        for leg, b in M.TIP.items():
            p, q = res[b]; pts["tip_" + leg] = (p + q @ (self.t[b] - self.h[b])) / CM
        return pts


def pose_gap(rig, a, b):
    """Largest joint distance (cm) between two solved poses."""
    ha, hb = rig.heads(rig.solve(a)), rig.heads(rig.solve(b))
    return max((ha[k] - hb[k]).length for k in ha)


def reference_joints(rig, s):
    """Heads of JOINTS (armature space, cm) at the frames 0, N/3, N/2, N of the action on rig.arm: the FBX round trip's reference."""
    out = []
    for f in sorted({0, s.frames // 3, s.frames // 2, s.frames}):
        bpy.context.scene.frame_set(f)
        out.append((f, {b: (rig.arm.matrix_world @ rig.pbs[b].head) / CM for b in JOINTS}))
    return out


def use_action(arm, act, n):
    arm.animation_data.action = act
    if getattr(act, "slots", None) and len(act.slots): arm.animation_data.action_slot = act.slots[0]
    sc = bpy.context.scene; sc.frame_start, sc.frame_end = 0, n


def export(arm, path):
    """Same settings as cat.fbx (cat_model.export): armature already x100 with the scale applied (cm bones, object scale 1), unit scale 0.01, -Z
    forward, Y up, no leaf bones, object named 'Armature' (UE skips it, the bone root stays the skeleton root). The exporter writes
    the pose of the current frame as the bones' transforms, which importers read as the rest: so the rest is keyed at REST_FRAME
    (outside the baked range 0..N) and exported from there, and taken out again afterwards. The rest then equals cat.fbx."""
    sc = bpy.context.scene; sc.unit_settings.scale_length = 0.01; sc.render.fps, sc.render.fps_base = M.FPS, 1.0
    arm.name = "Armature"
    for pb in arm.pose.bones:
        pb.rotation_quaternion = Quaternion(); pb.location = Vector()
        pb.keyframe_insert("rotation_quaternion", frame=REST_FRAME); pb.keyframe_insert("location", frame=REST_FRAME)
    sc.frame_set(REST_FRAME)
    bpy.ops.object.select_all(action="DESELECT"); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE"}, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_NONE", global_scale=1.0, add_leaf_bones=False, primary_bone_axis="Y",
                             secondary_bone_axis="X", axis_forward="-Z", axis_up="Y", bake_anim=True, bake_anim_use_all_bones=True,
                             bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True,
                             bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
    for pb in arm.pose.bones:
        pb.keyframe_delete("rotation_quaternion", frame=REST_FRAME); pb.keyframe_delete("location", frame=REST_FRAME)
    sc.frame_set(0)


# ------------------------------------------------------------------------------------------------------------------- measuring
def _finite(v): return all(math.isfinite(x) for x in v)


def _fur_vertices(mesh):
    import numpy as np
    me = mesh.data; fur = [i for i, s in enumerate(mesh.material_slots) if s.material and s.material.name.startswith("Fur") and "Card" not in s.material.name]
    idx = set()
    for p in me.polygons:
        if p.material_index in fur: idx.update(p.vertices)
    return np.array(sorted(idx), dtype=np.int64)


def floor_min(mesh, fur_idx):
    """Lowest fur vertex of the evaluated (skinned) mesh, world z in cm."""
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg); me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)[fur_idx]
    mw = np.array(ev.matrix_world); z = co @ mw[2, :3] + mw[2, 3]; ev.to_mesh_clear()
    return float(z.min()) / CM


def measure(rig, seq, mesh):
    """The gates of the plan for one sequence (its action on rig.arm): raises RuntimeError on a violated gate, returns the numbers."""
    n, fps, name = seq.frames, M.FPS, seq.name; warn = []
    poses = [seq.frame_pose(f) for f in range(n + 1)]
    for f, P in enumerate(poses):
        nf = [k for k, v in P.items() if not math.isfinite(v)]
        if nf: raise RuntimeError("%s frame %d: channels not finite %s" % (name, f, nf))
        bad = M.check_pose(P)
        if bad: raise RuntimeError("%s frame %d: channels outside limits %s" % (name, f, bad))
    miss = []
    for P in poses: rig.solve(P); miss.append(dict(rig.miss))
    tips, joints = [], []
    for f in range(n + 1):
        tips.append(rig.tips(f)); joints.append({pb.name: pb.head.copy() for pb in rig.pbs})
        for pb in rig.pbs:
            if not all(_finite(r) for r in pb.matrix): raise RuntimeError("%s frame %d: matrix of %s not finite" % (name, f, pb.name))
    loop = max((joints[0][b] - joints[n][b]).length for b in joints[0]) / CM if seq.loop else 0.0
    if loop > 0.05: raise RuntimeError("%s: loop does not close, %.3f cm" % (name, loop))

    def in_plant(leg, f):
        return any(t0 - 1e-6 <= f / fps <= t1 + 1e-6 for t0, t1 in seq.plants.get(leg, []))
    ik_plant = max((miss[f][leg] for f in range(n + 1) for leg in M.LEGS if in_plant(leg, f)), default=0.0)
    ik_free = max((miss[f][leg] for f in range(n + 1) for leg in M.LEGS if not in_plant(leg, f)), default=0.0)
    if ik_plant > 0.3: raise RuntimeError("%s: IK misses a planted paw by %.3f cm" % (name, ik_plant))
    if ik_free > 2.0: raise RuntimeError("%s: IK misses a paw by %.3f cm" % (name, ik_free))
    if ik_free > 0.3: warn.append("ik miss %.2f cm outside plants" % ik_free)
    slide = {"along": 0.0, "cross": 0.0, "up": 0.0}; plant = 0.0
    for leg, spans in seq.plants.items():
        for t0, t1 in spans:
            fs = [f for f in range(n + 1) if t0 - 1e-6 <= f / fps <= t1 + 1e-6]
            if not fs: continue
            x0, f0, z0 = tips[fs[0]][leg]
            for f in fs:
                x, fw, z = tips[f][leg]
                if seq.speed > 0:
                    exp = f0 - seq.speed * (f - fs[0]) / fps
                    slide["along"] = max(slide["along"], abs(fw - exp)); slide["cross"] = max(slide["cross"], abs(x - x0))
                    slide["up"] = max(slide["up"], abs(z - z0))
                else:
                    plant = max(plant, math.sqrt((x - x0) ** 2 + (fw - f0) ** 2 + (z - z0) ** 2))
    if slide["along"] > 0.5 or slide["cross"] > 0.3 or slide["up"] > 0.3: raise RuntimeError("%s: planted paw slides %s" % (name, slide))
    if plant > 0.3: raise RuntimeError("%s: planted paw drifts %.3f cm" % (name, plant))
    # evaluated paw tip against its keyed target (independent of the solver's own miss) and against the solver's miss (keying)
    tip_plant = tip_free = tip_vs_solver = 0.0
    for f, P in enumerate(poses):
        for leg in M.LEGS:
            e = math.sqrt(sum((a - b) ** 2 for a, b in zip(tips[f][leg], (P[leg + "_x"], P[leg + "_f"], P[leg + "_z"]))))
            tip_vs_solver = max(tip_vs_solver, abs(e - miss[f][leg]))
            if in_plant(leg, f): tip_plant = max(tip_plant, e)
            else: tip_free = max(tip_free, e)
    if tip_plant > 0.3: raise RuntimeError("%s: evaluated planted paw %.3f cm off its target" % (name, tip_plant))
    if tip_free > 2.0: raise RuntimeError("%s: evaluated paw %.3f cm off its target" % (name, tip_free))
    if tip_vs_solver > 0.05: raise RuntimeError("%s: evaluated paws differ from the solver by %.3f cm (keying)" % (name, tip_vs_solver))
    # planted paws stand on the floor; a paw on the floor (z <= 0.5) is planted (otherwise it would slide); overlays keep the rest
    contacts = {leg: [f for f in range(n + 1) if tips[f][leg][2] <= 0.5] for leg in M.LEGS}
    if not seq.overlay:
        for leg in M.LEGS:
            pf = [f for f in range(n + 1) if in_plant(leg, f)]
            off = [(f, round(tips[f][leg][2], 3)) for f in pf if not -0.3 <= tips[f][leg][2] <= 0.5]
            if off: raise RuntimeError("%s: planted %s not on the floor (frame, z cm) %s" % (name, leg, off[:5]))
            extra = sorted(set(contacts[leg]) - set(pf))
            if extra: raise RuntimeError("%s: %s touches the floor outside its plants, frames %s" % (name, leg, extra[:10]))
    touch = _touch(rig, seq, poses)
    fur = _fur_vertices(mesh); floor = []
    for f in range(n + 1):                    # every frame: lying bodies (belly, haunches, elbows, side) touch the floor
        bpy.context.scene.frame_set(f); floor.append(floor_min(mesh, fur))
    fmin = min(floor)
    if fmin < -FLOOR_SINK: raise RuntimeError("%s: fur %.2f cm below the floor at frame %d (allowed -%.1f)" % (name, fmin, floor.index(fmin), FLOOR_SINK))
    if name in ("LieLoop", "SleepLoop") and fmin > 1.5: raise RuntimeError("%s: lowest fur %.2f cm above the floor (must lie)" % (name, fmin))
    r = lambda v: round(v, 3)
    return {"frames": n, "length_s": r(seq.length), "group": seq.group, "speed": seq.speed, "ik_miss_cm": r(ik_plant),
            "ik_miss_free_cm": r(ik_free), "tip_err_cm": r(tip_plant), "tip_err_free_cm": r(tip_free),
            "tip_vs_solver_cm": r(tip_vs_solver), "slide_cm": {k: r(v) for k, v in slide.items()} if seq.speed > 0 else None,
            "plant_cm": r(plant), "floor_min_cm": r(fmin), "loop_cm": r(loop), "warnings": warn, "contacts": contacts,
            **({"touch": touch} if touch else {})}


def head_point(rig, res, local):
    """A point of the head (rest anim space cm, cat_poses.MOUTH ...) in the solved pose res, anim space cm."""
    p, q = res["head"]; w = (p + q @ (V(*local) - rig.h["head"])) / CM; return Vector((w.x, -w.y, w.z))


def _touch(rig, seq, poses):
    """Head contacts of an action (Seq.touch, see cat_anim_action.Action) from the solved poses: raises on a violated gate, returns
    {"head_clear_cm": smallest fore paw tip - P.HEAD_C distance, "near": [[leg, point, t0, t1, mode, limit, value]]}."""
    t = getattr(seq, "touch", None)
    if not t: return None
    import cat_poses as P
    tips, pts = [], []
    for pose in poses:
        res = rig.solve(pose); hd = rig.heads(res)
        tips.append({leg: Vector((hd["tip_" + leg].x, -hd["tip_" + leg].y, hd["tip_" + leg].z)) for leg in ("fl", "fr")})
        pts.append({n: head_point(rig, res, getattr(P, n)) for n in ("HEAD_C", "MOUTH", "CHEEK_R", "EAR_R")})
    clear = min((tips[f][leg] - pts[f]["HEAD_C"]).length for f in range(len(poses)) for leg in ("fl", "fr"))
    if clear < t["clear"]: raise RuntimeError("%s: a fore paw tip comes %.2f cm near the head centre (min %.1f)" % (seq.name, clear, t["clear"]))
    near = []
    for leg, pt, t0, t1, mode, lim in t.get("near", []):
        ds = [(tips[f][leg] - pts[f][pt]).length for f in range(len(poses)) if t0 - 1e-6 <= f / M.FPS <= t1 + 1e-6]
        v = max(ds) if mode == "max" else min(ds)
        near.append([leg, pt, round(t0, 3), round(t1, 3), mode, lim, round(v, 3)])
        if v > lim: raise RuntimeError("%s: %s tip %s distance to %s over %.2f-%.2f s is %.2f cm (limit %.1f)" % (seq.name, leg, mode, pt, t0, t1, v, lim))
    return {"head_clear_cm": round(clear, 3), "near": near}


def _channelbag_curves(act):
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags: out.extend(cb.fcurves)
    return out or list(getattr(act, "fcurves", []))


def _import(path):
    before = set(bpy.data.objects); bpy.ops.import_scene.fbx(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]; return new, next(o for o in new if o.type == "ARMATURE")


def rest_of(path):
    """Rest of an FBX's armature after import: object scale, bone names in order, world heads (cm)."""
    new, a = _import(path)
    k = 100.0 if a.matrix_world.to_scale().x < 0.5 else 1.0
    out = {"scale": tuple(round(v, 6) for v in a.matrix_world.to_scale()), "bones": [b.name for b in a.data.bones],
           "heads": {b.name: (a.matrix_world @ b.head_local) * k / CM for b in a.data.bones}}
    for o in new: bpy.data.objects.remove(o, do_unlink=True)
    return out


def verify_fbx(path, ref, rest=None):
    """Round trip: the exported FBX, imported as a separate armature, must put JOINTS where this session has them (ref from
    reference_joints), have the frame count and an unmoved root (bone and object). rest (rest_of(cat.fbx)): its rest must equal it."""
    new, src = _import(path); sc = bpy.context.scene
    act = src.animation_data.action; slot = getattr(src.animation_data, "action_slot", None)
    if slot is None and getattr(act, "slots", None) and len(act.slots): src.animation_data.action_slot = act.slots[0]
    rng = act.frame_range; frames = int(round(rng[1] - rng[0])) + 1
    k = 100.0 if src.matrix_world.to_scale().x < 0.5 else 1.0          # an import in metres
    worst = 0.0
    for f, row in ref:
        sc.frame_set(f + int(round(rng[0])))
        for b, p in row.items(): worst = max(worst, ((src.matrix_world @ src.pose.bones[b].head) * k / CM - p).length)
    rb = src.data.bones["root"]; moved = 0.0
    for f in range(int(round(rng[0])), int(round(rng[1])) + 1):
        sc.frame_set(f); pb = src.pose.bones["root"]
        moved = max(moved, (pb.head - rb.head_local).length * k / CM, (pb.tail - rb.tail_local).length * k / CM)
    obj = [c for c in _channelbag_curves(act) if not c.data_path.startswith("pose.bones")]
    moved = max([moved] + [abs(c.evaluate(f) - c.evaluate(rng[0])) for c in obj for f in range(int(rng[0]), int(rng[1]) + 1)])
    out = {"worst_cm": round(worst, 4), "root_moved": round(moved, 6), "frames": frames}
    if rest is not None:
        bones = [b.name for b in src.data.bones]; heads = {b.name: (src.matrix_world @ b.head_local) * k / CM for b in src.data.bones}
        out["bones"] = len(bones); out["root_first"] = bones[0] == "root"
        out["scale_equal"] = tuple(round(v, 6) for v in src.matrix_world.to_scale()) == rest["scale"]
        out["rest_cm"] = round(max((heads[b] - rest["heads"][b]).length for b in rest["heads"]), 6) if set(bones) == set(rest["bones"]) else -1.0
    for o in new: bpy.data.objects.remove(o, do_unlink=True)
    return out


# ------------------------------------------------------------------------------------------------------------------- review tiles
class Stage:
    """Workbench renders of the skinned cat: grey mesh, floor slab with a 5 cm grid, orthographic views."""
    WIDTH, RES, CENTRE = 70.0 * CM, (320, 240), Vector((0, 3.0 * CM, 15.0 * CM))   # y +3 (plan: -5): the tail tip reaches y +36
    DIRS = {"left": Vector((1, 0, 0)), "front": Vector((0, -1, 0)), "back": Vector((0, 1, 0)), "top": Vector((0, 0, 1))}

    def __init__(self, arm, mesh):
        sc = bpy.context.scene; self.arm, self.mesh = arm, mesh
        sc.render.engine = "BLENDER_WORKBENCH"; sh = sc.display.shading
        sh.light = "STUDIO"; sh.color_type = "OBJECT"; sh.show_cavity = True
        sc.view_settings.view_transform = "Standard"
        sc.world = bpy.data.worlds.new("review"); sc.world.color = (0.16, 0.16, 0.18)
        sc.render.resolution_x, sc.render.resolution_y = self.RES; sc.render.resolution_percentage = 100
        sc.render.image_settings.file_format = "PNG"
        mesh.color = (0.66, 0.66, 0.66, 1.0)
        s = 60.0 * CM
        self.floor = self._box("review_floor", (-s, -s, -1.0 * CM), (s, s, 0.0), (0.36, 0.38, 0.42, 1.0))
        lines = []
        for i in range(-12, 13):
            c = i * 5.0 * CM; w = (0.25 if i % 2 else 0.4) * CM / 2
            lines.append(((-s, c - w, 0.0), (s, c + w, 0.06 * CM))); lines.append(((c - w, -s, 0.0), (c + w, s, 0.06 * CM)))
        self.grid = self._boxes("review_grid", lines, (0.22, 0.23, 0.26, 1.0))
        cam = bpy.data.objects.new("review_cam", bpy.data.cameras.new("review_cam")); sc.collection.objects.link(cam); sc.camera = cam
        cam.data.type = "ORTHO"; cam.data.ortho_scale = self.WIDTH; cam.data.clip_start = 1.0 * CM; cam.data.clip_end = 2000.0 * CM
        self.cam = cam

    def _boxes(self, name, boxes, color):
        verts, faces = [], []
        for (x0, y0, z0), (x1, y1, z1) in boxes:
            b = len(verts)
            verts += [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
            faces += [tuple(b + i for i in f) for f in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))]
        me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
        ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); ob.color = color
        return ob

    def _box(self, name, lo, hi, color): return self._boxes(name, [(lo, hi)], color)

    # head close-ups: h<view> centres on the middle of the head bone, HEAD_WIDTH wide (jaw, ears, a paw at the face)
    HEAD_WIDTH = 25.0 * CM
    HEAD_DIRS = {"hleft": Vector((1, 0, 0)), "hfront": Vector((0, -1, 0)), "hq": Vector((-0.6, -0.75, 0.3)).normalized()}

    def shot(self, view, path):
        cam = self.cam
        if view in self.HEAD_DIRS:
            pb = self.arm.pose.bones["head"]; c = self.arm.matrix_world @ ((pb.head + pb.tail) / 2); d = self.HEAD_DIRS[view]
            cam.data.ortho_scale = self.HEAD_WIDTH
        else:
            c, d = self.CENTRE, self.DIRS[view]; cam.data.ortho_scale = self.WIDTH
        cam.location = c + d * 500.0 * CM
        cam.rotation_euler = (0.0, 0.0, math.pi / 2) if view == "top" else (-d).to_track_quat("-Z", "Y").to_euler()
        sc = bpy.context.scene; sc.render.filepath = path; bpy.ops.render.render(write_still=True)

    def tiles(self, seq, out_dir, frames, views):
        d = os.path.join(out_dir, seq.name); os.makedirs(d, exist_ok=True)
        for fn in os.listdir(d):
            if fn.endswith(".png"): os.remove(os.path.join(d, fn))
        for f in frames:
            bpy.context.scene.frame_set(f)
            for v in views: self.shot(v, os.path.join(d, "%s_%d.png" % (v, f)))
