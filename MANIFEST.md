# 文件清单：岗位结构化 + 去重模块

本目录从 `FusionCareer-Algorithm` 中整理出的 **你负责部分**，便于与远程仓库其他同事更新（如 `resume_parser`）独立保存、后续再合并。

整理时间：2026-05-28

---

## 一、本目录包含（你的模块）

| 路径 | 说明 |
|------|------|
| `job_structuring/engine.py` | **核心**：LLM 抽取、枚举映射、去重、`structure_data` 全部逻辑 |
| `job_structuring/paths.py` | `data/`、`logs/` 路径解析 |
| `job_structuring/export.py` | CSV → JSON 导出 |
| `job_structuring/__init__.py` | 模块对外 API |
| `structure_data.py` | CLI 兼容入口（转发 `engine.main`） |
| `pipeline/run_pipeline.py` | 推荐一键流水线 |
| `pipeline/__init__.py` | 包占位 |
| `config.json.example` | LLM 与路径配置模板（**无真实 Key**） |
| `requirements.txt` | `requests`、`openpyxl` |
| `sample_data/` | 小样本 Markdown + 示例 CSV/JSON |
| `data/articles/.gitkeep` | 输入目录占位 |
| `data/output/.gitkeep` | 输出目录占位 |
| `README_structure.md` | 模块使用说明 |
| `.gitignore` | 本模块 Git 忽略规则 |

**运行：**

```bash
pip install -r requirements.txt
copy config.json.example config.json
python pipeline/run_pipeline.py
```

---

## 二、刻意未放入本目录（仍属「结构化」但偏上传 / 非核心）

| 原仓库路径 | 原因 |
|------------|------|
| `job_structuring/upload_backend.py` | 后端批量上传，非「结构化+去重」核心 |
| `pipeline/upload_to_backend.py` | 同上 |

若需要上传后端，可从原 `FusionCareer-Algorithm` 单独拷贝，或等合并进新仓库后再加。

---

## 三、原仓库中不属于你负责的内容（勿与本模块混淆）

远程 `origin/main` 当前主要为其他同事维护，例如：

| 路径 | 负责人/用途 |
|------|-------------|
| `resume_parser/` | 简历解析（PDF/DOCX/OCR + LLM） |
| `resume_parser_example.py` | 简历示例脚本 |
| `resume_parser/requirements.txt` | 简历模块依赖（与岗位结构化不同） |
| 根目录 `README.md`（远程版） | 全仓库说明，含简历等 |
| `公众号文章/` | 爬虫产出的大量 Markdown（本地数据，非代码） |
| `config.json` | 本地密钥，**勿复制** |
| `logs/`、`data/output/*.csv` | 运行产物 |

建议：拉取远程最新代码后，将 **本目录** 整体复制回 `FusionCareer-Algorithm` 对应路径，避免覆盖 `resume_parser/`。

---

## 四、合并回更新后仓库的建议步骤

```bash
cd FusionCareer-Algorithm
git pull origin main

# 从本目录覆盖/添加岗位结构化文件（示例）
xcopy /E /Y ..\FusionCareer-JobPost-Structuring\job_structuring job_structuring\
xcopy /E /Y ..\FusionCareer-JobPost-Structuring\pipeline\run_pipeline.py pipeline\
copy ..\FusionCareer-JobPost-Structuring\structure_data.py .
copy ..\FusionCareer-JobPost-Structuring\config.json.example .
# 合并 requirements.txt 时保留 resume_parser 与 job_structuring 双方依赖
```

合并 `requirements.txt` 时请 **合并依赖行**，不要整文件覆盖远程简历模块的 pin 版本。
