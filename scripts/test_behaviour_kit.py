"""Editor test (AltUI edtest.sh, after BPGen built 91_velvetpaws.json): every pure decision function VP_* of BP_VP_Cat against
brain.kit_cases() (called on the class default object); from Task 7 on also the class defaults, the inherited components and the
office tables against assets/office/office_map.json."""
import json, os, sys
import unreal
W = os.environ.get("VELVETPAWS_DEV") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(W, "scripts"), os.path.join(W, "tools", "blender"), os.path.join(os.environ["ALTUI_DEV"], "tests", "editor")]
from velvetpaws import names, brain as B
from edtest_lib import report, expect, run
from kit_call import call_pure


def _arg(v):
    return unreal.Vector(*v) if isinstance(v, tuple) else v


def _same(got, want):
    if isinstance(want, tuple) and len(want) == 4: return all(abs(a - b) < 0.01 for a, b in zip((got.r, got.g, got.b, got.a), want))
    if isinstance(want, tuple): return all(abs(a - b) < 0.05 for a, b in zip((got.x, got.y, got.z), want))
    if isinstance(want, float): return abs(got - want) < 0.01
    return got == want


def cdo_checks(cdo):
    cap = cdo.get_editor_property("capsule_component"); cmc = cdo.get_editor_property("character_movement"); mesh = cdo.get_editor_property("mesh")
    expect("capsule radius", round(cap.get_unscaled_capsule_radius(), 2), B.CAPSULE_R)
    expect("capsule half height", round(cap.get_unscaled_capsule_half_height(), 2), B.CAPSULE_HH)
    expect("capsule spawns without collision", str(cap.get_collision_enabled()), str(unreal.CollisionEnabled.NO_COLLISION))
    expect("no controller physics", cmc.get_editor_property("run_physics_with_no_controller"), True)
    expect("orient to movement", cmc.get_editor_property("orient_rotation_to_movement"), True)
    expect("max walk speed", round(cmc.get_editor_property("max_walk_speed"), 2), B.MAX_SPEED)
    expect("mesh", mesh.get_editor_property("skeletal_mesh").get_path_name(), names.obj(names.MESH))
    expect("anim class", mesh.get_editor_property("anim_class").get_path_name(), names.ABP_CLASS)
    expect("mesh z", round(mesh.get_editor_property("relative_location").z, 2), -B.CAPSULE_HH)
    expect("not damageable", cdo.get_editor_property("can_be_damaged"), False)
    expect("no auto possess", str(cdo.get_editor_property("auto_possess_ai")), str(unreal.AutoPossessAI.DISABLED))


def table_checks():
    with open(os.path.join(W, names.OFFICE_MAP_REL)) as f: m = json.load(f)
    walk = unreal.load_asset(names.DT_WALK); spots = unreal.load_asset(names.DT_SPOT)
    expect("walk rows", len(unreal.DataTableFunctionLibrary.get_data_table_row_names(walk)), len(m["walk"]))
    expect("spot rows", len(unreal.DataTableFunctionLibrary.get_data_table_row_names(spots)), len(m["spots"]))
    col = [s.strip('"') for s in unreal.DataTableFunctionLibrary.get_data_table_column_as_string(walk, "Next")]
    expect("next-hop strings survive the import", col == [w["next"] for w in m["walk"]], True)


def decision_checks(cdo):
    bad = []
    for fn, args, want in B.kit_cases():
        got = call_pure(cdo, fn, tuple(_arg(a) for a in args))
        if isinstance(got, tuple) and len(got) == 1: got = got[0]
        if not _same(got, want): bad.append("%s%r -> %r, want %r" % (fn, args, got, want))
    for b in bad[:20]: unreal.log_warning("EDTEST info " + b)
    expect("decision cases wrong", len(bad), 0)


def main():
    cls = unreal.load_class(None, names.BP_CLASS); report("BP_VP_Cat loads", cls is not None)
    cdo = unreal.get_default_object(cls)
    cdo_checks(cdo); table_checks(); decision_checks(cdo)
    report("save game loads", unreal.load_class(None, names.SG_CLASS) is not None)


run(main)
