"""The cat's map of Jodi's office from the sampled level (office_scan.py): walk surface, walk points with links and next-hop strings,
lie spots with take-off points; writes assets/office/office_map.json and a top view for the visual check. Rules: plan Etappe 3, Task 5.
CLI: office_map.py <office dir> <out json> <out png>"""
import heapq, json, math, os, sys
from collections import deque
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from velvetpaws import brain as B

STAND_NZ, CLEAR, STEP = 0.9, 35.0, 12.0
GRID, SNAP, DOOR_SNAP, LINK, MAX_POINTS = 75.0, 30.0, 40.0, 160.0, 450   # plan: 400; the office needs 401 (Task 5 report)
SPOT_NZ, SPOT_CLEAR, SPOT_FLAT, SPOT_R, LIE_R, SLEEP_R = 0.95, 30.0, 2.0, 9.5, 18.0, 28.0   # SPOT_R plan: 12; 9.5 (check `r >= SPOT_R`) takes the 15 cm window sills (chamfer radius 10.0) with 0.5 cm margin
FROM_OUT, FROM_MAX, BODY, PER_INSTANCE, SPOT_SEP = 45.0, 120.0, 25.0, 2, 60.0
OPEN_ROOM = 999.0   # "room" of a spot with nothing above it within the scan (cm): free headroom for any jump
COVERED = 80.0      # a spot with less room above it is covered (a shelf compartment): the jump arc stays under the board above
ROOM_MARGIN = 4.0   # cm between the capsule's top at the arc's apex and the board above (brain.ROOM_MARGIN at runtime)
CUBBY_R = B.CAPSULE_R   # a compartment needs the capsule's radius free around the spot (the cat walks or jumps all the way in)
SHELF_LIMIT, SHELF_SEP = 6, 45.0   # shelf units: up to 6 spots (compartments), 45 cm apart
DOOR_RUN = (60.0, 115.0)   # a doorway: 60-115 cm of the door's local -Y side where a 120 cm line along its X axis is all walk surface
DOOR_PROBE = 40.0, 20.0    # door probes: this far each side of the doorway centre along its X axis, this high over its floor
LEDGE_IN = 1.0   # window sill narrower than the capsule: the spot sits this far inside the sill's room-side edge (see ledge)
# (name pattern on actor + mesh + class, neutral type, weight, posture cap or None, spots per instance); first match wins. Patterns are matched
# against the lower-case actor name first, then the mesh and class names (see kind_of). Desk clutter and the sink are never spots.
EXCLUDE = ("printer", "keyboard", "paper", "folder", "mousepad", "mouse_pad", "document", "monitor", "lamp", "phone", "mug", "sink")
KINDS = (("bed_table", "bedside", 1.0, None, 2), ("bedtable", "bedside", 1.0, None, 2), ("mattress", "bed", 3.0, B.P_SLEEP, 1), ("bed", "bed", 3.0, B.P_SLEEP, 1),
         ("armchair", "armchair", 3.0, None, 2), ("sofa", "sofa", 3.0, None, 2), ("couch", "sofa", 3.0, None, 2), ("window", "window", 2.0, None, 1),
         ("desk", "desk", 1.5, None, 2), ("tablec", "table", 1.0, None, 2), ("filecabinet", "cabinet", 1.0, None, 2), ("cupboard", "cupboard", 1.0, None, 2),
         ("hyperbox", "box", 1.0, None, 2), ("bookshelf", "shelf", 1.0, None, 2), ("shelf", "shelf", 1.0, None, 2), ("bench", "bench", 1.0, None, 2),
         ("room_c", "counter", 1.0, B.P_LIE, 2), ("toilet", "toilet", 0.5, B.P_LIE, 1), ("chair", "chair", 1.0, None, 2))


def kind_of(m):
    """(type, weight, posture cap, spots per instance) of a mesh instance, None = never a spot. The computer chair is a chair although its
    mesh is called ArmchairA; the bedside table is not a bed."""
    actor = m["actor"].lower(); other = (m["mesh"] + m["cls"]).lower(); full = actor + " " + other
    if any(x in full for x in EXCLUDE): return None
    if "chair" in actor and "armchair" not in actor: return ("chair", 1.0, None, 2)
    for key, typ, wt, cap, n in KINDS:
        if key in actor: return (typ, wt, cap, n)
    for key, typ, wt, cap, n in KINDS:
        if key in other: return (typ, wt, cap, n)
    return ("misc", 1.0, None, 2)


