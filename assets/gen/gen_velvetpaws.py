"""Generates assets/91_velvetpaws.json for BPGen: the office structs and tables (assets/office/office_map.json), the save game
SG_VP_Cat, the cat's animation sequences (cat_seqs.ORDER) on its own skeleton, the locomotion blend space, the animation blueprint
ABP_VP_Cat (blend space -> DefaultSlot -> additive overlay), the posture and action montages, BP_VP_Cat (a Character built by
vp_bp_core.cat_bp from MODULES, incl. sounds (vp_bp_sound)) with the defaults of its inherited components (subobject_defaults, right after it) and the
Blueprint Loader and mod tables. Order: structs -> tables and classes they name before the blueprint that uses them -> sequences ->
blend space -> animplayer (adds the slot to the skeleton) -> montages -> BP_VP_Cat -> its subobject defaults -> AltUI tables of the cat (Entries, Fields, Actions, Presets) -> loader tables (a row
naming a class not built yet cooks as null)."""
import hashlib, os, sys

W = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(W, "scripts"))
ALTUI_DEV = os.environ.get("ALTUI_DEV") or os.path.join(W, "..", "..", "AltUI", "dev")
sys.path.insert(0, os.path.join(ALTUI_DEV, "assets", "gen"))
from bpdsl import *
from velvetpaws import names
sys.path.insert(0, os.path.join(W, "tools", "blender"))
import cat_seqs as CS
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # vp_*.py next to this file (also when loaded by tests via importlib)
import vp_bp_decide
import vp_bp_posture
import vp_bp_move
import vp_bp_jump
import vp_bp_combat
import vp_bp_home
import vp_bp_sound
import vp_bp_ui
import vp_bp_rub
import modui as mu
import json
from velvetpaws import brain as B
from velvetpaws import sounds as SN
from velvetpaws import ui as UI
import vp_bp_core as core
TEST_KEYS = False    # stage 5: AltUI is the way in (play test keys of stages 3/4 off: brain.TEST_KEYS)
MODULES = [vp_bp_decide, vp_bp_posture, vp_bp_move, vp_bp_jump, vp_bp_combat, vp_bp_home, vp_bp_sound, vp_bp_ui, vp_bp_rub]

BPL_STRUCT = "/Game/Mod/TKA_BlueprintLoader/BlueprintToLoad_Struct"
DLC_STRUCT = "/Game/Project/Tables/DLC_Struct"
ANIM_REL = os.path.join("..", "build", "velvetpaws", "anim")   # relative to assets/
VEC = "struct:/Script/CoreUObject.Vector"


def fbx_rel(name): return os.path.join(ANIM_REL, "VP_Cat_%s.fbx" % name)


def anim_assets(shas):
    """shas: {sequence name: sha1 of its FBX}."""
    out = [animimport(names.seq(n), names.SKELETON, fbx_rel(n), fbx_sha1=shas[n]) for n in CS.ORDER]
    out.append(blendspace1d(names.BLENDSPACE, names.SKELETON, names.VAR_SPEED, 0, CS.SPEED_MAX, CS.SPEED_GRID,
                            [(names.seq(n), v) for n, v in CS.BLEND_SAMPLES], smoothing=0.3))
    out.append(animplayer(names.ABP, names.SKELETON, names.BLENDSPACE, names.seq("Overlay"), speed_var=names.VAR_SPEED,
                          alpha_var=names.VAR_OVERLAY, slot=names.SLOT, add_slot=True, make_overlay_additive=True))
    for m in CS.MONTAGES:
        segs = [segment(names.seq(s), length=CS.length(s)) for _, s, _ in m["sections"]]
        secs = [section(n, t, next=nx) for n, t, nx in CS.section_times(m)]
        out.append(montage(names.montage(m["name"]), names.SKELETON, names.SLOT, segs, sections=secs, blend_in=m["blend"][0], blend_out=m["blend"][1]))
    return out


