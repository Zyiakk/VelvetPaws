"""Spots and jumps of BP_VP_Cat (plan Etappe 3, Task 10). Office: spots from DT_VP_OfficeSpots (loaded and checked by vp_bp_home),
weighted choice near Jodi (Follow) or the anchor (Roam). Elsewhere: one trace candidate every 0.25 s (Spot Scan) until a spot is known.
Jumps (E23): turn, montage from its start, LaunchCharacter at brain.LAUNCH (lift-off), landing by the IsFalling edge, Exit section, then
on the spot (up) or on the floor with the pending move (down). Abort: not in the air 0.5 s after lift-off, or 3 s in the air."""
from bpdsl import G, fn, param, var, K_SYS, K_ARR, E_ACTOR
from vp_expr import X, num, VEC, E_CHAR, E_CMC, E_MOVE, E_PAWN
from vp_bp_core import montage_ops
from velvetpaws import brain as B

LAND_TURN_MAX = 1.5      # s after the landing she may still turn to face the spot's open side
WALK_IN_MAX = 4.0        # s for the walk into / out of a walk-in spot


def variables():
    return [var("PoOK", "bool", default="false"), var("JpSum", "float", default="0.0"), var("JpPick", "int", default="-1"), var("JpW", "float", default="0.0"),
            var("SsYaw", "float", default="0.0"), var("SsD", "float", default="0.0"), var("SsHit", VEC), var("SsOK", "bool", default="false"),
            var("SsFloor", "float", default="0.0")]


def arr_get(x, arr, i, out="Item"): return x.call(K_ARR, "Array_Get", out=out, TargetArray=x.var(arr), Index=i)


def f_take_spot():
    g = G(); x = X(g, "ts"); i = "@entry.I"
    g.chain("entry", x.setv("SpotIdx", i), x.setv("SpotLoc", arr_get(x, "SpotsLoc", i)), x.setv("SpotFrom", arr_get(x, "SpotsFrom", i)),
            x.setv("SpotYaw", arr_get(x, "SpotsYaw", i)), x.setv("SpotHeight", arr_get(x, "SpotsHeight", i)),
            x.setv("SpotPosture", arr_get(x, "SpotsPosture", i)), x.setv("SpotRoom", arr_get(x, "SpotsRoom", i)), x.setv("SpotValid", "true"))
    return fn("Take Spot", [param("I", "int")], graph=g)


def f_pick_office_spot():
    """Weighted reservoir choice among the checked spots within Radius of Center (not the one she is on), not left out for now
    (SpotsUntil), fitting her size (VP_SpotFits: height she jumps, a compartment's room), and with no closed door on the way
    (Route Prep once, Route Open per candidate: free when every door is open)."""
    g = G(); x = X(g, "po")
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("SpotsLoc")); fl = x.loop(x.subi(n, 1)); i = "@%s.Index" % fl
    ok = x.and_(arr_get(x, "SpotsOK", i), x.le(x.dist2d(arr_get(x, "SpotsLoc", i), "@entry.Center"), "@entry.Radius"),
                x.not_(x.and_(x.eqi(x.var("State"), B.ST_SPOT), x.eqi(x.var("SpotIdx"), i))),
                x.ge(x.now(), arr_get(x, "SpotsUntil", i)),
                x.self_fn("VP_SpotFits", Height=arr_get(x, "SpotsHeight", i), Room=arr_get(x, "SpotsRoom", i), Scale=x.scale()))
    b = x.br(ok); sw = x.setv("JpW", arr_get(x, "SpotsWeight", i)); ss = x.setv("JpSum", x.add(x.var("JpSum"), x.var("JpW")))
    bp = x.br(x.lt(x.mul(x.m("RandomFloat"), x.var("JpSum")), x.var("JpW")))
    found = x.gei(x.var("JpPick"), 0); bf = x.br(found)
    ro = x.do_self("Route Open", B=arr_get(x, "SpotsWalk", i)); q = x.seq(2); bro = x.br(x.var("PoOK"))
    g.chain("entry", x.do_self("Route Prep"), x.setv("JpSum", 0.0), x.setv("JpPick", -1), fl)
    g.chain(fl, b); g.chain(b + ":then", q); g.chain(q + ":then_0", ro, x.setv("PoOK", "@%s.Open" % ro))
    g.chain(q + ":then_1", bro); g.chain(bro + ":then", sw, ss, bp); g.chain(bp + ":then", x.setv("JpPick", i))
    g.chain(fl + ":Completed", bf); g.chain(bf + ":then", x.do_self("Take Spot", I=x.var("JpPick")), x.ret(Found="true"))
    g.chain(bf + ":else", x.ret(Found="false"))
    return fn("Pick Office Spot", [param("Center", VEC), param("Radius", "float")], [param("Found", "bool")], graph=g)


