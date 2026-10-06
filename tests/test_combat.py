import sys, pathlib, tempfile, subprocess, unittest, json, os
import contextlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "combat" / "scripts"))
import combat


@contextlib.contextmanager
def mock_env(key, value):
    old = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


SHEET_BASE = {
    "schema_version": 1,
    "name": "占位",
    "player": "",
    "race": "变体人类",
    "classes": [{"name": "法师", "level": 2, "subclass": "塑能学派"}],
    "background": "银家族贵族（流亡）",
    "alignment": "混乱善良",
    "xp": 300,
    "abilities": {"str": 8, "dex": 10, "con": 13, "int": 16, "wis": 10, "cha": 16},
    "save_profs": ["int", "wis"],
    "skill_profs": [],
    "skill_expertise": [],
    "tool_profs": [],
    "weapon_profs": [],
    "ac": {"base": 10, "temp": 0},
    "hp": {"max": 12, "current": 12, "temp": 0},
    "hit_dice": {"die": "d6", "total": 2, "used": 0},
    "speed": 30,
    "initiative_bonus": None,
    "spellcasting": {"ability": "int", "slots": {"1": {"max": 3, "used": 0}}, "spells": [], "concentration": None},
    "attacks": [{"name": "火焰箭", "bonus": 5, "damage": "1d10", "damage_type": "火焰", "range": 120}],
    "features": [],
    "languages": [],
    "personality": {"traits": [], "ideals": [], "bonds": [], "flaws": []},
    "inventory": [{"name": "治疗药水", "qty": 2}],
    "gold": 0,
    "conditions": [],
    "death_saves": {"successes": 0, "failures": 0},
    "notes": "",
}


def write_card(dirpath, name, **over):
    base = json.loads(json.dumps(SHEET_BASE))
    base.update(over)
    base["name"] = name
    d = pathlib.Path(dirpath) / "角色卡_CharacterSheets"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return d


