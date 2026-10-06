import sys, pathlib, tempfile, subprocess, unittest, json, os
from unittest import mock
import contextlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "campaign" / "scripts"))
import campaign


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
    "schema_version": 1, "name": "", "player": "", "race": "人类",
    "classes": [{"name": "法师", "level": 1, "subclass": None}],
    "background": "", "alignment": "", "xp": 0,
    "abilities": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "save_profs": [], "skill_profs": [], "skill_expertise": [],
    "tool_profs": [], "weapon_profs": [],
    "ac": {"base": 10, "temp": 0},
    "hp": {"max": 10, "current": 10, "temp": 0},
    "hit_dice": {"die": "d6", "total": 1, "used": 0},
    "speed": 30, "initiative_bonus": None,
    "spellcasting": {"ability": "int", "slots": {}, "spells": [], "concentration": None},
    "attacks": [], "features": [], "languages": [],
    "personality": {"traits": [], "ideals": [], "bonds": [], "flaws": []},
    "inventory": [], "gold": 0, "conditions": [],
    "death_saves": {"successes": 0, "failures": 0}, "notes": "",
}


def write_card(dirpath, name, **over):
    sdir = pathlib.Path(dirpath) / "角色卡_CharacterSheets"
    sdir.mkdir(parents=True, exist_ok=True)
    card = json.loads(json.dumps(SHEET_BASE))
    card["name"] = name
    card.update(over)
    (sdir / f"{name}.json").write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return sdir


