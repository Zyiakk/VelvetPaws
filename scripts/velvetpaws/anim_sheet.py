"""Contact sheets of the cat animations from the tiles of tools/blender/cat_anims.py.
Usage: build/venv/bin/python scripts/velvetpaws/anim_sheet.py <build/velvetpaws/review/anim>
Writes VP_Cat_<Name>.png (one row per view, one column per frame, labelled 'f12 0.40 s', header with the gates from measures.json)
and for the group 'gait' gait_<Name>.png (footfall bars hl, fl, hr, fr over one cycle, black where the paw is on the floor).
Prints SHEETS OK <n>."""
import json, os, re, sys

from PIL import Image, ImageDraw, ImageFont

FPS = 30
BG, FG, DIM = (30, 30, 34), (235, 235, 235), (150, 150, 158)
VIEW_ORDER = ("left", "front", "back", "top", "hleft", "hq", "hfront")


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def gates(m):
    if not m: return ["no measures"]
    rt = m.get("fbx_round_trip") or {}
    a = "IK miss %.3f cm (free %.3f)   plant %.3f cm   floor %.2f cm   loop %.3f cm" % (
        m.get("ik_miss_cm", 0), m.get("ik_miss_free_cm", 0), m.get("plant_cm", 0), m.get("floor_min_cm", 0), m.get("loop_cm", 0))
    if m.get("slide_cm"): a += "   slide %s" % ", ".join("%s %.3f" % kv for kv in m["slide_cm"].items())
    b = "FBX: joints %.4f cm, root %.6f, frames %s, rest %.6f cm" % (rt.get("worst_cm", -1), rt.get("root_moved", -1), rt.get("frames", "?"),
                                                                    rt.get("rest_cm", -1)) if rt else "FBX: not checked"
    return [a, b] + (["warnings: " + "; ".join(m["warnings"])] if m.get("warnings") else [])


def contact_sheet(name, tdir, m, out):
    tiles = {}
    for fn in os.listdir(tdir):
        g = re.match(r"([a-z]+)_(\d+)\.png$", fn)
        if g: tiles[(g.group(1), int(g.group(2)))] = os.path.join(tdir, fn)
    if not tiles: return False
    views = [v for v in VIEW_ORDER if any(k[0] == v for k in tiles)] + sorted({k[0] for k in tiles} - set(VIEW_ORDER))
    frames = sorted({k[1] for k in tiles})
    tw, th = Image.open(next(iter(tiles.values()))).size
    lab, head, cap = 60, 22 * (1 + len(gates(m))) + 6, 18
    W, H = lab + tw * len(frames), head + (th + cap) * len(views)
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img); f14, f12 = font(15), font(12)
    n = m.get("frames", frames[-1]) if m else frames[-1]
    d.text((8, 4), "VP_Cat_%s   %d frames   %.2f s   %s" % (name, n, n / FPS, m.get("group", "") if m else ""), fill=FG, font=f14)
    for i, line in enumerate(gates(m)): d.text((8, 26 + 22 * i), line, fill=DIM, font=f12)
    for r, v in enumerate(views):
        y = head + r * (th + cap); d.text((6, y + th // 2), v, fill=FG, font=f12)
        for c, f in enumerate(frames):
            x = lab + c * tw
            if (v, f) in tiles: img.paste(Image.open(tiles[(v, f)]).convert("RGB"), (x, y))
            d.text((x + 4, y + th + 2), "f%d %.2f s" % (f, f / FPS), fill=DIM, font=f12)
    img.save(out); return True


def gait_sheet(name, m, out):
    n = m["frames"]; legs = ("hl", "fl", "hr", "fr"); px, lab, bar, gap, top = 6, 40, 22, 8, 30
    W = lab + px * n + 10; H = top + len(legs) * (bar + gap) + 24
    img = Image.new("RGB", (W, H), (245, 245, 245)); d = ImageDraw.Draw(img); f12 = font(12)
    d.text((6, 6), "VP_Cat_%s footfall over one cycle (%d frames, black = paw on the floor)" % (name, n), fill=(0, 0, 0), font=f12)
    for r, leg in enumerate(legs):
        y = top + r * (bar + gap); on = set(m["contacts"].get(leg, [])); d.text((6, y + 4), leg, fill=(0, 0, 0), font=f12)
        for f in range(n):
            d.rectangle((lab + f * px, y, lab + (f + 1) * px - 1, y + bar), fill=(0, 0, 0) if f in on else (205, 205, 210))
    for f in range(0, n + 1, 10):
        x = lab + f * px; d.line((x, top - 4, x, H - 22), fill=(120, 120, 255)); d.text((x - 6, H - 20), str(f), fill=(0, 0, 0), font=f12)
    img.save(out)


def main(rdir):
    mpath = os.path.join(rdir, "measures.json"); meas = json.load(open(mpath)) if os.path.exists(mpath) else {}
    tdir = os.path.join(rdir, "tiles"); count = 0
    for name in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        m = meas.get(name, {})
        if contact_sheet(name, os.path.join(tdir, name), m, os.path.join(rdir, "VP_Cat_%s.png" % name)): count += 1
        if m.get("group") == "gait" and "contacts" in m: gait_sheet(name, m, os.path.join(rdir, "gait_%s.png" % name))
    print("SHEETS OK %d" % count)


if __name__ == "__main__":
    main(sys.argv[1])