def f_go_to_spot():
    g = G(); x = X(g, "gs")
    center = x.vsel(x.eqi(x.var("Mode"), B.MODE_FOLLOW), x.loc(x.var("Jodi")), x.var("Anchor"))
    radius = x.sel(x.eqi(x.var("Mode"), B.MODE_FOLLOW), B.FOLLOW_SPOT_R, B.ROAM_RADIUS)
    bo = x.br(x.eqi(x.var("Level"), B.LV_OFFICE)); po = x.do_self("Pick Office Spot", Center=center, Radius=radius)
    bf = x.br("@%s.Found" % po); bv = x.br(x.var("SpotValid"))
    go = lambda: [*x.dbg(B.DBG_WALK), x.do_self("Start Move", Purpose=str(B.GO_SPOT), To=x.var("SpotFrom"))]
    g.chain("entry", *x.dbg(count="DbgTries"), bo); g.chain(bo + ":then", po, bf); g.chain(bf + ":then", *go())
    g.chain(bo + ":else", bv); g.chain(bv + ":then", *go())
    x.then(bf + ":else", x.dbg(B.DBG_NONE_NEAR)); x.then(bv + ":else", x.dbg(B.DBG_NONE_NEAR))
    return fn("Go To Spot", graph=g)


def f_start_jump():
    g = G(); x = X(g, "sj"); hh = x.hh()
    tgt = x.vsel("@entry.Down", x.up(x.var("SpotFrom"), hh), x.up(x.var("SpotLoc"), hh))
    g.chain("entry", x.setv("JumpDown", "@entry.Down"), x.setv("JumpTarget", tgt), x.setv("State", B.ST_JUMP), x.setv("JumpPhase", B.JP_TURN),
            x.setv("WantPosture", B.P_STAND), x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")),
            *x.dbg(x.seli("@entry.Down", B.DBG_DOWN, B.DBG_TURN)))
    return fn("Start Jump", [param("Down", "bool")], graph=g)


def f_leave_spot():
    g = G(); x = X(g, "lv"); g.chain("entry", x.do_self("Start Jump", Down="true"))
    return fn("Leave Spot", graph=g)


def f_abort_jump():
    g = G(); x = X(g, "aj")
    b_os = x.br(x.and_(x.gei(x.var("SpotIdx"), 0), x.lti(x.var("SpotIdx"), B.SPOT_AUTO)))
    g.chain("entry", *montage_ops(x, [("stop", None, 0.2)]), x.setv("Posture", B.P_STAND), x.setv("WantPosture", B.P_STAND),
            x.setv("JumpPhase", B.JP_NONE), x.setv("State", B.ST_REST), x.setv("RestSince", x.now()), x.setv("SpotValid", "false"),
            x.setv("AfterJump", -1), b_os)
    # an office spot she could not jump onto is left out for a while, as after Stuck (Pick Office Spot skips it until then)
    g.chain(b_os + ":then", x.do(K_ARR, "Array_Set", TargetArray=x.var("SpotsUntil"), Index=x.var("SpotIdx"), Item=x.add(x.now(), B.SPOT_DROP_STUCK),
                                 bSizeToFit="false"))
    return fn("Abort Jump", graph=g)


