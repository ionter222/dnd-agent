import sys, pathlib, tempfile, subprocess, unittest, json, os
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "character-sheet" / "scripts"))
import sheet


class TestStorage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip(self):
        sheet.save_sheet("测试", {"schema_version": 1, "name": "测试"}, self.dir)
        self.assertEqual(sheet.load_sheet("测试", self.dir)["name"], "测试")

    def test_load_missing_raises(self):
        with self.assertRaises(sheet.SheetError):
            sheet.load_sheet("不存在", self.dir)

    def test_load_bad_json_raises(self):
        (pathlib.Path(self.dir) / "坏.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(sheet.SheetError):
            sheet.load_sheet("坏", self.dir)

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"DND_SHEET_DIR": self.dir}):
            self.assertEqual(sheet.resolve_sheet_dir(), pathlib.Path(self.dir))

    def test_cli_dir_beats_env(self):
        with mock.patch.dict(os.environ, {"DND_SHEET_DIR": "X"}):
            self.assertEqual(sheet.resolve_sheet_dir(self.dir), pathlib.Path(self.dir))


SAMPLE = {
    "schema_version": 1, "name": "薇拉",
    "classes": [{"name": "法师", "level": 5, "subclass": "预言学派"}],
    "abilities": {"str": 8, "dex": 14, "con": 12, "int": 16, "wis": 10, "cha": 13},
    "save_profs": ["int", "wis"], "skill_profs": ["奥秘", "调查", "历史"],
    "skill_expertise": [], "ac": {"base": 12, "temp": 0},
    "hp": {"max": 27, "current": 27, "temp": 0},
    "speed": 30, "initiative_bonus": 2,
    "spellcasting": {"ability": "int", "slots": {}, "spells": [], "concentration": None},
}


