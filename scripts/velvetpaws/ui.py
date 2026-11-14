"""The cat's page in AltUI's Mods tab (plan Etappe 5; AltUI's MOD_UI.md): one table for AltUI_Entries / AltUI_Fields /
AltUI_Actions / AltUI_Presets (gen_velvetpaws.py) and for the graphs of BPI_AltUIMod in BP_VP_Cat (assets/gen/vp_bp_ui.py). The key
of every value field is its variable in brain.SETTINGS. Plain Python 3.7 (the editor test reads it), no NumPy."""
from velvetpaws import names, brain as B

ENTRY = "VelvetPaws"; CAPTION = "VelvetPaws"
# Row names of all four tables carry this prefix (the Key column stays the setting's name, so saves and AltUI's remembered tabs keep
# working). Cause (round 6): the cooked tables give every Text cell the localization id namespace = table name ("AltUI_Fields" for
# every mod) and key = "<row>_<column>"; UE keeps one display string per id, so equal row names in two mods' tables share one label -
# a "Size" row of another mod's AltUI page (its label "Moon size") replaced the cat's "Size" label. Unique row names avoid that.
ROW = "VP_"
MODES = ["Follow", "Wait", "Roam"]                                         # brain.MODE_* order
COATS = ["Solid", "Tabby", "Brindle", "Spotted", "Tricolour", "Markings"]  # brain.PATTERNS order
INFO = "Status"; BUTTON_RECALL = "Recall"
# (key, type, label, order, extra columns) - lead (on every tab) first, then the tabs
FIELDS = [
    (INFO, "Info", "Now", 1, {}),
    ("Active", "Toggle", "Cat active", 2, {}),
    ("TabBehaviour", "Tab", "Behaviour", 10, {}),
    ("Mode", "Choice", "Mode", 11, {"Options": MODES}),
    ("TakeAlong", "Toggle", "Take along on missions", 12, {}),
    ("StayMin", "Slider", "Stay on a spot at least (minutes)", 15, {"Min": B.STAY_RANGE[0], "Max": B.STAY_RANGE[1], "Step": 0.5}),
    ("StayMax", "Slider", "Stay on a spot at most (minutes)", 16, {"Min": B.STAY_RANGE[0], "Max": B.STAY_RANGE[1], "Step": 0.5}),
    (BUTTON_RECALL, "Button", "Call her", 13, {}),
    ("RecallKey", "Key", "Key: call her", 14, {}),
    ("TabLook", "Tab", "Look", 20, {}),
    ("Pattern", "Choice", "Coat", 21, {"Options": COATS}),
    ("BaseColor", "Color", "Base colour", 22, {}),
    ("SecondColor", "Color", "Second colour", 23, {}),
    ("EyeColor", "Color", "Eye colour", 24, {}),
    ("Size", "Slider", "Scale", 25, {"Min": B.SIZE_MIN, "Max": B.SIZE_MAX, "Step": 1.0}),
    ("CatName", "Text", "Name", 26, {}),
    ("TabSound", "Tab", "Sounds", 30, {}),
    ("Meow", "Toggle", "Meow", 31, {}),
    ("MeowRate", "Slider", "How often", 32, {"Min": 0.0, "Max": 100.0, "Step": 5.0}),
    ("Purr", "Toggle", "Purr", 33, {}),
    ("Volume", "Slider", "Volume", 34, {"Min": 0.0, "Max": 100.0, "Step": 5.0}),
]
# value fields: key -> (kind, scale on the page, lowest, highest stored value)
VALUES = {"Active": ("bool", 1.0, 0.0, 1.0), "Mode": ("int", 1.0, 0.0, float(len(MODES) - 1)), "TakeAlong": ("bool", 1.0, 0.0, 1.0),
          "Pattern": ("int", 1.0, 0.0, float(len(COATS) - 1)), "Size": ("float", 1.0, B.SIZE_MIN, B.SIZE_MAX),
          "Meow": ("bool", 1.0, 0.0, 1.0), "MeowRate": ("float", 100.0, 0.0, 1.0), "Purr": ("bool", 1.0, 0.0, 1.0),
          "Volume": ("float", 100.0, 0.0, 1.0), "StayMin": ("float", 1.0) + B.STAY_RANGE, "StayMax": ("float", 1.0) + B.STAY_RANGE}