def f_tick_jump():
    g = G(); x = X(g, "tj"); now = x.now; ph = lambda: x.var("JumpPhase")
    cmc = lambda: x.var("CharacterMovement", cls=E_CHAR, obj=x.me())
    def turn_to(yaw):
        cur = x.call(E_ACTOR, "K2_GetActorRotation", self=x.me())
        return x.do(E_ACTOR, "K2_SetActorRotation", self=x.me(), NewRotation=x.m("RInterpTo", Current=cur, Target=x.rot(yaw), DeltaTime="@entry.DT",
                                                                                  InterpSpeed=num(B.TURN_RATE)), bTeleportPhysics="false")
    b_turn = x.br(x.eqi(ph(), B.JP_TURN)); b_take = x.br(x.eqi(ph(), B.JP_TAKEOFF)); b_air = x.br(x.eqi(ph(), B.JP_AIR)); b_land = x.br(x.eqi(ph(), B.JP_LAND))
    b_walk = x.br(x.eqi(ph(), B.JP_WALK))
    g.chain("entry", b_turn); g.chain(b_turn + ":else", b_take); g.chain(b_take + ":else", b_air); g.chain(b_air + ":else", b_land)
    g.chain(b_land + ":else", b_walk)
    # TURN: stand up first (WantPosture forced: a routine pick on the spot must not hold the jump), then face the target
    b_st = x.br(x.nei(x.var("Posture"), B.P_STAND))
    g.chain(b_turn + ":then", b_st); g.chain(b_st + ":then", x.setv("WantPosture", B.P_STAND), x.do_self("Posture Step"))
    yaw_t = x.yaw_to(x.loc(), x.var("JumpTarget")); yaw_c = x.yaw_of(x.call(E_ACTOR, "K2_GetActorRotation", self=x.me()))
    faced = x.lt(x.abs_(x.m("NormalizeAxis", Angle=x.sub(yaw_t, yaw_c))), 10.0)
    b_f = x.br(x.and_(faced, x.ge(now(), x.var("BusyUntil"))))
    b_dn = x.br(x.var("JumpDown"))
    # a walk-in spot (a compartment at floor level): no jump, she walks in (and out) - phase WALK
    b_wi = x.br(x.lt(x.var("SpotHeight"), B.SPOT_MIN))
    g.chain(b_st + ":else", turn_to(x.yaw_to(x.loc(), x.var("JumpTarget"))), b_f); g.chain(b_f + ":then", b_wi)
    g.chain(b_wi + ":then", x.setv("JumpPhase", B.JP_WALK), x.setv("AirSince", now()), *x.dbg(B.DBG_WALK_IN))
    g.chain(b_wi + ":else", b_dn)
    for m, branch in ((B.JUMP_DOWN, ":then"), (B.JUMP_UP, ":else")):
        g.chain(b_dn + branch, *montage_ops(x, [("play", m)]), x.setv("LaunchAt", x.add(now(), B.LAUNCH[m])), x.setv("JumpPhase", B.JP_TAKEOFF),
                *x.dbg(B.DBG_TAKEOFF))
    # TAKEOFF: launch at lift-off
    b_l = x.br(x.ge(now(), x.var("LaunchAt")))
    # under a compartment's board the apex stays low (VP_JumpClear from the spot's room and her size), also on the way down out of it
    room_clear = x.self_fn("VP_JumpClear", Room=x.var("SpotRoom"), Scale=x.scale())
    clear = x.sel(x.var("JumpDown"), x.fmin(B.JUMP_CLEAR_DOWN, room_clear), room_clear)
    gz = x.mul(-1.0, x.call(E_MOVE, "GetGravityZ", self=cmc()))
    vel = x.self_fn("VP_JumpVelocity", From=x.loc(), To=x.var("JumpTarget"), Clear=clear, G=gz)
    la = x.do(E_CHAR, "LaunchCharacter", self=x.me(), LaunchVelocity=vel, bXYOverride="true", bZOverride="true")
    g.chain(b_take + ":then", b_l); g.chain(b_l + ":then", la, x.setv("AirSince", now()), x.setv("WasFalling", "false"), x.setv("JumpPhase", B.JP_AIR),
                                            *x.dbg(B.DBG_AIR, count="DbgJumps"))
    # AIR: landing = falling edge; aborts
    falling = x.call(E_CMC, "IsFalling", self=cmc())
    b_long = x.br(x.gt(x.sub(now(), x.var("AirSince")), B.JUMP_ABORT_AIR)); b_fall = x.br(falling); b_was = x.br(x.var("WasFalling"))
    b_gr = x.br(x.gt(x.sub(now(), x.var("AirSince")), B.JUMP_ABORT_GROUND)); b_dn2 = x.br(x.var("JumpDown"))
    g.chain(b_air + ":then", b_long); g.chain(b_long + ":then", *x.dbg(B.DBG_AIR_LONG), x.do_self("Abort Jump")); g.chain(b_long + ":else", b_fall)
    g.chain(b_fall + ":then", x.setv("WasFalling", "true")); g.chain(b_fall + ":else", b_was)
    g.chain(b_was + ":else", b_gr); g.chain(b_gr + ":then", *x.dbg(B.DBG_NOT_AIRBORNE), x.do_self("Abort Jump"))
    g.chain(b_was + ":then", b_dn2)
    for m, branch in ((B.JUMP_DOWN, ":then"), (B.JUMP_UP, ":else")):
        g.chain(b_dn2 + branch, *montage_ops(x, [("jump", m, B.section(m, "exit"))]), x.setv("BusyUntil", x.add(now(), B.LAND_TIME[m])),
                x.setv("JumpPhase", B.JP_LAND), x.do_self("Cue", Id=str(B.CUE_LAND)))
    # LAND: turn to the spot's yaw (up: she faces the open side), then settle - not before she faces it (at most LAND_TURN_MAX more)
    b_up = x.br(x.not_(x.var("JumpDown"))); q = x.seq(2)
    g.chain(b_land + ":then", q); g.chain(q + ":then_0", b_up); g.chain(b_up + ":then", turn_to(x.var("SpotYaw")))
    yaw_now = x.yaw_of(x.call(E_ACTOR, "K2_GetActorRotation", self=x.me()))
    faced_spot = x.lt(x.abs_(x.m("NormalizeAxis", Angle=x.sub(x.var("SpotYaw"), yaw_now))), 8.0)
    b_done = x.br(x.and_(x.ge(now(), x.var("BusyUntil")),
                         x.or_(x.var("JumpDown"), faced_spot, x.ge(now(), x.add(x.var("BusyUntil"), LAND_TURN_MAX)))))
    b_dn3 = x.br(x.var("JumpDown"))
    _, _, mz = x.brk(x.loc()); _, _, tz = x.brk(x.var("JumpTarget"))
    b_on = x.br(x.lt(x.abs_(x.sub(mz, tz)), 25.0))
    b_aj = x.br(x.gei(x.var("AfterJump"), 0))
    rest = lambda: [x.setv("JumpPhase", B.JP_NONE), x.setv("State", B.ST_REST), x.setv("RestSince", x.now()), x.setv("NextRoutine", x.add(x.now(), B.ROUTINE_MIN))]
    g.chain(q + ":then_1", b_done); g.chain(b_done + ":then", b_dn3)
    g.chain(b_dn3 + ":then", *rest(), b_aj)
    g.chain(b_aj + ":then", x.do_self("Start Move", Purpose=x.var("AfterJump"), To=x.var("Goal")), x.setv("AfterJump", -1))
    g.chain(b_dn3 + ":else", b_on)
    # on the spot: in Roam mode a fresh rest before the next roam target (else Tick Spot would leave at once when RoamNext is past)
    roam_rest = x.add(x.now(), x.m("RandomFloatInRange", Min=num(B.ROAM_REST_MIN), Max=num(B.ROAM_REST_MAX)))
    stay = x.add(x.now(), x.self_fn("VP_StayTime", Lo=x.var("StayMin"), Hi=x.var("StayMax"), R=x.m("RandomFloat")))
    g.chain(b_on + ":then", x.setv("JumpPhase", B.JP_NONE), x.setv("State", B.ST_SPOT), x.setv("RestSince", x.now()),
            x.setv("WantPosture", x.var("SpotPosture")), x.setv("NextRoutine", x.add(x.now(), B.ROUTINE_MIN)), x.setv("RoamNext", roam_rest),
            x.setv("StayUntil", stay), *x.dbg(B.DBG_ON_SPOT))
    g.chain(b_on + ":else", *rest(), x.setv("SpotValid", "false"), *x.dbg(B.DBG_OFF_SPOT))
    # WALK (walk-in spot): straight to the target at a slow walk; there (or after WALK_IN_MAX) as after a landing: up = LAND (turn,
    # settle on the spot), down = on the floor with the pending move
    dist_t = x.dist2d(x.loc(), x.var("JumpTarget"))
    b_at = x.br(x.or_(x.lt(dist_t, 8.0), x.gt(x.sub(now(), x.var("AirSince")), WALK_IN_MAX))); b_dn4 = x.br(x.var("JumpDown"))
    lx, ly, _ = x.brk(x.loc()); tx, ty, _ = x.brk(x.var("JumpTarget"))
    dirv = x.normal(x.vec(x.sub(tx, lx), x.sub(ty, ly), 0.0))
    sw = x.setv("MaxWalkSpeed", x.fmin(B.WALK_ANIM, x.self_fn("VP_MaxSpeed", Scale=x.scale())), cls=E_CMC, obj=cmc())
    mv = x.do(E_PAWN, "AddMovementInput", self=x.me(), WorldDirection=dirv, ScaleValue="1.0", bForce="false")
    b_aj2 = x.br(x.gei(x.var("AfterJump"), 0))
    g.chain(b_walk + ":then", b_at); g.chain(b_at + ":else", sw, mv); g.chain(b_at + ":then", b_dn4)
    g.chain(b_dn4 + ":else", x.setv("BusyUntil", now()), x.setv("JumpPhase", B.JP_LAND))
    g.chain(b_dn4 + ":then", *rest(), b_aj2)
    g.chain(b_aj2 + ":then", x.do_self("Start Move", Purpose=x.var("AfterJump"), To=x.var("Goal")), x.setv("AfterJump", -1))
    return fn("Tick Jump", [param("DT", "float")], graph=g)


