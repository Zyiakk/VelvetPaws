"""BP_VP_Cat, stage 3: the cat as a Character without controller (plan Etappe 3). Core: class defaults and the inherited components'
defaults (BPGen subobject_defaults), variables, BeginPlay / Place Cat / Tick / EndPlay, Think (state dispatch), hooks the behaviour
modules fill, settings load and save (SG_VP_Cat), animation update, collision, small helpers (Teleport To, Floor At, Line Clear).
Flow: BeginPlay -> Load Settings -> level kind -> keep? -> scale, hidden, movement off -> 1 s -> Place Cat -> Jodi valid -> Anim ->
Init Level -> Place Start -> Enable Body -> visible -> Start Timers -> Placed. Tick: Placed and Jodi valid -> Think -> Update Anim."""
from bpdsl import G, blueprint, fn, param, var, subobject_defaults, K_GS, K_SYS, E_ACTOR
from vp_expr import X, num, VEC, E_CHAR, E_CMC, E_PRIM, E_SKMC, E_ANIMI, E_ACOMP
from velvetpaws import names, brain as B

NOCOL = '(CollisionEnabled=NoCollision,CollisionProfileName="NoCollision")'
# Measured in the kit (SK_VP_Cat reference pose): the nose points +Y like the game's figures; Yaw -90 turns the mesh so the
# actor's +X is the cat's forward.
MESH_YAW = -90.0
ABP_CAST_PIN = "AsABP VP Cat"     # as confirmed by the stage 2 build (gen_velvetpaws.ABP_CAST_PIN of stage 2): take that value
HOOKS = B.HOOKS             # one list for the generator and verify_cooked.py
TICK_HOOKS = {"Tick Rest", "Tick Move", "Tick Jump", "Tick Spot", "Tick Alarm", "Tick Rub"}
CLASS_DEFAULTS = {"bCanBeDamaged": False, "AutoPossessAI": "Disabled", "AutoPossessPlayer": "Disabled", "bUseControllerRotationYaw": False}


def subobjects():
    return [
        subobject_defaults(names.BP, "CapsuleComponent", CapsuleRadius=B.CAPSULE_R, CapsuleHalfHeight=B.CAPSULE_HH, BodyInstance=NOCOL,
                           bCanEverAffectNavigation=False),
        subobject_defaults(names.BP, "CharacterMovement", MaxWalkSpeed=B.MAX_SPEED, MaxAcceleration=700.0, BrakingDecelerationWalking=900.0,
                           GroundFriction=8.0, bOrientRotationToMovement=True, RotationRate="(Pitch=0.0,Yaw=420.0,Roll=0.0)", MaxStepHeight=12.0,
                           WalkableFloorAngle=50.0, bRunPhysicsWithNoController=True, AirControl=0.0, GravityScale=1.0),
        subobject_defaults(names.BP, "Mesh", SkeletalMesh=names.MESH, AnimationMode="AnimationBlueprint", AnimClass=names.ABP_CLASS,
                           RelativeLocation="(X=0.0,Y=0.0,Z=%s)" % num(-B.CAPSULE_HH), RelativeRotation="(Pitch=0.0,Yaw=%s,Roll=0.0)" % num(MESH_YAW),
                           BodyInstance=NOCOL, VisibilityBasedAnimTickOption="AlwaysTickPose", bCanEverAffectNavigation=False),
    ]


