"""Home and level start of BP_VP_Cat (plan Etappe 3, Task 12; E22). Office: the map tables into arrays (walk points for Office Path,
spots for Pick Office Spot), every spot checked by a trace (+-8 cm), then the cat appears at her saved place (spot or floor, in her
saved posture), else on the checked spot with the highest weight. Missions (only with TakeAlong; BeginPlay already destroyed her
otherwise): out of sight behind Jodi, standing; NavMesh looked up once (HasNav: Make Path uses FindPathToLocationSynchronously).
Her office place is saved every 10 s when it changed (> 30 cm or another posture) and at EndPlay."""
from bpdsl import G, fn, var, K_ARR, K_DT, E_ACTOR
from vp_expr import X, NAV
from velvetpaws import names, brain as B


def variables(): return [var("HmBest", "float", default="-1.0"), var("HmIdx", "int", default="-1")]


def _load(g, x, table, struct_, p, fields):
    """GetDataTableRowNames -> for each row: get_row -> break -> Array_Add per (array var, struct member); returns (first id, loop id)."""
    rn = x.do(K_DT, "GetDataTableRowNames", Table=table)
    g.foreach(p + "fe", "@%s.OutRowNames" % rn)
    g.n(p + "row", "get_row", table=table, inp={"RowName": "@%sfe.Array Element" % p}, miss="ignore")
    g.brk(p + "br", struct_, "@%srow.OutRow" % p)
    adds = [x.do(K_ARR, "Array_Add", TargetArray=x.var(arr), NewItem="@%sbr.%s" % (p, member)) for arr, member in fields]
    g.chain(p + "fe", p + "row", *adds)
    return rn, p + "fe"


def f_init_level():
    """Office: tables loaded, spots checked; any spot passed -> SpotValid and OfficeSpotsOK (Routine offers spots again after a floor
    start, Stuck or Abort Jump; Go To Spot picks among the checked ones). Mission: HasNav from a NavMesh projection of Jodi."""
    g = G(); x = X(g, "il")
    bo = x.br(x.eqi(x.var("Level"), B.LV_OFFICE))
    w0, wfe = _load(g, x, names.DT_WALK, names.S_WALK, "ilw", [("WalkLoc", "Location"), ("WalkNext", "Next"), ("WalkDoor", "Door"),
                                                               ("WalkDoorA", "DoorA"), ("WalkDoorB", "DoorB")])
    s0, sfe = _load(g, x, names.DT_SPOT, names.S_SPOT, "ils", [("SpotsLoc", "Location"), ("SpotsFrom", "From"), ("SpotsYaw", "Yaw"),
                                                               ("SpotsHeight", "Height"), ("SpotsPosture", "Posture"), ("SpotsWeight", "Weight"),
                                                               ("SpotsRoom", "Room"), ("SpotsWalk", "Walk")])
    # the doorway points (Route Prep traces only these)
    nw = x.call(K_ARR, "Array_Length", TargetArray=x.var("WalkDoor")); fd = x.loop(x.subi(nw, 1))
    bd = x.br(x.gei(x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("WalkDoor"), Index="@%s.Index" % fd), 0))
    # check every spot: a trace down onto it must hit within SPOT_VERIFY of its height; it starts under the board above a compartment
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("SpotsLoc")); fl = x.loop(x.subi(n, 1))
    sl = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsLoc"), Index="@%s.Index" % fl)
    room = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsRoom"), Index="@%s.Index" % fl)
    t, hit, hr = x.trace(x.up(sl, x.fmin(B.SPOT_VERIFY_UP, x.sub(room, 5.0))), x.up(sl, -30.0), ignore=x.var("Jodi"))
    h = x.hit(hr); _, _, hz = x.brk("@%s.Location" % h); _, _, sz = x.brk(sl)
    okv = x.and_(hit, x.le(x.abs_(x.sub(hz, sz)), B.SPOT_VERIFY))
    add_ok = x.do(K_ARR, "Array_Add", TargetArray=x.var("SpotsOK"), NewItem=okv)
    add_until = x.do(K_ARR, "Array_Add", TargetArray=x.var("SpotsUntil"), NewItem="0.0")
    bok = x.br(okv)
    # pure in 4.27 (BlueprintPure): not on the exec chain, read by the HasNav setter
    nav = x.call(NAV, "K2_ProjectPointToNavigation", Point=x.loc(x.var("Jodi")), QueryExtent="(X=100.0,Y=100.0,Z=250.0)")
    g.chain("entry", bo)
    g.chain(bo + ":then", w0, wfe); g.chain(wfe + ":Completed", fd); g.chain(fd, bd)
    g.chain(bd + ":then", x.do(K_ARR, "Array_Add", TargetArray=x.var("DoorPts"), NewItem="@%s.Index" % fd))
    g.chain(fd + ":Completed", s0, sfe); g.chain(sfe + ":Completed", fl); g.chain(fl, t, add_ok, add_until, bok)
    g.chain(bok + ":then", x.setv("SpotValid", "true"), x.setv("OfficeSpotsOK", "true"), *x.dbg(count="DbgOK"))
    g.chain(bo + ":else", x.setv("HasNav", nav))
    return fn("Init Level", graph=g)


