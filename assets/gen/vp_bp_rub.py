"""Rubbing round Jodi's legs (round 6). Routine (vp_bp_posture) starts it now and then when the cat rests on the floor near a still
Jodi (VP_RubWant); State RUB: she walks over, then loops round both legs with Jodi on her left (VP_RubPoint, RubWalk montage: body
curved and leaning in, tail up), purring (VP_PurrWant counts RUB), for RUB_TIME_MIN..MAX s, then a head rub (HeadRub montage) and back
to resting. Jodi walking off (RUB_STOP_SPEED), getting far, or an alarm ends it at once. Without the RubWalk / HeadRub sequences in
tools/blender/cat_seqs.py she loops with the plain slow walk and skips the head rub (HAS_RUBWALK / HAS_HEADRUB).
Watch Jodi (every tick from Think): when Jodi last moved (JodiMovedAt), the RubWalk montage stopped once she is no longer rubbing,
and the eyes' pupils (M_VP_CatEye PupilOpen on the dynamic eye instance: VP_PupilOpen, eased; a material without the parameter
ignores it)."""
import math
from bpdsl import G, fn, param, var, K_SYS, E_ACTOR
from vp_expr import X, num, E_CHAR, E_CMC, E_PAWN
from vp_bp_core import montage_ops
from velvetpaws import brain as B
import cat_seqs as CS

E_MID = "/Script/Engine.MaterialInstanceDynamic"
MONTAGES = {m["name"] for m in CS.MONTAGES}
HAS_RUBWALK, HAS_HEADRUB = "RubWalk" in MONTAGES, "HeadRub" in MONTAGES
PUPIL_PARAM = "PupilOpen"
OMEGA = 2.0 * math.pi / B.RUB_PERIOD


def variables():
    F, Bo = "float", "bool"
    return [var("RubT", F, default="0.0"), var("RubEnd", F, default="0.0"), var("RubOn", Bo, default="false"),
            var("LastRub", F, default="-1000.0"), var("JodiMovedAt", F, default="0.0"), var("PupilNow", F, default=num(B.PUPIL_CALM)),
            var("PupilSet", F, default="-1.0")]


def jodi_fwd(x): return x.call(E_ACTOR, "GetActorForwardVector", self=x.var("Jodi"))


def f_start_rub():
    g = G(); x = X(g, "su")
    t0 = x.self_fn("VP_RubPhase", Jodi=x.loc(x.var("Jodi")), Fwd=jodi_fwd(x), Cat=x.loc())
    g.chain("entry", x.setv("State", B.ST_RUB), x.setv("WantPosture", B.P_STAND), x.setv("RubOn", "false"), x.setv("RubEnd", 0.0),
            x.setv("RubT", t0), x.setv("ProgressAt", x.now()))
    return fn("Start Rub", graph=g)


def f_end_rub():
    """Back to resting; Head: the loop ran its time (not cut short), a head rub against her leg first."""
    g = G(); x = X(g, "eu"); bh = x.br("@entry.Head") if HAS_HEADRUB else None
    stop = montage_ops(x, [("stop", "RubWalk", 0.3)]) if HAS_RUBWALK else []
    g.chain("entry", *stop, x.setv("RubOn", "false"), x.setv("State", B.ST_REST), x.setv("RestSince", x.now()), x.setv("LastRub", x.now()),
            x.setv("NextRoutine", x.add(x.now(), B.ROUTINE_MIN)), *([bh] if bh else []))
    if bh:
        g.chain(bh + ":then", *montage_ops(x, [("play", "HeadRub")]), x.setv("BusyUntil", x.add(x.now(), B.L("HeadRub") - B.blend_out("HeadRub"))))
    return fn("End Rub", [param("Head", "bool")], graph=g)


