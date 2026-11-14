"""Combat reaction of BP_VP_Cat (plan Etappe 3, Task 11; E19). Enemies: Character_Base actors that are not Jodi, no Character_NPC
(followers, story NPCs), Health > 0; scanned every 0.5 s in missions. Within 8 m: stand at once, face the enemy, arch and hiss once per
episode (cut short when the enemy is within 3 m), then flee onto a known high spot or behind Jodi; calm after 10 s with nobody within 10 m.
She is not a Character_Base, so the game's AI never targets her; her capsule ignores every trace channel.
On a low spot she hisses up there and then jumps down before fleeing (CbFromSpot: Flee goes through Start Move's spot branch)."""
from bpdsl import G, fn, param, var, K_SYS, K_GS, K_ARR, E_ACTOR
from vp_expr import X, num, VEC
from vp_bp_core import montage_ops
from velvetpaws import brain as B

P_CB = "/Game/Project/Classes/Character_Base"; P_CNPC = "/Game/Project/Character/Npc/Character_NPC"


def variables(): return [var("CbD", "float", default="0.0"), var("CbFromSpot", "bool", default="false")]


def f_enemy_place():
    """The enemy's place, or her own when there is no valid enemy. An exec branch, not a pure select (a select evaluates both inputs:
    the location of a None Enemy logs "Accessed None")."""
    g = G(); x = X(g, "ep"); b = x.br(x.call(K_SYS, "IsValid", Object=x.var("Enemy")))
    g.chain("entry", b); g.chain(b + ":then", x.ret(Loc=x.loc(x.var("Enemy")))); g.chain(b + ":else", x.ret(Loc=x.loc()))
    return fn("Enemy Place", [], [param("Loc", VEC)], graph=g)


def flee_goal(x, ep): return x.self_fn("VP_FleeGoal", Jodi=x.loc(x.var("Jodi")), Enemy="@%s.Loc" % ep)


def events(g, x):
    g.custom("cb_scan", "Enemy Scan")
    ga = x.do(K_GS, "GetAllActorsOfClass", ActorClass=P_CB + ".Character_Base_C")
    g.foreach("cb_fe", "@%s.OutActors" % ga)
    el = "@cb_fe.Array Element"
    g.cast("cb_npc", P_CNPC, el, pure=True); g.cast("cb_base", P_CB, el, pure=True)
    health = x.var("Health", cls=P_CB, obj="@cb_base.AsCharacter Base")
    sd = x.setv("CbD", x.dist(x.loc(), x.loc(el)))
    cand = x.and_(x.not_(x.m("EqualEqual_ObjectObject", A=el, B=x.var("Jodi"))), x.not_(x.call(K_SYS, "IsValid", Object="@cb_npc.AsCharacter NPC")),
                  x.call(K_SYS, "IsValid", Object="@cb_base.AsCharacter Base"), x.gt(health, 0.0), x.lt(x.var("CbD"), x.var("EnemyDist")))
    bc = x.br(cand)
    near = x.br(x.lt(x.var("EnemyDist"), B.ENEMY_CALM_R)); start = x.br(x.and_(x.lt(x.var("EnemyDist"), B.ENEMY_NEAR), x.not_(x.var("Alarmed"))))
    bpl = x.br(x.var("Placed"))
    g.chain("cb_scan", bpl); g.chain(bpl + ":then", x.setv("EnemyDist", 1e5), ga, "cb_fe"); g.chain("cb_fe", sd, bc)
    g.chain(bc + ":then", x.setv("EnemyDist", x.var("CbD")), x.setv("Enemy", el))
    g.chain("cb_fe:Completed", near); g.chain(near + ":then", x.setv("LastEnemy", x.now()), start)
    g.chain(start + ":then", x.setv("Alarmed", "true"), x.do_self("Begin Alarm"))


