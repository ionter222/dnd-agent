# 规则索引结构（schema）

索引文件默认位于仓库根 `.rule_index/index.json`（可用环境变量 `DND_RULE_INDEX` 覆盖）。**该目录不进 git**。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int | 索引结构版本（当前为 `1`） |
| `built_at` | str | 建立时间（ISO 8601，秒精度） |
| `sources` | list[str] | 本次索引的来源简称，如 `["规则书","模组"]` |
| `books` | list[obj] | 每本书的元信息 |
| `chunks` | list[obj] | 全部文本块（查询的实际单位） |

### `books[]` 元素

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | str | 来源简称（规则书/模组/世界观） |
| `book` | str | 书名（文件去扩展名） |
| `file` | str | 源文件路径（相对仓库根） |
| `pages` | int | 页数 |
| `chunks` | int | 该书切出的文本块数 |

### `chunks[]` 元素

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | str | 来源简称 |
| `book` | str | 书名 |
| `page` | int | 页码（从 1 起） |
| `text` | str | 文本块正文（页内按空行分段，丢弃过短与纯目录行） |

## 固定文件夹与来源映射

| 来源简称 | 文件夹（仓库根下） |
|---|---|
| 规则书 | `规则书_Rulebooks/` |
| 模组 | `模组_Modules/` |
| 世界观 | `世界观_Worldbuilding/` |

支持的源文件：`.pdf`（优先 `pdftotext`，缺失则回落 `pypdf`）与 `.txt`（支持 `=== PAGE n ===` 分页标记，或整篇作一页）。

## 命令速查

| 命令 | 说明 |
|---|---|
| `status` | 索引状态（`--json` → `{exists, built_at, sources, books, chunks, summary}`） |
| `index [--source S]… [--all] [--book K]` | 建索引（默认只建「规则书」） |
| `query <词…> [--book K] [--limit N]` | 查询（`--json` → `{query, count, hits[]}`，`hits[]` 含 `source/book/page/score/snippet/text`） |
| `books` | 扫描固定文件夹，列出可索引的 PDF/txt（`--json` → `{books:[{source,book,file}]}`） |

错误处理：未知来源 / 未建索引就查询 / 无可索引文件 → **中文报错 + 退出码 2**，绝不静默。
