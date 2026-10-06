import sys, pathlib, subprocess, unittest, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "dice-roll" / "scripts"))
import roll


class TestParse(unittest.TestCase):
    def test_basic_dice(self):
        self.assertEqual(roll.parse_expression("1d20"), [roll.DiceTerm(1, 20)])

    def test_bare_d_means_one(self):
        self.assertEqual(roll.parse_expression("d20"), [roll.DiceTerm(1, 20)])

    def test_modifier(self):
        self.assertEqual(roll.parse_expression("2d6+3"),
                         [roll.DiceTerm(2, 6), roll.ConstTerm(3)])

    def test_negative_modifier(self):
        self.assertEqual(roll.parse_expression("1d20-1"),
                         [roll.DiceTerm(1, 20), roll.ConstTerm(1, -1)])

    def test_keep_drop(self):
        self.assertEqual(roll.parse_expression("4d6dl1"), [roll.DiceTerm(4, 6, drop_low=1)])
        self.assertEqual(roll.parse_expression("2d20kh1"), [roll.DiceTerm(2, 20, keep_high=1)])

    def test_multi_terms(self):
        self.assertEqual(len(roll.parse_expression("1d8+1d6-1")), 3)

    def test_invalid_raises(self):
        for bad in ["", "d", "1d", "1d20+", "abc", "2x6", "0d6"]:
            with self.assertRaises(ValueError):
                roll.parse_expression(bad)

    def test_oversize_raises(self):
        with self.assertRaises(ValueError):
            roll.parse_expression("100000d6")


class FakeRandom:
    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        return self.seq.pop(0)


class TestRollTerms(unittest.TestCase):
    def test_2d6_sums(self):
        r = roll.roll_terms(roll.parse_expression("2d6"), FakeRandom([3, 5]))
        self.assertEqual(r.total, 8)

    def test_modifier(self):
        r = roll.roll_terms(roll.parse_expression("2d6+3"), FakeRandom([3, 5]))
        self.assertEqual(r.total, 11)

    def test_drop_lowest(self):
        r = roll.roll_terms(roll.parse_expression("4d6dl1"), FakeRandom([6, 2, 5, 3]))
        self.assertEqual(r.total, 14)

    def test_keep_highest(self):
        r = roll.roll_terms(roll.parse_expression("2d20kh1"), FakeRandom([7, 15]))
        self.assertEqual(r.total, 15)

    def test_negative_modifier(self):
        r = roll.roll_terms(roll.parse_expression("1d20-1"), FakeRandom([10]))
        self.assertEqual(r.total, 9)


class TestAdvantage(unittest.TestCase):
    def test_advantage_takes_higher(self):
        r = roll.roll_terms(roll.parse_expression("1d20+5"),
                            FakeRandom([7, 15]), advantage="advantage")
        self.assertEqual(r.total, 20)

    def test_disadvantage_takes_lower(self):
        r = roll.roll_terms(roll.parse_expression("1d20+5"),
                            FakeRandom([7, 15]), advantage="disadvantage")
        self.assertEqual(r.total, 12)

    def test_advantage_consumes_two_dice(self):
        fr = FakeRandom([7, 15])
        roll.roll_terms(roll.parse_expression("1d20"), fr, advantage="advantage")
        self.assertEqual(fr.seq, [])

    def test_advantage_on_non_d20_raises(self):
        with self.assertRaises(ValueError):
            roll.roll_terms(roll.parse_expression("2d6"), FakeRandom([1, 2]),
                            advantage="advantage")


