# FusionCareer-Algorithm

复旦大学新闻学院就业智能体 **算法侧**：公众号抓取 → 岗位结构化 → 人岗匹配。

| 模块 | 目录 | 说明 |
|------|------|------|
| **公众号爬虫** | `wechat_crawler/` | 登录后台做 7–8 月全量；无登录时抓公开链接 |
| **岗位结构化 + 过滤** | `job_structuring/`、`pipeline/` | Markdown → JobPost；筛掉学院未开设专业 |
| **人岗匹配** | `matching/`、`pipeline/run_eval.py` | embedding 相似度；可选 LLM 打分 |
| **简历解析** | `resume_parser/` | PDF/Word/图片 → 结构化 JSON |

---

## 评测一条龙（抓取 → 结构化 → 匹配）

```bash
pip install -r requirements.txt

# 1) 无公众平台登录：抓公开招聘文
python wechat_crawler/fetch_public.py

# 2) 有 token/cookie：抓监测清单 2026-07-01 ~ 2026-08-31
#    cp wechat_crawler/config.example.json wechat_crawler/config.json
#    python wechat_crawler/wechat_crawler.py.py range --since 2026-07-01 --until 2026-08-31

# 3) 岗位结构化（需 DEEPSEEK_API_KEY；文章放 data/articles/）
cp config.json.example config.json   # 填 llm_api_key
python pipeline/run_pipeline.py

# 4) 人岗匹配：把老师给的结构化简历 JSON 放到 data/resumes/
python pipeline/run_eval.py --resumes data/resumes --jobs data/output/all_positions.json
```

无 DeepSeek Key 时，可用已整理的测试岗位池直接匹配：

```bash
python pipeline/run_eval.py \
  --resumes data/resumes \
  --jobs sample_data/output/harvested_jobs.json
```

老师简历请放 `data/resumes/*.json`（已 gitignore，不会提交）。字段与 `resume_parser` 的 `fc_user_profile` / `fc_resume` 对齐即可，支持「一个文件一份」或 JSON 数组。

---

## 岗位结构化 + 去重

```bash
pip install -r requirements.txt
cp config.json.example config.json
python pipeline/run_pipeline.py
```

输出：`data/output/all_positions.csv`、`all_positions.json`。

---

## 简历解析

```bash
pip install -r resume_parser/requirements.txt
export DEEPSEEK_API_KEY=sk-...
python resume_parser_example.py
```

---

## 配置与安全

- `config.json`、`.env`、老师真实简历 **勿提交**。
- 公众平台 `token`/`cookie` 只放在 `wechat_crawler/config.json`。
