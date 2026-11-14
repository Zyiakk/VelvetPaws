"""apply(obj) for TKAInfo look.py --tex: shows the cat with the baked masks, mixed exactly like the UE material
M_VP_CatFur (plan, Task 5):
    p = saturate(dot(A.rgb, W.rgb)); c = lerp(Base, Second, p); c = lerp(c, Third, A.a * W.a)
    c *= 1 - Tick * B.b * 0.5; c = lerp(c, 1, B.r * White); c = lerp(c, Skin, B.g)
A = mask_a, B = mask_b, W = pattern weights. The colours default to the stage 1 defaults (names.DEF_*: tabby).
The environment variable VP_LOOK picks another coat to look at: tabby (default), calico (black base, orange third
colour from the tricolour patches, white markings), spotted, brindle, tabwhite (tabby with white markings), lightgrey and
cream (solid), and every AltUI preset as preset:<Row> (e.g. preset:BlueGrey)."""
import os, sys
import bpy

W = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(W, "scripts")); from velvetpaws import names
TEX = os.environ.get("VP_TEX") or os.path.join(names.build_dir(W), "tex")     # VP_TEX: another bake (review renders)
TICK = names.DEF_TICK
_D = dict(pattern=names.DEF_PATTERN, white=names.DEF_WHITE, base=names.DEF_BASE, second=names.DEF_SECOND,
          third=names.DEF_THIRD)
VARIANTS = {
    "tabby": _D,
    "calico": dict(_D, pattern=(0.0, 0.0, 0.0, 1.0), white=1.0, base=(0.012, 0.011, 0.010, 1.0),
                   third=(0.55, 0.20, 0.05, 1.0)),
    "spotted": dict(_D, pattern=(0.0, 0.0, 1.0, 0.0)),
    "brindle": dict(_D, pattern=(0.0, 1.0, 0.0, 0.0)),
    "tabwhite": dict(_D, white=1.0),
    "lightgrey": dict(_D, pattern=(0.0, 0.0, 0.0, 0.0), base=(0.30, 0.30, 0.30, 1.0), second=(0.30, 0.30, 0.30, 1.0)),
    "cream": dict(_D, pattern=(0.0, 0.0, 0.0, 0.0), base=(0.62, 0.48, 0.32, 1.0), second=(0.62, 0.48, 0.32, 1.0)),
}
# every AltUI coat preset (scripts/velvetpaws/ui.py PRESETS) as "preset:<Row>", e.g. VP_LOOK=preset:BlueGrey
from velvetpaws import ui as _ui, brain as _brain
for _row, _cap, _v in _ui.PRESETS:
    _w, _white = _brain.PATTERNS[_v["Pattern"]]
    VARIANTS["preset:" + _row] = dict(_D, pattern=_w, white=_white, base=_v["BaseColor"], second=_v["SecondColor"])
COAT = VARIANTS[os.environ.get("VP_LOOK", "tabby")]


def _img(nt, name):
    n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(os.path.join(TEX, name), check_existing=True)
    n.image.colorspace_settings.name = "Non-Color"
    return n


def _sock(node, name, kind, out=False):
    return next(s for s in (node.outputs if out else node.inputs) if s.name == name and s.type == kind and s.enabled)


def _mix(nt, fac, a, b, blend="MIX"):
    """Colour mix (lerp a -> b by fac, or another blend type); fac, a, b are sockets or constants."""
    m = nt.nodes.new("ShaderNodeMix"); m.data_type = "RGBA"; m.blend_type = blend
    for name, v, kind in (("Factor", fac, "VALUE"), ("A", a, "RGBA"), ("B", b, "RGBA")):
        s = _sock(m, name, kind)
        if isinstance(v, (tuple, float, int)): s.default_value = (v, v, v, 1.0) if kind == "RGBA" and not isinstance(v, tuple) else v
        else: nt.links.new(v, s)
    return _sock(m, "Result", "RGBA", out=True)


