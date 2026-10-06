"""战役 / 休整 / 升级 skill：结构化战役存档 + 短/长休 + 升级（通用部分）。

纯 stdlib。同进程 import character-sheet 的 sheet.py 改卡。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CAMPAIGN_DIRNAME = "存档_Saves"
SHEET_DIRNAME = "角色卡_CharacterSheets"

_SHEET_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "character-sheet" / "scripts"
if str(_SHEET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHEET_SCRIPTS))
import sheet


class CampaignError(ValueError):
    """战役 skill 的业务错误（消息为中文）。"""


def resolve_campaign_dir(cli_dir=None):
    """战役目录：显式 cli_dir > 环境变量 DND_CAMPAIGN_DIR > 仓库根/存档_Saves。"""
    if cli_dir:
        return pathlib.Path(cli_dir)
    env = os.environ.get("DND_CAMPAIGN_DIR")
    if env:
        return pathlib.Path(env)
    return REPO_ROOT / CAMPAIGN_DIRNAME


def _check_name(name):
    """战役名不得含路径分隔符，避免目录穿越。"""
    if not name or name in (".", "..") or any(sep in name for sep in ("/", "\\")):
        raise CampaignError(f"战役名非法：{name}")


def campaign_path(name, cli_dir=None):
    _check_name(name)
    return resolve_campaign_dir(cli_dir) / f"{name}.json"


def _validate_shape(data, name):
    for key in ("party", "log", "npcs", "quests"):
        if key in data and not isinstance(data[key], list):
            raise CampaignError(f"战役文件损坏：{name}")


def load_campaign(name, cli_dir=None):
    """读取战役；缺失 → CampaignError；JSON 损坏/编码/非 dict → CampaignError。"""
    path = campaign_path(name, cli_dir)
    if not path.exists():
        raise CampaignError(f"找不到战役：{name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise CampaignError(f"战役文件损坏：{name}") from exc
    if not isinstance(data, dict):
        raise CampaignError(f"战役文件损坏：{name}")
    _validate_shape(data, name)
    return data


def save_campaign(name, data, cli_dir=None):
    """写战役（UTF-8、ensure_ascii=False、indent=2），自动建目录。"""
    path = campaign_path(name, cli_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def default_campaign(name):
    now = _now()
    return {
        "schema_version": 1,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "in_game_time": "",
        "novel": False,
        "party": [],
        "log": [],
        "npcs": [],
        "quests": [],
    }


def new_campaign(name, cli_dir=None):
    """新建战役；已存在 → CampaignError。"""
    if campaign_path(name, cli_dir).exists():
        raise CampaignError(f"战役已存在：{name}")
    save_campaign(name, default_campaign(name), cli_dir)
    return f"已创建战役：{name}"


def list_campaigns(cli_dir=None):
    """列出战役摘要（损坏文件跳过），按名字排序。"""
    directory = resolve_campaign_dir(cli_dir)
    rows = []
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            row = {
                "name": data.get("name", path.stem),
                "in_game_time": data.get("in_game_time", ""),
                "log_count": len(data.get("log", [])),
            }
        except (ValueError, OSError, TypeError, KeyError, AttributeError):
            continue
        rows.append(row)
    rows.sort(key=lambda r: r["name"])
    return rows


def _touch(data):
    data["updated_at"] = _now()


def add_log(name, title, summary, details=None, time=None, tags=None, cli_dir=None):
    """追加一条剧情记录（结构化事实；details 为可选的小说式叙事）。"""
    data = load_campaign(name, cli_dir)
    entry = {
        "seq": len(data.get("log", [])) + 1,
        "time": time if time is not None else data.get("in_game_time", ""),
        "title": title,
        "summary": summary,
        "details": details if details is not None else "",
        "tags": tags if tags is not None else [],
    }
    data.setdefault("log", []).append(entry)
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"已记录：{title}"


def set_time(name, text, cli_dir=None):
    """设置游戏内时间。"""
    data = load_campaign(name, cli_dir)
    data["in_game_time"] = text
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"游戏内时间：{text}"


def novel_set(name, on, cli_dir=None):
    """开启/关闭小说叙事模式（用户偏好，持久化在存档 novel 字段）。"""
    data = load_campaign(name, cli_dir)
    data["novel"] = bool(on)
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"小说叙事模式：{'开启' if on else '关闭'}"


def npc_add(name, npc, note="", tags=None, cli_dir=None):
    """登记/更新一个 NPC（同名覆盖 note/tags）。"""
    data = load_campaign(name, cli_dir)
    npcs = data.setdefault("npcs", [])
    for item in npcs:
        if item.get("name") == npc:
            item["note"] = note
            if tags is not None:
                item["tags"] = tags
            _touch(data)
            save_campaign(name, data, cli_dir)
            return f"已更新 NPC：{npc}"
    npcs.append({"name": npc, "note": note, "tags": tags if tags is not None else []})
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"已添加 NPC：{npc}"


def quest_add(name, quest, detail="", cli_dir=None):
    """新增任务（重名 → CampaignError），初始状态「进行中」。"""
    data = load_campaign(name, cli_dir)
    quests = data.setdefault("quests", [])
    for item in quests:
        if item.get("name") == quest:
            raise CampaignError(f"任务已存在：{quest}")
    quests.append({"name": quest, "detail": detail, "status": "进行中"})
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"已添加任务：{quest}"


def quest_update(name, quest, status=None, detail=None, cli_dir=None):
    """更新任务状态/细节；找不到或状态非法 → CampaignError。"""
    if status is not None and status not in ("进行中", "已完成", "已失败"):
        raise CampaignError(f"未知任务状态：{status}（应为 进行中/已完成/已失败）")
    data = load_campaign(name, cli_dir)
    for item in data.get("quests", []):
        if item.get("name") == quest:
            if status is not None:
                item["status"] = status
            if detail is not None:
                item["detail"] = detail
            _touch(data)
            save_campaign(name, data, cli_dir)
            return f"已更新任务：{quest}"
    raise CampaignError(f"找不到任务：{quest}")


def _active_quests(data):
    return [q for q in data.get("quests", []) if q.get("status") == "进行中"]


def recap_data(name, last=5, cli_dir=None):
    """给 agent 重装上下文用的短回顾。"""
    data = load_campaign(name, cli_dir)
    logs = data.get("log", [])
    recent = logs[-last:] if last else []
    return {
        "name": name,
        "in_game_time": data.get("in_game_time", ""),
        "party": data.get("party", []),
        "quests": _active_quests(data),
        "recent": recent,
    }


def render_recap(data):
    lines = [f"《{data['name']}》 · {data.get('in_game_time', '')}"]
    party = data.get("party", [])
    if party:
        lines.append("队伍：" + "、".join(p.get("sheet", "") for p in party))
    if data.get("quests"):
        lines.append("进行中任务：" + "、".join(q.get("name", "") for q in data["quests"]))
    lines.append("最近记录：")
    for entry in data.get("recent", []):
        lines.append(f"- {entry.get('time', '')} · {entry.get('title', '')}：{entry.get('summary', '')}")
    return "\n".join(lines)


def status_data(name, cli_dir=None):
    data = load_campaign(name, cli_dir)
    logs = data.get("log", [])
    return {
        "name": name,
        "in_game_time": data.get("in_game_time", ""),
        "party": data.get("party", []),
        "quests": _active_quests(data),
        "last_log": logs[-1] if logs else None,
    }


def render_status(data):
    lines = [f"《{data['name']}》 · {data.get('in_game_time', '')}"]
    party = data.get("party", [])
    lines.append("队伍：" + ("、".join(p.get("sheet", "") for p in party) if party else "（空）"))
    if data.get("quests"):
        lines.append("进行中任务：")
        for q in data["quests"]:
            lines.append(f"- {q.get('name', '')}（{q.get('status', '')}）")
    else:
        lines.append("进行中任务：无")
    last_log = data.get("last_log")
    if last_log:
        lines.append(f"最近记录：{last_log.get('time', '')} · {last_log.get('title', '')}：{last_log.get('summary', '')}")
    return "\n".join(lines)


def level_up(sheet_name, class_name, hp=None, avg=False, subclass=None, cli_dir=None, sheet_dir=None):
    """升级通用部分：等级/生命骰/HP。法术位与特性需手动录入。"""
    if (hp is None) == (avg is False):
        raise CampaignError("需要指定 --hp 或 --avg（二者恰一）")
    try:
        card = sheet.load_sheet(sheet_name, cli_dir=sheet_dir)
    except sheet.SheetError as exc:
        raise CampaignError(str(exc))
    classes = card.setdefault("classes", [])
    for cls in classes:
        if cls.get("name") == class_name:
            cls["level"] = cls.get("level", 0) + 1
            if subclass:
                cls["subclass"] = subclass
            break
    else:
        entry = {"name": class_name, "level": 1}
        if subclass:
            entry["subclass"] = subclass
        classes.append(entry)
    con_mod = sheet.ability_modifier(card["abilities"]["con"])
    sides = int(str(card["hit_dice"]["die"])[1:])
    gain = hp if hp is not None else max(1, sides // 2 + 1 + con_mod)
    card["hp"]["max"] += gain
    card["hp"]["current"] += gain
    card["hit_dice"]["total"] = card["hit_dice"].get("total", 0) + 1
    sheet.save_sheet(sheet_name, card, cli_dir=sheet_dir)
    return f"{sheet_name} 升至 {class_name} 级（+{gain} HP）。请手动录入新增法术位/特性。"


def _iter_cards(name, cli_dir, sheet_dir):
    data = load_campaign(name, cli_dir)
    for entry in data.get("party", []):
        sheet_name = entry.get("sheet")
        try:
            card = sheet.load_sheet(sheet_name, cli_dir=sheet_dir)
        except sheet.SheetError as exc:
            raise CampaignError(str(exc))
        yield sheet_name, card


def rest(name, kind, heal=None, spend=0, cli_dir=None, sheet_dir=None):
    """长休 / 短休。引擎不掷骰：短休治疗量由 DM 掷好传入。"""
    if kind not in ("long", "short"):
        raise CampaignError(f"未知休息类型：{kind}（应为 long 或 short）")
    if spend < 0:
        raise CampaignError("生命骰数量不能为负")
    members = list(_iter_cards(name, cli_dir, sheet_dir))
    if not members:
        raise CampaignError("队伍为空，无法休息")
    if kind == "short" and spend:
        for sheet_name, card in members:
            hd = card.get("hit_dice", {})
            used = hd.get("used", 0)
            total = hd.get("total", 0)
            if used + spend > total:
                raise CampaignError(f"生命骰不足：{sheet_name} 已用 {used}/{total}")
    for sheet_name, card in members:
        if kind == "long":
            hp = card.setdefault("hp", {})
            missing = hp.get("max", 0) - hp.get("current", 0)
            if missing:
                sheet.apply_hp(card, missing)
            hp["temp"] = 0
            for ring in card.get("spellcasting", {}).get("slots", {}):
                card["spellcasting"]["slots"][ring]["used"] = 0
            sheet.death_save(card, "reset")
            hit_dice = card.setdefault("hit_dice", {})
            total = hit_dice.get("total", 0)
            hit_dice["used"] = max(0, hit_dice.get("used", 0) - max(1, total // 2))
        else:
            if heal:
                sheet.apply_hp(card, heal)
            if spend:
                hit_dice = card.setdefault("hit_dice", {})
                hit_dice["used"] = hit_dice.get("used", 0) + spend
        sheet.save_sheet(sheet_name, card, cli_dir=sheet_dir)
    label = "长" if kind == "long" else "短"
    return f"已进行{label}休（{len(members)} 人）"


def link_sheet(name, sheet_name, role="pc", cli_dir=None, sheet_dir=None):
    """把角色卡加入队伍（pc/npc）；卡不存在 → CampaignError。"""
    try:
        card = sheet.load_sheet(sheet_name, cli_dir=sheet_dir)
    except sheet.SheetError as exc:
        raise CampaignError(str(exc))
    if not isinstance(card, dict):
        raise CampaignError(f"角色卡损坏：{sheet_name}")
    data = load_campaign(name, cli_dir)
    party = data.setdefault("party", [])
    for member in party:
        if member.get("sheet") == sheet_name:
            member["role"] = role
            _touch(data)
            save_campaign(name, data, cli_dir)
            return f"已更新队伍成员：{sheet_name}（{role}）"
    party.append({"sheet": sheet_name, "role": role})
    _touch(data)
    save_campaign(name, data, cli_dir)
    return f"已加入队伍：{sheet_name}（{role}）"


def unlink_sheet(name, sheet_name, cli_dir=None):
    """把角色卡移出队伍；不在队伍 → CampaignError。"""
    data = load_campaign(name, cli_dir)
    party = data.get("party", [])
    for i, member in enumerate(party):
        if member.get("sheet") == sheet_name:
            party.pop(i)
            _touch(data)
            save_campaign(name, data, cli_dir)
            return f"已移出队伍：{sheet_name}"
    raise CampaignError(f"队伍中没有：{sheet_name}")


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


def _emit(args, message, payload=None):
    if getattr(args, "json", False):
        print(json.dumps(payload if payload is not None else message, ensure_ascii=False))
    else:
        print(message)


def build_parser():
    parser = _ZhArgumentParser(prog="campaign", description="跑团战役存档 / 休息 / 升级")
    parser.add_argument("--campaign-dir", default=None)
    parser.add_argument("--sheet-dir", default=None)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("list")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("status")
    p.add_argument("name")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("log")
    p.add_argument("name")
    p.add_argument("title")
    p.add_argument("summary")
    p.add_argument("--details", default=None)
    p.add_argument("--time", default=None)
    p.add_argument("--tags", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("time")
    p.add_argument("name")
    p.add_argument("text")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("novel")
    p.add_argument("name")
    p.add_argument("state", choices=["on", "off"])
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("recap")
    p.add_argument("name")
    p.add_argument("--last", type=int, default=5)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("link")
    p.add_argument("name")
    p.add_argument("sheet")
    p.add_argument("--role", default="pc")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("unlink")
    p.add_argument("name")
    p.add_argument("sheet")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("npc")
    p.add_argument("name")
    p.add_argument("action", choices=["add"])
    p.add_argument("npc")
    p.add_argument("--note", default=None)
    p.add_argument("--tags", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("quest")
    p.add_argument("name")
    p.add_argument("action", choices=["add", "update"])
    p.add_argument("quest")
    p.add_argument("--detail", default=None)
    p.add_argument("--status", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("rest")
    p.add_argument("name")
    p.add_argument("kind", choices=["short", "long"])
    p.add_argument("--heal", type=int, default=None)
    p.add_argument("--spend", type=int, default=1)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("level")
    p.add_argument("sheet")
    p.add_argument("cls")
    p.add_argument("--hp", type=int, default=None)
    p.add_argument("--avg", action="store_true")
    p.add_argument("--subclass", default=None)
    p.add_argument("--json", action="store_true")

    return parser


def main(argv=None):
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    cli_dir = args.campaign_dir
    sheet_dir = args.sheet_dir
    try:
        cmd = args.command
        if cmd == "new":
            _emit(args, new_campaign(args.name, cli_dir))
        elif cmd == "list":
            rows = list_campaigns(cli_dir)
            text = chr(10).join(f"{r['name']}（{r['in_game_time']}，{r['log_count']} 条日志）" for r in rows) or "（无战役）"
            _emit(args, text, rows)
        elif cmd == "status":
            data = status_data(args.name, cli_dir)
            _emit(args, render_status(data), data)
        elif cmd == "log":
            tags = args.tags.split(",") if args.tags else None
            _emit(args, add_log(args.name, args.title, args.summary, details=args.details,
                                time=args.time, tags=tags, cli_dir=cli_dir))
        elif cmd == "time":
            _emit(args, set_time(args.name, args.text, cli_dir))
        elif cmd == "novel":
            _emit(args, novel_set(args.name, args.state == "on", cli_dir))
        elif cmd == "recap":
            data = recap_data(args.name, last=args.last, cli_dir=cli_dir)
            _emit(args, render_recap(data), data)
        elif cmd == "link":
            _emit(args, link_sheet(args.name, args.sheet, role=args.role, cli_dir=cli_dir, sheet_dir=sheet_dir))
        elif cmd == "unlink":
            _emit(args, unlink_sheet(args.name, args.sheet, cli_dir=cli_dir))
        elif cmd == "npc":
            if args.action == "add":
                tags = args.tags.split(",") if args.tags else None
                _emit(args, npc_add(args.name, args.npc, note=args.note or "", tags=tags, cli_dir=cli_dir))
            else:
                raise CampaignError(f"未知 npc 动作：{args.action}")
        elif cmd == "quest":
            if args.action == "add":
                _emit(args, quest_add(args.name, args.quest, detail=args.detail or "", cli_dir=cli_dir))
            else:
                _emit(args, quest_update(args.name, args.quest, status=args.status, detail=args.detail, cli_dir=cli_dir))
        elif cmd == "rest":
            _emit(args, rest(args.name, args.kind, heal=args.heal, spend=args.spend,
                             cli_dir=cli_dir, sheet_dir=sheet_dir))
        elif cmd == "level":
            _emit(args, level_up(args.sheet, args.cls, hp=args.hp, avg=args.avg, subclass=args.subclass,
                                 cli_dir=cli_dir, sheet_dir=sheet_dir))
        return 0
    except (CampaignError, sheet.SheetError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except (KeyError, TypeError) as exc:
        print(f"错误：数据异常：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
