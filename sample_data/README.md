# sample_data

本目录为 **可提交 Git 的小样本**，用于：

- 新同事了解 Markdown 输入格式
- 本地 dry-run / 单测（不依赖完整 `公众号文章/`）
- 对照 `all_positions` 输出字段

**请勿**将大批量爬虫文章或全量 `all_positions.csv` 放在此目录外并提交。

## 使用方式

```bash
# 将 config.json 中 articles_dir 临时指向样本（或复制文件到 data/articles/）
python pipeline/run_pipeline.py
```

样本输出可参考 `output/all_positions_sample.csv` / `.json`。
