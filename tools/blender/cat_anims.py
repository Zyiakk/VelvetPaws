"""Builds, checks and exports the cat's animation sequences (cat_seqs.SEQS) on the rig of build/velvetpaws/cat.blend.
Usage: blender -b --factory-startup --python-exit-code 1 --python tools/blender/cat_anims.py -- <build/velvetpaws> [--only A,B] [--no-review]
Runs cat_probe.probe first. Writes <out>/anim/VP_Cat_<Name>.fbx, <out>/review/anim/measures.json (a full run rewrites it,
--only merges its sequences into it)
and tiles; prints ANIMS MEASURE lines and ANIMS OK <n>.
Exports before anything of the review touches the scene: the same keys give the same bytes with or without --no-review.
cat.blend is only read, never saved."""
import json, os, sys
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_animlib as L
import cat_motion as M
import cat_poses as P
import cat_probe
import cat_seqs as S

VIEWS = {"gait": ("left", "front", "top"), "posture": ("left", "front", "top"), "jump": ("left", "front"),
         "action": ("left", "front", "back", "hleft", "hq", "hfront"), "overlay": ("back", "left"),
         "social": ("left", "front", "top", "back", "hq", "hfront")}


def arg(args, k, d=None): return args[args.index(k) + 1] if k in args else d


def to_cm(arm, mesh):
    """Same armature space as cat.fbx (cat_model.export): x100 with the scale applied, bones in cm, object scale 1.
    Only the armature is scaled, the mesh is its child and follows."""
    arm.scale = (100, 100, 100)
    bpy.ops.object.select_all(action="DESELECT")
    for o in (arm, mesh): o.select_set(True)
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out = args[0]; only = arg(args, "--only", ",".join(S.ORDER)).split(","); review = "--no-review" not in args
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "cat.blend"))
    arm = bpy.data.objects["root"]; mesh = bpy.data.objects["SK_VP_Cat"]
    to_cm(arm, mesh)
    rig = L.CatRig(arm); arm.animation_data_create(); acts, meas, ref = {}, {}, {}
    cat_probe.probe(rig, log=lambda line: print("ANIMS " + line))       # reach of the rig first: fails loudly
    for name in only:
        s = S.SEQS[name]; act = bpy.data.actions.new("VP_Cat_" + name); L.use_action(arm, act, s.frames)
        for f in range(s.frames + 1): rig.key(s.frame_pose(f), f, overlay=s.overlay)
        L.use_action(arm, act, s.frames)              # the first key created the action's slot
        acts[name] = act; m = L.measure(rig, s, mesh); meas[name] = m; ref[name] = L.reference_joints(rig, s)
        if s.lift_off is not None:                      # no pop from the lift-off into the flight pose
            (cm, c1, f1), (deg, c2, f2) = M.end_jumps(s); m["end_jump"] = {"cm": round(cm, 3), "cm_ch": c1, "deg": round(deg, 2), "deg_ch": c2}
            if cm > M.END_MAX_CM or deg > M.END_MAX_DEG:
                raise RuntimeError("%s: per-frame jump in its last %d frames: %.2f cm (%s f%d), %.1f deg (%s f%d)"
                                   % (name, M.END_FRAMES, cm, c1, f1, deg, c2, f2))
        (dg, c1, f1), (cm, c2, f2) = M.body_accel(s); m["smooth"] = {"deg": round(dg, 2), "deg_ch": c1, "cm": round(cm, 3), "cm_ch": c2}
        if s.group == "social" and (dg > M.SMOOTH_MAX_DEG or cm > M.SMOOTH_MAX_CM):    # no jerk in the trunk, head or tail
            raise RuntimeError("%s: not smooth: %.2f deg/frame^2 (%s f%d), %.3f cm/frame^2 (%s f%d)" % (name, dg, c1, f1, cm, c2, f2))
        print("ANIMS MEASURE %s %s" % (name, json.dumps({k: v for k, v in m.items() if k != "contacts"})))
    for name in only:                                   # postures connect after solving (Enter end == Loop start == Exit start ...)
        s = S.SEQS[name]
        for tag, t in ((s.start, 0.0), (s.end, s.length)):
            if tag:
                gap = L.pose_gap(rig, s.pose(t), P.POSES[tag])
                if gap > 0.05: raise RuntimeError("%s: %s at %.3f s is %.3f cm off posture %s" % (name, "start" if t == 0 else "end", t, gap, tag))
    L.fixed_fbx_time(); adir = os.path.join(out, "anim"); os.makedirs(adir, exist_ok=True)
    for name in only:
        L.use_action(arm, acts[name], S.SEQS[name].frames); bpy.context.scene.frame_set(0)
        L.export(arm, os.path.join(adir, "VP_Cat_%s.fbx" % name))
    rest = L.rest_of(os.path.join(out, "cat.fbx"))
    for name in only:
        L.use_action(arm, acts[name], S.SEQS[name].frames)
        rt = L.verify_fbx(os.path.join(adir, "VP_Cat_%s.fbx" % name), ref[name], rest); meas[name]["fbx_round_trip"] = rt
        print("ANIMS FBX %s %s" % (name, json.dumps(rt)))
        if rt["worst_cm"] > 0.1 or rt["root_moved"] > 1e-4 or rt["frames"] != S.SEQS[name].frames + 1:
            raise RuntimeError("FBX round trip of %s: %s" % (name, rt))
        if rt["bones"] != len(rest["bones"]) or not rt["root_first"] or not rt["scale_equal"] or not 0 <= rt["rest_cm"] <= 1e-4:
            raise RuntimeError("rest of %s differs from cat.fbx: %s" % (name, rt))
    rdir = os.path.join(out, "review", "anim"); os.makedirs(rdir, exist_ok=True)
    if review:
        stage = L.Stage(arm, mesh)
        for name in only:
            s = S.SEQS[name]; L.use_action(arm, acts[name], s.frames)
            frames = sorted({round(i * s.frames / 8) for i in range(8 if s.loop else 9)})
            stage.tiles(s, os.path.join(rdir, "tiles"), frames, VIEWS[s.group])
    mpath = os.path.join(rdir, "measures.json")
    old = {}
    if "--only" in args and os.path.exists(mpath):    # --only: the other sequences keep their entries (and sheet headers)
        with open(mpath) as fh: old = json.load(fh)
    old = {k: v for k, v in old.items() if k in S.SEQS}
    with open(mpath, "w") as fh: json.dump(dict(old, **meas), fh, indent=1)   # a full run starts afresh
    print("ANIMS OK %d" % len(only))


if __name__ == "__main__":
    main()
