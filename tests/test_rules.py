import sys, pathlib, tempfile, subprocess, unittest, json, os, shutil
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".opencode" / "skill" / "rules-reference" / "scripts"))
import rules


class TestStorage(unittest.TestCase):
    def test_source_dir_maps_fixed_folders(self):
        self.assertEqual(rules.source_dir("规则书").name, "规则书_Rulebooks")
        self.assertEqual(rules.source_dir("模组").name, "模组_Modules")
        self.assertEqual(rules.source_dir("世界观").name, "世界观_Worldbuilding")

    def test_source_dir_unknown_raises(self):
        with self.assertRaises(rules.RuleError):
            rules.source_dir("不存在")

    def test_resolve_index_dir_precedence(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(rules.resolve_index_dir(t), pathlib.Path(t))
        with mock.patch.dict(os.environ, {"DND_RULE_INDEX": "X:/idx"}):
            self.assertEqual(rules.resolve_index_dir(), pathlib.Path("X:/idx"))

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertIsNone(rules.load_index(t))

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            rules.save_index({"schema_version": 1, "chunks": []}, t)
            self.assertEqual(rules.load_index(t)["schema_version"], 1)


def _make_minimal_pdf(path, text):
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = ("BT /F1 24 Tf 72 700 Td (%s) Tj ET" % text).encode("ascii")
    objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n"); offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out); out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets: out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    path.write_bytes(bytes(out))


class TestExtract(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pdftotext"), "需要 pdftotext")
    def test_extract_pdf_via_pdftotext(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.pdf"; _make_minimal_pdf(p, "Hello Rules")
            pages = rules.extract_pdf(p)
            self.assertIn("Hello Rules", "".join(pages))

    def test_extract_txt_page_markers(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.txt"
            p.write_text("=== PAGE 1 ===\n甲\n=== PAGE 2 ===\n乙", encoding="utf-8")
            self.assertEqual(rules.extract_txt(p), ["甲", "乙"])

    def test_extract_file_dispatch(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.txt"; p.write_text("正文", encoding="utf-8")
            self.assertEqual(rules.extract_file(p), ["正文"])

    def test_list_books_missing_source_returns_empty(self):
        with mock.patch.object(rules, "source_dir", side_effect=rules.RuleError("x")):
            self.assertEqual(rules.list_books("规则书"), [])


class TestListBooksRecursive(unittest.TestCase):
    def test_recurses_into_subfolders_sorted_by_relative_path(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            (base / "sub").mkdir()
            (base / "top.txt").write_text("x", encoding="utf-8")
            (base / "sub" / "nested.pdf").write_bytes(b"%PDF")
            with mock.patch.object(rules, "source_dir", return_value=base):
                books = rules.list_books("模组")
            self.assertEqual([p.name for p in books], ["nested.pdf", "top.txt"])

    def test_skips_underscore_and_dot_prefixed_paths(self):
        with tempfile.TemporaryDirectory() as t:
            base = pathlib.Path(t)
            (base / "sub").mkdir()
            (base / "_extracted.txt").write_text("x", encoding="utf-8")
            (base / ".hidden.pdf").write_bytes(b"%PDF")
            (base / "sub" / "_part4.txt").write_text("x", encoding="utf-8")
            (base / "_draft").mkdir()
            (base / "_draft" / "x.pdf").write_bytes(b"%PDF")
            (base / "ok.txt").write_text("x", encoding="utf-8")
            with mock.patch.object(rules, "source_dir", return_value=base):
                books = rules.list_books("模组")
            self.assertEqual([p.name for p in books], ["ok.txt"])


class TestNormalizeCjkArtifacts(unittest.TestCase):
    def test_folds_kangxi_radical_plus_normal(self):
        self.assertEqual(rules.normalize_cjk_artifacts("巴森\u2F29小栈"), "巴森小栈")

    def test_folds_normal_plus_compat_ideograph(self):
        self.assertEqual(rules.normalize_cjk_artifacts("凡度林\uF9F4"), "凡度林")

    def test_folds_radical_normal_compat_triple(self):
        self.assertEqual(rules.normalize_cjk_artifacts("\u2F7C老\uF934"), "老")

    def test_repeated_pairs_keep_their_count(self):
        self.assertEqual(rules.normalize_cjk_artifacts("\u2F24\u5927\u2F24\u5927"), "大大")

    def test_leaves_plain_text_untouched(self):
        self.assertEqual(rules.normalize_cjk_artifacts("看看四周，大大方方。"), "看看四周，大大方方。")

    def test_maps_stray_artifact_chars_via_nfkc(self):
        self.assertEqual(rules.normalize_cjk_artifacts("\uF9E0"), "易")
        self.assertEqual(rules.normalize_cjk_artifacts("\u2F55"), "火")

    def test_folds_simplified_radicals_via_fallback(self):
        self.assertEqual(rules.normalize_cjk_artifacts("常\u2EC5见"), "常见")
        self.assertEqual(rules.normalize_cjk_artifacts("岩\u2EF0龙怪"), "岩龙怪")
        self.assertEqual(rules.normalize_cjk_artifacts("走\u2ED4，"), "走门，")
        self.assertEqual(rules.normalize_cjk_artifacts("\u2EAB标"), "目标")

    def test_extract_txt_normalizes_artifacts(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.txt"
            p.write_text("=== PAGE 1 ===\n巴森\u2F29小栈", encoding="utf-8")
            self.assertEqual(rules.extract_txt(p), ["巴森小栈"])

    @unittest.skipUnless(shutil.which("pdftotext"), "需要 pdftotext")
    def test_extract_pdf_normalizes_artifacts(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.pdf"
            _make_minimal_pdf(p, "Hello Rules")
            fake = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="巴森\u2F29小栈\f".encode("utf-8")
            )
            with mock.patch.object(rules.subprocess, "run", return_value=fake):
                self.assertEqual(rules.extract_pdf(p), ["巴森小栈"])


class TestChunk(unittest.TestCase):
    def test_splits_on_blank_lines_and_keeps_page(self):
        pages = ["第一段内容足够长。\n\n第二段内容也够长。", "第三页的段落内容。"]
        chunks = rules.chunk_pages("规则书", "书甲", pages)
        self.assertEqual([c["page"] for c in chunks], [1, 1, 2])
        self.assertEqual(chunks[0]["text"], "第一段内容足够长。")
        self.assertEqual(chunks[2]["book"], "书甲")

    def test_drops_short_and_toc_lines(self):
        pages = ["ok\n\n1\n\n............... 12\n\n这是足够长的正文段落。"]
        chunks = rules.chunk_pages("规则书", "书甲", pages)
        texts = [c["text"] for c in chunks]
        self.assertEqual(texts, ["这是足够长的正文段落。"])


class TestBuildIndex(unittest.TestCase):
    def test_build_index_structure(self):
        with mock.patch.object(rules, "list_books", return_value=[pathlib.Path("规则书_Rulebooks/书甲.pdf")]), \
             mock.patch.object(rules, "extract_file", return_value=["第一段正文内容。\n\n第二段正文内容。"]):
            idx = rules.build_index(["规则书"])
        self.assertEqual(idx["schema_version"], 1)
        self.assertEqual(idx["sources"], ["规则书"])
        self.assertEqual(idx["books"][0]["book"], "书甲")
        self.assertEqual(len(idx["chunks"]), 2)
        self.assertTrue(all(c["source"] == "规则书" for c in idx["chunks"]))

    def test_build_index_unknown_source_raises(self):
        with self.assertRaises(rules.RuleError):
            rules.build_index(["不存在"])

    def test_summarize_mentions_counts(self):
        idx = {"schema_version": 1, "sources": ["规则书"], "built_at": "t",
               "books": [{"source": "规则书", "book": "书甲", "file": "书甲.pdf", "pages": 1, "chunks": 2}],
               "chunks": [{"source": "规则书", "book": "书甲", "page": 1, "text": "x"}]}
        self.assertIn("书甲", rules.summarize_index(idx))

    def test_index_sources_empty_raises(self):
        with mock.patch.object(rules, "list_books", return_value=[]):
            with self.assertRaises(rules.RuleError):
                rules.index_sources(["规则书"])


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.idx = {"schema_version": 1, "books": [], "chunks": [
            {"source": "规则书", "book": "玩家手册", "page": 177, "text": "隐匿 隐匿 你躲藏起来"},
            {"source": "规则书", "book": "玩家手册", "page": 178, "text": "隐匿 一次"},
            {"source": "规则书", "book": "怪物图鉴", "page": 9, "text": "隐匿 隐匿 隐匿"},
        ]}

    def test_ranks_by_hit_count(self):
        hits = rules.search(self.idx, ["隐匿"], limit=5)
        self.assertEqual(hits[0]["book"], "怪物图鉴")
        self.assertEqual(hits[0]["score"], 3)

    def test_book_filter(self):
        hits = rules.search(self.idx, ["隐匿"], book="玩家手册")
        self.assertTrue(all(h["book"] == "玩家手册" for h in hits))

    def test_limit(self):
        self.assertEqual(len(rules.search(self.idx, ["隐匿"], limit=2)), 2)

    def test_no_hit_returns_empty(self):
        self.assertEqual(rules.search(self.idx, ["不存在的词"]), [])

    def test_normalize_splits_and_lowercases(self):
        self.assertEqual(rules.normalize_keywords(["Hide  Hide"]), ["hide", "hide"])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.hits = [{"source": "规则书", "book": "玩家手册", "page": 177, "score": 3,
                      "text": "隐匿：你尝试躲藏起来，直到被发现为止。"}]

    def test_render_text_has_book_page_and_query(self):
        out = rules.render_text("隐匿", self.hits)
        self.assertIn("玩家手册", out)
        self.assertIn("177", out)
        self.assertIn("隐匿", out)

    def test_render_text_no_hits(self):
        self.assertIn("未找到", rules.render_text("xyz", []))

    def test_snippet_is_a_window(self):
        long = "前" * 300 + "隐匿" + "后" * 300
        s = rules.snippet(long, ["隐匿"], width=50)
        self.assertIn("隐匿", s)
        self.assertLess(len(s), len(long))

    def test_render_json_shape(self):
        d = rules.render_json("隐匿", self.hits)
        self.assertEqual(d["query"], "隐匿")
        self.assertEqual(d["hits"][0]["page"], 177)
        self.assertIn("snippet", d["hits"][0])
        self.assertIn("text", d["hits"][0])


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, DND_RULE_INDEX=self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def _run(self, *args):
        return subprocess.run([sys.executable, str(ROOT / ".opencode" / "skill" / "rules-reference" / "scripts" / "rules.py"), *args],
                              capture_output=True, text=True, encoding="utf-8", env=self.env)

    def test_status_no_index(self):
        r = self._run("status", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(json.loads(r.stdout)["exists"])

    def test_query_without_index_exit2(self):
        r = self._run("query", "隐匿")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_invalid_source_exit2(self):
        r = self._run("index", "--source", "不存在")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_index_then_query_end_to_end(self):
        with mock.patch.object(rules, "list_books", return_value=[pathlib.Path("规则书_Rulebooks/书甲.txt")]), \
             mock.patch.object(rules, "extract_file", return_value=["隐匿：你尝试躲藏起来。"]):
            rules.save_index(rules.build_index(["规则书"]), self.tmp.name)
        r = self._run("query", "隐匿", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["hits"][0]["book"], "书甲")

    def test_utf8_pipe_not_garbled(self):
        with mock.patch.object(rules, "list_books", return_value=[pathlib.Path("规则书_Rulebooks/书甲.txt")]), \
             mock.patch.object(rules, "extract_file", return_value=["隐匿：你尝试躲藏起来。"]):
            rules.save_index(rules.build_index(["规则书"]), self.tmp.name)
        r = self._run("query", "隐匿")
        self.assertIn("书甲", r.stdout)


class TestDocs(unittest.TestCase):
    def test_skill_md_present(self):
        p = ROOT / ".opencode" / "skill" / "rules-reference" / "SKILL.md"
        text = p.read_text(encoding="utf-8")
        self.assertIn("name: rules-reference", text)
        self.assertIn("scripts/rules.py", text)
        self.assertIn("index", text)

    def test_schema_present(self):
        p = ROOT / ".opencode" / "skill" / "rules-reference" / "reference" / "schema.md"
        self.assertIn("schema_version", p.read_text(encoding="utf-8"))

    def test_gitignore_excludes_index(self):
        self.assertIn(".rule_index/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


class TestFinalReview(unittest.TestCase):
    def _txt(self, text):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.txt"
            p.write_text(text, encoding="utf-8")
            return rules.extract_txt(p)

    def test_txt_pages_do_not_shift_on_leading_content(self):
        pages = self._txt("封面\n=== PAGE 1 ===\n正文一。\n=== PAGE 2 ===\n正文二。")
        self.assertEqual(len(pages), 2)
        self.assertIn("封面", pages[0])
        self.assertIn("正文一", pages[0])
        self.assertIn("正文二", pages[1])

    def test_txt_pages_honor_marker_number_and_keep_gaps(self):
        pages = self._txt("=== PAGE 1 ===\n甲甲甲甲甲。\n=== PAGE 5 ===\n乙乙乙乙乙。")
        self.assertEqual(len(pages), 5)
        self.assertEqual(pages[4].strip(), "乙乙乙乙乙。")
        self.assertEqual(pages[1].strip(), "")

    def test_extract_pdf_error_is_wrapped(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "bad.pdf"
            p.write_bytes(b"%PDF-1.4 not really a pdf")
            with self.assertRaises(rules.RuleError):
                rules.extract_pdf(p)

    @unittest.skipUnless(shutil.which("pdftotext"), "需要 pdftotext")
    def test_extract_pdf_no_trailing_blank_page(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "a.pdf"; _make_minimal_pdf(p, "Hello Rules")
            self.assertEqual(len(rules.extract_pdf(p)), 1)

    def test_load_index_corrupt_non_utf8(self):
        with tempfile.TemporaryDirectory() as t:
            pathlib.Path(t, "index.json").write_bytes(b"\xff\xfe\x00bad")
            with self.assertRaises(rules.RuleError):
                rules.load_index(t)

    def test_load_index_non_dict(self):
        with tempfile.TemporaryDirectory() as t:
            pathlib.Path(t, "index.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(rules.RuleError):
                rules.load_index(t)

    def test_status_reports_built_at(self):
        with tempfile.TemporaryDirectory() as t:
            env = dict(os.environ, DND_RULE_INDEX=t)
            idx = {"schema_version": 1, "built_at": "2026-10-04T12:00:00",
                   "sources": ["规则书"], "books": [], "chunks": []}
            rules.save_index(idx, t)
            r = subprocess.run([sys.executable, str(ROOT / ".opencode" / "skill" / "rules-reference" / "scripts" / "rules.py"), "status", "--json"],
                               capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertEqual(r.returncode, 0)
            self.assertIn("built_at", json.loads(r.stdout))

    def test_available_books_aggregates_sources(self):
        def fake(source):
            return [pathlib.Path(f"{source}/书.txt")]
        with mock.patch.object(rules, "list_books", side_effect=fake):
            books = rules.available_books()
        self.assertEqual(len(books), len(rules.SOURCES))
        self.assertTrue(all("source" in b and "book" in b for b in books))

    def test_gitignore_excludes_content_folders(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for folder in ("规则书_Rulebooks/", "模组_Modules/", "世界观_Worldbuilding/"):
            self.assertIn(folder, text)


if __name__ == "__main__":
    unittest.main()