COLORS = ["BaseColor", "SecondColor", "EyeColor"]; TEXTS = ["CatName"]; KEYS = ["RecallKey"]
ACTIONS = [("ModeFollow", "Cat: follow", B.MODE_FOLLOW), ("ModeWait", "Cat: wait", B.MODE_WAIT), ("ModeRoam", "Cat: roam", B.MODE_ROAM)]
TABLES = ["AltUI_Entries", "AltUI_Fields", "AltUI_Actions", "AltUI_Presets"]
# material parameters Apply Look sets: (slot of names.SLOTS, parameter, source: a setting or "@pattern" / "@white"). The coat goes to
# the fur and the fur cards alike (M_VP_CatFurCard has the fur's parameter names); the kit test demands every one on its slot.
COAT = [("BaseColor", "BaseColor"), ("SecondColor", "SecondColor"), ("PatternWeights", "@pattern"), ("WhiteMarks", "@white")]
LOOK = [(slot, p, src) for slot in ("Fur", "FurCard") for p, src in COAT] + [("Eye", "EyeColor", "EyeColor")]
MID = {"Fur": "UiFur", "FurCard": "UiCard", "Eye": "UiEye"}                # slot -> BP variable of its dynamic instance
_BLACK = (0.010, 0.009, 0.008, 1.0); _AMBER = names.DEF_EYE
PRESETS = [("GreyTabby", "Grey tabby", {"Pattern": 1, "BaseColor": names.DEF_BASE, "SecondColor": names.DEF_SECOND, "EyeColor": _AMBER}),
           ("Black", "Black", {"Pattern": 0, "BaseColor": _BLACK, "SecondColor": _BLACK, "EyeColor": (0.45, 0.50, 0.05, 1.0)}),
           ("RedTabby", "Red tabby", {"Pattern": 1, "BaseColor": (0.42, 0.13, 0.03, 1.0), "SecondColor": (0.16, 0.035, 0.008, 1.0), "EyeColor": _AMBER}),
           ("Calico", "Calico", {"Pattern": 4, "BaseColor": _BLACK, "SecondColor": _BLACK, "EyeColor": _AMBER}),
           ("Tuxedo", "Tuxedo", {"Pattern": 5, "BaseColor": _BLACK, "SecondColor": _BLACK, "EyeColor": (0.30, 0.55, 0.15, 1.0)}),
           ("BlueGrey", "Blue grey", {"Pattern": 0, "BaseColor": (0.11, 0.115, 0.125, 1.0), "SecondColor": (0.05, 0.05, 0.055, 1.0), "EyeColor": (0.75, 0.50, 0.06, 1.0)})]
# status line (Info field)
NO_NAME = "The cat"; MODE_WORDS = ["follows Jodi", "waits", "roams"]; POSTURE_WORDS = ["standing", "sitting", "lying down", "asleep"]
DOING = {"alarm": "frightened", "move": "on her way", "jump": "jumping", "rub": "rubbing against Jodi's legs"}; PURRING = " (purring)"
OFF = "switched off"; HOME = "stays at home (take along is off)"; COMING = "on her way here"


def default(key):
    t, d = next((t, d) for n, t, d in B.SETTINGS if n == key)
    if t == "bool": return d == "true"
    if t == "int": return int(d)
    if t == "float": return float(d)
    return d


def to_ui(key, v):
    kind, scale, _, _ = VALUES[key]
    return (1.0 if v else 0.0) if kind == "bool" else float(v) * scale


def from_ui(key, f):
    kind, scale, lo, hi = VALUES[key]
    if kind == "bool": return f > 0.5
    if kind == "int": return int(max(lo, min(hi, int(round(f)))))
    return max(lo, min(hi, f / scale))


def hex_srgb(c):
    """Linear colour -> "#RRGGBB" in sRGB, as AltUI's Color To Hex (its presets read this back with Hex To Color)."""
    def ch(v):
        v = max(0.0, min(1.0, v)); s = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        return int(round(s * 255))
    return "#%02X%02X%02X" % tuple(ch(v) for v in c[:3])


DBG_WORDS = ["-", "none in reach", "walking to take-off", "stuck on the way", "turning", "take-off", "in the air", "not airborne",
             "too long in the air", "landed off the spot", "on the spot", "jumping down", "closed door on the way", "walking in"]   # index = brain.DBG_*
DBG_DEFAULT = (B.DBG_NONE, -1, 0, 0, 0, 0, 0)     # class defaults: code, SpotIdx, checked spots, spots, routine picks, spot tries, jumps


def spot_debug(code, idx, ok, n, picks, tries, jumps):
    """Suffix of the status line while brain.DEBUG_SPOTS: last step of the spot chain, spot index, checked/all office spots,
    routine picks, spot attempts (Go To Spot), jumps launched."""
    return " | spot: %s #%d ok%d/%d r%d t%d j%d" % (DBG_WORDS[code], idx, ok, n, picks, tries, jumps)


def status(name, active, level, take_along, placed, mode, state, posture, alarmed, purring, dbg=None):
    if dbg is not None: return status(name, active, level, take_along, placed, mode, state, posture, alarmed, purring) + spot_debug(*dbg)
    who = name or NO_NAME
    if not active: where = OFF
    elif level == B.LV_MISSION and not take_along: where = HOME
    elif not placed: where = COMING
    else:
        doing = (DOING["alarm"] if alarmed else DOING["move"] if state == B.ST_MOVE else DOING["jump"] if state == B.ST_JUMP
                 else DOING["rub"] if state == B.ST_RUB else POSTURE_WORDS[posture])
        where = "%s, %s%s" % (MODE_WORDS[mode], doing, PURRING if purring else "")
    return "%s: %s" % (who, where)


def entry_rows(cls): return {ENTRY: {"Caption": CAPTION, "Actor": cls, "Order": 0}}     # the entry row: unique already


def field_rows():
    return {ROW + k: dict({"Entry": ENTRY, "Key": k, "Type": t, "Label": label, "Order": order}, **extra) for k, t, label, order, extra in FIELDS}


def action_rows(cls): return {ROW + k: {"Caption": cap, "Actor": cls, "Key": k, "Order": i} for i, (k, cap, _) in enumerate(ACTIONS)}


def preset_rows():
    def text(k, v): return hex_srgb(v) if k in COLORS else str(v)
    return {ROW + row: {"Entry": ENTRY, "Caption": cap, "Order": i, "Values": {k: text(k, v) for k, v in vals.items()}}
            for i, (row, cap, vals) in enumerate(PRESETS)}


def pak_assets(): return list(TABLES)