class TestStorage(unittest.TestCase):
    def test_resolve_campaign_dir_precedence(self):
        with tempfile.TemporaryDirectory() as t:
            with mock_env("DND_CAMPAIGN_DIR", t):
                self.assertEqual(campaign.resolve_campaign_dir(), pathlib.Path(t))
                self.assertEqual(campaign.resolve_campaign_dir("/x"), pathlib.Path("/x"))

    def test_campaign_path(self):
        self.assertEqual(campaign.campaign_path("甲", "/d").name, "甲.json")

    def test_load_missing_raises(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(campaign.CampaignError):
                campaign.load_campaign("无", t)

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            campaign.save_campaign("甲", {"name": "甲"}, t)
            self.assertEqual(campaign.load_campaign("甲", t)["name"], "甲")

    def test_load_corrupt_raises(self):
        with tempfile.TemporaryDirectory() as t:
            (pathlib.Path(t) / "甲.json").write_text("{", encoding="utf-8")
            with self.assertRaises(campaign.CampaignError):
                campaign.load_campaign("甲", t)


class TestNew(unittest.TestCase):
    def test_new_campaign_default_shape(self):
        with tempfile.TemporaryDirectory() as t:
            campaign.new_campaign("甲", t)
            d = campaign.load_campaign("甲", t)
            self.assertEqual(d["schema_version"], 1)
            self.assertEqual(d["novel"], False)
            self.assertEqual(d["log"], [])
            self.assertEqual(d["party"], [])
            self.assertIn("created_at", d)

    def test_new_duplicate_raises(self):
        with tempfile.TemporaryDirectory() as t:
            campaign.new_campaign("甲", t)
            with self.assertRaises(campaign.CampaignError):
                campaign.new_campaign("甲", t)

    def test_list_campaigns(self):
        with tempfile.TemporaryDirectory() as t:
            campaign.new_campaign("甲", t); campaign.new_campaign("乙", t)
            names = [c["name"] for c in campaign.list_campaigns(t)]
            self.assertEqual(names, ["乙", "甲"])  # 中文按 Unicode 码点排序：乙(U+4E59) < 甲(U+7532)

    def test_list_skips_corrupt(self):
        with tempfile.TemporaryDirectory() as t:
            campaign.new_campaign("甲", t)
            (pathlib.Path(t) / "坏.json").write_text("{", encoding="utf-8")
            self.assertEqual([c["name"] for c in campaign.list_campaigns(t)], ["甲"])


class TestLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        campaign.new_campaign("甲", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_log_seq_increments(self):
        campaign.add_log("甲", "开场", "队伍在酒馆集合", cli_dir=self.dir)
        campaign.add_log("甲", "遇袭", "巨鼠窜出", cli_dir=self.dir)
        d = campaign.load_campaign("甲", self.dir)
        self.assertEqual([e["seq"] for e in d["log"]], [1, 2])
        self.assertEqual(d["log"][1]["title"], "遇袭")

    def test_add_log_stores_details_and_tags(self):
        campaign.add_log("甲", "开场", "概要", details="长文……", tags=["酒馆"], cli_dir=self.dir)
        e = campaign.load_campaign("甲", self.dir)["log"][0]
        self.assertEqual(e["details"], "长文……")
        self.assertEqual(e["tags"], ["酒馆"])

    def test_set_time_updates(self):
        campaign.set_time("甲", "第 3 日 · 傍晚", cli_dir=self.dir)
        self.assertEqual(campaign.load_campaign("甲", self.dir)["in_game_time"], "第 3 日 · 傍晚")


class TestNpcQuest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        campaign.new_campaign("甲", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_npc_add_and_update(self):
        campaign.npc_add("甲", "铁匠老周", note="在铁砧镇", cli_dir=self.dir)
        campaign.npc_add("甲", "铁匠老周", note="已知晓矿坑秘密", cli_dir=self.dir)
        d = campaign.load_campaign("甲", self.dir)
        self.assertEqual(len(d["npcs"]), 1)
        self.assertEqual(d["npcs"][0]["note"], "已知晓矿坑秘密")

    def test_quest_add_and_complete(self):
        campaign.quest_add("甲", "找回货车", detail="矿坑入口", cli_dir=self.dir)
        campaign.quest_update("甲", "找回货车", status="已完成", cli_dir=self.dir)
        q = campaign.load_campaign("甲", self.dir)["quests"][0]
        self.assertEqual(q["status"], "已完成")
        self.assertEqual(q["detail"], "矿坑入口")

    def test_quest_update_unknown_raises(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.quest_update("甲", "无此任务", status="已完成", cli_dir=self.dir)


class TestParty(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.sheet_dir = write_card(self.dir, "因特·银")
        campaign.new_campaign("甲", self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_adds_member(self):
        campaign.link_sheet("甲", "因特·银", role="pc", cli_dir=self.dir, sheet_dir=self.sheet_dir)
        self.assertEqual(campaign.load_campaign("甲", self.dir)["party"][0]["sheet"], "因特·银")

    def test_link_missing_sheet_raises(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.link_sheet("甲", "无此人", cli_dir=self.dir, sheet_dir=self.sheet_dir)

    def test_unlink_removes(self):
        campaign.link_sheet("甲", "因特·银", cli_dir=self.dir, sheet_dir=self.sheet_dir)
        campaign.unlink_sheet("甲", "因特·银", cli_dir=self.dir)
        self.assertEqual(campaign.load_campaign("甲", self.dir)["party"], [])


class TestRecap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        campaign.new_campaign("甲", self.dir)
        campaign.set_time("甲", "第 3 日", cli_dir=self.dir)
        for i in range(1, 8):
            campaign.add_log("甲", f"事件{i}", f"概要{i}", cli_dir=self.dir)
        campaign.quest_add("甲", "光复银家", cli_dir=self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recap_last_n(self):
        d = campaign.recap_data("甲", last=3, cli_dir=self.dir)
        self.assertEqual(len(d["recent"]), 3)
        self.assertEqual(d["recent"][-1]["title"], "事件7")

    def test_recap_empty_log_ok(self):
        campaign.new_campaign("乙", self.dir)
        d = campaign.recap_data("乙", cli_dir=self.dir)
        self.assertEqual(d["recent"], [])
        self.assertIn("乙", campaign.render_recap(d))

    def test_recap_last_overflow_ok(self):
        d = campaign.recap_data("甲", last=999, cli_dir=self.dir)
        self.assertEqual(len(d["recent"]), 7)

    def test_status_includes_active_quest(self):
        s = campaign.status_data("甲", cli_dir=self.dir)
        self.assertEqual(s["quests"][0]["name"], "光复银家")


class TestRest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.sheet_dir = write_card(
            os.path.join(self.dir, "sheets"), "甲",
            hp={"max": 20, "current": 5, "temp": 3},
            hit_dice={"die": "d8", "total": 2, "used": 2},
            spellcasting={"ability": "int", "slots": {"1": {"max": 3, "used": 2}}, "spells": [], "concentration": None},
            death_saves={"successes": 1, "failures": 1},
        )
        campaign.new_campaign("甲", self.dir)
        campaign.link_sheet("甲", "甲", cli_dir=self.dir, sheet_dir=self.sheet_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def _card(self):
        with open(os.path.join(self.sheet_dir, "甲.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_long_rest_restores(self):
        campaign.rest("甲", "long", cli_dir=self.dir, sheet_dir=self.sheet_dir)
        card = self._card()
        self.assertEqual(card["hp"]["current"], 20)
        self.assertEqual(card["hp"]["temp"], 0)
        self.assertEqual(card["spellcasting"]["slots"]["1"]["used"], 0)
        self.assertEqual(card["death_saves"], {"successes": 0, "failures": 0})
        self.assertEqual(card["hit_dice"]["used"], 1)

    def test_short_rest_with_heal(self):
        campaign.rest("甲", "short", heal=6, spend=0, cli_dir=self.dir, sheet_dir=self.sheet_dir)
        card = self._card()
        self.assertEqual(card["hp"]["current"], 11)
        self.assertEqual(card["hit_dice"]["used"], 2)

    def test_bad_kind_raises(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.rest("甲", "nap", cli_dir=self.dir, sheet_dir=self.sheet_dir)


class TestLevel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.sheet_dir = write_card(self.dir, "甲",
            abilities={"str": 8, "dex": 10, "con": 13, "int": 16, "wis": 10, "cha": 16},
            classes=[{"name": "法师", "level": 2, "subclass": "塑能学派"}],
            hp={"max": 12, "current": 12, "temp": 0},
            hit_dice={"die": "d6", "total": 2, "used": 0})

    def tearDown(self):
        self.tmp.cleanup()

    def _card(self, name="甲"):
        return json.loads((pathlib.Path(self.sheet_dir) / f"{name}.json").read_text(encoding="utf-8"))

    def test_level_existing_class_avg(self):
        campaign.level_up("甲", "法师", avg=True, sheet_dir=self.sheet_dir)
        c = self._card()
        self.assertEqual(c["classes"][0]["level"], 3)
        # d6 平均 3+1 + con(+1) = 5
        self.assertEqual(c["hp"]["max"], 17)
        self.assertEqual(c["hp"]["current"], 17)
        self.assertEqual(c["hit_dice"]["total"], 3)

    def test_level_new_class_appends(self):
        campaign.level_up("甲", "战士", hp=7, sheet_dir=self.sheet_dir)
        self.assertEqual(self._card()["classes"][1]["name"], "战士")

    def test_level_requires_hp_or_avg(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.level_up("甲", "法师", sheet_dir=self.sheet_dir)

    def test_level_rejects_both_hp_and_avg(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.level_up("甲", "法师", hp=5, avg=True, sheet_dir=self.sheet_dir)

    def test_level_negative_con_min_gain(self):
        write_card(self.dir, "乙", abilities={"str": 10, "dex": 10, "con": 3, "int": 10, "wis": 10, "cha": 10},
                   classes=[{"name": "法师", "level": 1}], hp={"max": 6, "current": 6, "temp": 0},
                   hit_dice={"die": "d6", "total": 1, "used": 0})
        campaign.level_up("乙", "法师", avg=True, sheet_dir=self.sheet_dir)
        # con 3 → -4；d6 平均 4 + (-4) = 0 → 至少 +1
        self.assertGreaterEqual(self._card("乙")["hp"]["max"] - 6, 1)

    def test_level_missing_sheet_raises(self):
        with self.assertRaises(campaign.CampaignError):
            campaign.level_up("无", "法师", avg=True, sheet_dir=self.sheet_dir)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sheet_dir = write_card(self.tmp.name, "甲")
        self.env = dict(os.environ, DND_CAMPAIGN_DIR=self.tmp.name,
                        DND_SHEET_DIR=str(self.sheet_dir))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / ".opencode" / "skill" / "campaign" / "scripts" / "campaign.py"), *args],
            capture_output=True, text=True, encoding="utf-8", env=self.env)

    def test_new_log_recap_flow(self):
        self.assertEqual(self._run("new", "甲").returncode, 0)
        self.assertEqual(self._run("log", "甲", "开场", "集合").returncode, 0)
        r = self._run("recap", "甲", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["recent"][0]["title"], "开场")

    def test_unknown_campaign_exit2(self):
        r = self._run("recap", "无")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_level_requires_hp_exit2(self):
        r = self._run("level", "甲", "法师")
        self.assertEqual(r.returncode, 2)

    def test_utf8_pipe_not_garbled(self):
        self._run("new", "甲")
        self._run("log", "甲", "标题", "中文概要")
        r = self._run("recap", "甲")
        self.assertIn("标题", r.stdout)

    def test_rest_long_via_cli(self):
        self._run("new", "甲")
        self._run("link", "甲", "甲")
        self.assertEqual(self._run("rest", "甲", "long").returncode, 0)


class TestDocs(unittest.TestCase):
    def test_skill_md_present(self):
        text = (ROOT / ".opencode" / "skill" / "campaign" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: campaign", text)
        self.assertIn("scripts/campaign.py", text)
        self.assertIn("小说", text)

    def test_schema_present(self):
        text = (ROOT / ".opencode" / "skill" / "campaign" / "reference" / "schema.md").read_text(encoding="utf-8")
        self.assertIn("schema_version", text)
        self.assertIn("novel", text)


class TestFinalReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_name_rejects_path_separators(self):
        for bad in ("../evil", "a/b", "a\\b"):
            with self.assertRaises(campaign.CampaignError):
                campaign.new_campaign(bad, self.dir)

    def test_list_skips_malformed_shape(self):
        campaign.new_campaign("甲", self.dir)
        (pathlib.Path(self.dir) / "坏.json").write_text(
            json.dumps({"name": "坏", "log": 5}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual([c["name"] for c in campaign.list_campaigns(self.dir)], ["甲"])

    def test_load_rejects_malformed_shape(self):
        (pathlib.Path(self.dir) / "坏.json").write_text(
            json.dumps({"name": "坏", "log": 5}, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(campaign.CampaignError):
            campaign.load_campaign("坏", self.dir)

    def test_link_rejects_non_dict_card(self):
        campaign.new_campaign("甲", self.dir)
        sdir = pathlib.Path(self.dir) / "角色卡_CharacterSheets"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "坏.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(campaign.CampaignError):
            campaign.link_sheet("甲", "坏", cli_dir=self.dir, sheet_dir=sdir)

    def test_quest_status_validated(self):
        campaign.new_campaign("甲", self.dir)
        campaign.quest_add("甲", "事", cli_dir=self.dir)
        with self.assertRaises(campaign.CampaignError):
            campaign.quest_update("甲", "事", status="乱写", cli_dir=self.dir)

    def test_completed_quest_not_active(self):
        campaign.new_campaign("甲", self.dir)
        campaign.quest_add("甲", "事", cli_dir=self.dir)
        campaign.quest_update("甲", "事", status="已完成", cli_dir=self.dir)
        self.assertEqual(campaign.status_data("甲", cli_dir=self.dir)["quests"], [])

    def test_novel_toggle(self):
        campaign.new_campaign("甲", self.dir)
        campaign.novel_set("甲", True, cli_dir=self.dir)
        self.assertTrue(campaign.load_campaign("甲", self.dir)["novel"])

    def test_short_rest_over_spend_raises(self):
        sheet_dir = write_card(os.path.join(self.dir, "s"), "甲",
            hit_dice={"die": "d8", "total": 2, "used": 2})
        campaign.new_campaign("甲", self.dir)
        campaign.link_sheet("甲", "甲", cli_dir=self.dir, sheet_dir=sheet_dir)
        with self.assertRaises(campaign.CampaignError):
            campaign.rest("甲", "short", spend=5, cli_dir=self.dir, sheet_dir=sheet_dir)

    def test_rest_negative_spend_raises(self):
        sheet_dir = write_card(os.path.join(self.dir, "s"), "甲",
            hit_dice={"die": "d8", "total": 2, "used": 0})
        campaign.new_campaign("甲", self.dir)
        campaign.link_sheet("甲", "甲", cli_dir=self.dir, sheet_dir=sheet_dir)
        with self.assertRaises(campaign.CampaignError):
            campaign.rest("甲", "short", spend=-1, cli_dir=self.dir, sheet_dir=sheet_dir)

    def _run(self, *args, **env):
        full = dict(os.environ, DND_CAMPAIGN_DIR=self.dir, **env)
        return subprocess.run(
            [sys.executable, str(ROOT / ".opencode" / "skill" / "campaign" / "scripts" / "campaign.py"), *args],
            capture_output=True, text=True, encoding="utf-8", env=full)

    def test_docs_commands_executable(self):
        self.assertEqual(self._run("new", "甲").returncode, 0)
        self.assertEqual(self._run("log", "甲", "标题", "摘要").returncode, 0)
        self.assertEqual(self._run("npc", "甲", "add", "老周").returncode, 0)

    def test_rest_short_default_spend_one(self):
        sheet_dir = write_card(os.path.join(self.dir, "s"), "甲",
            hit_dice={"die": "d8", "total": 3, "used": 0})
        self._run("new", "甲", DND_SHEET_DIR=str(sheet_dir))
        self._run("link", "甲", "甲", DND_SHEET_DIR=str(sheet_dir))
        r = self._run("rest", "甲", "short", DND_SHEET_DIR=str(sheet_dir))
        self.assertEqual(r.returncode, 0)
        card = json.loads((pathlib.Path(sheet_dir) / "甲.json").read_text(encoding="utf-8"))
        self.assertEqual(card["hit_dice"]["used"], 1)


if __name__ == "__main__":
    unittest.main()