def variables():
    I, F, Bo = "int", "float", "bool"
    v = [var(n, t, default=d) for n, t, d in B.SETTINGS + B.PLACE_VARS]
    v += [var("Jodi", "object:" + E_CHAR), var("Anim", "object:" + names.ABP), var("Level", I, default="0"), var("Placed", Bo, default="false"),
          var("PlaceTries", I, default="0"), var("HasNav", Bo, default="false"), var("HookNoop", Bo, default="false"), var("TickDT", F, default="0.033"),
          var("State", I, default=str(B.ST_REST)), var("Purpose", I, default="0"), var("Posture", I, default=str(B.P_STAND)),
          var("WantPosture", I, default=str(B.P_STAND)), var("BusyUntil", F, default="0.0"), var("AfterOp", I, default="0"),
          var("RestSince", F, default="0.0"), var("NextRoutine", F, default="0.0"),
          var("Goal", VEC), var("Waypoints", VEC, container="array"), var("WpIndex", I, default="0"), var("BestDist", F, default="0.0"),
          var("ProgressAt", F, default="0.0"), var("RepathAt", F, default="0.0"), var("Anchor", VEC), var("RoamNext", F, default="0.0"),
          var("AfterJump", I, default="-1"), var("JumpPhase", I, default="0"), var("JumpDown", Bo, default="false"), var("JumpTarget", VEC),
          var("LaunchAt", F, default="0.0"), var("AirSince", F, default="0.0"), var("WasFalling", Bo, default="false"),
          var("SpotValid", Bo, default="false"), var("OfficeSpotsOK", Bo, default="false"), var("SpotIdx", I, default="-1"), var("SpotLoc", VEC), var("SpotFrom", VEC),
          var("SpotYaw", F, default="0.0"), var("SpotHeight", F, default="0.0"), var("SpotPosture", I, default=str(B.P_LIE)),
          var("WalkLoc", VEC, container="array"), var("WalkNext", "string", container="array"),
          var("SpotsLoc", VEC, container="array"), var("SpotsFrom", VEC, container="array"), var("SpotsYaw", F, container="array"),
          var("SpotsHeight", F, container="array"), var("SpotsPosture", I, container="array"), var("SpotsWeight", F, container="array"),
          var("SpotsOK", Bo, container="array"),
          # round 6: doorway of each walk point (-1 none) and its probes, the doorway points, each spot's room above it and walk point,
          # the time until which a spot is left out (closed door / stuck / aborted jump), the taken spot's room, end of the stay
          var("WalkDoor", I, container="array"), var("WalkDoorA", VEC, container="array"), var("WalkDoorB", VEC, container="array"),
          var("DoorPts", I, container="array"), var("SpotsRoom", F, container="array"), var("SpotsWalk", I, container="array"),
          var("SpotsUntil", F, container="array"), var("SpotRoom", F, default=num(B.OPEN_ROOM)), var("StayUntil", F, default="0.0"),
          var("Enemy", "object:" + E_ACTOR), var("EnemyDist", F, default="100000.0"), var("Alarmed", Bo, default="false"),
          var("Hissed", Bo, default="false"), var("LastEnemy", F, default="-100.0"), var("SavedLoc", VEC), var("SavedPosture", I, default="-1"),
          var("Waking", Bo, default="false"), var("LevelReady", Bo, default="false"), var("SaveDue", Bo, default="false"),
          # spot diagnostic (brain.DEBUG_SPOTS; set at the steps only, read by Status Text)
          var("DbgSpot", I, default=str(B.DBG_NONE)), var("DbgOK", I, default="0"), var("DbgPicks", I, default="0"),
          var("DbgTries", I, default="0"), var("DbgJumps", I, default="0")]
    return v


def montage_ops(x, ops):
    """Exec ids of montage ops on Anim (brain op tuples)."""
    out = []
    for op in ops:
        anim = x.var("Anim")
        if op[0] == "play":
            out.append(x.do(E_ANIMI, "Montage_Play", self=anim, MontageToPlay=names.obj(names.montage(op[1])), InPlayRate="1.0",
                            ReturnValueType="MontageLength", InTimeToStartMontageAt="0.0", bStopAllMontages="true"))
        elif op[0] == "jump":
            out.append(x.do(E_ANIMI, "Montage_JumpToSection", self=anim, SectionName=op[2], Montage=names.obj(names.montage(op[1]))))
        else:
            out.append(x.do(E_ANIMI, "Montage_Stop", self=anim, InBlendOutTime=num(op[2]), Montage=names.obj(names.montage(op[1])) if op[1] else "None"))
    return out


HOOK_PARAMS = {"Cue": [("Id", "int")]}  # hooks with inputs other than DT


def _stub(name):
    g = G(); x = X(g, "h"); g.chain("entry", x.setv("HookNoop", "false"))
    return fn(name, [param("DT", "float")] if name in TICK_HOOKS else [param(n, t) for n, t in HOOK_PARAMS.get(name, [])], graph=g)


def f_think():
    g = G(); x = X(g, "th")
    # TickDT: the frame time for hooks without a DT input (Alarm Rest turns with it)
    chain = ["entry", x.setv("TickDT", "@entry.DT"), x.do_self("Poll Keys"), x.do_self("Combat Tick"), x.do_self("Sound Tick"), x.do_self("Watch Jodi")]
    prev = None
    for sid, hook in ((B.ST_REST, "Tick Rest"), (B.ST_MOVE, "Tick Move"), (B.ST_JUMP, "Tick Jump"), (B.ST_SPOT, "Tick Spot"), (B.ST_ALARM, "Tick Alarm"),
                      (B.ST_RUB, "Tick Rub")):
        b = x.br(x.eqi(x.var("State"), sid)); g.chain(b + ":then", x.do_self(hook, DT="@entry.DT"))
        if prev is None: chain.append(b)
        else: g.chain(prev + ":else", b)
        prev = b
    g.chain(*chain)
    return fn("Think", [param("DT", "float")], graph=g)