def f_tick_spot():
    """Leaves when Follow needs her (Jodi farther than FOLLOW_START) or her stay is over (StayUntil, from the AltUI stay times; not in
    Wait, where she stays); alarmed on a low spot: down and flee, on a high one: sits and watches.
    The routine only while she is still on the spot (not on the tick that starts the jump down)."""
    g = G(); x = X(g, "tsp"); q = x.seq(2)
    leave_f = x.and_(x.eqi(x.var("Mode"), B.MODE_FOLLOW), x.gt(x.dist2d(x.loc(), x.loc(x.var("Jodi"))), B.FOLLOW_START), x.not_(x.var("Alarmed")))
    leave_r = x.and_(x.nei(x.var("Mode"), B.MODE_WAIT), x.ge(x.now(), x.var("StayUntil")), x.not_(x.var("Alarmed")))
    bf = x.br(leave_f); brm = x.br(leave_r)
    bs = x.br(x.eqi(x.var("State"), B.ST_SPOT)); ba = x.br(x.var("Alarmed")); blow = x.br(x.lt(x.var("SpotHeight"), B.HIGH_SPOT))
    g.chain("entry", q)
    g.chain(q + ":then_0", bf)
    g.chain(bf + ":then", x.setv("AfterJump", B.GO_FOLLOW), x.setv("Goal", x.self_fn("VP_FollowPoint", Jodi=x.loc(x.var("Jodi")), Cat=x.loc())),
            x.do_self("Start Jump", Down="true"))
    g.chain(bf + ":else", brm); g.chain(brm + ":then", x.setv("AfterJump", -1), x.do_self("Start Jump", Down="true"))
    g.chain(q + ":then_1", bs); g.chain(bs + ":then", ba); g.chain(ba + ":then", blow)
    # low spot: Flee with CbFromSpot sets the flee goal and jumps down through Start Move's spot branch (flight starts on landing)
    g.chain(blow + ":then", x.setv("CbFromSpot", "true"), x.do_self("Flee"))
    g.chain(blow + ":else", x.setv("WantPosture", B.P_SIT), x.do_self("Posture Step"))     # high enough: watches from up there
    g.chain(ba + ":else", x.do_self("Rest Routine"))
    return fn("Tick Spot", [param("DT", "float")], graph=g)


