"""Behaviour of the VelvetPaws cat in plain Python (no Unreal): ids, thresholds, montage steps, settings and the reference of every
decision BP_VP_Cat makes as a pure Blueprint function (VP_*). assets/gen/vp_bp_*.py build the Blueprint from these constants;
tests/test_brain.py checks the reference; scripts/test_behaviour_kit.py calls the Blueprint functions in the kit with kit_cases().
Units: cm, s, degrees; vectors are (x, y, z) tuples in Unreal space (z up)."""
import math, os, sys

W = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(W, "tools", "blender"))
sys.path.insert(0, os.path.join(W, "scripts"))
import cat_seqs as CS
from velvetpaws import names

# ---- ids: plain ints in the Blueprint (no user enum: BPGen enum literals compile to 0) ----
MODE_FOLLOW, MODE_WAIT, MODE_ROAM = 0, 1, 2
ST_REST, ST_MOVE, ST_JUMP, ST_SPOT, ST_ALARM, ST_RUB = 0, 1, 2, 3, 4, 5
GO_FOLLOW, GO_ROAM, GO_RECALL, GO_FLEE, GO_SPOT = 0, 1, 2, 3, 4          # purpose of a move
P_STAND, P_SIT, P_LIE, P_SLEEP = 0, 1, 2, 3                               # postures, in chain order
LV_NONE, LV_OFFICE, LV_MISSION = 0, 1, 2
ACT_NONE, ACT_SIT, ACT_LIE, ACT_SLEEP, ACT_STAND, ACT_GROOM, ACT_YAWN, ACT_STRETCH, ACT_SPOT = range(9)
AFTER_NONE, AFTER_SIT_LOOP, AFTER_LIE_LOOP = 0, 1, 2                      # montage ops due when a step's time is over
JP_NONE, JP_TURN, JP_TAKEOFF, JP_AIR, JP_LAND, JP_WALK = 0, 1, 2, 3, 4, 5   # phases of a jump (JP_WALK: into / out of a walk-in spot)
SPOT_AUTO = 1000                                                          # SpotIdx of a spot found by trace (office spots: 0..n-1)

# ---- body and world ----
SIZE_MIN, SIZE_MAX = 40.0, 115.0          # setting Size in % (AltUI "Scale"), clamped after loading (E24); 40: a kitten (round 6)
CAPSULE_R, CAPSULE_HH = 14.0, 16.0        # cm at size 100 % (cat: 13 x 68.5 x 31 cm incl. tail, shoulder 25)
TRACE_UP, TRACE_DOWN = 150.0, 300.0       # floor traces: from this far above to this far below

# ---- speeds (E1, E14, E18) ----
RUN_ANIM = float(CS.SEQS["Run"].speed)    # top sample of the blend space (300): the cat never runs faster (size 100 %)
assert abs(RUN_ANIM - CS.SPEED_MAX) < 1e-6, "Run sample must be the top of the blend space axis"
MAX_SPEED = RUN_ANIM
WALK_ANIM = float(CS.SEQS["Walk"].speed)  # slowest gait sample (40): the lowest walking speed asked of CharacterMovement
FOLLOW_START, FOLLOW_STOP, FOLLOW_KEEP = 600.0, 300.0, 250.0
FOLLOW_MIN_SPEED, FOLLOW_RUN_AT, FOLLOW_MATCH_AT, FOLLOW_MATCH = 90.0, 1200.0, 450.0, 1.15
RECALL_SPEED, RECALL_ARRIVE, RECALL_TELEPORT = 220.0, 200.0, 4000.0
FOLLOW_TELEPORT = RECALL_TELEPORT          # Follow: farther from Jodi than this = catch up by teleport behind her (E1, E9)
ROAM_RADIUS, ROAM_SPEED, ROAM_STEP_MIN, ROAM_STEP_MAX = 1500.0, 60.0, 200.0, 800.0
ROAM_REST_MIN, ROAM_REST_MAX = 10.0, 40.0
SPOT_WALK_SPEED = 60.0
ARRIVE = 35.0                              # cm to a waypoint
REPATH = 0.5                               # s between new paths while following, recalling or fleeing
STUCK_TIME, STUCK_GAIN = 3.0, 10.0         # no 10 cm nearer to the current waypoint in 3 s = stuck (a repath never resets it)
STUCK_UNSEEDED = 1e9                       # BestDist after a new path / waypoint: the next tick only seeds it (no progress counted)
TURN_RATE = 6.0                            # RInterpTo speed when turning on the spot (jump, spot yaw, alarm)