class TestStorage(unittest.TestCase):
    def test_default_dir_uses_env(self):
        with tempfile.TemporaryDirectory() as d, mock_env("DND_COMBAT_DIR", d):
            self.assertEqual(combat.resolve_combat_dir(), pathlib.Path(d))

    def test_cli_dir_beats_env(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b, \
             mock_env("DND_COMBAT_DIR", a):
            self.assertEqual(combat.resolve_combat_dir(b), pathlib.Path(b))

    def test_load_missing_raises_chinese(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(combat.CombatError):
                combat.load_combat("不存在", cli_dir=d)

    def test_load_corrupt_raises(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "坏.json").write_text("{bad", encoding="utf-8")
            with self.assertRaises(combat.CombatError):
                combat.load_combat("坏", cli_dir=d)

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            combat.save_combat("试", {"name": "试", "schema_version": 1}, cli_dir=d)
            self.assertEqual(combat.load_combat("试", cli_dir=d)["name"], "试")


class TestUnits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "因特·银")
        self.cdir = str(self.root / "combats")

    def test_new_combat_writes_default(self):
        combat.new_combat("遭遇", cli_dir=self.cdir)
        loaded = combat.load_combat("遭遇", cli_dir=self.cdir)
        self.assertEqual(loaded["grid"], {"width": 30, "height": 20, "cell_ft": 5})
        self.assertEqual(loaded["round"], 0)
        self.assertEqual(loaded["turn_index"], 0)
        self.assertEqual(loaded["order"], [])
        self.assertEqual(loaded["combatants"], {})

    def test_new_combat_exists_raises(self):
        combat.new_combat("遭遇", cli_dir=self.cdir)
        with self.assertRaises(combat.CombatError):
            combat.new_combat("遭遇", cli_dir=self.cdir)

    def test_add_loads_card(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(data, "因特·银", side="pc", pos={"x": 2, "y": 3},
                             cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        c = data["combatants"]["因特·银"]
        self.assertEqual(c["sheet"], "因特·银")
        self.assertEqual(c["side"], "pc")
        self.assertEqual(c["pos"], {"x": 2, "y": 3})
        self.assertIsNone(c["initiative"])
        self.assertFalse(c["dead"])

    def test_add_default_pos_is_origin(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(data, "因特·银", side="pc",
                             cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(data["combatants"]["因特·银"]["pos"], {"x": 0, "y": 0})

    def test_add_missing_card_raises(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        with self.assertRaises(combat.CombatError):
            combat.add_combatant(data, "不存在的人", cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_add_duplicate_raises(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(data, "因特·银", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        with self.assertRaises(combat.CombatError):
            combat.add_combatant(data, "因特·银", cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_remove_deletes_from_order_and_combatants(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(data, "因特·银", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        data["order"].append("因特·银")
        combat.remove_combatant(data, "因特·银")
        self.assertNotIn("因特·银", data["combatants"])
        self.assertNotIn("因特·银", data["order"])
        with self.assertRaises(combat.CombatError):
            combat.remove_combatant(data, "不存在的人")

    def test_end_keeps_file_and_logs(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.end_combat(data)
        combat.save_combat("遭遇", data, cli_dir=self.cdir)
        loaded = combat.load_combat("遭遇", cli_dir=self.cdir)
        self.assertEqual(loaded["name"], "遭遇")
        self.assertIn("战斗结束", loaded["log"])


class TestInitiative(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "甲")
        write_card(self.root, "乙")
        write_card(self.root, "丙")
        self.cdir = str(self.root / "combats")

    def _combat_with(self, names):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        for n in names:
            combat.add_combatant(data, n, side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        return data

    def test_set_initiative_stores_value(self):
        data = self._combat_with(["甲"])
        combat.set_initiative(data, "甲", 18)
        self.assertEqual(data["combatants"]["甲"]["initiative"], 18)

    def test_set_initiative_unknown_raises(self):
        data = self._combat_with(["甲"])
        with self.assertRaises(combat.CombatError):
            combat.set_initiative(data, "不存在", 10)

    def test_begin_sorts_desc(self):
        data = self._combat_with(["甲", "乙", "丙"])
        combat.set_initiative(data, "甲", 12)
        combat.set_initiative(data, "乙", 18)
        combat.set_initiative(data, "丙", 5)
        combat.begin_combat(data)
        self.assertEqual(data["order"], ["乙", "甲", "丙"])
        self.assertEqual(data["round"], 1)
        self.assertEqual(data["turn_index"], 0)

    def test_begin_requires_all_initiative(self):
        data = self._combat_with(["甲", "乙"])
        combat.set_initiative(data, "甲", 10)
        with self.assertRaises(combat.CombatError):
            combat.begin_combat(data)

    def test_begin_tie_is_stable(self):
        data = self._combat_with(["甲", "乙"])
        combat.set_initiative(data, "甲", 15)
        combat.set_initiative(data, "乙", 15)
        combat.begin_combat(data)
        self.assertEqual(data["order"], ["甲", "乙"])

    def test_current_actor(self):
        data = self._combat_with(["甲", "乙", "丙"])
        combat.set_initiative(data, "甲", 12)
        combat.set_initiative(data, "乙", 18)
        combat.set_initiative(data, "丙", 5)
        combat.begin_combat(data)
        self.assertEqual(combat.current_actor(data), "乙")
        data["order"] = []
        self.assertIsNone(combat.current_actor(data))


class TestConditions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "甲")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "甲", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_add_and_list(self):
        combat.cond_add(self.data, "甲", "中毒", rounds=3)
        self.assertIn({"name": "中毒", "rounds": 3},
                      self.data["combatants"]["甲"]["conditions"])

    def test_add_duplicate_raises(self):
        combat.cond_add(self.data, "甲", "中毒", rounds=3)
        with self.assertRaises(combat.CombatError):
            combat.cond_add(self.data, "甲", "中毒")

    def test_remove_missing_raises(self):
        with self.assertRaises(combat.CombatError):
            combat.cond_remove(self.data, "甲", "中毒")

    def test_tick_decrements_and_expires(self):
        combat.cond_add(self.data, "甲", "中毒", rounds=3)
        combat.tick_conditions(self.data, "甲")
        self.assertEqual(self.data["combatants"]["甲"]["conditions"][0]["rounds"], 2)
        combat.tick_conditions(self.data, "甲")
        removed = combat.tick_conditions(self.data, "甲")
        self.assertIn("中毒", removed)
        self.assertEqual(self.data["combatants"]["甲"]["conditions"], [])

    def test_tick_unlimited_stays(self):
        combat.cond_add(self.data, "甲", "专注")
        combat.tick_conditions(self.data, "甲")
        conds = self.data["combatants"]["甲"]["conditions"]
        self.assertEqual(len(conds), 1)
        self.assertIsNone(conds[0]["rounds"])


class TestTurns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "甲")
        write_card(self.root, "乙")
        write_card(self.root, "丙")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        for n in ["甲", "乙", "丙"]:
            combat.add_combatant(self.data, n, side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.set_initiative(self.data, "甲", 18)
        combat.set_initiative(self.data, "乙", 12)
        combat.set_initiative(self.data, "丙", 5)
        combat.begin_combat(self.data)

    def test_next_advances(self):
        combat.next_turn(self.data)
        self.assertEqual(combat.current_actor(self.data), "乙")

    def test_next_wraps_and_increments_round(self):
        combat.next_turn(self.data)
        combat.next_turn(self.data)
        combat.next_turn(self.data)
        self.assertEqual(combat.current_actor(self.data), "甲")
        self.assertEqual(self.data["round"], 2)

    def test_next_clears_reaction_of_new_actor(self):
        combat.set_reaction(self.data, "乙", "used")
        self.assertTrue(self.data["combatants"]["乙"]["reaction_used"])
        combat.next_turn(self.data)
        self.assertFalse(self.data["combatants"]["乙"]["reaction_used"])

    def test_next_ticks_conditions_at_turn_start(self):
        combat.cond_add(self.data, "乙", "中毒", rounds=1)
        combat.next_turn(self.data)
        self.assertEqual(self.data["combatants"]["乙"]["conditions"], [])

    def test_set_reaction_used_and_reset(self):
        combat.set_reaction(self.data, "甲", "used")
        self.assertTrue(self.data["combatants"]["甲"]["reaction_used"])
        combat.set_reaction(self.data, "甲", "reset")
        self.assertFalse(self.data["combatants"]["甲"]["reaction_used"])


class TestDistanceMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "甲")
        write_card(self.root, "乙")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "甲", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "乙", side="enemy", cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def _set_pos(self, name, x, y):
        self.data["combatants"][name]["pos"] = {"x": x, "y": y}

    def test_distance_orthogonal(self):
        self._set_pos("乙", 3, 0)
        self.assertEqual(combat.distance_between(self.data, "甲", "乙"), 15)

    def test_distance_diagonal_uses_max(self):
        self._set_pos("乙", 3, 4)
        self.assertEqual(combat.distance_between(self.data, "甲", "乙"), 20)

    def test_distance_same_tile_zero(self):
        self.assertEqual(combat.distance_between(self.data, "甲", "甲"), 0)

    def test_move_within_speed_ok(self):
        combat.move_combatant(self.data, "甲", 6, 0, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(self.data["combatants"]["甲"]["pos"], {"x": 6, "y": 0})

    def test_move_over_speed_raises(self):
        with self.assertRaises(combat.CombatError):
            combat.move_combatant(self.data, "甲", 7, 0, cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_move_force_allows(self):
        combat.move_combatant(self.data, "甲", 7, 0, force=True, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(self.data["combatants"]["甲"]["pos"], {"x": 7, "y": 0})

    def test_move_out_of_bounds_raises(self):
        with self.assertRaises(combat.CombatError):
            combat.move_combatant(self.data, "甲", 30, 0, force=True, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        with self.assertRaises(combat.CombatError):
            combat.move_combatant(self.data, "甲", 0, -1, force=True, cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_distance_unknown_unit_raises(self):
        with self.assertRaises(combat.CombatError):
            combat.distance_between(self.data, "甲", "幽灵")


class TestSheetActions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "甲", hp={"max": 12, "current": 12, "temp": 5})
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "甲", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def _read(self, name="甲"):
        return json.loads((self.sheet_dir / f"{name}.json").read_text(encoding="utf-8"))

    def _rewrite(self, name="甲", **over):
        return write_card(self.root, name, **over)

    def _call(self, fn, *a, **kw):
        return fn(self.data, "甲", *a, cli_dir=self.cdir, sheet_dir=self.sheet_dir, **kw)

    def test_damage_absorbs_temp_then_current(self):
        self._call(combat.damage_combatant, 8)
        hp = self._read()["hp"]
        self.assertEqual(hp["temp"], 0)
        self.assertEqual(hp["current"], 9)

    def test_damage_clamps_zero_and_warns(self):
        msg = self._call(combat.damage_combatant, 99)
        self.assertEqual(self._read()["hp"]["current"], 0)
        self.assertIn("死亡豁免", msg)

    def test_heal_restores_current(self):
        self._rewrite(hp={"max": 12, "current": 5, "temp": 0})
        self._call(combat.heal_combatant, 3)
        self.assertEqual(self._read()["hp"]["current"], 8)

    def test_heal_with_item_decrements_inventory(self):
        msg = self._call(combat.heal_combatant, 3, item="治疗药水")
        inv = {i["name"]: i["qty"] for i in self._read()["inventory"]}
        self.assertEqual(inv["治疗药水"], 1)
        self.assertIn("治疗药水", msg)

    def test_heal_missing_item_raises(self):
        with self.assertRaises(combat.CombatError):
            self._call(combat.heal_combatant, 3, item="不存在药水")

    def test_adjust_ac_temp(self):
        self._call(combat.adjust_ac_combatant, "+", 3)
        self.assertEqual(self._read()["ac"]["temp"], 3)

    def test_use_slot(self):
        self._call(combat.use_slot_combatant, "1", 1)
        self.assertEqual(self._read()["spellcasting"]["slots"]["1"]["used"], 1)

    def test_give_xp(self):
        self._call(combat.give_xp, 100)
        self.assertEqual(self._read()["xp"], 400)


class TestKill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "阿")
        write_card(self.root, "贝")
        write_card(self.root, "妖精")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "阿", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "贝", side="npc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "妖精", side="enemy", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        for name, val in (("阿", 15), ("贝", 10), ("妖精", 5)):
            combat.set_initiative(self.data, name, val)
        combat.begin_combat(self.data)

    def _xp(self, name):
        return json.loads((self.sheet_dir / f"{name}.json").read_text(encoding="utf-8"))["xp"]

    def test_kill_marks_dead_and_removes_from_order(self):
        combat.kill_combatant(self.data, "妖精", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertTrue(self.data["combatants"]["妖精"]["dead"])
        self.assertNotIn("妖精", self.data["order"])

    def test_kill_current_actor_keeps_turn_index_valid(self):
        combat.kill_combatant(self.data, "阿", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertLess(self.data["turn_index"], len(self.data["order"]))
        self.assertIn(combat.next_turn(self.data), self.data["order"])

    def test_kill_with_xp_splits_evenly(self):
        combat.kill_combatant(self.data, "妖精", xp=100, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(self._xp("阿"), 350)
        self.assertEqual(self._xp("贝"), 350)

    def test_kill_xp_remainder_reported(self):
        msg = combat.kill_combatant(self.data, "妖精", xp=101, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(self._xp("阿"), 350)
        self.assertIn("余 1", msg)

    def test_kill_explicit_share(self):
        combat.kill_combatant(self.data, "妖精", xp=100, share=["阿"], cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(self._xp("阿"), 400)
        self.assertEqual(self._xp("贝"), 300)

    def test_kill_unknown_raises(self):
        with self.assertRaises(combat.CombatError):
            combat.kill_combatant(self.data, "不存在", cli_dir=self.cdir, sheet_dir=self.sheet_dir)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "阿")
        write_card(self.root, "妖精")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "阿", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "妖精", side="enemy", pos={"x": 3, "y": 0}, cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.set_initiative(self.data, "阿", 15)
        combat.set_initiative(self.data, "妖精", 5)
        combat.begin_combat(self.data)

    def test_status_includes_hp_ac_attacks(self):
        text = combat.render_status(self.data, sheet_dir=self.sheet_dir)
        self.assertIn("阿", text)
        self.assertIn("12/12", text)
        self.assertIn("AC", text)
        self.assertIn("火焰箭", text)

    def test_status_marks_current_actor(self):
        text = combat.render_status(self.data, sheet_dir=self.sheet_dir)
        marked = [ln for ln in text.splitlines() if ln.lstrip().startswith("→")]
        self.assertEqual(len(marked), 1)
        self.assertIn("阿", marked[0])

    def test_status_json_shape(self):
        sd = combat.status_data(self.data, sheet_dir=self.sheet_dir)
        self.assertEqual(sd["current"], combat.current_actor(self.data))
        row = [r for r in sd["rows"] if r["name"] == "妖精"][0]
        self.assertEqual(row["pos"], {"x": 3, "y": 0})
        self.assertIn("conditions", row)
        self.assertEqual(row["side"], "enemy")

    def test_status_handles_missing_card(self):
        (self.sheet_dir / "妖精.json").unlink()
        text = combat.render_status(self.data, sheet_dir=self.sheet_dir)
        self.assertIn("缺卡", text)


class TestSvg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "阿")
        write_card(self.root, "贝")
        write_card(self.root, "妖精")
        self.cdir = str(self.root / "combats")
        self.data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(self.data, "阿", side="pc", pos={"x": 1, "y": 1},
                             cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "贝", side="npc", pos={"x": 4, "y": 2},
                             cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(self.data, "妖精", side="enemy", pos={"x": 7, "y": 3},
                             cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.set_initiative(self.data, "阿", 15)
        combat.set_initiative(self.data, "贝", 10)
        combat.set_initiative(self.data, "妖精", 5)
        combat.begin_combat(self.data)

    def test_svg_has_root_and_grid(self):
        svg = combat.render_svg(self.data)
        self.assertIn("<svg", svg)
        self.assertIn("width=", svg)
        self.assertIn("<line", svg)

    def test_svg_has_tokens_with_sides(self):
        svg = combat.render_svg(self.data)
        self.assertIn("#3b82f6", svg)
        self.assertIn("#22c55e", svg)
        self.assertIn("#ef4444", svg)
        self.assertEqual(svg.count("<circle"), 3)

    def test_svg_marks_current_actor(self):
        svg = combat.render_svg(self.data)
        self.assertIn("#f59e0b", svg)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "阿")
        write_card(self.root, "妖精")
        self.cdir = self.root / "combats"
        self.env = dict(os.environ)
        self.env["DND_COMBAT_DIR"] = str(self.cdir)
        self.env["DND_SHEET_DIR"] = str(self.sheet_dir)
        self.script = str(ROOT / ".opencode" / "skill" / "combat" / "scripts" / "combat.py")

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, self.script, *args],
            capture_output=True, text=True, encoding="utf-8", env=self.env,
        )

    def test_full_flow(self):
        steps = [
            ("new", "遭遇"),
            ("add", "遭遇", "阿", "--side", "pc"),
            ("add", "遭遇", "妖精", "--pos", "3,0"),
            ("init", "遭遇", "阿", "15"),
            ("init", "遭遇", "妖精", "5"),
            ("begin", "遭遇"),
            ("next", "遭遇"),
        ]
        for s in steps:
            r = self._run(*s)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
        r = self._run("status", "遭遇", "--json")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("rows", json.loads(r.stdout))

    def test_map_writes_svg(self):
        for s in [("new", "遭遇"), ("add", "遭遇", "阿", "--side", "pc"),
                  ("init", "遭遇", "阿", "15"), ("begin", "遭遇")]:
            self._run(*s)
        out = self.root / "map.svg"
        r = self._run("map", "遭遇", "--out", str(out))
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("<svg", out.read_text(encoding="utf-8"))

    def test_svg_writes_file_via_cli(self):
        for s in [("new", "遭遇"), ("add", "遭遇", "阿", "--side", "pc"),
                  ("init", "遭遇", "阿", "15"), ("begin", "遭遇")]:
            self._run(*s)
        out = self.root / "m2.svg"
        r = self._run("map", "遭遇", "--out", str(out))
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn(str(out), r.stdout)
        self.assertTrue(out.exists())

    def test_unknown_combat_exit2(self):
        r = self._run("status", "不存在")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_begin_without_init_exit2(self):
        self._run("new", "遭遇")
        self._run("add", "遭遇", "阿", "--side", "pc")
        r = self._run("begin", "遭遇")
        self.assertEqual(r.returncode, 2)

    def test_move_over_speed_exit2(self):
        for s in [("new", "遭遇"), ("add", "遭遇", "阿", "--side", "pc")]:
            self._run(*s)
        r = self._run("move", "遭遇", "阿", "7", "0")
        self.assertEqual(r.returncode, 2)

    def test_utf8_pipe_not_garbled(self):
        self._run("new", "遭遇")
        r = self._run("status", "遭遇", "--json")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertEqual(json.loads(r.stdout)["name"], "遭遇")


class TestDocs(unittest.TestCase):
    def test_skill_md_exists(self):
        text = (ROOT / ".opencode" / "skill" / "combat" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: combat", text)
        self.assertIn("scripts/combat.py", text)
        self.assertIn("reference/rules.md", text)

    def test_rules_md_exists(self):
        text = (ROOT / ".opencode" / "skill" / "combat" / "reference" / "rules.md").read_text(encoding="utf-8")
        self.assertIn("先攻", text)
        self.assertIn("奇袭", text)
        self.assertIn("回合", text)


class TestFinalReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.sheet_dir = write_card(self.root, "阿")
        for n in ["贝", "丙", "妖精"]:
            write_card(self.root, n)
        self.cdir = str(self.root / "combats")

    def _three(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        for n, v in (("阿", 18), ("贝", 12), ("丙", 5)):
            combat.add_combatant(data, n, side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
            combat.set_initiative(data, n, v)
        combat.begin_combat(data)
        return data

    def test_remove_current_actor_keeps_index_valid(self):
        data = self._three()
        combat.next_turn(data)
        combat.next_turn(data)
        self.assertEqual(combat.current_actor(data), "丙")
        combat.remove_combatant(data, "丙")
        self.assertLess(data["turn_index"], len(data["order"]))
        self.assertIn(combat.current_actor(data), data["order"])

    def test_remove_prior_unit_keeps_current(self):
        data = self._three()
        combat.next_turn(data)
        combat.next_turn(data)
        combat.remove_combatant(data, "阿")
        self.assertEqual(combat.current_actor(data), "丙")

    def test_kill_prior_unit_keeps_current(self):
        data = self._three()
        combat.next_turn(data)
        combat.kill_combatant(data, "阿", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        self.assertEqual(combat.current_actor(data), "贝")

    def test_kill_xp_atomic_when_share_missing(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        combat.add_combatant(data, "阿", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(data, "贝", side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.add_combatant(data, "妖精", side="enemy", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        (self.sheet_dir / "贝.json").unlink()
        before = json.loads((self.sheet_dir / "阿.json").read_text(encoding="utf-8"))["xp"]
        with self.assertRaises(combat.CombatError):
            combat.kill_combatant(data, "妖精", xp=100, share=["阿", "贝"],
                                  cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        after = json.loads((self.sheet_dir / "阿.json").read_text(encoding="utf-8"))["xp"]
        self.assertEqual(after, before)
        self.assertFalse(data["combatants"]["妖精"]["dead"])

    def test_add_pos_out_of_bounds_raises(self):
        data = combat.new_combat("遭遇", cli_dir=self.cdir)
        with self.assertRaises(combat.CombatError):
            combat.add_combatant(data, "阿", pos={"x": 999, "y": 0},
                                 cli_dir=self.cdir, sheet_dir=self.sheet_dir)

    def test_begin_reports_tie(self):
        data = combat.new_combat("平手战", cli_dir=self.cdir)
        for n in ["阿", "贝"]:
            combat.add_combatant(data, n, side="pc", cli_dir=self.cdir, sheet_dir=self.sheet_dir)
        combat.set_initiative(data, "阿", 10)
        combat.set_initiative(data, "贝", 10)
        msg = combat.begin_combat(data)
        self.assertIn("平手", msg)

    def test_skill_md_cond_arg_order(self):
        text = (ROOT / ".opencode" / "skill" / "combat" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("cond <战斗名> <单位名> add", text)


if __name__ == "__main__":
    unittest.main()
