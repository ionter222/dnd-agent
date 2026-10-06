---
name: module
description: 模组运行跟踪 skill —— 记录单次模组（adventure）运行的进度：当前场景、已访问地点、已获线索、已清遭遇、关键决定，并可取回场景原文。触发词：跑模组、模组进度、场景、线索、遭遇、冒险记录、凡戴尔的失落矿坑。
---

# module —— 模组运行跟踪

跟踪**单次模组运行**的进度，防止 DM 忘记队伍在哪、漏记线索、重复触发已清遭遇。本 skill **不掷骰、不战斗、不查规则、不碰角色卡**。

## 何时用

- 开始跑一个模组（`new`）。
- 队伍进入新场景（`scene`）、探索地点（`visit`）。
- 发现线索（`clue add`）、清空遭遇/房间（`clear`）、做出关键分支决定（`decide`）。
- 需要模组场景原文（`read`）。

## 命令

| 命令 | 说明 |
|---|---|
| `new <运行名> --module <模组名> [--campaign <战役名>]` | 新建运行 |
| `list` | 列出所有运行 |
| `status <运行名>` | 运行概览 |
| `scene <运行名> <场景名>` | 设当前场景（自动入 visited） |
| `visit <运行名> <场景名>` | 标记已访问 |
| `clue <运行名> add <线索名> [--detail …]` | 记录线索（同名更新） |
| `clue <运行名> list` | 列出线索 |
| `clear <运行名> <遭遇名>` | 标记遭遇/房间已清 |
| `decide <运行名> <描述>` | 记录关键决定 |
| `read <运行名> [<场景名>] [--book …] [--limit N]` | 取场景原文（默认当前场景） |
| `link <运行名> <战役名>` / `unlink <运行名>` | 关联/解除战役 |
| `remove <运行名>` | 删除运行 |

所有命令支持 `--json`。

## 与其它 skill 的联动

- **rules-reference**：`read` 同进程调用其 `load_index` / `search` 取场景原文。若尚未建索引 → 退 0，返回模组 PDF 路径并提示 `rules-reference index --source 模组`（**不自动建索引**）。
- **campaign**：`--campaign` 关联战役，二者共用 `存档_Saves/`。
- 掷骰交 `dice-roll`；战斗交 `combat`；角色卡交 `character-sheet`。

## 铁律

1. 进度只经本 skill 落 `存档_Saves/<运行名>.json`，它是事实源。
2. 场景 / 遭遇名是**自由字符串**，取自模组原文小标题；不校验存在性。
3. `read` 无索引不报错——退 0 并给出 PDF 路径。
4. 不自动建索引、不改角色卡、不掷骰。
5. 非法输入 / 未知运行 → 中文报错退 2；强制 UTF-8；`--json` 可解析。

详见 `scripts/module.py` 与 `reference/schema.md`。