# ---- rest and routine (E15) ----
ROUTINE_MIN, ROUTINE_MAX = 6.0, 14.0
LIE_AFTER, SLEEP_AFTER = 8.0, 30.0
ROUTINE = {   # posture -> ((action, weight %), ...); the rest of 100 % is "nothing". ACT_SPOT also from sit and lie: a cat resting on the
              # floor gets up to a spot now and then (only from stand, 0.81 of floor-lying 20 min sessions had no spot attempt; now 0.07)
    P_STAND: ((ACT_SIT, 50), (ACT_STRETCH, 15), (ACT_SPOT, 25)),
    P_SIT: ((ACT_GROOM, 30), (ACT_YAWN, 15), (ACT_LIE, 20), (ACT_STAND, 5), (ACT_SPOT, 10)),
    P_LIE: ((ACT_SLEEP, 25), (ACT_SIT, 10), (ACT_SPOT, 5)),
    P_SLEEP: ((ACT_LIE, 10),),
}
ACT_POSTURE = {ACT_SIT: P_SIT, ACT_LIE: P_LIE, ACT_SLEEP: P_SLEEP, ACT_STAND: P_STAND}
OVERLAY_RATE = 2.0                         # FInterpTo speed of OverlayAlpha (1 awake, 0 asleep)

# ---- spots and jumps (E11, E23) ----
JUMP_MAX, SPOT_MIN = 150.0, 35.0           # spot height above the floor
JUMP_CLEAR_UP, JUMP_CLEAR_DOWN = 25.0, 10.0
JUMP_FROM = 45.0                           # cm from the spot's edge to the take-off point on the floor (auto spots)
SPOT_FLAT, SPOT_HALF, SPOT_HEADROOM = 3.0, 18.0, 40.0    # trace spot: 4 corner hits within 3 cm, at +-18 cm, free 40 cm above
SPOT_SCAN = 0.25                           # s between two trace candidates
SPOT_SCAN_MIN, SPOT_SCAN_MAX = 80.0, 400.0
SPOT_KEEP = 800.0                          # a known auto spot farther than this is forgotten
SPOT_VERIFY = 8.0                          # office spot: trace hit within this of the table height
SPOT_VERIFY_UP = 60.0                      # the check trace starts this far above the spot, or 5 cm under the board above a compartment
OPEN_ROOM = 999.0                          # Room of a spot with nothing above it (office_map.OPEN_ROOM)
ROOM_MARGIN = 4.0                          # cm between the capsule's top at the jump's apex and the board above a compartment
JUMP_CLEAR_MIN = 3.0                       # lowest apex over the target of a jump into a compartment
KITTEN_FULL = 0.85                         # scale from which she reaches every spot; smaller, the highest spot shrinks with her (kitten)
SPOT_DROP_BLOCKED, SPOT_DROP_STUCK = 60.0, 300.0   # s a spot is left out after a closed door on the way / after being stuck on the way
STAY_RANGE, STAY_DEFAULT = (0.5, 30.0), (2.0, 10.0)  # minutes on a chosen spot (AltUI "Stay at least/at most"); see stay_time
JUMP_ABORT_GROUND, JUMP_ABORT_AIR = 0.5, 3.0
FOLLOW_SPOT_R = 400.0                      # Follow: spots within this of Jodi

# ---- combat (E19) ----
ENEMY_NEAR, ENEMY_CALM_R, CALM_TIME, ENEMY_SCAN = 800.0, 1000.0, 10.0, 0.5
HISS_ABORT = 300.0
# ---- rubbing round Jodi's legs (round 6) ----
RUB_NEAR, RUB_STILL_SPEED, RUB_STILL, RUB_GAP, RUB_CHANCE = 400.0, 10.0, 2.0, 90.0, 35.0   # Jodi within 4 m, still 2 s; 90 s apart; 35 %
# a slow loop round both legs, always with Jodi on the cat's LEFT (RubWalk curves and leans the body to the left, cat_anim_social):
# an ellipse across her (legs at about +-10 cm) by front to back, her capsule centre this far from Jodi's
RUB_A, RUB_B = 30.0, 24.0
RUB_WALK = float(CS.RUB_SPEED) if getattr(CS, "RUB_SPEED", None) else 20.0   # cm/s of RubWalk (its sample speed); 20 without it
RUB_PERIOD = math.pi * (3 * (RUB_A + RUB_B) - math.sqrt((3 * RUB_A + RUB_B) * (RUB_A + 3 * RUB_B))) / RUB_WALK   # s per loop (Ramanujan)
RUB_CLOSE = 70.0                           # cm from Jodi: she starts circling (farther: she walks over, the loop waits)
RUB_TIME_MIN, RUB_TIME_MAX = 9.0, 16.0     # s of circling, then a head rub against her leg
RUB_STOP_SPEED, RUB_SPEED_MAX = 60.0, 150.0   # Jodi faster than this ends it; the cat never faster while rubbing
PUPIL_CALM, PUPIL_WIDE, PUPIL_RATE = 0.35, 0.75, 1.5   # M_VP_CatEye PupilOpen: moderate awake, wide while rubbing/purring or lying/asleep
FLEE_BEHIND, FLEE_SPEED, HIGH_SPOT, FLEE_SPOT_R = 200.0, MAX_SPEED, 90.0, 600.0

