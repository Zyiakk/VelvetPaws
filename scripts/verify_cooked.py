#!/usr/bin/env python3
"""What VERIFY OK does not see: the pak holds exactly our assets (no kit stand-ins), the loader row names BP_VP_Cat_C (a class
not built before the table cooks as null without an error), the mod table uses the game's DLC_Struct, the mesh uses its own
skeleton, the materials and textures; the sequences, the blend space, ABP_VP_Cat and the montages are on our skeleton; only
VP_Cat_Overlay is additive (tagged property AdditiveAnimType, read with uasset_props) and every sequence has its cat_seqs length;
BP_VP_Cat imports ABP_VP_Cat; its cooked bytecode (AltUI bpdump) has the stage 3 core calls (level kind, Place Cat timer, Jodi
guard, collision, teleport, floor trace, save game), the pure decision functions VP_* of brain.BP_FUNCS, the core functions and
every hook of brain.HOOKS, and no stage 2 demo cycle ("Demo 0"); the cooked class defaults of the inherited components (capsule
14/16 cm, movement without controller) as written by BPGen subobject_defaults; the sounds: every SoundWave imports SoundClass_SFX and its attenuation, only the purr loops, the attenuation assets carry their settings, BP_VP_Cat imports every wave; the office tables have as many rows as
assets/office/office_map.json; stage 5: BP_VP_Cat implements BPI_AltUIMod (imported, never shipped), the AltUI event names are in
its bytecode, the test keys are gone, and the four AltUI tables use AltUI's row structs with the rows ui.py builds; Pick Office Spot sets Found = true
somewhere and Enemy Place reads the enemy's location (a second primary "return" node once overwrote both). Usage: verify_cooked.py <VelvetPaws.pak> (needs ALTUI_DEV)"""
import json, os, subprocess, sys, tempfile
S = os.path.join(os.environ["ALTUI_DEV"], "scripts"); sys.path.insert(0, S)
from uasset_props import read_summary, dump

ROOT = "/Game/Mod/VelvetPaws"
TEXTURES = {"T_VP_CatMaskA", "T_VP_CatMaskB", "T_VP_CatFur_N", "T_VP_CatCard", "T_VP_CatEye"}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "blender"))
sys.path.insert(0, os.path.join(os.environ["ALTUI_DEV"], "assets", "gen"))
import modui as MU
from velvetpaws import names as N
from velvetpaws import ui as UI
from velvetpaws import sounds as SN
import cat_seqs as CS
PAIRS = [(m.rsplit("/", 1)[1], mi.rsplit("/", 1)[1]) for m, mi in N.MATERIALS]     # (master, instance) per slot
MATS = {x for pair in PAIRS for x in pair}
MONTAGES = [m["name"] for m in CS.MONTAGES]
FILES = {a.rsplit("/", 1)[-1] for a in N.pak_assets(CS.ORDER, MONTAGES)}
# on the cat's own skeleton: every sequence, the blend space, the animation blueprint, every montage
ANIMS = ["VP_Cat_" + n for n in CS.ORDER] + ["AM_VP_" + m for m in MONTAGES] + [N.BLENDSPACE.rsplit("/", 1)[1], N.ABP.rsplit("/", 1)[1]]
STUBS = {"BlueprintToLoad_Struct", "BlueprintLoader", "DLC_Struct", "Female_Skeleton", "SoundClass_SFX",
         "BPI_AltUIMod", "S_AltUIModEntry", "S_AltUIModField", "S_AltUIModAction", "S_AltUIModPreset"}
