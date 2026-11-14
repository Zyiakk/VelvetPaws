"""Postures, actions and the daily routine of BP_VP_Cat (plan Etappe 3, Task 8). A posture changes one step at a time along
stand <-> sit <-> lie <-> sleep (brain.TRANSITIONS); a step plays its montage op and blocks further steps until BusyUntil; an Exit that
ends in the next lower posture leaves an AfterOp (start that montage at Loop) due at BusyUntil. Actions need their posture and come back
to it the same way. Routine: every 6-14 s one weighted choice (VP_PickRoutine). The overlay alpha (1 awake, 0 asleep) follows Posture
in vp_bp_core.f_update_anim."""
from bpdsl import G, fn, param, var, E_ACTOR
from vp_expr import X, num
from vp_bp_core import montage_ops
from velvetpaws import brain as B


def variables():
    return [var("PsNext", "int", default="0"), var("PsR", "float", default="0.0"), var("PsAct", "int", default="0")]


def f_posture_step():
    g = G(); x = X(g, "ps")
    bb = x.br(x.lt(x.now(), x.var("BusyUntil"))); sq = x.seq(2)
    g.chain("entry", bb); g.chain(bb + ":else", sq)
    prev = sq + ":then_0"
    for code, ops in B.AFTER_OPS.items():
        if code == B.AFTER_NONE: continue
        b = x.br(x.eqi(x.var("AfterOp"), code)); g.chain(prev, b)
        g.chain(b + ":then", *montage_ops(x, ops), x.setv("AfterOp", B.AFTER_NONE)); prev = b + ":else"
    bn = x.br(x.nei(x.var("Posture"), x.var("WantPosture")))
    sn = x.setv("PsNext", x.self_fn("VP_PostureNext", P=x.var("Posture"), Want=x.var("WantPosture")))
    g.chain(sq + ":then_1", bn); g.chain(bn + ":then", sn); prev = sn
    for (p, q), (ops, t, after) in B.TRANSITIONS.items():
        b = x.br(x.and_(x.eqi(x.var("Posture"), p), x.eqi(x.var("PsNext"), q))); g.chain(prev, b)
        g.chain(b + ":then", *montage_ops(x, ops), x.setv("BusyUntil", x.add(x.now(), t)), x.setv("AfterOp", after), x.setv("Posture", q))
        prev = b + ":else"
    return fn("Posture Step", graph=g)


def f_snap_posture():
    """Straight into posture P (level start, after a teleport): all montages stopped, then the posture's montage from its Loop."""
    g = G(); x = X(g, "sp"); s = x.seq(2); g.chain("entry", s)
    stop = montage_ops(x, [("stop", None, 0.0)])[0]; g.chain(s + ":then_0", stop); prev = stop
    for p, m in B.POSTURE_MONTAGE.items():
        b = x.br(x.eqi("@entry.P", p)); g.chain(prev, b)
        g.chain(b + ":then", *montage_ops(x, [("play", m), ("jump", m, B.section(m, "loop"))])); prev = b + ":else"
    g.chain(s + ":then_1", x.setv("Posture", "@entry.P"), x.setv("WantPosture", "@entry.P"), x.setv("BusyUntil", "0.0"),
            x.setv("AfterOp", B.AFTER_NONE))
    return fn("Snap Posture", [param("P", "int")], graph=g)


def f_do_action():
    """Act's montage (brain.ACTIONS). Its posture is not checked again: VP_PickRoutine offers an action only in that posture."""
    g = G(); x = X(g, "da"); prev = "entry"
    for act, (m, need, t, after) in B.ACTIONS.items():
        b = x.br(x.eqi("@entry.Act", act)); g.chain(prev, b)
        cue = [x.do_self("Cue", Id=str(B.ACT_CUE[act]))] if act in B.ACT_CUE else []
        g.chain(b + ":then", *montage_ops(x, [("play", m)]), x.setv("BusyUntil", x.add(x.now(), t)), x.setv("AfterOp", after), *cue)
        prev = b + ":else"
    return fn("Do Action", [param("Act", "int")], graph=g)


def f_routine():
    g = G(); x = X(g, "rt"); now = x.now()
    due = x.and_(x.ge(now, x.var("NextRoutine")), x.ge(x.now(), x.var("BusyUntil")), x.eqi(x.var("Posture"), x.var("WantPosture")))
    b = x.br(due)
    s1 = x.setv("NextRoutine", x.add(x.now(), x.m("RandomFloatInRange", Min=num(B.ROUTINE_MIN), Max=num(B.ROUTINE_MAX))))
    s2 = x.setv("PsR", x.m("RandomFloatInRange", Min="0.0", Max="100.0"))
    # office: any checked spot counts (Go To Spot picks one), also after a floor start, Stuck or Abort Jump cleared SpotValid
    spot_ok = x.and_(x.or_(x.var("SpotValid"), x.var("OfficeSpotsOK")), x.nei(x.var("Mode"), B.MODE_WAIT), x.not_(x.var("Alarmed")))
    s3 = x.setv("PsAct", x.self_fn("VP_PickRoutine", Posture=x.var("Posture"), R=x.var("PsR"), Rest=x.sub(x.now(), x.var("RestSince")),
                                   SpotOK=spot_ok, OnSpot=x.eqi(x.var("State"), B.ST_SPOT)))
    steps = [s1, s2, s3] + x.dbg(count="DbgPicks")
    # rubbing round Jodi's legs first (vp_bp_rub): resting on the floor, not in Wait, Jodi near and still for a while, now and then
    jl = x.loc(x.var("Jodi"))
    rub = x.and_(x.eqi(x.var("State"), B.ST_REST), x.nei(x.var("Mode"), B.MODE_WAIT), x.not_(x.var("Alarmed")),
                 x.self_fn("VP_RubWant", Dist=x.dist2d(x.loc(), jl), JodiSpeed=x.m("VSize2D", A=x.call(E_ACTOR, "GetVelocity", self=x.var("Jodi"))),
                           StillFor=x.sub(x.now(), x.var("JodiMovedAt")), SinceRub=x.sub(x.now(), x.var("LastRub")), Posture=x.var("Posture"),
                           R=x.m("RandomFloatInRange", Min="0.0", Max="100.0")))
    brub = x.br(rub)
    g.chain("entry", b); g.chain(b + ":then", s1, brub); g.chain(brub + ":then", x.do_self("Start Rub")); g.chain(brub + ":else", *steps[1:])
    prev = steps[-1]
    for act, post in B.ACT_POSTURE.items():
        c = x.br(x.eqi(x.var("PsAct"), act)); g.chain(prev, c); g.chain(c + ":then", x.setv("WantPosture", post)); prev = c + ":else"
    for act in B.ACTIONS:
        c = x.br(x.eqi(x.var("PsAct"), act)); g.chain(prev, c); g.chain(c + ":then", x.do_self("Do Action", Act=str(act))); prev = c + ":else"
    c = x.br(x.eqi(x.var("PsAct"), B.ACT_SPOT)); g.chain(prev, c); g.chain(c + ":then", x.do_self("Go To Spot"))
    return fn("Routine", graph=g)


def f_rest_routine():
    g = G(); x = X(g, "rr"); g.chain("entry", x.do_self("Posture Step"), x.do_self("Routine"))
    return fn("Rest Routine", graph=g)


def functions(opts):
    return [f_posture_step(), f_snap_posture(), f_do_action(), f_routine(), f_rest_routine()]
