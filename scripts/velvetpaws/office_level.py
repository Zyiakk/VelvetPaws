"""Jodi's office as measured from the game: the cooked JodisOffice.umap (and the packages of the Blueprint furniture placed in it) read
with AltUI's uasset_props, every static mesh component with its world matrix (cm, column vectors), the player starts and the doors.
Doors are listed, not meshed: the cat's map treats them as open (runtime traces handle a closed one). CLI:
  office_level.py <extracted Content dir> <out actors.json>"""
import json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.environ.get("ALTUI_DEV") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "AltUI", "dev"), "scripts"))
from uasset_props import read_summary_bytes, clsname, Reader

UMAP = "Project/Maps/JodisOffice.umap"
SKIP_CLASSES = ("Door",)                 # class name parts whose meshes are left out (listed in "doors")
MESH_COMPONENTS = ("StaticMeshComponent",)


def rot_matrix(pitch, yaw, roll):
    """FRotationMatrix of an Unreal rotator, as a 3x3 for column vectors (columns = the rotated X, Y, Z axes)."""
    p, y, r = (math.radians(a) for a in (pitch, yaw, roll))
    SP, CP, SY, CY, SR, CR = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    X = (CP * CY, CP * SY, SP)
    Y = (SR * SP * CY - CR * SY, SR * SP * SY + CR * CY, -SR * CP)
    Z = (-(CR * SP * CY + SR * SY), CY * SR - CR * SP * SY, CR * CP)
    return np.array([X, Y, Z], dtype=float).T


def affine(loc, rot, scale):
    M = np.eye(4); M[:3, :3] = rot_matrix(*rot) @ np.diag(scale); M[:3, 3] = loc; return M


def _vec(d, k, default):
    v = d.get(k)
    if not isinstance(v, dict): return default
    if k == "RelativeRotation": return (v.get("pitch", 0.0), v.get("yaw", 0.0), v.get("roll", 0.0))
    return (v.get("x", default[0]), v.get("y", default[1]), v.get("z", default[2]))


def relative(props, base=None):
    """Relative transform of a component from its props, missing values from `base` (the Blueprint template) or the defaults."""
    b = base or {}
    loc = _vec(props, "RelativeLocation", _vec(b, "RelativeLocation", (0.0, 0.0, 0.0)))
    rot = _vec(props, "RelativeRotation", _vec(b, "RelativeRotation", (0.0, 0.0, 0.0)))
    sc = _vec(props, "RelativeScale3D", _vec(b, "RelativeScale3D", (1.0, 1.0, 1.0)))
    return affine(loc, rot, sc)


class Package:
    """One cooked package: exports as dicts {i, name, cls, outer, props}, imports, and import name -> package path."""

    def __init__(self, path):
        ux = path[:-len(os.path.splitext(path)[1])] + ".uexp"
        with open(path, "rb") as f: ua = f.read()
        ue = b""
        if os.path.exists(ux):
            with open(ux, "rb") as f: ue = f.read()
        d, names, self.imps, exps, _ = read_summary_bytes(ua); data = d + ue
        self.exports = []
        for i, (on, cls, sup, outer, ssz, soff) in enumerate(exps):
            cn = clsname(cls, self.imps, exps); r = Reader(data, names, self.imps, exps); r.p = soff
            try: props = r.props() if ssz else {}
            except Exception as e: props = {"__error__": str(e)}
            self.exports.append({"i": i + 1, "name": on, "cls": cn, "cls_index": cls, "super": sup, "outer": outer, "props": props})

    def imp_path(self, name, cls=None):
        """Package path of the import called `name` (e.g. a StaticMesh), via its outer package import."""
        for cp, cn, outer, on in self.imps:
            if on == name and (cls is None or cn == cls) and outer < 0: return self.imps[-outer - 1][3]
        return None

    def child(self, outer_i, name):
        return next((e for e in self.exports if e["outer"] == outer_i and e["name"] == name), None)


def _ref(v):   # "export:Name" / "import:Name (Class)" -> name
    return v.split(":", 1)[1].split(" (")[0] if isinstance(v, str) and ":" in v else None


def _class_package(pkg, actor):
    """Package path of a Blueprint actor's class (import <X>_C -> its outer package), or None for a native class."""
    ci = actor["cls_index"]
    if ci >= 0: return None
    cp, cn, outer, on = pkg.imps[-ci - 1]
    return pkg.imps[-outer - 1][3] if cn == "BlueprintGeneratedClass" and outer < 0 else None


