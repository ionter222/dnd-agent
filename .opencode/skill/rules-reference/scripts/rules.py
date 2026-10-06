"""规则查阅 skill：把用户自备的规则书/模组/世界观抽成本地全文索引并查询。

纯 stdlib；仅在建立索引时调用外部 `pdftotext`（缺失则回落 `pypdf`）。
索引完全本地、绝不进 git。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
INDEX_DIRNAME = ".rule_index"
SOURCES = {
    "规则书": "规则书_Rulebooks",
    "模组": "模组_Modules",
    "世界观": "世界观_Worldbuilding",
}


class RuleError(ValueError):
    """规则查阅 skill 的业务错误（消息为中文）。"""


def source_dir(source):
    """把来源简称映射到固定文件夹（仓库根下）。未知来源 → RuleError。"""
    folder = SOURCES.get(source)
    if folder is None:
        raise RuleError(f"未知来源：{source}（可选：{'、'.join(SOURCES)}）")
    return REPO_ROOT / folder


def resolve_index_dir(cli_dir=None):
    """索引目录：显式 cli_dir > 环境变量 DND_RULE_INDEX > 仓库根/.rule_index。"""
    if cli_dir:
        return pathlib.Path(cli_dir)
    env = os.environ.get("DND_RULE_INDEX")
    if env:
        return pathlib.Path(env)
    return REPO_ROOT / INDEX_DIRNAME


def _index_file(cli_dir=None):
    return resolve_index_dir(cli_dir) / "index.json"


def load_index(cli_dir=None):
    """读取索引；不存在 → None；损坏（JSON/编码/结构不符）→ RuleError。"""
    path = _index_file(cli_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise RuleError(f"索引文件损坏：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise RuleError(f"索引文件损坏：{path}（结构不符）")
    return data


def save_index(index, cli_dir=None):
    """写索引（UTF-8、ensure_ascii=False、indent=2），自动建目录。"""
    path = _index_file(cli_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


_ARTIFACT_RANGES = ((0x2E80, 0x2FDF), (0xF900, 0xFAFF))


def _is_artifact_char(ch):
    """是否属于 PDF 字体映射伪影常见区段（康熙部首、CJK 兼容表意字）。"""
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _ARTIFACT_RANGES)


# 无 NFKC 映射的变体部首 → 正体（仅收录实际书里出现过的）
_IDENTITY_RADICAL_FALLBACK = {
    "\u2EA0": "民",  # ⺠
    "\u2EA9": "王",  # ⺩
    "\u2EAB": "目",  # ⺫
    "\u2EB4": "罒",  # ⺴
    "\u2EC4": "西",  # ⻄
    "\u2EC5": "见",  # ⻅
    "\u2EC6": "角",  # ⻆
    "\u2EC9": "贝",  # ⻉
    "\u2ECB": "车",  # ⻋
    "\u2ED3": "长",  # ⻓
    "\u2ED4": "门",  # ⻔
    "\u2ED8": "青",  # ⻘
    "\u2EDA": "页",  # ⻚
    "\u2EDB": "风",  # ⻛
    "\u2EDC": "飞",  # ⻜
    "\u2EDD": "食",  # ⻝
    "\u2EE2": "马",  # ⻢
    "\u2EE3": "骨",  # ⻣
    "\u2EE4": "鬼",  # ⻤
    "\u2EE5": "鱼",  # ⻥
    "\u2EE6": "鸟",  # ⻦
    "\u2EE8": "麦",  # ⻨
    "\u2EE9": "黄",  # ⻩
    "\u2EEC": "齐",  # ⻬
    "\u2EEE": "齿",  # ⻮
    "\u2EF0": "龙",  # ⻰
}


def _fold_char(ch):
    """把单个伪影字符折成其正体；非伪影字符原样返回。"""
    if not _is_artifact_char(ch):
        return ch
    folded = unicodedata.normalize("NFKC", ch)
    if folded != ch:
        return folded
    return _IDENTITY_RADICAL_FALLBACK.get(ch, ch)


def normalize_cjk_artifacts(text):
    """折叠 PDF 字体伪影：变体与其正体成对出现（如「⼩小」→「小」、「林林」→「林」），
    或只吐出孤立变体码点（如「易」→「易」、「⻅」→「见」）。仅触及伪影区段字符，正常重复字（如「大大」）不受影响。"""
    chars = list(text)
    # ① 变体在前（部首/兼容字+正体）：与后一字符同形则删
    step1 = []
    for i, ch in enumerate(chars):
        if (
            _is_artifact_char(ch)
            and i + 1 < len(chars)
            and chars[i + 1] != ch
            and _fold_char(ch) == _fold_char(chars[i + 1])
        ):
            continue
        step1.append(ch)
    # ② 变体在后（正体+兼容字）：与前一字同形则删
    step2 = []
    for ch in step1:
        if (
            _is_artifact_char(ch)
            and step2
            and step2[-1] != ch
            and _fold_char(ch) == _fold_char(step2[-1])
        ):
            continue
        step2.append(ch)
    # ③ 剩余孤立变体 → 正体
    return "".join(_fold_char(ch) if _is_artifact_char(ch) else ch for ch in step2)


def extract_pdf(path):
    """抽取 PDF 每页文本。优先 pdftotext -enc UTF-8，失败回落 pypdf。会折叠字体伪影。"""
    path = pathlib.Path(path)
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(
                ["pdftotext", "-enc", "UTF-8", str(path), "-"],
                capture_output=True,
                check=True,
            )
            pages = out.stdout.decode("utf-8", errors="replace").split("\f")
            while pages and not pages[-1].strip():
                pages.pop()
            return [normalize_cjk_artifacts(p) for p in pages]
        except (subprocess.CalledProcessError, OSError):
            pass
    try:
        import pypdf
    except ImportError as exc:
        raise RuleError("无法抽取 PDF：需要 pdftotext 或 pypdf") from exc
    try:
        reader = pypdf.PdfReader(str(path))
        return [normalize_cjk_artifacts(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # 损坏/加密 PDF：归一为中文 RuleError
        raise RuleError(f"无法抽取 PDF：{path.name}（{exc}）") from exc


_PAGE_RE = re.compile(r"(?m)^\s*===\s*PAGE\s+(\d+)\s*===\s*$")


def extract_txt(path):
    """抽取 txt：按 '=== PAGE n ===' 或换页符 \\f 分页；否则整篇作一页。页码按标记保留。"""
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    if _PAGE_RE.search(text):
        parts = _PAGE_RE.split(text)
        pages_map = {}
        pre = parts[0]
        for j in range(1, len(parts), 2):
            num = int(parts[j])
            pages_map.setdefault(num, []).append(parts[j + 1])
        if pre.strip():
            pages_map.setdefault(1, [])
            pages_map[1].insert(0, pre)
        if not pages_map:
            return []
        maxn = max(pages_map)
        pages = ["\n".join(pages_map.get(k, [])).strip() for k in range(1, maxn + 1)]
        return [normalize_cjk_artifacts(p) for p in pages]
    if "\f" in text:
        pages = [p.strip() for p in text.split("\f")]
        while pages and not pages[-1]:
            pages.pop()
        return [normalize_cjk_artifacts(p) for p in pages]
    return [normalize_cjk_artifacts(text.strip())]


def extract_file(path):
    """按扩展名分派；其它扩展名 → RuleError。"""
    path = pathlib.Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".txt":
        return extract_txt(path)
    raise RuleError(f"无法抽取的文件类型：{path.name}（仅支持 .pdf/.txt）")


def list_books(source):
    """递归扫描来源目录下的 *.pdf/*.txt（含子文件夹），跳过路径中以 `_` 或 `.` 开头的
    文件/目录，按相对路径排序；目录不存在或来源未知 → []。"""
    try:
        directory = source_dir(source)
    except RuleError:
        return []
    if not directory.is_dir():
        return []
    files = []
    for p in directory.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (".pdf", ".txt"):
            continue
        rel = p.relative_to(directory)
        if any(part.startswith(("_", ".")) for part in rel.parts):
            continue
        files.append(p)
    return sorted(files, key=lambda p: p.relative_to(directory).as_posix())


def available_books():
    """扫描三个固定文件夹，列出可索引的 PDF/txt（未建索引也能用）。"""
    result = []
    for source in SOURCES:
        for path in list_books(source):
            result.append({"source": source, "book": path.stem, "file": str(path)})
    return result


_TOC_RE = re.compile(r"^[\d\s.·\-–—]+$")


def chunk_pages(source, book, pages):
    """把每页文本切成段落级块：按空行分段、去首尾空白；
    丢弃 len<8 的块与纯目录行。返回 [{source,book,page,text}]。"""
    chunks = []
    for page_no, page in enumerate(pages, 1):
        for para in re.split(r"\n\s*\n", page):
            text = para.strip()
            if len(text) < 8:
                continue
            if _TOC_RE.match(text):
                continue
            chunks.append(
                {"source": source, "book": book, "page": page_no, "text": text}
            )
    return chunks


def build_index(sources, book_filter=None):
    """对每个来源抽书、切块，汇总成索引 dict。未知来源 → RuleError。"""
    books = []
    all_chunks = []
    for source in sources:
        source_dir(source)
        for path in list_books(source):
            book = path.stem
            if book_filter and book_filter not in book:
                continue
            pages = extract_file(path)
            chunks = chunk_pages(source, book, pages)
            books.append(
                {
                    "source": source,
                    "book": book,
                    "file": path.name,
                    "pages": len(pages),
                    "chunks": len(chunks),
                }
            )
            all_chunks.extend(chunks)
    return {
        "schema_version": 1,
        "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sources": list(sources),
        "books": books,
        "chunks": all_chunks,
    }


def summarize_index(index):
    """多行中文摘要：来源、书数/块数、每本书的块数与页数。"""
    books = index.get("books", [])
    lines = [
        f"索引建立于：{index.get('built_at', '（未知）')}",
        f"索引来源：{'、'.join(index.get('sources', []))}",
        f"书数：{len(books)}，块数：{len(index.get('chunks', []))}",
    ]
    for b in books:
        lines.append(f"  - {b['book']}（{b['source']}）：{b['chunks']} 块 / {b['pages']} 页")
    return "\n".join(lines)


def index_sources(sources, book_filter=None, cli_dir=None):
    """建索引并落盘；无任何块 → RuleError。返回摘要。"""
    index = build_index(sources, book_filter=book_filter)
    if not index["chunks"]:
        raise RuleError("没有可索引的文件（检查规则书_Rulebooks/ 等固定文件夹）")
    save_index(index, cli_dir=cli_dir)
    return summarize_index(index)


def _to_halfwidth(text):
    """全角数字/字母/空格 → 半角。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def normalize_keywords(raw):
    """把关键词列表合并、切分为词、英文小写、全角转半角。"""
    joined = _to_halfwidth(" ".join(raw))
    return [word.lower() for word in joined.split()]


def search(index, keywords, book=None, limit=5):
    """按关键词子串出现次数打分；score>0 命中；按 score 降序、page 升序取前 limit。"""
    kws = normalize_keywords(keywords)
    hits = []
    for chunk in index.get("chunks", []):
        if book and book not in chunk.get("book", ""):
            continue
        text_norm = _to_halfwidth(chunk.get("text", "")).lower()
        score = sum(text_norm.count(kw) for kw in kws)
        if score > 0:
            hits.append(
                {
                    "source": chunk.get("source"),
                    "book": chunk.get("book"),
                    "page": chunk.get("page"),
                    "score": score,
                    "text": chunk.get("text"),
                }
            )
    hits.sort(key=lambda h: (-h["score"], h["page"]))
    return hits[:limit]


def snippet(text, keywords, width=100):
    """以首个命中词为中心取左右各 width 字符；无命中则取开头。"""
    kws = normalize_keywords(keywords)
    norm = _to_halfwidth(text).lower()
    pos = -1
    hit_len = 0
    for kw in kws:
        i = norm.find(kw)
        if i != -1:
            pos, hit_len = i, len(kw)
            break
    if pos == -1:
        return text[: width * 2]
    start = max(0, pos - width)
    end = min(len(text), pos + hit_len + width)
    return text[start:end]


def render_text(query, hits):
    """人类可读文本：标题 + 每段一行元信息 + 缩进片段，段间以 '---' 分隔。"""
    if not hits:
        return f"未找到与 {query} 相关的片段"
    blocks = []
    for h in hits:
        body = snippet(h["text"], [query])
        blocks.append(f"《{h['book']}》第 {h['page']} 页 · 命中 {h['score']}\n  {body}")
    return f"命中 {len(hits)} 段（查询：{query}）\n\n" + "\n---\n".join(blocks)


def render_json(query, hits):
    """机器可读结构：query/count/hits（含 snippet 与原文 text）。"""
    return {
        "query": query,
        "count": len(hits),
        "hits": [
            {
                "source": h["source"],
                "book": h["book"],
                "page": h["page"],
                "score": h["score"],
                "snippet": snippet(h["text"], [query]),
                "text": h["text"],
            }
            for h in hits
        ],
    }


def _force_utf8():
    """把 stdout/stderr 强制为 UTF-8，避免管道下中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


class _ZhArgumentParser(argparse.ArgumentParser):
    """参数解析错误时输出中文并退出码 2。"""

    def error(self, message):
        print("错误：参数无效，请检查输入（可用 -h 查看帮助）", file=sys.stderr)
        raise SystemExit(2)


def build_parser():
    """构建命令行解析器：status / index / query / books，均支持 --json。"""
    parser = _ZhArgumentParser(
        prog="rules",
        description="规则查阅：把规则书/模组/世界观抽成本地索引并查询。",
    )
    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="查看索引状态")
    p_status.add_argument("--json", action="store_true")

    p_index = sub.add_parser("index", help="建立索引")
    p_index.add_argument("--source", action="append", choices=list(SOURCES))
    p_index.add_argument("--all", action="store_true", dest="all_sources")
    p_index.add_argument("--book")
    p_index.add_argument("--json", action="store_true")

    p_query = sub.add_parser("query", help="按关键词查询索引")
    p_query.add_argument("keywords", nargs="*")
    p_query.add_argument("--book")
    p_query.add_argument("--limit", type=int, default=5)
    p_query.add_argument("--json", action="store_true")

    p_books = sub.add_parser("books", help="列出已索引的书")
    p_books.add_argument("--json", action="store_true")

    return parser


def main(argv=None):
    """命令行入口：返回退出码（0 成功，2 业务/参数错误）。"""
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        if args.command == "status":
            index = load_index()
            if index is None:
                if args.json:
                    print(json.dumps({"exists": False}, ensure_ascii=False))
                else:
                    print("尚未建立索引")
                return 0
            summary = summarize_index(index)
            if args.json:
                print(
                    json.dumps(
                        {
                            "exists": True,
                            "built_at": index.get("built_at"),
                            "sources": index.get("sources", []),
                            "books": index.get("books", []),
                            "chunks": len(index.get("chunks", [])),
                            "summary": summary,
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                print(summary)
            return 0

        if args.command == "index":
            if args.all_sources:
                sources = list(SOURCES)
            elif args.source:
                sources = args.source
            else:
                sources = ["规则书"]
            summary = index_sources(sources, book_filter=args.book)
            if args.json:
                print(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False))
            else:
                print(summary)
            return 0

        if args.command == "query":
            if args.limit < 1:
                raise RuleError("--limit 必须 ≥ 1")
            index = load_index()
            if index is None:
                raise RuleError("尚未建立索引，请先运行：rules index")
            query = " ".join(args.keywords)
            hits = search(index, args.keywords, book=args.book, limit=args.limit)
            if args.json:
                print(json.dumps(render_json(query, hits), ensure_ascii=False))
            else:
                print(render_text(query, hits))
            return 0

        if args.command == "books":
            books = available_books()
            if args.json:
                print(json.dumps({"books": books}, ensure_ascii=False))
            else:
                if not books:
                    print("（固定文件夹中没有可索引的 PDF/txt）")
                for b in books:
                    print(f"{b['book']}（{b['source']}）")
            return 0
    except RuleError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