def f_place_start():
    g = G(); x = X(g, "pl"); hh = x.hh()
    n = x.call(K_ARR, "Array_Length", TargetArray=x.var("SpotsLoc"))
    ps = x.var("PlaceSpot")
    # the index range is checked by its own branch first: SpotsOK is only read with PlaceSpot inside 0..n-1 (a pure AND evaluates
    # every input, so an out-of-range PlaceSpot would read past the array)
    saved_in = x.and_(x.var("HasPlace"), x.gei(ps, 0), x.lti(ps, n))
    # still the same spot (a new map can reorder the table): the saved place lies over it
    saved_spot = x.and_(x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsOK"), Index=ps),
                        x.lt(x.dist2d(x.var("PlaceLoc"), x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsLoc"), Index=ps)), 30.0))
    # a saved floor place only when it was saved on the floor: a saved spot that failed the check falls back to the best spot
    # (its PlaceLoc is up on the furniture, not a floor place)
    saved_floor = x.and_(x.var("HasPlace"), x.lti(x.var("PlaceSpot"), 0))
    bo = x.br(x.eqi(x.var("Level"), B.LV_OFFICE)); b0 = x.br(saved_in); b1 = x.br(saved_spot); b2 = x.br(saved_floor)
    stay = lambda: x.setv("StayUntil", x.add(x.now(), x.self_fn("VP_StayTime", Lo=x.var("StayMin"), Hi=x.var("StayMax"), R=x.m("RandomFloat"))))
    on_spot = lambda yaw, posture: [x.do_self("Teleport To", Loc=x.up(x.var("SpotLoc"), x.add(hh, 2.0)), Yaw=yaw), x.setv("State", B.ST_SPOT),
                                    x.do_self("Snap Posture", P=posture), stay()]
    # 1: saved spot (facing as the map says: the saved yaw may be from an older map)
    g.chain(b1 + ":then", x.do_self("Take Spot", I=x.var("PlaceSpot")), *on_spot(x.var("SpotYaw"), x.var("PlacePosture")))
    # 2: saved floor place
    fa = x.do_self("Floor At", P=x.var("PlaceLoc"))
    p = x.vsel("@%s.Hit" % fa, x.up("@%s.Loc" % fa, x.add(hh, 2.0)), x.var("PlaceLoc"))
    g.chain(b0 + ":then", b1); g.chain(b0 + ":else", b2); g.chain(b1 + ":else", b2)
    g.chain(b2 + ":then", fa, x.do_self("Teleport To", Loc=p, Yaw=x.var("PlaceYaw")), x.setv("State", B.ST_REST), x.do_self("Snap Posture", P=x.var("PlacePosture")))
    # 3: best spot by weight
    fl = x.loop(x.subi(n, 1)); i = "@%s.Index" % fl
    w = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsWeight"), Index=i)
    ok = x.call(K_ARR, "Array_Get", out="Item", TargetArray=x.var("SpotsOK"), Index=i)
    bb = x.br(x.and_(ok, x.gt(w, x.var("HmBest"))))
    bf = x.br(x.gei(x.var("HmIdx"), 0))
    g.chain(b2 + ":else", x.setv("HmBest", -1.0), x.setv("HmIdx", -1), fl)
    g.chain(fl, bb); g.chain(bb + ":then", x.setv("HmBest", w), x.setv("HmIdx", i))
    g.chain(fl + ":Completed", bf)
    g.chain(bf + ":then", x.do_self("Take Spot", I=x.var("HmIdx")), *on_spot(x.var("SpotYaw"), x.var("SpotPosture")))
    g.chain(bf + ":else", x.do_self("Teleport Behind"), x.setv("State", B.ST_REST))
    # mission
    g.chain(bo + ":else", x.do_self("Teleport Behind"), x.setv("State", B.ST_REST))
    tail = [x.setv("Anchor", x.loc()), x.setv("RestSince", x.now()), x.setv("NextRoutine", x.add(x.now(), B.ROUTINE_MIN)),
            x.setv("RoamNext", x.add(x.now(), B.ROAM_REST_MIN)), x.setv("SavedLoc", x.loc()), x.setv("SavedPosture", x.var("Posture"))]
    q = x.seq(2); g.chain("entry", q); g.chain(q + ":then_0", bo); g.chain(q + ":then_1", *tail)
    g.chain(bo + ":then", b0)
    return fn("Place Start", graph=g)


def f_save_place():
    g = G(); x = X(g, "sv")
    can = x.and_(x.var("Placed"), x.eqi(x.var("Level"), B.LV_OFFICE), x.or_(x.eqi(x.var("State"), B.ST_REST), x.eqi(x.var("State"), B.ST_SPOT)),
                 x.ge(x.now(), x.var("BusyUntil")))
    moved = x.or_(x.gt(x.dist(x.loc(), x.var("SavedLoc")), B.SAVE_MOVED), x.nei(x.var("Posture"), x.var("SavedPosture")))
    b = x.br(x.and_(can, moved))
    spot = x.seli(x.and_(x.eqi(x.var("State"), B.ST_SPOT), x.lti(x.var("SpotIdx"), B.SPOT_AUTO)), x.var("SpotIdx"), -1)
    yaw = x.yaw_of(x.call(E_ACTOR, "K2_GetActorRotation", self=x.me()))
    g.chain("entry", b)
    g.chain(b + ":then", x.setv("HasPlace", "true"), x.setv("PlaceSpot", spot), x.setv("PlaceLoc", x.loc()), x.setv("PlaceYaw", yaw),
            x.setv("PlacePosture", x.var("Posture")), x.setv("SavedLoc", x.loc()), x.setv("SavedPosture", x.var("Posture")), x.do_self("Save Settings"))
    return fn("Save Place", graph=g)


def events(g, x):
    g.custom("hm_save", "Save Tick"); g.chain("hm_save", x.do_self("Save Place"))


def functions(opts):
    return [f_init_level(), f_place_start(), f_save_place()]
