"""Pose language of the VelvetPaws animations, plain Python (no Blender): channels, keyed tracks, periodic helpers, the paw path
of the gaits and the sequence types. cat_animlib.py solves a pose onto the rig; tests and gen_velvetpaws.py import this directly.

Anim space in cm: the cat faces -Y; x = to her left (+X), f = forward (-Y), z = up, floor z = 0. Angles in degrees, each about an
armature axis (see CHANNELS). The rig's rest is STAND: every angle 0, the paws on REST_PAW. Paw channels are absolute targets of the
contact point (tail of toe_* / finger_*); the joints between hip or shoulder and paw are solved by IK in cat_animlib.py."""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cat_rig

FPS = 30
LEGS = ("hl", "hr", "fl", "fr")          # hind left/right (thigh..toe), fore left/right (scapula..finger)
TIP = {"hl": "toe_l", "hr": "toe_r", "fl": "finger_l", "fr": "finger_r"}


def _rest_tip(bone):
    _, _, _, (x, y, z) = next(b for b in cat_rig.BONES if b[0] == bone)
    return (round(x * 100, 3), round(-y * 100, 3), round(z * 100, 3))


REST_PAW = {leg: _rest_tip(b) for leg, b in TIP.items()}


def _ch(lo, hi, doc, default=0.0): return (default, lo, hi, doc)


# name -> (default, min, max, meaning). Rotation axes: Z up (yaw), X to the left (pitch), Y backwards (roll).
CHANNELS = {
    "pel_x": _ch(-15, 15, "pelvis shift to the left, cm"), "pel_f": _ch(-15, 15, "pelvis shift forward, cm"),
    "pel_z": _ch(-16, 8, "pelvis height change, cm"),
    "pel_y": _ch(-60, 60, "pelvis yaw, + turns to her left (about +Z)"),
    "pel_p": _ch(-60, 60, "pelvis pitch, + nose down (about +X)"),
    "pel_r": _ch(-95, 95, "pelvis roll, + left side down (about +Y)"),
    # spine: each bone relative to its parent, same sense as the pelvis; sp_r is spread over the three bones
    "sp1_p": _ch(-30, 30, "spine_01 pitch, + front end down"), "sp2_p": _ch(-30, 30, "spine_02 pitch"), "sp3_p": _ch(-30, 30, "spine_03 pitch"),
    "sp1_y": _ch(-25, 25, "spine_01 yaw"), "sp2_y": _ch(-25, 25, "spine_02 yaw"), "sp3_y": _ch(-25, 25, "spine_03 yaw"),
    "sp_r": _ch(-30, 30, "roll spread over spine_01..03"),
    "nk1_p": _ch(-45, 45, "neck_01 pitch, + raises the neck (about -X)"), "nk2_p": _ch(-45, 45, "neck_02 pitch, + raises"),
    "nk_y": _ch(-50, 50, "neck yaw spread over neck_01/02"),
    "hd_p": _ch(-60, 60, "head pitch, + nose down"), "hd_y": _ch(-60, 60, "head yaw"), "hd_r": _ch(-45, 45, "head roll, + left ear down"),
    "jaw": _ch(0, 40, "jaw open"),
    "earl_p": _ch(-20, 80, "left ear back/flat (+)"), "earl_y": _ch(-40, 60, "left ear turned outward (+)"),
    "earr_p": _ch(-20, 80, "right ear back/flat (+)"), "earr_y": _ch(-40, 60, "right ear turned outward (+)"),
    # tail: lift spread over tail_01..03 (+ up, about +X since the tail points +Y), curl over tail_04..08 (+ tip up),
    # side spread over all eight (+ to her left), wrap over tail_04..08 about the vertical, wave = travelling yaw wave (amplitude per bone) at phase tl_ph (cycles)
    "tl_lift": _ch(-40, 120, "tail raised (+)"), "tl_curl": _ch(-60, 90, "tail tip curled up (+)"),
    "tl_wrap": _ch(-200, 200, "tail_04..08 turned about the vertical, + curving forward round her left side (a tail laid round the paws)"),
    "tl_side": _ch(-120, 120, "tail swung to her left (+)"), "tl_wave": _ch(0, 15, "travelling wave, deg per bone"),
    "tl_ph": _ch(-1e6, 1e6, "phase of the wave, cycles"),
}
for _leg in LEGS:
    _x, _f, _z = REST_PAW[_leg]
    CHANNELS.update({
        _leg + "_x": _ch(-25, 25, "paw target x, cm", _x), _leg + "_f": _ch(-45, 45, "paw target forward, cm", _f),
        _leg + "_z": _ch(-0.3, 45, "paw target height, cm", _z),
        _leg + "_ank": _ch(-90, 140, "hind: metatarsus tilt, + heel up; fore: wrist flex, + paw curls back", 0.0),
        _leg + "_toe": _ch(-40, 160, "toe flex, + toes curl down/back (past 90: a tucked paw's digits point back)", 0.0),
        _leg + "_roll": _ch(-95, 95, "paw rolled about the forward axis, + as pel_r (left side down): a paw lying on its side", 0.0),
        _leg + "_pole": _ch(-60, 60, "knee/elbow turned outward (+)", 0.0),
    })
