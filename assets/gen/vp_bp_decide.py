"""Pure decision functions of BP_VP_Cat (VP_*), built from the constants of scripts/velvetpaws/brain.py with the same formulas as its
reference functions; scripts/test_behaviour_kit.py calls them in the kit with brain.kit_cases()."""
from bpdsl import G, fn, param, K_STR
from vp_expr import X, num
from velvetpaws import brain as B



def variables(): return []


def _norm2d(x, ax, ay, fx, fy):
    l = x.sqrt(x.add(x.mul(ax, ax), x.mul(ay, ay))); ok = x.gt(l, 1e-3); ls = x.fmax(l, 1e-3)
    return x.sel(ok, x.div(ax, ls), fx), x.sel(ok, x.div(ay, ls), fy)


def follow_speed(x, d, js):
    v1 = x.maprc(d, B.FOLLOW_STOP, B.FOLLOW_RUN_AT, B.FOLLOW_MIN_SPEED, B.MAX_SPEED)
    v2 = x.sel(x.gt(d, B.FOLLOW_MATCH_AT), x.fmax(v1, x.mul(js, B.FOLLOW_MATCH)), v1)
    return x.sel(x.le(d, B.FOLLOW_STOP), 0.0, x.fmin(v2, B.MAX_SPEED))


def follow_point(x, j, c):
    jx, jy, jz = x.brk(j); cx, cy, cz = x.brk(c)
    dx, dy = _norm2d(x, x.sub(cx, jx), x.sub(cy, jy), -1.0, 0.0)
    return x.vec(x.add(jx, x.mul(dx, B.FOLLOW_KEEP)), x.add(jy, x.mul(dy, B.FOLLOW_KEEP)), cz)


def anim_speed(x, v, s): return x.fmin(x.div(v, s), B.RUN_ANIM)


def max_speed(x, s): return x.mul(s, B.MAX_SPEED)


def jump_velocity(x, f, t, clear, g):
    fx, fy, fz = x.brk(f); tx, ty, tz = x.brk(t)
    dz = x.sub(tz, fz); h = x.add(x.fmax(dz, 0.0), clear)
    vz = x.sqrt(x.mul(x.mul(2.0, g), h)); T = x.add(x.div(vz, g), x.sqrt(x.div(x.mul(2.0, x.sub(h, dz)), g)))
    return x.vec(x.div(x.sub(tx, fx), T), x.div(x.sub(ty, fy), T), vz)


def posture_next(x, p, w): return x.subi(x.addi(p, x.b2i(x.gti(w, p))), x.b2i(x.lti(w, p)))


def pick_routine(x, p, r, rest, ok, on):
    allowed = {B.ACT_SPOT: x.and_(ok, x.not_(on)), B.ACT_STRETCH: x.not_(on), B.ACT_STAND: x.not_(on),
               B.ACT_LIE: x.ge(rest, B.LIE_AFTER), B.ACT_SLEEP: x.ge(rest, B.SLEEP_AFTER)}
    def table(rows):
        out = str(B.ACT_NONE); acc = float(sum(w for _, w in rows))
        for act, w in reversed(rows):
            a = x.seli(allowed[act], act, B.ACT_NONE) if act in allowed else str(act)
            out = x.seli(x.lt(r, acc), a, out); acc -= w
        return out
    out = str(B.ACT_NONE)
    for posture in sorted(B.ROUTINE, reverse=True):
        out = x.seli(x.eqi(p, posture), table(B.ROUTINE[posture]), out)
    return out


def teleport_candidate(x, i, j, yaw):
    A = B.TELEPORT_ANGLES; a = num(A[-1])
    for k in range(len(A) - 2, -1, -1): a = x.sel(x.eqi(i, k), A[k], a)
    total = x.add(x.add(yaw, 180.0), a); jx, jy, jz = x.brk(j)
    return x.vec(x.add(jx, x.mul(x.m("DegCos", A=total), B.TELEPORT_DIST)), x.add(jy, x.mul(x.m("DegSin", A=total), B.TELEPORT_DIST)), jz)


