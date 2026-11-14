"""Samples Jodi's office for the cat's map (Etappe 3, E10): reads build/velvetpaws/office/actors.json and the umodel glTF of every mesh,
places the triangles in Unreal space (cm; glTF from umodel is 0.01 * (x, z, y) of Unreal), builds one BVH and casts rays straight down
on a 5 cm grid over the office rooms, up to K surfaces per column (from the top, each next ray starts 0.5 cm under the last hit).
Everything higher than CUT above the floor (ceilings, the level's 600 cm top plate, high cupboard tops) is no use to the cat: of
those hits only the lowest is kept, as the column's lid in layer 0, so the other layers reach down to the floor under furniture.
The region is first the room shells' bounding box (+1 m), then cropped to the columns with a surface below the cut (+1 m): the top
plate of Office_Room_A spans about 26 x 20 m, far beyond the rooms.
Gates: the region holds every player start; under at least 3 of the 4 starts there is floor 92 cm below the capsule centre (+-10) and
the column is free from 5 to 180 cm above it. Usage: blender -b --python office_scan.py -- <office dir>"""
import json, math, os, struct, sys
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

CELL, K, ROOM_PART, MARGIN = 5.0, 8, "/Maps/JodisOffice/Office", 100.0
CUT, MAX_RAYS = 240.0, 64   # cm above the floor under the player starts; rays per column at most
COMP = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def gltf_path(gdir, mesh):
    rel = mesh[len("/Game/"):]
    for cand in (os.path.join(gdir, "Game", rel + ".gltf"), os.path.join(gdir, rel + ".gltf")):
        if os.path.exists(cand): return cand
    return None


def _load_json(path):
    with open(path) as f: return json.load(f)