def f_tick_rub():
    g = G(); x = X(g, "tu"); now = x.now
    jl = lambda: x.loc(x.var("Jodi")); dj = lambda: x.dist2d(x.loc(), jl())
    js = x.m("VSize2D", A=x.call(E_ACTOR, "GetVelocity", self=x.var("Jodi")))
    timed_out = x.and_(x.gt(x.var("RubEnd"), 0.0), x.ge(now(), x.var("RubEnd")))
    stop = x.or_(x.var("Alarmed"), x.gt(js, B.RUB_STOP_SPEED), x.gt(dj(), B.RUB_NEAR + 150.0), timed_out,
                 x.gt(x.sub(now(), x.var("ProgressAt")), 20.0))          # never reached her (blocked): give up after 20 s
    bstop = x.br(stop)
    ready = x.and_(x.eqi(x.var("Posture"), B.P_STAND), x.ge(now(), x.var("BusyUntil"))); brd = x.br(ready)
    g.chain("entry", bstop)
    g.chain(bstop + ":then", x.do_self("End Rub", Head=x.and_(timed_out, x.not_(x.var("Alarmed")))))
    g.chain(bstop + ":else", brd)
    g.chain(brd + ":else", x.setv("WantPosture", B.P_STAND), x.do_self("Posture Step"))
    q = x.seq(2); g.chain(brd + ":then", q)
    # (0) close enough: the loop runs (its phase moves on; first time: end time and the RubWalk montage)
    bc = x.br(x.lt(dj(), B.RUB_CLOSE)); bfirst = x.br(x.le(x.var("RubEnd"), 0.0))
    g.chain(q + ":then_0", bc)
    g.chain(bc + ":then", x.setv("RubT", x.add(x.var("RubT"), x.mul("@entry.DT", OMEGA))), x.setv("ProgressAt", now()), bfirst)
    g.chain(bfirst + ":then", x.setv("RubEnd", x.add(now(), x.m("RandomFloatInRange", Min=num(B.RUB_TIME_MIN), Max=num(B.RUB_TIME_MAX)))),
            *(montage_ops(x, [("play", "RubWalk")]) if HAS_RUBWALK else []), x.setv("RubOn", "true"))
    # (1) steer to the loop point: slow, faster only to catch up with it
    tgt = x.self_fn("VP_RubPoint", Jodi=jl(), Fwd=jodi_fwd(x), T=x.var("RubT"))
    lx, ly, _ = x.brk(x.loc()); tx, ty, _ = x.brk(tgt)
    dirv = x.normal(x.vec(x.sub(tx, lx), x.sub(ty, ly), 0.0))
    spd = x.fmin(x.fmin(x.fmax(x.mul(x.dist2d(x.loc(), tgt), 2.0), B.RUB_WALK), B.RUB_SPEED_MAX), x.self_fn("VP_MaxSpeed", Scale=x.scale()))
    cmc = x.var("CharacterMovement", cls=E_CHAR, obj=x.me())
    g.chain(q + ":then_1", x.setv("MaxWalkSpeed", spd, cls=E_CMC, obj=cmc),
            x.do(E_PAWN, "AddMovementInput", self=x.me(), WorldDirection=dirv, ScaleValue="1.0", bForce="false"))
    return fn("Tick Rub", [param("DT", "float")], graph=g)


def f_watch_jodi():
    g = G(); x = X(g, "wj"); q = x.seq(3)
    js = x.m("VSize2D", A=x.call(E_ACTOR, "GetVelocity", self=x.var("Jodi")))
    bm = x.br(x.gt(js, B.RUB_STILL_SPEED))
    bo = x.br(x.and_(x.var("RubOn"), x.nei(x.var("State"), B.ST_RUB)))
    g.chain("entry", q); g.chain(q + ":then_0", bm); g.chain(bm + ":then", x.setv("JodiMovedAt", x.now()))
    g.chain(q + ":then_1", bo)
    g.chain(bo + ":then", *(montage_ops(x, [("stop", "RubWalk", 0.3)]) if HAS_RUBWALK else []), x.setv("RubOn", "false"))
    # pupils: eased towards VP_PupilOpen, written to the eye instance only when it moved noticeably
    pn = x.m("FInterpTo", Current=x.var("PupilNow"), Target=x.self_fn("VP_PupilOpen", State=x.var("State"), Posture=x.var("Posture")),
             DeltaTime=x.var("TickDT"), InterpSpeed=num(B.PUPIL_RATE))
    bw = x.br(x.and_(x.gt(x.abs_(x.sub(x.var("PupilNow"), x.var("PupilSet"))), 0.005), x.call(K_SYS, "IsValid", Object=x.var("UiEye"))))
    g.chain(q + ":then_2", x.setv("PupilNow", pn), bw)
    g.chain(bw + ":then", x.do(E_MID, "SetScalarParameterValue", self=x.var("UiEye"), ParameterName=PUPIL_PARAM, Value=x.var("PupilNow")),
            x.setv("PupilSet", x.var("PupilNow")))
    return fn("Watch Jodi", graph=g)


def functions(opts):
    return [f_start_rub(), f_end_rub(), f_tick_rub(), f_watch_jodi()]
