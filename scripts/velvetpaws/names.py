"""Names shared by the VelvetPaws build: kit paths, assets, build folders."""
import os

MOD = "VelvetPaws"
ROOT = "/Game/Mod/" + MOD
MESH = ROOT + "/SK_VP_Cat"
SKELETON = MESH + "_Skeleton"          # created by the FBX import (scripts/import_cat.py)
PHYSICS = MESH + "_PhysicsAsset"
ANIM = ROOT + "/Anim"
BP = ROOT + "/BP_VP_Cat"
BP_CLASS = BP + ".BP_VP_Cat_C"
ABP = ROOT + "/ABP_VP_Cat"
ABP_CLASS = ABP + ".ABP_VP_Cat_C"
BLENDSPACE = ANIM + "/BS_VP_Locomotion"
SLOT = "DefaultSlot"                     # BPGen animplayer adds it to the cat's skeleton (group DefaultGroup)
VAR_SPEED, VAR_OVERLAY = "Speed", "OverlayAlpha"
MATS = ROOT + "/Materials"
MAT_FUR, MAT_CARD, MAT_EYE = MATS + "/M_VP_CatFur", MATS + "/M_VP_CatFurCard", MATS + "/M_VP_CatEye"
MI_FUR, MI_CARD, MI_EYE = MATS + "/MI_VP_CatFur", MATS + "/MI_VP_CatFurCard", MATS + "/MI_VP_CatEye"
MAT_MOUTH, MAT_TEETH = MATS + "/M_VP_CatMouth", MATS + "/M_VP_CatTeeth"
MI_MOUTH, MI_TEETH = MATS + "/MI_VP_CatMouth", MATS + "/MI_VP_CatTeeth"
TEX = ROOT + "/Textures"
# asset name -> PNG written by tools/blender/cat_bake.py; kind decides compression (color / normal / mask)
TEXTURES = {"T_VP_CatMaskA": ("mask_a.png", "mask"), "T_VP_CatMaskB": ("mask_b.png", "mask"),
            "T_VP_CatFur_N": ("fur_n.png", "normal"), "T_VP_CatCard": ("card.png", "color"), "T_VP_CatEye": ("eye.png", "mask")}
# FBX material slot -> material instance
SLOTS = {"Fur": MI_FUR, "Eye": MI_EYE, "FurCard": MI_CARD, "Mouth": MI_MOUTH, "Teeth": MI_TEETH}   # FBX slot order
# master material -> instance, in slot order (import_cat builds them, verify_cooked expects them in the pak)
MATERIALS = [(MAT_FUR, MI_FUR), (MAT_EYE, MI_EYE), (MAT_CARD, MI_CARD), (MAT_MOUTH, MI_MOUTH), (MAT_TEETH, MI_TEETH)]
# defaults of stage 1: tabby, near-black lines on a mid grey-brown ground, amber eyes (linear colours)
# look pass: a grey mackerel tabby: a cool grey ground (the warm agouti undertone comes from DEF_UNDERTONE between the strands),
# near-black stripes
DEF_BASE = (0.108, 0.101, 0.094, 1.0); DEF_SECOND = (0.0065, 0.006, 0.0055, 1.0); DEF_THIRD = (0.55, 0.20, 0.05, 1.0)
DEF_SKIN = (0.55, 0.28, 0.28, 1.0); DEF_EYE = (0.75, 0.42, 0.06, 1.0)
# mouth: tint on the mesh's point colours (cavity, gums, tongue); teeth: ivory (linear colours)
DEF_MOUTH = (1.0, 1.0, 1.0, 1.0); DEF_MOUTH_ROUGH = 0.72
DEF_TEETH = (0.80, 0.74, 0.60, 1.0); DEF_TEETH_ROUGH = 0.28
DEF_EYE_ROUGH, DEF_EYE_SPEC, DEF_EYE_GLINT = 0.14, 0.5, 0.3   # wet cornea, not a mirror; painted glint as emissive
# pupil (round 6): M_VP_CatEye scalar PupilOpen, 0 = slit .. 1 = nearly round, default a moderate vertical ellipse; the Blueprint
# may widen it (dark places, play, excitement). Shape family on the eye's front (unit sphere projected, cat_bake.paint_eye): the
# ellipse |x| <= w(o) * sqrt(1 - (y / PUPIL_H)^2), w(o) = lerp(PUPIL_W[0], PUPIL_W[1], o). eye.png G stores, per texel, the
# opening o at which it turns pupil, encoded g = (o + PUPIL_ENC[0]) / PUPIL_ENC[1]; the material: pupil = saturate((PupilOpen +
# PUPIL_ENC[0] - PUPIL_ENC[1] * g) * PUPIL_SHARP + 0.5).
DEF_PUPIL_OPEN = 0.35
PUPIL_RANGE = (0.0, 1.0)
PUPIL_W, PUPIL_H = (0.05, 0.40), 0.47
PUPIL_ENC = (0.25, 1.5)
PUPIL_SHARP = 16.0
# iris colour: towards the pupil the eye colour deepens (EyeColor ^ IRIS_DEEP), out to the limbus it is EyeColor (eye.png A = radius)
IRIS_DEEP = 2.0
DEF_PATTERN = (1.0, 0.0, 0.0, 0.0)   # weights of MaskA channels: tabby, brindle, spots, tricolour patches
DEF_WHITE = 0.0                      # weight of the white markings (MaskB.R)
DEF_TICK = 0.35                      # ticking strength: darkens by up to Tick * MaskB.B * 0.5 (agouti grain)
# fur look, applied after the colour formula (M_VP_CatFur): the roots between the strands darker (MaskB.A fur depth),
# a soft brightening towards grazing angles (fur sheen, Fresnel), rough and weakly specular fur, the skin (nose) smoother
DEF_UNDERTONE = (1.0, 0.70, 0.45, 1.0)     # tint of the roots between the strands (warm brown agouti bands under grey tips)
DEF_FUR_CAVITY = 0.42; DEF_FUR_SHEEN = 0.85; DEF_FUR_ROUGH = 0.86; DEF_SKIN_ROUGH = 0.55; DEF_FUR_SPEC = 0.30