def read_gltf(path):
    """All triangles of a glTF from umodel: (vertices (n, 3) in Unreal cm, triangles (m, 3))."""
    g = _load_json(path); bins = {}
    def acc(i):
        a = g["accessors"][i]; bv = g["bufferViews"][a["bufferView"]]; b = g["buffers"][bv["buffer"]]
        if bv["buffer"] not in bins:
            with open(os.path.join(os.path.dirname(path), b["uri"]), "rb") as f: bins[bv["buffer"]] = f.read()
        n = NCOMP[a["type"]]; fmt = COMP[a["componentType"]]; size = struct.calcsize(fmt)
        stride = bv.get("byteStride", n * size); off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        raw = bins[bv["buffer"]]
        arr = np.frombuffer(raw, dtype=np.dtype(fmt).newbyteorder("<"), count=(a["count"] - 1) * stride // size + n, offset=off)
        return arr.reshape(-1, stride // size)[:, :n] if stride != n * size else arr.reshape(-1, n)
    V, T = [], []; base = 0
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4: continue
            p = acc(prim["attributes"]["POSITION"]).astype(float)
            idx = acc(prim["indices"]).reshape(-1).astype(np.int64) if "indices" in prim else np.arange(len(p))
            V.append(np.stack([p[:, 0], p[:, 2], p[:, 1]], 1) * 100.0); T.append(idx.reshape(-1, 3) + base); base += len(p)
    return (np.concatenate(V), np.concatenate(T)) if V else (np.zeros((0, 3)), np.zeros((0, 3), np.int64))


def main(odir):
    A = _load_json(os.path.join(odir, "actors.json")); gdir = os.path.join(odir, "gltf")
    verts, polys, owner, missing, cache = [], [], [], set(), {}
    base = 0
    for mi, m in enumerate(A["meshes"]):
        if m["mesh"] not in cache:
            p = gltf_path(gdir, m["mesh"]); cache[m["mesh"]] = read_gltf(p) if p else None
            if p is None: missing.add(m["mesh"])
        data = cache[m["mesh"]]
        if data is None or not len(data[1]): continue
        M = np.array(m["matrix"]).reshape(4, 4); v = (M[:3, :3] @ data[0].T).T + M[:3, 3]
        verts.append(v); polys.append(data[1] + base); owner.append(np.full(len(data[1]), mi)); base += len(v)
    V = np.concatenate(verts); T = np.concatenate(polys); OWN = np.concatenate(owner)
    print("SCAN meshes=%d triangles=%d missing=%d" % (len(A["meshes"]), len(T), len(missing)))
    for m in sorted(missing): print("SCAN missing", m)
    # region: bounding box of the office room shells (+1 m), must hold every player start
    floor0 = float(np.median([s[2] for s in A["player_starts"]])) - 92.0; cut = floor0 + CUT
    room_v = [V[T[OWN == mi].reshape(-1)] for mi, m in enumerate(A["meshes"]) if ROOM_PART in m["mesh"] and (OWN == mi).any()]
    rv = np.concatenate(room_v); top = float(rv[:, 2].max() + 50.0); x0, y0 = rv[:, 0].min() - MARGIN, rv[:, 1].min() - MARGIN; x1, y1 = rv[:, 0].max() + MARGIN, rv[:, 1].max() + MARGIN
    for x, y, z, _ in A["player_starts"]:
        if not (x0 <= x <= x1 and y0 <= y <= y1): raise SystemExit("SCAN FAIL player start %s outside the region" % ((x, y),))
    bvh = BVHTree.FromPolygons([Vector(p) for p in V.tolist()], T.tolist(), all_triangles=True, epsilon=0.0)
    nx, ny = int(math.ceil((x1 - x0) / CELL)), int(math.ceil((y1 - y0) / CELL))
    Z = np.full((nx, ny, K), np.nan, np.float32); NZ = np.full((nx, ny, K), np.nan, np.float32); INST = np.full((nx, ny, K), -1, np.int32)
    down = Vector((0.0, 0.0, -1.0))
    for i in range(nx):
        x = x0 + (i + 0.5) * CELL
        for j in range(ny):
            y = y0 + (j + 0.5) * CELL; z = top; k = 0; lid = None
            for _ in range(MAX_RAYS):
                loc, nrm, face, dist = bvh.ray_cast(Vector((x, y, z)), down, z - (-500.0))
                if loc is None: break
                z = loc.z - 0.5
                if loc.z > cut: lid = (loc.z, nrm.z, OWN[face]); continue
                if lid is not None: Z[i, j, 0], NZ[i, j, 0], INST[i, j, 0] = lid; lid = None; k = 1
                if k >= K: break
                Z[i, j, k] = loc.z; NZ[i, j, k] = nrm.z; INST[i, j, k] = OWN[face]; k += 1
            if lid is not None: Z[i, j, 0], NZ[i, j, 0], INST[i, j, 0] = lid
    low = (~np.isnan(Z) & (Z <= cut)).any(2); ii, jj = np.where(low); m = int(MARGIN / CELL)
    i0, i1, j0, j1 = int(max(0, ii.min() - m)), int(min(nx, ii.max() + 1 + m)), int(max(0, jj.min() - m)), int(min(ny, jj.max() + 1 + m))
    Z, NZ, INST = Z[i0:i1, j0:j1], NZ[i0:i1, j0:j1], INST[i0:i1, j0:j1]; full_region = [x0, y0, x1, y1]
    x0, y0 = x0 + i0 * CELL, y0 + j0 * CELL; nx, ny = i1 - i0, j1 - j0; x1, y1 = x0 + nx * CELL, y0 + ny * CELL; hits = int((~np.isnan(Z)).sum())
    for x, y, z, _ in A["player_starts"]:
        if not (x0 <= x <= x1 and y0 <= y <= y1): raise SystemExit("SCAN FAIL player start %s outside the cropped region" % ((x, y),))
    gates = {"starts_ok": 0, "floor_sign": []}
    for x, y, z, _ in A["player_starts"]:
        i, j = int((x - x0) // CELL), int((y - y0) // CELL); ok = ~np.isnan(Z[i, j]); col = Z[i, j][ok]; nzc = NZ[i, j][ok]
        floor = z - 92.0; near = np.abs(col - floor) <= 10.0
        free = not ((col > floor + 5.0) & (col < floor + 180.0)).any()
        gates["starts_ok"] += int(near.any() and free)
        if near.any(): gates["floor_sign"].append(float(np.sign(nzc[near][0])))
    if gates["starts_ok"] < 3: raise SystemExit("SCAN FAIL floor under only %d of 4 player starts" % gates["starts_ok"])
    # face winding after the glTF round trip decides the normal's sign: the floor under the starts must face up
    signs = set(gates["floor_sign"])
    if len(signs) != 1: raise SystemExit("SCAN FAIL floor normals disagree under the starts: %s" % gates["floor_sign"])
    NZ *= signs.pop()
    np.savez_compressed(os.path.join(odir, "scan.npz"), z=Z, nz=NZ, inst=INST)
    full = ~np.isnan(Z[:, :, K - 1]); lowest = np.nanmin(np.where(np.isnan(Z), np.inf, Z), axis=2)
    no_floor = int((full & (lowest > floor0 + 5.0)).sum())
    with open(os.path.join(odir, "scan.json"), "w") as f: json.dump({"origin": [x0, y0], "cell": CELL, "nx": nx, "ny": ny, "top": top, "cut": cut, "full_no_floor": no_floor, "region": [x0, y0, x1, y1], "shell_region": full_region,
               "meshes": [{k: m[k] for k in ("actor", "cls", "comp", "mesh")} for m in A["meshes"]],
               "player_starts": A["player_starts"], "doors": A["doors"], "gates": gates}, f, indent=1)
    print("SCAN OK nx=%d ny=%d hits=%d starts_ok=%d/4 full_columns=%d full_no_floor=%d" % (nx, ny, hits, gates["starts_ok"], int(full.sum()), no_floor))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