CHANNELS.update({"fl_scap": _ch(-40, 40, "left scapula extra pitch, + top back"), "fr_scap": _ch(-40, 40, "right scapula extra pitch"),
                 "fl_sld": _ch(-1.5, 1.5, "left scapula slide along its long axis, cm, + down (- = blade rises above the back)"),
                 "fr_sld": _ch(-1.5, 1.5, "right scapula slide, cm, + down")})


def zero_pose():
    return {k: v[0] for k, v in CHANNELS.items()}


def check_pose(P):
    """Names of channels that are missing, unknown, NaN or outside their limits."""
    bad = [k for k in CHANNELS if k not in P] + [k for k in P if k not in CHANNELS]
    for k, v in P.items():
        if k in CHANNELS and (v != v or not CHANNELS[k][1] <= v <= CHANNELS[k][2]): bad.append(k)
    return bad


def F(n):
    """Frame n (may be fractional) in seconds."""
    return n / FPS


def chan(pose, *names):
    """The given channels of a pose (to key them together)."""
    return {n: pose[n] for n in names}


PAW = ("_x", "_f", "_z", "_ank", "_toe")


def paw_keys(pose, leg):
    """A paw's target and digit channels of a pose (leg + _x _f _z _ank _toe), to key."""
    return {leg + c: pose[leg + c] for c in PAW}


def paw_xyz(pose, leg):
    """A paw's target as (x, f, z), cm."""
    return (pose[leg + "_x"], pose[leg + "_f"], pose[leg + "_z"])


def step_arc(lift, d, n):
    """Height of a step d into its n (seconds or frames) between two plants: lift * sin(pi d / n), so the paw leaves the floor
    at once and lands at d = n."""
    return lift * math.sin(math.pi * d / n) if 0.0 < d < n else 0.0


def key_step_arc(tracks, leg, a, b, lift):
    """Keys the paw's z on the step arc at every frame strictly between frames a and b (its z at a and b keyed by the caller)."""
    for k in range(a + 1, b): tracks.add(F(k), **{leg + "_z": step_arc(lift, k - a, b - a)})


def smooth(u):
    u = min(max(u, 0.0), 1.0); return u * u * (3 - 2 * u)


def harm(phase, amp, n=1, off=0.0):
    """amp * sin(2 pi (n phase - off)): integer n closes every loop."""
    return amp * math.sin(2 * math.pi * (n * phase - off))


def breath(t, period, amp):
    """Breathing: 0 at t = 0, smooth in- and exhale (sin^2 keeps the rest pose as the low point)."""
    return amp * math.sin(math.pi * t / period) ** 2


def _peak(s, at):
    """0..1..0 bump over s in [0, 1] with its top at s = at (sin of a power-warped s)."""
    s = min(max(s, 0.0), 1.0)
    return math.sin(math.pi * s ** (math.log(0.5) / math.log(at))) if 0.0 < at < 1.0 and at != 0.5 else math.sin(math.pi * s)


