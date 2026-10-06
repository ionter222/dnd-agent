import sys, pathlib, tempfile, subprocess, unittest, json, os
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "module" / "scripts"))
import module as mod


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_then_load_roundtrip(self):
        mod.save_run("甲", {"name": "甲", "module": "矿坑"}, self.dir)
        self.assertEqual(mod.load_run("甲", self.dir)["module"], "矿坑")

    def test_load_missing_raises_chinese(self):
        with self.assertRaises(mod.ModuleError):
            mod.load_run("无此运行", self.dir)

    def test_load_corrupt_raises(self):
        p = mod.run_path("坏", self.dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not json", encoding="utf-8")
        with self.assertRaises(mod.ModuleError):
            mod.load_run("坏", self.dir)

    def test_name_traversal_rejected(self):
        with self.assertRaises(mod.ModuleError):
            mod.run_path("../escaped", self.dir)

    def test_env_fallback(self):
        with mock.patch.dict(os.environ, {"DND_MODULE_DIR": self.dir}):
            self.assertEqual(mod.resolve_run_dir(), pathlib.Path(self.dir))


class TestRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_run_defaults(self):
        mod.new_run("矿坑1", "凡戴尔的失落矿坑", self.dir)
        d = mod.load_run("矿坑1", self.dir)
        self.assertEqual(d["module"], "凡戴尔的失落矿坑")
        self.assertIsNone(d["campaign"])
        self.assertIsNone(d["current"])
        self.assertEqual(d["visited"], [])
        self.assertEqual(d["schema_version"], 1)

    def test_new_duplicate_raises(self):
        mod.new_run("矿坑1", "m", self.dir)
        with self.assertRaises(mod.ModuleError):
            mod.new_run("矿坑1", "m", self.dir)

    def test_list_runs_sorted(self):
        mod.new_run("甲", "m", self.dir)
        mod.new_run("乙", "m", self.dir)
        names = [r["name"] for r in mod.list_runs(self.dir)]
        self.assertEqual(names, ["乙", "甲"])

    def test_remove_run(self):
        mod.new_run("甲", "m", self.dir)
        mod.remove_run("甲", self.dir)
        with self.assertRaises(mod.ModuleError):
            mod.load_run("甲", self.dir)

    def test_link_unlink(self):
        mod.new_run("甲", "m", self.dir)
        mod.link_campaign("甲", "战役X", self.dir)
        self.assertEqual(mod.load_run("甲", self.dir)["campaign"], "战役X")
        mod.unlink_campaign("甲", self.dir)
        self.assertIsNone(mod.load_run("甲", self.dir)["campaign"])


class TestScene(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        mod.new_run("甲", "矿坑", cli_dir=self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scene_sets_current_and_visits(self):
        mod.set_scene("甲", "地精巢穴", cli_dir=self.dir)
        d = mod.load_run("甲", self.dir)
        self.assertEqual(d["current"], "地精巢穴")
        self.assertEqual(d["visited"], ["地精巢穴"])

    def test_visit_dedupes(self):
        mod.visit("甲", "村口", cli_dir=self.dir)
        mod.visit("甲", "村口", cli_dir=self.dir)
        self.assertEqual(mod.load_run("甲", self.dir)["visited"], ["村口"])

    def test_scene_does_not_duplicate_visited(self):
        mod.visit("甲", "地精巢穴", cli_dir=self.dir)
        mod.set_scene("甲", "地精巢穴", cli_dir=self.dir)
        self.assertEqual(mod.load_run("甲", self.dir)["visited"], ["地精巢穴"])


class TestClues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        mod.new_run("甲", "矿坑", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clue_add(self):
        mod.clue_add("甲", "血手印", detail="在酒窖门后", cli_dir=self.dir)
        clues = mod.load_run("甲", self.dir)["clues"]
        self.assertEqual(len(clues), 1)
        self.assertEqual(clues[0]["name"], "血手印")

    def test_clue_same_name_updates_detail(self):
        mod.clue_add("甲", "血手印", detail="旧", cli_dir=self.dir)
        mod.clue_add("甲", "血手印", detail="新", cli_dir=self.dir)
        clues = mod.load_run("甲", self.dir)["clues"]
        self.assertEqual(len(clues), 1)
        self.assertEqual(clues[0]["detail"], "新")

    def test_clue_list(self):
        mod.clue_add("甲", "甲线索", cli_dir=self.dir)
        mod.clue_add("甲", "乙线索", cli_dir=self.dir)
        self.assertEqual([c["name"] for c in mod.clue_list("甲", self.dir)], ["甲线索", "乙线索"])


class TestEncounterDecisions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        mod.new_run("甲", "矿坑", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clear_dedup(self):
        mod.clear_encounter("甲", "哥布林哨兵", self.dir)
        mod.clear_encounter("甲", "哥布林哨兵", self.dir)
        self.assertEqual(mod.load_run("甲", self.dir)["cleared"], ["哥布林哨兵"])

    def test_decide_records(self):
        mod.decide("甲", "放过俘虏", self.dir)
        d = mod.load_run("甲", self.dir)["decisions"]
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["text"], "放过俘虏")

    def test_decide_has_time(self):
        mod.decide("甲", "直取首领", self.dir)
        self.assertIn("time", mod.load_run("甲", self.dir)["decisions"][0])


class TestStatusRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        mod.new_run("甲", "矿坑", cli_dir=self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status_data_shape(self):
        mod.set_scene("甲", "地精巢穴", cli_dir=self.dir)
        data = mod.status_data("甲", self.dir)
        self.assertEqual(data["current"], "地精巢穴")
        self.assertEqual(data["module"], "矿坑")
        self.assertIn("visited", data)

    def test_read_no_index_degrades(self):
        mods = pathlib.Path(self.tmp.name) / "mods"
        mods.mkdir()
        (mods / "凡戴尔的失落矿坑.pdf").write_bytes(b"%PDF-1.4")
        idx = pathlib.Path(self.tmp.name) / "empty_index"
        result = mod.read_scene("甲", "地精巢穴", cli_dir=self.dir,
                                index_dir=str(idx), modules_dir=str(mods))
        self.assertFalse(result["indexed"])
        self.assertTrue(any("凡戴尔" in p for p in result["module_pdfs"]))

    def test_read_with_index(self):
        idx = pathlib.Path(self.tmp.name) / "idx"
        mod.rules.save_index({"chunks": [
            {"source": "模组", "book": "矿坑", "page": 3, "text": "地精巢穴：两只地精守卫洞口"},
        ]}, str(idx))
        result = mod.read_scene("甲", "地精巢穴", cli_dir=self.dir, index_dir=str(idx))
        self.assertTrue(result["indexed"])
        self.assertTrue(result["hits"])


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.run_dir = os.path.join(self.root, "存档_Saves")
        self.script = str(ROOT / ".opencode" / "skill" / "module" / "scripts" / "module.py")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        env = dict(
            os.environ,
            DND_MODULE_DIR=self.run_dir,
            DND_RULE_INDEX=os.path.join(self.root, "no_such_index"),
        )
        return subprocess.run([sys.executable, self.script, *args], capture_output=True, text=True, encoding="utf-8", env=env)

    def test_full_flow_json(self):
        r = self._run("new", "甲", "--module", "矿坑")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._run("scene", "甲", "矿坑入口")
        self._run("clue", "甲", "add", "看到守卫")
        r = self._run("status", "甲", "--json")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["current"], "矿坑入口")

    def test_read_no_index_falls_back(self):
        self._run("new", "甲", "--module", "矿坑")
        r = self._run("read", "甲", "矿坑入口", "--json")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertFalse(data["indexed"])

    def test_unknown_run_exit2(self):
        r = self._run("status", "无此")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr)

    def test_utf8_pipe(self):
        self._run("new", "甲", "--module", "矿坑")
        r = self._run("status", "甲", "--json")
        json.loads(r.stdout)


class TestDocs(unittest.TestCase):
    def test_skill_md_lists_files(self):
        text = (ROOT / ".opencode" / "skill" / "module" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: module", text)
        self.assertIn("scripts/module.py", text)
        self.assertIn("模组", text)

    def test_schema_lists_fields(self):
        text = (ROOT / ".opencode" / "skill" / "module" / "reference" / "schema.md").read_text(encoding="utf-8")
        self.assertIn("schema_version", text)
        self.assertIn("visited", text)


class TestFinalReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.script = str(ROOT / ".opencode" / "skill" / "module" / "scripts" / "module.py")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_raw(self, name, obj):
        p = mod.run_path(name, self.dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def test_malformed_list_field_raises(self):
        data = mod.default_run("坏", "矿坑")
        data["visited"] = "oops"
        self._write_raw("坏", data)
        with self.assertRaises(mod.ModuleError):
            mod.load_run("坏", self.dir)

    def test_malformed_clue_item_raises(self):
        data = mod.default_run("坏", "矿坑")
        data["clues"] = [1, 2]
        self._write_raw("坏", data)
        with self.assertRaises(mod.ModuleError):
            mod.load_run("坏", self.dir)

    def test_colon_name_rejected(self):
        with self.assertRaises(mod.ModuleError):
            mod.run_path("z:evil", self.dir)

    def test_control_char_name_rejected(self):
        with self.assertRaises(mod.ModuleError):
            mod.run_path("a\x01b", self.dir)

    def test_list_skips_corrupt(self):
        mod.new_run("乙", "m", self.dir)
        p = mod.run_path("坏", self.dir)
        p.write_text("not json", encoding="utf-8")
        names = [r["name"] for r in mod.list_runs(self.dir)]
        self.assertIn("乙", names)
        self.assertNotIn("坏", names)

    def test_cli_damaged_archive_exit2(self):
        self._write_raw("坏", {"schema_version": 1, "name": "坏", "module": "m", "visited": "oops"})
        r = subprocess.run([sys.executable, self.script, "--run-dir", self.dir, "status", "坏"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_cli_traversal_name_exit2(self):
        r = subprocess.run([sys.executable, self.script, "--run-dir", self.dir, "new", "z:evil", "--module", "m"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)

    def test_cli_read_no_scene_exit2(self):
        mod.new_run("甲", "矿坑", self.dir)
        r = subprocess.run([sys.executable, self.script, "--run-dir", self.dir, "read", "甲"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
