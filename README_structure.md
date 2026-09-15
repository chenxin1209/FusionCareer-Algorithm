# 岗位结构化与去重模块

本目录为独立整理的 **结构化 + 去重** 代码包，详见 [MANIFEST.md](MANIFEST.md)。

- **核心**：`job_structuring/engine.py`
- **入口**：`python pipeline/run_pipeline.py`
- **管理员端解析**：`python -m job_structuring.admin_parse --file sample_data/admin_jobs/学院内推_小实习.txt`
- **解析 HTTP**：`uvicorn job_structuring.serve:app --host 0.0.0.0 --port 9101`

完整使用说明见下文各节。

---

## 1. 模块功能

| 能力 | 说明 |
|------|------|
| LLM 结构化 | 从 Markdown 抽取一个或多个岗位 |
| 汇总文拆岗 | 「招聘岗位汇总」按单位×岗位拆条，禁止用汇编标题当岗位名 |
| 管理员端解析 | 粘贴原文回填表单：学院内推、大/小实习、无年份日期补全 |
| 字段对齐 | camelCase，对齐后端 `JobPostRequest` |
| 标题预过滤 | 跳过双选会、讲座等非招聘文 |
| 去重 | 篇内 + CSV 增量 + 流水线全量去重 |

**去重键：** `(sourceUrl 或 source_md, companyName, positionName)`

## 2. 输入

- 目录：`data/articles/`（或 `config.json` 的 `articles_dir`）
- 格式：UTF-8 `.md`，含 `# 标题` 与 `**Link:**` 原文链接
- 管理员粘贴：纯文本，见 `sample_data/admin_jobs/`

## 3. 输出

- `data/output/all_positions.csv`（UTF-8 BOM）
- `data/output/all_positions.json`（数组）

管理员解析 HTTP：`POST /internal/job/parse`，body `{"raw_text":"..."}`，返回 `data.position`（单表单）与 `data.positions`（一文多岗）。

## 4. 运行

```bash
pip install -r requirements.txt
copy config.json.example config.json
python pipeline/run_pipeline.py
```

或：`python structure_data.py --batch-dir`

管理员端（缩短等待：默认 `deepseek-chat`，JSON 模式，独立短提示词，超时约 60 秒）：

```bash
python -m job_structuring.admin_parse --file sample_data/admin_jobs/学院内推_小实习.txt
uvicorn job_structuring.serve:app --host 0.0.0.0 --port 9101
```

## 5. 日志

- `logs/pipeline.log` — 流水线摘要
- `logs/non_recruitment.log` — 跳过记录
- `logs/llm_io/YYYY-MM-DD.jsonl` — **每次 LLM 的完整输入/输出**（`channel=crawl` 爬虫抽取，`channel=admin` 管理员解析）
- `logs/llm_io/latest.json` — 最近一次调用快照

此前版本只记录跳过原因，不落盘模型 I/O；对照材料见 `sample_data/job_extract_io_for_teacher.md`。

## 6. LLM Key（占位）

```json
{
  "llm_api_key": "sk-your-deepseek-key",
  "llm_base_url": "https://api.deepseek.com/v1",
  "llm_model": "deepseek-chat",
  "llm_fast_model": "deepseek-chat"
}
```

亦可：`export DEEPSEEK_API_KEY=sk-your-deepseek-key`

不要把 `llm_model` 配成 `deepseek-reasoner`：管理员解析会等待过久。若必须关掉思考链，可设 `"llm_send_disable_thinking": true`（部分兼容网关支持）。
