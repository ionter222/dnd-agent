---
name: character-sheet
description: D&D 5e 角色卡管理。建卡、查看/读写字段、扣血与治疗、法术位消耗、AC 调整、状态增减、死亡豁免、技能/豁免加值查询、校验、导出 Markdown。触发词：角色卡、建卡、HP、血量、法术位、AC、护甲等级、状态、死亡豁免、熟练加值、调整值、被动感知、法术DC。
---

# 角色卡管理（character-sheet）

角色卡的**唯一事实源是一份 JSON**（`角色卡_CharacterSheets/<名>.json`）。任何 HP、法术位、AC、状态的变化都必须通过 `scripts/sheet.py` 落盘——不要只在对话里记，也不要手改文件。派生值（熟练、调整值、加值、DC 等）由脚本现算，不写进 JSON。

## 何时使用

- 建卡 / 查卡 / 改卡 / 升级调整。
- 战斗或剧情导致 HP、法术位、AC、状态、死亡豁免变化。
- 需要某个技能或豁免的加值（把结果交给 dice-roll skill 掷骰）。
- 会话前校验角色卡、导出可读的 Markdown。

## 命令

| 命令 | 说明 |
|---|---|
| `list` | 列出全部角色卡 |
| `new <名> [--from <模板>]` | 建卡（可复制已有卡作模板） |
| `show <名> [--md] [--write]` | 显示（默认 JSON；`--md` 输出 Markdown，`--write` 落 `<名>.md`） |
| `get <名> <路径>` | 读一个字段（如 `hp.current`） |
| `set <名> <路径> <值>` | 写一个字段 |
| `add <名> <路径> <增量>` | 数值字段加减 |
| `hp <名> <增量>` | 变更当前 HP（负数受伤、正数治疗） |
| `hp-set <名> <值>` / `hp-max <名> <值>` | 设置当前 / 上限 HP |
| `slot <名> <环> <数量> [--restore]` | 消耗（或恢复）法术位 |
| `ac <名> <+|-|set|reset> [值]` | 调整护甲等级（如法术「护盾术」`ac 薇拉 +5`） |
| `cond <名> <add|remove> <状态>` | 增减状态 |
| `death <名> <success|failure|reset>` | 死亡豁免 |
| `check <名> <技能>` | 查询技能加值 |
| `save <名> <属性>` | 查询豁免加值 |
| `validate <名>` | 校验角色卡 |

所有命令可加 `--json` 取机器可读输出；顶层 `--dir` 指定角色卡目录。

示例（与 dice-roll 联动）：

```bash
python .opencode/skill/character-sheet/scripts/sheet.py check 薇拉 奥秘
# → 6，再交给掷骰引擎
python .opencode/skill/dice-roll/scripts/roll.py "1d20+6" --dc 15 --label "奥秘检定"
```

## 建卡流程

**A. 从人设建 PC / NPC**

1. `new <名>` 建骨架（或 `new <名> --from <模板>` 复制一份）。
2. 身份：`set <名> race 人类`、`set <名> classes '[{"name":"法师","level":2,"subclass":"塑能学派"}]'`、`background`、`alignment`。
3. 属性：`set <名> abilities '{"str":8,"dex":10,"con":13,"int":16,"wis":10,"cha":16}'`（标准 5e 购点 27 点、8–15，种族加值后再落）。
4. 熟练：`set <名> save_profs '["int","wis"]'`、`skill_profs`、`skill_expertise`、`weapon_profs`、`tool_profs`。
5. 战斗数值：`hp-max <名> 12`、`set <名> hit_dice '{"die":"d6","total":2,"used":0}'`、`speed`、`set <名> ac '{"base":10,"temp":0}'`。
6. 法术：`set <名> spellcasting '{"ability":"int","slots":{"1":{"max":3,"used":0}},"spells":["火焰箭"],"concentration":null}'`。
7. 攻击：`set <名> attacks '[{"name":"匕首","bonus":2,"damage":"1d4","damage_type":"穿刺","range":"近战"}]'`。
8. 其余：`features` / `languages` / `personality` / `inventory` / `gold` / `notes`。
9. `validate <名>` 通过后 `show <名> --md --write` 出视图。

**B. 从怪物 statblock 建怪物卡**（敌我同构，怪物也是角色卡）

映射见 `reference/schema.md` 的「怪物 statblock → 字段映射」。

**通用**：所有 `set` 的值按 JSON 解析（失败当字符串）；不确定的数值（等级/法术位/装备）先问玩家，绝不臆造。

## 铁律

1. **唯一事实源**：角色卡 JSON 是权威。先 `show`/`get` 读，改完由脚本写回；绝不凭空臆造数值。
2. **资源变化必落盘**：受伤、施法、状态、死亡豁免都要用本 skill 更新，不能只停留在叙述里。
3. **掷骰交给 dice-roll**：本 skill 只给加值/DC，随机结果一律用 `dice-roll` skill 产生。
4. **不确定就问玩家**：角色卡里没有的信息（等级、法术位、装备）必须问，不得替玩家假设。
5. **出错就报错**：非法输入/未知路径/校验失败会以非零码退出并给中文提示，遇到就修正。

## 文件

- 实现：`scripts/sheet.py`（仅 Python 标准库，Python 3.10+）
- 字段与公式：`reference/schema.md`
