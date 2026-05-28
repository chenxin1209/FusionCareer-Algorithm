#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将结构化 CSV/JSON 批量上传至 FusionCareer 后端 JobPost API。

用法（仓库根目录）:
  python pipeline/upload_to_backend.py
  python pipeline/upload_to_backend.py --dry-run
  python pipeline/upload_to_backend.py --input-json data/output/all_positions.json
  python pipeline/upload_to_backend.py --no-fetch-existing
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from job_structuring import paths
from job_structuring.engine import load_config
from job_structuring.upload_backend import upload_structured_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="上传结构化岗位至后端 JobPost API")
    parser.add_argument(
        "--input-json",
        help="结构化 JSON 路径（默认 config output_json）",
    )
    parser.add_argument(
        "--input-csv",
        help="结构化 CSV 路径（默认 config output_csv；无 JSON 时使用）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅解析与去重，不实际请求后端",
    )
    parser.add_argument(
        "--no-fetch-existing",
        action="store_true",
        help="不拉取后端已有岗位，仅依赖本地 upload_state 去重",
    )
    args = parser.parse_args()

    paths.ensure_project_dirs()
    config = load_config()
    paths.configure(config)

    try:
        stats = upload_structured_jobs(
            config,
            json_path=args.input_json,
            csv_path=args.input_csv,
            dry_run=args.dry_run,
            fetch_existing=False if args.no_fetch_existing else None,
        )
    except ValueError as e:
        print(f"[upload] 配置错误: {e}")
        return 1
    except FileNotFoundError as e:
        print(f"[upload] {e}")
        return 1
    except Exception as e:
        print(f"[upload] 失败: {e}")
        return 1

    if stats.get("failed_batches", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
