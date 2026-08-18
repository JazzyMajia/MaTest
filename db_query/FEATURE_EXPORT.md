# FEATURE_EXPORT.md — 数据导出功能模块设计文档

> 在"智能数据库查询工具"上新增的数据导出模块：支持 CSV / JSON 两种格式，
> 提供界面按钮、主动询问、后端 API、`make export` 与 Claude Code `/export-query`
> 五种触发方式，覆盖"人工点击 → 脚本一键 → Agent 自动化"的完整光谱。

## 1. 功能概述

| 能力 | 说明 |
|---|---|
| 导出格式 | CSV（`text/csv`）、JSON（`application/json`），二者语义一致、互为补充 |
| 界面导出 | 查询结果卡片上的 EXPORT CSV / EXPORT JSON 按钮（本地即时导出） |
| 主动询问 | 查询成功后右上角弹出通知：「查询返回 N 行，要导出为 CSV 或 JSON 吗？」8 秒自动关闭 |
| API 导出 | `POST /api/v1/dbs/{name}/query/export?format=csv\|json`，返回附件下载 |
| 一键命令 | `make export DB=... SQL="..." FORMAT=csv`（curl 单命令完成"执行+导出"） |
| Agent 命令 | Claude Code 自定义命令 `/export-query <db> "<SQL或自然语言>" [csv\|json] [文件]` |

## 2. 总体架构与任务分解

导出是一个天然的**可分解任务**。本模块按"获取查询结果 → 格式化数据 → 创建文件"
三个子任务分层实现，每层独立可测试：

```
┌─ 触发层（谁发起导出）────────────────────────────────────┐
│  ① Home.tsx 按钮/主动询问通知（浏览器本地导出）           │
│  ② /export-query 自定义命令（Claude Code Agent）         │
│  ③ make export（curl 一键命令）                          │
├─ API 层【子任务 1：获取查询结果】────────────────────────┤
│  POST /api/v1/dbs/{name}/query/export?format=csv|json    │
│  复用 execute_query_with_service() 执行 SQL 得到结果      │
├─ 格式化层【子任务 2：格式化数据】────────────────────────┤
│  app/services/exporter.py（纯函数，无 IO）                │
│  result_to_csv() / result_to_json() / build_filename()   │
├─ 文件层【子任务 3：创建文件】────────────────────────────┤
│  Response + Content-Disposition 附件响应                  │
│  → 浏览器保存 / curl -o / Agent 写盘，三种消费者同一协议  │
└──────────────────────────────────────────────────────────┘
```

**为什么这样分层**：格式化逻辑做成无副作用的纯函数，是最容易被 Agent 理解和复用的
"工具单元"；执行查询复用已有的 `execute_query_with_service`（含 SQL 校验、历史记录），
导出端点不重复实现任何执行逻辑。

## 3. 后端设计

### 3.1 格式化服务 `backend/app/services/exporter.py`

| 函数 | 职责 |
|---|---|
| `result_to_csv(result)` | 列顺序跟随 `result.columns`；null → 空串；datetime → ISO-8601；转义交给 stdlib `csv`（quote-minimal、`""` 转义） |
| `result_to_json(result)` | 导出 rows 数组（与前端既有行为一致）；datetime → ISO 字符串；`ensure_ascii=False` 保留中文 |
| `build_filename(db, fmt)` | `{库名}_{时间戳}.{格式}`，与前端命名约定一致 |
| `format_result(result, fmt)` | 格式分发入口，不支持的格式抛 `ValueError` |

### 3.2 API 端点（`app/api/v1/queries.py`）

```
POST /api/v1/dbs/{name}/query/export?format=csv|json
Content-Type: application/json

{"sql": "SELECT id, name FROM users"}
```

成功响应（200）：

- `Content-Type: text/csv`（或 `application/json`）
- `Content-Disposition: attachment; filename="users_2026-08-17T10-30-00.csv"`
- Body 即文件内容

错误约定与既有端点完全一致：`404` 连接不存在；`400` SQL 校验失败（非 SELECT 等）；
`422` format 参数不合法（FastAPI `Literal["csv", "json"]` 自动校验）；`500` 执行失败。

### 3.3 关键权衡：导出时重新执行查询

`queryhistory` 表只保存查询元数据（SQL 文本、行数、耗时），**不保存结果集**。因此导出
采用"重新执行 SQL"策略（BI 工具的通用做法），代价与收益：

- ✅ 无需引入结果集持久化（大结果会撑爆 SQLite / 内存）
- ✅ 导出的永远是最新数据，不存在"过期快照"问题
- ⚠️ 查询会执行两次（试执行 + 导出）、历史中会多一条记录 —— 对只读 SELECT 可接受
- 🔮 演进方向：给导出端点加 `history_id` 参数以复用历史 SQL；或引入短期结果缓存

## 4. 前端设计

### 4.1 共享工具 `frontend/src/utils/export.ts`

原先导出逻辑内联在 `Home.tsx`（两段几乎重复的 Blob 下载代码）。现抽取为共享模块：

- `buildCsvContent / buildJsonContent / downloadFile / exportResultLocally`
- **前后端 CSV 转义规则刻意保持一致**（引号包裹、`""` 转义、null → 空串），
  同一条查询无论从浏览器导出还是从服务端导出，得到等价文件

`Home.tsx` 中 4 个函数（`handleExportCSV/JSON` + `exportToCSV/JSON`）收敛为
`doExport(format, result)` + `handleExport(format)`，保留原有的空数据警告与
>10000 行确认弹窗。

### 4.2 主动询问交互（用户交互设计）

