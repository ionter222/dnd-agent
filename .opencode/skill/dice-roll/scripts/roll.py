"""dice-roll：DNDagent 的骰子判定引擎（零第三方依赖，Python 3.10+）。"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass

MAX_COUNT = 1000
MAX_SIDES = 1000
MAX_REPEAT = 1000
MAX_BONUS = 100

_TERM_RE = re.compile(r"^(\d*)d(\d+)(kh|kl|dh|dl)?(\d*)$", re.IGNORECASE)


@dataclass
class DiceTerm:
    count: int
    sides: int
    keep_high: int | None = None
    keep_low: int | None = None
    drop_high: int | None = None
    drop_low: int | None = None
    operator: int = 1


@dataclass
class ConstTerm:
    value: int
    operator: int = 1


def _parse_term(token: str) -> "DiceTerm | ConstTerm":
    token = token.strip()
    if token == "":
        raise ValueError(f"无法解析的骰式: {token!r}")
    if re.fullmatch(r"\d+", token):
        return ConstTerm(int(token))
    m = _TERM_RE.match(token)
    if not m:
        raise ValueError(f"无法解析的骰式: {token!r}")
    count_s, sides_s, keep_drop, kd_n = m.groups()
    count = int(count_s) if count_s else 1
    sides = int(sides_s)
    if not (1 <= count <= MAX_COUNT) or not (1 <= sides <= MAX_SIDES):
        raise ValueError(
            f"骰子数量/面数超出范围(1..{MAX_COUNT}): {token!r}"
        )
    term = DiceTerm(count=count, sides=sides)
    if keep_drop:
        n = int(kd_n) if kd_n else 1
        if n < 1 or n > count:
            raise ValueError(f"保留/丢弃数量非法: {token!r}")
        if keep_drop.lower() == "kh":
            term.keep_high = n
        elif keep_drop.lower() == "kl":
            term.keep_low = n
        elif keep_drop.lower() == "dh":
            term.drop_high = n
        else:
            term.drop_low = n
    return term


def parse_expression(expr: str) -> list[object]:
    expr = expr.strip()
    if not expr:
        raise ValueError("无法解析的骰式: ''")
    parts = re.split(r"([+-])", expr)
    terms: list[object] = []
    sign = 1
    for i, part in enumerate(parts):
        if i % 2 == 1:
            sign = 1 if part == "+" else -1
            continue
        term = _parse_term(part)
        term.operator = sign
        terms.append(term)
    if not terms:
        raise ValueError(f"无法解析的骰式: {expr!r}")
    return terms


@dataclass
class TermResult:
    operator: int
    detail: str
    subtotal: int
    rolls: list[int]
    kept: list[int] | None = None
    sides: int | None = None
    count: int | None = None
    mode: str = "normal"


@dataclass
class RollResult:
    label: str | None
    expression: str
    terms: list[TermResult]
    modifier: int
    total: int
    advantage: str | None = None
    coc: dict | None = None
    check: dict | None = None
    secret: bool = False


def _keep_set(term: DiceTerm, rolls: list[int]) -> list[int]:
    if term.keep_high is not None:
        return sorted(rolls, reverse=True)[:term.keep_high]
    if term.keep_low is not None:
        return sorted(rolls)[:term.keep_low]
    if term.drop_high is not None:
        return sorted(rolls)[:term.count - term.drop_high]
    if term.drop_low is not None:
        return sorted(rolls, reverse=True)[:term.count - term.drop_low]
    return list(rolls)


def roll_terms(
    terms,
    rng,
    *,
    label=None,
    advantage=None,
    coc=None,
    check=None,
    secret=False,
) -> RollResult:
    adv_term = None
    if advantage is not None:
        dice_terms = [t for t in terms if isinstance(t, DiceTerm)]
        if len(dice_terms) != 1 or dice_terms[0].sides != 20 or dice_terms[0].count != 1:
            raise ValueError("优势/劣势仅适用于单个 d20 检定")
        adv_term = dice_terms[0]

    results: list[TermResult] = []
    total = 0
    modifier = 0
    for term in terms:
        if isinstance(term, ConstTerm):
            sub = term.operator * term.value
            modifier += sub
            total += sub
            results.append(TermResult(term.operator, str(term.value), sub, []))
        elif term is adv_term:
            rolls = [rng.randint(1, 20), rng.randint(1, 20)]
            chosen = max(rolls) if advantage == "advantage" else min(rolls)
            sub = term.operator * chosen
            total += sub
            detail = f"1d20({rolls[0]},{rolls[1]}→{chosen})"
            results.append(TermResult(term.operator, detail, sub, rolls,
                                      kept=[chosen], sides=20, count=2,
                                      mode=advantage))
        else:
            rolls = [rng.randint(1, term.sides) for _ in range(term.count)]
            kept = _keep_set(term, rolls)
            sub = term.operator * sum(kept)
            total += sub
            body = "+".join(str(x) for x in kept)
            detail = f"{term.count}d{term.sides}({body}={sum(kept)})"
            mode = "normal"
            if term.keep_high is not None:
                mode = "kh"
            elif term.keep_low is not None:
                mode = "kl"
            elif term.drop_high is not None:
                mode = "dh"
            elif term.drop_low is not None:
                mode = "dl"
            results.append(TermResult(term.operator, detail, sub, rolls,
                                      kept=kept, sides=term.sides,
                                      count=term.count, mode=mode))
    return RollResult(
        label=label,
        expression="",
        terms=results,
        modifier=modifier,
        total=total,
        advantage=advantage,
        coc=coc,
        check=check,
        secret=secret,
    )


def roll_d100_coc(rng, bonus: int = 0, penalty: int = 0) -> dict:
    """CoC 7e 的 d100 奖励骰/惩罚骰。先抽单位骰，再抽 1+abs(net) 颗十位骰。"""
    net = bonus - penalty
    n_tens = 1 + abs(net)
    units = rng.randint(0, 9)
    tens_digits = [rng.randint(0, 9) for _ in range(n_tens)]
    tens = [d * 10 for d in tens_digits]

    def value_of(tens_digit: int) -> int:
        if tens_digit == 0 and units == 0:
            return 100
        return tens_digit * 10 + units

    candidates = [value_of(d) for d in tens_digits]
    if net > 0:
        value = min(candidates)
    elif net < 0:
        value = max(candidates)
    else:
        value = candidates[0]
    used_digit = tens_digits[candidates.index(value)]
    return {
        "bonus": bonus,
        "penalty": penalty,
        "net": net,
        "units": units,
        "tens": tens,
        "used": used_digit * 10,
        "value": value,
    }


def dnd5e_success(total: int, dc: int) -> bool:
    """D&D 5e 检定：总值达到或超过 DC 即成功。"""
    return total >= dc


def coc_success_level(roll: int, skill: int) -> str:
    """CoC 7e 成功等级：critical/extreme/hard/regular/fail/fumble。"""
    if roll == 1:
        return "critical"
    if roll <= skill // 5:
        return "extreme"
    if roll <= skill // 2:
        return "hard"
    if roll == 100 or (skill < 50 and roll >= 96):
        return "fumble"
    if roll <= skill:
        return "regular"
    return "fail"


_LEVEL_ZH = {
    "critical": "大成功",
    "extreme": "极难成功",
    "hard": "困难成功",
    "regular": "常规成功",
    "fail": "失败",
    "fumble": "大失败",
}

_SUCCESS_LEVELS = {"critical", "extreme", "hard", "regular"}


def _check_suffix(check) -> str:
    if not check:
        return ""
    if "dc" in check:
        verdict = "成功" if check.get("success") else "失败"
        return f" vs DC{check['dc']} → {verdict}"
    if "skill" in check:
        level = check.get("level")
        return f" vs 技能值{check['skill']} → {_LEVEL_ZH.get(level, level)}"
    return ""


def render_text(result) -> str:
    label = f"[{result.label}] " if result.label else ""
    chunks = []
    for i, tr in enumerate(result.terms):
        sign = "+" if tr.operator >= 0 else "-"
        if i == 0 and tr.operator >= 0:
            chunks.append(tr.detail)
        else:
            chunks.append(sign + tr.detail)
    body = " ".join(chunks) if chunks else "-"
    line = f"{label}{body} = {result.total}{_check_suffix(result.check)}"
    if result.secret:
        player_label = f"[{result.label}] " if result.label else ""
        return line + "\n" + f"{player_label}已暗投（仅 DM 可见）"
    return line


def render_json(result) -> dict:
    modifier_detail = "".join(
        f"{'+' if tr.operator >= 0 else '-'}{abs(tr.subtotal)}"
        for tr in result.terms
        if not tr.rolls
    )
    data = {
        "label": result.label,
        "expression": result.expression,
        "modifier": result.modifier,
        "dice": [
            {
                "type": f"d{tr.sides}",
                "count": tr.count,
                "results": list(tr.rolls),
                "kept": list(tr.kept if tr.kept is not None else tr.rolls),
                "mode": tr.mode,
                "operator": tr.operator,
                "subtotal": tr.subtotal,
                "detail": tr.detail,
            }
            for tr in result.terms
            if tr.rolls
        ],
        "modifier_detail": modifier_detail,
        "total": result.total,
        "advantage": result.advantage,
        "bonus_penalty": result.coc,
        "check": result.check,
        "secret": result.secret,
    }
    if result.secret:
        data["player_view"] = {
            "label": result.label,
            "message": "已暗投（仅 DM 可见）",
        }
    return data


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


class _ZhArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("错误：参数无效，请检查输入（可用 -h 查看帮助）", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _ZhArgumentParser(
        prog="roll.py",
        description="dice-roll：DNDagent 的骰子判定引擎（支持 5e 优势/劣势、CoC 奖励/惩罚骰、暗骰）",
    )
    parser.add_argument("expression", help="骰式，如 2d6+3、1d20+5、4d6dl1")
    parser.add_argument("--adv", action="store_true", help="优势（单个 d20 掷两颗取高）")
    parser.add_argument("--dis", action="store_true", help="劣势（单个 d20 掷两颗取低）")
    parser.add_argument("--bonus", type=int, default=0, help="CoC 奖励骰数量")
    parser.add_argument("--penalty", type=int, default=0, help="CoC 惩罚骰数量")
    parser.add_argument("--dc", type=int, default=None, help="D&D 5e 检定 DC")
    parser.add_argument("--skill", type=int, default=None, help="CoC 技能值")
    parser.add_argument("--system", choices=["dnd5e", "coc7e"], default=None,
                        help="规则系统（缺省按 --skill/--dc 推断）")
    parser.add_argument("--secret", action="store_true", help="暗骰（玩家视图隐藏数字）")
    parser.add_argument("--label", default=None, help="本次判定的标签，如 力量豁免")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（仅供调试复现）")
    parser.add_argument("--count", type=int, default=1, help="投掷次数")
    return parser


def main(argv=None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not (1 <= args.count <= MAX_REPEAT):
            raise ValueError(f"--count 必须在 1..{MAX_REPEAT} 之间")
        if not (0 <= args.bonus <= MAX_BONUS):
            raise ValueError(f"--bonus 必须在 0..{MAX_BONUS} 之间")
        if not (0 <= args.penalty <= MAX_BONUS):
            raise ValueError(f"--penalty 必须在 0..{MAX_BONUS} 之间")
        if args.dc is not None and args.skill is not None:
            raise ValueError("--dc 与 --skill 不能同时使用（5e 与 CoC 互斥）")
        if args.system == "dnd5e" and args.skill is not None:
            raise ValueError("--system dnd5e 不能与 --skill 同时使用")
        if args.system == "coc7e" and args.dc is not None:
            raise ValueError("--system coc7e 不能与 --dc 同时使用")

        rng = random.Random(args.seed) if args.seed is not None else random.Random()

        system = args.system
        if system is None:
            if args.skill is not None:
                system = "coc7e"
            elif args.dc is not None:
                system = "dnd5e"
            elif args.bonus or args.penalty:
                system = "coc7e"

        advantage = None
        adv_dis_note = None
        if args.adv and args.dis:
            adv_dis_note = "优势与劣势抵消，按普通检定"
        elif args.adv:
            advantage = "advantage"
        elif args.dis:
            advantage = "disadvantage"

        results = []
        for _ in range(args.count):
            terms = parse_expression(args.expression)
            is_d100 = (
                len(terms) == 1
                and isinstance(terms[0], DiceTerm)
                and terms[0].sides == 100
                and terms[0].count == 1
                and terms[0].operator == 1
            )
            coc = None
            check = None
            if system == "coc7e" and is_d100:
                coc = roll_d100_coc(rng, args.bonus, args.penalty)
                if coc["net"] > 0:
                    mode = "bonus"
                elif coc["net"] < 0:
                    mode = "penalty"
                else:
                    mode = "normal"
                value = coc["value"]
                tr = TermResult(1, f"1d100({value})", value, [value], [value],
                                100, 1, mode)
                result = RollResult(label=args.label, expression=args.expression,
                                    terms=[tr], modifier=0, total=value,
                                    advantage=advantage, coc=coc, check=None,
                                    secret=args.secret)
                if args.skill is not None:
                    level = coc_success_level(value, args.skill)
                    check = {"system": "coc7e", "skill": args.skill, "roll": value,
                             "level": level, "success": level in _SUCCESS_LEVELS,
                             "bonus_penalty": coc}
            else:
                if system == "coc7e":
                    print("警告：CoC 检定需要单个 d100，已按 d100 语义处理",
                          file=sys.stderr)
                    if args.bonus or args.penalty:
                        print("警告：奖励/惩罚骰仅适用于 d100，已忽略",
                              file=sys.stderr)
                result = roll_terms(terms, rng, label=args.label,
                                    advantage=advantage, coc=None, check=None,
                                    secret=args.secret)
                result.expression = args.expression
                if system == "coc7e" and args.skill is not None:
                    level = coc_success_level(result.total, args.skill)
                    check = {"system": "coc7e", "skill": args.skill,
                             "roll": result.total, "level": level,
                             "success": level in _SUCCESS_LEVELS,
                             "bonus_penalty": None}
                if args.dc is not None:
                    check = {"system": "dnd5e", "dc": args.dc,
                             "success": dnd5e_success(result.total, args.dc)}
            result.check = check
            results.append(result)

        if args.json:
            payload = render_json(results[0]) if args.count == 1 else [render_json(r) for r in results]
            print(json.dumps(payload, ensure_ascii=False))
        else:
            for i, r in enumerate(results):
                print(render_text(r))
                if adv_dis_note and i == 0:
                    print(adv_dis_note)
                print(json.dumps(render_json(r), ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