def root_tint(w, u=DEF_UNDERTONE, cav=DEF_FUR_CAVITY):
    """Colour factor at the deepest roots (M_VP_CatFur CatFurSheen, final review I1): the warm Undertone only as far as the coat
    is agouti (tabby, brindle, spots: PatternWeights r + g + b); a solid, tricolour or white-marked coat keeps its own hue
    (a blue grey or cream would otherwise turn brownish). HLSL: (1 - Cav) * lerp(1, U.rgb, saturate(W.r + W.g + W.b))."""
    a = max(0.0, min(1.0, w[0] + w[1] + w[2]))
    return tuple((1.0 - cav) * (1.0 + (c - 1.0) * a) for c in u[:3])


def pupil_cover(g, open_):
    """Pupil coverage (0..1) at PupilOpen = open_ for an eye.png G value g (0..1): the formula of M_VP_CatEye and cat_look_tex."""
    return min(1.0, max(0.0, (open_ + PUPIL_ENC[0] - PUPIL_ENC[1] * g) * PUPIL_SHARP + 0.5))


def build_dir(w):
    return os.path.join(w, "build", "velvetpaws")


def seq(name): return ANIM + "/VP_Cat_" + name


def montage(name): return ANIM + "/AM_VP_" + name


def obj(path): return "%s.%s" % (path, path.rsplit("/", 1)[1])


def anim_dir(w): return os.path.join(build_dir(w), "anim")


def pak_assets(seqs, montages):
    """Every asset the pak holds, relative to ROOT without extension (build.sh checks the pak list, verify_cooked.py the cooked pak).
    seqs: cat_seqs.ORDER, montages: the montage names (cat_seqs.MONTAGES)."""
    rel = lambda p: p[len(ROOT) + 1:]
    return ([rel(p) for p in (MESH, SKELETON, PHYSICS, BP, ABP, BLENDSPACE, SG, S_WALK, S_SPOT, DT_WALK, DT_SPOT)] + ["TKA_BlueprintLoader", "TKA_Mod_Table"]
            + [rel(seq(n)) for n in seqs] + [rel(montage(m)) for m in montages]
            + [rel(p) for pair in MATERIALS for p in pair] + [rel(TEX + "/" + t) for t in TEXTURES] + _sound_assets())


def _sound_assets():
    from velvetpaws import sounds, ui
    return sounds.pak_assets() + ui.pak_assets()


DATA = ROOT + "/Data"
S_WALK, S_SPOT = DATA + "/S_VP_WalkPoint", DATA + "/S_VP_Spot"
DT_WALK, DT_SPOT = DATA + "/DT_VP_OfficeWalk", DATA + "/DT_VP_OfficeSpots"
SG = ROOT + "/SG_VP_Cat"
SG_CLASS = SG + ".SG_VP_Cat_C"
SAVE_SLOT = "VelvetPaws"
OFFICE_MAP_REL = os.path.join("assets", "office", "office_map.json")
SOUND = ROOT + "/Sound"
SOUND_CLASS_SFX = "/Game/Project/Sounds/SoundClass_SFX"   # the game's: its options menu sets the SFX volume through this class; never packed
