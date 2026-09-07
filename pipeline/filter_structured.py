#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对【已经结构化好】的岗位表做新闻传播方向筛选，不调用 LLM。

用法（仓库根目录）:
  python pipeline/filter_structured.py --input 朋友的岗位.xlsx
  python pipeline/filter_structured.py --input data/incoming/jobs.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from job_structuring import paths
from job_structuring.filter import filter_jobs, log_dropped
from job_structuring.ingest import detect_columns, load_structured_any, write_rows_csv, write_rows_json
from job_structuring.normalize import collect_facets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="筛选新闻传播相关岗位（不跑 LLM）")
    parser.add_argument("--input", "-i", required=True, help="朋友的结构化文件：csv / json / xlsx")
    parser.add_argument(
        "--out-dir",
        default="",
        help="输出目录，默认 data/output",
    )
    parser.add_argument("--prefix", default="journalism_jobs", help="输出文件名前缀")
    args = parser.parse_args(argv)

    paths.ensure_project_dirs()
    out_dir = args.out_dir.strip() or paths.OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(paths.LOGS_DIR, exist_ok=True)

    rows = load_structured_any(args.input)
    cols = detect_columns(rows)
    if not cols.get("positionName"):
        print("警告: 没有识别到「岗位名称」列，筛选会偏严。请确认表头是否为 岗位名称 / positionName / 职位")
        print("文件列名:", cols.get("keysInFile"))

    kept, dropped = filter_jobs(rows)
    kept_csv = os.path.join(out_dir, f"{args.prefix}.csv")
    kept_json = os.path.join(out_dir, f"{args.prefix}.json")
    drop_json = os.path.join(paths.LOGS_DIR, "filtered_out_jobs.json")
    drop_log = os.path.join(paths.LOGS_DIR, "filtered_jobs.log")
    stats_path = os.path.join(paths.LOGS_DIR, "filter_stats.json")

    write_rows_csv(kept_csv, kept)
    write_rows_json(kept_json, kept)
    write_rows_json(drop_json, dropped)
    log_dropped(dropped, drop_log)

    reasons = Counter(str(d.get("_filterReason") or "unknown") for d in dropped)
    stats = {
        "finishedAt": datetime.now().isoformat(timespec="seconds"),
        "input": os.path.abspath(args.input),
        "total": len(rows),
        "kept": len(kept),
        "dropped": len(dropped),
        "columnsMapped": cols,
        "dropReasons": reasons.most_common(20),
        "facets": collect_facets(kept),
        "keptCsv": os.path.abspath(kept_csv),
        "keptJson": os.path.abspath(kept_json),
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"输入 {len(rows)} 条 → 保留 {len(kept)}，删除 {len(dropped)}")
    print(f"保留: {kept_csv}")
    print(f"删除明细: {drop_json}")
    print(f"统计: {stats_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
