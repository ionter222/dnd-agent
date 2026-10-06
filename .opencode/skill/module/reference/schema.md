# module 运行文件结构（schema v1）

存储：`存档_Saves/<运行名>.json`（UTF-8，`ensure_ascii=False, indent=2`）。
目录优先级：`--run-dir` > 环境变量 `DND_MODULE_DIR` > `<仓库根>/存档_Saves`。

## 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int | 结构版本（=1） |
| `name` | str | 运行名 |
| `campaign` | str / null | 关联的战役名 |
| `module` | str | 模组名 |
| `created_at` / `updated_at` | str | ISO8601 |
| `current` | str / null | 当前场景 |
| `visited` | list[str] | 已访问场景 |
| `clues` | list[{name,detail,time}] | 已获线索（同名更新 detail） |
| `cleared` | list[str] | 已清遭遇 / 房间 |
| `decisions` | list[{text,time}] | 关键决定 |

## 命令速查

| 命令 | 语义 |
|---|---|
| `new <运行名> --module <模组名> [--campaign <战役名>]` | 新建；已存在 → 退 2 |
| `list` | 所有运行摘要，按名排序 |
| `status <运行名>` | 概览 |
| `scene <运行名> <场景名>` | 设 `current`；自动入 `visited` |
| `visit <运行名> <场景名>` | 只入 `visited` |
| `clue <运行名> add <线索名> [--detail …]` | 追加 / 同名更新 |
| `clue <运行名> list` | 线索列表 |
| `clear <运行名> <遭遇名>` | 去重标记 |
| `decide <运行名> <描述>` | 追加决定 |
| `read <运行名> [<场景名>] [--book …] [--limit N]` | 取原景原文 |
| `link` / `unlink` / `remove` | 关联 / 解除 / 删除 |

## read 规则

- 场景名缺省取 `current`；两者皆空 → 退 2。
- 有 rules-reference 索引 → 返回命中片段 + 页码（`book` 缺省为 `module`）。
- 无索引 → **退 0** + 中文提示「尚未建立模组索引」+ 返回模组 PDF 路径 + 提示 `rules-reference index --source 模组`。

## 校验

- 运行名不得为空、`.`、`..`，且不含 `/` 或 `\`（防目录穿越）。
- 运行文件缺失 / 损坏（非 dict 或非法 JSON）→ 中文报错退 2。