def f_update_anim():
    g = G(); x = X(g, "ua")
    v = x.m("VSize2D", A=x.call(E_ACTOR, "GetVelocity", self=x.me()))
    # a jump plays its montage (speed 0); walking into or out of a walk-in spot (JP_WALK) uses the gait like any walk
    spd = x.sel(x.and_(x.eqi(x.var("State"), B.ST_JUMP), x.nei(x.var("JumpPhase"), B.JP_WALK)), 0.0, x.self_fn("VP_AnimSpeed", V=v, Scale=x.scale()))
    anim = x.var("Anim"); b = x.br(x.call(K_SYS, "IsValid", Object=anim))
    s1 = x.setv(names.VAR_SPEED, spd, cls=names.ABP, obj=anim)
    tgt = x.sel(x.eqi(x.var("Posture"), B.P_SLEEP), 0.0, 1.0)
    a = x.m("FInterpTo", Current=x.var(names.VAR_OVERLAY, cls=names.ABP, obj=x.var("Anim")), Target=tgt, DeltaTime="@entry.DT", InterpSpeed=num(B.OVERLAY_RATE))
    s2 = x.setv(names.VAR_OVERLAY, a, cls=names.ABP, obj=x.var("Anim"))
    g.chain("entry", b); g.chain(b + ":then", s1, s2)
    return fn("Update Anim", [param("DT", "float")], graph=g)


def f_enable_body():
    g = G(); x = X(g, "eb"); cap = lambda: x.var("CapsuleComponent", cls=E_CHAR, obj=x.me())
    cmc = x.var("CharacterMovement", cls=E_CHAR, obj=x.me())
    g.chain("entry", x.do(E_PRIM, "SetCollisionObjectType", self=cap(), Channel="ECC_Pawn"),
            x.do(E_PRIM, "SetCollisionResponseToAllChannels", self=cap(), NewResponse="ECR_Ignore"),
            x.do(E_PRIM, "SetCollisionResponseToChannel", self=cap(), Channel="ECC_WorldStatic", NewResponse="ECR_Block"),
            x.do(E_PRIM, "SetCollisionResponseToChannel", self=cap(), Channel="ECC_WorldDynamic", NewResponse="ECR_Block"),
            # the office's sofas, armchairs and collection shelves are PhysicsBody (profiles PhysicsActorIgnoreCamera/-ViewLine in the
            # game's DefaultEngine.ini): without this the cat walks and lands through them
            x.do(E_PRIM, "SetCollisionResponseToChannel", self=cap(), Channel="ECC_PhysicsBody", NewResponse="ECR_Block"),
            x.do(E_PRIM, "SetCollisionEnabled", self=cap(), NewType="QueryOnly"),
            x.do(E_CMC, "SetMovementMode", self=cmc, NewMovementMode="MOVE_Walking", NewCustomMode="0"))
    return fn("Enable Body", graph=g)


def f_teleport_to():
    g = G(); x = X(g, "tp")
    tp = x.do(E_ACTOR, "K2_TeleportTo", self=x.me(), DestLocation="@entry.Loc", DestRotation=x.rot("@entry.Yaw"))
    stop = x.do(E_CMC, "StopMovementImmediately", self=x.var("CharacterMovement", cls=E_CHAR, obj=x.me()))
    g.chain("entry", tp, stop, x.ret(Ok="@%s.ReturnValue" % tp))
    return fn("Teleport To", [param("Loc", VEC), param("Yaw", "float")], [param("Ok", "bool")], graph=g)


def f_floor_at():
    g = G(); x = X(g, "fa")
    t, hit, hr = x.trace(x.up("@entry.P", B.TRACE_UP), x.up("@entry.P", -B.TRACE_DOWN), ignore=x.var("Jodi"))
    h = x.hit(hr)
    g.chain("entry", t, x.ret(Hit=hit, Loc="@%s.Location" % h))
    return fn("Floor At", [param("P", VEC)], [param("Hit", "bool"), param("Loc", VEC)], graph=g)


def f_line_clear():
    g = G(); x = X(g, "lc")
    t, hit, _ = x.trace("@entry.A", "@entry.B", ignore=x.var("Jodi"))
    g.chain("entry", t, x.ret(Clear=x.not_(hit)))
    return fn("Line Clear", [param("A", VEC), param("B", VEC)], [param("Clear", "bool")], graph=g)


