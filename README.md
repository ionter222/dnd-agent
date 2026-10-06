# 🎲 D&D 5E DM Agent · 龙与地下城跑团智能体

[中文](#-中文文档) | [English](#-english)

> ⚠️ **本仓库不含任何受版权保护的规则书 / 模组 / 世界观内容。**
> 规则书（PHB / DMG / MM）与冒险模组请**自行合法获取**后放入对应文件夹。

---

## 🇨🇳 中文文档

一个基于 [opencode](https://opencode.ai) 的 **D&D 5E 跑团（TRPG）智能体**：让 AI 像人类 DM 一样带团——管骰子、管角色卡、管战斗、查规则、记存档、跑模组。

### ✨ 功能一览

| Skill | 作用 |
|---|---|
| **dice-roll** | 骰子与判定：d20 优势/劣势、优势惩罚骰、CoC 奖励/惩罚骰、5e DC、暗骰、文本/JSON 输出 |
| **character-sheet** | 角色卡：唯一 JSON 事实源，HP / 法术位 / AC / 状态 / 死亡豁免 / 派生值 / 建卡流程 |
| **combat** | 战斗状态机：先攻、回合、坐标地图、距离查询、改卡联动（**引擎不掷骰**） |
| **rules-reference** | 规则/模组索引与查询：本地全文关键词检索，**建索引前先询问用户**，防幻觉 |
| **campaign** | 战役存档：日志、游戏内时间、NPC 名册、任务、长休/短休、升级、可选小说叙事 |
| **module** | 模组进度跟踪：场景、已获线索、遭遇清空、关键决定；联动规则查询取原文 |

外加：

- **DM 智能体** `dm.md`（15 节骨架 + 铁律：永不替玩家决策、一切随机必走脚本、资源变化必落卡、及时存档）
- **人格插件** `personas/`（猫娘 / 但丁 / 罗伯特 / 娜塔莎 / 三无）——*叠加*在 `dm.md` 骨架之上生效，骨架铁律不可推翻；用户不指定人格时用默认的人类 DM 风格

### 📁 目录结构

```
.opencode/agent/dm.md              主 DM 智能体
.opencode/agent/personas/*.md      人格插件
.opencode/skill/<name>/            6 个 skill（SKILL.md + scripts/ + reference/）
tests/                             单元测试（stdlib unittest）
规则书_Rulebooks/        ← 放你的 PHB / DMG / MM（自行获取）
世界观_Worldbuilding/    ← 放你的世界观设定
模组_Modules/            ← 放你的冒险模组
角色卡_CharacterSheets/  ← 角色卡（运行时生成）
存档_Saves/              ← 战役存档（运行时生成）
战斗_Combats/            ← 战斗状态（运行时生成）
```

> 内容文件夹在仓库里是**空的**（只有 `.gitkeep`），且已被 `.gitignore` 忽略——你放进去的书和存档不会被误传。

### 🚀 安装

需要 [opencode](https://opencode.ai)（建议 ≥ v1.14.24）与 **Python 3.10+**（本项目**零第三方依赖**，仅用标准库）。

```bash
git clone https://github.com/ionter222/dnd-agent.git
cd dnd-agent
opencode            # 在项目目录内启动；opencode 会自动读取 .opencode/
```

启动后选择 `dm` 智能体即可开团。

### 📚 用你自己的规则书 / 世界观 / 模组

1. 把你的 **PDF / TXT** 放进对应文件夹：

   ```
   规则书_Rulebooks/      e.g. 玩家手册.pdf  怪物图鉴.pdf
   世界观_Worldbuilding/  e.g. 费伦大陆.pdf
   模组_Modules/          e.g. 凡戴尔的失落矿坑.pdf
   ```

2. **（可选，强烈推荐）建立索引以防幻觉**：

   ```bash
   # 只索引规则书（默认）
   python .opencode/skill/rules-reference/scripts/rules.py index --source 规则书
   # 索引模组 / 世界观
   python .opencode/skill/rules-reference/scripts/rules.py index --source 模组
   ```

   > 索引仅存本地 `.rule_index/`（已 gitignore），**不会**上传。
   > 不建索引也能用，只是查规则时会退化为让 AI 直接读 PDF。

### 🎮 开始跑团

在 opencode 里对 `dm` 说：

```
/dm 开始一个新的战役
```

DM 会依次：建角色卡 → 掷骰判定 → 战斗管理 → 查规则 → 记录存档。**所有随机结果都来自 `dice-roll` 脚本，AI 不会自己编数字。**

### 🧰 单独使用 skill（命令行）

```bash
python .opencode/skill/dice-roll/scripts/roll.py "1d20+5" --dc 15 --label 攻击          # 判定
python .opencode/skill/dice-roll/scripts/roll.py "1d20+5" --adv --json                  # 优势
python .opencode/skill/character-sheet/scripts/sheet.py new 亚瑟                        # 建卡
python .opencode/skill/character-sheet/scripts/sheet.py hp 亚瑟 -8                      # 扣血
python .opencode/skill/combat/scripts/combat.py new 遭遇                                 # 建战斗
python .opencode/skill/rules-reference/scripts/rules.py query "火球术 伤害"              # 查规则
python .opencode/skill/campaign/scripts/campaign.py new 银之远征                         # 建战役
python .opencode/skill/module/scripts/module.py new 矿坑 --module 凡戴尔的失落矿坑        # 建模组进度
```

### 🧪 运行测试

```bash
python -m unittest discover -s tests -v
```

### 📜 版权声明

本项目管理**只**包含智能体提示词与 skill 脚本，**不包含**任何 D&D 规则书、冒险模组或世界观文本。D&D、Dungeons & Dragons 及相关商标归 Wizards of the Coast 所有。使用者需自行合法获取所需的规则书与模组。

---

## 🇬🇧 English

A **D&D 5E tabletop-RPG agent** built on [opencode](https://opencode.ai). It lets an AI act as your Dungeon Master — rolling dice, tracking character sheets, running combat, looking up rules, saving campaigns, and tracking module progress.

> ⚠️ **This repository contains NO copyrighted rulebooks, modules, or setting text.**
> Please obtain the PHB / DMG / MM and any adventures **legally** yourself and drop them into the folders below.

### ✨ What's inside

| Skill | What it does |
|---|---|
| **dice-roll** | Dice & checks: d20 advantage/disadvantage, CoC bonus/penalty dice, 5e DC, secret rolls, text + JSON output |
| **character-sheet** | Character sheets: a single JSON source of truth — HP / spell slots / AC / conditions / death saves / derived stats |
| **combat** | Combat state machine: initiative, turns, coordinate map, distance, sheet updates (**the engine never rolls dice**) |
| **rules-reference** | Rule/module index & query: local full-text keyword search, asks before building an index, anti-hallucination |
| **campaign** | Campaign save file: log, in-game time, NPC roster, quests, long/short rest, level-up, optional novel-style narrative |
| **module** | Module progress tracking: scenes, clues, cleared encounters, key decisions; integrates with rules lookup |

Plus:

- **DM agent** `dm.md` — a 15-section skeleton with hard rules: *never act for the player, always roll via the script, always persist resource changes, save often*.
- **Persona plugins** `personas/` — 猫娘 / 但丁 / 罗伯特 / 娜塔莎 / 三无 (catgirl / Dante / Robert / Natasha / silent). They *layer on top of* `dm.md`; the skeleton's hard rules cannot be overridden.

### 📁 Layout

```
.opencode/agent/dm.md              main DM agent
.opencode/agent/personas/*.md      persona plugins
.opencode/skill/<name>/            6 skills (SKILL.md + scripts/ + reference/)
tests/                             unit tests (stdlib unittest)
规则书_Rulebooks/                  ← your PHB / DMG / MM (obtain legally)
世界观_Worldbuilding/              ← your worldbuilding docs
模组_Modules/                      ← your adventure modules
角色卡_CharacterSheets/            ← character cards (generated at runtime)
存档_Saves/                        ← campaign saves (generated at runtime)
战斗_Combats/                      ← combat state (generated at runtime)
```

> The content folders ship **empty** (only a `.gitkeep`) and are gitignored — anything you add stays local.

### 🚀 Install

Requires [opencode](https://opencode.ai) (≥ v1.14.24 recommended) and **Python 3.10+** (the project has **zero third-party dependencies**, stdlib only).

```bash
git clone https://github.com/ionter222/dnd-agent.git
cd dnd-agent
opencode            # launch inside the project; opencode reads .opencode/ automatically
```

Then pick the `dm` agent and start playing.

### 📚 Bring your own rulebooks

1. Drop your **PDF / TXT** files into the matching folder (see layout above).
2. **(Optional but recommended) Build an index to prevent hallucination:**

   ```bash
   python .opencode/skill/rules-reference/scripts/rules.py index --source 规则书
   ```

   > The index lives in local `.rule_index/` (gitignored) and is **never** uploaded.

### 🎮 Play

Tell the `dm` agent:

```
/dm start a new campaign
```

The DM will create sheets → roll checks → run combat → look up rules → save progress. **Every random outcome comes from the `dice-roll` script — the AI never makes up numbers.**

### 🧰 Use a skill directly

```bash
python .opencode/skill/dice-roll/scripts/roll.py "1d20+5" --dc 15 --label attack
python .opencode/skill/character-sheet/scripts/sheet.py new Arthur
python .opencode/skill/combat/scripts/combat.py new encounter
python .opencode/skill/rules-reference/scripts/rules.py query "fireball damage"
```

### 🧪 Tests

```bash
python -m unittest discover -s tests -v
```

### 📜 Copyright

This project ships **only** agent prompts and skill scripts — **no** D&D rulebooks, adventures, or setting text. Dungeons & Dragons and related trademarks belong to Wizards of the Coast. You are responsible for legally obtaining any rulebooks or modules you use.

---

## 📄 License

MIT (see `LICENSE`) — *add your preferred license before publishing.*
