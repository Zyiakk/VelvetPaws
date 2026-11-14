"""Close-up renders of the skinned cat for review: rest or a frame of a sequence (cat_seqs.SEQS), clay (Workbench) or
textured (Cycles with cat_look_tex), around the head or the whole cat, several views. One PNG per view and frame.
cat.blend is only read, never saved.
Usage: blender -b --factory-startup --python-exit-code 1 --python tools/blender/cat_closeup.py -- <build/velvetpaws> <out_dir>
       [--seq Yawn] [--frames 0,25] [--views hfront,hq,hleft] [--tex] [--width 14] [--res 640] [--focus head|mouth|eye|tail|body|x,y,z] [--floor]
Views: hfront hq hleft hright hlow hback (head), and front fl left bl back br right fr top (whole cat with --focus body);
gfl gfr gbl gleft gfront look down from about the game camera's height (third person, 30-35 deg); eyeq looks at the left eye from 3/4, eyeg
along its gaze; tq tback tleft at the tail root (3/4 from behind, behind, side).
--floor: a dark floor slab with a 5 cm grid at z 0 (paws on or in the floor).
Prints CLOSEUP <path> per image."""
import math, os, sys
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_anims, cat_animlib as L, cat_model, cat_seqs as S

DIRS = {"hfront": (0, -1, 0.05), "hq": (-0.6, -0.75, 0.15), "hleft": (1, 0, 0.02), "hright": (-1, 0, 0.02),
        "hlow": (-0.35, -0.8, -0.45), "hback": (0, 1, 0.25), "front": (0, -1, 0), "fl": (1, -1, 0), "left": (1, 0, 0), "bl": (1, 1, 0),
        "back": (0, 1, 0), "br": (-1, 1, 0), "right": (-1, 0, 0), "fr": (-1, -1, 0), "top": (0, 0.001, 1),
        "gfl": (0.55, -0.8, 0.6), "gfr": (-0.55, -0.8, 0.6), "gbl": (0.6, 0.75, 0.6),
        "gleft": (1, 0, 0.65), "gfront": (0, -1, 0.65), "eyeq": (0.75, -0.66, 0.08), "eyeg": (0.21, -0.98, 0.05),
        "tq": (0.7, 0.7, 0.35), "tback": (0, 1, 0.35), "tleft": (1, 0, 0.1)}      # g*: from the game camera's height


def arg(args, k, d=None): return args[args.index(k) + 1] if k in args else d


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, dst = args[0], args[1]; os.makedirs(dst, exist_ok=True)
    seq = arg(args, "--seq"); frames = [int(f) for f in arg(args, "--frames", "0").split(",")]
    views = arg(args, "--views", "hfront,hq,hleft").split(","); tex = "--tex" in args
    width = float(arg(args, "--width", "14")); res = int(arg(args, "--res", "640")); focus = arg(args, "--focus", "head")
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "cat.blend"))
    arm = bpy.data.objects["root"]; mesh = bpy.data.objects["SK_VP_Cat"]
    cat_anims.to_cm(arm, mesh)
    arm.animation_data_create()
    if seq:
        rig = L.CatRig(arm); s = S.SEQS[seq]; act = bpy.data.actions.new("VP_Cat_" + seq); L.use_action(arm, act, s.frames)
        for f in range(s.frames + 1): rig.key(s.frame_pose(f), f, overlay=s.overlay)
        L.use_action(arm, act, s.frames)
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = res; sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"; sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("cu"); sc.world.color = (0.30, 0.30, 0.32)
    if tex:
        import cat_look_tex
        sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48
        sc.world.use_nodes = True; bg = sc.world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.35, 0.35, 0.38, 1); bg.inputs[1].default_value = 0.6
        cat_look_tex.apply(mesh); sc.view_settings.exposure = 0.0
        for name, loc, power in (("key", (-60, -90, 90), 9e5), ("fill", (90, -40, 40), 3e5), ("rim", (0, 90, 80), 4e5)):
            ld = bpy.data.lights.new(name, "POINT"); ld.energy = power; ld.shadow_soft_size = 20
            lo = bpy.data.objects.new(name, ld); lo.location = loc; sc.collection.objects.link(lo)
    else:
        sc.render.engine = "BLENDER_WORKBENCH"; sh = sc.display.shading
        sh.light = "STUDIO"; sh.color_type = "MATERIAL"; sh.show_cavity = True
        cols = {"Fur": (0.66, 0.66, 0.66, 1), "Eye": (0.25, 0.35, 0.6, 1), "FurCard": (0.5, 0.45, 0.4, 1),
                "Mouth": (0.55, 0.22, 0.25, 1), "Teeth": (0.95, 0.92, 0.82, 1)}
        for s_ in mesh.material_slots:
            if s_.material: s_.material.diffuse_color = cols.get(s_.material.name, (1, 0, 1, 1))
    if "--floor" in args:
        fm = bpy.data.materials.new("cu_floor"); fm.diffuse_color = (0.30, 0.27, 0.22, 1)
        gm = bpy.data.materials.new("cu_grid"); gm.diffuse_color = (0.18, 0.16, 0.13, 1)
        bpy.ops.mesh.primitive_plane_add(size=120.0, location=(0, 0, -0.01)); bpy.context.object.data.materials.append(fm)
        for i in range(-12, 13):
            for rot in (0.0, math.pi / 2):
                bpy.ops.mesh.primitive_plane_add(size=1.0, location=(i * 5.0, 0, 0.0) if rot else (0, i * 5.0, 0.0))
                o = bpy.context.object; o.scale = (0.25, 120.0, 1) if rot else (120.0, 0.25, 1); o.data.materials.append(gm)
    cam = bpy.data.objects.new("cu_cam", bpy.data.cameras.new("cu_cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = width; cam.data.clip_start = 1.0; cam.data.clip_end = 5000.0
    for f in frames:
        sc.frame_set(f)
        if focus == "head":
            pb = arm.pose.bones["head"]; c = arm.matrix_world @ (pb.head * 0.35 + pb.tail * 0.65)
        elif focus == "body": c = Vector((0, 3.0, 15.0))
        elif focus == "tail":                                                    # the tail root (rump to tail transition)
            c = arm.matrix_world @ arm.pose.bones["tail_01"].head
        elif focus == "eye":                                                     # the left eye
            pb = arm.pose.bones["head"]; c = arm.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted() @ \
                Vector([v * 100 for v in cat_model._hp(cat_model.EYE_AT)])
        elif focus == "mouth":
            c = arm.matrix_world @ ((arm.pose.bones["jaw"].tail + arm.pose.bones["head"].tail) * 0.5)    # between chin and nose
        else: c = Vector([float(v) * 100 for v in focus.split(",")])
        for v in views:
            d = Vector(DIRS[v]).normalized(); cam.location = c + d * 400.0
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(dst, "%s_%s_%d.png" % (seq or "rest", v, f)); sc.render.filepath = path
            bpy.ops.render.render(write_still=True); print("CLOSEUP " + path)


if __name__ == "__main__":
    main()