# ---- teleport out of sight (E9) ----
TELEPORT_DIST = 350.0
TELEPORT_ANGLES = (0.0, 35.0, -35.0, 70.0, -70.0, 110.0, -110.0)   # degrees from straight behind the camera
VIEW_COS = 0.5

# ---- levels and home (E22) ----
OFFICE = "JodisOffice"
MENU_LEVELS = ("", "Intro", "Loading", "Menu", "Menu_Level2", "Menu_Sitting", "Menu_Standing", "Entry")
PLACE_DELAY, PLACE_RETRY, PLACE_TRIES = 1.0, 0.5, 20
SAVE_EVERY, SAVE_MOVED = 10.0, 30.0
HOP_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"   # office next-hop strings: two base-36 digits per target, "ZZ" = unreachable
HOP_NONE = 36 * 36 - 1
HOOKS = ["Init Level", "Place Start", "Start Timers", "Poll Keys", "Combat Tick", "Tick Rest", "Tick Move", "Tick Jump", "Tick Spot",
         "Tick Alarm", "Save Place", "Go To Spot", "Leave Spot", "Alarm Rest", "Rest Routine", "Sound Tick", "Cue", "Tick Rub", "Watch Jodi"]   # BP_VP_Cat functions the modules fill

# ---- settings (E21): (variable, bpdsl type, default ImportText) ----
LC = "struct:/Script/CoreUObject.LinearColor"; KEY = "struct:/Script/InputCore.Key"; VEC = "struct:/Script/CoreUObject.Vector"
def _lc(c): return "(R=%g,G=%g,B=%g,A=%g)" % tuple(c)
SETTINGS = [
    ("Active", "bool", "true"), ("Mode", "int", str(MODE_FOLLOW)), ("TakeAlong", "bool", "true"),
    ("Pattern", "int", "1"),                                          # 0 solid, 1 tabby (default), 2 brindle, 3 spotted, 4 tricolour, 5 markings
    ("BaseColor", LC, _lc(names.DEF_BASE)), ("SecondColor", LC, _lc(names.DEF_SECOND)), ("EyeColor", LC, _lc(names.DEF_EYE)),
    ("Size", "float", "100.0"), ("Meow", "bool", "true"), ("MeowRate", "float", "0.5"), ("Purr", "bool", "true"),
    ("Volume", "float", "1.0"), ("CatName", "string", ""), ("RecallKey", KEY, None),   # None: no default (no key)
    ("StayMin", "float", "%.1f" % STAY_DEFAULT[0]), ("StayMax", "float", "%.1f" % STAY_DEFAULT[1]),   # minutes on a chosen spot
]
PLACE_VARS = [("HasPlace", "bool", "false"), ("PlaceSpot", "int", "-1"), ("PlaceLoc", VEC, "(X=0,Y=0,Z=0)"),
              ("PlaceYaw", "float", "0.0"), ("PlacePosture", "int", str(P_STAND))]
# coat pattern (setting Pattern) -> (PatternWeights of M_VP_CatFur: tabby, brindle, spots, tricolour patches; WhiteMarks); the
# third colour (red-orange) stays the instance's fixed ThirdColor (spec). As tools/blender/cat_look_tex.py: calico, tabwhite.
PATTERNS = {0: ((0.0, 0.0, 0.0, 0.0), 0.0), 1: ((1.0, 0.0, 0.0, 0.0), 0.0), 2: ((0.0, 1.0, 0.0, 0.0), 0.0),
            3: ((0.0, 0.0, 1.0, 0.0), 0.0), 4: ((0.0, 0.0, 0.0, 1.0), 1.0), 5: ((0.0, 0.0, 0.0, 0.0), 1.0)}
