---
name: dice-roll
description: 骰子判定引擎。跑团/TRPG 需要任何随机结果时使用——常规掷骰、D&D 5e 优势/劣势、CoC 7e 奖励骰/惩罚骰、暗骰，以及给定技能值/DC 的成败判定。触发词：掷骰、骰子、检定、判定、d20、d100、优势、劣势、奖励骰、惩罚骰、暗骰、先攻。
---

# 骰子判定（dice-roll）

所有随机结果都必须由 `scripts/roll.py` 产生。**绝不臆造骰值，绝不用脑内随机**——骰子必须可复核。DC 与技能值由 DM 依情境裁定，脚本只负责掷与判。

## 快速开始

```bash
python .opencode/skill/dice-roll/scripts/roll.py "1d20+5" --dc 15 --label "力量豁免"
python .opencode/skill/dice-roll/scripts/roll.py "2d20kh1" --dc 15 --label "攻击（优势）"
python .opencode/skill/dice-roll/scripts/roll.py "1d100" --skill 55 --system coc7e --bonus 1 --label "图书馆使用"
python .opencode/skill/dice-roll/scripts/roll.py "1d20" --secret --label "NPC 暗中侦查"
```

## 表达式语法

`表达式 := 项 (('+'|'-') 项)*`，项为 `数量?d面数 修正?` 或一个整数。

| 写法 | 含义 |
|---|---|
| `1d20` / `d20` | 一颗 20 面骰（`数量` 缺省为 1） |
| `2d6+3` | 两颗 d6 之和加 3 |
| `1d20-1` | 支持负修正 |
| `4d6dl1` | 掷 4 颗 d6，去掉最低 1 颗（`dl`=drop lowest） |
| `2d20kh1` | 掷 2 颗 d20，取最高 1 颗（`kh`=keep highest） |
| `4d6dh1` | 去掉最高 1 颗；`kl` = 保留最低 n 颗 |

修正关键字：`kh`/`kl`/`dh`/`dl`，后面跟数量 `n`（缺省 1，须 ≤ 骰数）。

## 命令行选项

| 选项 | 说明 |
|---|---|
| `--adv` / `--dis` | D&D 5e 优势 / 劣势（仅对单个 `d20` 检定生效，掷两颗取高/取低）。两者同给则互相抵消，按单骰处理 |
| `--bonus N` / `--penalty N` | CoC 7e 奖励骰 / 惩罚骰（十位骰取低 / 取高）；同给则抵消，多个可叠加 |
| `--dc N` | D&D 5e 难度，脚本据此判定成功/失败 |
| `--skill N` | CoC 7e 技能值，脚本据此给出成功等级 |
| `--system dnd5e\|coc7e` | 判定体系；缺省时由 `--skill`→coc7e、`--dc`→dnd5e 推断 |
| `--secret` | 暗骰：玩家视图不含任何数字 |
| `--label TEXT` | 给这次检定起个名字（如「潜行」） |
| `--json` | 只输出 JSON（默认输出「文本 + 一行 JSON」） |
| `--count N` | 重复掷 N 次 |
| `--seed N` | 固定随机种子，仅用于调试复现 |

## 判定规则

- **D&D 5e**：`总值 ≥ DC` 即成功。DC 参考（详见 `reference/rules.md`）：5 极易 / 10 易 / 15 中 / 20 难 / 25 很难 / 30 近乎不可能。
- **CoC 7e**：按 d100 结果分等级——大成功(01) / 极难(≤ 技能值÷5) / 困难(≤ 技能值÷2) / 常规(≤ 技能值) / 失败 / 大失败(100，或技能值<50 时 96–100)。详见 `reference/rules.md`。

## 铁律

1. **一切随机走脚本**：任何掷骰都必须运行 `scripts/roll.py`，把真实输出写进叙述，不得编造数值。
2. **DC / 技能值由 DM 定**：脚本不替你决定难度，你依剧情与规则给值，再交给脚本。
3. **暗骰不泄底**：`--secret` 的结果只用 DM 视图，玩家侧绝不出现数字。
4. **出错就报错**：非法表达式会让脚本以非零码退出并给出中文提示，遇到就修正，不要忽略。

## 文件

- 实现：`scripts/roll.py`（仅 Python 标准库，Python 3.10+）
- 规则附录：`reference/rules.md`