def f_load_settings():
    g = G(); x = X(g, "ls")
    ex = x.do(K_GS, "DoesSaveGameExist", SlotName=names.SAVE_SLOT, UserIndex="0"); b = x.br("@%s.ReturnValue" % ex)
    ld = x.do(K_GS, "LoadGameFromSlot", SlotName=names.SAVE_SLOT, UserIndex="0")
    g.cast("ls_cast", names.SG, "@%s.ReturnValue" % ld, pure=False, miss="ignore")
    sg = "@ls_cast.AsSG VP Cat"
    sets = [x.setv(n, x.var(n, cls=names.SG, obj=sg)) for n, _, _ in B.SETTINGS + B.PLACE_VARS]
    # Size out of range (0 from an empty or older save) would divide by zero in x.scale() / VP_AnimSpeed
    clamp = x.setv("Size", x.m("FClamp", Value=x.var("Size"), Min=num(B.SIZE_MIN), Max=num(B.SIZE_MAX)))
    g.chain("entry", ex, b); g.chain(b + ":then", ld, "ls_cast", *sets, clamp)
    return fn("Load Settings", graph=g)


def f_save_settings():
    g = G(); x = X(g, "ss")
    mk = x.do(K_GS, "CreateSaveGameObject", SaveGameClass=names.SG_CLASS); sg = "@%s.ReturnValue" % mk
    sets = [x.setv(n, x.var(n), cls=names.SG, obj=sg) for n, _, _ in B.SETTINGS + B.PLACE_VARS]
    sv = x.do(K_GS, "SaveGameToSlot", SaveGameObject=sg, SlotName=names.SAVE_SLOT, UserIndex="0")
    g.chain("entry", mk, *sets, sv)
    return fn("Save Settings", graph=g)


def f_place_front():
    """Default Place Start (until vp_bp_home replaces it): on the floor 150 cm in front of Jodi, facing her, standing."""
    g = G(); x = X(g, "pf")
    jl = x.loc(x.var("Jodi")); front = x.vadd(jl, x.vmul(x.call(E_ACTOR, "GetActorForwardVector", self=x.var("Jodi")), 150.0))
    fa = x.do_self("Floor At", P=front)
    p = x.vsel("@%s.Hit" % fa, x.up("@%s.Loc" % fa, x.add(x.hh(), 2.0)), x.up(front, -60.0))
    tp = x.do_self("Teleport To", Loc=p, Yaw=x.yaw_to(p, jl))
    g.chain("entry", fa, tp, x.setv("State", B.ST_REST), x.setv("RestSince", x.now()), x.setv("Anchor", x.loc()))
    return fn("Place Start", graph=g)


def f_start_timers():
    g = G(); x = X(g, "st"); lv = x.var("Level")
    b1 = x.br(x.eqi(lv, B.LV_MISSION)); b2 = x.br(x.eqi(x.var("Level"), B.LV_OFFICE))
    g.chain("entry", b1); g.chain(b1 + ":then", x.timer("Enemy Scan", B.ENEMY_SCAN, loop=True), x.timer("Spot Scan", B.SPOT_SCAN, loop=True))
    g.chain(b1 + ":else", b2); g.chain(b2 + ":then", x.timer("Save Tick", B.SAVE_EVERY, loop=True))
    return fn("Start Timers", graph=g)


def core_functions(opts):
    return [f_think(), f_update_anim(), f_enable_body(), f_teleport_to(), f_floor_at(), f_line_clear(), f_load_settings(), f_save_settings(),
            f_place_front(), f_start_timers()]