# what BP_VP_Cat must call (assets/gen/vp_bp_core.py, vp_bp_decide.py); a missing one means BPGen dropped a node
CALLS = {"GetCurrentLevelName", "K2_DestroyActor", "K2_SetTimer", "GetPlayerCharacter", "LineTraceSingle",
         "BreakHitResult", "SelectVector", "FindLookAtRotation", "MakeRotator", "GetAnimInstance",
         # stage 3 core (vp_bp_core.py) instead of the stage 2 demo cycle
         "IsValid", "DisableMovement", "SetMovementMode", "SetActorScale3D", "SetActorHiddenInGame", "SetCollisionObjectType",
         "SetCollisionResponseToAllChannels", "SetCollisionResponseToChannel", "SetCollisionEnabled", "K2_TeleportTo",
         "StopMovementImmediately", "DoesSaveGameExist", "LoadGameFromSlot", "CreateSaveGameObject", "SaveGameToSlot", "VSize2D", "FInterpTo",
         # stage 3: the pure decision functions VP_* (assets/gen/vp_bp_decide.py)
         "MapRangeClamped", "DegCos", "DegSin", "Dot_VectorVector", "GetCharacterAsNumber", "Multiply_IntInt", "Sqrt",
         "EqualEqual_StriStri",
         # stage 3: postures, actions, routine (assets/gen/vp_bp_posture.py)
         "Montage_Play", "Montage_JumpToSection", "Montage_Stop", "RandomFloatInRange",
         "FClamp",   # Size clamped after loading (review of Tasks 6+7)
         # stage 3: movement, modes, keys (assets/gen/vp_bp_move.py)
         "AddMovementInput", "FindPathToLocationSynchronously", "K2_GetRandomReachablePointInRadius", "GetPlayerCameraManager",
         "GetCameraLocation", "GetCameraRotation", "WasInputKeyJustPressed", "Key_IsValid", "Percent_IntInt",
         # stage 3: spots and jumps (assets/gen/vp_bp_jump.py)
         "LaunchCharacter", "IsFalling", "GetGravityZ", "RInterpTo", "K2_SetActorRotation", "RandomFloat",
         # stage 3: combat (assets/gen/vp_bp_combat.py)
         "GetAllActorsOfClass", "EqualEqual_ObjectObject",
         # stage 3: home, level start, place saving (assets/gen/vp_bp_home.py)
         "GetDataTableRowNames", "K2_ProjectPointToNavigation", "Array_Add",
         # stage 4: sound decisions (vp_bp_decide.py)
         "Exp", "FFloor", "Min",
         # stage 4: sounds (assets/gen/vp_bp_sound.py)
         "SpawnSoundAttached", "SetVolumeMultiplier", "SetPitchMultiplier", "FadeIn", "FadeOut", "RandomBool",
         # stage 5: AltUI page, look at runtime, presence (assets/gen/vp_bp_ui.py)
         "CreateDynamicMaterialInstance", "SetVectorParameterValue", "SetScalarParameterValue", "MakeColor", "EqualEqual_NameName", "SelectColor",
         "SelectString", "Concat_StrStr", "IsEmpty", "Round", "Clamp", "GetActorScale3D", "K2_AddActorWorldOffset",
         "SetComponentTickEnabled",   # final review M2: no pose ticks while dormant
         # round 6: rubbing loop and its phase (vp_bp_decide.py, vp_bp_rub.py), facing check on landing
         "Sin", "Cos", "Atan2", "GetActorForwardVector", "NormalizeAxis"}
from velvetpaws import brain as BR
FUNCS = set(BR.BP_FUNCS) | set(BR.HOOKS) | {"Think", "Update Anim", "Enable Body", "Teleport To", "Floor At", "Line Clear", "Load Settings", "Save Settings",
                                                     "Play Cue", "Play Meow", "Fire Cue", "Start Purr", "Stop Purr", "Stop Sounds",
                                                     "Posture Step", "Snap Posture", "Do Action", "Routine",
                                                     "Start Move", "Make Path", "Office Path", "Nearest Walk", "Arrive", "Stuck",
                                                     "Teleport Behind", "Roam Next", "Recall", "Cycle Mode", "Start Jump",
                                                     "Take Spot", "Pick Office Spot", "Abort Jump", "Probe Spot",
                                                     "Begin Alarm", "Face Enemy", "Flee", "Save Place",
                                                     MU.GET_VALUE, MU.GET_COLOR, MU.GET_TEXT, MU.GET_KEY, "Status Text", "Make Materials", "Apply Look",
                                                     "Apply Size", "Apply Volume", "Refresh Presence", "Go Dormant", "Save Soon", "Set Mode",
                                                     # round 6: closed doors, routes, rubbing
                                                     "Blocked", "Door Closed", "Path Shut", "Route Prep", "Route Open", "Start Rub", "End Rub"}
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errs = []


def imports(path): return read_summary(path)[2]


