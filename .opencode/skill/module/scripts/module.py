"""模组运行 skill：跟踪模组进度并取回场景原文。"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
RUN_DIRNAME = "存档_Saves"

_RULES_SCRIPTS = REPO_ROOT / ".opencode" / "skill" / "rules-reference" / "scripts"
if str(_RULES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RULES_SCRIPTS))
import rules  # noqa: E402


class ModuleError(ValueError):
    """模组运行的通用错误（中文消息）。"""


def resolve_run_dir(cli_dir=None):
    if cli_dir:
        return pathlib.Path(cli_dir)
    env = os.environ.get("DND_MODULE_DIR")
    if env:
        return pathlib.Path(env)
    return REPO_ROOT / RUN_DIRNAME


def _check_name(name):
    if (not name or name in (".", "..") or "/" in name or "\\" in name
            or ":" in name or any(ord(ch) < 32 for ch in name)):
        raise ModuleError(f"运行名非法：{name}")


def run_path(name, cli_dir=None):
    _check_name(name)
    return resolve_run_dir(cli_dir) / f"{name}.json"


def _validate_run(data, name):
    if not isinstance(data, dict):
        raise ModuleError(f"运行文件损坏：{name}")
    for key in ("visited", "clues", "cleared", "decisions"):
        value = data.get(key)
        if value is not None and not isinstance(value, list):
            raise ModuleError(f"运行文件损坏：{name}")
    for key in ("clues", "decisions"):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                raise ModuleError(f"运行文件损坏：{name}")
    return data


def load_run(name, cli_dir=None):
    path = run_path(name, cli_dir)
    if not path.exists():
        raise ModuleError(f"找不到运行：{name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise ModuleError(f"运行文件损坏：{name}")
    return _validate_run(data, name)


def save_run(name, data, cli_dir=None):
    path = run_path(name, cli_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _touch(data):
    data["updated_at"] = _now()


def default_run(name, module_name, campaign=None):
    now = _now()
    return {
        "schema_version": 1,
        "name": name,
        "campaign": campaign,
        "module": module_name,
        "created_at": now,
        "updated_at": now,
        "current": None,
        "visited": [],
        "clues": [],
        "cleared": [],
        "decisions": [],
    }


def new_run(name, module_name, cli_dir=None, campaign=None):
    if run_path(name, cli_dir).exists():
        raise ModuleError(f"运行已存在：{name}")
    save_run(name, default_run(name, module_name, campaign), cli_dir)
    return f"已新建运行：{name}（模组：{module_name}）"


def list_runs(cli_dir=None):
    root = resolve_run_dir(cli_dir)
    rows = []
    if not root.exists():
        return rows
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            rows.append({
                "name": data.get("name", path.stem),
                "module": data.get("module", ""),
                "current": data.get("current"),
                "visited_count": len(data.get("visited", []) or []),
                "clue_count": len(data.get("clues", []) or []),
                "cleared_count": len(data.get("cleared", []) or []),
            })
        except (ValueError, OSError, TypeError, KeyError):
            continue
    rows.sort(key=lambda r: r["name"])
    return rows


def remove_run(name, cli_dir=None):
    path = run_path(name, cli_dir)
    if not path.exists():
        raise ModuleError(f"找不到运行：{name}")
    path.unlink()
    return f"已删除运行：{name}"


def link_campaign(name, campaign, cli_dir=None):
    data = load_run(name, cli_dir)
    data["campaign"] = campaign
    _touch(data)
    save_run(name, data, cli_dir)
    return f"已关联战役：{campaign}"


def unlink_campaign(name, cli_dir=None):
    data = load_run(name, cli_dir)
    data["campaign"] = None
    _touch(data)
    save_run(name, data, cli_dir)
    return f"已解除战役关联：{name}"


def set_scene(name, scene, cli_dir=None):
    """设当前场景，并确保场景进入 visited。"""
    data = load_run(name, cli_dir)
    data["current"] = scene
    visited = data.setdefault("visited", [])
    if scene not in visited:
        visited.append(scene)
    _touch(data)
    save_run(name, data, cli_dir)
    return f"当前场景：{scene}"


def visit(name, scene, cli_dir=None):
    """仅标记已访问，不改变 current。"""
    data = load_run(name, cli_dir)
    visited = data.setdefault("visited", [])
    if scene not in visited:
        visited.append(scene)
        _touch(data)
        save_run(name, data, cli_dir)
    return f"已访问：{scene}"


def clue_add(name, clue, detail="", cli_dir=None):
    """追加线索；同名线索更新 detail（幂等）。"""
    data = load_run(name, cli_dir)
    clues = data.setdefault("clues", [])
    now = _now()
    for item in clues:
        if item.get("name") == clue:
            item["detail"] = detail
            item["time"] = now
            _touch(data)
            save_run(name, data, cli_dir)
            return f"已更新线索：{clue}"
    clues.append({"name": clue, "detail": detail, "time": now})
    _touch(data)
    save_run(name, data, cli_dir)
    return f"已记录线索：{clue}"


def clue_list(name, cli_dir=None):
    return load_run(name, cli_dir).get("clues", [])


def clear_encounter(name, encounter, cli_dir=None):
    """标记遭遇/房间已清（去重）。"""
    data = load_run(name, cli_dir)
    cleared = data.setdefault("cleared", [])
    if encounter not in cleared:
        cleared.append(encounter)
        _touch(data)
        save_run(name, data, cli_dir)
        return f"已标记清空：{encounter}"
    return f"已标记（无需重复）：{encounter}"


def decide(name, text, cli_dir=None):
    """记录关键分支决定。"""
    data = load_run(name, cli_dir)
    data.setdefault("decisions", []).append({"text": text, "time": _now()})
    _touch(data)
    save_run(name, data, cli_dir)
    return f"已记录决定：{text}"


def status_data(name, cli_dir=None):
    data = load_run(name, cli_dir)
    return {
        "name": data.get("name", name),
        "module": data.get("module", ""),
        "campaign": data.get("campaign"),
        "current": data.get("current"),
        "visited": data.get("visited", []),
        "clues": data.get("clues", []),
        "cleared": data.get("cleared", []),
        "decisions": data.get("decisions", []),
    }


def render_status(data):
    lines = [f"《{data['name']}》 · 模组：{data.get('module', '')}"]
    lines.append(f"当前：{data.get('current') or '（未设定）'}")
    lines.append(
        f"已访问 {len(data.get('visited', []))} · 线索 {len(data.get('clues', []))}"
        f" · 已清 {len(data.get('cleared', []))} · 决定 {len(data.get('decisions', []))}"
    )
    return "\n".join(lines)


def read_scene(name, scene=None, book=None, limit=5, cli_dir=None, index_dir=None, modules_dir=None):
    """取场景原文；有索引走 rules-reference，无索引优雅降级。"""
    data = load_run(name, cli_dir)
    scene = scene or data.get("current")
    if not scene:
        raise ModuleError("未指定场景（也没有当前场景）")
    try:
        index = rules.load_index(index_dir)
    except Exception:
        index = None
    if index:
        hits = rules.search(index, [scene], book=book or data.get("module"), limit=limit)
        return {"indexed": True, "scene": scene, "hits": hits}
    base = pathlib.Path(modules_dir) if modules_dir else REPO_ROOT / "模组_Modules"
    module = data.get("module", "")
    pdfs = []
    if base.exists():
        pdfs = [str(p) for p in base.rglob("*.pdf") if module in p.name]
    return {
        "indexed": False,
        "scene": scene,
        "hits": [],
        "module_pdfs": pdfs,
        "message": "尚未建立模组索引，可运行 rules-reference index --source 模组",
    }


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


class _ZhArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print("错误：参数无效，请检查输入（可用 -h 查看帮助）", file=sys.stderr)
        raise SystemExit(2)


def build_parser():
    p = _ZhArgumentParser(prog="module", description="模组运行：跟踪进度并取回场景原文。")
    p.add_argument("--run-dir", default=None)
    p.add_argument("--index-dir", default=None)
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("new")
    sp.add_argument("name")
    sp.add_argument("--module", required=True)
    sp.add_argument("--campaign", default=None)
    sp.add_argument("--json", action="store_true")
    sub.add_parser("list").add_argument("--json", action="store_true")
    sp = sub.add_parser("status")
    sp.add_argument("name")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("scene")
    sp.add_argument("name")
    sp.add_argument("scene")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("visit")
    sp.add_argument("name")
    sp.add_argument("scene")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("clue")
    sp.add_argument("name")
    sp.add_argument("action", choices=["add", "list"])
    sp.add_argument("clue", nargs="?")
    sp.add_argument("--detail", default="")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("clear")
    sp.add_argument("name")
    sp.add_argument("encounter")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("decide")
    sp.add_argument("name")
    sp.add_argument("text")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("read")
    sp.add_argument("name")
    sp.add_argument("scene", nargs="?")
    sp.add_argument("--book", default=None)
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("link")
    sp.add_argument("name")
    sp.add_argument("campaign")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("unlink")
    sp.add_argument("name")
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("remove")
    sp.add_argument("name")
    sp.add_argument("--json", action="store_true")
    return p


def _emit(args, message, payload=None):
    if getattr(args, "json", False):
        print(json.dumps(payload if payload is not None else {"message": message}, ensure_ascii=False))
    else:
        print(message)


def _render_read(result):
    if result.get("indexed"):
        if not result.get("hits"):
            return f"未找到与 {result['scene']} 相关的片段"
        lines = [f"《{result['scene']}》原文片段："]
        for h in result["hits"]:
            lines.append(f"- [{h.get('book', '')} p{h.get('page', '')}] {h.get('text', '')}")
        return "\n".join(lines)
    lines = [result.get("message", "尚未建立模组索引")]
    pdfs = result.get("module_pdfs", [])
    if pdfs:
        lines.append("模组 PDF：")
        lines.extend(f"- {p}" for p in pdfs)
    return "\n".join(lines)


def main(argv=None):
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        rd = args.run_dir
        if args.command == "new":
            new_run(args.name, args.module, cli_dir=rd, campaign=args.campaign)
            _emit(args, f"已新建模组运行：{args.name}（{args.module}）", {"name": args.name, "module": args.module})
        elif args.command == "list":
            runs = list_runs(rd)
            if getattr(args, "json", False):
                print(json.dumps(runs, ensure_ascii=False))
            elif not runs:
                print("（没有进行中的模组运行）")
            else:
                for r in runs:
                    print(f"- {r['name']}（{r['module']}）当前：{r['current'] or '—'} 已访问 {r['visited_count']} · 线索 {r['clue_count']} · 已清 {r['cleared_count']}")
        elif args.command == "status":
            data = status_data(args.name, cli_dir=rd)
            _emit(args, render_status(data), data)
        elif args.command == "scene":
            set_scene(args.name, args.scene, cli_dir=rd)
            _emit(args, f"当前场景：{args.scene}", {"current": args.scene})
        elif args.command == "visit":
            visit(args.name, args.scene, cli_dir=rd)
            _emit(args, f"已标记访问：{args.scene}", {"visited": args.scene})
        elif args.command == "clue":
            if args.action == "add":
                if not args.clue:
                    print("错误：clue add 需要线索名", file=sys.stderr)
                    return 2
                clue_add(args.name, args.clue, detail=args.detail, cli_dir=rd)
                _emit(args, f"已记录线索：{args.clue}", {"clue": args.clue})
            else:
                clues = clue_list(args.name, cli_dir=rd)
                if getattr(args, "json", False):
                    print(json.dumps(clues, ensure_ascii=False))
                else:
                    for c in clues:
                        print(f"- {c['name']}：{c['detail']}")
        elif args.command == "clear":
            clear_encounter(args.name, args.encounter, cli_dir=rd)
            _emit(args, f"已标记清除：{args.encounter}", {"cleared": args.encounter})
        elif args.command == "decide":
            decide(args.name, args.text, cli_dir=rd)
            _emit(args, f"已记录决定：{args.text}", {"decision": args.text})
        elif args.command == "read":
            result = read_scene(args.name, args.scene, book=args.book, limit=args.limit, cli_dir=rd, index_dir=args.index_dir)
            _emit(args, _render_read(result), result)
        elif args.command == "link":
            link_campaign(args.name, args.campaign, cli_dir=rd)
            _emit(args, f"已关联战役：{args.campaign}", {"campaign": args.campaign})
        elif args.command == "unlink":
            unlink_campaign(args.name, cli_dir=rd)
            _emit(args, "已解除关联", {"campaign": None})
        elif args.command == "remove":
            remove_run(args.name, cli_dir=rd)
            _emit(args, f"已删除模组运行：{args.name}", {"name": args.name})
        return 0
    except (ModuleError, rules.RuleError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, AttributeError) as exc:
        print(f"错误：数据异常：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