def event_graph(g):
    x = X(g, "eg")
    want = lambda: x.self_fn("VP_WantHere", Active=x.var("Active"), Level=x.var("Level"), TakeAlong=x.var("TakeAlong"))
    # BeginPlay: menus -> gone; elsewhere the actor stays (hidden and still while she is off or stays home: AltUI keeps her page live)
    g.event("bp", E_ACTOR, "ReceiveBeginPlay")
    g.call("lvl", K_GS, "GetCurrentLevelName", inp={"bRemovePrefixString": "true"})       # not pure in 4.27: on the exec chain
    sl = x.setv("Level", x.self_fn("VP_LevelKind", Name="@lvl.ReturnValue"))
    bm = x.br(x.eqi(x.var("Level"), B.LV_NONE)); s = x.scale()
    g.chain("bp", x.do_self("Load Settings"), "lvl", sl, bm)
    g.chain(bm + ":then", x.do(E_ACTOR, "K2_DestroyActor", self=x.me()))
    g.chain(bm + ":else", x.do(E_CMC, "DisableMovement", self=x.var("CharacterMovement", cls=E_CHAR, obj=x.me())),
            x.do(E_ACTOR, "SetActorScale3D", self=x.me(), NewScale3D=x.vec(s, s, s)),
            x.do(E_ACTOR, "SetActorHiddenInGame", self=x.me(), bNewHidden="true"), x.do_self("Make Materials"), x.do_self("Apply Look"),
            x.do_self("Refresh Presence", Delay=num(B.PLACE_DELAY)))
    # Place Cat: still wanted? Jodi spawned? (IsValid guard, retried); tables and timers once per level
    g.custom("pce", "Place Cat")
    bw = x.br(want())
    pc = x.call(K_GS, "GetPlayerCharacter", PlayerIndex="0"); bv = x.br(x.call(K_SYS, "IsValid", Object=pc))
    inc = x.setv("PlaceTries", x.addi(x.var("PlaceTries"), 1)); bt = x.br(x.lti(x.var("PlaceTries"), B.PLACE_TRIES))
    ai = x.call(E_SKMC, "GetAnimInstance", self=x.var("Mesh", cls=E_CHAR, obj=x.me()))
    g.cast("pc_abp", names.ABP, ai, pure=True)
    q = x.seq(2); blr = x.br(x.not_(x.var("LevelReady")))
    g.chain("pce", bw); g.chain(bw + ":else", x.setv("Waking", "false"))
    g.chain(bw + ":then", bv); g.chain(bv + ":else", inc, bt); g.chain(bt + ":then", x.timer("Place Cat", B.PLACE_RETRY))
    g.chain(bt + ":else", x.setv("Waking", "false"))                         # no Jodi: stays dormant (AltUI keeps her page)
    g.chain(bv + ":then", x.setv("Jodi", pc), x.setv("Anim", "@pc_abp.%s" % ABP_CAST_PIN), q)
    g.chain(q + ":then_0", blr); g.chain(blr + ":then", x.do_self("Init Level"), x.do_self("Start Timers"), x.setv("LevelReady", "true"))
    g.chain(q + ":then_1", x.do(E_ACOMP, "SetComponentTickEnabled", self=x.var("Mesh", cls=E_CHAR, obj=x.me()), bEnabled="true"),
            x.do_self("Place Start"), x.do_self("Enable Body"), x.do(E_ACTOR, "SetActorHiddenInGame", self=x.me(), bNewHidden="false"),
            x.setv("Placed", "true"), x.setv("Waking", "false"))
    # Tick: only when placed and Jodi valid
    g.event("tk", E_ACTOR, "ReceiveTick")
    bp_ = x.br(x.var("Placed")); pc2 = x.call(K_GS, "GetPlayerCharacter", PlayerIndex="0"); bj = x.br(x.call(K_SYS, "IsValid", Object=pc2))
    g.chain("tk", bp_); g.chain(bp_ + ":then", bj)
    g.chain(bj + ":then", x.setv("Jodi", pc2), x.do_self("Think", DT="@tk.DeltaSeconds"), x.do_self("Update Anim", DT="@tk.DeltaSeconds"))
    # EndPlay (level change): keep the office place and anything not saved yet
    g.event("ep", E_ACTOR, "ReceiveEndPlay"); qe = x.seq(2)
    be = x.br(x.and_(x.var("Placed"), x.eqi(x.var("Level"), B.LV_OFFICE))); bs = x.br(x.var("SaveDue"))
    g.chain("ep", qe); g.chain(qe + ":then_0", be); g.chain(be + ":then", x.do_self("Save Place"))
    g.chain(qe + ":then_1", bs); g.chain(bs + ":then", x.setv("SaveDue", "false"), x.do_self("Save Settings"))


def cat_bp(modules, opts):
    funcs = {f["name"]: f for f in core_functions(opts)}
    variables_ = variables(); g = G()
    event_graph(g)
    for m in modules:
        variables_ += m.variables()
        for f in m.functions(opts):
            if f["name"] in funcs and f["name"] not in HOOKS: raise ValueError("function twice: " + f["name"])
            funcs[f["name"]] = f
        if hasattr(m, "events"): m.events(g, X(g, m.__name__.split("_")[-1]))
    for h in HOOKS:
        if h not in funcs: funcs[h] = _stub(h)
    vn = [v["name"] for v in variables_]
    if len(vn) != len(set(vn)): raise ValueError("variables twice: %s" % sorted({n for n in vn if vn.count(n) > 1}))
    return blueprint(names.BP, E_CHAR, variables=variables_, functions=list(funcs.values()), event_graph=g, defaults=dict(CLASS_DEFAULTS),
                     interfaces=list(opts.get("interfaces", ())))