class Scan:
    def __init__(self, z, nz, inst, origin, cell, meshes, player_starts, doors):
        self.z, self.nz, self.inst, self.origin, self.cell = z, nz, inst, origin, cell
        self.meshes, self.player_starts, self.doors = meshes, player_starts, doors
        self.nx, self.ny, self.K = z.shape

    @classmethod
    def load(cls, odir):
        with np.load(os.path.join(odir, "scan.npz")) as a, open(os.path.join(odir, "scan.json")) as f:
            j = json.load(f); z, nz, inst = a["z"], a["nz"], a["inst"]
        act = os.path.join(odir, "actors.json")     # the instances' world matrices (same order as scan.json): their axes square the facing
        if os.path.exists(act):
            with open(act) as f: am = json.load(f)["meshes"]
            if len(am) == len(j["meshes"]) and all(x["actor"] == y["actor"] and x["comp"] == y["comp"] for x, y in zip(am, j["meshes"])):
                for x, y in zip(am, j["meshes"]): y["matrix"] = x["matrix"]
        return cls(z, nz, inst, tuple(j["origin"]), j["cell"], j["meshes"], j["player_starts"], j["doors"])

    def cell_of(self, x, y): return int((x - self.origin[0]) // self.cell), int((y - self.origin[1]) // self.cell)
    def pos(self, i, j): return self.origin[0] + (i + 0.5) * self.cell, self.origin[1] + (j + 0.5) * self.cell
    def inside(self, i, j): return 0 <= i < self.nx and 0 <= j < self.ny

    def clearance(self, i, j, k):
        return np.inf if k == 0 or np.isnan(self.z[i, j, k - 1]) else float(self.z[i, j, k - 1] - self.z[i, j, k])


def walk_surface(S):
    """H[i, j] = height of the reached stand surface (NaN = not walkable), flood-filled from the player starts."""
    H = np.full((S.nx, S.ny), np.nan); q = deque()
    stand = lambda i, j, k: not np.isnan(S.z[i, j, k]) and S.nz[i, j, k] > STAND_NZ and S.clearance(i, j, k) >= CLEAR
    for x, y, zc, _ in S.player_starts:
        i, j = S.cell_of(x, y)
        for k in range(S.K):
            if stand(i, j, k) and abs(S.z[i, j, k] - (zc - 92.0)) <= 10.0 and np.isnan(H[i, j]): H[i, j] = S.z[i, j, k]; q.append((i, j))
    while q:
        i, j = q.popleft(); h = H[i, j]
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if not S.inside(a, b): continue
            for k in range(S.K):
                if stand(a, b, k) and abs(S.z[a, b, k] - h) <= STEP:
                    if np.isnan(H[a, b]) or S.z[a, b, k] < H[a, b]:
                        if np.isnan(H[a, b]): q.append((a, b))
                        H[a, b] = S.z[a, b, k]
                    break
    return H


def erode(H, r):
    """Cells whose disc of r cells is all walk surface without a step over STEP to the centre."""
    ok = ~np.isnan(H); nx, ny = H.shape; Hp = np.pad(H, r, constant_values=np.nan); E = ok.copy()
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if di * di + dj * dj > r * r: continue
            N = Hp[r + di:r + di + nx, r + dj:r + dj + ny]
            E &= ~np.isnan(N) & (np.abs(np.nan_to_num(N, nan=1e9) - np.nan_to_num(H, nan=0.0)) <= STEP)
    return E


def nearest_cell(E, S, x, y, radius):
    ci, cj = S.cell_of(x, y); r = int(math.ceil(radius / S.cell)); best = None
    for i in range(ci - r, ci + r + 1):
        for j in range(cj - r, cj + r + 1):
            if S.inside(i, j) and E[i, j]:
                d = (i - ci) ** 2 + (j - cj) ** 2
                if d * S.cell ** 2 <= radius ** 2 and (best is None or d < best[0]): best = (d, i, j)
    return None if best is None else best[1:]


def line_ok(E, H, S, a, b):
    (x0, y0), (x1, y1) = S.pos(*a), S.pos(*b); n = max(1, int(math.hypot(x1 - x0, y1 - y0) / S.cell)); last = H[a]
    for t in range(n + 1):
        i, j = S.cell_of(x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n)
        if not S.inside(i, j) or not E[i, j] or abs(H[i, j] - last) > STEP: return False
        last = H[i, j]
    return True


def doorways(S, H):
    """Doorways of the level's door actors (office_level lists them, the map counts them as open): per door the centre of the gap, the
    crossing axis n (the door actor's X axis) and the gap's half width, or None when no bounded gap of DOOR_RUN width lies on the actor's
    -Y side (the hinge is at the actor's root, the leaf spans local Y 0..-86 cm; the apartment's entrance leads out of the walk surface).
    A closed leaf stands in the gap; the probes A/B (DOOR_PROBE) on both sides are what the Blueprint traces between."""
    def walk(x, y):
        i, j = S.cell_of(x, y); return S.inside(i, j) and not np.isnan(H[i, j])
    out = []
    for x, y, _, yaw in S.doors:
        a = math.radians(yaw); n = (math.cos(a), math.sin(a)); u = (-math.sin(a), math.cos(a))
        ok = [off for off in range(-150, 5, 5) if all(walk(x + u[0] * off + n[0] * t, y + u[1] * off + n[1] * t) for t in range(-60, 61, 5))]
        run = []
        for o in sorted(ok, reverse=True):              # the run that starts at the hinge (offset 0) and goes to -Y
            if (not run and o >= -5) or (run and run[-1] - o == 5): run.append(o)
            elif run: break
        width = (run[0] - run[-1] + 5) if run else 0
        if not run or not DOOR_RUN[0] <= width <= DOOR_RUN[1] or run[-1] <= -150: out.append(None); continue
        mid = (run[0] + run[-1]) / 2.0; cx, cy = x + u[0] * mid, y + u[1] * mid
        i, j = S.cell_of(cx, cy); fz = float(H[i, j]) if S.inside(i, j) and not np.isnan(H[i, j]) else 0.0
        a_, b_ = [(round(cx + sg * n[0] * DOOR_PROBE[0], 1), round(cy + sg * n[1] * DOOR_PROBE[0], 1), round(fz + DOOR_PROBE[1], 1)) for sg in (-1, 1)]
        out.append({"centre": (cx, cy), "n": n, "u": u, "half": width / 2.0, "a": a_, "b": b_})
    return out


def _cross(p, q, c, u, half):
    """Segment p-q crosses the doorway line c +- half * u."""
    d = (q[0] - p[0], q[1] - p[1]); e = (2 * half * u[0], 2 * half * u[1]); s0 = (c[0] - half * u[0], c[1] - half * u[1])
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9: return False
    w = (s0[0] - p[0], s0[1] - p[1]); t = (w[0] * e[1] - w[1] * e[0]) / den; v = (w[0] * d[1] - w[1] * d[0]) / den
    return 0.0 <= t <= 1.0 and 0.0 <= v <= 1.0


def walk_graph(S, H, E, doors=None):
    x0, y0 = S.origin; pts = []
    for gx in np.arange(x0 + GRID / 2, x0 + S.nx * S.cell, GRID):
        for gy in np.arange(y0 + GRID / 2, y0 + S.ny * S.cell, GRID):
            c = nearest_cell(E, S, gx, gy, SNAP)
            if c and c not in pts: pts.append(c)
    door_pt = {}                                     # point index -> doorway index: every way through a doorway passes its point
    for k, dw in enumerate(doors if doors is not None else [None] * len(S.doors)):
        if dw is None:                                   # no doorway found (the entrance): a plain point at the door actor, as before
            x, y = S.doors[k][:2]; c = nearest_cell(E, S, x, y, DOOR_SNAP)
            if c and c not in pts: pts.append(c)
            continue
        c = nearest_cell(E, S, dw["centre"][0], dw["centre"][1], DOOR_SNAP)
        if c is None: continue
        if c in pts: pts.remove(c)
        pts.append(c); door_pt[len(pts) - 1] = k
    n = len(pts); adj = [dict() for _ in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            d = math.dist(S.pos(*pts[a]), S.pos(*pts[b]))
            if d > LINK or not line_ok(E, H, S, pts[a], pts[b]): continue
            pa, pb = S.pos(*pts[a]), S.pos(*pts[b])
            if any(k not in (door_pt.get(a), door_pt.get(b)) and dw is not None and _cross(pa, pb, dw["centre"], dw["u"], dw["half"] + 10.0)
                   for k, dw in enumerate(doors or [])): continue
            adj[a][b] = adj[b][a] = d
    comp = [-1] * n; comps = []
    for s in range(n):
        if comp[s] >= 0: continue
        stack, members = [s], []; comp[s] = len(comps)
        while stack:
            u = stack.pop(); members.append(u)
            for v in adj[u]:
                if comp[v] < 0: comp[v] = comp[s]; stack.append(v)
        comps.append(members)
    keep = sorted(max(comps, key=len)) if comps else []
    if len(keep) > MAX_POINTS: raise SystemExit("MAP FAIL %d walk points (max %d)" % (len(keep), MAX_POINTS))
    idx = {o: i for i, o in enumerate(keep)}
    adj2 = [{idx[v]: w for v, w in adj[o].items() if v in idx} for o in keep]
    return [pts[o] for o in keep], adj2, len(comps) - 1, n - len(keep), {idx[o]: k for o, k in door_pt.items() if o in idx}


def next_hops(adj):
    n = len(adj); nxt = [[-1] * n for _ in range(n)]
    for b in range(n):
        dist = [math.inf] * n; dist[b] = 0.0; h = [(0.0, b)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u]: continue
            for v, w in adj[u].items():
                if d + w < dist[v]: dist[v] = d + w; heapq.heappush(h, (dist[v], v))
        for i in range(n):
            if i == b: nxt[i][b] = b
            elif dist[i] < math.inf: nxt[i][b] = min(adj[i], key=lambda v: adj[i][v] + dist[v])
    return nxt


def chamfer(mask):
    """Distance (cells) to the nearest cell outside `mask`, 3-4 chamfer, two passes."""
    INF = 1e9; D = np.where(mask, INF, 0.0); nx, ny = D.shape
    for i in range(nx):
        for j in range(ny):
            if D[i, j]:
                for di, dj, w in ((-1, 0, 3), (0, -1, 3), (-1, -1, 4), (-1, 1, 4)):
                    a, b = i + di, j + dj
                    D[i, j] = min(D[i, j], (D[a, b] if 0 <= a < nx and 0 <= b < ny else 0.0) + w)
    for i in range(nx - 1, -1, -1):
        for j in range(ny - 1, -1, -1):
            if D[i, j]:
                for di, dj, w in ((1, 0, 3), (0, 1, 3), (1, 1, 4), (1, -1, 4)):
                    a, b = i + di, j + dj
                    D[i, j] = min(D[i, j], (D[a, b] if 0 <= a < nx and 0 <= b < ny else 0.0) + w)
    return D / 3.0


def floor_of(S, H, i, j):
    col = [S.z[i, j, k] for k in range(S.K) if not np.isnan(S.z[i, j, k]) and S.nz[i, j, k] > STAND_NZ]
    return H[i, j] if not np.isnan(H[i, j]) else (min(col) if col else np.nan)


def spots(S, H, E):
    """Lie spots: flat raised regions per mesh instance with a valid take-off point on the walk surface."""
    seen = np.zeros((S.nx, S.ny, S.K), bool); found = []
    floor0 = float(np.nanmin(H))
    for i0 in range(S.nx):
        for j0 in range(S.ny):
            for k0 in range(S.K):
                if seen[i0, j0, k0] or np.isnan(S.z[i0, j0, k0]): continue
                if S.nz[i0, j0, k0] <= SPOT_NZ or S.clearance(i0, j0, k0) < SPOT_CLEAR: continue
                h = S.z[i0, j0, k0] - floor0; mi = S.inst[i0, j0, k0]
                if not (B.SPOT_MIN <= h <= B.JUMP_MAX or low_cubby(S, i0, j0, k0, h)): continue
                region = []; q = deque([(i0, j0, k0)]); seen[i0, j0, k0] = True
                while q:
                    i, j, k = q.popleft(); region.append((i, j, k))
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        a, b = i + di, j + dj
                        if not S.inside(a, b): continue
                        for kk in range(S.K):
                            if (not seen[a, b, kk] and S.inst[a, b, kk] == mi and not np.isnan(S.z[a, b, kk]) and S.nz[a, b, kk] > SPOT_NZ
                                    and abs(S.z[a, b, kk] - S.z[i, j, k]) <= SPOT_FLAT and S.clearance(a, b, kk) >= SPOT_CLEAR):
                                seen[a, b, kk] = True; q.append((a, b, kk)); break
                found.append((mi, region))
    out = []; by_inst = {}
    for mi, region in found:                       # candidates of all regions of one instance compete: at most PER_INSTANCE per instance
        ii = np.array([r[0] for r in region]); jj = np.array([r[1] for r in region])
        i_lo, j_lo = ii.min() - 1, jj.min() - 1; mask = np.zeros((ii.max() - i_lo + 2, jj.max() - j_lo + 2), bool)
        mask[ii - i_lo, jj - j_lo] = True; D = chamfer(mask) * S.cell; reg = (ii, jj, mask, i_lo, j_lo)
        by_inst.setdefault(mi, []).extend((D[i - i_lo, j - j_lo], i, j, k, reg) for i, j, k in region)
    counts = {}
    for mi, cands in by_inst.items():
        kd = kind_of(S.meshes[mi])
        if kd is None: continue                    # desk clutter, sink
        typ, wt, cap, limit = kd
        if typ == "bed":                           # one spot, the valid one closest to the mattress centre
            cx = float(np.mean([c[1] for c in cands])); cy = float(np.mean([c[2] for c in cands]))
            cands = [c for c in cands if c[0] >= SPOT_R]; cands.sort(key=lambda c: (c[1] - cx) ** 2 + (c[2] - cy) ** 2)
        else: cands.sort(key=lambda c: c[:4], reverse=True)
        chosen = []
        lim, sep = (SHELF_LIMIT, SHELF_SEP) if typ == "shelf" else (min(PER_INSTANCE, limit), SPOT_SEP)
        per_region = {}
        for r, i, j, k, reg in cands:
            ii, jj, mask, i_lo, j_lo = reg
            if r < SPOT_R or len(chosen) >= lim: break
            x, y = S.pos(i, j); top = float(S.z[i, j, k])
            # apart in 3D (a shelf's compartments stand above each other); a shelf gives at most 2 per board (region)
            dist = (lambda c: math.dist((x, y, top), c["loc"])) if typ == "shelf" else (lambda c: math.hypot(x - c["loc"][0], y - c["loc"][1]))
            if any(dist(c) < sep for c in chosen): continue
            if typ == "shelf" and per_region.get(id(reg), 0) >= 2: continue
            room = room_of(S, i, j, k); covered = room < COVERED
            if covered and (typ != "shelf" or r < CUBBY_R): continue          # only shelf compartments, and the capsule fits
            walkin = top - floor0 < B.SPOT_MIN
            clear = min(B.JUMP_CLEAR_UP, room - 2 * B.CAPSULE_HH - ROOM_MARGIN)
            if not walkin and clear < 3.0: continue
            frm = takeoff(S, H, E, mask, i_lo, j_lo, (x, y), top, clear=clear, covered=covered, walkin=walkin)
            if frm is None: continue
            pts = np.stack([ii, jj], 1).astype(float); cov = np.cov((pts - pts.mean(0)).T) if len(pts) > 2 else np.eye(2)
            w, v = np.linalg.eigh(cov); ax = v[:, int(np.argmax(w))]
            if typ == "window" and r < B.CAPSULE_R:   # the pane stands on the sill's middle line (benches and small tables have none)
                x, y, frm = ledge(S, H, E, mask, i_lo, j_lo, (x, y), top, ax, frm)
            m = S.meshes[mi]; name = "%s/%s" % (m["actor"], m["mesh"].rsplit("/", 1)[1])
            post = B.P_SLEEP if r >= SLEEP_R else (B.P_LIE if r >= LIE_R else B.P_SIT)
            if cap is not None: post = cap if typ == "bed" else min(post, cap)
            per_region[id(reg)] = per_region.get(id(reg), 0) + 1
            chosen.append({"label": "cubby" if covered else typ, "src_debug": name, "loc": [round(x, 1), round(y, 1), round(top, 1)],
                           "from": [round(c, 1) for c in frm], "yaw": facing(typ, (x, y), frm, piece_axis(m, ax)), "height": round(top - frm[2], 1),
                           "posture": post, "weight": CUBBY_WEIGHT if covered else wt, "room": room})
        out.extend(chosen)
    for s in out: counts[s["label"]] = counts.get(s["label"], 0) + 1; s["label"] = "%s %d" % (s["label"], counts[s["label"]])
    return out


CUBBY_WEIGHT = 2.0   # shelf compartments: a cat's favourite kind of place


def facing(typ, c, frm, ax=None):
    """Yaw (degrees) the cat faces on the spot: the open side, i.e. towards her take-off point. Seats are left on their open front
    (the backrest blocks every arc from behind), beds and compartments on their open side; window sills face the pane (she looks
    out; the take-off point is in the room). With the region's main axis `ax`, the direction is squared to the piece: the one of
    +-ax and +-its normal nearest the take-off direction (take-off points come in 15 degree steps)."""
    d = (frm[0] - c[0], frm[1] - c[1])
    if ax is not None:
        cands = [(ax[0], ax[1]), (-ax[0], -ax[1]), (-ax[1], ax[0]), (ax[1], -ax[0])]
        d = max(cands, key=lambda v: v[0] * d[0] + v[1] * d[1])
    a = math.degrees(math.atan2(d[1], d[0]))
    if typ == "window": a += 180.0
    return round((a + 180.0) % 360.0 - 180.0, 1)


def piece_axis(m, ax):
    """The mesh instance's local X axis in the plane (its world matrix; furniture is modelled square to its axes), else the region's
    main axis."""
    if "matrix" in m:
        M = np.array(m["matrix"], float).reshape(4, 4); v = M[:2, 0]; n = float(np.hypot(*v))
        if n > 1e-6: return (float(v[0] / n), float(v[1] / n))
    return (float(ax[0]), float(ax[1]))


def low_cubby(S, i, j, k, h):
    """A shelf compartment at floor level (2 cm up to SPOT_MIN, covered by the board above): a walk-in spot, no jump."""
    kd = kind_of(S.meshes[S.inst[i, j, k]])
    return kd is not None and kd[0] == "shelf" and 2.0 <= h < B.SPOT_MIN and S.clearance(i, j, k) < COVERED


def room_of(S, i, j, k):
    c = S.clearance(i, j, k); return OPEN_ROOM if not np.isfinite(c) else min(OPEN_ROOM, round(float(c), 1))


def ledge(S, H, E, mask, i_lo, j_lo, c, top, ax, frm):
    """A window sill narrower than the capsule (15-16 cm deep): its middle line is where the window pane stands (Window_A_Glass,
    BlockAll, 1.6 cm thick: a spot trace from above starts inside it and fails, and no capsule fits there). The spot moves across the
    ledge towards the take-off side (the room) to LEDGE_IN inside the region's edge, so the spot trace hits the sill in front of the pane;
    the landing capsule touches the pane and settles on the sill edge (r 14 cm, edge contact within the radius is a valid floor). Returns
    the new (x, y, take-off point); the take-off point is searched again from the new spot, square to the sill first (a slanted jump
    would land along the pane), the old one is kept when none is found."""
    def edge(n):                                   # distance from c to the region's edge along n (0.5 cm steps, +-0.25 cm)
        t = 0.0
        while True:
            i, j = S.cell_of(c[0] + n[0] * (t + 0.5), c[1] + n[1] * (t + 0.5)); mi_, mj_ = i - i_lo, j - j_lo
            if not (0 <= mi_ < mask.shape[0] and 0 <= mj_ < mask.shape[1] and mask[mi_, mj_]): return t + 0.25
            t += 0.5
    def room(n):                                   # walk surface FROM_OUT beyond the edge on this side
        i, j = S.cell_of(c[0] + n[0] * (edge(n) + FROM_OUT), c[1] + n[1] * (edge(n) + FROM_OUT)); return S.inside(i, j) and bool(E[i, j])
    n = np.array([-ax[1], ax[0]])
    if room(-n) and not room(n) or room(n) == room(-n) and (frm[0] - c[0]) * n[0] + (frm[1] - c[1]) * n[1] < 0: n = -n
    t = max(edge(n) - LEDGE_IN, 0.0); x, y = c[0] + n[0] * t, c[1] + n[1] * t
    f2 = takeoff(S, H, E, mask, i_lo, j_lo, (x, y), top, [math.atan2(n[1], n[0])])     # straight at the pane, else any direction
    if f2 is None: f2 = takeoff(S, H, E, mask, i_lo, j_lo, (x, y), top)
    return x, y, f2 if f2 is not None else frm


def free_at(S, i, j, zl, body=BODY):
    """A body can be at height zl in this column: something below it, and the next surface above faces down (an underside) at least
    `body` cm higher, or there is none. Under an upward face (a top) we are inside a closed body."""
    if not S.inside(i, j): return False
    col = [(float(S.z[i, j, k]), float(S.nz[i, j, k])) for k in range(S.K) if not np.isnan(S.z[i, j, k])]
    if not [c for c in col if c[0] <= zl]: return False
    above = [c for c in col if c[0] > zl]
    if above:
        za, na = min(above)
        if na > 0 or za - zl < body: return False
    return True


def takeoff(S, H, E, mask, i_lo, j_lo, c, top, angles=None, clear=B.JUMP_CLEAR_UP, covered=False, walkin=False):
    """Shortest valid take-off point: FROM_OUT beyond the region's edge in one of 24 directions, on the eroded walk surface, at most
    FROM_MAX away horizontally, and the ballistic path of the runtime jump (brain.jump_velocity, apex JUMP_CLEAR_UP over the top) free
    for the capsule's bottom and centre in every 5 cm column it crosses. A covered spot (compartment): the arc's apex `clear` over the
    top stays under the board above, checked for the whole capsule (2 * CAPSULE_HH from its bottom). A walk-in spot: the point is on the
    walk surface at the spot's own height and the straight way in stays on the walk surface (no step over STEP)."""
    best = None; g = 980.0; HH = B.CAPSULE_HH
    for ang in (angles if angles is not None else [2 * math.pi * a / 24 for a in range(24)]):
        dx, dy = math.cos(ang), math.sin(ang); t = 0.0
        while True:
            i, j = S.cell_of(c[0] + dx * t, c[1] + dy * t); mi_, mj_ = i - i_lo, j - j_lo
            if not (0 <= mi_ < mask.shape[0] and 0 <= mj_ < mask.shape[1] and mask[mi_, mj_]): break
            t += S.cell / 2
        t += FROM_OUT; fx, fy = c[0] + dx * t, c[1] + dy * t; fi, fj = S.cell_of(fx, fy)
        if t > FROM_MAX or not S.inside(fi, fj) or not E[fi, fj]: continue
        fz = float(H[fi, fj])
        if walkin:
            n = max(1, int(t / (S.cell / 2))); ok = abs(top - fz) <= STEP
            for s in range(n + 1):
                i, j = S.cell_of(fx + (c[0] - fx) * s / n, fy + (c[1] - fy) * s / n)
                if not S.inside(i, j) or np.isnan(H[i, j]) or abs(H[i, j] - fz) > STEP: ok = False; break
            if ok and (best is None or t < best[0]): best = (t, (fx, fy, fz))
            continue
        if not B.SPOT_MIN <= top - fz <= B.JUMP_MAX: continue
        frm, to = (fx, fy, fz + HH), (c[0], c[1], top + HH)
        vx, vy, vz = B.jump_velocity(frm, to, clear, g)
        T = vz / g + math.sqrt(2.0 * (max(to[2] - frm[2], 0.0) + clear - (to[2] - frm[2])) / g)
        ok = True
        for s in range(1, 40):
            tt = T * s / 40; x, y, zc = frm[0] + vx * tt, frm[1] + vy * tt, frm[2] + vz * tt - 0.5 * g * tt * tt
            i, j = S.cell_of(x, y)
            free = free_at(S, i, j, zc - HH + 2.0, 2 * HH) if covered else (free_at(S, i, j, zc - HH + 2.0) and free_at(S, i, j, zc))
            if not free: ok = False; break
        if ok and (best is None or t < best[0]): best = (t, (fx, fy, fz))
    return None if best is None else best[1]


def spot_walk(S, H, E, cells, frm):
    """Index of the walk point nearest the take-off point with a clear walk line to it (else the nearest at all): where the
    Blueprint's route check (next hops, closed doors) ends for this spot."""
    fc = S.cell_of(frm[0], frm[1]); order = sorted(range(len(cells)), key=lambda i: math.dist(S.pos(*cells[i]), frm[:2]))
    for i in order[:12]:
        if S.inside(*fc) and E[fc] and line_ok(E, H, S, cells[i], fc): return i
    return order[0]


def build(S): return _build(S)[1]


def _build(S):
    H = walk_surface(S); E = erode(H, int(round(B.CAPSULE_R / S.cell + 0.49)))
    dw = doorways(S, H) if S.doors else []
    cells, adj, dropped_comps, dropped_pts, door_pt = walk_graph(S, H, E, dw or None); nxt = next_hops(adj)
    walk = []
    for i, c in enumerate(cells):
        k = door_pt.get(i, -1); none = [0.0, 0.0, 0.0]
        walk.append({"loc": [round(S.pos(*c)[0], 1), round(S.pos(*c)[1], 1), round(float(H[c]), 1)], "next": B.encode_hops(nxt[i]),
                     "door": k, "door_a": list(dw[k]["a"]) if k >= 0 else none, "door_b": list(dw[k]["b"]) if k >= 0 else none})
    sp = spots(S, H, E)
    for s in sp: s["walk"] = spot_walk(S, H, E, cells, s["from"])
    return H, {"walk": walk, "spots": sp, "stats": {"walk_cells": int((~np.isnan(H)).sum()), "eroded_cells": int(E.sum()), "points": len(walk),
            "links": sum(len(a) for a in adj) // 2, "dropped_components": dropped_comps, "dropped_points": dropped_pts, "spots": len(sp),
            "doors": len([d for d in dw if d]), "door_points": len(door_pt)}}


def short(label):
    """Neutral label 'sofa 3' -> 'sofa 3' (picture labels only)."""
    return label


def picture(S, M, png, H=None):
    """Top view as seen from above in Unreal (X right, Y down, no mirror), 3 px per 5 cm cell. Grey = highest up-facing surface under
    230 cm over the floor (darker = higher), green tint = walk surface; blue = walk points and links (drawn where next_hop is the target
    itself); orange ring = spot, colour by weight (red 3, orange 2, yellow 1.5, white 1), tick = facing (from the centre), line = jump from the take-off point;
    label = short mesh name and height; magenta square = player start; cyan cross = door actor, cyan ring + line = doorway point and its
    probe line."""
    from PIL import Image, ImageDraw
    H = walk_surface(S) if H is None else H; floor0 = float(np.nanmin(H))
    up = np.where((S.nz > 0.5) & (S.z < floor0 + 230.0), S.z, np.nan); top = np.nanmax(np.where(np.isnan(up), -np.inf, up), axis=2)
    g = np.where(np.isfinite(top), 225 - np.clip((top - floor0) / 150.0, 0, 1) * 150, 40).astype(np.uint8)
    rgb = np.stack([g, g, g], -1); w_ = ~np.isnan(H); rgb[w_] = (rgb[w_] * [0.7, 1.0, 0.7]).astype(np.uint8)
    SC = 3; img = Image.fromarray(np.transpose(rgb, (1, 0, 2)).copy()).resize((S.nx * SC, S.ny * SC), Image.NEAREST); d = ImageDraw.Draw(img)
    px = lambda x, y: ((x - S.origin[0]) / S.cell * SC, (y - S.origin[1]) / S.cell * SC)
    W_ = M["walk"]
    for i, w in enumerate(W_):
        for b in range(i + 1, len(W_)):
            if B.next_hop(w["next"], b) == b: d.line([px(*w["loc"][:2]), px(*W_[b]["loc"][:2])], fill=(70, 120, 235))
    for w in W_: x, y = px(*w["loc"][:2]); d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(0, 40, 200))
    col = {3.0: (230, 0, 0), 2.0: (255, 140, 0), 1.5: (230, 210, 0)}
    for s in M["spots"]:
        x, y = px(*s["loc"][:2]); fx, fy = px(*s["from"][:2]); c = col.get(s["weight"], (255, 255, 255))
        d.line([(fx, fy), (x, y)], fill=(255, 120, 0), width=2); d.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill=(255, 120, 0))
        d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=c, width=3); a = math.radians(s["yaw"])
        d.line([(x, y), (x + 14 * math.cos(a), y + 14 * math.sin(a))], fill=(0, 0, 0), width=2)
        d.text((x + 9, y - 5), "%s %.0f" % (short(s["label"]), s["height"]), fill=(0, 0, 0))
    for x, y, _, _ in S.player_starts: X, Y = px(x, y); d.rectangle([X - 5, Y - 5, X + 5, Y + 5], outline=(255, 0, 255), width=2)
    for x, y, _, _ in S.doors: X, Y = px(x, y); d.line([X - 8, Y - 8, X + 8, Y + 8], fill=(0, 200, 220), width=3); d.line([X - 8, Y + 8, X + 8, Y - 8], fill=(0, 200, 220), width=3)
    for w in W_:                                   # doorway point and its probe line (cyan): the Blueprint traces A-B for a closed leaf
        if w.get("door", -1) >= 0:
            X, Y = px(*w["loc"][:2]); d.ellipse([X - 6, Y - 6, X + 6, Y + 6], outline=(0, 200, 220), width=3)
            d.line([px(*w["door_a"][:2]), px(*w["door_b"][:2])], fill=(0, 200, 220), width=2)
    img.save(png)


def main(odir, dst, png):
    S = Scan.load(odir); H, M = _build(S)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w") as f: json.dump(M, f, indent=1, ensure_ascii=False)
    os.makedirs(os.path.dirname(png), exist_ok=True); picture(S, M, png, H)
    print("MAP OK points=%(points)d links=%(links)d spots=%(spots)d dropped_points=%(dropped_points)d doors=%(doors)d door_points=%(door_points)d" % M["stats"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