def _math(nt, op, a, b, clamp=False):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = op; m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if isinstance(v, (float, int)): m.inputs[i].default_value = v
        else: nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def _coat(nt, a, b, skin=True):
    """The coat formula on the mask images a, b; returns (colour socket, separated mask_b node)."""
    sa = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(a.outputs["Color"], sa.inputs[0])
    sb = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(b.outputs["Color"], sb.inputs[0])
    w = COAT["pattern"]
    p = 0.0                                                            # saturate(dot(A.rgb, W.rgb))
    for ch, k in zip(("Red", "Green", "Blue"), w[:3]):
        p = _math(nt, "ADD", p, _math(nt, "MULTIPLY", sa.outputs[ch], float(k)))
    p = _math(nt, "ADD", p, 0.0, clamp=True)
    c = _mix(nt, p, COAT["base"], COAT["second"])
    c = _mix(nt, _math(nt, "MULTIPLY", a.outputs["Alpha"], float(w[3])), c, COAT["third"])
    tick = _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", sb.outputs["Blue"], TICK * 0.5))
    c = _mix(nt, 1.0, c, tick, blend="MULTIPLY")                       # c *= 1 - Tick * B.b * 0.5
    c = _mix(nt, _math(nt, "MULTIPLY", sb.outputs["Red"], float(COAT["white"])), c, (1.0, 1.0, 1.0, 1.0))
    if skin: c = _mix(nt, sb.outputs["Green"], c, names.DEF_SKIN)
    return c, sb