def paw_cycle(phase, touchdown, duty, sweep, lift, v_off=0.0, v_on=0.0, zpeak=0.5):
    """One paw over a gait cycle. Stance (share `duty` from `touchdown`): from +sweep/2 to -sweep/2, linear in time, so a planted paw
    moves back at the body speed under the in-place cat. Swing: back to front as a cubic Hermite whose end velocities keep v_off of the
    stance speed at lift-off (the paw peels off backwards) and match v_on of it at touchdown (the paw is drawn back before it lands,
    so it meets the ground softly); defaults 0 = eased from rest to rest. `lift` cm at the swing's highest point, at s = zpeak.
    Returns (df, z, stance_s or None, swing_s or None) with s = 0..1 through the phase."""
    u = (phase - touchdown) % 1.0
    if u < duty:
        s = u / duty; return sweep * (0.5 - s), 0.0, s, None
    s = (u - duty) / (1.0 - duty); m = -sweep * (1.0 - duty) / duty         # stance velocity in swing-s units
    p0, p1, m0, m1 = -0.5 * sweep, 0.5 * sweep, v_off * m, v_on * m
    df = ((2 * s ** 3 - 3 * s ** 2 + 1) * p0 + (s ** 3 - 2 * s ** 2 + s) * m0 + (-2 * s ** 3 + 3 * s ** 2) * p1 + (s ** 3 - s ** 2) * m1)
    return df, lift * _peak(s, zpeak), None, s


def _slopes(ts, vs):
    """Monotone cubic (Fritsch-Butland): no overshoot, flat at ends and turning points."""
    n = len(ts); m = [0.0] * n
    if n < 2: return m
    d = [(vs[i + 1] - vs[i]) / (ts[i + 1] - ts[i]) for i in range(n - 1)]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0:
            h0, h1 = ts[i] - ts[i - 1], ts[i + 1] - ts[i]
            m[i] = 3 * (h0 + h1) / ((2 * h1 + h0) / d[i - 1] + (h1 + 2 * h0) / d[i])
    return m


class Tracks:
    """Keys per channel; each channel interpolates over its own keys, so paws, trunk, head and tail are keyed at their own times.
    add(t, pose, **kw) keys the given channels only."""

    def __init__(self, base):
        self.k = {n: {} for n in base}; self.add(0.0, base)

    def add(self, t, pose=None, **kw):
        for n, v in dict(pose or {}, **kw).items():
            if n not in self.k: raise KeyError("unknown channel " + n)
            self.k[n][round(t, 4)] = float(v)
        return self

    def value(self, n, t):
        ks = sorted(self.k[n].items()); ts = [a for a, _ in ks]; vs = [b for _, b in ks]
        if t <= ts[0]: return vs[0]
        if t >= ts[-1]: return vs[-1]
        m = _slopes(ts, vs)
        for i in range(len(ts) - 1):
            if t <= ts[i + 1]:
                h = ts[i + 1] - ts[i]; u = (t - ts[i]) / h
                return ((2 * u ** 3 - 3 * u ** 2 + 1) * vs[i] + (u ** 3 - 2 * u ** 2 + u) * h * m[i] + (-2 * u ** 3 + 3 * u ** 2) * vs[i + 1]
                        + (u ** 3 - u ** 2) * h * m[i + 1])
        return vs[-1]

    def pose(self, t):
        return {n: self.value(n, t) for n in self.k}


class Seq:
    """One exported sequence. frames = intervals (frames + 1 keyed frames, the last at `length`); loop: last pose == first.
    start/end: posture tags of cat_poses.POSES (None = free, e.g. gaits); plants: {leg: [(t0, t1)]} where a paw must stand still
    (in-place gaits: move back at `speed`); overlay: only tail and ears keyed, every other bone at rest (an additive); lift_off:
    seconds where the last paws leave the floor (jumps: stage 3 launches the capsule there)."""

    def __init__(self, name, frames, pose_fn, loop=False, start=None, end=None, plants=None, speed=0.0, overlay=False, group="",
                 lift_off=None):
        self.name, self.frames, self.pose_fn, self.loop, self.lift_off = name, int(frames), pose_fn, loop, lift_off
        self.start, self.end, self.plants, self.speed, self.overlay, self.group = start, end, dict(plants or {}), float(speed), overlay, group

    @property
    def length(self): return self.frames / FPS

    def pose(self, t): return self.pose_fn(min(max(t, 0.0), self.length))

    def frame_pose(self, f): return self.pose(f / FPS)


