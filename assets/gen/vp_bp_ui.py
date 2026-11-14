"""AltUI page of BP_VP_Cat (plan Etappe 5; AltUI's MOD_UI.md; layout in scripts/velvetpaws/ui.py). The look at runtime:
dynamic instances of the fur, fur card and eye slots (Make Materials, once per actor), colours, pattern weights and white marks
(Apply Look); the size live (Apply Size: scaled and lifted by the capsule's growth); the volume of a running purr (Apply Volume).
Presence (Refresh Presence, Go Dormant) and saving (Save Soon, event Save Now); BPI_AltUIMod: the page reads the settings
(Get AltUI Value/Color/Text/Key, Status Text) and every change is applied and saved (On AltUI Changed/Color/Text/Key Changed)."""
import modui as mu
from bpdsl import G, fn, param, var, K_SYS, K_ARR, K_STR, E_ACTOR
from vp_expr import X, num, E_CHAR, E_CMC, E_PRIM, E_ACOMP
from vp_bp_core import montage_ops
from velvetpaws import names, brain as B, ui as UI, sounds as SN

E_MID = "/Script/Engine.MaterialInstanceDynamic"; E_AUDIO = "/Script/Engine.AudioComponent"
SLOT_INDEX = {s: i for i, s in enumerate(names.SLOTS)}     # FBX slot order = the mesh's material index


def variables():
    return [var(v, "object:" + E_MID) for v in sorted(set(UI.MID.values()))] + [var("UiOldScale", "float", default="1.0")]


def f_make_materials():
    g = G(); x = X(g, "mm")
    b = x.br(x.not_(x.call(K_SYS, "IsValid", Object=x.var(UI.MID["Fur"])))); steps = []
    for slot, v in sorted(UI.MID.items()):
        c = x.do(E_PRIM, "CreateDynamicMaterialInstance", self=x.var("Mesh", cls=E_CHAR, obj=x.me()), ElementIndex=str(SLOT_INDEX[slot]),
                 OptionalName="None")
        steps += [c, x.setv(v, "@%s.ReturnValue" % c)]
    g.chain("entry", b); g.chain(b + ":then", *steps)
    return fn("Make Materials", graph=g)


def f_apply_look():
    g = G(); x = X(g, "al")
    ok = x.and_(*[x.call(K_SYS, "IsValid", Object=x.var(v)) for v in sorted(set(UI.MID.values()))])
    b = x.br(ok); steps = []
    for slot, p, src in UI.LOOK:
        mid = x.var(UI.MID[slot])
        if src == "@white":
            steps.append(x.do(E_MID, "SetScalarParameterValue", self=mid, ParameterName=p, Value=x.self_fn("VP_WhiteMarks", P=x.var("Pattern"))))
        else:
            val = x.self_fn("VP_PatternWeights", P=x.var("Pattern")) if src == "@pattern" else x.var(src)
            steps.append(x.do(E_MID, "SetVectorParameterValue", self=mid, ParameterName=p, Value=val))
    g.chain("entry", b); g.chain(b + ":then", *steps)
    return fn("Apply Look", graph=g)


def f_apply_size():
    g = G(); x = X(g, "as")
    _, _, oz = x.brk(x.call(E_ACTOR, "GetActorScale3D", self=x.me()))
    s = x.scale(); b = x.br(x.var("Placed"))
    lift = x.vec(0.0, 0.0, x.mul(x.sub(x.scale(), x.var("UiOldScale")), B.CAPSULE_HH))
    g.chain("entry", x.setv("UiOldScale", oz), x.do(E_ACTOR, "SetActorScale3D", self=x.me(), NewScale3D=x.vec(s, s, s)), b)
    g.chain(b + ":then", x.do(E_ACTOR, "K2_AddActorWorldOffset", self=x.me(), DeltaLocation=lift, bSweep="false", bTeleport="true"))
    return fn("Apply Size", graph=g)


