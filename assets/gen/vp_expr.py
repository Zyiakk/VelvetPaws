"""Expression helper for the BP_VP_Cat generators (assets/gen/vp_bp_*.py): every method adds nodes to a bpdsl graph and returns either
the output reference "@id.Pin" (pure nodes) or the node id (exec nodes, for G.chain). Node ids carry a per-graph prefix, so several
modules can add to one event graph. Numbers become pin defaults through num(); ints through str()."""
from bpdsl import K_MATH, K_SYS, K_GS, K_STR, K_ARR, E_ACTOR
from velvetpaws import brain as B

VEC = "struct:/Script/CoreUObject.Vector"; ROT = "struct:/Script/CoreUObject.Rotator"
E = "/Script/Engine."
E_CHAR, E_CMC, E_PRIM, E_SKMC, E_ANIMI = E + "Character", E + "CharacterMovementComponent", E + "PrimitiveComponent", E + "SkeletalMeshComponent", E + "AnimInstance"
E_ACOMP = E + "ActorComponent"
E_PC, E_PCM, E_PAWN, E_MOVE = E + "PlayerController", E + "PlayerCameraManager", E + "Pawn", E + "MovementComponent"
NAV, NAVPATH = "/Script/NavigationSystem.NavigationSystemV1", "/Script/NavigationSystem.NavigationPath"
K_IN = "/Script/Engine.KismetInputLibrary"
TRACE_VIS = "TraceTypeQuery1"   # Visibility
TRACE_CAM = "TraceTypeQuery2"   # Camera: a closed door's leaf and its hidden doorway wall (InvisibleWallDynamic ignores only Visibility)


def num(v): return v if isinstance(v, str) else repr(float(v))


def _i(v): return v if isinstance(v, str) else str(int(v))