def out_of_view(x, p, cam, fwd): return x.lt(x.dot(x.normal(x.vsub(p, cam)), fwd), B.VIEW_COS)


def flee_goal(x, j, e):
    jx, jy, jz = x.brk(j); ex, ey, ez = x.brk(e)
    dx, dy = _norm2d(x, x.sub(jx, ex), x.sub(jy, ey), 1.0, 0.0)
    return x.vec(x.add(jx, x.mul(dx, B.FLEE_BEHIND)), x.add(jy, x.mul(dy, B.FLEE_BEHIND)), jz)


def level_kind(x, name):
    # EqualEqual_StriStri: case-insensitive like the reference (EqualEqual_StrStr compares case-sensitively in 4.27, checked in the kit)
    eq = lambda s: x.call(K_STR, "EqualEqual_StriStri", A=name, B=s)
    menu = x.or_(*[eq(m) for m in B.MENU_LEVELS])
    return x.seli(eq(B.OFFICE), B.LV_OFFICE, x.seli(menu, B.LV_NONE, B.LV_MISSION))


def next_hop(x, nxt, b):
    mul = lambda a, k: x.m("Multiply_IntInt", A=a, B=str(k))
    def digit(i):                                   # '0'..'9' -> 0..9, 'A'..'Z' -> 10..35
        c = x.call(K_STR, "GetCharacterAsNumber", SourceString=nxt, Index=i)
        return x.subi(x.subi(c, 48), mul(x.b2i(x.gei(c, 65)), 7))
    i0 = mul(b, 2)
    v = x.addi(mul(digit(i0), 36), digit(x.addi(i0, 1)))
    return x.seli(x.eqi(v, B.HOP_NONE), -1, v)


def meow_interval(x, rate, r):
    k = x.m("FClamp", Value=rate, Min="0.0", Max="1.0")
    return x.mul(x.mul(B.MEOW_SLOW, x.m("Exp", A=x.mul(k, B.MEOW_LN))), x.add(0.5, r))


def sound_pitch(x, s, r):
    return x.mul(x.sqrt(x.div(1.0, s)), x.add(1.0, x.mul(B.PITCH_VAR, x.sub(x.mul(2.0, r), 1.0))))


def next_variant(x, last, r, n):
    skip = x.and_(x.gei(last, 0), x.lti(last, n), x.gti(n, 1))
    m = x.subi(n, x.b2i(skip))
    pick = x.m("Min", A=x.m("FFloor", A=x.mul(r, x.i2f(m))), B=x.subi(m, 1))
    return x.addi(pick, x.b2i(x.and_(skip, x.gei(pick, last))))


def purr_want(x, st, p, al, d, pu):
    resting = x.and_(x.or_(x.and_(x.or_(x.eqi(st, B.ST_REST), x.eqi(st, B.ST_SPOT)), x.gei(p, B.P_SIT)), x.eqi(st, B.ST_RUB)), x.not_(al))
    return x.and_(resting, x.lt(d, x.sel(pu, B.PURR_STOP, B.PURR_START)))


def _per_pattern(x, p, value):
    """value(index) for the index p (brain.PATTERNS), the solid pattern's for anything else."""
    out = num(value(0))
    for k in sorted(B.PATTERNS, reverse=True): out = x.sel(x.eqi(p, k), value(k), out)
    return out


def pattern_weights(x, p):
    ch = [_per_pattern(x, p, lambda k, c=c: B.PATTERNS[k][0][c]) for c in range(4)]
    return x.m("MakeColor", R=ch[0], G=ch[1], B=ch[2], A=ch[3])


def white_marks(x, p): return _per_pattern(x, p, lambda k: B.PATTERNS[k][1])


def want_here(x, a, lv, ta): return x.and_(a, x.or_(x.eqi(lv, B.LV_OFFICE), x.and_(x.eqi(lv, B.LV_MISSION), ta)))


