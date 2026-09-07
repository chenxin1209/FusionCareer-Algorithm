"""岗位 Markdown → 结构化 CSV/JSON（LLM 抽取 + 去重 + 学院过滤）。"""
from job_structuring.engine import (
    PositionDedupIndex,
    deduplicate_csv_file,
    export_positions_xlsx,
    load_config,
    process_new_markdown,
    run_batch_dir,
)
from job_structuring.export import export_positions_json
from job_structuring.filter import filter_jobs, refilter_structured_files, should_keep_job
from job_structuring.ingest import adapt_external_row, load_structured_any
from job_structuring.normalize import collect_facets, normalize_job_row
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
    "filter_jobs",
    "refilter_structured_files",
    "should_keep_job",
    "normalize_job_row",
    "collect_facets",
    "load_structured_any",
    "adapt_external_row",
]
