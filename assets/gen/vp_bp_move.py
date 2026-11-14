"""Movement of BP_VP_Cat (plan Etappe 3, Task 9): paths (office map: nearest visible walk point, next-hop strings; NavMesh:
FindPathToLocationSynchronously; else straight), walking the waypoints with AddMovementInput, arrival per purpose, stuck after 3 s
without 10 cm progress, teleport out of sight behind Jodi, modes Follow / Wait / Roam, recall, the keys (RecallKey; F6/F8/F9/F10 only
while gen_velvetpaws.TEST_KEYS). Speed: MaxWalkSpeed is set every walking tick to min(purpose speed, VP_MaxSpeed(Size/100)) (E1, E24);
the class default (300) is never relied on. A move ends in Arrive or Stuck, both reset RestSince (lie/sleep count from there)."""
from bpdsl import G, fn, param, var, K_SYS, K_GS, K_ARR, E_ACTOR
from vp_expr import X, num, VEC, E_CHAR, E_CMC, E_PC, E_PCM, E_PAWN, NAV, NAVPATH, K_IN, TRACE_CAM
from velvetpaws import brain as B


def variables():
    I, F, Bo = "int", "float", "bool"
    return [var("MvBest", F, default="0.0"), var("MvIdx", I, default="-1"), var("MvA", I, default="-1"), var("MvB", I, default="-1"),
            var("MvDone", Bo, default="false"), var("MvNew", VEC), var("MvPath", "object:" + NAVPATH), var("MvP", VEC),
            var("MvCam", VEC), var("MvFwd", VEC), var("MvYaw", F, default="0.0"), var("MvShut", Bo, default="false"),
            var("WpDoor", I, container="array"), var("RoShut", Bo, default="false"), var("RoFrom", I, default="-1"), var("RoCur", I, default="-1"),
            var("RoRes", Bo, default="true")]


def jodi_loc(x): return x.loc(x.var("Jodi"))


def purpose_is(x, *ps): return x.or_(*[x.eqi(x.var("Purpose"), p) for p in ps])


def moving(x): return x.eqi(x.var("State"), B.ST_MOVE)


def f_start_move():
    g = G(); x = X(g, "sm")
    bs = x.br(x.eqi(x.var("State"), B.ST_SPOT)); bj = x.br(x.eqi(x.var("State"), B.ST_JUMP))
    g.chain("entry", bs)
    g.chain(bs + ":then", x.setv("AfterJump", "@entry.Purpose"), x.setv("Goal", "@entry.To"), x.do_self("Leave Spot"))
    g.chain(bs + ":else", bj)
    g.chain(bj + ":then", x.setv("AfterJump", "@entry.Purpose"), x.setv("Goal", "@entry.To"))
    g.chain(bj + ":else", x.setv("State", B.ST_MOVE), x.setv("Purpose", "@entry.Purpose"), x.setv("Goal", "@entry.To"),
            x.setv("WantPosture", B.P_STAND), x.setv("RepathAt", x.add(x.now(), B.REPATH)), x.setv("ProgressAt", x.now()),
            x.do_self("Make Path", To="@entry.To"))
    return fn("Start Move", [param("Purpose", "int"), param("To", VEC)], graph=g)