def _fur(nt, bsdf):
    a, b, n = _img(nt, "mask_a.png"), _img(nt, "mask_b.png"), _img(nt, "fur_n.png")
    c, sb = _coat(nt, a, b)
    # after the formula (M_VP_CatFur CatFurSheen): roots darker by fur depth (B.a), warmer only on agouti coats (names.root_tint),
    # Fresnel sheen (exponent 3)
    nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    depth = b.outputs["Alpha"]
    root = names.root_tint(COAT["pattern"]) + (1.0,)
    c = _mix(nt, 1.0, c, _mix(nt, depth, root, (1.0, 1.0, 1.0, 1.0)), blend="MULTIPLY")
    geo = nt.nodes.new("ShaderNodeNewGeometry"); cam = nt.nodes.new("ShaderNodeVectorMath"); cam.operation = "DOT_PRODUCT"
    nt.links.new(nm.outputs[0], cam.inputs[0]); nt.links.new(geo.outputs["Incoming"], cam.inputs[1])
    f = _math(nt, "POWER", _math(nt, "SUBTRACT", 1.0, _math(nt, "MAXIMUM", cam.outputs["Value"], 0.0)), 3.0)
    s = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", f, names.DEF_FUR_SHEEN), _math(nt, "SUBTRACT", 1.0, sb.outputs["Green"]))
    c = _mix(nt, 1.0, c, _mix(nt, s, (1.0, 1.0, 1.0, 1.0), (2.0, 2.0, 2.0, 1.0)), blend="MULTIPLY")   # o * (1 + s)
    c = _mix(nt, 1.0, c, _mix(nt, s, (0.0, 0.0, 0.0, 1.0), (0.02, 0.02, 0.02, 1.0)), blend="ADD")      # + s * 0.02
    nt.links.new(c, bsdf.inputs["Base Color"])
    r = _math(nt, "ADD", names.DEF_FUR_ROUGH, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, depth), 0.08))
    mr = nt.nodes.new("ShaderNodeMix"); mr.data_type = "FLOAT"
    nt.links.new(sb.outputs["Green"], _sock(mr, "Factor", "VALUE")); nt.links.new(r, _sock(mr, "A", "VALUE"))
    _sock(mr, "B", "VALUE").default_value = names.DEF_SKIN_ROUGH
    nt.links.new(_sock(mr, "Result", "VALUE", out=True), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = names.DEF_FUR_SPEC


def _card(nt, bsdf):
    """Fur cards as M_VP_CatFurCard: the coat formula (no skin) on the masks at the card's FurUV (the fur UV of its base),
    times the strand shade of card.png (x 1.25); alpha = strand coverage."""
    c = _img(nt, "card.png"); nt.links.new(c.outputs["Alpha"], bsdf.inputs["Alpha"])
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "FurUV"
    a, b = _img(nt, "mask_a.png"), _img(nt, "mask_b.png")
    for im in (a, b): nt.links.new(uvn.outputs["UV"], im.inputs["Vector"])
    coat, _ = _coat(nt, a, b, skin=False)
    shade = _mix(nt, 1.0, c.outputs["Color"], (1.25, 1.25, 1.25, 1.0), blend="MULTIPLY")
    nt.links.new(_mix(nt, 1.0, coat, shade, blend="MULTIPLY"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85; bsdf.inputs["Specular IOR Level"].default_value = names.DEF_FUR_SPEC


PUPIL = float(os.environ.get("VP_PUPIL", names.DEF_PUPIL_OPEN))     # VP_PUPIL: another PupilOpen to look at (0 slit .. 1 round)


def _eye(nt, bsdf):
    """M_VP_CatEye (import_cat EYE_HLSL): iris = lerp(EyeColor ^ IRIS_DEEP, EyeColor, smoothstep(0.25, 0.9, E.a)) * E.r; pupil from
    the field in E.g at PupilOpen; the painted glint as emission."""
    e = _img(nt, "eye.png"); s = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(e.outputs["Color"], s.inputs[0])
    deep = tuple(c ** names.IRIS_DEEP for c in names.DEF_EYE[:3]) + (1.0,)
    sm = nt.nodes.new("ShaderNodeMapRange"); sm.interpolation_type = "SMOOTHSTEP"
    sm.inputs["From Min"].default_value = 0.25; sm.inputs["From Max"].default_value = 0.9
    nt.links.new(e.outputs["Alpha"], sm.inputs["Value"])
    iris = _mix(nt, sm.outputs["Result"], deep, names.DEF_EYE)
    iris = _mix(nt, 1.0, iris, _mix(nt, s.outputs["Red"], (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)), blend="MULTIPLY")
    e0, e1 = names.PUPIL_ENC
    pup = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", PUPIL + e0, _math(nt, "MULTIPLY", s.outputs["Green"], e1)),
                                 names.PUPIL_SHARP), 0.5, clamp=True)
    col = _mix(nt, pup, iris, (0.004, 0.004, 0.004, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    em = _mix(nt, _math(nt, "MULTIPLY", s.outputs["Blue"], names.DEF_EYE_GLINT), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0))
    nt.links.new(em, bsdf.inputs["Emission Color"]); bsdf.inputs["Emission Strength"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = names.DEF_EYE_ROUGH
    bsdf.inputs["Specular IOR Level"].default_value = names.DEF_EYE_SPEC


def _mouth(nt, bsdf, col="Col"):
    """Mouth cavity, gums, tongue: the point colours `col` (sRGB in the mesh, linear here, as M_VP_CatMouth reads them
    with a 2.2 power) times MouthTint, moist."""
    a = nt.nodes.new("ShaderNodeVertexColor"); a.layer_name = col
    nt.links.new(_mix(nt, 1.0, a.outputs["Color"], names.DEF_MOUTH, blend="MULTIPLY"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = names.DEF_MOUTH_ROUGH


def _teeth(nt, bsdf):
    bsdf.inputs["Base Color"].default_value = names.DEF_TEETH; bsdf.inputs["Roughness"].default_value = names.DEF_TEETH_ROUGH


SLOTS = {"Fur": _fur, "FurCard": _card, "Eye": _eye, "Mouth": _mouth, "Teeth": _teeth}


def apply(obj):
    ca = obj.data.color_attributes
    col = (ca.active_color or ca[0]).name if ca else "Col"     # the mesh's colour attribute (cat.blend: "Col"; glTF renames it)
    # look.py's lights are set for Jodi-sized scenes; one stop down keeps the fur from reading white
    bpy.context.scene.view_settings.exposure = -1.0
    for slot in obj.material_slots:
        name = slot.material.name if slot.material else slot.name
        kind = next((k for k in sorted(SLOTS, key=len, reverse=True) if name.startswith(k)), None)
        if kind is None: raise ValueError("cat_look_tex: unknown material slot %r (expected %s)" % (name, list(SLOTS)))
        mat = bpy.data.materials.new("look_" + name); mat.use_nodes = True; nt = mat.node_tree
        (_mouth(nt, nt.nodes["Principled BSDF"], col) if kind == "Mouth" else SLOTS[kind](nt, nt.nodes["Principled BSDF"]))
        slot.material = mat
