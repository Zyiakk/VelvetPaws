"""Editor script (AltUI edtest.sh): imports the cat's textures, builds its five master materials and their instances,
imports the skeletal mesh with a NEW skeleton and physics asset and maps its slots. Prints EDTEST PASS.
Reruns in place: the mesh (with skeleton and physics asset) goes first, the masters are emptied and rebuilt rather than
deleted (deleting a material something still uses crashes the commandlet, see RedDunesExile fauna_material.py)."""
import os, sys, unreal

W = os.environ["VELVETPAWS_DEV"]; sys.path.insert(0, os.path.join(W, "scripts"))
from velvetpaws import names

AT = unreal.AssetToolsHelpers.get_asset_tools(); MEL = unreal.MaterialEditingLibrary; EAL = unreal.EditorAssetLibrary
OUT = names.build_dir(W)
MP = unreal.MaterialProperty
BONES = 37                      # tools/blender/cat_model.py: root + 36


def fail(msg):
    unreal.log_error("EDTEST FAIL " + msg); raise SystemExit(1)


def task(path, dest, name, opts=None):
    t = unreal.AssetImportTask()
    for k, v in (("filename", path), ("destination_path", dest), ("destination_name", name), ("automated", True), ("save", False), ("replace_existing", True)):
        t.set_editor_property(k, v)
    if opts: t.set_editor_property("options", opts)
    return t


def import_textures():
    for n in names.TEXTURES:                # delete first: a failed PNG import must not silently keep an old texture
        p = "%s/%s" % (names.TEX, n)
        if EAL.does_asset_exist(p) and not EAL.delete_asset(p): fail("cannot delete " + p)
    tasks = [task(os.path.join(OUT, "tex", f), names.TEX, n) for n, (f, _) in names.TEXTURES.items()]
    AT.import_asset_tasks(tasks)
    TC = unreal.TextureCompressionSettings
    for n, (_, kind) in names.TEXTURES.items():
        t = unreal.load_asset("%s/%s" % (names.TEX, n))
        if not t: fail("texture not imported: " + n)
        comp, srgb = {"normal": (TC.TC_NORMALMAP, False), "mask": (TC.TC_MASKS, False), "color": (TC.TC_DEFAULT, True)}[kind]
        flip = kind == "normal"             # Blender bakes OpenGL normals (+Y); UE wants DirectX (-Y)
        t.set_editor_property("compression_settings", comp); t.set_editor_property("srgb", srgb)
        t.set_editor_property("flip_green_channel", flip)
        if t.get_editor_property("compression_settings") != comp or t.get_editor_property("srgb") != srgb \
                or bool(t.get_editor_property("flip_green_channel")) != flip:
            fail("texture settings not applied: " + n)
        EAL.save_loaded_asset(t)


def tex(n): return unreal.load_asset("%s/%s" % (names.TEX, n))


def new_material(path):
    if EAL.does_asset_exist(path):
        m = unreal.load_asset(path); MEL.delete_all_material_expressions(m); return m
    d, n = path.rsplit("/", 1); return AT.create_asset(n, d, unreal.Material, unreal.MaterialFactoryNew())


def expr(m, cls, x, y): return MEL.create_material_expression(m, cls, x, y)


def link(a, out, b, pin):
    if not MEL.connect_material_expressions(a, out, b, pin): fail("connect %s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), pin))


def to(a, out, prop):
    if not MEL.connect_material_property(a, out, prop): fail("connect %s.%s -> %s" % (a.get_name(), out, prop))


def tparam(m, name, texture, y, sampler):
    e = expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -900, y)
    e.set_editor_property("parameter_name", name); e.set_editor_property("texture", texture); e.set_editor_property("sampler_type", sampler); return e


def vparam(m, name, value, y):
    e = expr(m, unreal.MaterialExpressionVectorParameter, -900, y)
    e.set_editor_property("parameter_name", name); e.set_editor_property("default_value", unreal.LinearColor(*value)); return e