SAVE_SOON = 0.25            # s after the last slider / colour change until it is saved (Save Now timer)
WAKE_DELAY = 0.1            # s from switching her on (AltUI) until Place Cat
TEST_KEYS = {"Recall": "F8", "CycleMode": "F9", "TakeAlong": "F10", "Meow": "F6"}   # play tests of stages 3/4 only (gen_velvetpaws.TEST_KEYS)
# spot diagnostic for play tests: the last step of the spot chain and counters appended to the AltUI status line (ui.spot_debug);
# set only at the steps (no per-tick work), words in ui.DBG_WORDS. Off for a release.
DEBUG_SPOTS = False
(DBG_NONE, DBG_NONE_NEAR, DBG_WALK, DBG_STUCK, DBG_TURN, DBG_TAKEOFF, DBG_AIR, DBG_NOT_AIRBORNE, DBG_AIR_LONG, DBG_OFF_SPOT, DBG_ON_SPOT,
 DBG_DOWN, DBG_DOOR, DBG_WALK_IN) = range(14)


# ---- montages (names and sections from cat_seqs.MONTAGES only) ----
def _montage(name): return next(m for m in CS.MONTAGES if m["name"] == name)


def section(montage, role):
    """Section name of a montage: enter = first, loop = the one whose next is itself, exit = last of a three-section montage."""
    secs = _montage(montage)["sections"]
    if len(secs) < 3: raise KeyError("%s has no %s section" % (montage, role))
    if role == "enter": return secs[0][0]
    if role == "exit": return secs[-1][0]
    if role == "loop": return next(n for n, _, nx in secs if nx == n)
    raise KeyError(role)


def blend_out(montage): return _montage(montage)["blend"][1]


L = CS.length
POSTURE_MONTAGE = {P_SIT: "Sit", P_LIE: "Lie", P_SLEEP: "Sleep"}
# ops: ("play", montage) | ("jump", montage, section) | ("stop", montage or None, blend seconds)
AFTER_OPS = {AFTER_NONE: [], AFTER_SIT_LOOP: [("play", "Sit"), ("jump", "Sit", section("Sit", "loop"))],
             AFTER_LIE_LOOP: [("play", "Lie"), ("jump", "Lie", section("Lie", "loop"))]}
# (from, to) -> (ops at the start, seconds until the next step may start, after-op code due then); stage 2 interface: an Exit ends in
# the posture where the next lower montage starts its Loop, the caller starts it while the running one blends out
TRANSITIONS = {
    (P_STAND, P_SIT): ([("play", "Sit")], L("SitEnter"), AFTER_NONE),
    (P_SIT, P_STAND): ([("jump", "Sit", section("Sit", "exit"))], L("SitExit"), AFTER_NONE),
    (P_SIT, P_LIE): ([("play", "Lie")], L("LieEnter"), AFTER_NONE),
    (P_LIE, P_SIT): ([("jump", "Lie", section("Lie", "exit"))], L("LieExit") - blend_out("Lie"), AFTER_SIT_LOOP),
    (P_LIE, P_SLEEP): ([("play", "Sleep")], L("SleepEnter"), AFTER_NONE),
    (P_SLEEP, P_LIE): ([("jump", "Sleep", section("Sleep", "exit"))], L("SleepExit") - blend_out("Sleep"), AFTER_LIE_LOOP),
}
# action -> (montage, posture it needs, seconds, after-op)
ACTIONS = {
    ACT_GROOM: ("Groom", P_SIT, L("Groom") - blend_out("Groom"), AFTER_SIT_LOOP),
    ACT_YAWN: ("Yawn", P_SIT, L("Yawn") - blend_out("Yawn"), AFTER_SIT_LOOP),
    ACT_STRETCH: ("Stretch", P_STAND, L("Stretch"), AFTER_NONE),
}
HISS = ("Hiss", L("Hiss"))
JUMP_UP, JUMP_DOWN = "Jump", "JumpDown"
LAND_TIME = {JUMP_UP: L(_montage(JUMP_UP)["sections"][-1][1]), JUMP_DOWN: L(_montage(JUMP_DOWN)["sections"][-1][1])}
LAUNCH = {JUMP_UP: CS.launch_time(JUMP_UP), JUMP_DOWN: CS.launch_time(JUMP_DOWN)}

# ---- sounds (plan Etappe 4) ----
CUE_NONE, CUE_HISS, CUE_YAWN, CUE_LAND, CUE_CALLED, CUE_ARRIVED, CUE_GREET = range(7)
MEOW_SLOW, MEOW_FAST = 240.0, 20.0        # mean seconds between meows at MeowRate 0 and 1 (0.5: about 69 s)
MEOW_LN = math.log(MEOW_FAST / MEOW_SLOW)
PITCH_VAR = 0.04                           # +-4 % random pitch; the size shifts it by sqrt(100 / Size)
PURR_START, PURR_STOP = 300.0, 350.0       # Jodi nearer than 3 m: purr; farther than 3.5 m: stop
PURR_FADE_IN, PURR_FADE_OUT, STOP_FADE = 0.8, 0.6, 0.2
REUNION_FAR, REUNION_NEAR, REUNION_AWAY = 1200.0, 400.0, 20.0
CALL_DELAY, ARRIVE_DELAY, GREET_DELAY, ARRIVE_MEOW = 0.35, 0.25, 0.6, 0.5


