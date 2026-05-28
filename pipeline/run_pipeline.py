#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
岗位结构化流水线（统一入口）

原始 Markdown → LLM 结构化 → 去重 → data/output/all_positions.csv + .json

用法（在仓库根目录）:
  python pipeline/run_pipeline.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from job_structuring import paths
from job_structuring.engine import deduplicate_csv_file, load_config, run_batch_dir
from job_structuring.export import export_positions_json

_PIPELINE_LOG = os.path.join(paths.LOGS_DIR, "pipeline.log")


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(paths.LOGS_DIR, exist_ok=True)
    with open(_PIPELINE_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run() -> int:
    paths.ensure_project_dirs()
    config = load_config()
    paths.configure(config)

    articles_dir = paths.resolve_articles_dir()
    if not os.path.isdir(articles_dir):
        _log(f"文章目录不存在: {articles_dir}")
        _log("请将 Markdown 放入 data/articles/，或在 config.json 设置 articles_dir")
        return 1

    csv_out = paths.csv_path()
    json_out = paths.json_path()

    _log("========== pipeline start ==========")
    _log(f"articles: {articles_dir}")
    _log(f"csv: {csv_out}")
    _log(f"json: {json_out}")

    run_batch_dir(articles_dir, config)

    if not os.path.isfile(csv_out):
        _log("未生成 CSV（可能无有效岗位或未配置 llm_api_key / DEEPSEEK_API_KEY）")
        _log("========== pipeline end ==========")
        return 0

    before, after = deduplicate_csv_file(csv_out)
    _log(f"CSV dedup: {before} -> {after} rows")

    json_path = export_positions_json(csv_path=csv_out, json_path=json_out)
    _log(f"JSON exported: {json_path}")
    _log("========== pipeline end ==========")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