class TestCoC(unittest.TestCase):
    def test_bonus_takes_lower(self):
        # units=4, tens=[2,4]->[20,40]; 候选 24/44 -> 取 24
        r = roll.roll_d100_coc(FakeRandom([4, 2, 4]), bonus=1, penalty=0)
        self.assertEqual(r["value"], 24)
        self.assertEqual(sorted(r["tens"]), [20, 40])

    def test_penalty_takes_higher(self):
        r = roll.roll_d100_coc(FakeRandom([1, 2, 4]), bonus=0, penalty=1)
        self.assertEqual(r["value"], 41)

    def test_bonus_penalty_cancel(self):
        r = roll.roll_d100_coc(FakeRandom([5, 3]), bonus=1, penalty=1)
        self.assertEqual(r["net"], 0)
        self.assertEqual(r["value"], 35)

    def test_00_plus_0_is_100(self):
        r = roll.roll_d100_coc(FakeRandom([0, 0]), bonus=0, penalty=0)
        self.assertEqual(r["value"], 100)

    def test_00_plus_nonzero_is_units(self):
        r = roll.roll_d100_coc(FakeRandom([3, 0]), bonus=0, penalty=0)
        self.assertEqual(r["value"], 3)

    def test_bonus_avoids_100(self):
        # units=0, tens=[0,4]->[0,40]; 候选 100/40 -> 奖励取 40
        r = roll.roll_d100_coc(FakeRandom([0, 0, 4]), bonus=1, penalty=0)
        self.assertEqual(r["value"], 40)


class TestChecks(unittest.TestCase):
    def test_dnd5e(self):
        self.assertTrue(roll.dnd5e_success(15, 15))
        self.assertFalse(roll.dnd5e_success(14, 15))

    def test_coc_levels(self):
        self.assertEqual(roll.coc_success_level(1, 55), "critical")
        self.assertEqual(roll.coc_success_level(11, 55), "extreme")
        self.assertEqual(roll.coc_success_level(12, 55), "hard")
        self.assertEqual(roll.coc_success_level(27, 55), "hard")
        self.assertEqual(roll.coc_success_level(28, 55), "regular")
        self.assertEqual(roll.coc_success_level(55, 55), "regular")
        self.assertEqual(roll.coc_success_level(56, 55), "fail")
        self.assertEqual(roll.coc_success_level(100, 55), "fumble")
        self.assertEqual(roll.coc_success_level(96, 40), "fumble")
        self.assertEqual(roll.coc_success_level(95, 40), "fail")
        self.assertEqual(roll.coc_success_level(96, 55), "fail")


class TestRender(unittest.TestCase):
    def _res(self, **kw):
        base = roll.roll_terms(roll.parse_expression("1d20+5"), FakeRandom([15]))
        for k, v in kw.items():
            setattr(base, k, v)
        return base

    def test_text_has_total(self):
        s = roll.render_text(self._res(label="力量豁免"))
        self.assertIn("力量豁免", s)
        self.assertIn("20", s)

    def test_json_parsable(self):
        j = roll.render_json(self._res())
        json.dumps(j)
        self.assertEqual(j["total"], 20)

    def test_secret_player_view_hides_numbers(self):
        j = roll.render_json(self._res(secret=True))
        pv = j["player_view"]
        self.assertEqual(set(pv.keys()), {"label", "message"})
        self.assertNotIn("20", str(pv))