def f_apply_volume():
    g = G(); x = X(g, "av")
    b = x.br(x.and_(x.var("SdPurring"), x.call(K_SYS, "IsValid", Object=x.var("SdPurrAC"))))
    g.chain("entry", b)
    g.chain(b + ":then", x.do(E_AUDIO, "SetVolumeMultiplier", self=x.var("SdPurrAC"), NewVolumeMultiplier=x.mul(SN.gain("Purr"), x.var("Volume"))))
    return fn("Apply Volume", graph=g)


def f_refresh_presence():
    """Wanted here (VP_WantHere) and neither placed nor on the way: Place Cat after Delay. Not wanted but placed or on the way: dormant."""
    g = G(); x = X(g, "rp")
    want = x.self_fn("VP_WantHere", Active=x.var("Active"), Level=x.var("Level"), TakeAlong=x.var("TakeAlong"))
    busy = lambda: x.or_(x.var("Placed"), x.var("Waking"))
    bw = x.br(want); bwk = x.br(x.not_(busy())); bd = x.br(busy())
    g.chain("entry", bw)
    g.chain(bw + ":then", bwk); g.chain(bwk + ":then", x.setv("Waking", "true"), x.setv("PlaceTries", 0), x.timer("Place Cat", "@entry.Delay"))
    g.chain(bw + ":else", bd); g.chain(bd + ":then", x.do_self("Go Dormant"))
    return fn("Refresh Presence", [param("Delay", "float")], graph=g)


def f_go_dormant():
    g = G(); x = X(g, "gd"); q = x.seq(3)
    ba = x.br(x.call(K_SYS, "IsValid", Object=x.var("Anim")))
    cap = x.var("CapsuleComponent", cls=E_CHAR, obj=x.me())
    g.chain("entry", q)
    g.chain(q + ":then_0", x.do_self("Save Place"))                       # office and placed only (guarded inside)
    g.chain(q + ":then_1", ba); g.chain(ba + ":then", *montage_ops(x, [("stop", None, 0.2)]))
    g.chain(q + ":then_2", x.do_self("Stop Sounds"), x.setv("Placed", "false"), x.setv("Waking", "false"), x.setv("State", B.ST_REST),
            x.setv("Alarmed", "false"), x.setv("Hissed", "false"), x.setv("CbFromSpot", "false"), x.setv("JumpPhase", B.JP_NONE),
            x.setv("Posture", B.P_STAND), x.setv("WantPosture", B.P_STAND), x.setv("AfterOp", B.AFTER_NONE),
            x.do(K_ARR, "Array_Clear", TargetArray=x.var("Waypoints")),
            x.do(E_ACTOR, "SetActorHiddenInGame", self=x.me(), bNewHidden="true"),
            # hidden, the mesh would still tick its pose every frame (AlwaysTickPose); Place Cat switches it on again
            x.do(E_ACOMP, "SetComponentTickEnabled", self=x.var("Mesh", cls=E_CHAR, obj=x.me()), bEnabled="false"),
            x.do(E_PRIM, "SetCollisionEnabled", self=cap, NewType="NoCollision"),
            x.do(E_CMC, "DisableMovement", self=x.var("CharacterMovement", cls=E_CHAR, obj=x.me())))
    return fn("Go Dormant", graph=g)


def f_save_soon():
    g = G(); x = X(g, "sn")
    g.chain("entry", x.setv("SaveDue", "true"), x.timer("Save Now", B.SAVE_SOON))   # a new timer on the same event restarts it
    return fn("Save Soon", graph=g)


def _eq(x, key, k): return x.m("EqualEqual_NameName", A=key, B=k)


def _s(x, a, b, pick): return x.m("SelectString", A=a, B=b, bPickA=pick)


def _cat(x, *parts):
    out = parts[0]
    for p in parts[1:]: out = x.call(K_STR, "Concat_StrStr", A=out, B=p)
    return out


