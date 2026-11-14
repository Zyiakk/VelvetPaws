"""Editor test (AltUI edtest.sh, after BPGen built 91_velvetpaws.json): the cat's animation blueprint, blend space, montages, slot and overlay
as built in the kit (BPGenAnimLib.DescribeAnim / DescribeAnimAsset). Sequence lengths and skeletons are read from DescribeAnim's ANIM line."""
import os, re, sys
import unreal
W = os.environ.get("VELVETPAWS_DEV") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(W, "scripts"), os.path.join(W, "tools", "blender"), os.path.join(os.environ["ALTUI_DEV"], "tests", "editor")]
from velvetpaws import names
import cat_seqs as CS
from edtest_lib import report, expect, run


def lines(path, fn):
    out = list(fn(unreal.load_asset(path)))
    for l in out: unreal.log_warning("EDTEST info %s" % l)
    return out


def fields(line): return dict(m.groups() for m in re.finditer(r"(\w+)=(\S+)", line))


def main():
    L = lines(names.ABP, unreal.BPGenAnimLib.describe_anim_asset)
    head = fields(L[0])
    expect("abp skeleton and status (3 = up to date)", (L[0].split()[1], head.get("skeleton"), head.get("status")),
           ("ABP_VP_Cat", names.obj(names.SKELETON), "3"))
    nodes = [l.split()[1] for l in L if l.startswith("NODE")]
    for cls in ("AnimGraphNode_BlendSpacePlayer", "AnimGraphNode_Slot", "AnimGraphNode_SequencePlayer", "AnimGraphNode_ApplyAdditive", "AnimGraphNode_Root"):
        expect("abp has " + cls, nodes.count(cls), 1)
    expect("abp slot", [l for l in L if "AnimGraphNode_Slot" in l and l.startswith("NODE")][0].split(" ", 2)[2], "slot=DefaultSlot group=DefaultGroup")
    report("abp overlay additive", any(("VP_Cat_Overlay" in l and "additive=1" in l) for l in L))
    expect("abp blend space", [fields(l).get("blendspace") for l in L if l.startswith("NODE AnimGraphNode_BlendSpacePlayer")], [names.obj(names.BLENDSPACE)])
    B = lines(names.BLENDSPACE, unreal.BPGenAnimLib.describe_anim_asset)
    bh = fields(B[0])
    expect("bs axis", (bh.get("axis"), float(bh["min"]), float(bh["max"]), int(bh["grid"])), (names.VAR_SPEED, 0.0, CS.SPEED_MAX, CS.SPEED_GRID))
    expect("bs samples", [(fields(l)["anim"].rsplit(".", 1)[1], float(fields(l)["value"])) for l in B if l.startswith("SAMPLE")],
           [("VP_Cat_" + n, v) for n, v in CS.BLEND_SAMPLES])
    expect("bs elements", sum(1 for l in B if l.startswith("ELEMENT")), CS.SPEED_GRID + 1)
    for m in CS.MONTAGES:
        D = lines(names.montage(m["name"]), unreal.BPGenAnimLib.describe_anim)
        expect("montage %s slot" % m["name"], [l.split()[2] for l in D if l.startswith("SLOT")], ["DefaultSlot"])
        expect("montage %s sections" % m["name"], [(l.split()[2], fields(l)["next"]) for l in D if l.startswith("SECTION")],
               [(n, nx or "None") for n, _, nx in CS.section_times(m)])
        expect("montage %s segments" % m["name"], [fields(l)["anim"].rsplit(".", 1)[1] for l in D if l.startswith("SEGMENT")],
               ["VP_Cat_" + s for _, s, _ in m["sections"]])
    for n in CS.ORDER:
        a = unreal.load_asset(names.seq(n))
        if not report("sequence %s exists" % n, a is not None): continue
        f = fields(unreal.BPGenAnimLib.describe_anim(a)[0])
        expect("sequence %s skeleton" % n, f.get("skeleton"), names.obj(names.SKELETON))
        report("sequence %s length" % n, abs(float(f["length"]) - CS.length(n)) < 1e-3, "%s vs %s" % (f["length"], CS.length(n)))


run(main)