def _templates(content, class_pkg, pkgs, missing, depth=0):
    """name -> props of the component templates (<name>_GEN_VARIABLE) of a Blueprint class, following its parent Blueprints (4 deep).
    Every class package tried goes into `pkgs` (the shell script extracts what is missing), each one not on disk into `missing`."""
    if not class_pkg or depth > 4 or not class_pkg.startswith("/Game/"): return {}
    pkgs.add(class_pkg)
    path = os.path.join(content, class_pkg[len("/Game/"):] + ".uasset")
    if not os.path.exists(path): missing.add(class_pkg); return {}
    p = Package(path); out = {}
    gen = next((e for e in p.exports if e["cls"] == "BlueprintGeneratedClass"), None)
    if gen and gen["super"] < 0:
        cp, cn, outer, on = p.imps[-gen["super"] - 1]
        if cn == "BlueprintGeneratedClass" and outer < 0: out.update(_templates(content, p.imps[-outer - 1][3], pkgs, missing, depth + 1))
    names_ = {e["i"]: e["name"] for e in p.exports}
    for e in p.exports:
        # SCS templates (<name>_GEN_VARIABLE) and the class default object's own components (e.g. StaticMeshComponent0 of a
        # Blueprint whose native parent is StaticMeshActor)
        if e["name"].endswith("_GEN_VARIABLE"): key = e["name"][:-len("_GEN_VARIABLE")]
        elif names_.get(e["outer"], "").startswith("Default__"): key = e["name"]
        else: continue
        props = dict(e["props"]); sm = _ref(props.get("StaticMesh"))
        if sm: props["__mesh__"] = p.imp_path(sm, "StaticMesh")
        out[key] = props
    return out


def read_level(content, umap_rel=UMAP):
    pkg = Package(os.path.join(content, umap_rel))
    out = {"meshes": [], "player_starts": [], "doors": [], "packages": set(), "warnings": []}; missing = set()
    level = next(e for e in pkg.exports if e["cls"] == "Level")
    actors = [e for e in pkg.exports if e["outer"] == level["i"] and e["cls"] not in ("Model", "BrushComponent")]
    for a in actors:
        comps = {e["name"]: e for e in pkg.exports if e["outer"] == a["i"]}
        cpkg = _class_package(pkg, a)
        tmpl = _templates(content, cpkg, out["packages"], missing) if cpkg else {}
        cache = {}

        def world(name, seen=()):
            if name in cache: return cache[name]
            e = comps.get(name)
            if e is None or name in seen: return np.eye(4)
            M = relative(e["props"], tmpl.get(name))
            parent = _ref(e["props"].get("AttachParent"))
            if parent: M = world(parent, seen + (name,)) @ M
            cache[name] = M; return M

        if a["cls"] == "PlayerStart":
            cap = comps.get("CollisionCapsule")
            M = world("CollisionCapsule") if cap else np.eye(4)
            out["player_starts"].append([*M[:3, 3].round(3).tolist(), _vec(cap["props"] if cap else {}, "RelativeRotation", (0, 0, 0))[1]])
            continue
        if any(s in a["cls"] for s in SKIP_CLASSES):
            root = _ref(a["props"].get("RootComponent"))
            M = world(root) if root else np.eye(4)
            out["doors"].append([*M[:3, 3].round(3).tolist(), math.degrees(math.atan2(M[1, 0], M[0, 0]))])
            continue
        for name, e in comps.items():
            is_mesh = e["cls"] in MESH_COMPONENTS or "__mesh__" in tmpl.get(name, {})   # also subclasses whose template has a mesh
            if not is_mesh: continue
            sm = _ref(e["props"].get("StaticMesh")); mesh = pkg.imp_path(sm, "StaticMesh") if sm else (tmpl.get(name) or {}).get("__mesh__")
            if not mesh:
                out["warnings"].append("%s.%s (%s): no static mesh" % (a["name"], name, a["cls"])); continue
            M = world(name)
            out["meshes"].append({"actor": a["name"], "cls": a["cls"], "comp": name, "mesh": mesh, "matrix": M.reshape(-1).round(6).tolist()})
            out["packages"].add(mesh)
    out["warnings"] += ["class package not extracted: %s" % m for m in sorted(missing)]
    out["packages"] = sorted(out["packages"])
    return out


def main(content, dst):
    L = read_level(content)
    with open(dst, "w") as f: json.dump(L, f, indent=1)
    print("LEVEL OK meshes=%d starts=%d doors=%d packages=%d warnings=%d" % (len(L["meshes"]), len(L["player_starts"]), len(L["doors"]),
                                                                              len(L["packages"]), len(L["warnings"])))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
