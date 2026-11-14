"""Sounds of BP_VP_Cat (plan Etappe 4). Play Cue: a one-shot attached to the head bone (SpawnSoundAttached, gain x Volume, pitch
by size and chance; Volume 0 plays nothing). Play Meow: the next variant (never the same twice). Cue(Id): the other modules report an
event; its sound follows brain.CUE_AT seconds later (the newest cue wins), fired by Sound Tick through Fire Cue. Sound Tick
(from Think): the regular meow by MeowRate (only awake), the greeting after a reunion (> 12 m for 20 s, then < 4 m), the purr loop
(one AudioComponent faded in and out by VP_PurrWant). Stop Sounds: purr out, nothing pending (stage 5: dormant cat).
Every wave is in SoundClass_SFX (scripts/import_sounds.py): the game's SFX volume comes on top of Volume."""
from bpdsl import G, fn, param, var, K_GS, K_SYS
from vp_expr import X, num, E_CHAR
from velvetpaws import brain as B, sounds as SN

E_AUDIO = "/Script/Engine.AudioComponent"; E_SOUNDBASE = "/Script/Engine.SoundBase"


def variables():
    F, I, Bo = "float", "int", "bool"
    return [var("SdNextMeow", F, default="0.0"), var("SdLastMeow", I, default="-1"), var("SdPick", I, default="0"),
            var("SdFarSince", F, default="-1.0"), var("SdPendCue", I, default=str(B.CUE_NONE)), var("SdPendAt", F, default="0.0"),
            var("SdPurring", Bo, default="false"), var("SdPurrAC", "object:" + E_AUDIO), var("SdReady", Bo, default="false")]


def _spawn(x, sound, volume, pitch, auto_destroy):
    mesh = x.var("Mesh", cls=E_CHAR, obj=x.me())
    return x.do(K_GS, "SpawnSoundAttached", Sound=sound, AttachToComponent=mesh, AttachPointName=SN.ATTACH_BONE,
                Location="(X=0.0,Y=0.0,Z=0.0)", Rotation=x.rot(0.0), LocationType="KeepRelativeOffset",
                bStopWhenAttachedToDestroyed="true", VolumeMultiplier=volume, PitchMultiplier=pitch, StartTime="0.0",
                bAutoDestroy="true" if auto_destroy else "false")


def _next_meow(x):
    return x.setv("SdNextMeow", x.add(x.now(), x.self_fn("VP_MeowInterval", Rate=x.var("MeowRate"), R=x.m("RandomFloat"))))


def _awake(x):
    return x.and_(x.nei(x.var("Posture"), B.P_SLEEP), x.not_(x.var("Alarmed")), x.nei(x.var("State"), B.ST_JUMP))


def f_play_cue():
    g = G(); x = X(g, "pc")
    b = x.br(x.gt(x.var("Volume"), 0.001))
    pitch = x.self_fn("VP_SoundPitch", Scale=x.scale(), R=x.m("RandomFloat"))
    g.chain("entry", b); g.chain(b + ":then", _spawn(x, "@entry.Sound", x.mul("@entry.Gain", x.var("Volume")), pitch, True))
    return fn("Play Cue", [param("Sound", "object:" + E_SOUNDBASE), param("Gain", "float")], graph=g)


def f_meow():  # named "Play Meow": a function "Meow" collides with the setting variable Meow (BPGen: no exec pin)
    g = G(); x = X(g, "mw"); n = SN.variants("Meow")
    b = x.br(x.and_(x.var("Meow"), x.var("Placed")))
    s1 = x.setv("SdPick", x.self_fn("VP_NextVariant", Last=x.var("SdLastMeow"), R=x.m("RandomFloat"), N=str(n)))
    s2 = x.setv("SdLastMeow", x.var("SdPick"))
    g.chain("entry", b); g.chain(b + ":then", s1, s2); prev = s2
    for i in range(n):
        c = x.br(x.eqi(x.var("SdPick"), i)); g.chain(prev, c)
        g.chain(c + ":then", x.do_self("Play Cue", Sound=SN.obj_path("Meow", i), Gain=num(SN.gain("Meow")))); prev = c + ":else"
    return fn("Play Meow", graph=g)


def f_cue():
    g = G(); x = X(g, "cu"); d = "0.0"
    for cid, t in sorted(B.CUE_AT.items()): d = x.sel(x.eqi("@entry.Id", cid), t, d)
    g.chain("entry", x.setv("SdPendCue", "@entry.Id"), x.setv("SdPendAt", x.add(x.now(), d)))
    return fn("Cue", [param("Id", "int")], graph=g)


def f_fire_cue():
    g = G(); x = X(g, "fc"); i = "@entry.Id"; prev = "entry"
    one = lambda name, k=0: x.do_self("Play Cue", Sound=SN.obj_path(name, k), Gain=num(SN.gain(name)))
    land = x.br(x.m("RandomBool"))
    for cid, body in ((B.CUE_HISS, [one("Hiss")]), (B.CUE_YAWN, [one("Yawn")]), (B.CUE_LAND, [land]),
                      (B.CUE_CALLED, [x.do_self("Play Meow")]), (B.CUE_GREET, [x.do_self("Play Meow")])):
        b = x.br(x.eqi(i, cid)); g.chain(prev, b); g.chain(b + ":then", *body); prev = b + ":else"
    g.chain(land + ":then", one("Land", 0)); g.chain(land + ":else", one("Land", 1))
    ba = x.br(x.and_(x.eqi(i, B.CUE_ARRIVED), x.lt(x.m("RandomFloat"), B.ARRIVE_MEOW)))
    g.chain(prev, ba); g.chain(ba + ":then", x.do_self("Play Meow"))
    return fn("Fire Cue", [param("Id", "int")], graph=g)


