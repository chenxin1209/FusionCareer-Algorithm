"""岗位 Markdown → 结构化 CSV/JSON（LLM 抽取 + 去重）。"""
from job_structuring.engine import (
    PositionDedupIndex,
    deduplicate_csv_file,
    export_positions_xlsx,
    load_config,
    process_new_markdown,
    run_batch_dir,
)
from job_structuring.export import export_positions_json
from job_structuring import paths

__all__ = [
    "paths",
    "load_config",
    "process_new_markdown",
    "run_batch_dir",
    "deduplicate_csv_file",
    "export_positions_json",
    "export_positions_xlsx",
    "PositionDedupIndex",
]