class Gait(Seq):
    """An in-place gait cycle from footfall data. touchdown: phase of each paw's touchdown (hl at 0); duty: stance share; speed: body
    speed in cm/s (sweep = speed * duty * length); lift: swing height per 'h'/'f'; home: middle of each paw's sweep (x, f); body:
    {channel: (amp, n, off)} added as harm(phase, amp, n, off); base: the pose the gait is built on.
    Paws (per 'h'/'f'): roll = (_ank at touchdown, _ank at lift-off): the stance rolls the foot from one to the other (hind: heel rises
    late, s^2; fore: carpus lifts, smooth), which also lets the paws reach further at both ends; ankle (hind) / wrist (fore) = the
    tuck of _ank in the swing (hock flexed, paw trailing / wrist curled), at tuck_peak of the swing; toe = toe curl in the swing;
    swing_v = (v_off, v_on) of paw_cycle; zpeak = where in the swing the paw is highest. shrug: the scapula of a standing fore leg
    rises (cm, _sld) at mid-stance, the chest sinks between the blades. steady = (pitch, yaw, roll) share of the trunk's oscillation
    the head turns against (the gaze stays level)."""

    def __init__(self, name, frames, speed, duty, touchdown, lift, home, base, body, ankle=25.0, wrist=60.0, toe=30.0, tail_wave=None,
                 roll=None, swing_v=(0.0, 0.0), zpeak=None, tuck_peak=None, shrug=0.0, steady=(0.0, 0.0, 0.0)):
        self.duty, self.touchdown, self.lift, self.home, self.base, self.body = duty, dict(touchdown), dict(lift), dict(home), dict(base), dict(body)
        self.ankle, self.wrist, self.toe, self.tail_wave = ankle, wrist, toe, tail_wave
        self.roll = dict(roll or {"h": (0.0, 0.5 * ankle), "f": (0.0, 0.0)})
        self.swing_v, self.zpeak = tuple(swing_v), dict(zpeak or {"h": 0.5, "f": 0.5})
        self.tuck_peak, self.shrug, self.steady = dict(tuck_peak or {"h": 0.4, "f": 0.45}), shrug, tuple(steady)
        super().__init__(name, frames, self._pose, loop=True, speed=speed, group="gait")
        self.sweep = speed * duty * self.length
        self.plants = {leg: self.stance(leg) for leg in LEGS}

    def stance(self, leg):
        """Stance spans in seconds; a paw that touches down at phase 0 also stands at the loop's last frame (= the first)."""
        a = self.touchdown[leg] * self.length; b = a + self.duty * self.length; L = self.length
        out = [(a, b)] if b <= L else [(a, L), (0.0, b - L)]
        return out + [(L, L)] if a == 0.0 else out

    def _pose(self, t):
        phase = (t / self.length) % 1.0
        P = dict(self.base)
        for leg in LEGS:
            e = leg[0]
            df, z, st, sw = paw_cycle(phase, self.touchdown[leg], self.duty, self.sweep, self.lift[e], self.swing_v[0], self.swing_v[1],
                                      self.zpeak[e])
            x, f = self.home[leg]
            P[leg + "_x"], P[leg + "_f"], P[leg + "_z"] = x, f + df, z
            land, push = self.roll[e]; tuck = self.ankle if e == "h" else self.wrist
            if st is not None:
                P[leg + "_ank"] = self.base[leg + "_ank"] + land + (push - land) * (st * st if e == "h" else smooth(st))
            else:
                P[leg + "_ank"] = self.base[leg + "_ank"] + push + (land - push) * smooth(sw) + tuck * _peak(sw, self.tuck_peak[e])
            P[leg + "_toe"] = self.base[leg + "_toe"] + (0.0 if st is not None else self.toe * _peak(sw, self.tuck_peak[e]))
            if e == "f" and self.shrug:
                u = (phase - self.touchdown[leg]) % 1.0
                P[leg + "_sld"] = self.base[leg + "_sld"] - self.shrug * math.cos(2 * math.pi * (u - 0.5 * self.duty))
        osc = {}
        for ch, (amp, n, off) in self.body.items():
            v = harm(phase, amp, n, off); P[ch] += v; osc[ch] = osc.get(ch, 0.0) + v
        kp, ky, kr = self.steady
        if kp: P["hd_p"] -= kp * sum(osc.get(c, 0.0) * sg for c, sg in (("pel_p", 1), ("sp1_p", 1), ("sp2_p", 1), ("sp3_p", 1),
                                                                          ("nk1_p", -1), ("nk2_p", -1)))
        if ky: P["hd_y"] -= ky * sum(osc.get(c, 0.0) for c in ("pel_y", "sp1_y", "sp2_y", "sp3_y", "nk_y"))
        if kr: P["hd_r"] -= kr * sum(osc.get(c, 0.0) for c in ("pel_r", "sp_r"))
        if self.tail_wave:
            amp, n = self.tail_wave; P["tl_wave"] = amp; P["tl_ph"] = n * phase
        return P