def loader_table():
    return datatable(names.ROOT + "/TKA_BlueprintLoader", BPL_STRUCT, rows={names.MOD: {"Actor Class": names.BP_CLASS}})


def mod_table():
    return datatable(names.ROOT + "/TKA_Mod_Table", DLC_STRUCT, rows={names.MOD: {"Caption": "VelvetPaws", "Desc": "A cat that keeps Jodi company",
                                                                                  "Version": 0.2, "Tables": []}})


def structs():
    return [struct(names.S_WALK, [param("Index", "int"), param("Location", VEC), param("Next", "string"), param("Door", "int"), param("DoorA", VEC),
                                  param("DoorB", VEC)]),
            struct(names.S_SPOT, [param("Index", "int"), param("Label", "string"), param("Location", VEC), param("From", VEC), param("Yaw", "float"),
                                  param("Height", "float"), param("Posture", "int"), param("Weight", "float"), param("Room", "float"), param("Walk", "int")])]


def _v(p): return "(X=%.1f,Y=%.1f,Z=%.1f)" % tuple(p)


def office_tables():
    """The measured office map as two tables; rows in index order (GetDataTableRowNames keeps it, the Next strings count in it).
    The map's src_debug field is build-only and not packed."""
    with open(os.path.join(W, names.OFFICE_MAP_REL)) as f: m = json.load(f)
    walk = {"W%03d" % i: {"Index": i, "Location": _v(w["loc"]), "Next": w["next"], "Door": w["door"], "DoorA": _v(w["door_a"]),
                          "DoorB": _v(w["door_b"])} for i, w in enumerate(m["walk"])}
    spots = {"S%02d" % i: {"Index": i, "Label": s["label"], "Location": _v(s["loc"]), "From": _v(s["from"]), "Yaw": s["yaw"],
                           "Height": s["height"], "Posture": s["posture"], "Weight": s["weight"], "Room": s["room"], "Walk": s["walk"]}
             for i, s in enumerate(m["spots"])}
    return [datatable(names.DT_WALK, names.S_WALK, rows=walk), datatable(names.DT_SPOT, names.S_SPOT, rows=spots)]


def save_game():
    return blueprint(names.SG, "/Script/Engine.SaveGame", variables=[var(n, t, default=d) for n, t, d in B.SETTINGS + B.PLACE_VARS])


def cat_bp():
    return core.cat_bp(MODULES, {"test_keys": TEST_KEYS, "interfaces": [mu.INTERFACE]})


def altui_tables():
    """The cat's page in AltUI's Mods tab (MOD_UI.md): on AltUI's row structs, which the pak never ships; after BP_VP_Cat (rows name it)."""
    t = lambda name, struct, rows: datatable(names.ROOT + "/" + name, struct, rows=rows)
    return [t(mu.ENTRIES_TABLE, mu.ENTRY_STRUCT, UI.entry_rows(names.BP_CLASS)), t(mu.FIELDS_TABLE, mu.FIELD_STRUCT, UI.field_rows()),
            t(mu.ACTIONS_TABLE, mu.ACTION_STRUCT, UI.action_rows(names.BP_CLASS)), t(mu.PRESETS_TABLE, mu.PRESET_STRUCT, UI.preset_rows())]


def build(shas):
    return (structs() + office_tables() + [save_game()] + anim_assets(shas) + [cat_bp()] + core.subobjects() + altui_tables()
            + [loader_table(), mod_table()])


def main():
    assets_dir = os.path.join(W, "assets")
    shas = {n: hashlib.sha1(open(os.path.join(assets_dir, fbx_rel(n)), "rb").read()).hexdigest() for n in CS.ORDER}
    write(os.path.join(assets_dir, "91_velvetpaws.json"), build(shas))
    with open(os.path.join(assets_dir, "velvetpaws_manifest.txt"), "w") as f: f.write("91_velvetpaws.json\n")


if __name__ == "__main__":
    main()