def jaw_open(seq, deg=3.0):
    """Seconds into a sequence where the jaw first opens beyond deg degrees (the cue of its sound)."""
    s = CS.SEQS[seq]
    for f in range(s.frames + 1):
        if s.frame_pose(f)["jaw"] > deg: return f * s.length / s.frames
    raise ValueError("%s never opens the jaw" % seq)


CUE_AT = {CUE_HISS: jaw_open(HISS[0]), CUE_YAWN: jaw_open("Yawn"), CUE_LAND: 0.0, CUE_CALLED: CALL_DELAY,
          CUE_ARRIVED: ARRIVE_DELAY, CUE_GREET: GREET_DELAY}
ACT_CUE = {ACT_YAWN: CUE_YAWN}             # actions with a sound (vp_bp_posture.f_do_action)


# ---- reference of the pure Blueprint functions (same formulas, same order of operations) ----
def _clamp(v, lo, hi): return max(lo, min(hi, v))


def map_clamped(v, a, b, c, d):                    # KismetMathLibrary.MapRangeClamped
    return c + (d - c) * _clamp((v - a) / (b - a), 0.0, 1.0)


def _norm2d(x, y, fallback):                        # Normal(MakeVector(x, y, 0)) with a fallback when shorter than 1e-3
    l = math.hypot(x, y)
    return (x / l, y / l) if l > 1e-3 else fallback


def follow_speed(dist, jodi_speed):
    v = map_clamped(dist, FOLLOW_STOP, FOLLOW_RUN_AT, FOLLOW_MIN_SPEED, MAX_SPEED)
    if dist > FOLLOW_MATCH_AT: v = max(v, jodi_speed * FOLLOW_MATCH)
    return 0.0 if dist <= FOLLOW_STOP else min(v, MAX_SPEED)


def follow_point(jodi, cat):
    dx, dy = _norm2d(cat[0] - jodi[0], cat[1] - jodi[1], (-1.0, 0.0))
    return (jodi[0] + dx * FOLLOW_KEEP, jodi[1] + dy * FOLLOW_KEEP, cat[2])


def anim_speed(v, scale): return min(v / scale, RUN_ANIM)


def max_speed(scale): return MAX_SPEED * scale


def jump_velocity(frm, to, clear, g):
    dz = to[2] - frm[2]; h = max(dz, 0.0) + clear
    vz = math.sqrt(2.0 * g * h); T = vz / g + math.sqrt(2.0 * (h - dz) / g)
    return ((to[0] - frm[0]) / T, (to[1] - frm[1]) / T, vz)


def posture_next(p, want): return p + int(want > p) - int(want < p)


def _allowed(act, rest, spot_ok, on_spot):
    if act == ACT_SPOT: return spot_ok and not on_spot
    if act in (ACT_STRETCH, ACT_STAND): return not on_spot
    if act == ACT_LIE: return rest >= LIE_AFTER
    if act == ACT_SLEEP: return rest >= SLEEP_AFTER
    return True


def pick_routine(posture, r, rest, spot_ok, on_spot):
    acc = 0.0
    for act, w in ROUTINE.get(posture, ()):
        acc += w
        if r < acc: return act if _allowed(act, rest, spot_ok, on_spot) else ACT_NONE
    return ACT_NONE


def teleport_candidate(i, jodi, cam_yaw):
    a = math.radians(cam_yaw + 180.0 + TELEPORT_ANGLES[i])
    return (jodi[0] + math.cos(a) * TELEPORT_DIST, jodi[1] + math.sin(a) * TELEPORT_DIST, jodi[2])


def out_of_view(p, cam, fwd):
    d = (p[0] - cam[0], p[1] - cam[1], p[2] - cam[2]); l = math.sqrt(sum(c * c for c in d))
    n = tuple(c / l for c in d) if l > 1e-2 else (0.0, 0.0, 0.0)     # KismetMathLibrary.Normal(A, 1e-4): zero when tiny
    return sum(a * b for a, b in zip(n, fwd)) < VIEW_COS


def flee_goal(jodi, enemy):
    dx, dy = _norm2d(jodi[0] - enemy[0], jodi[1] - enemy[1], (1.0, 0.0))
    return (jodi[0] + dx * FLEE_BEHIND, jodi[1] + dy * FLEE_BEHIND, jodi[2])


