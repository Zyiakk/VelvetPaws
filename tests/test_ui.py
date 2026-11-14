import importlib.util, os, sys, unittest

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(W, "scripts")); sys.path.insert(0, os.path.join(W, "tools", "blender"))
from velvetpaws import ui as UI, brain as B, names
ALTUI_DEV = os.environ.get("ALTUI_DEV") or os.path.join(W, "..", "..", "AltUI", "dev")
spec = importlib.util.spec_from_file_location("modui", os.path.join(ALTUI_DEV, "assets", "gen", "modui.py"))
mu = importlib.util.module_from_spec(spec); spec.loader.exec_module(mu)


class UiTest(unittest.TestCase):
    def test_every_setting_has_a_field(self):
        keys = {k for k, *_ in UI.FIELDS}
        for n, _, _ in B.SETTINGS: self.assertIn(n, keys)
        self.assertEqual(len(keys), len(UI.FIELDS))

    def test_field_rows_are_valid_for_altui(self):
        rows = {r["Key"]: r for r in UI.field_rows().values()}
        for r in rows.values():
            self.assertIn(r["Type"], mu.TYPES); self.assertEqual(r["Entry"], UI.ENTRY)
            if r["Type"] in mu.RANGED: self.assertLess(r["Min"], r["Max"])
            if r["Type"] == "Choice": self.assertTrue(r["Options"])
            if r["Type"] == "Tab": self.assertTrue(r["Label"])
        self.assertEqual(rows["Size"]["Min"], B.SIZE_MIN); self.assertEqual(rows["Size"]["Max"], B.SIZE_MAX)
        self.assertEqual(len(rows["Mode"]["Options"]), 3); self.assertEqual(len(rows["Pattern"]["Options"]), len(B.PATTERNS))
        self.assertEqual(rows["Status"]["Type"], "Info"); self.assertEqual(rows["Recall"]["Type"], "Button")
        self.assertEqual([r["Type"] for r in sorted(rows.values(), key=lambda r: r["Order"])][:2], ["Info", "Toggle"])   # lead

    def test_round6_page(self):
        self.assertEqual(UI.CAPTION, "VelvetPaws"); self.assertEqual(UI.ENTRY, "VelvetPaws")
        for k, t, label, *_ in UI.FIELDS: self.assertNotIn("%", label, k)       # labels plain (no percent signs)
        by = {r["Key"]: r for r in UI.field_rows().values()}
        self.assertEqual(by["Size"]["Label"], "Scale"); self.assertEqual(by["Size"]["Min"], 40.0)
        for k in ("StayMin", "StayMax"):
            self.assertEqual((by[k]["Min"], by[k]["Max"]), B.STAY_RANGE); self.assertEqual(by[k]["Type"], "Slider")
            self.assertEqual(UI.to_ui(k, UI.default(k)), dict(StayMin=B.STAY_DEFAULT[0], StayMax=B.STAY_DEFAULT[1])[k])
        # localization ids are table name + row name: every row name of every table carries the mod's prefix (or is the entry)
        for rows in (UI.field_rows(), UI.action_rows(names.BP_CLASS), UI.preset_rows()):
            for r in rows: self.assertTrue(r.startswith(UI.ROW), r)
        self.assertEqual({r["Key"] for r in UI.field_rows().values()}, {k for k, *_ in UI.FIELDS})   # keys unchanged (saves)

    def test_values_cover_the_numeric_fields(self):
        num = {k for k, t, *_ in UI.FIELDS if t in ("Toggle", "Slider", "Number", "Choice")}
        self.assertEqual(num, set(UI.VALUES))
        self.assertEqual(set(UI.COLORS), {k for k, t, *_ in UI.FIELDS if t == "Color"})

    def test_conversions(self):
        self.assertEqual(UI.to_ui("Volume", UI.default("Volume")), 100.0)
        self.assertEqual(UI.to_ui("MeowRate", UI.default("MeowRate")), 50.0)
        self.assertEqual(UI.to_ui("Active", UI.default("Active")), 1.0)
        self.assertEqual(UI.to_ui("Pattern", UI.default("Pattern")), 1.0)
        self.assertAlmostEqual(UI.from_ui("Volume", 70.0), 0.7)
        self.assertEqual(UI.from_ui("Size", 200.0), B.SIZE_MAX)          # clamped
        self.assertEqual(UI.from_ui("Mode", 2.4), 2); self.assertEqual(UI.from_ui("Mode", 7.0), 2)
        self.assertIs(UI.from_ui("Purr", 0.2), False)

    def test_tables_named_as_altui_reads_them(self):
        self.assertEqual(UI.TABLES, [mu.ENTRIES_TABLE, mu.FIELDS_TABLE, mu.ACTIONS_TABLE, mu.PRESETS_TABLE])
        self.assertEqual(UI.entry_rows(names.BP_CLASS), {UI.ENTRY: {"Caption": UI.CAPTION, "Actor": names.BP_CLASS, "Order": 0}})
        acts = UI.action_rows(names.BP_CLASS)
        self.assertEqual(sorted(r["Key"] for r in acts.values()), sorted(k for k, _, _ in UI.ACTIONS))
        self.assertFalse({k for k, _, _ in UI.ACTIONS} & {k for k, *_ in UI.FIELDS})

    def test_presets(self):
        keys = {k: t for k, t, *_ in UI.FIELDS}
        for row, values in ((r, v["Values"]) for r, v in UI.preset_rows().items()):
            for k, v in values.items():
                self.assertIn(keys[k], mu.PRESET_TYPES, (row, k))
                if keys[k] == "Color": self.assertRegex(v, r"^#[0-9A-F]{6}$")
        self.assertEqual(UI.hex_srgb((1.0, 1.0, 1.0, 1.0)), "#FFFFFF"); self.assertEqual(UI.hex_srgb((0.0, 0.0, 0.0, 1.0)), "#000000")
        self.assertEqual(UI.hex_srgb((0.0015, 2.0, -1.0, 1.0)), "#05FF00")          # linear part below 0.0031308, clamped

    def test_look_parameters_per_slot(self):
        self.assertEqual({s for s, _, _ in UI.LOOK}, {"Fur", "FurCard", "Eye"})
        for s in UI.MID: self.assertIn(s, names.SLOTS)

    def test_undertone_only_on_agouti_coats(self):
        """Final review I1: the warm root tint follows the coat; solid / tricolour / markings stay neutral (no brown cast)."""
        neutral = tuple(1.0 - names.DEF_FUR_CAVITY for _ in range(3))
        warm = tuple((1.0 - names.DEF_FUR_CAVITY) * u for u in names.DEF_UNDERTONE[:3])
        for p, (w, _) in B.PATTERNS.items():
            got = names.root_tint(w)
            want = warm if p in (1, 2, 3) else neutral                   # tabby, brindle, spotted vs solid, tricolour, markings
            for a, b in zip(got, want): self.assertAlmostEqual(a, b, places=6, msg=(p, got))
        for a, b in zip(names.root_tint(names.DEF_PATTERN), warm): self.assertAlmostEqual(a, b, places=6)   # default grey tabby as before
        with open(os.path.join(W, "scripts", "import_cat.py")) as fh: src = fh.read()
        self.assertIn("lerp(float3(1,1,1), U.rgb, saturate(W.r + W.g + W.b))", src)
        self.assertIn('("W", w, ""),', src[src.index("FUR_SHEEN_HLSL, ["):][:200])

    def test_status(self):
        st = lambda **kw: UI.status(**dict(dict(name="", active=True, level=B.LV_OFFICE, take_along=True, placed=True, mode=B.MODE_FOLLOW,
                                                state=B.ST_REST, posture=B.P_SIT, alarmed=False, purring=False), **kw))
        self.assertEqual(st(), "The cat: follows Jodi, sitting")
        self.assertEqual(st(name="Mira", purring=True), "Mira: follows Jodi, sitting (purring)")
        self.assertEqual(st(active=False), "The cat: switched off")
        self.assertEqual(st(level=B.LV_MISSION, take_along=False), "The cat: stays at home (take along is off)")
        self.assertEqual(st(placed=False), "The cat: on her way here")
        self.assertEqual(st(state=B.ST_MOVE, mode=B.MODE_ROAM), "The cat: roams, on her way")
        self.assertEqual(st(alarmed=True, state=B.ST_MOVE), "The cat: follows Jodi, frightened")
        self.assertEqual(st(dbg=(B.DBG_TURN, 7, 39, 45, 12, 3, 1)),
                         "The cat: follows Jodi, sitting | spot: turning #7 ok39/45 r12 t3 j1")
        self.assertTrue(st(dbg=UI.DBG_DEFAULT).endswith(" | spot: - #-1 ok0/0 r0 t0 j0"))

    def test_in_the_pak_list(self):
        import cat_seqs as CS
        pak = names.pak_assets(CS.ORDER, [m["name"] for m in CS.MONTAGES])
        for t in UI.TABLES: self.assertIn(t, pak)


if __name__ == "__main__":
    unittest.main()