class TestDerived(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(sheet.total_level(SAMPLE), 5)
        self.assertEqual(sheet.proficiency_bonus(SAMPLE), 3)

    def test_floor_negative_modifier(self):
        self.assertEqual(sheet.ability_modifier(8), -1)
        self.assertEqual(sheet.ability_modifier(14), 2)
        self.assertEqual(sheet.ability_modifier(10), 0)

    def test_multiclass_levels_sum(self):
        d = dict(SAMPLE, classes=[{"name": "法师", "level": 3}, {"name": "牧师", "level": 2}])
        self.assertEqual(sheet.total_level(d), 5)

    def test_save_and_skill(self):
        self.assertEqual(sheet.save_bonus(SAMPLE, "int"), 6)   # 3 + 3
        self.assertEqual(sheet.save_bonus(SAMPLE, "str"), -1)  # 未熟练
        self.assertEqual(sheet.skill_bonus(SAMPLE, "奥秘"), 6)
        self.assertEqual(sheet.skill_bonus(SAMPLE, "察觉"), 0)

    def test_expertise_stacks(self):
        d = dict(SAMPLE, skill_expertise=["奥秘"])
        self.assertEqual(sheet.skill_bonus(d, "奥秘"), 9)      # 3 + 3 + 3

    def test_passive_spell_ac_init(self):
        self.assertEqual(sheet.passive_perception(SAMPLE), 10)
        self.assertEqual(sheet.spell_dc(SAMPLE), 14)           # 8 + 3 + 3
        self.assertEqual(sheet.spell_attack_bonus(SAMPLE), 6)
        self.assertEqual(sheet.armor_class(SAMPLE), 12)
        self.assertEqual(sheet.initiative_bonus(SAMPLE), 2)

    def test_initiative_defaults_to_dex(self):
        d = {k: v for k, v in SAMPLE.items() if k != "initiative_bonus"}
        self.assertEqual(sheet.initiative_bonus(d), 2)


class TestNew(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.dir = self._tmp.name
    def tearDown(self):
        self._tmp.cleanup()
    def test_default_template(self):
        d = sheet.default_sheet("新人")
        self.assertEqual(d["name"], "新人")
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(set(d["abilities"]), set(sheet.ABILITIES))
        self.assertTrue(all(v == 10 for v in d["abilities"].values()))
        self.assertEqual(d["classes"][0]["level"], 1)
    def test_new_persists(self):
        sheet.new_sheet("新人", None, self.dir)
        self.assertEqual(sheet.load_sheet("新人", self.dir)["name"], "新人")
    def test_new_existing_raises(self):
        sheet.new_sheet("新人", None, self.dir)
        with self.assertRaises(sheet.SheetError):
            sheet.new_sheet("新人", None, self.dir)
    def test_new_from_template(self):
        sheet.save_sheet("源", {**sheet.default_sheet("源"), "abilities": {**sheet.default_sheet("源")["abilities"], "int": 16}}, self.dir)
        d = sheet.new_sheet("副本", "源", self.dir)
        self.assertEqual(d["abilities"]["int"], 16)
        self.assertEqual(d["name"], "副本")
    def test_list_summaries(self):
        sheet.save_sheet("甲", {**sheet.default_sheet("甲"), "hp": {"max": 20, "current": 15, "temp": 0}}, self.dir)
        rows = sheet.list_sheets(self.dir)
        self.assertEqual(rows[0]["name"], "甲")
        self.assertEqual(rows[0]["level"], 1)
        self.assertEqual(rows[0]["hp_current"], 15)


def _hp_sheet(**hp):
    base = sheet.default_sheet("测试")
    base["hp"] = {"max": 30, "current": 30, "temp": 0, **hp}
    return base


class TestHpSlot(unittest.TestCase):
    def test_damage_uses_temp_first(self):
        d = _hp_sheet(current=20, temp=5)
        sheet.apply_hp(d, -8)
        self.assertEqual((d["hp"]["temp"], d["hp"]["current"]), (0, 17))

    def test_heal_does_not_touch_temp(self):
        d = _hp_sheet(current=20, temp=5)
        sheet.apply_hp(d, 6)
        self.assertEqual((d["hp"]["temp"], d["hp"]["current"]), (5, 26))

    def test_clamp_zero_and_hint(self):
        d = _hp_sheet(current=3, temp=0)
        msg = sheet.apply_hp(d, -10)
        self.assertEqual(d["hp"]["current"], 0)
        self.assertIn("死亡豁免", msg)

    def test_clamp_max(self):
        d = _hp_sheet(current=28, temp=0)
        sheet.apply_hp(d, 10)
        self.assertEqual(d["hp"]["current"], 30)

    def test_set_hp_bounds(self):
        with self.assertRaises(sheet.SheetError):
            sheet.set_hp(_hp_sheet(), 999)

    def test_set_hp_max_lowers_current(self):
        d = _hp_sheet(current=30)
        sheet.set_hp_max(d, 25)
        self.assertEqual((d["hp"]["max"], d["hp"]["current"]), (25, 25))

    def test_slot_use_restore(self):
        d = sheet.default_sheet("测试")
        d["spellcasting"]["slots"] = {"1": {"max": 4, "used": 0}}
        sheet.use_slot(d, "1", 2)
        self.assertEqual(d["spellcasting"]["slots"]["1"]["used"], 2)
        sheet.use_slot(d, "1", 1, restore=True)
        self.assertEqual(d["spellcasting"]["slots"]["1"]["used"], 1)

    def test_slot_overuse_raises(self):
        d = sheet.default_sheet("测试")
        d["spellcasting"]["slots"] = {"1": {"max": 4, "used": 3}}
        with self.assertRaises(sheet.SheetError):
            sheet.use_slot(d, "1", 5)


class TestAcCondDeath(unittest.TestCase):
    def test_ac_ops(self):
        d = sheet.default_sheet("测试")
        sheet.modify_ac(d, "+", 5)
        self.assertEqual(d["ac"]["temp"], 5)
        sheet.modify_ac(d, "-", 2)
        self.assertEqual(d["ac"]["temp"], 3)
        sheet.modify_ac(d, "set", 4)
        self.assertEqual(d["ac"]["temp"], 4)
        sheet.modify_ac(d, "reset")
        self.assertEqual(d["ac"]["temp"], 0)

    def test_cond_add_remove(self):
        d = sheet.default_sheet("测试")
        sheet.cond_add(d, "束缚")
        self.assertEqual(d["conditions"], ["束缚"])
        with self.assertRaises(sheet.SheetError):
            sheet.cond_add(d, "束缚")
        sheet.cond_remove(d, "束缚")
        self.assertEqual(d["conditions"], [])
        with self.assertRaises(sheet.SheetError):
            sheet.cond_remove(d, "束缚")

    def test_death_saves(self):
        d = sheet.default_sheet("测试")
        for _ in range(3):
            msg = sheet.death_save(d, "failure")
        self.assertIn("死亡", msg)
        self.assertEqual(d["death_saves"]["failures"], 3)
        sheet.death_save(d, "reset")
        self.assertEqual(d["death_saves"], {"successes": 0, "failures": 0})

    def test_death_save_cap(self):
        d = sheet.default_sheet("测试")
        for _ in range(3):
            sheet.death_save(d, "success")
        with self.assertRaises(sheet.SheetError):
            sheet.death_save(d, "success")


class TestPaths(unittest.TestCase):
    def test_get_nested(self):
        d = {**SAMPLE, "spellcasting": {"ability": "int", "slots": {"2": {"max": 3, "used": 1}}, "spells": [], "concentration": None}}
        self.assertEqual(sheet.get_path(d, "spellcasting.slots.2.used"), 1)
        self.assertEqual(sheet.get_path(d, "abilities.dex"), 14)
    def test_get_missing_raises(self):
        with self.assertRaises(sheet.SheetError):
            sheet.get_path(SAMPLE, "abilities.luck")
    def test_set_path(self):
        d = json.loads(json.dumps(SAMPLE))
        sheet.set_path(d, "abilities.str", 12)
        self.assertEqual(d["abilities"]["str"], 12)
    def test_add_path_non_numeric_raises(self):
        with self.assertRaises(sheet.SheetError):
            sheet.add_path(SAMPLE, "name", 1)
    def test_check_and_save(self):
        self.assertEqual(sheet.check_bonus(SAMPLE, "奥秘"), 6)
        self.assertEqual(sheet.save_bonus_value(SAMPLE, "int"), 6)
        with self.assertRaises(sheet.SheetError):
            sheet.check_bonus(SAMPLE, "不存在技能")


class TestValidate(unittest.TestCase):
    def test_valid_sample_clean(self):
        self.assertEqual(sheet.validate_sheet(SAMPLE), [])

    def test_catches_multiple(self):
        d = json.loads(json.dumps(SAMPLE))
        d["abilities"]["str"] = 99
        d["hp"] = {"max": 10, "current": 20, "temp": 0}
        d["skill_expertise"] = ["奥秘", "隐匿"]
        probs = sheet.validate_sheet(d)
        self.assertTrue(any("属性" in p for p in probs))
        self.assertTrue(any("hp" in p.lower() or "HP" in p for p in probs))
        self.assertTrue(any("专精" in p for p in probs))

    def test_missing_schema_version(self):
        d = json.loads(json.dumps(SAMPLE))
        del d["schema_version"]
        self.assertTrue(any("schema_version" in p for p in sheet.validate_sheet(d)))


class TestMarkdown(unittest.TestCase):
    def test_contains_key_facts(self):
        md = sheet.render_markdown(SAMPLE)
        self.assertIn("# 薇拉", md)
        self.assertIn("法师", md)
        self.assertIn("16", md)
        self.assertIn("+3", md)
        self.assertIn("12", md)
        self.assertIn("奥秘", md)

    def test_missing_fields_dont_crash(self):
        md = sheet.render_markdown(
            {"name": "极简", "abilities": {}, "classes": [], "ac": {}, "hp": {}}
        )
        self.assertIn("# 极简", md)


class TestCLI(unittest.TestCase):
    def _run(self, *args, dir=None):
        script = str(ROOT / ".opencode" / "skill" / "character-sheet" / "scripts" / "sheet.py")
        return subprocess.run([sys.executable, script, "--dir", dir, *args],
                              capture_output=True, text=True, encoding="utf-8")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_show_json(self):
        self.assertEqual(self._run("new", "武", dir=self.dir).returncode, 0)
        p = self._run("show", "武", "--json", dir=self.dir)
        self.assertEqual(json.loads(p.stdout)["name"], "武")

    def test_hp_persists(self):
        self._run("new", "武", dir=self.dir)
        self._run("hp", "武", "-5", dir=self.dir)
        p = self._run("get", "武", "hp.current", dir=self.dir)
        self.assertEqual(p.stdout.strip(), "5")

    def test_missing_sheet_exit2(self):
        p = self._run("show", "不存在", dir=self.dir)
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.stderr.strip())

    def test_validate_reports(self):
        self._run("new", "武", dir=self.dir)
        p = self._run("validate", "武", dir=self.dir)
        self.assertEqual(p.returncode, 0)

    def test_show_write_md(self):
        self._run("new", "武", dir=self.dir)
        self._run("show", "武", "--md", "--write", dir=self.dir)
        self.assertTrue((pathlib.Path(self.dir) / "武.md").exists())

    def test_utf8_pipe(self):
        self._run("new", "武", dir=self.dir)
        p = self._run("show", "武", "--json", dir=self.dir)
        json.loads(p.stdout)  # 中文不乱码才能解析


class TestDocs(unittest.TestCase):
    def test_skill_md(self):
        text = (ROOT / ".opencode" / "skill" / "character-sheet" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: character-sheet", text)
        self.assertIn("scripts/sheet.py", text)
        self.assertIn("reference/schema.md", text)

    def test_schema_md(self):
        text = (ROOT / ".opencode" / "skill" / "character-sheet" / "reference" / "schema.md").read_text(encoding="utf-8")
        self.assertIn("schema_version", text)
        self.assertIn("熟练", text)

    def test_build_guide_in_skill(self):
        text = (ROOT / ".opencode" / "skill" / "character-sheet" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("建卡流程", text)

    def test_statblock_mapping_in_schema(self):
        text = (ROOT / ".opencode" / "skill" / "character-sheet" / "reference" / "schema.md").read_text(encoding="utf-8")
        self.assertIn("statblock", text)
        self.assertIn("怪物", text)


class TestFinalReview(unittest.TestCase):
    def _run(self, *args):
        script = str(ROOT / ".opencode" / "skill" / "character-sheet" / "scripts" / "sheet.py")
        return subprocess.run([sys.executable, script, "--dir", self.dir, *args],
                              capture_output=True, text=True, encoding="utf-8")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_set_parses_json_value(self):
        self._run("new", "薇拉")
        r = self._run("set", "薇拉", "abilities.str", "16")
        self.assertEqual(r.returncode, 0)
        g = self._run("get", "薇拉", "abilities.str", "--json")
        self.assertEqual(g.stdout.strip(), "16")
        self.assertEqual(self._run("check", "薇拉", "运动").returncode, 0)

    def test_set_string_value_stays_string(self):
        self._run("new", "薇拉")
        self._run("set", "薇拉", "notes", "你好")
        g = self._run("get", "薇拉", "notes", "--json")
        self.assertIn("你好", g.stdout)

    def test_non_integer_args_chinese_exit2(self):
        self._run("new", "薇拉")
        for argv in [("hp", "薇拉", "三"), ("hp-set", "薇拉", "abc"),
                     ("hp-max", "薇拉", "x"), ("slot", "薇拉", "1", "y"),
                     ("add", "薇拉", "xp", "abc")]:
            r = self._run(*argv)
            self.assertEqual(r.returncode, 2, argv)
            self.assertTrue(r.stderr.strip(), argv)

    def test_list_survives_incomplete_and_corrupt(self):
        self._run("new", "好人")
        d = pathlib.Path(self.dir)
        (d / "残缺.json").write_text('{"name":"残缺"}', encoding="utf-8")
        (d / "损坏.json").write_text("{not json", encoding="utf-8")
        r = self._run("list", "--json")
        self.assertEqual(r.returncode, 0)
        names = [x["name"] for x in json.loads(r.stdout)]
        self.assertIn("好人", names)

    def test_markdown_initiative_uses_bonus(self):
        d = json.loads(json.dumps(SAMPLE))
        d["initiative_bonus"] = 5
        self.assertIn("先攻: +5", sheet.render_markdown(d))
        sheet.render_markdown({"name": "极简", "abilities": {}, "classes": [], "ac": {}, "hp": {}})

    def test_ac_op_requires_value(self):
        self._run("new", "薇拉")
        for argv in [("ac", "薇拉", "+"), ("ac", "薇拉", "-"), ("ac", "薇拉", "set")]:
            r = self._run(*argv)
            self.assertEqual(r.returncode, 2, argv)
            self.assertTrue(r.stderr.strip(), argv)


class TestFeatures(unittest.TestCase):
    def test_markdown_includes_features(self):
        d = json.loads(json.dumps(SAMPLE))
        d["features"] = ["奥术恢复", "塑像鬼才"]
        md = sheet.render_markdown(d)
        self.assertIn("## 特性", md)
        self.assertIn("奥术恢复", md)
        self.assertIn("塑像鬼才", md)

    def test_markdown_without_features_has_no_section(self):
        d = json.loads(json.dumps(SAMPLE))
        d["features"] = []
        self.assertNotIn("## 特性", sheet.render_markdown(d))


class TestLanguages(unittest.TestCase):
    def test_markdown_includes_languages(self):
        d = sheet.default_sheet("语者")
        d["languages"] = ["通用语", "龙语", "精灵语"]
        md = sheet.render_markdown(d)
        self.assertIn("## 语言", md)
        self.assertIn("龙语", md)
        self.assertIn("精灵语", md)

    def test_markdown_without_languages_has_no_section(self):
        d = sheet.default_sheet("无")
        d.pop("languages", None)
        self.assertNotIn("## 语言", sheet.render_markdown(d))


class TestPersonality(unittest.TestCase):
    def test_markdown_includes_personality(self):
        d = sheet.default_sheet("人")
        d["personality"] = {
            "traits": ["理想主义，能帮就帮"],
            "ideals": ["建立正义公平的国土"],
            "bonds": ["半身人朋友"],
            "flaws": ["幽闭恐惧症"],
        }
        md = sheet.render_markdown(d)
        self.assertIn("## 人格", md)
        self.assertIn("建立正义公平的国土", md)
        self.assertIn("幽闭恐惧症", md)

    def test_markdown_without_personality_has_no_section(self):
        d = sheet.default_sheet("无")
        d.pop("personality", None)
        self.assertNotIn("## 人格", sheet.render_markdown(d))


class TestProfs(unittest.TestCase):
    def test_markdown_includes_tool_and_weapon_profs(self):
        d = sheet.default_sheet("人")
        d["tool_profs"] = ["书法工具"]
        d["weapon_profs"] = ["匕首", "法杖"]
        md = sheet.render_markdown(d)
        self.assertIn("工具熟练: 书法工具", md)
        self.assertIn("武器熟练:", md)
        self.assertIn("匕首", md)

    def test_markdown_empty_profs_show_none(self):
        md = sheet.render_markdown(sheet.default_sheet("无"))
        self.assertIn("工具熟练: 无", md)
        self.assertIn("武器熟练: 无", md)

    def test_default_sheet_has_prof_fields(self):
        d = sheet.default_sheet("人")
        self.assertEqual(d["tool_profs"], [])
        self.assertEqual(d["weapon_profs"], [])


if __name__ == "__main__":
    unittest.main()