def sparam(m, name, value, y):
    e = expr(m, unreal.MaterialExpressionScalarParameter, -900, y)
    e.set_editor_property("parameter_name", name); e.set_editor_property("default_value", value); return e


# binding: the same formula as tools/blender/cat_look_tex.py (W.a passed as WA)
FUR_HLSL = """float p = saturate(dot(A.rgb, W.rgb));
float3 c = lerp(Base.rgb, Second.rgb, p);
c = lerp(c, Third.rgb, A.a * WA);
c *= 1.0 - Tick * B.b * 0.5;
c = lerp(c, float3(1,1,1), B.r * White);
c = lerp(c, Skin.rgb, B.g);
return c;"""
# after the formula (cat_look_tex does the same, names.root_tint): fur depth darkens and tints the roots (Undertone: the warm agouti
# bands, only as far as the coat is agouti: tabby, brindle, spots; solid coats keep their hue), the sheen brightens towards grazing angles
FUR_SHEEN_HLSL = """float3 u = lerp(float3(1,1,1), U.rgb, saturate(W.r + W.g + W.b));
float3 o = C * lerp((1.0 - Cav) * u, float3(1,1,1), B.a);
float s = Sheen * F * (1.0 - B.g);
return o * (1.0 + s) + s * 0.02;"""
FUR_ROUGH_HLSL = "return lerp(Rough + 0.08 * (1.0 - B.a), SkinRough, B.g);"


def custom(m, code, ins, out_type, desc, x, y):
    cu = expr(m, unreal.MaterialExpressionCustom, x, y)
    cu.set_editor_property("code", code); cu.set_editor_property("output_type", out_type); cu.set_editor_property("description", desc)
    inputs = []
    for name, _, _ in ins:
        ci = unreal.CustomInput(); ci.set_editor_property("input_name", name); inputs.append(ci)
    cu.set_editor_property("inputs", inputs)
    for name, e, out in ins: link(e, out, cu, name)
    return cu


def opaque(m):
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE); m.set_editor_property("two_sided", False)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)


def skeletal(m):
    m.set_editor_property("used_with_skeletal_mesh", True); m.set_editor_property("used_with_static_lighting", False)