def f_begin_alarm():
    g = G(); x = X(g, "ba")
    bj = x.br(x.eqi(x.var("State"), B.ST_JUMP))
    on_spot = x.eqi(x.var("State"), B.ST_SPOT)
    safe = x.and_(on_spot, x.ge(x.var("SpotHeight"), B.HIGH_SPOT)); bs = x.br(safe)
    bh = x.br(x.not_(x.var("Hissed")))
    g.chain("entry", bj); g.chain(bj + ":else", bs)          # in a jump: decided after landing; on a high spot: stays
    g.chain(bs + ":else", x.setv("CbFromSpot", x.eqi(x.var("State"), B.ST_SPOT)),     # low spot: hisses up there, jumps down to flee
            *montage_ops(x, [("stop", None, 0.2)]), x.setv("Posture", B.P_STAND), x.setv("WantPosture", B.P_STAND),
            x.setv("AfterOp", B.AFTER_NONE), x.setv("State", B.ST_ALARM), x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")), bh)
    g.chain(bh + ":then", x.setv("Hissed", "true"), *montage_ops(x, [("play", B.HISS[0])]), x.setv("BusyUntil", x.add(x.now(), B.HISS[1])),
            x.do_self("Cue", Id=str(B.CUE_HISS)))
    g.chain(bh + ":else", x.setv("BusyUntil", x.now()))
    return fn("Begin Alarm", graph=g)


def f_face_enemy():
    g = G(); x = X(g, "fe")
    cur = x.call(E_ACTOR, "K2_GetActorRotation", self=x.me())
    # the pure turn is read only by the setter behind the IsValid branch, so a None Enemy is never touched
    r = x.m("RInterpTo", Current=cur, Target=x.rot(x.yaw_to(x.loc(), x.loc(x.var("Enemy")))), DeltaTime="@entry.DT", InterpSpeed=num(B.TURN_RATE))
    b = x.br(x.call(K_SYS, "IsValid", Object=x.var("Enemy")))
    g.chain("entry", b); g.chain(b + ":then", x.do(E_ACTOR, "K2_SetActorRotation", self=x.me(), NewRotation=r, bTeleportPhysics="false"))
    return fn("Face Enemy", [param("DT", "float")], graph=g)


def f_tick_alarm():
    g = G(); x = X(g, "ta")
    b = x.br(x.or_(x.ge(x.now(), x.var("BusyUntil")), x.lt(x.var("EnemyDist"), B.HISS_ABORT)))
    g.chain("entry", x.do_self("Face Enemy", DT="@entry.DT"), b)
    g.chain(b + ":then", *montage_ops(x, [("stop", B.HISS[0], 0.15)]), x.do_self("Flee"))
    return fn("Tick Alarm", [param("DT", "float")], graph=g)


def f_flee():
    g = G(); x = X(g, "fl"); ep = x.do_self("Enemy Place")
    high = x.and_(x.var("SpotValid"), x.ge(x.var("SpotHeight"), B.HIGH_SPOT), x.lt(x.dist2d(x.loc(), x.var("SpotFrom")), B.FLEE_SPOT_R),
                  x.gt(x.dist2d("@%s.Loc" % ep, x.var("SpotLoc")), x.var("EnemyDist")))
    b = x.br(high); bsp = x.br(x.var("CbFromSpot"))
    g.chain("entry", ep, bsp)
    # still up on a (low) spot: Start Move's spot branch jumps down first and then walks behind Jodi
    g.chain(bsp + ":then", x.setv("CbFromSpot", "false"), x.setv("State", B.ST_SPOT), x.do_self("Start Move", Purpose=str(B.GO_FLEE), To=flee_goal(x, ep)))
    g.chain(bsp + ":else", x.setv("State", B.ST_REST), b)
    g.chain(b + ":then", x.do_self("Start Move", Purpose=str(B.GO_SPOT), To=x.var("SpotFrom")))
    g.chain(b + ":else", x.do_self("Start Move", Purpose=str(B.GO_FLEE), To=flee_goal(x, ep)))
    return fn("Flee", graph=g)


def f_alarm_rest():
    """Resting while alarmed (after fleeing): standing, facing the enemy; flees again (once a second) when the enemy is still near and she
    is away from the point behind Jodi."""
    g = G(); x = X(g, "ar"); ep = x.do_self("Enemy Place")
    again = x.and_(x.call(K_SYS, "IsValid", Object=x.var("Enemy")), x.lt(x.var("EnemyDist"), B.ENEMY_NEAR), x.ge(x.now(), x.var("RepathAt")),
                   x.gt(x.dist2d(x.loc(), flee_goal(x, ep)), 150.0))
    b = x.br(again)
    g.chain("entry", x.setv("WantPosture", B.P_STAND), x.do_self("Posture Step"), x.do_self("Face Enemy", DT=x.var("TickDT")), ep, b)
    g.chain(b + ":then", x.setv("RepathAt", x.add(x.now(), 1.0)), x.do_self("Flee"))
    return fn("Alarm Rest", graph=g)


def f_combat_tick():
    g = G(); x = X(g, "ct")
    calm = x.and_(x.var("Alarmed"), x.gt(x.sub(x.now(), x.var("LastEnemy")), B.CALM_TIME)); b = x.br(calm)
    ba = x.br(x.eqi(x.var("State"), B.ST_ALARM))
    g.chain("entry", b); g.chain(b + ":then", x.setv("Alarmed", "false"), x.setv("Hissed", "false"), x.setv("CbFromSpot", "false"), ba)
    g.chain(ba + ":then", *montage_ops(x, [("stop", B.HISS[0], 0.2)]), x.setv("State", B.ST_REST), x.setv("RestSince", x.now()))
    return fn("Combat Tick", graph=g)


def functions(opts):
    return [f_enemy_place(), f_begin_alarm(), f_face_enemy(), f_tick_alarm(), f_flee(), f_alarm_rest(), f_combat_tick()]