# per-frame change allowed at the end of a jump's take-off (END_FRAMES frames into the flight pose): cm for paw targets and pelvis
# shifts, degrees for angles. The old single-frame lift-off moved a hind paw 7 cm and its toes 30 deg in one frame; the fast
# but continuous push before lift-off peaks at about 14 deg (hind heels, fore wrists) and 3.2 cm (fore paws reaching up)
# per frame.
END_FRAMES, END_MAX_CM, END_MAX_DEG = 6, 4.0, 15.0


def _is_cm(ch): return ch.endswith(("_x", "_f", "_z", "_sld"))


def end_jumps(seq, frames=END_FRAMES):
    """Largest per-frame channel change over the last `frames` frames of seq: (cm, cm channel, deg, deg channel, frame)."""
    cm, deg = (0.0, "", 0), (0.0, "", 0)
    for f in range(seq.frames - frames + 1, seq.frames + 1):
        a, b = seq.frame_pose(f - 1), seq.frame_pose(f)
        for ch in CHANNELS:
            if ch == "tl_ph": continue
            d = abs(b[ch] - a[ch])
            if _is_cm(ch):
                if d > cm[0]: cm = (d, ch, f)
            elif d > deg[0]: deg = (d, ch, f)
    return cm, deg



# smoothness of the trunk, head, ears and tail (round 6, gated for the "social" group, cat_anims): the largest per-frame second
# difference of those channels (paw channels are left out: touchdown and lift-off are sharp by nature, plants and the floor gate them).
# A loop is measured across its seam too. The older sequences reach up to 9 deg (Yawn's head turn), the gaits 1.6.
SMOOTH_MAX_DEG, SMOOTH_MAX_CM = 3.0, 0.3


def body_accel(seq):
    """(deg, channel, frame), (cm, channel, frame): largest |p[f+1] - 2 p[f] + p[f-1]| over the body channels of seq."""
    P = [seq.frame_pose(f) for f in range(seq.frames + 1)]
    if seq.loop: P = [P[-2]] + P + [P[1]]
    deg, cm = (0.0, "", 0), (0.0, "", 0)
    for i in range(1, len(P) - 1):
        for ch in CHANNELS:
            if ch == "tl_ph" or ch[:2] in LEGS: continue
            a = abs(P[i + 1][ch] - 2 * P[i][ch] + P[i - 1][ch]); f = i - 1 if seq.loop else i
            if _is_cm(ch):
                if a > cm[0]: cm = (a, ch, f)
            elif a > deg[0]: deg = (a, ch, f)
    return deg, cm
