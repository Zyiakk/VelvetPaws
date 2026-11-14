"""All animation sequences of the cat in export order, the montages built from them and the blend space samples. Plain Python:
cat_anims.py (Blender) exports SEQS, gen_velvetpaws.py builds the kit assets from the same data."""
import importlib, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
GROUPS = ("cat_anim_gait", "cat_anim_posture", "cat_anim_jump", "cat_anim_action", "cat_anim_social", "cat_anim_overlay")
SEQS = {}
for _g in GROUPS:
    try:
        _m = importlib.import_module(_g)
    except ModuleNotFoundError as e:
        if e.name != _g: raise
        continue
    for _s in _m.SEQS: SEQS[_s.name] = _s
ORDER = list(SEQS)


def length(name): return SEQS[name].length


# montages: name, segments (sequence names), sections ([] = one "Default"), blend in/out (s), start/end posture
_ENTER_LOOP_EXIT = lambda a, b, c: [("Enter", a, "Loop"), ("Loop", b, "Loop"), ("Exit", c, None)]
MONTAGES = [
    {"name": "Sit", "sections": _ENTER_LOOP_EXIT("SitEnter", "SitLoop", "SitExit"), "blend": (0.25, 0.25)},
    {"name": "Lie", "sections": _ENTER_LOOP_EXIT("LieEnter", "LieLoop", "LieExit"), "blend": (0.3, 0.3)},
    {"name": "Sleep", "sections": _ENTER_LOOP_EXIT("SleepEnter", "SleepLoop", "SleepExit"), "blend": (0.4, 0.4)},
    {"name": "Jump", "sections": _ENTER_LOOP_EXIT("JumpTakeoff", "JumpAir", "JumpLand"), "blend": (0.1, 0.2)},
    {"name": "JumpDown", "sections": _ENTER_LOOP_EXIT("JumpDownStart", "JumpAirDown", "JumpDownLand"), "blend": (0.15, 0.2)},
    {"name": "Groom", "sections": [("Default", "Groom", None)], "blend": (0.2, 0.25)},
    {"name": "Stretch", "sections": [("Default", "Stretch", None)], "blend": (0.25, 0.3)},
    {"name": "Yawn", "sections": [("Default", "Yawn", None)], "blend": (0.2, 0.2)},
    {"name": "Hiss", "sections": [("Default", "Hiss", None)], "blend": (0.12, 0.3)},
    # rubbing round Jodi's legs (round 6): RubWalk loops in its one section while the capsule walks slowly (RUB_SPEED) round her with
    # her legs on the cat's left; HeadRub is a one-shot from and back to the stand
    {"name": "RubWalk", "sections": [("Loop", "RubWalk", "Loop")], "blend": (0.3, 0.3)},
    {"name": "HeadRub", "sections": [("Default", "HeadRub", None)], "blend": (0.25, 0.3)},
]
MONTAGES = [m for m in MONTAGES if all(s in SEQS for _, s, _ in m["sections"])]   # only those whose sequences exist yet


RUB_SPEED = SEQS["RubWalk"].speed if "RubWalk" in SEQS else None     # cm/s the capsule should move while RubWalk plays


def section_times(m):
    out, t = [], 0.0
    for name, s, nxt in m["sections"]:
        out.append((name, round(t, 4), nxt)); t += length(s)
    return out


def launch_time(montage):
    """Seconds into the montage where the last paws leave the ground (Seq.lift_off of the Enter section, a few frames before its
    end: the legs trail and draw in after it): stage 3 calls LaunchCharacter there."""
    m = next(m for m in MONTAGES if m["name"] == montage); return SEQS[m["sections"][0][1]].lift_off


# blend space: Speed 0..SPEED_MAX in SPEED_GRID divisions (10 cm/s); samples on grid points (natural speed of each gait)
SPEED_MAX, SPEED_GRID = 300.0, 30           # Run sits at the top; stage 3 caps the cat's speed at SPEED_MAX
BLEND_SAMPLES = [(n, SEQS[n].speed) for n in ("Stand", "Walk", "Trot", "Run") if n in SEQS]
