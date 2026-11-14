"""Reach probe of the cat rig: fore paws swept -8/-4/+4/+8 cm and the pelvis raised 1 cm on the gait base pose (cat_poses.GAIT) and
on STAND; each probe pose is solved, keyed and evaluated, so the reported error is the evaluated paw tip against its target (not
the solver's own number). Fails loudly (RuntimeError, exit code 1) if a paw misses by more than LIMIT_CM.
Usage: blender -b --factory-startup --python-exit-code 1 --python tools/blender/cat_probe.py -- <build/velvetpaws> [--render <dir>]
Prints PROBE <case> {...} per case and PROBE OK <n>. cat_anims.py runs probe() before it builds anything. cat.blend is never saved.
--render: left/front/top tiles of STAND, GAIT and the fore paws at +-8 cm (one forward, one back) into <dir>/tiles/Probes/
(columns f0..f3 = RENDER)."""
import json, os, sys
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_motion as M
import cat_poses as P

LIMIT_CM = 0.1
FORE = (-8.0, -4.0, 4.0, 8.0)


def cases():
    """(name, pose, gated): the probes, named after the pose they sit on. Gated (must reach): every fore paw sweep on GAIT and the
    raised pelvis on GAIT and STAND. Reported only: the sweeps on STAND (legs nearly straight at rest; 8 cm forward from there
    needs the chest lowered, which is what GAIT does)."""
    out = []
    for tag, base in (("gait", P.GAIT), ("stand", P.STAND)):
        for d in FORE:
            out.append(("%s_fore%+d" % (tag, d), dict(base, fl_f=base["fl_f"] + d, fr_f=base["fr_f"] + d), tag == "gait"))
        out.append(("%s_fore_split+8" % tag, dict(base, fl_f=base["fl_f"] + 8, fr_f=base["fr_f"] - 8), tag == "gait"))
        out.append(("%s_pel_z+1" % tag, dict(base, pel_z=base["pel_z"] + 1.0), True))
    return out


def probe(rig, limit=LIMIT_CM, log=print):
    """Solves and keys every case (frame i) on a scratch action of rig.arm, evaluates the tips (rig.tips) and compares them with
    the targets; the active action is restored afterwards. Returns {case: numbers}; raises if a paw misses."""
    import cat_animlib as L
    arm = rig.arm; ad = arm.animation_data or arm.animation_data_create()
    old_act, sc = ad.action, bpy.context.scene; old_range = (sc.frame_start, sc.frame_end)
    act = bpy.data.actions.new("vp_probe"); L.use_action(arm, act, 1)
    cs = cases(); solved = {}
    for i, (name, pose, _) in enumerate(cs):
        bad_ch = M.check_pose(pose)
        if bad_ch: raise RuntimeError("probe %s: channels outside limits %s" % (name, bad_ch))
        rig.key(pose, i); solved[name] = (dict(rig.miss), dict(getattr(rig, "scap_state", {})))
    L.use_action(arm, act, len(cs))                    # the first key created the action's slot
    out, bad = {}, []
    for i, (name, pose, gated) in enumerate(cs):
        tips = rig.tips(i)
        err = {leg: sum((a - b) ** 2 for a, b in zip(tips[leg], (pose[leg + "_x"], pose[leg + "_f"], pose[leg + "_z"]))) ** 0.5
               for leg in M.LEGS}
        miss, scap = solved[name]
        r = {"tip_err_cm": {k: round(v, 3) for k, v in err.items()}, "solver_miss_cm": {k: round(v, 3) for k, v in miss.items()}}
        if scap: r["scapula_deg_cm"] = scap
        r["gated"] = gated
        out[name] = r; log("PROBE %s %s" % (name, json.dumps(r)))
        if gated and max(err.values()) > limit: bad.append("%s %.3f cm" % (name, max(err.values())))
    ad.action = old_act; sc.frame_start, sc.frame_end = old_range
    if old_act is not None and getattr(old_act, "slots", None) and len(old_act.slots): ad.action_slot = old_act.slots[0]
    bpy.data.actions.remove(act)
    for s, sign in (("l", 1.0), ("r", -1.0)):    # ear _y: + tips the ear outward (its tip moves to her side, x), as CHANNELS says
        res0 = rig.solve(P.STAND); res1 = rig.solve(dict(P.STAND, **{"ear%s_y" % s: 30.0}))
        tip = lambda res: res["ear_" + s][0] + res["ear_" + s][1] @ (rig.t["ear_" + s] - rig.h["ear_" + s])
        d = tip(res1) - tip(res0); out["ear_%s_y+30" % s] = {"tip_move_cm": [round(v, 3) for v in d]}
        log("PROBE ear_%s_y+30 %s" % (s, json.dumps(out["ear_%s_y+30" % s])))
        if sign * d.x < 1.0 or abs(d.x) < 2 * abs(d.y): bad.append("ear_%s_y does not tip the ear outward %s" % (s, tuple(d)))
    if bad: raise RuntimeError("probe: paws miss their targets by more than %.2f cm: %s" % (limit, ", ".join(bad)))
    log("PROBE OK %d" % len(out))
    return out


RENDER = ("Stand", "Gait", "fore +8 / -8 (fl / fr)", "fore -8 / +8 (fl / fr)")


def render(rig, mesh, rdir):
    """Review tiles like cat_anims (Stage; left/front/top) into <rdir>/tiles/Probes/, one column (frame i) per RENDER pose: STAND,
    GAIT and GAIT with the fore paws 8 cm apart forward/back. Compose with scripts/velvetpaws/anim_sheet.py <rdir>."""
    import cat_animlib as L
    g = P.GAIT
    poses = [P.STAND, g, dict(g, fl_f=g["fl_f"] + 8, fr_f=g["fr_f"] - 8), dict(g, fl_f=g["fl_f"] - 8, fr_f=g["fr_f"] + 8)]
    arm = rig.arm; act = bpy.data.actions.new("vp_probe_render"); L.use_action(arm, act, len(poses) - 1)
    for i, pose in enumerate(poses): rig.key(pose, i)
    L.use_action(arm, act, len(poses) - 1)
    L.Stage(arm, mesh).tiles(M.Seq("Probes", len(poses) - 1, lambda t: P.STAND), os.path.join(rdir, "tiles"), range(len(poses)),
                             ("left", "front", "top"))


def main():
    import cat_animlib as L
    import cat_anims as A
    args = sys.argv[sys.argv.index("--") + 1:]; out = args[0]
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "cat.blend"))
    arm = bpy.data.objects["root"]; mesh = bpy.data.objects["SK_VP_Cat"]; A.to_cm(arm, mesh)
    rig = L.CatRig(arm); arm.animation_data_create()
    rdir = A.arg(args, "--render")
    try:
        probe(rig)
    finally:
        if rdir: render(rig, mesh, rdir)


if __name__ == "__main__":
    main()