def f_probe_spot():
    """One trace candidate (E11): 80-400 cm in a random direction, flat (4 corners within 3 cm), 35-150 cm above her floor, 40 cm free
    above, no pawn, a floor take-off point 18 + 45 cm back towards her, and a clear line for the jump."""
    g = G(); x = X(g, "ps")
    lx, ly, lz = x.brk(x.loc())
    sf = x.setv("SsFloor", x.sub(lz, x.hh()))
    sy = x.setv("SsYaw", x.m("RandomFloatInRange", Min="0.0", Max="360.0"))
    sd = x.setv("SsD", x.m("RandomFloatInRange", Min=num(B.SPOT_SCAN_MIN), Max=num(B.SPOT_SCAN_MAX)))
    dx, dy = x.m("DegCos", A=x.var("SsYaw")), x.m("DegSin", A=x.var("SsYaw"))
    cx, cy = x.add(lx, x.mul(dx, x.var("SsD"))), x.add(ly, x.mul(dy, x.var("SsD")))
    t, hit, hr = x.trace(x.vec(cx, cy, x.add(x.var("SsFloor"), B.JUMP_MAX + 20.0)), x.vec(cx, cy, x.add(x.var("SsFloor"), 20.0)), ignore=x.var("Jodi"))
    h = x.hit(hr)
    _, _, nzz = x.brk("@%s.ImpactNormal" % h); _, _, hz = x.brk("@%s.Location" % h)
    height = x.sub(hz, x.var("SsFloor"))
    g.cast("ps_pawn", E_PAWN, "@%s.HitActor" % h, pure=True)
    ok1 = x.and_(hit, x.gt(nzz, 0.95), x.ge(height, B.SPOT_MIN), x.le(height, B.JUMP_MAX),
                 x.not_(x.call(K_SYS, "IsValid", Object="@ps_pawn.AsPawn")))
    b1 = x.br(ok1); s_hit = x.setv("SsHit", "@%s.Location" % h); s_ok = x.setv("SsOK", "true")
    g.chain("entry", sf, sy, sd, t, b1); g.chain(b1 + ":then", s_hit, s_ok); prev = s_ok
    # 4 corners
    for ox, oy in ((B.SPOT_HALF, 0), (-B.SPOT_HALF, 0), (0, B.SPOT_HALF), (0, -B.SPOT_HALF)):
        c = x.vadd(x.var("SsHit"), x.vec(ox, oy, 0.0))
        tk, hk, hrk = x.trace(x.up(c, 30.0), x.up(c, -10.0), ignore=x.var("Jodi")); hb = x.hit(hrk); _, _, zk = x.brk("@%s.Location" % hb)
        _, _, z0 = x.brk(x.var("SsHit"))
        sk = x.setv("SsOK", x.and_(x.var("SsOK"), hk, x.le(x.abs_(x.sub(zk, z0)), B.SPOT_FLAT)))
        g.chain(prev, tk, sk); prev = sk
    # headroom
    tu, hu, _ = x.trace(x.up(x.var("SsHit"), 5.0), x.up(x.var("SsHit"), B.SPOT_HEADROOM), ignore=x.var("Jodi"))
    su = x.setv("SsOK", x.and_(x.var("SsOK"), x.not_(hu))); g.chain(prev, tu, su)
    # take-off point and jump line
    back = x.vec(x.mul(dx, -(B.SPOT_HALF + B.JUMP_FROM)), x.mul(dy, -(B.SPOT_HALF + B.JUMP_FROM)), 0.0)
    hx, hy, _ = x.brk(x.var("SsHit"))
    f = x.vadd(x.vec(hx, hy, x.var("SsFloor")), back)
    fa = x.do_self("Floor At", P=f); _, _, fz = x.brk("@%s.Loc" % fa)
    lc = x.do_self("Line Clear", A=x.up("@%s.Loc" % fa, x.add(x.hh(), 25.0)), B=x.up(x.var("SsHit"), x.add(x.hh(), 20.0)))
    b2 = x.br(x.and_(x.var("SsOK"), "@%s.Hit" % fa, x.le(x.abs_(x.sub(fz, x.var("SsFloor"))), 10.0), "@%s.Clear" % lc))
    g.chain(su, fa, lc, b2)
    _, _, sz = x.brk(x.var("SsHit"))
    g.chain(b2 + ":then", x.setv("SpotLoc", x.var("SsHit")), x.setv("SpotFrom", "@%s.Loc" % fa), x.setv("SpotHeight", x.sub(sz, fz)),
            x.setv("SpotYaw", x.var("SsYaw")), x.setv("SpotPosture", B.P_LIE), x.setv("SpotIdx", B.SPOT_AUTO), x.setv("SpotValid", "true"))
    return fn("Probe Spot", graph=g)