作业要求的"AI 助手主动询问"落地为：**查询成功 → 主动弹出通知**：

> Export this result? — The query returned 42 rows. Would you like to export
> it as a CSV or JSON file?  【EXPORT CSV】【EXPORT JSON】

设计要点：

- **不打断**：用 `notification`（右上角、8 秒自动消失）而非模态框，用户可完全忽略
- **一键直达**：通知内直接放两个导出按钮，比"找到结果卡片 → 点导出"少一步
- **克制的触发条件**：仅在有数据（rows > 0）时询问，空结果不打扰
- 该交互模式与 AI 对话中的"主动追问"同构：系统在完成一个动作后，主动提供
  下一步建议，用户一键采纳

## 5. 自动化设计

### 5.1 Claude Code 自定义命令 `/export-query`

命令文件：`.claude/commands/export-query.md`（项目内，随代码提交）。
用法示例：

```
/export-query interview_db "SELECT department, COUNT(*) AS cnt FROM candidates GROUP BY department" csv

/export-query interview_db "每个部门的候选人数量" json exports/by_dept.json
```

命令把 Agent 的执行过程编排为 6 个子任务，**每步失败即停、向用户报告，不猜测**：

| 步骤 | 子任务 | 失败处理 |
|---|---|---|
| 1 | 解析参数（库名/SQL或自然语言/格式/输出路径），缺项询问用户 | — |
| 2 | `curl /health` 确认后端在线 | 提示 `make dev-backend` |
| 3 | 自然语言 → `POST /query/natural` 生成 SQL，**展示并确认** | 用户可修改 |
| 4 | `POST /query` 试执行，报告行数 | 原样报告 `detail` 错误 |
| 5 | `POST /query/export` 下载到目标文件 | — |
| 6 | `wc -l` + `head` 校验文件并汇报绝对路径/行数/SQL | — |

这直接对应作业的"Agent 任务分解"练习点：Agent 在「获取查询结果（步骤 2-4）→
格式化数据（服务端 exporter）→ 创建文件（步骤 5-6）」间协调，且把**需要人类判断
的节点**（确认生成的 SQL、空结果是否继续）显式留给人。

### 5.2 Makefile 一键命令

```bash
make export DB=interview_db SQL="SELECT * FROM candidates LIMIT 10" FORMAT=csv
# → exports/interview_db_20260817_103000.csv
```

不依赖 Claude Code，适合写进脚本/CI，也是对后端导出端点的最简冒烟测试。

## 6. 测试与验证

| 层 | 测试 | 命令 |
|---|---|---|
| 格式化 | 17 个用例：表头顺序、逗号/引号/换行转义、null、datetime、中文、非法格式 | `cd backend && uv run pytest tests/unit/test_exporter.py -v` |
| API | 7 个用例：csv/json 成功（含响应头）、默认格式、422/404/400/500 | `uv run pytest tests/unit/test_api_export.py -v` |
| 前端 | `npx tsc --noEmit` 类型检查通过 | `cd frontend && npx tsc --noEmit` |
| 端到端 | `make dev-backend` + `make export DB=... SQL=...` 实测下载 | 需真实 MySQL/PG 连接 |

测试遵循项目既有模式：内存 SQLite fixture + FastAPI `dependency_overrides` +
`TestClient`，mock 目标为路由模块实际导入的 `execute_query_with_service`。
（注：仓库中部分存量测试 mock 了重构前的旧符号 `execute_query`，属于历史遗留失败，
与本次改动无关，未修改。）

## 7. Cursor 与 Claude Code 的结合（工具链思考）

- **Cursor**（AI 编辑器，强在"写代码"）：适合本次的**代码生成与快速迭代**——
  新增 exporter 服务、端点、前端组件这类"目标明确、上下文在当前文件"的任务，
  在编辑器里 Tab/Chat 循环几轮就能成形，即时预览类型错误。
- **Claude Code**（终端 Agent，强在"多步骤自动化"）：适合**跨系统、有状态的流程**——
  本次"执行查询 + 导出文件"需要串联 HTTP 调用、文件写入、结果校验，还要处理
  后端未启动、SQL 非法、空结果等分支。这类任务在编辑器里要人肉搬运每一步的
  中间结果，而 Agent 能一气呵成并在失败点自动降级询问。
- **本项目的结合方式**：用 Cursor 完成导出模块的编码与界面打磨；用 Claude Code
  的自定义命令把模块变成"一句话可触发"的能力（`/export-query`），并让它承担
  日常数据导出这类重复操作。代码能力沉淀在**项目里**（端点 + 命令文件随仓库提交），
  而不是沉淀在某个 AI 工具的会话里——之后无论谁、用什么工具，都能复用。

## 8. 变更清单

| 文件 | 变更 |
|---|---|
| `backend/app/services/exporter.py` | 新增：CSV/JSON 格式化服务 |
| `backend/app/api/v1/queries.py` | 新增 `POST /{name}/query/export` 端点 |
| `backend/tests/unit/test_exporter.py` | 新增：格式化单测（17 例） |
| `backend/tests/unit/test_api_export.py` | 新增：端点单测（7 例） |
| `frontend/src/utils/export.ts` | 新增：共享导出工具 |
| `frontend/src/pages/Home.tsx` | 重构导出逻辑；新增查询后主动询问通知 |
| `.claude/commands/export-query.md` | 新增：Claude Code 自定义命令 |
| `Makefile` | 新增 `export` 一键目标 |
| `backend/README.md` | 新增（修复上游 pyproject 引用缺失导致 `uv sync` 失败） |
