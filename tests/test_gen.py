import importlib.util, json, os, sys, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("gen_velvetpaws", os.path.join(W, "assets", "gen", "gen_velvetpaws.py"))
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
B = gen.B; core = gen.core

PURE_KINDS = {"get", "self", "make_array", "break", "make"}


def graphs(bp):
    yield "event graph", bp["event_graph"]
    for f in bp.get("functions", []):
        if "graph" in f: yield f["name"], f["graph"]


class GenTest(unittest.TestCase):
    # kept from stage 2 (0f85071), unchanged: test_sequences_in_order_with_their_sha, test_anims_on_own_skeleton, test_blendspace,
    # test_animplayer, test_montages, test_loader_row_points_at_class, test_mod_table_has_row (they use of_type and assets[-2]/[-1])
    # and test_decisions_are_pure_with_brain_signatures (Task 6); replaced: test_order, test_no_rotator_pin_literals, test_office_only,
    # test_exec_chains_only_use_exec_nodes, test_no_unsupported_node_kinds; removed: test_bp_uses_abp_and_demo, test_demo_montages_exist
    def of_type(self, t): return next(a for a in self.assets if a["type"] == t)

    def setUp(self):
        self.assets = gen.build({n: "0" * 40 for n in gen.CS.ORDER})
        self.bp = next(a for a in self.assets if a["type"] == "blueprint" and a["path"] == gen.names.BP)
        self.types = [a["type"] for a in self.assets]

    def test_order(self):
        i_bp = self.assets.index(self.bp)
        before = {a["path"] for a in self.assets[:i_bp]}
        for p in (gen.names.S_WALK, gen.names.S_SPOT, gen.names.DT_WALK, gen.names.DT_SPOT, gen.names.SG, gen.names.ABP):
            self.assertIn(p, before)
        subs = [a for a in self.assets[i_bp + 1:] if a["type"] == "subobject_defaults"]
        self.assertEqual([s["component"] for s in subs], ["CapsuleComponent", "CharacterMovement", "Mesh"])
        self.assertEqual(self.types[-2:], ["datatable", "datatable"])          # loader and mod table last

    def test_altui_tables(self):
        mu = gen.mu; paths = [a["path"] for a in self.assets]
        tabs = {t: next(a for a in self.assets if a["path"] == gen.names.ROOT + "/" + t) for t in gen.UI.TABLES}
        i_bp = paths.index(gen.names.BP)
        for t, a in tabs.items(): self.assertGreater(paths.index(a["path"]), i_bp)
        self.assertEqual(self.types[-2:], ["datatable", "datatable"])                # loader and mod table still last
        self.assertEqual([tabs[t]["row_struct"] for t in gen.UI.TABLES], [mu.ENTRY_STRUCT, mu.FIELD_STRUCT, mu.ACTION_STRUCT, mu.PRESET_STRUCT])
        self.assertEqual(tabs["AltUI_Fields"]["rows"], gen.UI.field_rows())
        self.assertEqual(tabs["AltUI_Entries"]["rows"][gen.UI.ENTRY]["Actor"], gen.names.BP_CLASS)
        self.assertFalse([p for p in paths if p.startswith("/Game/Mod/AltUI/")])     # nothing of AltUI's own

    def test_character_class(self):
        self.assertEqual(self.bp["parent"], "/Script/Engine.Character")
        self.assertEqual(self.bp["defaults"]["bCanBeDamaged"], False)
        self.assertEqual(self.bp["defaults"]["AutoPossessAI"], "Disabled")
        cap = next(a for a in self.assets if a.get("component") == "CapsuleComponent")["properties"]
        self.assertEqual((cap["CapsuleRadius"], cap["CapsuleHalfHeight"]), (B.CAPSULE_R, B.CAPSULE_HH))
        self.assertIn("NoCollision", cap["BodyInstance"])
        cmc = next(a for a in self.assets if a.get("component") == "CharacterMovement")["properties"]
        self.assertTrue(cmc["bRunPhysicsWithNoController"]); self.assertEqual(cmc["MaxWalkSpeed"], B.MAX_SPEED)

    def test_no_demo_left(self):
        text = json.dumps(self.bp)
        self.assertNotIn("Demo 0", text); self.assertNotIn("PlayAnimation", text); self.assertFalse(hasattr(gen, "DEMO"))

    def test_hooks_once(self):
        names_ = [f["name"] for f in self.bp["functions"]]
        self.assertEqual(len(names_), len(set(names_)))
        for h in core.HOOKS: self.assertIn(h, names_)

    def test_settings_and_save_game(self):
        bpvars = {v["name"] for v in self.bp["variables"]}
        sg = next(a for a in self.assets if a["path"] == gen.names.SG)
        sgvars = {v["name"] for v in sg["variables"]}
        for n, _, _ in B.SETTINGS + B.PLACE_VARS: self.assertIn(n, bpvars); self.assertIn(n, sgvars)

    def test_office_tables_match_map(self):
        with open(os.path.join(W, gen.names.OFFICE_MAP_REL)) as f: m = json.load(f)
        walk = next(a for a in self.assets if a["path"] == gen.names.DT_WALK); spots = next(a for a in self.assets if a["path"] == gen.names.DT_SPOT)
        self.assertEqual(len(walk["rows"]), len(m["walk"])); self.assertEqual(len(spots["rows"]), len(m["spots"]))
        self.assertEqual(sorted(walk["rows"]), list(walk["rows"]))         # row order = index order
        self.assertEqual(walk["rows"]["W000"]["Next"], m["walk"][0]["next"])

    def test_exec_chains_only_exec_nodes(self):
        pure_self = {f["name"] for f in self.bp["functions"] if f.get("pure")}
        for where, g in graphs(self.bp):
            nodes = {n["id"]: n for n in g["nodes"]}
            for ch in g["exec"]:
                for step in ch:
                    nid = step.split(":")[0]
                    if nid == "entry": continue
                    self.assertIn(nid, nodes, (where, nid)); n = nodes[nid]
                    self.assertNotIn(n["kind"], PURE_KINDS, (where, nid))
                    self.assertFalse(n["kind"] == "cast" and n.get("pure"), (where, nid))
                    self.assertFalse(n["kind"] == "call_self" and n["function"] in pure_self, (where, nid))

    def test_no_rotator_pin_literals(self):
        for where, g in graphs(self.bp):
            self.assertNotIn("(Pitch=", json.dumps(g), where)

    def test_no_unsupported_node_kinds(self):
        for where, g in graphs(self.bp):
            self.assertNotIn("delay", {n["kind"] for n in g["nodes"]}, where)   # BPGen has no such kind: a timer + custom event instead

    def test_one_primary_return_per_graph(self):
        # BPGen kind "return" is the graph's one primary result node: a second "return" lands on the same node and overwrites its pin
        # defaults (Pick Office Spot returned Found = false on both branches); further result nodes must be "return_new"
        for where, g in graphs(self.bp):
            self.assertLessEqual(len([n for n in g["nodes"] if n["kind"] == "return"]), 1, where)
            if any(n["kind"] == "return_new" for n in g["nodes"]): self.assertTrue(any(n["kind"] == "return" for n in g["nodes"]), where)

    def test_pick_office_spot_returns_found_after_take_spot(self):
        g = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}["Pick Office Spot"]
        nodes = {n["id"]: n for n in g["nodes"]}
        res = {n["id"]: n["in"]["Found"] for n in g["nodes"] if n["kind"] in ("return", "return_new")}
        self.assertEqual(sorted(res.values()), ["false", "true"])
        t = [r for r, v in res.items() if v == "true"][0]
        ch = [c for c in g["exec"] if t in c][0]
        take = [i for i in ch if nodes.get(i.split(":")[0], {}).get("function") == "Take Spot"]
        self.assertTrue(take and ch.index(take[0]) < ch.index(t))

    def test_enemy_place_result_nodes_differ(self):
        g = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}["Enemy Place"]
        res = [n for n in g["nodes"] if n["kind"] in ("return", "return_new")]
        self.assertEqual(len(res), 2); self.assertNotEqual(res[0]["in"]["Loc"], res[1]["in"]["Loc"])
        enemy = [n for n in res if any(d["kind"] == "get" and d.get("var") == "Enemy" for d in self._deps(g, n["in"]["Loc"]))]
        self.assertEqual(len(enemy), 1)

    def test_jodi_always_checked(self):
        for where, g in graphs(self.bp):
            ids = [n["id"] for n in g["nodes"] if n.get("function") == "GetPlayerCharacter"]
            valid = [n for n in g["nodes"] if n.get("function") == "IsValid"]
            for i in ids: self.assertTrue(any(json.dumps(v).find("@%s." % i) >= 0 for v in valid), (where, i))

    def test_sequences_in_order_with_their_sha(self):
        seqs = [a for a in self.assets if a["type"] == "animimport"]
        self.assertEqual([a["path"] for a in seqs], [gen.names.seq(n) for n in gen.CS.ORDER])
        self.assertTrue(all(a["fbx"].endswith("VP_Cat_%s.fbx" % n) and a["fbx_sha1"] == "0" * 40 for a, n in zip(seqs, gen.CS.ORDER)))
        self.assertNotIn(gen.names.ANIM + "/VP_Cat_Breathe", [a["path"] for a in self.assets])

    def test_anims_on_own_skeleton(self):
        for a in self.assets:
            if "skeleton" in a: self.assertEqual(a["skeleton"], gen.names.SKELETON, a["path"])

    def test_blendspace(self):
        bs = self.of_type("blendspace1d")
        self.assertEqual(bs["path"], gen.names.BLENDSPACE)
        self.assertEqual([s[0] for s in bs["samples"]], [gen.names.seq(n) for n in ("Stand", "Walk", "Trot", "Run")])
        self.assertEqual((bs["axis"]["min"], bs["axis"]["max"], bs["axis"]["grid"]), (0.0, 300.0, 30))
        self.assertEqual(bs["samples"][-1][1], gen.CS.SPEED_MAX)          # Run sits at the end of the axis

    def test_animplayer(self):
        ap = self.of_type("animplayer")
        self.assertEqual((ap["slot"], ap["add_slot"], ap["make_overlay_additive"], ap["overlay"]), ("DefaultSlot", True, True, gen.names.seq("Overlay")))
        self.assertEqual((ap["path"], ap["blendspace"]), (gen.names.ABP, gen.names.BLENDSPACE))

    def test_montages(self):
        ms = {a["path"]: a for a in self.assets if a["type"] == "montage"}
        sit = ms[gen.names.montage("Sit")]
        self.assertEqual([(s["name"], s.get("next")) for s in sit["sections"]], [("Enter", "Loop"), ("Loop", "Loop"), ("Exit", None)])
        self.assertAlmostEqual(sit["sections"][1]["time"], gen.CS.length("SitEnter"))
        jd = ms[gen.names.montage("JumpDown")]
        self.assertEqual([s["anim"] for s in jd["segments"]], [gen.names.seq(n) for n in ("JumpDownStart", "JumpAirDown", "JumpDownLand")])
        groom = ms[gen.names.montage("Groom")]
        self.assertEqual([(s["name"], s["time"]) for s in groom["sections"]], [("Default", 0.0)])
        for m in ms.values(): self.assertEqual(m["slot"], "DefaultSlot")

    def test_loader_row_points_at_class(self):
        loader = self.assets[-2]
        self.assertTrue(loader["path"].endswith("/VelvetPaws/TKA_BlueprintLoader"))
        self.assertEqual(list(loader["rows"].values())[0]["Actor Class"], gen.names.BP_CLASS)

    def test_mod_table_has_row(self):
        mt = self.assets[-1]
        self.assertTrue(mt["path"].endswith("/VelvetPaws/TKA_Mod_Table")); self.assertTrue(mt["rows"])

    def test_decisions_are_pure_with_brain_signatures(self):
        import sys; sys.path.insert(0, os.path.join(W, "scripts")); from velvetpaws import brain as B
        fs = {f["name"]: f for f in self.bp["functions"]}   # self.bp: the first blueprint is SG_VP_Cat now
        for name, (_, params, out) in B.BP_FUNCS.items():
            self.assertIn(name, fs); f = fs[name]
            self.assertTrue(f.get("pure"), name)
            self.assertEqual([(p["name"], p["type"]) for p in f["inputs"]], params, name)
            self.assertEqual([(p["name"], p["type"]) for p in f["outputs"]], [("Out", out)], name)

    def test_posture_steps_follow_brain(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        text = json.dumps(fs["Posture Step"])
        for (p, q), (ops, t, after) in B.TRANSITIONS.items():
            for op in ops: self.assertIn(gen.names.obj(gen.names.montage(op[1])), text)
            self.assertIn(repr(float(t)), text)
        for need in ("Snap Posture", "Do Action", "Routine", "Rest Routine"): self.assertIn(need, fs)
        self.assertIn(B.section("Sit", "loop"), json.dumps(fs["Snap Posture"]))

    def test_every_timer_has_its_custom_event(self):
        events = {n["name"] for n in self.bp["event_graph"]["nodes"] if n["kind"] == "custom_event"}
        timers = {n["in"]["FunctionName"] for _, g in graphs(self.bp) for n in g["nodes"] if n.get("function") == "K2_SetTimer"}
        self.assertIn("Place Cat", timers)
        self.assertEqual(sorted(timers - events), [])

    def test_size_clamped_after_load(self):
        f = next(f for f in self.bp["functions"] if f["name"] == "Load Settings")
        c = [n for n in f["graph"]["nodes"] if n.get("function") == "FClamp"]
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]["in"]["Min"], c[0]["in"]["Max"]), (repr(B.SIZE_MIN), repr(B.SIZE_MAX)))

    def test_move_module(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        for need in ("Start Move", "Make Path", "Office Path", "Nearest Walk", "Arrive", "Stuck", "Teleport Behind", "Roam Next", "Recall",
                     "Set Mode", "Cycle Mode", "Tick Move", "Tick Rest", "Poll Keys"):
            self.assertIn(need, fs)
        tm = json.dumps(fs["Tick Move"])
        for c in ("AddMovementInput", "VP_MaxSpeed", "Stuck", "Arrive"): self.assertIn(c, tm)
        self.assertIn("FindPathToLocationSynchronously", json.dumps(fs["Make Path"]))
        self.assertIn("VP_NextHop", json.dumps(fs["Office Path"]))
        keys = json.dumps(fs["Poll Keys"])
        for k in B.TEST_KEYS.values(): self.assertNotIn('"%s"' % k, keys)       # stage 5: test keys off
        self.assertIn("RecallKey", keys); self.assertIn("WasInputKeyJustPressed", keys)

    def test_test_keys_switch(self):
        self.assertFalse(gen.TEST_KEYS)
        gen.TEST_KEYS = True
        try:
            bp = gen.cat_bp(); keys = json.dumps(next(f for f in bp["functions"] if f["name"] == "Poll Keys"))
            for k in B.TEST_KEYS.values(): self.assertIn('"%s"' % k, keys)
        finally:
            gen.TEST_KEYS = False

    def test_no_anykey_input(self):
        text = json.dumps(self.bp)
        self.assertNotIn("EnableInput", text); self.assertNotIn('"kind": "key"', text)   # no input stack, nothing consumed (A6)

    def test_altui_interface(self):
        mu = gen.mu
        self.assertEqual(self.bp.get("interfaces"), [mu.INTERFACE])
        fs = {f["name"]: f for f in self.bp["functions"]}
        for f in (mu.GET_VALUE, mu.GET_COLOR, mu.GET_TEXT, mu.GET_KEY): self.assertIn(f, fs)
        for e in (mu.ON_CHANGED, mu.ON_COLOR, mu.ON_TEXT, mu.ON_KEY):
            self.assertEqual(len([n for n in self.bp["event_graph"]["nodes"] if n.get("kind") == "event" and n.get("name") == e]), 1, e)
        gv = json.dumps(fs[mu.GET_VALUE])
        for k in gen.UI.VALUES: self.assertIn('"%s"' % k, gv)
        gc = json.dumps(fs[mu.GET_COLOR])
        for k in gen.UI.COLORS: self.assertIn(k, gc)
        self.assertIn("Status Text", json.dumps(fs[mu.GET_TEXT])); self.assertIn("RecallKey", json.dumps(fs[mu.GET_KEY]))
        self.assertTrue(fs["Status Text"].get("pure"))

    def test_every_change_applied_and_saved(self):
        ev = self.bp["event_graph"]; nodes = {n["id"]: n for n in ev["nodes"]}
        oc = next(n["id"] for n in ev["nodes"] if n.get("kind") == "event" and n.get("name") == gen.mu.ON_CHANGED)
        branches = {}
        for n in ev["nodes"]:
            if n["kind"] == "branch":
                c = nodes.get(n["in"]["Condition"].lstrip("@").split(".")[0], {})
                if c.get("function") == "EqualEqual_NameName" and c["in"]["A"] == "@%s.Key" % oc: branches[c["in"]["B"]] = n["id"]
        want = set(gen.UI.VALUES) | {gen.UI.BUTTON_RECALL} | {k for k, _, _ in gen.UI.ACTIONS}
        self.assertEqual(set(branches), want)
        after = {k: [nodes[i.split(":")[0]] for c in ev["exec"] if c[0] == b + ":then" for i in c[1:]] for k, b in branches.items()}
        calls = lambda k: [n.get("function") for n in after[k] if n["kind"] == "call_self"]
        for k in ("Active", "TakeAlong"): self.assertIn("Refresh Presence", calls(k)); self.assertIn("Save Settings", calls(k))
        self.assertEqual(calls("Mode"), ["Set Mode"])
        self.assertEqual(calls("Pattern"), ["Apply Look", "Save Settings"])
        self.assertEqual(calls("Size"), ["Apply Size", "Save Soon"]); self.assertEqual(calls("Volume"), ["Apply Volume", "Save Soon"])
        self.assertEqual(calls("MeowRate"), ["Save Soon"]); self.assertEqual(calls("Meow"), ["Save Settings"]); self.assertEqual(calls("Purr"), ["Save Settings"])
        for k, _, m in gen.UI.ACTIONS:
            sm = [n for n in after[k] if n.get("function") == "Set Mode"]; self.assertEqual(sm[0]["in"]["M"], str(m))

    def test_walk_speed_capped_by_size(self):
        # MaxWalkSpeed set at runtime (class default 300 is for size 100 %) from min(purpose speed, VP_MaxSpeed(Size/100))
        g = next(f for f in self.bp["functions"] if f["name"] == "Tick Move")["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        sw = [n for n in g["nodes"] if n["kind"] == "set" and n["var"] == "MaxWalkSpeed"]
        self.assertEqual(len(sw), 1)
        fmin = nodes[sw[0]["in"]["MaxWalkSpeed"][1:].split(".")[0]]
        self.assertEqual(fmin.get("function"), "FMin")
        self.assertEqual(nodes[fmin["in"]["B"][1:].split(".")[0]].get("function"), "VP_MaxSpeed")
        self.assertIn("VP_FollowSpeed", json.dumps(g))

    def test_move_end_resets_rest(self):
        # lie after 8 s / sleep after 30 s count from the end of a move, not from placement
        for name in ("Arrive", "Stuck"):
            g = next(f for f in self.bp["functions"] if f["name"] == name)["graph"]
            self.assertTrue(any(n["kind"] == "set" and n["var"] == "RestSince" for n in g["nodes"]), name)

    def _deps(self, g, ref):
        """Ids of every node a pin reference (\"@id.Pin\") depends on, transitively."""
        nodes = {n["id"]: n for n in g["nodes"]}; seen = set(); todo = [ref]
        while todo:
            r = todo.pop()
            if not (isinstance(r, str) and r.startswith("@")): continue
            i = r[1:].split(".")[0]
            if i in seen or i not in nodes: continue
            seen.add(i); todo += list(nodes[i].get("in", {}).values())
        return [nodes[i] for i in seen]

    def test_stuck_clock_counts_waypoint_progress(self):
        # a repath (every 0.5 s while Jodi walks) must not reset the stuck clock; progress is measured to the current waypoint
        fs = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}
        sets = lambda name, var: [n for n in fs[name]["nodes"] if n["kind"] == "set" and n["var"] == var]
        self.assertEqual(sets("Make Path", "ProgressAt"), [])
        self.assertEqual([n["in"]["BestDist"] for n in sets("Make Path", "BestDist")], [repr(B.STUCK_UNSEEDED)])
        self.assertTrue(sets("Start Move", "ProgressAt"))
        tm = fs["Tick Move"]
        measured = [n for n in sets("Tick Move", "BestDist") if n["in"]["BestDist"].startswith("@")]
        self.assertEqual(len(measured), 2)                                     # seed + progress
        for n in measured:
            deps = self._deps(tm, n["in"]["BestDist"])
            self.assertTrue(any(d["kind"] == "get" and d.get("var") == "Waypoints" for d in deps))
            self.assertFalse(any(d["kind"] == "get" and d.get("var") == "Goal" for d in deps))
        self.assertIn(repr(B.STUCK_UNSEEDED), [n["in"]["BestDist"] for n in sets("Tick Move", "BestDist")])   # new waypoint re-seeds

    def test_follow_catch_up_and_roam_fixes(self):
        fs = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}
        self.assertEqual(B.FOLLOW_TELEPORT, B.RECALL_TELEPORT)
        tm = fs["Tick Move"]; nodes = {n["id"]: n for n in tm["nodes"]}
        tb = [n for n in tm["nodes"] if n["kind"] == "call_self" and n["function"] == "Teleport Behind"]
        self.assertEqual(len(tb), 1)
        # the teleport branch's condition reads both purposes (recall and follow)
        br = [b for b in tm["nodes"] if b["kind"] == "branch" and any(e[:2] == [b["id"] + ":then", tb[0]["id"]] for e in tm["exec"])]
        self.assertEqual(len(br), 1)
        purposes = {d["in"].get("B") for d in self._deps(tm, br[0]["in"]["Condition"]) if d.get("function") == "EqualEqual_IntInt"}
        self.assertTrue({str(B.GO_RECALL), str(B.GO_FOLLOW)} <= purposes, purposes)
        # recall in roam mode: rest 10-40 s, anchor moves (two RoamNext setters, two Anchor setters in Arrive)
        ar = fs["Arrive"]
        self.assertEqual(len([n for n in ar["nodes"] if n["kind"] == "set" and n["var"] == "RoamNext"]), 2)
        self.assertEqual(len([n for n in ar["nodes"] if n["kind"] == "set" and n["var"] == "Anchor"]), 2)
        # into Follow (and into Wait) a running walk is stopped
        self.assertEqual(len([n for n in fs["Set Mode"]["nodes"] if n["kind"] == "call_self" and n["function"] == "Arrive"]), 2)
        # NavMesh random point read once
        np_ = next(n["id"] for n in fs["Roam Next"]["nodes"] if n.get("function") == "K2_GetRandomReachablePointInRadius")
        rn = json.dumps(fs["Roam Next"])
        self.assertEqual(rn.count("@%s." % np_), 1); self.assertIn("@%s.RandomLocation" % np_, rn)

    def test_no_select_reads_a_possibly_none_actor(self):
        # a pure select evaluates both inputs: a location read of Enemy/Jodi/Spot actors feeding a select logs "Accessed None"
        # when the actor is None; the enemy's place comes from the exec branch in Enemy Place instead
        for where, g in graphs(self.bp):
            for n in g["nodes"]:
                if not str(n.get("function", "")).startswith("Select"): continue
                for ref in (n["in"].get("A", ""), n["in"].get("B", "")):
                    for nd in self._deps(g, ref):
                        self.assertFalse(nd["kind"] == "get" and nd.get("var") == "Enemy", (where, "select reads Enemy", n["id"]))
        fs = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}
        ep = fs["Enemy Place"]
        br = [n for n in ep["nodes"] if n["kind"] == "branch"]
        self.assertEqual(len(br), 1)
        self.assertEqual([n["kind"] for n in ep["nodes"] if n["kind"] in ("return", "return_new")], ["return", "return_new"])
        for name in ("Tick Move", "Flee", "Alarm Rest"):
            self.assertTrue(any(n["kind"] == "call_self" and n["function"] == "Enemy Place" for n in fs[name]["nodes"]), name)

    def test_capsule_blocks_physics_bodies(self):
        # the office's sofas, armchairs and collection shelves are PhysicsBody (game profiles PhysicsActorIgnoreCamera / -ViewLine):
        # a capsule that ignores them walks and lands through them (round 2 of the furniture-jump diagnosis)
        eb = {f["name"]: f for f in self.bp["functions"]}["Enable Body"]["graph"]
        blocked = {n["in"].get("Channel") for n in eb["nodes"] if n.get("function") == "SetCollisionResponseToChannel"
                   and n["in"].get("NewResponse") == "ECR_Block"}
        self.assertEqual(blocked, {"ECC_WorldStatic", "ECC_WorldDynamic", "ECC_PhysicsBody"})

    def test_spot_diagnostic(self):
        fs = {f["name"]: json.dumps(f) for f in self.bp["functions"]}
        names_ = {v["name"] for v in self.bp["variables"]}
        self.assertTrue({"DbgSpot", "DbgOK", "DbgPicks", "DbgTries", "DbgJumps"} <= names_)
        sets = lambda f, v: '"%s"' % v in fs[f] and "set" in fs[f]
        if not B.DEBUG_SPOTS:
            for f in ("Go To Spot", "Tick Jump", "Stuck", "Routine", "Init Level", "Status Text"): self.assertNotIn('"DbgSpot"', fs[f], f)
            return
        for f, v in (("Routine", "DbgPicks"), ("Go To Spot", "DbgTries"), ("Go To Spot", "DbgSpot"), ("Tick Jump", "DbgJumps"),
                     ("Tick Jump", "DbgSpot"), ("Stuck", "DbgSpot"), ("Start Jump", "DbgSpot"), ("Init Level", "DbgOK")):
            self.assertTrue(sets(f, v), (f, v))
        st = fs["Status Text"]
        for w in gen.UI.DBG_WORDS[1:]: self.assertIn(json.dumps(w), st)
        self.assertIn("Conv_IntToString", st)
        self.assertEqual(len(gen.UI.DBG_WORDS), B.DBG_WALK_IN + 1)

    def test_jump_module(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        tj = json.dumps(fs["Tick Jump"])
        for c in ("LaunchCharacter", "VP_JumpVelocity", "IsFalling", "GetGravityZ", "Montage_JumpToSection"): self.assertIn(c, tj)
        for m in (B.JUMP_UP, B.JUMP_DOWN):
            self.assertIn(gen.names.obj(gen.names.montage(m)), tj); self.assertIn(repr(float(B.LAUNCH[m])), tj)
        self.assertIn(B.section(B.JUMP_UP, "exit"), tj)
        for need in ("Take Spot", "Pick Office Spot", "Start Jump", "Abort Jump", "Probe Spot", "Go To Spot", "Leave Spot", "Tick Spot"):
            self.assertIn(need, fs)
        events = [n["name"] for n in self.bp["event_graph"]["nodes"] if n["kind"] == "custom_event"]
        self.assertIn("Spot Scan", events)

    def test_combat_module(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        events = [n["name"] for n in self.bp["event_graph"]["nodes"] if n["kind"] == "custom_event"]
        self.assertIn("Enemy Scan", events)
        eg = json.dumps(self.bp["event_graph"])
        self.assertIn("/Game/Project/Classes/Character_Base", eg); self.assertIn("/Game/Project/Character/Npc/Character_NPC", eg)
        self.assertIn(gen.names.obj(gen.names.montage(B.HISS[0])), json.dumps(fs["Begin Alarm"]))
        for need in ("Flee", "Combat Tick", "Tick Alarm", "Alarm Rest"): self.assertIn(need, fs)
        self.assertIn(repr(float(B.CALM_TIME)), json.dumps(fs["Combat Tick"]))

    def test_jump_turn_and_spot_keep_the_jump(self):
        # standing up for a jump forces WantPosture = stand (a routine pick must not leave the turn phase waiting forever), and Tick
        # Spot's routine only runs while she is still on the spot (not on the tick that starts the jump down)
        fs = {f["name"]: f for f in self.bp["functions"]}
        tj = fs["Tick Jump"]["graph"]
        self.assertTrue(any(n["kind"] == "set" and n["var"] == "WantPosture" and n["in"]["WantPosture"] == str(B.P_STAND) for n in tj["nodes"]))
        ts = json.dumps(fs["Tick Spot"])
        self.assertIn('"Rest Routine"', ts); self.assertIn('"%d"' % B.ST_SPOT, ts)

    def test_reached_waypoint_keeps_the_stuck_clock(self):
        # review s3-t10-11 Important 1: no ProgressAt setter shares an exec chain with the WpIndex increment
        tm = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}["Tick Move"]
        nodes = {n["id"]: n for n in tm["nodes"]}
        is_set = lambda i, v: nodes.get(i.split(":")[0], {}).get("kind") == "set" and nodes[i.split(":")[0]].get("var") == v
        inc = [c for c in tm["exec"] if any(is_set(i, "WpIndex") for i in c)]
        self.assertEqual(len(inc), 1)
        self.assertFalse(any(is_set(i, "ProgressAt") for i in inc[0]))

    def test_cb_from_spot_jumps_down_then_flees(self):
        # review s3-t10-11 Minors 1 and 5: Flee's CbFromSpot branch sets State = SPOT before Start Move(GO_FLEE, flee goal), so Start
        # Move's spot branch jumps down with the flee goal set; Tick Spot's alarmed low-spot branch goes through it
        fs = {f["name"]: f["graph"] for f in self.bp["functions"] if "graph" in f}
        for name, first in (("Flee", None), ("Tick Spot", "CbFromSpot")):
            g = fs[name]; nodes = {n["id"]: n for n in g["nodes"]}
            node = lambda i: nodes.get(i.split(":")[0], {})
            if name == "Flee":
                bsp = [i for i, n in nodes.items() if n["kind"] == "branch" and node(n["in"]["Condition"].lstrip("@").split(".")[0]).get("var") == "CbFromSpot"]
                self.assertEqual(len(bsp), 1)
                c = [c for c in g["exec"] if c[0] == bsp[0] + ":then"][0]
                kinds = [(node(i).get("kind"), node(i).get("var") or node(i).get("function")) for i in c[1:]]
                self.assertIn(("set", "State"), kinds); self.assertEqual(kinds[-1], ("call_self", "Start Move"))
                st = [node(i) for i in c if node(i).get("var") == "State"][0]
                self.assertEqual(st["in"]["State"], str(B.ST_SPOT))
                self.assertLess(kinds.index(("set", "State")), len(kinds) - 1)
                sm = node(c[-1]); self.assertEqual(sm["in"]["Purpose"], str(B.GO_FLEE))
                self.assertIn("VP_FleeGoal", json.dumps(self._deps(g, sm["in"]["To"])))
            else:
                c = [c for c in g["exec"] if any(node(i).get("function") == "Flee" for i in c)]
                self.assertEqual(len(c), 1)
                fl = [i for i in c[0] if node(i).get("function") == "Flee"][0]
                cb = [i for i in c[0] if node(i).get("var") == first]
                self.assertTrue(cb and c[0].index(cb[0]) < c[0].index(fl))
                self.assertEqual(node(cb[0])["in"][first], "true")
                self.assertNotIn("Start Jump", json.dumps([node(i) for i in c[0]]))

    def test_jump_and_scan_fixes(self):
        # review s3-t10-11 Minors 2-4: Abort Jump gives an office spot up (SpotsOK), the spot scan leaves a GO_SPOT walk alone,
        # Alarm Rest turns with the tick's DT (TickDT, set first in Think)
        fs = {f["name"]: f for f in self.bp["functions"]}
        aj = json.dumps(fs["Abort Jump"]); self.assertIn("Array_Set", aj); self.assertIn("SpotsUntil", aj)   # left out for a while (round 6)
        scan = json.dumps(self.bp["event_graph"]); self.assertIn("Spot Scan", scan)
        ev = self.bp["event_graph"]; nodes = {n["id"]: n for n in ev["nodes"]}
        q = [c for c in ev["exec"] if c[0] == "jp_scan"][0][1]
        jb = [nodes[c[1]] for c in ev["exec"] if c[0] in (q + ":then_0", q + ":then_1")]
        self.assertEqual(len(jb), 2)
        for b in jb:
            self.assertIn("Purpose", {d.get("var") for d in self._deps(ev, b["in"]["Condition"])})
        ar = fs["Alarm Rest"]["graph"]; an = {n["id"]: n for n in ar["nodes"]}
        fe = [n for n in ar["nodes"] if n.get("function") == "Face Enemy"][0]
        self.assertEqual(an[fe["in"]["DT"].lstrip("@").split(".")[0]].get("var"), "TickDT")
        th = fs["Think"]["graph"]; tn = {n["id"]: n for n in th["nodes"]}
        first = [c for c in th["exec"] if c[0] == "entry"][0][1]
        self.assertEqual((tn[first]["kind"], tn[first]["var"], tn[first]["in"]["TickDT"]), ("set", "TickDT", "@entry.DT"))

    def test_home_module(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        il = json.dumps(fs["Init Level"])
        for t in (gen.names.DT_WALK, gen.names.DT_SPOT): self.assertIn(t, il)
        self.assertIn("K2_ProjectPointToNavigation", il)
        ps = json.dumps(fs["Place Start"])
        for c in ("Take Spot", "Snap Posture", "Teleport Behind", "PlaceSpot", "HasPlace"): self.assertIn(c, ps)
        self.assertIn("Save Settings", json.dumps(fs["Save Place"]))
        events = [n["name"] for n in self.bp["event_graph"]["nodes"] if n["kind"] == "custom_event"]
        self.assertIn("Save Tick", events)

    def test_place_start_reads_saved_spot_in_range(self):
        # Place Start reads SpotsOK[PlaceSpot] only behind a branch that checked PlaceSpot against 0..n-1 (a pure AND evaluates every
        # input, so the range check and the read must not share one condition)
        g = {f["name"]: f for f in self.bp["functions"]}["Place Start"]["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        var_of = lambda r: nodes.get(r.lstrip("@").split(".")[0], {}).get("var") if isinstance(r, str) else None
        get = [i for i, n in nodes.items() if n.get("function") == "Array_Get" and var_of(n["in"]["TargetArray"]) == "SpotsOK"
               and var_of(n["in"].get("Index")) == "PlaceSpot"]
        self.assertEqual(len(get), 1)
        # (round 6: ANDed with "the saved place lies over that spot")
        br = [i for i, n in nodes.items() if n["kind"] == "branch" and get[0] in {d["id"] for d in self._deps(g, n["in"]["Condition"])}]
        self.assertEqual(len(br), 1)
        before = {c[c.index(br[0]) - 1] for c in g["exec"] if br[0] in c and c.index(br[0]) > 0}
        self.assertEqual(len(before), 1); src = before.pop()
        self.assertTrue(src.endswith(":then") and nodes[src.split(":")[0]]["kind"] == "branch", src)
        self.assertIn("PlaceSpot", {n.get("var") for n in self._deps(g, nodes[src.split(":")[0]]["in"]["Condition"])})

    def test_home_feeds_paths_and_spots(self):
        # Init Level fills the arrays Make Path / Office Path and Pick Office Spot read, sets HasNav (missions) and, when a spot passed
        # the check, SpotValid and OfficeSpotsOK; Routine offers spots on OfficeSpotsOK too (floor start, after Stuck / Abort Jump)
        fs = {f["name"]: f for f in self.bp["functions"]}
        sets = {n["var"] for n in fs["Init Level"]["graph"]["nodes"] if n["kind"] == "set"}
        self.assertTrue({"HasNav", "SpotValid", "OfficeSpotsOK"} <= sets)
        adds = {n["in"]["TargetArray"] for n in fs["Init Level"]["graph"]["nodes"] if n.get("function") == "Array_Add"}
        gets = {n["id"]: n.get("var") for n in fs["Init Level"]["graph"]["nodes"] if n["kind"] == "get"}
        arrs = {gets[a.lstrip("@").split(".")[0]] for a in adds}
        self.assertEqual(arrs, {"WalkLoc", "WalkNext", "SpotsLoc", "SpotsFrom", "SpotsYaw", "SpotsHeight", "SpotsPosture", "SpotsWeight", "SpotsOK",
                                "WalkDoor", "WalkDoorA", "WalkDoorB", "DoorPts", "SpotsRoom", "SpotsWalk", "SpotsUntil"})
        mp = json.dumps(fs["Make Path"])
        for c in ("HasNav", "WalkLoc", "Office Path", "FindPathToLocationSynchronously"): self.assertIn(c, mp)
        self.assertIn("OfficeSpotsOK", json.dumps(fs["Routine"]))

    def test_cues_where_things_happen(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        def cues(name):
            g = fs[name]["graph"]
            return sorted(int(n["in"]["Id"]) for n in g["nodes"] if n["kind"] == "call_self" and n["function"] == "Cue")
        self.assertEqual(cues("Begin Alarm"), [B.CUE_HISS])
        self.assertEqual(cues("Do Action"), [B.CUE_YAWN])
        self.assertEqual(cues("Tick Jump"), [B.CUE_LAND, B.CUE_LAND])          # landing up and landing down
        self.assertEqual(cues("Recall"), [B.CUE_CALLED])
        self.assertEqual(cues("Arrive"), [B.CUE_ARRIVED])
        pk = json.dumps(fs["Poll Keys"])
        self.assertNotIn('"%s"' % B.TEST_KEYS["Meow"], pk)       # stage 5: test keys off

    def test_sound_module(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        for need in ("Play Cue", "Play Meow", "Cue", "Fire Cue", "Sound Tick", "Start Purr", "Stop Purr", "Stop Sounds"): self.assertIn(need, fs)
        pc = [n for n in fs["Play Cue"]["graph"]["nodes"] if n.get("function") == "SpawnSoundAttached"]
        self.assertEqual(len(pc), 1); self.assertEqual(pc[0]["in"]["AttachPointName"], gen.SN.ATTACH_BONE)
        meow = json.dumps(fs["Play Meow"])
        for i in range(gen.SN.variants("Meow")): self.assertIn(gen.SN.obj_path("Meow", i), meow)
        self.assertIn("VP_NextVariant", meow)
        tick = json.dumps(fs["Sound Tick"])
        for c in ("VP_MeowInterval", "VP_PurrWant", "Fire Cue", "Start Purr", "Stop Purr"): self.assertIn(c, tick)
        self.assertIn('"%s"' % gen.SN.obj_path("Purr"), json.dumps(fs["Start Purr"]))
        cue = json.dumps(fs["Cue"])
        self.assertIn(repr(B.CUE_AT[B.CUE_HISS]), cue)
        self.assertEqual([p["name"] for p in fs["Cue"]["inputs"]], ["Id"])

    def test_think_calls_sound_tick(self):
        g = next(f for f in self.bp["functions"] if f["name"] == "Think")["graph"]
        calls = [n["function"] for n in g["nodes"] if n["kind"] == "call_self"]
        self.assertLess(calls.index("Combat Tick"), calls.index("Sound Tick"))

    def test_land_has_two_variants(self):
        self.assertEqual(gen.SN.variants("Land"), 2)       # Fire Cue picks one of two with RandomBool

    def test_look_at_runtime(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        mm = [n for n in fs["Make Materials"]["graph"]["nodes"] if n.get("function") == "CreateDynamicMaterialInstance"]
        self.assertEqual(sorted(int(n["in"]["ElementIndex"]) for n in mm), sorted(list(gen.names.SLOTS).index(s) for s in gen.UI.MID))
        al = fs["Apply Look"]["graph"]; nodes = {n["id"]: n for n in al["nodes"]}
        sets = [n for n in al["nodes"] if n.get("function") in ("SetVectorParameterValue", "SetScalarParameterValue")]
        got = set()
        for n in sets:
            mid = nodes[n["in"]["self"][1:].split(".")[0]]["var"]
            got.add((mid, n["in"]["ParameterName"]))
        self.assertEqual(got, {(gen.UI.MID[s], p) for s, p, _ in gen.UI.LOOK})
        self.assertIn("VP_PatternWeights", json.dumps(al)); self.assertIn("VP_WhiteMarks", json.dumps(al))
        sz = json.dumps(fs["Apply Size"]); self.assertIn("SetActorScale3D", sz); self.assertIn("K2_AddActorWorldOffset", sz)
        self.assertIn("SetVolumeMultiplier", json.dumps(fs["Apply Volume"]))
        bp_chain = json.dumps(self.bp["event_graph"])
        self.assertIn('"Make Materials"', bp_chain); self.assertIn('"Apply Look"', bp_chain)

    def test_presence(self):
        ev = self.bp["event_graph"]
        destroys = [n for n in ev["nodes"] if n.get("function") == "K2_DestroyActor"]
        self.assertEqual(len(destroys), 1)                                   # menus only; Place Cat gives up into dormancy
        fs = {f["name"]: f for f in self.bp["functions"]}
        self.assertIn("VP_WantHere", json.dumps(fs["Refresh Presence"])); self.assertIn("Go Dormant", json.dumps(fs["Refresh Presence"]))
        gd = json.dumps(fs["Go Dormant"])
        for c in ("Stop Sounds", "Save Place", "SetActorHiddenInGame", "NoCollision", "DisableMovement", "Montage_Stop"): self.assertIn(c, gd)
        nodes = {n["id"]: n for n in ev["nodes"]}
        first = nodes[[c for c in ev["exec"] if c[0] == "pce"][0][1].split(":")[0]]            # Place Cat asks first: still wanted?
        self.assertEqual(first["kind"], "branch")
        self.assertEqual(nodes[first["in"]["Condition"].lstrip("@").split(".")[0]].get("function"), "VP_WantHere")
        self.assertIn("LevelReady", json.dumps(ev)); self.assertIn('"Refresh Presence"', json.dumps(ev))

    def test_saving_soon_and_at_end(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        ss = [n for n in fs["Save Soon"]["graph"]["nodes"] if n.get("function") == "K2_SetTimer"]
        self.assertEqual(ss[0]["in"]["FunctionName"], "Save Now"); self.assertEqual(ss[0]["in"]["Time"], repr(B.SAVE_SOON))
        ev = json.dumps(self.bp["event_graph"]); self.assertIn('"Save Now"', ev); self.assertIn("SaveDue", ev)

    def test_dormant_cat_does_not_scan_or_save(self):
        ev = self.bp["event_graph"]; nodes = {n["id"]: n for n in ev["nodes"]}
        first = [c for c in ev["exec"] if c[0] == "cb_scan"][0][1].split(":")[0]
        self.assertEqual(nodes[first]["kind"], "branch")
        self.assertIn("Placed", json.dumps(next(f for f in self.bp["functions"] if f["name"] == "Save Place")))

    def test_cycle_mode_goes_through_set_mode(self):
        fs = {f["name"]: f for f in self.bp["functions"]}
        self.assertEqual([p["name"] for p in fs["Set Mode"]["inputs"]], ["M"])
        self.assertIn('"Set Mode"', json.dumps(fs["Cycle Mode"]))
        self.assertIn("Save Settings", json.dumps(fs["Set Mode"]))