def _walk(o):
    """Every dict inside a bpdump statement list (expressions nest)."""
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from _walk(v)
    elif isinstance(o, list):
        for v in o: yield from _walk(v)


def imp_names(path): return {i[3] for i in imports(path)}


with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, os.path.join(S, "pak11_extract.py"), sys.argv[1], d, "."], check=True, stdout=subprocess.DEVNULL)
    paths = {os.path.splitext(f)[0]: os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.endswith(".uasset")}
    found = set(paths)
    if found != FILES: errs.append("pak holds %s" % sorted(found ^ FILES))
    if found & STUBS: errs.append("kit stand-ins in the pak: %s" % sorted(found & STUBS))
    p = lambda n: paths[n]
    # loader row -> our class (null when the class was built after the table)
    rows = dump(p("TKA_BlueprintLoader"))["TKA_BlueprintLoader"]
    if rows["props"].get("RowStruct") != "import:BlueprintToLoad_Struct (UserDefinedStruct)": errs.append("loader table struct %s" % rows["props"])
    row = rows.get("rows", {}).get("VelvetPaws") or {}
    cls = [v for k, v in row.items() if k.startswith("Actor_Class")]
    if cls != ["import:BP_VP_Cat_C (BlueprintGeneratedClass)"]: errs.append("loader row Actor Class is %s (row %s)" % (cls, row))
    if ROOT + "/BP_VP_Cat" not in imp_names(p("TKA_BlueprintLoader")): errs.append("loader table does not import " + ROOT + "/BP_VP_Cat")
    if "/Game/Mod/TKA_BlueprintLoader/BlueprintToLoad_Struct" not in imp_names(p("TKA_BlueprintLoader")): errs.append("loader struct path")
    mt = dump(p("TKA_Mod_Table"))["TKA_Mod_Table"]
    if "/Game/Project/Tables/DLC_Struct" not in imp_names(p("TKA_Mod_Table")) or "VelvetPaws" not in mt.get("rows", {}):
        errs.append("mod table %s" % mt)
    # mesh: own skeleton, physics asset, the material instances of all slots
    mesh = imp_names(p("SK_VP_Cat"))
    if "Female_Skeleton" in mesh: errs.append("mesh uses Female_Skeleton")
    for n in ("SK_VP_Cat_Skeleton", "SK_VP_Cat_PhysicsAsset", *(mi for _, mi in PAIRS)):
        if n not in mesh and ROOT + "/" + n not in mesh and not any(x.endswith("/" + n) for x in mesh):
            # own-package objects are exports, not imports: check the name table
            if n not in read_summary(p("SK_VP_Cat"))[1]: errs.append("mesh does not reference " + n)
    for a in ANIMS:
        if a in paths and "SK_VP_Cat_Skeleton" not in imp_names(p(a)): errs.append("%s not on SK_VP_Cat_Skeleton (imports %s)" % (a, sorted(imp_names(p(a)))))
    # sequences: the overlay is additive (local space, ABP_VP_Cat's Apply Additive), every other one is not; lengths as in cat_seqs
    for n in CS.ORDER:
        a = "VP_Cat_" + n
        if a not in paths: continue
        props = dump(p(a)).get(a, {}).get("props", {})
        want = "AAT_LocalSpaceBase" if CS.SEQS[n].overlay else None
        if props.get("AdditiveAnimType") != want: errs.append("%s AdditiveAnimType %s, want %s" % (a, props.get("AdditiveAnimType"), want))
        if abs(props.get("SequenceLength", -1) - CS.length(n)) > 1e-3: errs.append("%s length %s, want %.4f" % (a, props.get("SequenceLength"), CS.length(n)))
    for m, mi in PAIRS:
        if m not in imp_names(p(mi)): errs.append("%s has no parent %s" % (mi, m))
    used = set().union(*(imp_names(p(m)) for m in ("M_VP_CatFur", "M_VP_CatFurCard", "M_VP_CatEye")))
    if not TEXTURES <= used: errs.append("materials lack %s" % sorted(TEXTURES - used))
    # sounds (plan Etappe 4): class, attenuation and looping as set by scripts/import_sounds.py
    for a, base, _ in SN.assets():
        if a not in paths: continue
        im = imp_names(p(a)); s = SN.by_name(base)
        if "SoundClass_SFX" not in im: errs.append("%s is not in SoundClass_SFX (imports %s)" % (a, sorted(im)))
        if SN.att_asset(s.att) not in im: errs.append("%s lacks %s" % (a, SN.att_asset(s.att)))
        loop = dump(p(a)).get(a, {}).get("props", {}).get("bLooping") is True
        if loop != s.loop: errs.append("%s looping %s, want %s" % (a, loop, s.loop))
    for k in SN.ATTENUATION:
        n = SN.att_asset(k)
        if n in paths and not {"FalloffDistance", "AttenuationShapeExtents"} <= set(read_summary(p(n))[1]): errs.append(n + " lacks its settings")
    # BP: mesh component points at SK_VP_Cat, the bytecode has the graph
    bp = imp_names(p("BP_VP_Cat"))
    if "SK_VP_Cat" not in bp: errs.append("BP_VP_Cat does not import SK_VP_Cat")
    miss_snd = [a for a, _, _ in SN.assets() if a not in bp]
    if miss_snd: errs.append("BP_VP_Cat does not import %s" % miss_snd)
    if not any(n.startswith("BPI_AltUIMod") or n.endswith("/BPI_AltUIMod") for n in bp):
        errs.append("BP_VP_Cat does not implement BPI_AltUIMod (imports %s)" % sorted(bp))
    if N.ABP not in bp and "ABP_VP_Cat_C" not in bp: errs.append("BP_VP_Cat does not reference ABP_VP_Cat (imports %s)" % sorted(bp))
    tool = os.path.join(os.environ["ALTUI_DEV"], "tools", "bpdump", "bin", "Release", "net10.0", "bpdump")
    if not os.path.exists(tool): errs.append("bpdump missing (%s): cd $ALTUI_DEV/tools/bpdump && dotnet build -c Release" % tool)
    else:
        out = os.path.join(d, "bp.json"); subprocess.run([tool, p("BP_VP_Cat"), out], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out) as fh: code = json.load(fh)
        s = json.dumps(code)
        miss = sorted(c for c in CALLS if '"%s"' % c not in s)
        if miss: errs.append("BP_VP_Cat bytecode lacks %s (functions %s)" % (miss, list(code)))
        missf = sorted(FUNCS - set(code))
        if missf: errs.append("BP_VP_Cat lacks functions %s" % missf)
        if '"JodisOffice"' not in s: errs.append("BP_VP_Cat bytecode lacks the level name JodisOffice")
        if '"Place Cat"' not in s: errs.append("BP_VP_Cat has no Place Cat event / timer name")
        if '"Demo 0"' in s: errs.append("BP_VP_Cat still has the stage 2 demo cycle")
        if ('" | spot: "' in s) != BR.DEBUG_SPOTS: errs.append("spot diagnostic in the status line: %s, want %s" % ('" | spot: "' in s, BR.DEBUG_SPOTS))
        for e in ('"Save Now"', '"%s"' % MU.ON_CHANGED, '"%s"' % MU.ON_COLOR, '"%s"' % MU.ON_TEXT, '"%s"' % MU.ON_KEY):
            if e not in s: errs.append("BP_VP_Cat bytecode lacks %s" % e)
        # literals the result nodes return (a second BPGen "return" node used to overwrite the first: Found = false on both branches)
        if not any(st.get("Inst") == "LetBool" and st.get("Variable", {}).get("Variable Name") == "Found" and st.get("Expression", {}).get("Inst") == "True"
                   for st in code.get("Pick Office Spot", [])):
            errs.append("Pick Office Spot never sets Found = true")
        if not any(e.get("Inst") == "Context" and e.get("Context", {}).get("Variable Name") == "Enemy"
                   and e.get("Expression", {}).get("Function") == "K2_GetActorLocation" for e in _walk(code.get("Enemy Place", []))):
            errs.append("Enemy Place never reads the enemy's location")
        left = [k for k in BR.TEST_KEYS.values() if '"%s"' % k in s]
        if left: errs.append("BP_VP_Cat still polls the test keys %s" % left)
    # class defaults of the inherited components, as cooked (BPGen subobject_defaults); a missing value was not saved
    bpd = dump(p("BP_VP_Cat"))
    by_cls = lambda c: [v.get("props", {}) for v in bpd.values() if v.get("class") == c]
    caps, cmcs = by_cls("CapsuleComponent"), by_cls("CharacterMovementComponent")
    if len(caps) != 1: errs.append("BP_VP_Cat has %d CapsuleComponent exports (%s)" % (len(caps), sorted(bpd)))
    for c in caps[:1]:
        if (c.get("CapsuleRadius"), c.get("CapsuleHalfHeight")) != (BR.CAPSULE_R, BR.CAPSULE_HH):
            errs.append("capsule %s/%s, want %s/%s" % (c.get("CapsuleRadius"), c.get("CapsuleHalfHeight"), BR.CAPSULE_R, BR.CAPSULE_HH))
    if len(cmcs) != 1: errs.append("BP_VP_Cat has %d CharacterMovementComponent exports (%s)" % (len(cmcs), sorted(bpd)))
    for c in cmcs[:1]:
        if c.get("bRunPhysicsWithNoController") is not True: errs.append("movement bRunPhysicsWithNoController %s" % c.get("bRunPhysicsWithNoController"))
        if c.get("MaxWalkSpeed") != BR.MAX_SPEED: errs.append("movement MaxWalkSpeed %s, want %s" % (c.get("MaxWalkSpeed"), BR.MAX_SPEED))
    # office tables: one row per walk point and spot of the map
    with open(os.path.join(W, N.OFFICE_MAP_REL)) as fh: omap = json.load(fh)
    for t, key in (("DT_VP_OfficeWalk", "walk"), ("DT_VP_OfficeSpots", "spots")):
        n = len(dump(p(t)).get(t, {}).get("rows", {}))
        if n != len(omap[key]): errs.append("%s has %d rows, want %d" % (t, n, len(omap[key])))
    # round 6 columns: doorway points (Door >= 0) and every spot's room above it
    rows = dump(p("DT_VP_OfficeWalk")).get("DT_VP_OfficeWalk", {}).get("rows", {})
    col = lambda r, name: next((v for k, v in r.items() if k.split("_")[0] == name), None)
    doors = sum(1 for r in rows.values() if isinstance(col(r, "Door"), int) and col(r, "Door") >= 0)
    if doors != sum(1 for w in omap["walk"] if w["door"] >= 0): errs.append("DT_VP_OfficeWalk has %d doorway rows, want %d" % (doors, sum(1 for w in omap["walk"] if w["door"] >= 0)))
    srows = dump(p("DT_VP_OfficeSpots")).get("DT_VP_OfficeSpots", {}).get("rows", {})
    if sorted(round(col(r, "Room") or 0.0, 1) for r in srows.values()) != sorted(round(s["room"], 1) for s in omap["spots"]):
        errs.append("DT_VP_OfficeSpots Room column differs from the map")
    # AltUI's tables of the cat (MOD_UI.md): AltUI's row structs (imported, never shipped), rows as ui.py builds them
    for t, struct in zip(UI.TABLES, ("S_AltUIModEntry", "S_AltUIModField", "S_AltUIModAction", "S_AltUIModPreset")):
        d = dump(p(t)).get(t, {})
        if d.get("props", {}).get("RowStruct") != "import:%s (UserDefinedStruct)" % struct: errs.append("%s row struct %s" % (t, d.get("props")))
        if "/Game/Mod/AltUI/" + struct not in imp_names(p(t)): errs.append("%s does not import /Game/Mod/AltUI/%s" % (t, struct))
    for t, want in (("AltUI_Fields", len(UI.FIELDS)), ("AltUI_Actions", len(UI.ACTIONS)), ("AltUI_Presets", len(UI.PRESETS))):
        n = len(dump(p(t)).get(t, {}).get("rows", {}))
        if n != want: errs.append("%s has %d rows, want %d" % (t, n, want))
    if "BP_VP_Cat_C" not in json.dumps(dump(p("AltUI_Actions"))): errs.append("AltUI_Actions does not name BP_VP_Cat_C")
    if "BP_VP_Cat_C" not in json.dumps(dump(p("AltUI_Entries"))): errs.append("AltUI_Entries does not name BP_VP_Cat_C")
print("\n".join(errs) or "COOKED OK"); sys.exit(1 if errs else 0)