def f_make_path():
    g = G(); x = X(g, "mp")
    clr = x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints"))
    office = x.and_(x.eqi(x.var("Level"), B.LV_OFFICE), x.gti(x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc")), 0))
    bo = x.br(office); bn = x.br(x.var("HasNav"))
    fp = x.do(NAV, "FindPathToLocationSynchronously", PathStart=x.loc(), PathEnd="@entry.To")
    sp = x.setv("MvPath", "@%s.ReturnValue" % fp)
    pts = lambda: x.var("PathPoints", cls=NAVPATH, obj=x.var("MvPath"))
    ok = x.and_(x.call(K_SYS, "IsValid", Object=x.var("MvPath")), x.gei(x.call(K_ARR, "Array_Length", TargetArray=pts()), 2))
    bv = x.br(ok); g.foreach("mp_fe", pts())
    bi = x.br(x.gti("@mp_fe.Array Index", 0))                               # point 0 is where the cat stands
    add_pt = x.do(K_ARR, "Array_Add", TargetArray=x.var("Waypoints"), NewItem="@mp_fe.Array Element")
    add_to = lambda: x.do(K_ARR, "Array_Add", TargetArray=x.var("Waypoints"), NewItem="@entry.To")
    # a new path re-seeds BestDist (Tick Move step 3) but never resets the stuck clock: only a new move / standing up / a waypoint does
    clr_d = x.do(K_ARR, "Array_Clear", TargetArray=x.var("WpDoor"))
    ps = x.do_self("Path Shut"); bps = x.br("@%s.Shut" % ps)
    g.chain("entry", clr, clr_d, x.setv("WpIndex", 0), x.setv("BestDist", B.STUCK_UNSEEDED), bo)
    # office: a closed door on the new path ends the move at once (Blocked), not after walking up to the door
    g.chain(bo + ":then", x.do_self("Office Path", To="@entry.To"), ps, bps); g.chain(bps + ":then", x.do_self("Blocked"))
    g.chain(bo + ":else", bn); g.chain(bn + ":then", fp, sp, bv); g.chain(bn + ":else", add_to())
    g.chain(bv + ":then", "mp_fe"); g.chain("mp_fe", bi); g.chain(bi + ":then", add_pt); g.chain(bv + ":else", add_to())
    return fn("Make Path", [param("To", VEC)], graph=g)


def f_nearest_walk():
    """Index of the nearest walk point to From (2D); with Trace only one in clear sight (Line Clear at cat height). -1: none."""
    g = G(); x = X(g, "nw")
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc"))
    fl = x.loop(x.subi(n, 1))
    wp = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkLoc"), Index="@%s.Index" % fl)
    d = x.dist2d("@entry.From", wp)
    b1 = x.br(x.lt(d, x.var("MvBest")))
    lc = x.do_self("Line Clear", A=x.up("@entry.From", 4.0), B=x.up(wp, 20.0))
    b2 = x.br(x.or_(x.not_("@entry.Trace"), "@%s.Clear" % lc))
    g.chain("entry", x.setv("MvBest", 1e9), x.setv("MvIdx", -1), fl)
    g.chain(fl, b1); g.chain(b1 + ":then", lc, b2); g.chain(b2 + ":then", x.setv("MvBest", d), x.setv("MvIdx", "@%s.Index" % fl))
    g.chain(fl + ":Completed", x.ret(Out=x.var("MvIdx")))
    return fn("Nearest Walk", [param("From", VEC), param("Trace", "bool")], [param("Out", "int")], graph=g)


def f_office_path():
    g = G(); x = X(g, "op")
    a = x.do_self("Nearest Walk", From=x.loc(), Trace="true"); sa = x.setv("MvA", "@%s.Out" % a)
    b = x.do_self("Nearest Walk", From="@entry.To", Trace="false"); sb = x.setv("MvB", "@%s.Out" % b)
    direct = x.do_self("Line Clear", A=x.up(x.loc(), 4.0), B=x.up("@entry.To", 20.0))
    bd = x.br(x.or_("@%s.Clear" % direct, x.lti(x.var("MvA"), 0), x.lti(x.var("MvB"), 0)))
    add_ = lambda v: x.do(K_ARR, "Array_Add", TargetArray=x.var("Waypoints"), NewItem=v)
    wl = lambda i: x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkLoc"), Index=i)
    add_d = lambda d: x.do(K_ARR, "Array_Add", TargetArray=x.var("WpDoor"), NewItem=d)
    # WpDoor parallel to Waypoints: the walk index of a doorway point (Path Shut traces its door), else -1
    door_of = lambda i: x.seli(x.gei(x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkDoor"), Index=i), 0), i, -1)
    add_w = lambda i: [add_(wl(i)), add_d(door_of(i))]
    add_to = lambda: [add_("@entry.To"), add_d("-1")]
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc"))
    fl = x.loop(n, brk=True)
    be = x.br(x.eqi(x.var("MvA"), x.var("MvB")))
    nxt = x.self_fn("VP_NextHop", Next=x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkNext"), Index=x.var("MvA")), B=x.var("MvB"))
    sn = x.setv("MvA", nxt); bneg = x.br(x.lti(x.var("MvA"), 0))
    g.chain("entry", a, sa, b, sb, direct, bd)
    g.chain(bd + ":then", *add_to())
    g.chain(bd + ":else", *add_w(x.var("MvA")), fl)
    g.chain(fl, be); g.chain(be + ":then", fl + ":Break"); g.chain(be + ":else", sn, bneg)
    g.chain(bneg + ":then", fl + ":Break"); g.chain(bneg + ":else", *add_w(x.var("MvA")))
    g.chain(fl + ":Completed", *add_to())
    return fn("Office Path", [param("To", VEC)], graph=g)


def f_tick_move():
    """Not ready to walk (not standing, or a step/action still running): stand up first; the stuck clock waits meanwhile (a sleeping
    cat needs several seconds to stand). Steps 1-3 only while the move still runs (Arrive / Stuck of an earlier step end it).
    Stuck = no STUCK_GAIN nearer to the current waypoint in STUCK_TIME (not to the moving goal: neither a repath nor a
    reached waypoint resets the clock). Follow farther than FOLLOW_TELEPORT from Jodi: teleport behind her like recall (E1, E9)."""
    g = G(); x = X(g, "tm"); now = x.now
    ready = x.and_(x.eqi(x.var("Posture"), B.P_STAND), x.ge(now(), x.var("BusyUntil")))
    bp_ = x.br(x.not_(ready))
    g.chain("entry", bp_)
    g.chain(bp_ + ":then", x.setv("WantPosture", B.P_STAND), x.setv("ProgressAt", now()), x.do_self("Posture Step"))
    q = x.seq(4); g.chain(bp_ + ":else", q)
    # (0) new goal every REPATH s for follow / recall / flee, when it moved > 100 cm
    br0 = x.br(x.and_(x.ge(now(), x.var("RepathAt")), purpose_is(x, B.GO_FOLLOW, B.GO_RECALL, B.GO_FLEE)))
    # the enemy's place comes from an exec branch on IsValid (Enemy Place), not a select: a pure select evaluates both inputs and
    # the location of a None Enemy logs "Accessed None"
    ep = x.do_self("Enemy Place")
    flee = x.self_fn("VP_FleeGoal", Jodi=jodi_loc(x), Enemy="@%s.Loc" % ep)
    new = x.vsel(x.eqi(x.var("Purpose"), B.GO_FOLLOW), x.self_fn("VP_FollowPoint", Jodi=jodi_loc(x), Cat=x.loc()),
                 x.vsel(x.eqi(x.var("Purpose"), B.GO_RECALL), jodi_loc(x), flee))
    sn = x.setv("MvNew", new); bm = x.br(x.gt(x.dist2d(x.var("MvNew"), x.var("Goal")), 100.0))
    g.chain(q + ":then_0", br0); g.chain(br0 + ":then", x.setv("RepathAt", x.add(now(), B.REPATH)), ep, sn, bm)
    g.chain(bm + ":then", x.setv("Goal", x.var("MvNew")), x.do_self("Make Path", To=x.var("MvNew")))
    # (1) arrival / teleport by purpose
    dj = lambda: x.dist2d(x.loc(), jodi_loc(x))
    b_f = x.br(x.and_(x.eqi(x.var("Purpose"), B.GO_FOLLOW), x.le(dj(), B.FOLLOW_STOP)))
    b_r = x.br(x.and_(x.eqi(x.var("Purpose"), B.GO_RECALL), x.le(dj(), B.RECALL_ARRIVE)))
    b_t = x.br(x.or_(x.and_(x.eqi(x.var("Purpose"), B.GO_RECALL), x.gt(dj(), B.RECALL_TELEPORT)),
                     x.and_(x.eqi(x.var("Purpose"), B.GO_FOLLOW), x.gt(dj(), B.FOLLOW_TELEPORT))))
    g.chain(q + ":then_1", b_f); g.chain(b_f + ":then", x.do_self("Arrive")); g.chain(b_f + ":else", b_r)
    g.chain(b_r + ":then", x.do_self("Arrive")); g.chain(b_r + ":else", b_t); g.chain(b_t + ":then", x.do_self("Teleport Behind"), x.do_self("Arrive"))
    # (2) steer along the waypoints
    b2 = x.br(moving(x))
    n = lambda: x.call(K_ARR, "Array_Length", TargetArray=x.var("Waypoints"))
    be = x.br(x.gei(x.var("WpIndex"), n()))
    wp = lambda: x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("Waypoints"), Index=x.var("WpIndex"))
    bc = x.br(x.lt(x.dist2d(x.loc(), wp()), B.ARRIVE))
    # a reached waypoint only re-seeds: the clock moves on real STUCK_GAIN progress (step 3), never on reaching a waypoint (after a
    # repath the first waypoint can already be within ARRIVE, so a reset here would keep a pinned cat "unstuck" while Jodi walks)
    inc = [x.setv("WpIndex", x.addi(x.var("WpIndex"), 1)), x.setv("BestDist", B.STUCK_UNSEEDED)]
    bl = x.br(x.and_(x.eqi(x.var("Level"), B.LV_OFFICE), x.lti(x.var("WpIndex"), n())))
    lc = x.do_self("Line Clear", A=x.up(x.loc(), 4.0), B=x.up(wp(), 20.0)); bb = x.br(x.not_("@%s.Clear" % lc))
    js = x.m("VSize2D", A=x.call(E_ACTOR, "GetVelocity", self=x.var("Jodi")))
    speed = x.sel(x.eqi(x.var("Purpose"), B.GO_FOLLOW), x.self_fn("VP_FollowSpeed", Dist=dj(), JodiSpeed=js),
                  x.sel(x.eqi(x.var("Purpose"), B.GO_RECALL), B.RECALL_SPEED,
                        x.sel(x.eqi(x.var("Purpose"), B.GO_FLEE), B.FLEE_SPEED,
                              x.sel(x.eqi(x.var("Purpose"), B.GO_ROAM), B.ROAM_SPEED, B.SPOT_WALK_SPEED))))
    cmc = x.var("CharacterMovement", cls=E_CHAR, obj=x.me())
    # follow: fmin(VP_FollowSpeed, VP_MaxSpeed(Scale)); every purpose capped the same way (E1, E24)
    sw = x.setv("MaxWalkSpeed", x.fmin(x.fmax(speed, B.WALK_ANIM), x.self_fn("VP_MaxSpeed", Scale=x.scale())), cls=E_CMC, obj=cmc)
    lx, ly, _ = x.brk(x.loc()); wx, wy, _ = x.brk(wp())
    dirv = x.normal(x.vec(x.sub(wx, lx), x.sub(wy, ly), 0.0))
    mv = x.do(E_PAWN, "AddMovementInput", self=x.me(), WorldDirection=dirv, ScaleValue="1.0", bForce="false")
    g.chain(q + ":then_2", b2); g.chain(b2 + ":then", be); g.chain(be + ":then", x.do_self("Arrive")); g.chain(be + ":else", bc)
    ps = x.do_self("Path Shut"); bps = x.br("@%s.Shut" % ps)        # a door shut since the path was made: noticed at the next waypoint
    g.chain(bc + ":then", *inc, bl); g.chain(bl + ":then", ps, bps); g.chain(bps + ":then", x.do_self("Blocked"))
    g.chain(bps + ":else", lc, bb); g.chain(bb + ":then", x.do_self("Stuck"))
    g.chain(bc + ":else", sw, mv)
    # (3) progress towards the current waypoint (seeded once after a new path or waypoint)
    b3 = x.br(x.and_(moving(x), x.lti(x.var("WpIndex"), n())))
    dg = lambda: x.dist2d(x.loc(), wp())
    bseed = x.br(x.ge(x.var("BestDist"), B.STUCK_UNSEEDED))
    bp2 = x.br(x.lt(dg(), x.sub(x.var("BestDist"), B.STUCK_GAIN)))
    bs = x.br(x.gt(x.sub(now(), x.var("ProgressAt")), B.STUCK_TIME))
    g.chain(q + ":then_3", b3); g.chain(b3 + ":then", bseed)
    g.chain(bseed + ":then", x.setv("BestDist", dg())); g.chain(bseed + ":else", bp2)
    g.chain(bp2 + ":then", x.setv("BestDist", dg()), x.setv("ProgressAt", now()))
    g.chain(bp2 + ":else", bs); g.chain(bs + ":then", x.do_self("Stuck"))
    return fn("Tick Move", [param("DT", "float")], graph=g)


def f_arrive():
    g = G(); x = X(g, "ar")
    clr = x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints"))
    head = ["entry", clr, x.setv("State", B.ST_REST), x.setv("RestSince", x.now()),
            x.setv("NextRoutine", x.add(x.now(), B.ROUTINE_MIN))]
    b_sit = x.br(purpose_is(x, B.GO_FOLLOW, B.GO_RECALL))
    b_wait = x.br(x.eqi(x.var("Mode"), B.MODE_WAIT))
    b_roam = x.br(x.eqi(x.var("Purpose"), B.GO_ROAM))
    b_spot = x.br(x.eqi(x.var("Purpose"), B.GO_SPOT))
    g.chain(*head, b_sit)
    b_rr = x.br(x.and_(x.eqi(x.var("Purpose"), B.GO_RECALL), x.eqi(x.var("Mode"), B.MODE_ROAM)))
    roam_rest = lambda: x.setv("RoamNext", x.add(x.now(), x.m("RandomFloatInRange", Min=num(B.ROAM_REST_MIN), Max=num(B.ROAM_REST_MAX))))
    brc = x.br(x.eqi(x.var("Purpose"), B.GO_RECALL)); qa = x.seq(2)
    g.chain(b_sit + ":then", x.setv("WantPosture", B.P_SIT), qa)
    g.chain(qa + ":then_0", brc); g.chain(brc + ":then", x.do_self("Cue", Id=str(B.CUE_ARRIVED)))
    g.chain(qa + ":then_1", b_wait); g.chain(b_wait + ":then", x.setv("Anchor", x.loc()))
    g.chain(b_wait + ":else", b_rr); g.chain(b_rr + ":then", roam_rest(), x.setv("Anchor", x.loc()))   # recalled while roaming: rest, roam here
    g.chain(b_sit + ":else", b_roam)
    g.chain(b_roam + ":then", roam_rest())
    g.chain(b_roam + ":else", b_spot); g.chain(b_spot + ":then", x.do_self("Start Jump", Down="false"))
    return fn("Arrive", graph=g)


def f_stuck():
    g = G(); x = X(g, "sk")
    b_tp = x.br(purpose_is(x, B.GO_FOLLOW, B.GO_RECALL, B.GO_FLEE)); b_roam = x.br(x.eqi(x.var("Purpose"), B.GO_ROAM))
    office_spot = x.and_(x.gei(x.var("SpotIdx"), 0), x.lti(x.var("SpotIdx"), B.SPOT_AUTO))
    b_os = x.br(office_spot)
    rest = lambda: [x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")), x.setv("State", B.ST_REST), x.setv("RestSince", x.now())]
    g.chain("entry", b_tp); g.chain(b_tp + ":then", x.do_self("Teleport Behind"), x.do_self("Arrive"))
    g.chain(b_tp + ":else", b_roam)
    g.chain(b_roam + ":then", x.setv("RoamNext", x.now()), *rest())
    g.chain(b_roam + ":else", *x.dbg(B.DBG_STUCK), x.setv("SpotValid", "false"), b_os)          # a spot it cannot reach: left out for a while
    g.chain(b_os + ":then", x.do(K_ARR, "Array_Set", TargetArray=x.var("SpotsUntil"), Index=x.var("SpotIdx"), Item=x.add(x.now(), B.SPOT_DROP_STUCK),
                                 bSizeToFit="false"), *rest())
    g.chain(b_os + ":else", *rest())
    return fn("Stuck", graph=g)


def f_blocked():
    """A closed door on the path (Path Shut): as Stuck, but at once and a spot is left out only SPOT_DROP_BLOCKED (the door may open).
    Follow / recall / flee: out of sight behind Jodi (she cannot follow through the door); roam: a new target next tick (Roam Next
    checks the routes)."""
    g = G(); x = X(g, "bk")
    b_tp = x.br(purpose_is(x, B.GO_FOLLOW, B.GO_RECALL, B.GO_FLEE)); b_roam = x.br(x.eqi(x.var("Purpose"), B.GO_ROAM))
    b_os = x.br(x.and_(x.eqi(x.var("Purpose"), B.GO_SPOT), x.gei(x.var("SpotIdx"), 0), x.lti(x.var("SpotIdx"), B.SPOT_AUTO)))
    rest = lambda: [x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")), x.setv("State", B.ST_REST), x.setv("RestSince", x.now())]
    g.chain("entry", *x.dbg(B.DBG_DOOR), b_tp); g.chain(b_tp + ":then", x.do_self("Teleport Behind"), x.do_self("Arrive"))
    g.chain(b_tp + ":else", b_roam); g.chain(b_roam + ":then", x.setv("RoamNext", x.add(x.now(), 1.0)), *rest())
    g.chain(b_roam + ":else", x.setv("SpotValid", "false"), b_os)
    g.chain(b_os + ":then", x.do(K_ARR, "Array_Set", TargetArray=x.var("SpotsUntil"), Index=x.var("SpotIdx"), Item=x.add(x.now(), B.SPOT_DROP_BLOCKED),
                                 bSizeToFit="false"), *rest())
    g.chain(b_os + ":else", *rest())
    return fn("Blocked", graph=g)


def f_door_closed():
    """The door of doorway point W is shut: a Camera trace between its probes (a closed leaf blocks every channel; the doorway's hidden
    wall, InvisibleWallDynamic, ignores only Visibility) hits something. Jodi is ignored (she may stand in the doorway)."""
    g = G(); x = X(g, "dc")
    get = lambda a: x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var(a), Index="@entry.W")
    t, hit, _ = x.trace(get("WalkDoorA"), get("WalkDoorB"), ignore=x.var("Jodi"), channel=TRACE_CAM)
    g.chain("entry", t, x.ret(Closed=hit))
    return fn("Door Closed", [param("W", "int")], [param("Closed", "bool")], graph=g)


def f_path_shut():
    """A doorway point among the path's remaining waypoints (WpDoor from WpIndex) whose door is shut."""
    g = G(); x = X(g, "pt")
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("WpDoor")); fl = x.loop(x.subi(n, 1), brk=True, first=x.var("WpIndex"))
    d = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WpDoor"), Index="@%s.Index" % fl)
    bd = x.br(x.gei(d, 0)); dc = x.do_self("Door Closed", W=d); bc = x.br("@%s.Closed" % dc)
    g.chain("entry", x.setv("MvShut", "false"), fl); g.chain(fl, bd); g.chain(bd + ":then", dc, bc)
    g.chain(bc + ":then", x.setv("MvShut", "true"), fl + ":Break")
    g.chain(fl + ":Completed", x.ret(Shut=x.var("MvShut")))
    return fn("Path Shut", outputs=[param("Shut", "bool")], graph=g)


def f_route_prep():
    """Before choosing targets: is any door shut (RoShut, one trace per doorway); only then her own walk point (RoFrom, in clear
    sight) for Route Open."""
    g = G(); x = X(g, "rq")
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("DoorPts")); fl = x.loop(x.subi(n, 1))
    dc = x.do_self("Door Closed", W=x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("DoorPts"), Index="@%s.Index" % fl))
    bc = x.br("@%s.Closed" % dc); bs = x.br(x.var("RoShut")); nw = x.do_self("Nearest Walk", From=x.loc(), Trace="true")
    g.chain("entry", x.setv("RoShut", "false"), x.setv("RoFrom", -1), fl); g.chain(fl, dc, bc); g.chain(bc + ":then", x.setv("RoShut", "true"))
    g.chain(fl + ":Completed", bs); g.chain(bs + ":then", nw, x.setv("RoFrom", "@%s.Out" % nw))
    return fn("Route Prep", graph=g)


def f_route_open():
    """No shut door on the way from RoFrom to walk point B along the next hops (and B reachable). Free when Route Prep found every
    door open (no walk at all)."""
    g = G(); x = X(g, "ro")
    go = x.br(x.and_(x.var("RoShut"), x.gei(x.var("RoFrom"), 0), x.gei("@entry.B", 0)))
    fl = x.loop(x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc")), brk=True); q = x.seq(2)
    bdw = x.br(x.gei(x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkDoor"), Index=x.var("RoCur")), 0))
    dc = x.do_self("Door Closed", W=x.var("RoCur")); bc = x.br("@%s.Closed" % dc)
    bb = x.br(x.and_(x.var("RoRes"), x.nei(x.var("RoCur"), "@entry.B")))
    nxt = x.self_fn("VP_NextHop", Next=x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkNext"), Index=x.var("RoCur")), B="@entry.B")
    bn = x.br(x.lti(x.var("RoCur"), 0))
    g.chain("entry", go); g.chain(go + ":else", x.ret(Open="true"))
    g.chain(go + ":then", x.setv("RoRes", "true"), x.setv("RoCur", x.var("RoFrom")), fl); g.chain(fl, q)
    g.chain(q + ":then_0", bdw); g.chain(bdw + ":then", dc, bc); g.chain(bc + ":then", x.setv("RoRes", "false"), fl + ":Break")
    g.chain(q + ":then_1", bb); g.chain(bb + ":then", x.setv("RoCur", nxt), bn); g.chain(bn + ":then", x.setv("RoRes", "false"), fl + ":Break")
    g.chain(bb + ":else", fl + ":Break")
    g.chain(fl + ":Completed", x.ret(Open=x.var("RoRes")))
    return fn("Route Open", [param("B", "int")], [param("Open", "bool")], graph=g)


def f_teleport_behind():
    """Out of sight behind Jodi (E9): candidates around the point behind the camera, floor under it, outside the view cone, Jodi can
    see it (no wall between); K2_TeleportTo checks the capsule. None works: candidate 0 without the view checks."""
    g = G(); x = X(g, "tb")
    cm = x.call(K_GS, "GetPlayerCameraManager", PlayerIndex="0")
    rot = x.call(E_PCM, "GetCameraRotation", self=cm)
    s0 = x.setv("MvCam", x.call(E_PCM, "GetCameraLocation", self=cm)); s1 = x.setv("MvFwd", x.m("GetForwardVector", InRot=rot))
    s2 = x.setv("MvYaw", x.yaw_of(rot)); s3 = x.setv("MvDone", "false")
    fl = x.loop(len(B.TELEPORT_ANGLES) - 1, brk=True)
    cand = x.self_fn("VP_TeleportCandidate", Index="@%s.Index" % fl, Jodi=jodi_loc(x), CamYaw=x.var("MvYaw"))
    fa = x.do_self("Floor At", P=cand); bh = x.br("@%s.Hit" % fa)
    sp = x.setv("MvP", x.up("@%s.Loc" % fa, x.add(x.hh(), 2.0)))
    lc = x.do_self("Line Clear", A=x.up(jodi_loc(x), 60.0), B=x.up(x.var("MvP"), 20.0))
    bok = x.br(x.and_(x.self_fn("VP_OutOfView", P=x.var("MvP"), Cam=x.var("MvCam"), Fwd=x.var("MvFwd")), "@%s.Clear" % lc))
    tp = x.do_self("Teleport To", Loc=x.var("MvP"), Yaw=x.yaw_to(x.var("MvP"), jodi_loc(x))); btp = x.br("@%s.Ok" % tp)
    g.chain("entry", s0, s1, s2, s3, fl)
    g.chain(fl, fa, bh); g.chain(bh + ":then", sp, lc, bok); g.chain(bok + ":then", tp, btp)
    g.chain(btp + ":then", x.setv("MvDone", "true"), fl + ":Break")
    c0 = x.self_fn("VP_TeleportCandidate", Index="0", Jodi=jodi_loc(x), CamYaw=x.var("MvYaw"))
    fa0 = x.do_self("Floor At", P=c0)
    p0 = x.vsel("@%s.Hit" % fa0, x.up("@%s.Loc" % fa0, x.add(x.hh(), 2.0)), c0)
    bnd = x.br(x.not_(x.var("MvDone"))); q = x.seq(2)
    g.chain(fl + ":Completed", q)
    g.chain(q + ":then_0", bnd); g.chain(bnd + ":then", fa0, x.do_self("Teleport To", Loc=p0, Yaw=x.yaw_to(p0, jodi_loc(x))))
    g.chain(q + ":then_1", x.do_self("Snap Posture", P=str(B.P_STAND)), x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")))
    return fn("Teleport Behind", graph=g)


def f_roam_next():
    g = G(); x = X(g, "rn"); R = B.ROAM_RADIUS
    office = x.and_(x.eqi(x.var("Level"), B.LV_OFFICE), x.gti(x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc")), 0))
    bo = x.br(office); bn = x.br(x.var("HasNav"))
    # office: up to 8 random walk points, the first within the radius of the anchor
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkLoc"))
    fl = x.loop(7, brk=True)
    pick = x.setv("MvA", x.m("RandomIntegerInRange", Min="0", Max=x.subi(n, 1)))
    wl = lambda: x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkLoc"), Index=x.var("MvA"))
    bi = x.br(x.le(x.dist2d(wl(), x.var("Anchor")), R))
    # NavMesh (pure in 4.27: every read is a new draw, so read once into MvP; on failure the engine returns Origin = Anchor)
    rp = x.nid("np"); g.call(rp, NAV, "K2_GetRandomReachablePointInRadius", inp={"Origin": x.var("Anchor"), "Radius": num(R)})
    # neither: a step of 2-8 m in a random direction from the cat, pulled back inside the radius, floor under it
    yaw = x.m("RandomFloatInRange", Min="0.0", Max="360.0"); step = x.m("RandomFloatInRange", Min=num(B.ROAM_STEP_MIN), Max=num(B.ROAM_STEP_MAX))
    sy = x.setv("MvYaw", yaw); ss = x.setv("MvBest", step)                  # MvBest holds the step length here (Nearest Walk not running)
    lx, ly, lz = x.brk(x.loc())
    p = x.vec(x.add(lx, x.mul(x.m("DegCos", A=x.var("MvYaw")), x.var("MvBest"))), x.add(ly, x.mul(x.m("DegSin", A=x.var("MvYaw")), x.var("MvBest"))), lz)
    inside = x.le(x.dist2d(p, x.var("Anchor")), R)
    toward = x.vadd(x.var("Anchor"), x.vmul(x.normal(x.vsub(p, x.var("Anchor"))), R * 0.7))
    spp = x.setv("MvP", x.vsel(inside, p, toward))
    fa = x.do_self("Floor At", P=x.var("MvP")); bf = x.br("@%s.Hit" % fa)
    retry = x.setv("RoamNext", x.add(x.now(), 1.0))
    go = lambda v: x.do_self("Start Move", Purpose=str(B.GO_ROAM), To=v)
    ro = x.do_self("Route Open", B=x.var("MvA")); bro = x.br("@%s.Open" % ro)       # not behind a shut door
    g.chain("entry", bo)
    g.chain(bo + ":then", x.do_self("Route Prep"), x.setv("MvDone", "false"), fl); g.chain(fl, pick, bi); g.chain(bi + ":then", ro, bro)
    g.chain(bro + ":then", x.setv("MvDone", "true"), go(wl()), fl + ":Break")
    bnd = x.br(x.not_(x.var("MvDone"))); g.chain(fl + ":Completed", bnd); g.chain(bnd + ":then", x.setv("RoamNext", x.add(x.now(), 1.0)))
    g.chain(bo + ":else", bn)
    brp = x.br(x.gt(x.dist2d(x.var("MvP"), x.var("Anchor")), 1.0))
    g.chain(bn + ":then", x.setv("MvP", "@%s.RandomLocation" % rp), brp); g.chain(brp + ":then", go(x.var("MvP"))); g.chain(brp + ":else", x.setv("RoamNext", x.add(x.now(), 1.0)))
    g.chain(bn + ":else", sy, ss, spp, fa, bf); g.chain(bf + ":then", go("@%s.Loc" % fa)); g.chain(bf + ":else", retry)
    return fn("Roam Next", graph=g)


def f_recall():
    g = G(); x = X(g, "rc")
    g.chain("entry", x.do_self("Start Move", Purpose=str(B.GO_RECALL), To=jodi_loc(x)), x.do_self("Cue", Id=str(B.CUE_CALLED)))
    return fn("Recall", graph=g)


def f_set_mode():
    """Mode M (Follow / Wait / Roam: AltUI, quick menu, Cycle Mode). Into Wait while walking after Jodi or roaming: stop where she is
    (E16 "bleibt"). Into Follow while on a roam walk: stop it, so Tick Rest starts following at once. Saved at once."""
    g = G(); x = X(g, "cm")
    sm = x.setv("Mode", "@entry.M")
    bw = x.br(x.eqi(x.var("Mode"), B.MODE_WAIT)); br_ = x.br(x.eqi(x.var("Mode"), B.MODE_ROAM))
    bstop = x.br(x.and_(moving(x), purpose_is(x, B.GO_FOLLOW, B.GO_ROAM))); q = x.seq(2)
    g.chain("entry", sm, bw); g.chain(bw + ":then", q)
    g.chain(q + ":then_0", bstop); g.chain(bstop + ":then", x.do_self("Arrive"))
    g.chain(q + ":then_1", x.setv("Anchor", x.loc()), x.do_self("Save Settings"))
    # roam anchor: Jodi's place; a dormant cat (AltUI while she is off) may have no Jodi yet: her own place then. An exec branch, not a
    # select: a pure select evaluates both inputs, and Jodi's location on a None Jodi logs "Accessed None"
    bj = x.br(x.call(K_SYS, "IsValid", Object=x.var("Jodi")))
    g.chain(bw + ":else", br_); g.chain(br_ + ":then", bj)
    g.chain(bj + ":then", x.setv("Anchor", jodi_loc(x)), x.setv("RoamNext", x.now()), x.do_self("Save Settings"))
    g.chain(bj + ":else", x.setv("Anchor", x.loc()), x.setv("RoamNext", x.now()), x.do_self("Save Settings"))
    bstop_f = x.br(x.and_(moving(x), x.eqi(x.var("Purpose"), B.GO_ROAM))); q2 = x.seq(2)
    g.chain(br_ + ":else", q2); g.chain(q2 + ":then_0", bstop_f); g.chain(bstop_f + ":then", x.do_self("Arrive"))
    g.chain(q2 + ":then_1", x.do_self("Save Settings"))
    return fn("Set Mode", [param("M", "int")], graph=g)


def f_cycle_mode():
    g = G(); x = X(g, "cy")
    g.chain("entry", x.do_self("Set Mode", M=x.m("Percent_IntInt", A=x.addi(x.var("Mode"), 1), B="3")))
    return fn("Cycle Mode", graph=g)


def f_tick_rest():
    """Follow / roam starts first; the routine (or the alarm rest) only while the cat still rests (no routine on the first walking tick)."""
    g = G(); x = X(g, "tr"); q = x.seq(2)
    follow = x.and_(x.eqi(x.var("Mode"), B.MODE_FOLLOW), x.gt(x.dist2d(x.loc(), jodi_loc(x)), B.FOLLOW_START), x.not_(x.var("Alarmed")))
    bf = x.br(follow)
    roam = x.and_(x.eqi(x.var("Mode"), B.MODE_ROAM), x.ge(x.now(), x.var("RoamNext")), x.ge(x.now(), x.var("BusyUntil")), x.not_(x.var("Alarmed")))
    brm = x.br(roam); bst = x.br(x.eqi(x.var("State"), B.ST_REST)); ba = x.br(x.var("Alarmed"))
    g.chain("entry", q)
    g.chain(q + ":then_0", bf); g.chain(bf + ":then", x.do_self("Start Move", Purpose=str(B.GO_FOLLOW),
                                                                  To=x.self_fn("VP_FollowPoint", Jodi=jodi_loc(x), Cat=x.loc())))
    g.chain(bf + ":else", brm); g.chain(brm + ":then", x.do_self("Roam Next"))
    g.chain(q + ":then_1", bst); g.chain(bst + ":then", ba)
    g.chain(ba + ":then", x.do_self("Alarm Rest")); g.chain(ba + ":else", x.do_self("Rest Routine"))
    return fn("Tick Rest", [param("DT", "float")], graph=g)


def f_poll_keys(test_keys):
    g = G(); x = X(g, "pk")
    pc = lambda: x.call(K_GS, "GetPlayerController", PlayerIndex="0")
    bv = x.br(x.call(K_SYS, "IsValid", Object=pc()))
    pressed = lambda key: x.call(E_PC, "WasInputKeyJustPressed", self=pc(), Key=key)
    actions = [(x.and_(x.call(K_IN, "Key_IsValid", Key=x.var("RecallKey")), pressed(x.var("RecallKey"))), [x.do_self("Recall")])]
    if test_keys:
        actions += [(pressed(B.TEST_KEYS["Recall"]), [x.do_self("Recall")]),
                    (pressed(B.TEST_KEYS["CycleMode"]), [x.do_self("Cycle Mode")]),
                    (pressed(B.TEST_KEYS["TakeAlong"]), [x.setv("TakeAlong", x.not_(x.var("TakeAlong"))), x.do_self("Save Settings")]),
                    (pressed(B.TEST_KEYS["Meow"]), [x.do_self("Play Meow")])]
    q = x.seq(len(actions)); g.chain("entry", bv); g.chain(bv + ":then", q)
    for k, (cond, body) in enumerate(actions):
        b = x.br(cond); g.chain(q + ":then_%d" % k, b); g.chain(b + ":then", *body)
    return fn("Poll Keys", graph=g)


def functions(opts):
    return [f_start_move(), f_make_path(), f_nearest_walk(), f_office_path(), f_tick_move(), f_arrive(), f_stuck(), f_blocked(), f_door_closed(),
            f_path_shut(), f_route_prep(), f_route_open(), f_teleport_behind(),
            f_roam_next(), f_recall(), f_set_mode(), f_cycle_mode(), f_tick_rest(), f_poll_keys(opts["test_keys"])]