class X:
    def __init__(self, g, prefix):
        self.g, self.p, self.k = g, prefix, 0

    def nid(self, tag="n"):
        self.k += 1; return "%s_%s%d" % (self.p, tag, self.k)

    # ---- pure ----
    # "this" instead of "self": pin dicts carry a "self" key (the target pin)
    def call(this, cls, fn, out="ReturnValue", **inp):
        i = this.nid(); this.g.call(i, cls, fn, inp=inp); return "@%s.%s" % (i, out)

    def m(this, fn, out="ReturnValue", **inp): return this.call(K_MATH, fn, out, **inp)

    def self_fn(self, fn, out="Out", **inp):
        i = self.nid("f"); self.g.n(i, "call_self", function=fn, inp=inp); return "@%s.%s" % (i, out)

    def var(self, name, cls=None, obj=None):
        i = self.nid("g"); self.g.get(i, name, cls)
        if obj: self.g.link(obj.lstrip("@"), "%s.self" % i)
        return "@%s.%s" % (i, name)

    def me(self):
        i = self.nid("s"); self.g.self_(i); return "@%s.self" % i

    def now(self): return self.call(K_GS, "GetTimeSeconds")
    def add(self, a, b): return self.m("Add_FloatFloat", A=num(a), B=num(b))
    def sub(self, a, b): return self.m("Subtract_FloatFloat", A=num(a), B=num(b))
    def mul(self, a, b): return self.m("Multiply_FloatFloat", A=num(a), B=num(b))
    def div(self, a, b): return self.m("Divide_FloatFloat", A=num(a), B=num(b))
    def lt(self, a, b): return self.m("Less_FloatFloat", A=num(a), B=num(b))
    def gt(self, a, b): return self.m("Greater_FloatFloat", A=num(a), B=num(b))
    def le(self, a, b): return self.m("LessEqual_FloatFloat", A=num(a), B=num(b))
    def ge(self, a, b): return self.m("GreaterEqual_FloatFloat", A=num(a), B=num(b))
    def fmin(self, a, b): return self.m("FMin", A=num(a), B=num(b))
    def fmax(self, a, b): return self.m("FMax", A=num(a), B=num(b))
    def sel(self, cond, a, b): return self.m("SelectFloat", A=num(a), B=num(b), bPickA=cond)
    def abs_(self, a): return self.m("Abs", A=num(a))
    def sqrt(self, a): return self.m("Sqrt", A=num(a))
    def maprc(self, v, a, b, c, d): return self.m("MapRangeClamped", Value=v, InRangeA=num(a), InRangeB=num(b), OutRangeA=num(c), OutRangeB=num(d))
    def addi(self, a, b): return self.m("Add_IntInt", A=_i(a), B=_i(b))
    def subi(self, a, b): return self.m("Subtract_IntInt", A=_i(a), B=_i(b))
    def eqi(self, a, b): return self.m("EqualEqual_IntInt", A=_i(a), B=_i(b))
    def nei(self, a, b): return self.m("NotEqual_IntInt", A=_i(a), B=_i(b))
    def lti(self, a, b): return self.m("Less_IntInt", A=_i(a), B=_i(b))
    def gti(self, a, b): return self.m("Greater_IntInt", A=_i(a), B=_i(b))
    def gei(self, a, b): return self.m("GreaterEqual_IntInt", A=_i(a), B=_i(b))
    def seli(self, cond, a, b): return self.m("SelectInt", A=_i(a), B=_i(b), bPickA=cond)
    def b2i(self, b): return self.m("Conv_BoolToInt", InBool=b)
    def i2f(self, i): return self.m("Conv_IntToFloat", InInt=_i(i))
    def and_(self, *bs):
        out = bs[0]
        for b in bs[1:]: out = self.m("BooleanAND", A=out, B=b)
        return out
    def or_(self, *bs):
        out = bs[0]
        for b in bs[1:]: out = self.m("BooleanOR", A=out, B=b)
        return out
    def not_(self, b): return self.m("Not_PreBool", A=b)
    def vec(self, x, y, z): return self.m("MakeVector", X=num(x), Y=num(y), Z=num(z))
    def brk(self, v):
        i = self.nid("bv"); self.g.call(i, K_MATH, "BreakVector", inp={"InVec": v}); return "@%s.X" % i, "@%s.Y" % i, "@%s.Z" % i
    def vadd(self, a, b): return self.m("Add_VectorVector", A=a, B=b)
    def vsub(self, a, b): return self.m("Subtract_VectorVector", A=a, B=b)
    def vmul(self, a, f): return self.m("Multiply_VectorFloat", A=a, B=num(f))
    def vsel(self, cond, a, b): return self.m("SelectVector", A=a, B=b, bPickA=cond)
    def dist2d(self, a, b): return self.m("Vector_Distance2D", v1=a, v2=b)
    def dist(self, a, b): return self.m("Vector_Distance", v1=a, v2=b)
    def normal(self, v): return self.m("Normal", A=v, Tolerance="0.0001")
    def dot(self, a, b): return self.m("Dot_VectorVector", A=a, B=b)
    def dbg(self, code=None, count=None):
        """Exec steps of the spot diagnostic (brain.DEBUG_SPOTS): reason code DbgSpot and/or counter +1; none while it is off."""
        if not B.DEBUG_SPOTS: return []
        out = [self.setv("DbgSpot", code)] if code is not None else []
        if count: out.append(self.setv(count, self.addi(self.var(count), 1)))
        return out
    def then(self, src, steps):
        """g.chain(src, *steps) when there are steps (a chain needs two ids)."""
        if steps: self.g.chain(src, *steps)
    def up(self, v, dz): return self.vadd(v, self.vec(0, 0, dz))
    def yaw_to(self, a, b):
        i = self.nid("ry"); self.g.call(i, K_MATH, "BreakRotator", inp={"InRot": self.m("FindLookAtRotation", Start=a, Target=b)}); return "@%s.Yaw" % i
    def yaw_of(self, rot):
        i = self.nid("ry"); self.g.call(i, K_MATH, "BreakRotator", inp={"InRot": rot}); return "@%s.Yaw" % i
    def rot(self, yaw): return self.m("MakeRotator", Roll="0.0", Pitch="0.0", Yaw=num(yaw))
    def loc(self, obj=None): return self.call(E_ACTOR, "K2_GetActorLocation", self=obj or self.me())
    def arr1(self, obj):
        i = self.nid("ar"); self.g.n(i, "make_array", count=1, type="object:" + E_ACTOR, inp={"[0]": obj}); return "@%s.Array" % i
    def scale(self): return self.div(self.var("Size"), 100.0)
    def hh(self): return self.mul(self.scale(), B.CAPSULE_HH)          # capsule half height at the actor's scale

    # ---- exec ----
    def do(this, cls, fn, **inp):
        i = this.nid("x"); this.g.call(i, cls, fn, inp=inp); return i
    def do_self(self, fn, **inp):
        i = self.nid("c"); self.g.n(i, "call_self", function=fn, inp=inp); return i
    def setv(self, var, val, cls=None, obj=None):
        if isinstance(val, bool): val = "true" if val else "false"
        elif isinstance(val, int): val = _i(val)
        elif not isinstance(val, str): val = num(val)
        i = self.nid("v"); inp = {var: val}
        if obj: inp["self"] = obj
        self.g.set(i, var, **({"cls": cls} if cls else {}), inp=inp); return i
    def br(self, cond):
        i = self.nid("b"); self.g.branch(i, cond); return i
    def seq(self, n):
        i = self.nid("q"); self.g.seq(i, n); return i
    def ret(self, **out):
        """Result node. BPGen kind "return" is the graph's one primary K2Node_FunctionResult (every "return" node of a graph lands on
        it, the last pin defaults win), so only the first ret() of a graph uses it; every further one is a "return_new" (an extra
        result node with the same pins). Counted on the graph, not on X: one graph can have several X."""
        first = not getattr(self.g, "_vp_has_ret", False); self.g._vp_has_ret = True
        i = self.nid("r"); self.g.n(i, "return" if first else "return_new", inp=out); return i
    def timer(self, event, secs, loop=False):
        return self.do(K_SYS, "K2_SetTimer", Object=self.me(), FunctionName=event, Time=num(secs), bLooping="true" if loop else "false")
    def trace(self, a, b, ignore=None, channel=TRACE_VIS):
        """LineTraceSingle on Visibility (or `channel`) from a to b, ignoring self (and `ignore`); returns (id, hit, hit result)."""
        i = self.nid("t")
        inp = {"Start": a, "End": b, "TraceChannel": channel, "bTraceComplex": "false", "DrawDebugType": "None", "bIgnoreSelf": "true",
               "TraceColor": "(R=1,G=0,B=0,A=1)", "TraceHitColor": "(R=0,G=1,B=0,A=1)", "DrawTime": "0.0"}
        if ignore: inp["ActorsToIgnore"] = self.arr1(ignore)
        self.g.call(i, K_SYS, "LineTraceSingle", inp=inp); return i, "@%s.ReturnValue" % i, "@%s.OutHit" % i
    def hit(self, hitresult):
        i = self.nid("hb"); self.g.call(i, "/Script/Engine.GameplayStatics", "BreakHitResult", inp={"Hit": hitresult}); return i
    def loop(self, last, brk=False, first=0):
        i = self.nid("l"); self.g.n(i, "macro", name="ForLoopWithBreak" if brk else "ForLoop", inp={"First Index": _i(first), "Last Index": _i(last)}); return i