def f_status_text():
    """The Info line (ui.status): '<name or The cat>: <what she does>'."""
    g = G(); x = X(g, "tx")
    who = _s(x, UI.NO_NAME, x.var("CatName"), x.call(K_STR, "IsEmpty", InString=x.var("CatName")))
    mode = UI.MODE_WORDS[-1]
    for k in range(len(UI.MODE_WORDS) - 2, -1, -1): mode = _s(x, UI.MODE_WORDS[k], mode, x.eqi(x.var("Mode"), k))
    post = UI.POSTURE_WORDS[-1]
    for k in range(len(UI.POSTURE_WORDS) - 2, -1, -1): post = _s(x, UI.POSTURE_WORDS[k], post, x.eqi(x.var("Posture"), k))
    post = _s(x, UI.DOING["rub"], post, x.eqi(x.var("State"), B.ST_RUB))
    doing = _s(x, UI.DOING["alarm"], _s(x, UI.DOING["move"], _s(x, UI.DOING["jump"], post, x.eqi(x.var("State"), B.ST_JUMP)),
                                         x.eqi(x.var("State"), B.ST_MOVE)), x.var("Alarmed"))
    here = _cat(x, mode, ", ", doing, _s(x, UI.PURRING, "", x.var("SdPurring")))
    home = x.and_(x.eqi(x.var("Level"), B.LV_MISSION), x.not_(x.var("TakeAlong")))
    where = _s(x, UI.OFF, _s(x, UI.HOME, _s(x, UI.COMING, here, x.not_(x.var("Placed"))), home), x.not_(x.var("Active")))
    line = _cat(x, who, ": ", where)
    if B.DEBUG_SPOTS:   # ui.spot_debug: built only when AltUI reads the line
        its = lambda v: x.call(K_STR, "Conv_IntToString", InInt=v)
        word = UI.DBG_WORDS[-1]
        for k in range(len(UI.DBG_WORDS) - 2, -1, -1): word = _s(x, UI.DBG_WORDS[k], word, x.eqi(x.var("DbgSpot"), k))
        n = x.call(K_ARR, "Array_Length", TargetArray=x.var("SpotsLoc"))
        line = _cat(x, line, " | spot: ", word, " #", its(x.var("SpotIdx")), " ok", its(x.var("DbgOK")), "/", its(n), " r",
                    its(x.var("DbgPicks")), " t", its(x.var("DbgTries")), " j", its(x.var("DbgJumps")))
    g.chain("entry", x.ret(Out=line))
    return fn("Status Text", outputs=[param("Out", "string")], graph=g, pure=True)


def f_get_value():
    g = G(); x = X(g, "gv"); out = "0.0"
    for k, (kind, scale, _, _) in UI.VALUES.items():
        v = x.var(k)
        val = x.sel(v, 1.0, 0.0) if kind == "bool" else (x.i2f(v) if kind == "int" else x.mul(v, scale))
        out = x.sel(_eq(x, "@entry.Key", k), val, out)
    g.chain("entry", x.ret(Value=out))
    return fn(mu.GET_VALUE, graph=g)


def f_get_color():
    g = G(); x = X(g, "gc"); out = x.var(UI.COLORS[0])
    for k in UI.COLORS[1:]: out = x.m("SelectColor", A=x.var(k), B=out, bPickA=_eq(x, "@entry.Key", k))
    g.chain("entry", x.ret(Color=out))
    return fn(mu.GET_COLOR, graph=g)


def f_get_text():
    g = G(); x = X(g, "gt")
    g.chain("entry", x.ret(Text=_s(x, x.var("CatName"), x.self_fn("Status Text"), _eq(x, "@entry.Key", "CatName"))))
    return fn(mu.GET_TEXT, graph=g)


def f_get_key():
    g = G(); x = X(g, "gk"); g.chain("entry", x.ret(Pressed=x.var("RecallKey")))
    return fn(mu.GET_KEY, graph=g)


