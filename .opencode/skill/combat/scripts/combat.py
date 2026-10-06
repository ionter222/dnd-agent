from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
COMBAT_DIRNAME = "战斗_Combats"

# 同进程复用 character-sheet 的脚本（路径注入，不启子进程）
_SHEET_SCRIPTS = REPO_ROOT / ".opencode" / "skill" / "character-sheet" / "scripts"
if str(_SHEET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHEET_SCRIPTS))
import sheet  # noqa: E402


class CombatError(ValueError):
    pass


def resolve_combat_dir(cli_dir=None) -> pathlib.Path:
    if cli_dir is not None:
        return pathlib.Path(cli_dir)
    env = os.environ.get("DND_COMBAT_DIR")
    if env:
        return pathlib.Path(env)
    return REPO_ROOT / COMBAT_DIRNAME


def combat_path(name, cli_dir=None) -> pathlib.Path:
    return resolve_combat_dir(cli_dir) / f"{name}.json"


def load_combat(name, cli_dir=None) -> dict:
    path = combat_path(name, cli_dir)
    if not path.exists():
        raise CombatError(f"找不到战斗：{name}")
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise CombatError(f"战斗文件损坏：{name}") from None


def save_combat(name, data, cli_dir=None) -> None:
    path = combat_path(name, cli_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def default_combat(name) -> dict:
    return {
        "schema_version": 1,
        "name": name,
        "grid": {"width": 30, "height": 20, "cell_ft": 5},
        "round": 0,
        "turn_index": 0,
        "order": [],
        "combatants": {},
        "log": [],
    }


def new_combat(name, cli_dir=None) -> dict:
    if combat_path(name, cli_dir).exists():
        raise CombatError(f"战斗已存在：{name}")
    data = default_combat(name)
    data["log"].append("战斗创建")
    save_combat(name, data, cli_dir)
    return data


def _check_bounds(data, x, y) -> None:
    grid = data["grid"]
    if not (0 <= x < grid["width"] and 0 <= y < grid["height"]):
        raise CombatError("坐标出界")


def add_combatant(data, card_name, side="enemy", pos=None, cli_dir=None, sheet_dir=None) -> str:
    if card_name in data["combatants"]:
        raise CombatError(f"单位已存在：{card_name}")
    try:
        sheet.load_sheet(card_name, cli_dir=sheet_dir)
    except sheet.SheetError as exc:
        raise CombatError(str(exc)) from None
    spot = dict(pos) if pos else {"x": 0, "y": 0}
    _check_bounds(data, spot["x"], spot["y"])
    data["combatants"][card_name] = {
        "sheet": card_name,
        "side": side,
        "initiative": None,
        "pos": spot,
        "conditions": [],
        "reaction_used": False,
        "dead": False,
    }
    data["log"].append(f"加入单位：{card_name}（{side}）")
    return f"已加入 {card_name}（{side}）"


def _remove_from_order(data, name) -> None:
    order = data["order"]
    if name not in order:
        return
    idx = order.index(name)
    order.pop(idx)
    if idx < data["turn_index"]:
        data["turn_index"] -= 1
    data["turn_index"] = min(data["turn_index"], max(len(order) - 1, 0))


def remove_combatant(data, name) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    del data["combatants"][name]
    _remove_from_order(data, name)
    data["log"].append(f"移除单位：{name}")
    return f"已移除 {name}"


def end_combat(data) -> str:
    data["log"].append("战斗结束")
    return "战斗结束"


def set_initiative(data, name, value) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    data["combatants"][name]["initiative"] = value
    data["log"].append(f"录入先攻：{name} = {value}")
    return f"{name} 先攻 {value}"


def _turn_start(data, name) -> None:
    if name in data["combatants"]:
        data["combatants"][name]["reaction_used"] = False
        tick_conditions(data, name)


def begin_combat(data) -> str:
    for n, c in data["combatants"].items():
        if c["initiative"] is None:
            raise CombatError("仍有单位未录入先攻")
    order = sorted(data["combatants"].keys(),
                   key=lambda n: data["combatants"][n]["initiative"],
                   reverse=True)
    data["order"] = order
    data["round"] = 1
    data["turn_index"] = 0
    first = order[0] if order else "无"
    inits = [data["combatants"][n]["initiative"] for n in order]
    tie_note = "（有平手，由 DM 裁定）" if len(inits) != len(set(inits)) else ""
    data["log"].append(f"战斗开始（第 1 轮，先手：{first}{tie_note}）")
    if order:
        _turn_start(data, order[0])
    return f"战斗开始，先手：{first}{tie_note}"


def current_actor(data):
    order = data.get("order") or []
    if not order:
        return None
    return order[data["turn_index"]]


def cond_add(data, name, cond, rounds=None) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    conds = data["combatants"][name]["conditions"]
    if any(c["name"] == cond for c in conds):
        raise CombatError(f"条件已存在：{cond}")
    conds.append({"name": cond, "rounds": rounds})
    suffix = f"（{rounds} 回合）" if rounds is not None else ""
    data["log"].append(f"{name} 获得条件：{cond}{suffix}")
    return f"{name} 获得条件：{cond}{suffix}"


def cond_remove(data, name, cond) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    conds = data["combatants"][name]["conditions"]
    for c in conds:
        if c["name"] == cond:
            conds.remove(c)
            data["log"].append(f"{name} 移除条件：{cond}")
            return f"{name} 移除条件：{cond}"
    raise CombatError(f"条件不存在：{cond}")


def tick_conditions(data, name) -> list:
    if name not in data["combatants"]:
        return []
    conds = data["combatants"][name]["conditions"]
    removed = []
    for c in list(conds):
        if c["rounds"] is not None:
            c["rounds"] -= 1
            if c["rounds"] <= 0:
                conds.remove(c)
                removed.append(c["name"])
    return removed


def next_turn(data) -> str:
    order = data.get("order") or []
    if not order:
        raise CombatError("先攻顺序为空，请先 begin")
    data["turn_index"] += 1
    if data["turn_index"] >= len(order):
        data["turn_index"] = 0
        data["round"] += 1
    actor = order[data["turn_index"]]
    _turn_start(data, actor)
    data["log"].append(f"第 {data['round']} 轮 · {actor}")
    return actor


def set_reaction(data, name, state) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    if state == "used":
        data["combatants"][name]["reaction_used"] = True
    elif state == "reset":
        data["combatants"][name]["reaction_used"] = False
    else:
        raise CombatError(f"未知反应状态：{state}")
    return f"{name} 反应：{state}"


def distance_between(data, a, b) -> int:
    combatants = data["combatants"]
    for n in (a, b):
        if n not in combatants:
            raise CombatError(f"找不到单位：{n}")
    pa = combatants[a]["pos"]
    pb = combatants[b]["pos"]
    dx = abs(pa["x"] - pb["x"])
    dy = abs(pa["y"] - pb["y"])
    return max(dx, dy) * data["grid"]["cell_ft"]


def move_combatant(data, name, x, y, force=False, cli_dir=None, sheet_dir=None) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    _check_bounds(data, x, y)
    grid = data["grid"]
    c = data["combatants"][name]
    ox, oy = c["pos"]["x"], c["pos"]["y"]
    feet = max(abs(x - ox), abs(y - oy)) * grid["cell_ft"]
    if not force:
        card = sheet.load_sheet(c["sheet"], cli_dir=sheet_dir)
        speed = card["speed"]
        if feet > speed:
            raise CombatError(f"移动超出速度（{feet} > {speed} 尺）")
    c["pos"] = {"x": x, "y": y}
    data["log"].append(f"{name} 移动到 ({x},{y})")
    return f"{name} 移动到 ({x},{y})（{feet} 尺）"


def _card(data, name, sheet_dir):
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    card_name = data["combatants"][name]["sheet"]
    try:
        card = sheet.load_sheet(card_name, cli_dir=sheet_dir)
    except sheet.SheetError as e:
        raise CombatError(str(e))
    return card, card_name


def _persist(card, card_name, sheet_dir):
    sheet.save_sheet(card_name, card, cli_dir=sheet_dir)


def damage_combatant(data, name, n, cli_dir=None, sheet_dir=None) -> str:
    card, card_name = _card(data, name, sheet_dir)
    try:
        msg = sheet.apply_hp(card, -n)
    except sheet.SheetError as e:
        raise CombatError(str(e))
    _persist(card, card_name, sheet_dir)
    text = f"{name} 受到 {n} 点伤害；{msg}"
    data["log"].append(text)
    return text


def heal_combatant(data, name, n, item=None, cli_dir=None, sheet_dir=None) -> str:
    card, card_name = _card(data, name, sheet_dir)
    extra = ""
    if item is not None:
        inv = card.get("inventory", [])
        target = next((it for it in inv if it.get("name") == item), None)
        if target is None:
            raise CombatError(f"库存中没有：{item}")
        target["qty"] = target.get("qty", 1) - 1
        if target["qty"] <= 0:
            inv.remove(target)
        extra = f"（消耗 {item}）"
    try:
        msg = sheet.apply_hp(card, n)
    except sheet.SheetError as e:
        raise CombatError(str(e))
    _persist(card, card_name, sheet_dir)
    text = f"{name} 恢复 {n} 点生命{extra}；{msg}"
    data["log"].append(text)
    return text


def adjust_ac_combatant(data, name, op, value=None, cli_dir=None, sheet_dir=None) -> str:
    card, card_name = _card(data, name, sheet_dir)
    try:
        msg = sheet.modify_ac(card, op, value)
    except sheet.SheetError as e:
        raise CombatError(str(e))
    _persist(card, card_name, sheet_dir)
    data["log"].append(f"{name} AC：{msg}")
    return msg


def use_slot_combatant(data, name, ring, n, restore=False, cli_dir=None, sheet_dir=None) -> str:
    card, card_name = _card(data, name, sheet_dir)
    try:
        msg = sheet.use_slot(card, ring, n, restore=restore)
    except sheet.SheetError as e:
        raise CombatError(str(e))
    _persist(card, card_name, sheet_dir)
    data["log"].append(f"{name} 法术位：{msg}")
    return msg


def give_xp(data, name, n, cli_dir=None, sheet_dir=None) -> str:
    card, card_name = _card(data, name, sheet_dir)
    card["xp"] = card.get("xp", 0) + n
    _persist(card, card_name, sheet_dir)
    text = f"{name} 获得 {n} 点经验（现 {card['xp']}）"
    data["log"].append(text)
    return text


def status_data(data, cli_dir=None, sheet_dir=None) -> dict:
    current = current_actor(data)
    rows = []
    for name in data["order"]:
        c = data["combatants"][name]
        row = {
            "name": name,
            "side": c["side"],
            "initiative": c["initiative"],
            "pos": c["pos"],
            "conditions": c["conditions"],
            "current": (name == current),
            "hp": None,
            "ac": None,
            "attacks": [],
        }
        try:
            card = sheet.load_sheet(c["sheet"], cli_dir=sheet_dir)
            row["hp"] = dict(card.get("hp", {}))
            row["ac"] = sheet.armor_class(card)
            row["attacks"] = [a["name"] for a in card.get("attacks", [])]
        except sheet.SheetError:
            row["error"] = "缺卡"
        rows.append(row)
    return {
        "name": data.get("name"),
        "round": data["round"],
        "turn": data["turn_index"],
        "current": current,
        "rows": rows,
    }


def render_status(data, cli_dir=None, sheet_dir=None) -> str:
    sd = status_data(data, cli_dir=cli_dir, sheet_dir=sheet_dir)
    lines = [f"第 {sd['round']} 轮 · 当前 {sd['current'] or '（无）'}"]
    for row in sd["rows"]:
        mark = "→" if row["current"] else " "
        head = f"{mark} [{row['side']}] {row['name']}"
        pos = f"@({row['pos']['x']},{row['pos']['y']})"
        if row.get("error"):
            line = f"{head}  HP 缺卡  {pos}"
        else:
            hp = row["hp"]
            atk = "、".join(row["attacks"]) if row["attacks"] else "无"
            line = (
                f"{head}  HP {hp.get('current')}/{hp.get('max')}"
                f"  临{hp.get('temp', 0)}  AC {row['ac']}  攻击 {atk}  {pos}"
            )
        if row["conditions"]:
            cond_txt = "、".join(
                cc["name"] + (f"({cc['rounds']})" if cc.get("rounds") is not None else "")
                for cc in row["conditions"]
            )
            line += f"  条件 {cond_txt}"
        lines.append(line)
    return "\n".join(lines)


def kill_combatant(data, name, xp=None, share=None, cli_dir=None, sheet_dir=None) -> str:
    if name not in data["combatants"]:
        raise CombatError(f"找不到单位：{name}")
    shares = None
    if xp is not None:
        shares = share or [n for n, c in data["combatants"].items() if c["side"] in ("pc", "npc")]
        if not shares:
            raise CombatError("没有可分配经验的目标")
        for s in shares:
            _card(data, s, sheet_dir)
    data["combatants"][name]["dead"] = True
    _remove_from_order(data, name)
    data["log"].append(f"{name} 被击败")
    msg = f"{name} 被击败"
    if xp is not None:
        per = xp // len(shares)
        rem = xp - per * len(shares)
        for s in shares:
            give_xp(data, s, per, cli_dir=cli_dir, sheet_dir=sheet_dir)
        msg += f"；经验 {xp} 分给 {len(shares)} 人，每人 {per}"
        if rem > 0:
            msg += f"，余 {rem}"
    return msg


_SIDE_COLORS = {"pc": "#3b82f6", "npc": "#22c55e", "enemy": "#ef4444"}


def _xml_escape(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_svg(data, cell_px=24, margin=24) -> str:
    grid = data["grid"]
    gw = grid["width"] * cell_px
    gh = grid["height"] * cell_px
    w = margin * 2 + gw
    h = margin * 2 + gh
    current = current_actor(data)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#f8fafc"/>',
    ]
    for i in range(grid["width"] + 1):
        x = margin + i * cell_px
        parts.append(
            f'<line x1="{x}" y1="{margin}" x2="{x}" y2="{margin + gh}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )
    for j in range(grid["height"] + 1):
        y = margin + j * cell_px
        parts.append(
            f'<line x1="{margin}" y1="{y}" x2="{margin + gw}" y2="{y}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )
    title = f'{data.get("name", "战斗")} · 第 {data["round"]} 轮'
    parts.append(
        f'<text x="{margin}" y="{margin - 6}" font-size="14" '
        f'font-family="sans-serif" fill="#0f172a">{_xml_escape(title)}</text>'
    )
    for name in data["order"]:
        c = data["combatants"][name]
        cx = margin + c["pos"]["x"] * cell_px + cell_px / 2
        cy = margin + c["pos"]["y"] * cell_px + cell_px / 2
        r = cell_px * 0.4
        color = _SIDE_COLORS.get(c["side"], "#94a3b8")
        stroke = ' stroke="#f59e0b" stroke-width="3"' if name == current else ""
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"{stroke}/>')
        parts.append(
            f'<text x="{cx}" y="{cy + 4}" font-size="11" font-family="sans-serif" '
            f'fill="#ffffff" text-anchor="middle">{_xml_escape(name)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


class _ZhArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        print("错误：参数无效，请检查输入（可用 -h 查看帮助）", file=sys.stderr)
        raise SystemExit(2)


def _parse_pos(text):
    try:
        xs, ys = text.split(",")
        return {"x": int(xs), "y": int(ys)}
    except Exception:
        raise argparse.ArgumentTypeError(f"坐标格式应为 x,y：{text}")


def _emit(args, message, payload=None) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload if payload is not None else {"message": message},
                         ensure_ascii=False))
    else:
        print(message)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = _ZhArgumentParser(prog="combat", description="DnD 5e 战斗状态机（引擎不掷骰）")
    p.add_argument("--combat-dir", default=None)
    p.add_argument("--sheet-dir", default=None)
    sub = p.add_subparsers(dest="cmd")

    def add(name):
        sp = sub.add_parser(name)
        sp.add_argument("--json", action="store_true")
        return sp

    sp = add("new"); sp.add_argument("name")
    sp = add("add"); sp.add_argument("combat"); sp.add_argument("card")
    sp.add_argument("--side", choices=["pc", "npc", "enemy"], default="enemy")
    sp.add_argument("--pos", type=_parse_pos, default=None)
    sp = add("init"); sp.add_argument("combat"); sp.add_argument("name"); sp.add_argument("value", type=int)
    sp = add("begin"); sp.add_argument("combat")
    sp = add("next"); sp.add_argument("combat")
    sp = add("turn"); sp.add_argument("combat")
    sp = add("move"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("x", type=int); sp.add_argument("y", type=int)
    sp.add_argument("--force", action="store_true")
    sp = add("distance"); sp.add_argument("combat"); sp.add_argument("a"); sp.add_argument("b")
    sp = add("damage"); sp.add_argument("combat"); sp.add_argument("name"); sp.add_argument("n", type=int)
    sp = add("heal"); sp.add_argument("combat"); sp.add_argument("name"); sp.add_argument("n", type=int)
    sp.add_argument("--item", default=None)
    sp = add("cond"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("action", choices=["add", "remove"]); sp.add_argument("condname")
    sp.add_argument("--rounds", type=int, default=None)
    sp = add("kill"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("--xp", type=int, default=None); sp.add_argument("--share", default=None)
    sp = add("xp"); sp.add_argument("combat"); sp.add_argument("name"); sp.add_argument("n", type=int)
    sp = add("ac"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("op", choices=["+", "-", "set", "reset"])
    sp.add_argument("value", type=int, nargs="?", default=None)
    sp = add("slot"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("ring"); sp.add_argument("action", choices=["use", "restore"]); sp.add_argument("n", type=int)
    sp = add("reaction"); sp.add_argument("combat"); sp.add_argument("name")
    sp.add_argument("state", choices=["used", "reset"])
    sp = add("status"); sp.add_argument("combat")
    sp = add("map"); sp.add_argument("combat"); sp.add_argument("--out", default=None)
    sp = add("remove"); sp.add_argument("combat"); sp.add_argument("name")
    sp = add("end"); sp.add_argument("combat")
    return p


def main(argv=None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    cdir = args.combat_dir
    sdir = args.sheet_dir

    try:
        if args.cmd == "new":
            new_combat(args.name, cli_dir=cdir)
            return _emit(args, f"已创建战斗：{args.name}", {"name": args.name})

        if args.cmd == "status":
            data = load_combat(args.combat, cli_dir=cdir)
            if args.json:
                print(json.dumps(status_data(data, cli_dir=cdir, sheet_dir=sdir), ensure_ascii=False))
            else:
                print(render_status(data, cli_dir=cdir, sheet_dir=sdir))
            return 0

        if args.cmd == "map":
            data = load_combat(args.combat, cli_dir=cdir)
            out = pathlib.Path(args.out) if args.out else (resolve_combat_dir(cli_dir=cdir) / f"{args.combat}.svg")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_svg(data), encoding="utf-8")
            return _emit(args, f"地图已写入：{out}", {"path": str(out)})

        if args.cmd == "turn":
            data = load_combat(args.combat, cli_dir=cdir)
            actor = current_actor(data)
            return _emit(args, f"第 {data['round']} 轮 · 当前行动者：{actor}",
                         {"round": data["round"], "current": actor})

        if args.cmd == "distance":
            data = load_combat(args.combat, cli_dir=cdir)
            feet = distance_between(data, args.a, args.b)
            return _emit(args, f"{args.a} 与 {args.b} 相距 {feet} 尺", {"feet": feet})

        data = load_combat(args.combat, cli_dir=cdir)
        if args.cmd == "add":
            msg = add_combatant(data, args.card, side=args.side, pos=args.pos,
                                cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "init":
            msg = set_initiative(data, args.name, args.value)
        elif args.cmd == "begin":
            msg = begin_combat(data)
        elif args.cmd == "next":
            msg = next_turn(data)
        elif args.cmd == "move":
            msg = move_combatant(data, args.name, args.x, args.y, force=args.force,
                                 cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "damage":
            msg = damage_combatant(data, args.name, args.n, cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "heal":
            msg = heal_combatant(data, args.name, args.n, item=args.item, cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "cond":
            if args.action == "add":
                msg = cond_add(data, args.name, args.condname, rounds=args.rounds)
            else:
                msg = cond_remove(data, args.name, args.condname)
        elif args.cmd == "kill":
            shares = args.share.split(",") if args.share else None
            msg = kill_combatant(data, args.name, xp=args.xp, share=shares,
                                 cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "xp":
            msg = give_xp(data, args.name, args.n, cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "ac":
            msg = adjust_ac_combatant(data, args.name, args.op, value=args.value,
                                      cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "slot":
            msg = use_slot_combatant(data, args.name, args.ring, args.n,
                                     restore=(args.action == "restore"),
                                     cli_dir=cdir, sheet_dir=sdir)
        elif args.cmd == "reaction":
            msg = set_reaction(data, args.name, args.state)
        elif args.cmd == "remove":
            msg = remove_combatant(data, args.name)
        elif args.cmd == "end":
            msg = end_combat(data)
        else:
            parser.print_help()
            return 2
        save_combat(args.combat, data, cli_dir=cdir)
        return _emit(args, msg)
    except (CombatError, sheet.SheetError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
