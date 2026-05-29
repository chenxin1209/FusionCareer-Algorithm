# 岗位结构化与去重模块

本目录为独立整理的 **结构化 + 去重** 代码包，详见 [MANIFEST.md](MANIFEST.md)。

- **核心**：`job_structuring/engine.py`
- **入口**：`python pipeline/run_pipeline.py`
- **不负责**：爬虫、`resume_parser`、后端服务

完整使用说明见下文各节。

---

## 1. 模块功能

| 能力 | 说明 |
|------|------|
| LLM 结构化 | 从 Markdown 抽取一个或多个岗位（JSON 数组） |
| 字段对齐 | camelCase，对齐后端 `JobPostRequest` |
| 标题预过滤 | 跳过双选会、讲座等非招聘文 |
| 去重 | 篇内 + CSV 增量 + 流水线全量去重 |

**去重键：** `(sourceUrl 或 source_md, companyName, positionName)`

## 2. 输入

- 目录：`data/articles/`（或 `config.json` 的 `articles_dir`）
- 格式：UTF-8 `.md`，含 `# 标题` 与 `**Link:**` 原文链接

## 3. 输出

- `data/output/all_positions.csv`（UTF-8 BOM）
- `data/output/all_positions.json`（数组）

## 4. 运行

```bash
pip install -r requirements.txt
copy config.json.example config.json
python pipeline/run_pipeline.py
```

或：`python structure_data.py --batch-dir`

## 5. 日志

- `logs/pipeline.log` — 流水线摘要
- `logs/non_recruitment.log` — 跳过记录

## 6. LLM Key（占位）

```json
{
  "llm_api_key": "sk-your-deepseek-key",
  "llm_base_url": "https://api.deepseek.com/v1",
  "llm_model": "deepseek-chat"
}
```

亦可：`export DEEPSEEK_API_KEY=sk-your-deepseek-key`