def _after(x, k, v):
    """Exec steps for value field k with the converted value v (only this field's nodes are built)."""
    if k == "Mode": return [x.do_self("Set Mode", M=v)]
    s = x.setv(k, v)
    if k in ("Active", "TakeAlong"): return [s, x.do_self("Refresh Presence", Delay=num(B.WAKE_DELAY)), x.do_self("Save Settings")]
    if k == "Pattern": return [s, x.do_self("Apply Look"), x.do_self("Save Settings")]
    if k == "Size": return [s, x.do_self("Apply Size"), x.do_self("Save Soon")]
    if k in ("StayMin", "StayMax"):                          # at least <= at most: moving one past the other pushes the other along
        o = "StayMax" if k == "StayMin" else "StayMin"
        push = x.setv(o, x.fmax(x.var(o), x.var(k)) if k == "StayMin" else x.fmin(x.var(o), x.var(k)))
        return [s, push, x.do_self("Save Soon")]
    if k == "Volume": return [s, x.do_self("Apply Volume"), x.do_self("Save Soon")]
    if k == "MeowRate":
        return [s, x.setv("SdNextMeow", x.add(x.now(), x.self_fn("VP_MeowInterval", Rate=x.var("MeowRate"), R=x.m("RandomFloat")))), x.do_self("Save Soon")]
    return [s, x.do_self("Save Settings")]                   # Meow, Purr


def _convert(x, k, val):
    kind, scale, lo, hi = UI.VALUES[k]
    if kind == "bool": return x.gt(val, 0.5)
    if kind == "int": return x.m("Clamp", Value=x.m("Round", A=val), Min=str(int(lo)), Max=str(int(hi)))
    return x.m("FClamp", Value=x.div(val, scale), Min=num(lo), Max=num(hi))


def events(g, x):
    g.custom("ui_sn", "Save Now"); b = x.br(x.var("SaveDue"))
    g.chain("ui_sn", b); g.chain(b + ":then", x.setv("SaveDue", "false"), x.do_self("Save Settings"))
    # On AltUI Changed: value fields, the Call her button, the quick menu's mode actions
    g.event("ui_oc", mu.INTERFACE_CLASS, mu.ON_CHANGED); prev = "ui_oc"
    for k in UI.VALUES:
        b = x.br(_eq(x, "@ui_oc.Key", k)); g.chain(prev, b); g.chain(b + ":then", *_after(x, k, _convert(x, k, "@ui_oc.Value"))); prev = b + ":else"
    b = x.br(_eq(x, "@ui_oc.Key", UI.BUTTON_RECALL)); bpl = x.br(x.var("Placed"))
    g.chain(prev, b); g.chain(b + ":then", bpl); g.chain(bpl + ":then", x.do_self("Recall")); prev = b + ":else"
    for k, _, mode in UI.ACTIONS:
        b = x.br(_eq(x, "@ui_oc.Key", k)); g.chain(prev, b); g.chain(b + ":then", x.do_self("Set Mode", M=str(mode))); prev = b + ":else"
    # colours: live while picking, saved soon after
    g.event("ui_occ", mu.INTERFACE_CLASS, mu.ON_COLOR); prev = "ui_occ"
    for k in UI.COLORS:
        b = x.br(_eq(x, "@ui_occ.Key", k)); g.chain(prev, b)
        g.chain(b + ":then", x.setv(k, "@ui_occ.Color"), x.do_self("Apply Look"), x.do_self("Save Soon")); prev = b + ":else"
    # text (the name) and the recall key: saved at once
    g.event("ui_oct", mu.INTERFACE_CLASS, mu.ON_TEXT); bt = x.br(_eq(x, "@ui_oct.Key", UI.TEXTS[0]))
    g.chain("ui_oct", bt); g.chain(bt + ":then", x.setv(UI.TEXTS[0], "@ui_oct.Text"), x.do_self("Save Settings"))
    g.event("ui_ock", mu.INTERFACE_CLASS, mu.ON_KEY); bk = x.br(_eq(x, "@ui_ock.Key", UI.KEYS[0]))
    g.chain("ui_ock", bk); g.chain(bk + ":then", x.setv(UI.KEYS[0], "@ui_ock.Pressed"), x.do_self("Save Settings"))


def functions(opts):
    return [f_make_materials(), f_apply_look(), f_apply_size(), f_apply_volume(), f_refresh_presence(), f_go_dormant(), f_save_soon(),
            f_status_text(), f_get_value(), f_get_color(), f_get_text(), f_get_key()]
