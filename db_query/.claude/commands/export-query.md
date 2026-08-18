---
description: 执行 SQL 查询并将结果一键导出为 CSV/JSON 文件
argument-hint: <数据库名> "<SQL 或自然语言>" [csv|json] [输出文件路径]
---

# 导出查询结果

你的任务：把用户的输入解析为「数据库 + 查询 + 导出格式」，通过 db_query 后端 API
执行查询并把结果保存为本地文件。参数：$ARGUMENTS

把整个流程严格分解为以下子任务，按顺序执行，每步失败就停下向用户报告，不要猜测：

## 子任务 1：解析参数

从 $ARGUMENTS 中识别（缺少的项向用户询问，不要编造）：

- **数据库名**（必需）：已注册的连接名。可用 `curl -s http://localhost:8000/api/v1/dbs` 列出全部连接名供用户选择。
- **查询**（必需）：一段 SQL（以 SELECT 开头），或一句自然语言（如「每个部门的候选人数量」）。
- **格式**（可选，默认 `csv`）：`csv` 或 `json`。
- **输出文件**（可选，默认 `db_query/exports/<数据库名>_<时间戳>.<格式>`）。

## 子任务 2：确认后端在线

```bash
curl -fsS http://localhost:8000/health
```

失败则告诉用户先在 db_query 目录运行 `make dev-backend`，然后停止。

## 子任务 3：如果是自然语言，先转成 SQL

仅当子任务 1 判断输入是自然语言时执行：

```bash
curl -fsS -X POST http://localhost:8000/api/v1/dbs/<数据库名>/query/natural \
  -H "Content-Type: application/json" \
  -d '{"prompt": "<用户的自然语言查询>"}'
```

把返回的 `sql` 和 `explanation` 展示给用户，确认后再继续。用户也可以修改 SQL。

## 子任务 4：试执行查询，确认有数据

```bash
curl -fsS -X POST http://localhost:8000/api/v1/dbs/<数据库名>/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "<SQL>"}'
```

- 成功：向用户报告行数与耗时；0 行时提醒导出会得到空文件，确认是否继续。
- 失败（400/404/500）：把 `detail` 里的错误信息原样报告给用户并停止。

## 子任务 5：调用导出端点，创建文件

```bash
mkdir -p <输出目录>
curl -fsS -X POST "http://localhost:8000/api/v1/dbs/<数据库名>/query/export?format=<格式>" \
  -H "Content-Type: application/json" \
  -d '{"sql": "<SQL>"}' \
  -o "<输出文件>"
```

注意：导出端点会**重新执行一次查询**（结果不落库），确保导出的是最新数据。

## 子任务 6：校验并汇报

- 用 `wc -l` 和 `head -5` 检查文件非空、格式正确（CSV 有表头、JSON 是合法数组）。
- 向用户汇报：文件绝对路径、行数、使用的 SQL、格式。

全程不要修改任何项目源代码；这是一个"查询 + 导出"的自动化操作命令。
