"""角色卡 skill 实现。存储层 + 派生值 + 变更结算 + 校验/渲染 + CLI。"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SHEET_DIRNAME = "角色卡_CharacterSheets"


class SheetError(ValueError):
    """角色卡操作错误（中文消息，CLI 捕获后退 2）。"""


def resolve_sheet_dir(cli_dir: str | None = None) -> pathlib.Path:
    if cli_dir:
        return pathlib.Path(cli_dir)
    env = os.environ.get("DND_SHEET_DIR")
    if env:
        return pathlib.Path(env)
    return REPO_ROOT / SHEET_DIRNAME


def sheet_path(name: str, cli_dir: str | None = None) -> pathlib.Path:
    return resolve_sheet_dir(cli_dir) / f"{name}.json"


def load_sheet(name: str, cli_dir: str | None = None) -> dict:
    path = sheet_path(name, cli_dir)
    if not path.exists():
        raise SheetError(f"找不到角色卡：{name}")
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SheetError(f"角色卡 {name} 的 JSON 损坏：{exc}") from exc


def save_sheet(name: str, data: dict, cli_dir: str | None = None) -> None:
    path = sheet_path(name, cli_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]

SKILL_ABILITIES = {
    "运动": "str",
    "杂技": "dex", "巧手": "dex", "隐匿": "dex",
    "奥秘": "int", "历史": "int", "调查": "int", "自然": "int", "宗教": "int",
    "驯兽": "wis", "洞悉": "wis", "医药": "wis", "察觉": "wis", "生存": "wis",
    "欺瞒": "cha", "威吓": "cha", "表演": "cha", "说服": "cha",
}


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def total_level(data: dict) -> int:
    return sum(c["level"] for c in data["classes"])


def proficiency_bonus(data: dict) -> int:
    return 2 + (total_level(data) - 1) // 4


def save_bonus(data: dict, ability: str) -> int:
    mod = ability_modifier(data["abilities"][ability])
    if ability in data.get("save_profs", []):
        mod += proficiency_bonus(data)
    return mod


def skill_bonus(data: dict, skill: str) -> int:
    ability = SKILL_ABILITIES[skill]
    mod = ability_modifier(data["abilities"][ability])
    prof = proficiency_bonus(data)
    if skill in data.get("skill_profs", []):
        mod += prof
    if skill in data.get("skill_expertise", []):
        mod += prof
    return mod


def passive_perception(data: dict) -> int:
    return 10 + skill_bonus(data, "察觉")


def _spellcasting_ability_mod(data: dict) -> tuple[int, int]:
    sc = data.get("spellcasting")
    if not sc or not sc.get("ability"):
        raise SheetError("该角色无施法能力")
    return ability_modifier(data["abilities"][sc["ability"]]), proficiency_bonus(data)


def spell_dc(data: dict) -> int:
    mod, prof = _spellcasting_ability_mod(data)
    return 8 + prof + mod


def spell_attack_bonus(data: dict) -> int:
    mod, prof = _spellcasting_ability_mod(data)
    return prof + mod


def armor_class(data: dict) -> int:
    ac = data["ac"]
    return ac["base"] + ac.get("temp", 0)


def initiative_bonus(data: dict) -> int:
    val = data.get("initiative_bonus")
    if val is not None:
        return val
    return ability_modifier(data["abilities"]["dex"])


def default_sheet(name: str) -> dict:
    return {
        "schema_version": 1,
        "name": name,
        "player": "",
        "race": "",
        "classes": [{"name": "冒险者", "level": 1}],
        "background": "",
        "alignment": "",
        "xp": 0,
        "abilities": {a: 10 for a in ABILITIES},
        "save_profs": [],
        "skill_profs": [],
        "skill_expertise": [],
        "tool_profs": [],
        "weapon_profs": [],
        "ac": {"base": 10, "temp": 0},
        "hp": {"max": 10, "current": 10, "temp": 0},
        "hit_dice": {"die": "d8", "total": 1, "used": 0},
        "speed": 30,
        "initiative_bonus": None,
        "spellcasting": {"ability": None, "slots": {}, "spells": [], "concentration": None},
        "attacks": [],
        "features": [],
        "languages": [],
        "personality": {"traits": [], "ideals": [], "bonds": [], "flaws": []},
        "inventory": [],
        "gold": 0,
        "conditions": [],
        "death_saves": {"successes": 0, "failures": 0},
        "notes": "",
    }


def new_sheet(name: str, from_name: str | None = None, cli_dir=None) -> dict:
    if sheet_path(name, cli_dir).exists():
        raise SheetError(f"角色卡已存在：{name}")
    if from_name is not None:
        data = load_sheet(from_name, cli_dir)
        data["name"] = name
    else:
        data = default_sheet(name)
    save_sheet(name, data, cli_dir)
    return data


def list_sheets(cli_dir=None) -> list[dict]:
    directory = resolve_sheet_dir(cli_dir)
    if not directory.exists():
        return []
    rows = []
    for p in directory.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            hp = data.get("hp", {})
            rows.append({
                "name": data.get("name", p.stem),
                "level": total_level(data),
                "hp_current": hp.get("current"),
                "hp_max": hp.get("max"),
            })
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            continue
    rows.sort(key=lambda r: r["name"])
    return rows


def apply_hp(data: dict, delta: int) -> str:
    hp = data["hp"]
    before_temp, before_current = hp["temp"], hp["current"]
    if delta < 0:
        dmg = -delta
        absorbed = min(hp["temp"], dmg)
        hp["temp"] -= absorbed
        dmg -= absorbed
        hp["current"] -= dmg
    else:
        hp["current"] += delta
    hp["current"] = max(0, min(hp["current"], hp["max"]))
    hp["temp"] = max(0, hp["temp"])
    msg = f"HP {before_current}(+{before_temp}) → {hp['current']}(+{hp['temp']})"
    if hp["current"] == 0 and before_current > 0:
        msg += "；进入 0 HP，需做死亡豁免"
    return msg


def set_hp(data: dict, value: int) -> str:
    if not (0 <= value <= data["hp"]["max"]):
        raise SheetError(f"HP 必须在 0..{data['hp']['max']} 之间")
    old = data["hp"]["current"]
    data["hp"]["current"] = value
    return f"HP {old} → {value}"


def set_hp_max(data: dict, value: int) -> str:
    if value < 1:
        raise SheetError("HP 上限必须 >= 1")
    old = data["hp"]["max"]
    data["hp"]["max"] = value
    if data["hp"]["current"] > value:
        data["hp"]["current"] = value
    return f"HP 上限 {old} → {value}"


def use_slot(data: dict, ring: str, n: int, restore: bool = False) -> str:
    slots = data.get("spellcasting", {}).get("slots", {})
    if ring not in slots:
        raise SheetError(f"不存在 {ring} 环法术位")
    slot = slots[ring]
    new_used = slot["used"] - n if restore else slot["used"] + n
    if not (0 <= new_used <= slot["max"]):
        raise SheetError(f"{ring} 环法术位不足（已用 {slot['used']}/{slot['max']}）")
    slot["used"] = new_used
    action = "恢复" if restore else "消耗"
    return f"{ring} 环法术位{action} {n}，已用 {new_used}/{slot['max']}"


def modify_ac(data: dict, op: str, value: int | None = None) -> str:
    if op in ("+", "-", "set") and value is None:
        raise SheetError(f"AC 操作 {op} 需要一个数值")
    old = data["ac"]["temp"]
    if op == "+":
        data["ac"]["temp"] = old + value
    elif op == "-":
        data["ac"]["temp"] = old - value
    elif op == "set":
        data["ac"]["temp"] = value
    elif op == "reset":
        data["ac"]["temp"] = 0
    else:
        raise SheetError(f"未知的 AC 操作：{op}")
    return f"AC 临时加值 {old} → {data['ac']['temp']}"


def cond_add(data: dict, cond: str) -> str:
    if cond in data["conditions"]:
        raise SheetError(f"状态已存在：{cond}")
    data["conditions"].append(cond)
    return f"获得状态：{cond}"


def cond_remove(data: dict, cond: str) -> str:
    if cond not in data["conditions"]:
        raise SheetError(f"不存在状态：{cond}")
    data["conditions"].remove(cond)
    return f"移除状态：{cond}"


def death_save(data: dict, kind: str) -> str:
    ds = data["death_saves"]
    if kind == "reset":
        ds["successes"] = 0
        ds["failures"] = 0
        return "死亡豁免已重置"
    if kind == "success":
        if ds["successes"] >= 3:
            raise SheetError("死亡豁免成功已达上限")
        ds["successes"] += 1
        if ds["successes"] >= 3:
            return f"死亡豁免成功 {ds['successes']}/3，伤势稳定"
        return f"死亡豁免成功 {ds['successes']}/3"
    if kind == "failure":
        if ds["failures"] >= 3:
            raise SheetError("死亡豁免失败已达上限")
        ds["failures"] += 1
        if ds["failures"] >= 3:
            return f"死亡豁免失败 {ds['failures']}/3，死亡"
        return f"死亡豁免失败 {ds['failures']}/3"
    raise SheetError(f"未知的死亡豁免类型：{kind}")


def get_path(data: dict, path: str):
    node = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SheetError(f"路径不存在：{path}")
        node = node[part]
    return node


def set_path(data: dict, path: str, value) -> str:
    parts = path.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            raise SheetError(f"路径不存在：{path}")
        node = node[part]
    if not isinstance(node, dict):
        raise SheetError(f"路径不存在：{path}")
    node[parts[-1]] = value
    return f"设置 {path} = {value}"


def add_path(data: dict, path: str, delta: float) -> str:
    current = get_path(data, path)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        raise SheetError(f"路径不是数字，无法加值：{path}")
    value = current + delta
    set_path(data, path, value)
    return f"{path}: {current} → {value}"


def check_bonus(data: dict, skill: str) -> int:
    if skill not in SKILL_ABILITIES:
        raise SheetError(f"未知技能：{skill}")
    return skill_bonus(data, skill)


def save_bonus_value(data: dict, ability: str) -> int:
    if ability not in ABILITIES:
        raise SheetError(f"未知属性：{ability}")
    return save_bonus(data, ability)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_sheet(data: dict) -> list[str]:
    problems: list[str] = []

    if "schema_version" not in data:
        problems.append("缺少 schema_version")

    abilities = data.get("abilities", {})
    for ab in ABILITIES:
        score = abilities.get(ab)
        if not _is_int(score) or not (1 <= score <= 30):
            problems.append(f"属性 {ab} 超出范围 1..30：{score!r}")

    classes = data.get("classes") or []
    if not classes:
        problems.append("classes 不能为空")
    else:
        for i, item in enumerate(classes):
            lvl = item.get("level") if isinstance(item, dict) else None
            if not _is_int(lvl) or lvl < 1:
                problems.append(f"classes[{i}].level 必须 ≥ 1：{lvl!r}")

    hp = data.get("hp", {})
    hp_max = hp.get("max")
    hp_cur = hp.get("current")
    if not _is_int(hp_max) or not _is_int(hp_cur) or not (0 <= hp_cur <= hp_max):
        problems.append(f"hp 不合理：current={hp_cur!r} max={hp_max!r}")
    hp_temp = hp.get("temp", 0)
    if not _is_int(hp_temp) or hp_temp < 0:
        problems.append(f"hp.temp 不能为负：{hp_temp!r}")

    slots = (data.get("spellcasting") or {}).get("slots", {})
    for ring, slot in slots.items():
        used = slot.get("used", 0) if isinstance(slot, dict) else None
        mx = slot.get("max", 0) if isinstance(slot, dict) else None
        if not _is_int(used) or not _is_int(mx) or used > mx:
            problems.append(f"法术位 {ring} 已用超过上限：used={used!r} max={mx!r}")

    for ab in data.get("save_profs", []):
        if ab not in ABILITIES:
            problems.append(f"save_profs 含未知属性：{ab}")

    profs = data.get("skill_profs", [])
    for sk in profs:
        if sk not in SKILL_ABILITIES:
            problems.append(f"skill_profs 含未知技能：{sk}")
    for sk in data.get("skill_expertise", []):
        if sk not in SKILL_ABILITIES:
            problems.append(f"skill_expertise 含未知技能：{sk}")
        elif sk not in profs:
            problems.append(f"专精技能未在熟练列表中：{sk}")

    ds = data.get("death_saves", {})
    for key in ("successes", "failures"):
        val = ds.get(key, 0)
        if not _is_int(val) or not (0 <= val <= 3):
            problems.append(f"death_saves.{key} 超出 0..3：{val!r}")

    ac = data.get("ac", {})
    for key in ("base", "temp"):
        val = ac.get(key, 0)
        if not _is_int(val):
            problems.append(f"ac.{key} 必须是整数：{val!r}")

    return problems


_ABILITY_LABELS = [
    ("str", "力量"),
    ("dex", "敏捷"),
    ("con", "体质"),
    ("int", "智力"),
    ("wis", "感知"),
    ("cha", "魅力"),
]


def _mod_of(data: dict, ability: str) -> int:
    abilities = data.get("abilities") or {}
    return ability_modifier(abilities.get(ability, 10))


def _ability_label(ability: str) -> str:
    for key, label in _ABILITY_LABELS:
        if key == ability:
            return label
    return ability


def render_markdown(data: dict) -> str:
    name = data.get("name", "未命名")
    lines = [f"# {name}"]

    classes = data.get("classes") or []
    cls_txt = "、".join(
        f"{c.get('name', '?')} {c.get('level', '?')} 级"
        + (f"（{c['subclass']}）" if c.get("subclass") else "")
        for c in classes
    )
    info = [x for x in [cls_txt, data.get("race"), data.get("alignment")] if x]
    if info:
        lines += ["", "> " + " ｜ ".join(info)]

    abilities = data.get("abilities") or {}
    lines += ["", "## 属性"]
    for key, label in _ABILITY_LABELS:
        score = abilities.get(key, 10)
        lines.append(f"- {label}: {score}（{ability_modifier(score):+d}）")

    ac = data.get("ac") or {}
    hp = data.get("hp") or {}
    lines += ["", "## 战斗"]
    lines.append(f"- AC: {ac.get('base', 10) + ac.get('temp', 0)}")
    if data.get("speed") is not None:
        lines.append(f"- 速度: {data['speed']} 尺")
    try:
        init_mod = initiative_bonus(data)
    except (KeyError, TypeError):
        init_mod = _mod_of(data, "dex")
    lines.append(f"- 先攻: {init_mod:+d}")
    hp_line = f"- HP: {hp.get('current', 0)}/{hp.get('max', 0)}"
    if hp.get("temp"):
        hp_line += f"（临时 +{hp['temp']}）"
    lines.append(hp_line)

    ds = data.get("death_saves") or {}
    lines.append(f"- 死亡豁免: 成功 {ds.get('successes', 0)} / 失败 {ds.get('failures', 0)}")

    save_profs = data.get("save_profs") or []
    skill_profs = data.get("skill_profs") or []
    expertise = data.get("skill_expertise") or []
    lines += ["", "## 熟练与施法"]
    lines.append(
        "- 豁免熟练: " + ("、".join(_ability_label(a) for a in save_profs) if save_profs else "无")
    )
    lines.append("- 技能熟练: " + ("、".join(skill_profs) if skill_profs else "无"))
    lines.append("- 技能专精: " + ("、".join(expertise) if expertise else "无"))
    tool_profs = data.get("tool_profs") or []
    weapon_profs = data.get("weapon_profs") or []
    lines.append("- 工具熟练: " + ("、".join(tool_profs) if tool_profs else "无"))
    lines.append("- 武器熟练: " + ("、".join(weapon_profs) if weapon_profs else "无"))
    try:
        lines.append(f"- 被动感知: {passive_perception(data)}")
    except Exception:
        pass

    sc = data.get("spellcasting") or {}
    if sc.get("ability"):
        try:
            lines.append(f"- 法术 DC: {spell_dc(data)}")
            lines.append(f"- 法术攻击: {spell_attack_bonus(data):+d}")
        except Exception:
            pass
        slots = sc.get("slots") or {}
        if slots:
            parts = [f"{ring} 环 {v.get('used', 0)}/{v.get('max', 0)}" for ring, v in slots.items()]
            lines.append("- 法术位: " + "、".join(parts))
        if sc.get("concentration"):
            lines.append(f"- 专注: {sc['concentration']}")

    attacks = data.get("attacks") or []
    if attacks:
        lines += ["", "## 攻击"]
        for atk in attacks:
            row = f"- {atk.get('name', '?')}: {atk.get('bonus', '')} {atk.get('damage', '')} {atk.get('damage_type', '')}"
            lines.append(row.rstrip())

    conditions = data.get("conditions") or []
    lines += ["", "## 状态"]
    lines.append("- 状态: " + ("、".join(conditions) if conditions else "无"))

    features = data.get("features") or []
    if features:
        lines += ["", "## 特性"]
        lines += [f"- {f}" for f in features]

    languages = data.get("languages") or []
    if languages:
        lines += ["", "## 语言"]
        lines.append("- " + "、".join(languages))

    personality = data.get("personality") or {}
    if any(personality.get(k) for k in ("traits", "ideals", "bonds", "flaws")):
        lines += ["", "## 人格"]
        for label, key in (("特质", "traits"), ("理想", "ideals"), ("羁绊", "bonds"), ("缺陷", "flaws")):
            for value in personality.get(key) or []:
                lines.append(f"- {label}: {value}")

    inv = data.get("inventory") or []
    lines += ["", "## 物品与金钱"]
    if inv:
        for item in inv:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name', '?')} ×{item.get('qty', 1)}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- 物品: 无")
    lines.append(f"- 金钱: {data.get('gold', 0)} gp")

    if data.get("notes"):
        lines += ["", "## 备注", str(data["notes"])]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


class _ZhArgumentParser(argparse.ArgumentParser):
    def error(self, message):  # noqa: ARG002
        print("错误：参数无效，请检查输入（可用 -h 查看帮助）", file=sys.stderr)
        raise SystemExit(2)


def _number_arg(text: str):
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"不是有效数值：{text}")


def build_parser() -> argparse.ArgumentParser:
    parser = _ZhArgumentParser(prog="sheet.py", description="D&D 5e 角色卡管理")
    parser.add_argument("--dir", default=None, help="角色卡存储目录")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="列出全部角色卡")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("new", help="创建角色卡")
    p.add_argument("name")
    p.add_argument("--from", dest="from_name", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("show", help="显示角色卡")
    p.add_argument("name")
    p.add_argument("--md", action="store_true")
    p.add_argument("--write", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("get", help="读取一个字段")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("set", help="设置一个字段")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("value")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("add", help="给数值字段加/减")
    p.add_argument("name")
    p.add_argument("path")
    p.add_argument("delta", type=_number_arg)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("hp", help="变更当前 HP")
    p.add_argument("name")
    p.add_argument("delta", type=int)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("hp-set", help="设置当前 HP")
    p.add_argument("name")
    p.add_argument("value", type=int)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("hp-max", help="设置 HP 上限")
    p.add_argument("name")
    p.add_argument("value", type=int)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("slot", help="消耗/恢复法术位")
    p.add_argument("name")
    p.add_argument("ring")
    p.add_argument("n", type=int)
    p.add_argument("--restore", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("ac", help="调整护甲等级")
    p.add_argument("name")
    p.add_argument("op")
    p.add_argument("value", nargs="?", type=int, default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("cond", help="添加/移除状态")
    p.add_argument("name")
    p.add_argument("action", choices=["add", "remove"])
    p.add_argument("condition")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("death", help="死亡豁免")
    p.add_argument("name")
    p.add_argument("kind", choices=["success", "failure", "reset"])
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check", help="查询技能加值")
    p.add_argument("name")
    p.add_argument("skill")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("save", help="查询豁免加值")
    p.add_argument("name")
    p.add_argument("ability")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("validate", help="校验角色卡")
    p.add_argument("name")
    p.add_argument("--json", action="store_true")

    return parser


def _print_scalar(value) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False))


def _emit(args, message, payload=None) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload if payload is not None else {"message": message},
                         ensure_ascii=False))
    else:
        print(message)


def main(argv=None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    if not command:
        parser.print_help()
        return 2
    cli_dir = args.dir
    try:
        if command == "list":
            sheets = list_sheets(cli_dir)
            if args.json:
                print(json.dumps(sheets, ensure_ascii=False, indent=2))
            elif sheets:
                for s in sheets:
                    print(f"{s['name']}  等级 {s['level']}  HP {s['hp_current']}/{s['hp_max']}")
            else:
                print("（没有角色卡）")
            return 0

        if command == "new":
            new_sheet(args.name, from_name=args.from_name, cli_dir=cli_dir)
            _emit(args, f"已创建角色卡：{args.name}", {"name": args.name})
            return 0

        if command == "show":
            data = load_sheet(args.name, cli_dir)
            if args.md:
                md = render_markdown(data)
                if args.write:
                    path = sheet_path(args.name, cli_dir).with_suffix(".md")
                    path.write_text(md, encoding="utf-8")
                    _emit(args, f"已写出 Markdown：{path}", {"path": str(path)})
                else:
                    print(md)
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0

        if command == "get":
            data = load_sheet(args.name, cli_dir)
            _print_scalar(get_path(data, args.path))
            return 0

        if command == "set":
            data = load_sheet(args.name, cli_dir)
            try:
                value = json.loads(args.value)
            except json.JSONDecodeError:
                value = args.value
            set_path(data, args.path, value)
            save_sheet(args.name, data, cli_dir)
            _emit(args, f"已设置 {args.path} = {value}")
            return 0

        if command == "add":
            data = load_sheet(args.name, cli_dir)
            msg = add_path(data, args.path, args.delta)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg)
            return 0

        if command == "hp":
            data = load_sheet(args.name, cli_dir)
            msg = apply_hp(data, args.delta)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg, {"hp": data["hp"], "message": msg})
            return 0

        if command == "hp-set":
            data = load_sheet(args.name, cli_dir)
            set_hp(data, args.value)
            save_sheet(args.name, data, cli_dir)
            _emit(args, f"当前 HP 设为 {data['hp']['current']}", {"hp": data["hp"]})
            return 0

        if command == "hp-max":
            data = load_sheet(args.name, cli_dir)
            set_hp_max(data, args.value)
            save_sheet(args.name, data, cli_dir)
            _emit(args, f"HP 上限设为 {data['hp']['max']}", {"hp": data["hp"]})
            return 0

        if command == "slot":
            data = load_sheet(args.name, cli_dir)
            msg = use_slot(data, args.ring, args.n, restore=args.restore)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg, {"slots": data["spellcasting"]["slots"], "message": msg})
            return 0

        if command == "ac":
            data = load_sheet(args.name, cli_dir)
            msg = modify_ac(data, args.op, args.value)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg, {"ac": data["ac"], "message": msg})
            return 0

        if command == "cond":
            data = load_sheet(args.name, cli_dir)
            if args.action == "add":
                msg = cond_add(data, args.condition)
            else:
                msg = cond_remove(data, args.condition)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg, {"conditions": data["conditions"], "message": msg})
            return 0

        if command == "death":
            data = load_sheet(args.name, cli_dir)
            msg = death_save(data, args.kind)
            save_sheet(args.name, data, cli_dir)
            _emit(args, msg, {"death_saves": data["death_saves"], "message": msg})
            return 0

        if command == "check":
            data = load_sheet(args.name, cli_dir)
            _print_scalar(check_bonus(data, args.skill))
            return 0

        if command == "save":
            data = load_sheet(args.name, cli_dir)
            _print_scalar(save_bonus_value(data, args.ability))
            return 0

        if command == "validate":
            data = load_sheet(args.name, cli_dir)
            issues = validate_sheet(data)
            if args.json:
                print(json.dumps(issues, ensure_ascii=False, indent=2))
            if issues:
                for issue in issues:
                    print(f"校验问题：{issue}", file=sys.stderr)
                return 2
            if not args.json:
                print("校验通过")
            return 0
    except SheetError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