def spot_fits(x, h, room, s):
    reach = x.mul(B.JUMP_MAX, x.fmin(1.0, x.div(s, B.KITTEN_FULL)))
    return x.and_(x.le(h, reach), x.ge(room, x.add(x.mul(2.0 * B.CAPSULE_HH, s), B.ROOM_MARGIN)))


def jump_clear(x, room, s):
    return x.fmax(B.JUMP_CLEAR_MIN, x.fmin(B.JUMP_CLEAR_UP, x.sub(x.sub(room, x.mul(2.0 * B.CAPSULE_HH, s)), B.ROOM_MARGIN)))


def stay_time(x, lo, hi, r):
    a = x.fmin(lo, hi); b = x.fmax(lo, hi)
    return x.mul(60.0, x.add(a, x.mul(x.sub(b, a), r)))


def rub_want(x, d, js, still, since, p, r):
    return x.and_(x.le(d, B.RUB_NEAR), x.le(js, B.RUB_STILL_SPEED), x.ge(still, B.RUB_STILL), x.ge(since, B.RUB_GAP), x.lti(p, B.P_SIT + 1),
                  x.lt(r, B.RUB_CHANCE))


def _fr(x, fwd):
    fx, fy, _ = x.brk(fwd); fx, fy = _norm2d(x, fx, fy, 1.0, 0.0)
    return fx, fy, x.mul(-1.0, fy), fx                                    # forward, right = forward turned +90 degrees


def rub_point(x, j, fwd, t):
    jx, jy, jz = x.brk(j); fx, fy, rx, ry = _fr(x, fwd)
    c = x.m("Cos", A=t); s = x.m("Sin", A=t)
    a = x.mul(B.RUB_A, c); b = x.mul(B.RUB_B, s)
    return x.vec(x.add(jx, x.add(x.mul(a, rx), x.mul(b, fx))), x.add(jy, x.add(x.mul(a, ry), x.mul(b, fy))), jz)


def rub_phase(x, j, fwd, cat):
    jx, jy, _ = x.brk(j); cx, cy, _ = x.brk(cat); fx, fy, rx, ry = _fr(x, fwd)
    dx, dy = x.sub(cx, jx), x.sub(cy, jy)
    return x.m("Atan2", Y=x.div(x.add(x.mul(dx, fx), x.mul(dy, fy)), B.RUB_B), X=x.div(x.add(x.mul(dx, rx), x.mul(dy, ry)), B.RUB_A))


def pupil_open(x, st, p): return x.sel(x.or_(x.eqi(st, B.ST_RUB), x.gei(p, B.P_LIE)), B.PUPIL_WIDE, B.PUPIL_CALM)


BODIES = {"VP_FollowSpeed": follow_speed, "VP_FollowPoint": follow_point, "VP_AnimSpeed": anim_speed, "VP_MaxSpeed": max_speed,
          "VP_JumpVelocity": jump_velocity, "VP_PostureNext": posture_next, "VP_PickRoutine": pick_routine,
          "VP_TeleportCandidate": teleport_candidate, "VP_OutOfView": out_of_view, "VP_FleeGoal": flee_goal, "VP_LevelKind": level_kind,
          "VP_NextHop": next_hop, "VP_MeowInterval": meow_interval, "VP_SoundPitch": sound_pitch,
          "VP_NextVariant": next_variant, "VP_PurrWant": purr_want,
          "VP_PatternWeights": pattern_weights, "VP_WhiteMarks": white_marks, "VP_WantHere": want_here,
          "VP_SpotFits": spot_fits, "VP_JumpClear": jump_clear, "VP_StayTime": stay_time, "VP_RubWant": rub_want, "VP_RubPoint": rub_point,
          "VP_RubPhase": rub_phase, "VP_PupilOpen": pupil_open}


def functions(opts):
    out = []
    for name, (_, params, otype) in B.BP_FUNCS.items():
        g = G(); x = X(g, "d")
        res = BODIES[name](x, *["@entry." + p for p, _ in params])
        g.chain("entry", x.ret(Out=res))
        out.append(fn(name, [param(p, t) for p, t in params], [param("Out", otype)], graph=g, pure=True))
    return out
