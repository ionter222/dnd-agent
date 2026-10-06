# 角色卡 schema 与派生值

角色卡以 JSON 存储（UTF-8），`schema_version` 当前为 `1`。派生值一律现算，不写进文件。

## 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int | 数据格式版本，必填 |
| `name` | str | 角色名 |
| `player` | str | 玩家 |
| `race` | str | 种族 |
| `classes` | list | `[{name, level, subclass}]`，总等级 = Σ level |
| `background` / `alignment` | str | 背景 / 阵营 |
| `xp` | int | 经验值 |
| `abilities` | dict | 六属性原始值：`str/dex/con/int/wis/cha`，各 1..30 |
| `save_profs` | list | 有豁免熟练的属性 |
| `skill_profs` | list | 有技能熟练的技能 |
| `skill_expertise` | list | 有专精的技能（须同时熟练） |
| `ac` | dict | `{base, temp}`，有效 AC = base + temp |
| `hp` | dict | `{max, current, temp}` |
| `hit_dice` | dict | `{die, total, used}` |
| `speed` | int | 速度（尺） |
| `initiative_bonus` | int \| null | 先攻额外加值；null 时用敏捷调整值 |
| `spellcasting` | dict | `{ability, slots{环:{max,used}}, spells[], concentration}` |
| `attacks` | list | `[{name, bonus, damage, damage_type, range}]` |
| `features` / `inventory` | list | 特性 / 物品 `[{name, qty}]` |
| `conditions` | list | 当前状态 |
| `death_saves` | dict | `{successes, failures}`，各 0..3 |
| `gold` | int | 金钱 |
| `notes` | str | 备注 |

## 派生值公式

- **调整值**：`⌊(属性值 − 10) ÷ 2⌋`（向下取整；8 → −1，9 → −1，10 → 0）。
- **总等级**：Σ 各职业 `level`。
- **熟练加值**：`2 + ⌊(总等级 − 1) ÷ 4⌋`。
- **豁免加值**：属性调整值 +（该属性在 `save_profs` 则加熟练加值）。
- **技能加值**：属性调整值 +（技能熟练 +熟练加值）+（技能专精再加一次熟练加值）。
- **被动感知**：`10 + 察觉技能加值`。
- **法术 DC**：`8 + 熟练加值 + 施法属性调整值`。
- **法术攻击加值**：`熟练加值 + 施法属性调整值`。
- **AC（有效）**：`ac.base + ac.temp`。
- **先攻**：`initiative_bonus`；若为 null，则用敏捷调整值。

## 18 项技能 → 属性映射

| 属性 | 技能 |
|---|---|
| 力量 str | 运动 |
| 敏捷 dex | 杂技、巧手、隐匿 |
| 体质 con | （无） |
| 智力 int | 奥秘、历史、调查、自然、宗教 |
| 感知 wis | 驯兽、洞悉、医药、察觉、生存 |
| 魅力 cha | 欺瞒、威吓、表演、说服 |

## 怪物 statblock → 字段映射

怪物与 PC/NPC 同构，同样是一张角色卡。5e 怪物书 statblock 的映射：

| statblock 项 | 卡字段 |
|---|---|
| 护甲等级 Armor Class | `ac.base` |
| 生命值 Hit Points | `hp.max` / `hp.current` |
| 速度 Speed | `speed` |
| 六属性 STR/DEX/CON/INT/WIS/CHA | `abilities.{str,dex,con,int,wis,cha}` |
| 豁免 Saving Throws（熟练者） | `save_profs` |
| 技能 Skills | `skill_profs` |
| 感官 Senses | 特殊感官记 `features` |
| 语言 Languages | `languages` |
| 挑战等级 CR / 熟练加值 | 记 `notes` 或 `features`（无专字段） |
| 伤害抗性/免疫、状态免疫 | 记 `features`（无专字段） |
| 特性 Traits | `features` |
| 动作 Actions（含攻击） | `attacks` `[{name,bonus,damage,damage_type,range}]` |
| 附赠动作 / 反应 | `features` |

> schema 无 CR / 抗性 / 感官专字段（YAGNI）；需要时写进 `features` 或 `notes`。

## 相关文件

- 实现在 `scripts/sheet.py`。