def events(g, x):
    """Spot Scan (looping timer from Start Timers, missions only): forget a far spot, probe while none is known and she is not jumping."""
    g.custom("jp_scan", "Spot Scan")
    # not while she walks to the known spot (GO_SPOT): SpotLoc/SpotFrom must stay what Arrive jumps onto
    spot_walk = lambda: x.and_(x.eqi(x.var("State"), B.ST_MOVE), x.eqi(x.var("Purpose"), B.GO_SPOT))
    far = x.and_(x.var("SpotValid"), x.gt(x.dist2d(x.loc(), x.var("SpotLoc")), B.SPOT_KEEP), x.nei(x.var("State"), B.ST_SPOT),
                 x.nei(x.var("State"), B.ST_JUMP), x.not_(spot_walk()))
    bfar = x.br(far)
    want = x.and_(x.var("Placed"), x.not_(x.var("SpotValid")), x.or_(x.eqi(x.var("State"), B.ST_REST), x.eqi(x.var("State"), B.ST_MOVE)),
                  x.not_(spot_walk()))
    bw = x.br(want); q = x.seq(2)
    g.chain("jp_scan", q); g.chain(q + ":then_0", bfar); g.chain(bfar + ":then", x.setv("SpotValid", "false"))
    g.chain(q + ":then_1", bw); g.chain(bw + ":then", x.do_self("Probe Spot"))


def functions(opts):
    return [f_take_spot(), f_pick_office_spot(), f_go_to_spot(), f_start_jump(), f_leave_spot(), f_abort_jump(), f_tick_jump(), f_tick_spot(),
            f_probe_spot()]
