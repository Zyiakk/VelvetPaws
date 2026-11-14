"""Editor test (AltUI edtest.sh, after BPGen): BP_VP_Cat implements BPI_AltUIMod and answers AltUI with its defaults (Get AltUI
Value / Color / Text / Key on the class default object against ui.to_ui and brain.SETTINGS), its status line (ui.status), the cat's
four AltUI tables on AltUI's row structs with ui.py's rows, the mesh's material slots in names.SLOTS order and every material
parameter Apply Look sets (ui.LOOK) on the slot's instance."""
import os, sys
import unreal
W = os.environ.get("VELVETPAWS_DEV") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(W, "scripts"), os.path.join(W, "tools", "blender"), os.path.join(os.environ["ALTUI_DEV"], "tests", "editor")]
from velvetpaws import names, brain as B, ui as UI
from edtest_lib import report, expect, run
from kit_call import call_pure

IFACE = "/Game/Mod/AltUI/BPI_AltUIMod.BPI_AltUIMod_C"
STRUCTS = ["S_AltUIModEntry", "S_AltUIModField", "S_AltUIModAction", "S_AltUIModPreset"]
MEL = unreal.MaterialEditingLibrary


def one(v): return v[0] if isinstance(v, tuple) and len(v) == 1 else v


def main():
    cdo = unreal.get_default_object(unreal.load_class(None, names.BP_CLASS))
    report("implements BPI_AltUIMod", unreal.SystemLibrary.does_implement_interface(cdo, unreal.load_class(None, IFACE)))
    for k in UI.VALUES:
        expect("Get AltUI Value " + k, round(one(call_pure(cdo, "Get AltUI Value", (unreal.Name(k),))), 3), round(UI.to_ui(k, UI.default(k)), 3))
    c = one(call_pure(cdo, "Get AltUI Color", (unreal.Name("EyeColor"),)))
    expect("Get AltUI Color EyeColor", tuple(round(v, 3) for v in (c.r, c.g, c.b)), tuple(round(v, 3) for v in names.DEF_EYE[:3]))
    expect("Get AltUI Text CatName", one(call_pure(cdo, "Get AltUI Text", (unreal.Name("CatName"),))), "")
    expect("status line", one(call_pure(cdo, "Get AltUI Text", (unreal.Name(UI.INFO),))),
           UI.status("", True, 0, True, False, B.MODE_FOLLOW, B.ST_REST, B.P_STAND, False, False,
                     UI.DBG_DEFAULT if B.DEBUG_SPOTS else None))
    report("no recall key", not unreal.InputLibrary.key_is_valid(one(call_pure(cdo, "Get AltUI Key", (unreal.Name("RecallKey"),)))))
    for t, s in zip(UI.TABLES, STRUCTS):
        dt = unreal.load_asset(names.ROOT + "/" + t)
        expect(t + " row struct", dt.get_editor_property("row_struct").get_path_name(), "/Game/Mod/AltUI/%s.%s" % (s, s))
    expect("AltUI_Fields rows", len(unreal.DataTableFunctionLibrary.get_data_table_row_names(unreal.load_asset(names.ROOT + "/AltUI_Fields"))), len(UI.FIELDS))
    mesh = unreal.load_asset(names.MESH)
    got = [m.get_editor_property("material_interface").get_path_name() for m in mesh.get_editor_property("materials")]
    expect("material slots in names.SLOTS order", got, [names.obj(names.SLOTS[s]) for s in names.SLOTS])
    for slot, p, _ in UI.LOOK:
        mi = unreal.load_asset(names.SLOTS[slot])
        have = [str(n) for n in MEL.get_vector_parameter_names(mi)] + [str(n) for n in MEL.get_scalar_parameter_names(mi)]
        report("%s has %s" % (slot, p), p in have, str(have))


run(main)