class TestCLI(unittest.TestCase):
    def _run(self, *args):
        import subprocess
        script = str(ROOT / ".opencode" / "skill" / "dice-roll" / "scripts" / "roll.py")
        return subprocess.run([sys.executable, script, *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_basic_runs(self):
        p = self._run("1d20", "--seed", "1")
        self.assertEqual(p.returncode, 0)

    def test_invalid_exit_2(self):
        p = self._run("1d20+")
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.stderr.strip())

    def test_adv_dis_cancel_single_roll(self):
        p = self._run("1d20", "--adv", "--dis", "--json", "--seed", "1")
        self.assertEqual(p.returncode, 0)
        self.assertIsNone(json.loads(p.stdout)["advantage"])

    def test_json_only(self):
        p = self._run("2d6", "--json", "--seed", "1")
        self.assertEqual(json.loads(p.stdout)["expression"], "2d6")

    def test_secret_flag(self):
        p = self._run("1d20", "--secret", "--json", "--seed", "1")
        self.assertTrue(json.loads(p.stdout)["secret"])


class TestDocs(unittest.TestCase):
    def test_skill_md_frontmatter_and_paths(self):
        p = ROOT / ".opencode" / "skill" / "dice-roll" / "SKILL.md"
        text = p.read_text(encoding="utf-8")
        self.assertIn("name: dice-roll", text)
        self.assertIn("scripts/roll.py", text)
        self.assertIn("reference/rules.md", text)

    def test_rules_md_has_tables(self):
        p = ROOT / ".opencode" / "skill" / "dice-roll" / "reference" / "rules.md"
        text = p.read_text(encoding="utf-8")
        self.assertIn("DC", text)
        self.assertIn("极难", text)
        self.assertIn("大失败", text)


class TestFinalReview(unittest.TestCase):
    def _run(self, *args):
        script = str(ROOT / ".opencode" / "skill" / "dice-roll" / "scripts" / "roll.py")
        return subprocess.run([sys.executable, script, *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_output_is_utf8_under_pipe(self):
        script = str(ROOT / ".opencode" / "skill" / "dice-roll" / "scripts" / "roll.py")
        p = subprocess.run([sys.executable, script, "1d20", "--label", "力量",
                            "--json", "--seed", "1"], capture_output=True)
        text = p.stdout.decode("utf-8")
        self.assertIn("力量", text)

    def test_bonus_alone_infers_coc(self):
        p = self._run("1d100", "--bonus", "1", "--json", "--seed", "1")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["bonus_penalty"]["net"], 1)

    def test_coc_non_d100_warns(self):
        p = self._run("1d20", "--system", "coc7e", "--skill", "55", "--json", "--seed", "1")
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stderr.strip())
        self.assertEqual(json.loads(p.stdout)["check"]["system"], "coc7e")

    def test_json_dice_contract(self):
        p = self._run("1d20+5", "--adv", "--dc", "15", "--json", "--seed", "1")
        d = json.loads(p.stdout)
        die = d["dice"][0]
        for key in ("type", "count", "results", "kept", "mode"):
            self.assertIn(key, die)
        self.assertEqual(die["type"], "d20")
        self.assertEqual(die["count"], 2)
        self.assertEqual(len(die["results"]), 2)
        self.assertEqual(len(die["kept"]), 1)
        self.assertEqual(die["mode"], "advantage")
        self.assertEqual(d["check"]["system"], "dnd5e")

    def test_json_coc_check_contract(self):
        p = self._run("1d100", "--skill", "55", "--system", "coc7e", "--bonus", "1",
                      "--json", "--seed", "1")
        c = json.loads(p.stdout)["check"]
        for key in ("system", "skill", "roll", "level", "success", "bonus_penalty"):
            self.assertIn(key, c)
        self.assertEqual(c["system"], "coc7e")
        self.assertEqual(c["success"], c["level"] in ("critical", "extreme", "hard", "regular"))

    def test_argparse_error_chinese(self):
        p = self._run("1d20", "--system", "foo")
        self.assertEqual(p.returncode, 2)
        self.assertIn("错误", p.stderr)
        self.assertNotIn("invalid choice", p.stderr)

    def test_coc_fumble_at_100_high_skill(self):
        self.assertEqual(roll.coc_success_level(100, 100), "fumble")

    def test_2d100_not_hijacked_by_coc(self):
        p = self._run("2d100", "--system", "coc7e", "--skill", "55", "--json", "--seed", "1")
        d = json.loads(p.stdout)
        self.assertEqual(len(d["dice"][0]["results"]), 2)
        self.assertEqual(d["total"], sum(d["dice"][0]["results"]))

    def test_count_upper_bound(self):
        p = self._run("1d20", "--count", "1000000")
        self.assertEqual(p.returncode, 2)
        self.assertIn("错误", p.stderr)

    def test_bonus_upper_bound(self):
        p = self._run("1d100", "--bonus", "1000000", "--system", "coc7e")
        self.assertEqual(p.returncode, 2)
        self.assertIn("错误", p.stderr)

    def test_dc_and_skill_conflict(self):
        p = self._run("1d20", "--dc", "10", "--skill", "50")
        self.assertEqual(p.returncode, 2)
        self.assertIn("错误", p.stderr)

    def test_coc_text_chinese_level(self):
        p = self._run("1d100", "--skill", "55", "--system", "coc7e", "--seed", "1")
        self.assertEqual(p.returncode, 0)
        self.assertTrue(any(name in p.stdout for name in
                            ("大成功", "极难", "困难", "常规", "失败", "大失败")))
        self.assertNotIn("regular", p.stdout)


if __name__ == "__main__":
    unittest.main()