def f_sound_tick():
    g = G(); x = X(g, "st"); q = x.seq(5); g.chain("entry", q)
    dj = lambda: x.dist2d(x.loc(), x.loc(x.var("Jodi")))
    # (0) first tick after placing: regular meows from one interval on; she counts as long away (first approach = greeting)
    b0 = x.br(x.not_(x.var("SdReady")))
    g.chain(q + ":then_0", b0)
    g.chain(b0 + ":then", x.setv("SdReady", "true"), _next_meow(x), x.setv("SdFarSince", x.sub(x.now(), B.REUNION_AWAY)))
    # (1) a pending cue is due (read before it is cleared)
    b1 = x.br(x.and_(x.nei(x.var("SdPendCue"), B.CUE_NONE), x.ge(x.now(), x.var("SdPendAt"))))
    g.chain(q + ":then_1", b1); g.chain(b1 + ":then", x.do_self("Fire Cue", Id=x.var("SdPendCue")), x.setv("SdPendCue", B.CUE_NONE))
    # (2) the regular meow
    b2 = x.br(x.ge(x.now(), x.var("SdNextMeow"))); bw = x.br(_awake(x))
    g.chain(q + ":then_2", b2); g.chain(b2 + ":then", _next_meow(x), bw); g.chain(bw + ":then", x.do_self("Play Meow"))
    # (3) reunion
    bf = x.br(x.gt(dj(), B.REUNION_FAR)); bfs = x.br(x.lt(x.var("SdFarSince"), 0.0))
    bn = x.br(x.and_(x.lt(dj(), B.REUNION_NEAR), x.ge(x.var("SdFarSince"), 0.0)))
    bg = x.br(x.and_(x.ge(x.sub(x.now(), x.var("SdFarSince")), B.REUNION_AWAY), _awake(x)))
    reset = x.setv("SdFarSince", -1.0)
    g.chain(q + ":then_3", bf); g.chain(bf + ":then", bfs); g.chain(bfs + ":then", x.setv("SdFarSince", x.now()))
    g.chain(bf + ":else", bn); g.chain(bn + ":then", bg)
    g.chain(bg + ":then", x.do_self("Cue", Id=str(B.CUE_GREET)), reset); g.chain(bg + ":else", reset)
    # (4) purr
    want = lambda: x.and_(x.var("Purr"), x.self_fn("VP_PurrWant", State=x.var("State"), Posture=x.var("Posture"), Alarmed=x.var("Alarmed"),
                                                   Dist=dj(), Purring=x.var("SdPurring")))
    bs = x.br(x.and_(want(), x.not_(x.var("SdPurring")))); be = x.br(x.and_(x.not_(want()), x.var("SdPurring")))
    g.chain(q + ":then_4", bs); g.chain(bs + ":then", x.do_self("Start Purr")); g.chain(bs + ":else", be)
    g.chain(be + ":then", x.do_self("Stop Purr", Fade=num(B.PURR_FADE_OUT)))
    return fn("Sound Tick", graph=g)


def f_start_purr():
    """One AudioComponent for the loop, spawned silent and stopped the first time; then volume, pitch (size only) and a fade in."""
    g = G(); x = X(g, "sp"); ac = lambda: x.var("SdPurrAC")
    bv = x.br(x.call(K_SYS, "IsValid", Object=ac()))
    sp = _spawn(x, SN.obj_path("Purr"), "0.0", "1.0", False)
    vol = x.do(E_AUDIO, "SetVolumeMultiplier", self=ac(), NewVolumeMultiplier=x.mul(SN.gain("Purr"), x.var("Volume")))
    pit = x.do(E_AUDIO, "SetPitchMultiplier", self=ac(), NewPitchMultiplier=x.self_fn("VP_SoundPitch", Scale=x.scale(), R="0.5"))
    fi = x.do(E_AUDIO, "FadeIn", self=ac(), FadeInDuration=num(B.PURR_FADE_IN), FadeVolumeLevel="1.0", StartTime="0.0", FadeCurve="Linear")
    g.chain("entry", bv)
    g.chain(bv + ":else", sp, x.setv("SdPurrAC", "@%s.ReturnValue" % sp), x.do(E_AUDIO, "Stop", self=ac()), vol)
    g.chain(bv + ":then", vol); g.chain(vol, pit, fi, x.setv("SdPurring", "true"))
    return fn("Start Purr", graph=g)


def f_stop_purr():
    g = G(); x = X(g, "xp"); b = x.br(x.call(K_SYS, "IsValid", Object=x.var("SdPurrAC")))
    g.chain("entry", x.setv("SdPurring", "false"), b)
    g.chain(b + ":then", x.do(E_AUDIO, "FadeOut", self=x.var("SdPurrAC"), FadeOutDuration="@entry.Fade", FadeVolumeLevel="0.0", FadeCurve="Linear"))
    return fn("Stop Purr", [param("Fade", "float")], graph=g)


def f_stop_sounds():
    g = G(); x = X(g, "ss")
    g.chain("entry", x.setv("SdPendCue", B.CUE_NONE), x.setv("SdReady", "false"), x.do_self("Stop Purr", Fade=num(B.STOP_FADE)))
    return fn("Stop Sounds", graph=g)


def functions(opts):
    return [f_play_cue(), f_meow(), f_cue(), f_fire_cue(), f_sound_tick(), f_start_purr(), f_stop_purr(), f_stop_sounds()]
