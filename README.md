# FusionCareer-Algorithm

FusionCareer 算法侧仓库，当前包含两大模块：

| 模块 | 目录 | 说明 |
|------|------|------|
| **岗位结构化 + 去重** | `job_structuring/`、`pipeline/` | Markdown → LLM 抽取 → CSV/JSON（对齐 `JobPostRequest`） |
| **简历解析** | `resume_parser/` | PDF/Word/图片简历 → 结构化 JSON |

- 爬虫、后端 Java 服务由其他同事维护。
- 岗位模块详细文档见 **[README_structure.md](README_structure.md)**。

---

## 仓库结构

```
FusionCareer-Algorithm/
├── job_structuring/          # 岗位结构化核心
├── pipeline/
│   ├── run_pipeline.py       # 岗位流水线（推荐）
│   └── upload_to_backend.py  # 可选：上传后端
├── structure_data.py         # 岗位 CLI 兼容入口
├── sample_data/              # 岗位小样本
├── data/articles/            # 岗位输入（.gitkeep）
├── data/output/              # 岗位输出（.gitkeep）
├── resume_parser/            # 简历解析
├── resume_parser_example.py
├── config.json.example
├── requirements.txt          # 岗位模块依赖
└── README_structure.md       # 岗位模块专文
```

---

## 岗位结构化 + 去重（快速开始）

```bash
pip install -r requirements.txt
copy config.json.example config.json   # 填入 llm_api_key，勿提交
python pipeline/run_pipeline.py
```

输出：`data/output/all_positions.csv`、`all_positions.json`。

上传后端（可选，需配置 `backend_base_url`）：

```bash
python pipeline/upload_to_backend.py
```

更多说明见 [README_structure.md](README_structure.md)。

---

## 简历解析模块（Resume Parser）

支持从 PDF、Word、图片简历中提取关键信息，调用 DeepSeek 输出结构化 JSON。

### 目录

```
resume_parser/
├── extractors/     # docx / pdf / image
├── llm/            # DeepSeek 客户端
├── ocr/            # PaddleOCR
├── parser.py
├── prompt.py
└── requirements.txt
resume_parser_example.py
```

### 快速开始

```bash
pip install -r resume_parser/requirements.txt
# 环境变量 DEEPSEEK_API_KEY，或项目根目录 .env
python resume_parser_example.py
```

---

## 配置与安全

- `config.json`、`.env` 含 API Key，**已 gitignore，勿提交**。
- 仅提交 `config.json.example` 占位配置。
- 大批量 Markdown（`公众号文章/`）、运行日志、`data/output/*.csv` 勿提交。

---

## License

见 [LICENSE](LICENSE).