def build_fur():
    m = new_material(names.MAT_FUR); opaque(m); skeletal(m)
    a = tparam(m, "MaskA", tex("T_VP_CatMaskA"), 0, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    b = tparam(m, "MaskB", tex("T_VP_CatMaskB"), 250, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    n = tparam(m, "FurNormal", tex("T_VP_CatFur_N"), 500, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    w = vparam(m, "PatternWeights", names.DEF_PATTERN, 750)   # 4.27: a vector parameter's "" pin is RGB only, alpha via "A"
    ins = [("A", a, "RGBA"), ("B", b, "RGBA"), ("W", w, ""), ("WA", w, "A"),
           ("Base", vparam(m, "BaseColor", names.DEF_BASE, 900), ""), ("Second", vparam(m, "SecondColor", names.DEF_SECOND, 1050), ""),
           ("Third", vparam(m, "ThirdColor", names.DEF_THIRD, 1200), ""), ("Skin", vparam(m, "SkinColor", names.DEF_SKIN, 1350), ""),
           ("White", sparam(m, "WhiteMarks", names.DEF_WHITE, 1500), ""), ("Tick", sparam(m, "Ticking", names.DEF_TICK, 1600), "")]
    F3, F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT3, unreal.CustomMaterialOutputType.CMOT_FLOAT1
    cu = custom(m, FUR_HLSL, ins, F3, "CatFur", -400, 400)
    fr = expr(m, unreal.MaterialExpressionFresnel, -400, 700)
    fr.set_editor_property("exponent", 3.0); fr.set_editor_property("base_reflect_fraction", 0.0)
    sh = custom(m, FUR_SHEEN_HLSL, [("C", cu, ""), ("B", b, "RGBA"), ("F", fr, ""), ("W", w, ""),
                                    ("Cav", sparam(m, "FurCavity", names.DEF_FUR_CAVITY, 1800), ""),
                                    ("U", vparam(m, "Undertone", names.DEF_UNDERTONE, 2200), ""),
                                    ("Sheen", sparam(m, "FurSheen", names.DEF_FUR_SHEEN, 1900), "")], F3, "CatFurSheen", -200, 500)
    ro = custom(m, FUR_ROUGH_HLSL, [("B", b, "RGBA"), ("Rough", sparam(m, "Roughness", names.DEF_FUR_ROUGH, 1700), ""),
                                    ("SkinRough", sparam(m, "SkinRoughness", names.DEF_SKIN_ROUGH, 2000), "")], F1, "CatFurRough", -200, 800)
    to(sh, "", MP.MP_BASE_COLOR)
    to(n, "RGB", MP.MP_NORMAL)
    to(ro, "", MP.MP_ROUGHNESS)
    to(sparam(m, "Specular", names.DEF_FUR_SPEC, 2100), "", MP.MP_SPECULAR)
    MEL.recompile_material(m); EAL.save_loaded_asset(m); return m


# fur cards: the coat formula (FUR_HLSL without the skin) sampled at the card's FurUV (UV 1: the fur UV of the skin it grows from),
# times the strand shade of the card texture; same parameter names as M_VP_CatFur, so a coat setting applies to both
CARD_HLSL = FUR_HLSL.replace("c = lerp(c, Skin.rgb, B.g);\n", "").replace("return c;", "return c * S.rgb * 1.25;")


def build_card():
    m = new_material(names.MAT_CARD); skeletal(m)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED); m.set_editor_property("two_sided", True)
    m.set_editor_property("opacity_mask_clip_value", 0.33)
    c = tparam(m, "Card", tex("T_VP_CatCard"), 0, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    uv1 = expr(m, unreal.MaterialExpressionTextureCoordinate, -1100, 300); uv1.set_editor_property("coordinate_index", 1)
    a = tparam(m, "MaskA", tex("T_VP_CatMaskA"), 250, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    b = tparam(m, "MaskB", tex("T_VP_CatMaskB"), 500, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    link(uv1, "", a, "UVs"); link(uv1, "", b, "UVs")
    w = vparam(m, "PatternWeights", names.DEF_PATTERN, 750)
    ins = [("A", a, "RGBA"), ("B", b, "RGBA"), ("W", w, ""), ("WA", w, "A"),
           ("Base", vparam(m, "BaseColor", names.DEF_BASE, 900), ""), ("Second", vparam(m, "SecondColor", names.DEF_SECOND, 1050), ""),
           ("Third", vparam(m, "ThirdColor", names.DEF_THIRD, 1200), ""),
           ("White", sparam(m, "WhiteMarks", names.DEF_WHITE, 1500), ""), ("Tick", sparam(m, "Ticking", names.DEF_TICK, 1600), ""),
           ("S", c, "RGB")]
    cu = custom(m, CARD_HLSL, ins, unreal.CustomMaterialOutputType.CMOT_FLOAT3, "CatFurCard", -400, 300)
    to(cu, "", MP.MP_BASE_COLOR); to(c, "A", MP.MP_OPACITY_MASK)
    to(sparam(m, "Roughness", 0.85, 1700), "", MP.MP_ROUGHNESS)
    to(sparam(m, "Specular", names.DEF_FUR_SPEC, 1800), "", MP.MP_SPECULAR)
    MEL.recompile_material(m); EAL.save_loaded_asset(m); return m


# eye (round 6): iris = EyeColor deepened towards the pupil (EyeColor ^ IRIS_DEEP inside, EyeColor in the outer iris; E.a = iris radius)
# times the iris brightness E.r; the pupil from the field in E.g at PupilOpen (names.PUPIL_*, 0 slit .. 1 nearly round); cat_look_tex
# builds the same in Blender
EYE_HLSL = """float3 inner = pow(max(Eye.rgb, 1e-4), %(deep)s);
float3 iris = lerp(inner, Eye.rgb, smoothstep(0.25, 0.9, E.a)) * E.r;
float pupil = saturate((Open + %(e0)s - %(e1)s * E.g) * %(sharp)s + 0.5);
return lerp(iris, float3(0.004, 0.004, 0.004), pupil);""" % dict(deep=names.IRIS_DEEP, e0=names.PUPIL_ENC[0], e1=names.PUPIL_ENC[1],
                                                                  sharp=names.PUPIL_SHARP)


def build_eye():
    m = new_material(names.MAT_EYE); opaque(m); skeletal(m)
    e = tparam(m, "Eye", tex("T_VP_CatEye"), 0, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    cu = custom(m, EYE_HLSL, [("E", e, "RGBA"), ("Eye", vparam(m, "EyeColor", names.DEF_EYE, 250), ""),
                              ("Open", sparam(m, "PupilOpen", names.DEF_PUPIL_OPEN, 350), "")],
                unreal.CustomMaterialOutputType.CMOT_FLOAT3, "CatEye", -400, 0)
    glint = expr(m, unreal.MaterialExpressionMultiply, -300, 250); glint.set_editor_property("const_b", names.DEF_EYE_GLINT)
    link(e, "B", glint, "A")
    to(cu, "", MP.MP_BASE_COLOR); to(glint, "", MP.MP_EMISSIVE_COLOR)
    to(sparam(m, "Roughness", names.DEF_EYE_ROUGH, 400), "", MP.MP_ROUGHNESS)
    to(sparam(m, "Specular", names.DEF_EYE_SPEC, 500), "", MP.MP_SPECULAR)
    MEL.recompile_material(m); EAL.save_loaded_asset(m); return m


def build_mouth():
    """Mouth cavity, gums, tongue, cheeks: the mesh's point colours (sRGB bytes; UE passes them on unconverted, so ^2.2
    to linear) times MouthTint; moist."""
    m = new_material(names.MAT_MOUTH); opaque(m); skeletal(m)
    vc = expr(m, unreal.MaterialExpressionVertexColor, -700, 0)
    pw = expr(m, unreal.MaterialExpressionPower, -500, 0); pw.set_editor_property("const_exponent", 2.2)
    link(vc, "", pw, "Base")
    mul = expr(m, unreal.MaterialExpressionMultiply, -300, 0)
    link(pw, "", mul, "A"); link(vparam(m, "MouthTint", names.DEF_MOUTH, 250), "", mul, "B")
    to(mul, "", MP.MP_BASE_COLOR)
    to(sparam(m, "Roughness", names.DEF_MOUTH_ROUGH, 400), "", MP.MP_ROUGHNESS)
    MEL.recompile_material(m); EAL.save_loaded_asset(m); return m


def build_teeth():
    m = new_material(names.MAT_TEETH); opaque(m); skeletal(m)
    to(vparam(m, "TeethColor", names.DEF_TEETH, 0), "", MP.MP_BASE_COLOR)
    to(sparam(m, "Roughness", names.DEF_TEETH_ROUGH, 250), "", MP.MP_ROUGHNESS)
    MEL.recompile_material(m); EAL.save_loaded_asset(m); return m


def build_instances():
    for parent, mi in names.MATERIALS:
        if EAL.does_asset_exist(mi) and not EAL.delete_asset(mi): fail("cannot delete " + mi)    # a stale override would stay in effect
        d, n = mi.rsplit("/", 1)
        inst = AT.create_asset(n, d, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(inst, unreal.load_asset(parent)); EAL.save_loaded_asset(inst)


def delete_mesh():
    for p in (names.MESH, names.PHYSICS, names.SKELETON):
        if EAL.does_asset_exist(p) and not EAL.delete_asset(p): fail("cannot delete " + p)


def import_mesh():
    ui = unreal.FbxImportUI()
    for k, v in (("import_mesh", True), ("import_as_skeletal", True), ("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH),
                 ("skeleton", None), ("create_physics_asset", True), ("import_animations", False), ("import_materials", False),
                 ("import_textures", False), ("automated_import_should_detect_type", False)):
        ui.set_editor_property(k, v)
    sd = ui.skeletal_mesh_import_data
    sd.set_editor_property("import_morph_targets", False)
    sd.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    d, n = names.MESH.rsplit("/", 1)
    AT.import_asset_tasks([task(os.path.join(OUT, "cat.fbx"), d, n, ui)])
    mesh = unreal.load_asset(names.MESH)
    if not mesh: fail("mesh not imported")
    if not EAL.does_asset_exist(names.SKELETON): fail("skeleton missing: " + names.SKELETON)
    if not EAL.does_asset_exist(names.PHYSICS): fail("physics asset missing: " + names.PHYSICS)
    mats = mesh.get_editor_property("materials"); seen = []
    for i in range(len(mats)):
        sm = mats[i]                       # a copy of the struct: written back below
        slot = str(sm.get_editor_property("material_slot_name")); seen.append(slot)
        if slot not in names.SLOTS: fail("unexpected slot " + slot)
        sm.set_editor_property("material_interface", unreal.load_asset(names.SLOTS[slot])); mats[i] = sm
    mesh.set_editor_property("materials", mats)
    if sorted(seen) != sorted(names.SLOTS): fail("slots %s" % seen)
    EAL.save_loaded_asset(mesh); EAL.save_loaded_asset(unreal.load_asset(names.SKELETON)); EAL.save_loaded_asset(unreal.load_asset(names.PHYSICS))
    b = mesh.get_bounds(); e = b.box_extent
    unreal.log_warning("EDTEST cat bounds %.1f %.1f %.1f cm" % (e.x * 2, e.y * 2, e.z * 2))
    return mesh


def read_back(mesh):
    """Skeleton bones, physics bodies, slot mapping, MI parameter defaults: all read from the saved assets."""
    mesh = unreal.load_asset(names.MESH)       # reload what was saved
    if not mesh: fail("mesh reload")
    mc = unreal.load_asset(names.MAT_CARD)
    if mc.get_editor_property("blend_mode") != unreal.BlendMode.BLEND_MASKED or not mc.get_editor_property("two_sided") \
            or abs(mc.get_editor_property("opacity_mask_clip_value") - 0.33) > 1e-4: fail("MAT_CARD blend/two_sided/clip")
    sk = unreal.load_asset(names.SKELETON)
    if mesh.get_editor_property("skeleton") != sk: fail("mesh does not use " + names.SKELETON)
    comp = unreal.SkeletalMeshComponent(); comp.set_skeletal_mesh(mesh)   # reference skeleton through an unregistered component
    bones = [str(comp.get_bone_name(i)) for i in range(comp.get_num_bones())]
    unreal.log_warning("EDTEST bones %d: %s" % (len(bones), " ".join(bones)))
    if len(bones) != BONES or bones[0] != "root" or bones.count("root") != 1: fail("skeleton bones %d, first %s" % (len(bones), bones[:2]))
    if str(comp.get_parent_bone(bones[1])) != "root": fail("second bone's parent %s" % comp.get_parent_bone(bones[1]))
    pa = unreal.load_asset(names.PHYSICS)
    if mesh.get_editor_property("physics_asset") != pa: fail("mesh does not use " + names.PHYSICS)
    # SkeletalBodySetups is not exposed to Python in 4.27; the asset registry tags of UPhysicsAsset carry the counts
    tags = unreal.AssetRegistryHelpers.get_asset_registry().get_asset_by_object_path(pa.get_path_name())
    bodies, cons = int(tags.get_tag_value("Bodies") or 0), int(tags.get_tag_value("Constraints") or 0)
    unreal.log_warning("EDTEST physics asset: %d bodies, %d constraints" % (bodies, cons))
    if bodies < 1: fail("physics asset without bodies")
    slots = {}
    for s in mesh.get_editor_property("materials"):
        mi_ = s.get_editor_property("material_interface")
        if mi_ is None: fail("slot %s has no material_interface" % s.get_editor_property("material_slot_name"))
        slots[str(s.get_editor_property("material_slot_name"))] = mi_.get_path_name().split(".")[0]
    unreal.log_warning("EDTEST slots %s" % sorted(slots.items()))
    if slots != names.SLOTS: fail("slot mapping %s" % slots)
    fur = unreal.load_asset(names.MI_FUR)
    for k, v in (("BaseColor", names.DEF_BASE), ("SecondColor", names.DEF_SECOND), ("ThirdColor", names.DEF_THIRD), ("SkinColor", names.DEF_SKIN),
                 ("PatternWeights", names.DEF_PATTERN), ("Undertone", names.DEF_UNDERTONE)):
        c = MEL.get_material_instance_vector_parameter_value(fur, k)
        if max(abs(c.r - v[0]), abs(c.g - v[1]), abs(c.b - v[2]), abs(c.a - v[3])) > 1e-4: fail("MI_VP_CatFur %s = %s" % (k, c))
    for k, v in (("WhiteMarks", names.DEF_WHITE), ("Ticking", names.DEF_TICK), ("Roughness", names.DEF_FUR_ROUGH),
                 ("FurCavity", names.DEF_FUR_CAVITY), ("FurSheen", names.DEF_FUR_SHEEN), ("SkinRoughness", names.DEF_SKIN_ROUGH),
                 ("Specular", names.DEF_FUR_SPEC)):
        if abs(MEL.get_material_instance_scalar_parameter_value(fur, k) - v) > 1e-4: fail("MI_VP_CatFur %s" % k)
    for k in ("MaskA", "MaskB", "FurNormal"):
        if not MEL.get_material_instance_texture_parameter_value(fur, k): fail("MI_VP_CatFur texture " + k)
    eye = unreal.load_asset(names.MI_EYE); c = MEL.get_material_instance_vector_parameter_value(eye, "EyeColor")
    if abs(c.r - names.DEF_EYE[0]) > 1e-4: fail("MI_VP_CatEye EyeColor %s" % c)
    po = MEL.get_material_instance_scalar_parameter_value(eye, "PupilOpen")
    if abs(po - names.DEF_PUPIL_OPEN) > 1e-4: fail("MI_VP_CatEye PupilOpen %s" % po)
    card = unreal.load_asset(names.MI_CARD)
    for k in ("Card", "MaskA", "MaskB"):
        if not MEL.get_material_instance_texture_parameter_value(card, k): fail("MI_VP_CatFurCard texture " + k)
    c = MEL.get_material_instance_vector_parameter_value(card, "BaseColor")
    if abs(c.r - names.DEF_BASE[0]) > 1e-4: fail("MI_VP_CatFurCard BaseColor %s" % c)
    mouth = unreal.load_asset(names.MI_MOUTH); c = MEL.get_material_instance_vector_parameter_value(mouth, "MouthTint")
    if abs(c.r - names.DEF_MOUTH[0]) > 1e-4: fail("MI_VP_CatMouth MouthTint %s" % c)
    teeth = unreal.load_asset(names.MI_TEETH); c = MEL.get_material_instance_vector_parameter_value(teeth, "TeethColor")
    if abs(c.r - names.DEF_TEETH[0]) > 1e-4: fail("MI_VP_CatTeeth TeethColor %s" % c)
    order = [str(s.get_editor_property("material_slot_name")) for s in mesh.get_editor_property("materials")]
    if order != list(names.SLOTS): fail("slot order %s (want %s)" % (order, list(names.SLOTS)))
    names_ = {p: [str(x) for x in MEL.get_scalar_parameter_names(unreal.load_asset(p))] + [str(x) for x in MEL.get_vector_parameter_names(unreal.load_asset(p))]
              for p, _ in names.MATERIALS}
    unreal.log_warning("EDTEST parameters %s" % names_)
    unreal.log_warning("EDTEST read-back ok: %d bones, %d bodies, slots mapped, MI defaults" % (len(bones), bodies))


delete_mesh()
import_textures(); build_fur(); build_card(); build_eye(); build_mouth(); build_teeth(); build_instances()
read_back(import_mesh())
unreal.log_warning("EDTEST PASS")
