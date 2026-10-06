# 战役存档格式（schema_version = 1）

存档路径：`存档_Saves/<战役名>.json`（UTF-8，进 git）。可用 `DND_CAMPAIGN_DIR` 或 `--campaign-dir` 覆盖。

## 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | int | 恒为 `1` |
| `name` | str | 战役名 |
| `created_at` | str | 创建时间（ISO 秒） |
| `updated_at` | str | 最近更新时间（ISO 秒） |
| `in_game_time` | str | 游戏内时间（自由文本） |
| `novel` | bool | 是否启用小说式叙事（用户偏好） |
| `party` | list | 队员：`{sheet, role}`（`role` 为 `pc`/`npc`） |
| `log` | list | 日志：`{seq, time, title, summary, details, tags}` |
| `npcs` | list | NPC：`{name, note, tags}` |
| `quests` | list | 任务：`{name, detail, status}`（初始 `进行中`；状态取值 `进行中`/`已完成`/`已失败`） |

## 命令速查

```
campaign.py new <战役名>
campaign.py list
campaign.py status <战役名>
campaign.py log <战役名> <标题> <摘要> [--details <细节>] [--time <时间>] [--tags a,b]
campaign.py time <战役名> <文本>
campaign.py novel <战役名> <on|off>
campaign.py recap <战役名> [--last N]
campaign.py link <战役名> <角色卡名> [--role pc|npc]
campaign.py unlink <战役名> <角色卡名>
campaign.py npc <战役名> add <NPC名> [--note <备注>]
campaign.py quest <战役名> add <任务名> [--detail <细节>]
campaign.py quest <战役名> update <任务名> [--status <状态>] [--detail <细节>]
campaign.py rest <战役名> <long|short> [--heal N] [--spend N]
campaign.py level <角色卡名> <职业> [--hp N | --avg] [--subclass <学派>]
```

## rest 规则

- **长休（long）**：HP 补满、临时 HP 清零、各环法术位 `used` 归零、死亡豁免归零、恢复生命骰 `max(1, total//2)`。
- **短休（short）**：DM 用 `dice-roll` 掷好治疗量 → `--heal N` 记入 HP；`--spend N` 记花掉的生命骰。
- 队伍为空时报错。

## level 规则

- `--hp N` 与 `--avg` 恰用其一：`--hp` 用 DM 掷出的值；`--avg` 用平均 `max(1, sides//2 + 1 + 体质调整)`。
- 只更新：职业等级、HP 上限与当前值、生命骰总数。
- **法术位与特性不自动改**，由 DM 手动写进角色卡。