def level_kind(name):
    n = name.lower()                                                  # VP_LevelKind compares with EqualEqual_StriStri
    if n == OFFICE.lower(): return LV_OFFICE
    return LV_NONE if n in [m.lower() for m in MENU_LEVELS] else LV_MISSION


def encode_hops(row):
    """Two base-36 digits (0-9, A-Z) per target b: the next walk point from this one towards b; "ZZ" = unreachable. Plain ASCII
    letters and digits: no quoting or escaping anywhere between JSON, BPGen and the DataTable, and no parsing at level start."""
    if len(row) >= HOP_NONE: raise ValueError("%d walk points: the encoding holds at most %d" % (len(row), HOP_NONE - 1))
    return "".join(HOP_DIGITS[v // 36] + HOP_DIGITS[v % 36] for v in (h if h >= 0 else HOP_NONE for h in row))


def _digit(c):                                      # GetCharacterAsNumber: '0'..'9' = 48..57, 'A'..'Z' = 65..90
    return ord(c) - 48 - 7 * int(ord(c) >= 65)


def next_hop(next_str, b):
    v = 36 * _digit(next_str[2 * b]) + _digit(next_str[2 * b + 1])
    return -1 if v == HOP_NONE else v


def meow_interval(rate, r):
    return MEOW_SLOW * math.exp(_clamp(rate, 0.0, 1.0) * MEOW_LN) * (0.5 + r)


def sound_pitch(scale, r): return math.sqrt(1.0 / scale) * (1.0 + PITCH_VAR * (2.0 * r - 1.0))


def next_variant(last, r, n):
    skip = 0 <= last < n and n > 1
    m = n - int(skip)
    pick = min(int(math.floor(r * m)), m - 1)
    return pick + int(skip and pick >= last)


def purr_want(state, posture, alarmed, dist, purring):
    resting = (state in (ST_REST, ST_SPOT) and posture >= P_SIT or state == ST_RUB) and not alarmed
    return resting and dist < (PURR_STOP if purring else PURR_START)


def pattern_weights(p): return PATTERNS.get(p, PATTERNS[0])[0]


def white_marks(p): return PATTERNS.get(p, PATTERNS[0])[1]


def want_here(active, level, take_along): return bool(active and (level == LV_OFFICE or (level == LV_MISSION and take_along)))


def jump_reach(scale): return JUMP_MAX * min(1.0, scale / KITTEN_FULL)


def spot_fits(height, room, scale):
    """A spot for her size: not higher than she jumps (a kitten less high), and a compartment tall enough for her capsule."""
    return height <= jump_reach(scale) and room >= 2.0 * CAPSULE_HH * scale + ROOM_MARGIN


def jump_clear(room, scale):
    """Apex of the jump over the spot: JUMP_CLEAR_UP in the open, lower under a compartment's board (her capsule's top stays
    ROOM_MARGIN under it)."""
    return max(JUMP_CLEAR_MIN, min(JUMP_CLEAR_UP, room - 2.0 * CAPSULE_HH * scale - ROOM_MARGIN))


def stay_time(lo, hi, r):
    """Seconds on a chosen spot: between the two settings (minutes, either order), r in 0..1."""
    a, b = min(lo, hi), max(lo, hi)
    return 60.0 * (a + (b - a) * r)


def rub_want(dist, jodi_speed, still_for, since_rub, posture, r):
    return (dist <= RUB_NEAR and jodi_speed <= RUB_STILL_SPEED and still_for >= RUB_STILL and since_rub >= RUB_GAP and posture <= P_SIT
            and r < RUB_CHANCE)


def rub_point(jodi, fwd, t):
    """Point of the loop round Jodi's legs at phase t (radians): RUB_A * cos t to her right, RUB_B * sin t to her front; a growing t
    keeps her on the cat's left. fwd: her forward vector (only x, y count)."""
    fx, fy = _norm2d(fwd[0], fwd[1], (1.0, 0.0)); rx, ry = -fy, fx          # Unreal: right = forward turned +90 degrees about z
    c, s = math.cos(t), math.sin(t)
    return (jodi[0] + RUB_A * c * rx + RUB_B * s * fx, jodi[1] + RUB_A * c * ry + RUB_B * s * fy, jodi[2])


def rub_phase(jodi, fwd, cat):
    """Phase of the loop point in the cat's direction from Jodi (where she joins the loop)."""
    fx, fy = _norm2d(fwd[0], fwd[1], (1.0, 0.0)); rx, ry = -fy, fx; dx, dy = cat[0] - jodi[0], cat[1] - jodi[1]
    return math.atan2((dx * fx + dy * fy) / RUB_B, (dx * rx + dy * ry) / RUB_A)


def pupil_open(state, posture):
    return PUPIL_WIDE if state == ST_RUB or posture >= P_LIE else PUPIL_CALM


# name -> (reference, [(param, bpdsl type)], output type); the Blueprint function has exactly these inputs and one output "Out"
F, I, V, S, Bo = "float", "int", VEC, "string", "bool"
BP_FUNCS = {
    "VP_FollowSpeed": (follow_speed, [("Dist", F), ("JodiSpeed", F)], F),
    "VP_FollowPoint": (follow_point, [("Jodi", V), ("Cat", V)], V),
    "VP_AnimSpeed": (anim_speed, [("V", F), ("Scale", F)], F),
    "VP_MaxSpeed": (max_speed, [("Scale", F)], F),
    "VP_JumpVelocity": (jump_velocity, [("From", V), ("To", V), ("Clear", F), ("G", F)], V),
    "VP_PostureNext": (posture_next, [("P", I), ("Want", I)], I),
    "VP_PickRoutine": (pick_routine, [("Posture", I), ("R", F), ("Rest", F), ("SpotOK", Bo), ("OnSpot", Bo)], I),
    "VP_TeleportCandidate": (teleport_candidate, [("Index", I), ("Jodi", V), ("CamYaw", F)], V),
    "VP_OutOfView": (out_of_view, [("P", V), ("Cam", V), ("Fwd", V)], Bo),
    "VP_FleeGoal": (flee_goal, [("Jodi", V), ("Enemy", V)], V),
    "VP_LevelKind": (level_kind, [("Name", S)], I),
    "VP_NextHop": (next_hop, [("Next", S), ("B", I)], I),
    "VP_MeowInterval": (meow_interval, [("Rate", F), ("R", F)], F),
    "VP_SoundPitch": (sound_pitch, [("Scale", F), ("R", F)], F),
    "VP_NextVariant": (next_variant, [("Last", I), ("R", F), ("N", I)], I),
    "VP_PurrWant": (purr_want, [("State", I), ("Posture", I), ("Alarmed", Bo), ("Dist", F), ("Purring", Bo)], Bo),
    "VP_PatternWeights": (pattern_weights, [("P", I)], LC),
    "VP_WhiteMarks": (white_marks, [("P", I)], F),
    "VP_WantHere": (want_here, [("Active", Bo), ("Level", I), ("TakeAlong", Bo)], Bo),
    "VP_SpotFits": (spot_fits, [("Height", F), ("Room", F), ("Scale", F)], Bo),
    "VP_JumpClear": (jump_clear, [("Room", F), ("Scale", F)], F),
    "VP_StayTime": (stay_time, [("Lo", F), ("Hi", F), ("R", F)], F),
    "VP_RubWant": (rub_want, [("Dist", F), ("JodiSpeed", F), ("StillFor", F), ("SinceRub", F), ("Posture", I), ("R", F)], Bo),
    "VP_RubPoint": (rub_point, [("Jodi", V), ("Fwd", V), ("T", F)], V),
    "VP_RubPhase": (rub_phase, [("Jodi", V), ("Fwd", V), ("Cat", V)], F),
    "VP_PupilOpen": (pupil_open, [("State", I), ("Posture", I)], F),
}


def kit_cases():
    """(function, args in parameter order, expected) for scripts/test_behaviour_kit.py."""
    out = []
    add = lambda fn, *a: out.append((fn, a, BP_FUNCS[fn][0](*a)))
    for d in (0.0, 250.0, 300.0, 301.0, 450.0, 451.0, 600.0, 1000.0, 1200.0, 3000.0):
        for js in (0.0, 200.0, 500.0): add("VP_FollowSpeed", d, js)
    for j, c in (((0.0, 0.0, 90.0), (0.0, 1000.0, 16.0)), ((100.0, 50.0, 0.0), (100.0, 50.0, 0.0)), ((0.0, 0.0, 0.0), (-300.0, 400.0, 5.0))):
        add("VP_FollowPoint", j, c)
    for v in (0.0, 150.0, 300.0, 450.0):
        for s in (0.85, 1.0, 1.15): add("VP_AnimSpeed", v, s)
    for s in (0.85, 1.0, 1.15): add("VP_MaxSpeed", s)
    for frm, to, cl in (((0.0, 0.0, 16.0), (80.0, 30.0, 166.0), JUMP_CLEAR_UP), ((0.0, 0.0, 60.0), (60.0, 0.0, 16.0), JUMP_CLEAR_DOWN),
                        ((10.0, 10.0, 16.0), (10.0, 90.0, 61.0), JUMP_CLEAR_UP)):
        add("VP_JumpVelocity", frm, to, cl, 980.0)
    for p in range(4):
        for w in range(4): add("VP_PostureNext", p, w)
    for p in range(4):
        for r in (0.0, 10.0, 30.0, 37.0, 49.9, 50.0, 64.9, 65.0, 72.0, 89.9, 90.0, 99.9):
            for rest in (0.0, 10.0, 40.0):
                for ok in (False, True):
                    for on in (False, True): add("VP_PickRoutine", p, r, rest, ok, on)
    for i in range(len(TELEPORT_ANGLES)):
        for yaw in (0.0, 90.0, -135.0): add("VP_TeleportCandidate", i, (100.0, -50.0, 20.0), yaw)
    for p, cam, fwd in (((-350.0, 0.0, 0.0), (-200.0, 0.0, 50.0), (1.0, 0.0, 0.0)), ((300.0, 0.0, 0.0), (-200.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                        ((0.0, 500.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))):
        add("VP_OutOfView", p, cam, fwd)
    for j, e in (((0.0, 0.0, 5.0), (300.0, 0.0, 0.0)), ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), ((50.0, 50.0, 0.0), (-100.0, 200.0, 0.0))):
        add("VP_FleeGoal", j, e)
    for n in ("JodisOffice", "jodisoffice", "Level_1", "Level_3", "ShootingRange", "Challenge_Maze") + MENU_LEVELS: add("VP_LevelKind", n)
    s = encode_hops([0, 2, -1, 3, 399, 17, 35, 36])
    for b in range(8): add("VP_NextHop", s, b)
    for rate in (-0.2, 0.0, 0.25, 0.5, 1.0, 1.5):
        for r in (0.0, 0.5, 0.999): add("VP_MeowInterval", rate, r)
    for sc in (0.85, 1.0, 1.15):
        for r in (0.0, 0.5, 1.0): add("VP_SoundPitch", sc, r)
    for n in (1, 2, 4):
        for last in (-1, 0, 1, 3):
            for r in (0.0, 0.3, 0.6, 0.999): add("VP_NextVariant", last, r, n)
    for st in (ST_REST, ST_MOVE, ST_SPOT, ST_ALARM, ST_RUB):
        for p in range(4):
            for al in (False, True):
                for d in (100.0, 320.0, 400.0):
                    for pu in (False, True): add("VP_PurrWant", st, p, al, d, pu)
    for p in range(-1, 8): add("VP_PatternWeights", p); add("VP_WhiteMarks", p)
    for a in (False, True):
        for lv in (LV_NONE, LV_OFFICE, LV_MISSION):
            for ta in (False, True): add("VP_WantHere", a, lv, ta)
    for h in (3.0, 50.0, 60.0, 100.0, 127.0, 134.0, 150.0):
        for room in (OPEN_ROOM, 47.5, 44.3, 30.0):
            for sc in (0.4, 0.6, 0.85, 1.0, 1.15): add("VP_SpotFits", h, room, sc)
    for room in (OPEN_ROOM, 47.5, 44.3, 38.0, 20.0):
        for sc in (0.4, 1.0, 1.15): add("VP_JumpClear", room, sc)
    for lo, hi in ((0.5, 30.0), (2.0, 10.0), (10.0, 2.0), (5.0, 5.0)):
        for r in (0.0, 0.5, 1.0): add("VP_StayTime", lo, hi, r)
    for d in (100.0, 400.0, 401.0):
        for js in (0.0, 10.0, 11.0):
            for st in (1.0, 2.0):
                for sr in (30.0, 90.0):
                    for p in (P_STAND, P_SIT, P_LIE):
                        for r in (10.0, 34.9, 35.0): add("VP_RubWant", d, js, st, sr, p, r)
    for fwd in ((1.0, 0.0, 0.0), (0.0, 2.0, 0.5), (-0.6, 0.8, 0.0), (0.0, 0.0, 1.0)):
        for t in (0.0, 0.7, math.pi / 2, 2.5, math.pi, 4.0, 3 * math.pi / 2, 6.0, 13.0): add("VP_RubPoint", (120.0, -40.0, 92.0), fwd, t)
        for cat in ((300.0, -40.0, 16.0), (120.0, 200.0, 16.0), (0.0, -100.0, 16.0)): add("VP_RubPhase", (120.0, -40.0, 92.0), fwd, cat)
    for st in (ST_REST, ST_MOVE, ST_SPOT, ST_RUB):
        for p in range(4): add("VP_PupilOpen", st, p)
    return out
