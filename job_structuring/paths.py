"""项目路径与可配置输出位置（由 config.json 或 pipeline 注入）。"""
from __future__ import annotations

import os
from typing import Any, Optional

# FusionCareer-Algorithm 仓库根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

DEFAULT_ARTICLES_DIR = os.path.join(DATA_DIR, "articles")
LEGACY_ARTICLES_DIR = os.path.join(PROJECT_ROOT, "公众号文章")

CONFIG_FILE = "config.json"
CSV_BASENAME = "all_positions.csv"
JSON_BASENAME = "all_positions.json"
XLSX_BASENAME = "all_positions.xlsx"
SKIP_LOG_BASENAME = "non_recruitment.log"

_runtime: dict[str, Any] = {}


def configure(config: Optional[dict] = None) -> None:
    """由 pipeline / CLI 在启动时注入 config，用于覆盖 articles_dir、输出路径等。"""
    global _runtime
    _runtime = dict(config or {})


def _resolve_under_root(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def config_path() -> str:
    return os.path.join(PROJECT_ROOT, CONFIG_FILE)


def articles_dir() -> str:
    custom = (_runtime.get("articles_dir") or "").strip()
    if custom:
        return _resolve_under_root(custom)
    return DEFAULT_ARTICLES_DIR


def _dir_has_markdown(dir_path: str) -> bool:
    if not os.path.isdir(dir_path):
        return False
    for root, _, files in os.walk(dir_path):
        if "__MACOSX" in root.replace("\\", "/"):
            continue
        for name in files:
            if name.startswith("._"):
                continue
            if name.lower().endswith(".md"):
                return True
    return False


def resolve_articles_dir() -> str:
    """优先含 .md 的目录：config/data/articles，否则回退根目录「公众号文章」。"""
    primary = articles_dir()
    if _dir_has_markdown(primary):
        return primary
    if _dir_has_markdown(LEGACY_ARTICLES_DIR):
        return LEGACY_ARTICLES_DIR
    if os.path.isdir(primary):
        return primary
    if os.path.isdir(LEGACY_ARTICLES_DIR):
        return LEGACY_ARTICLES_DIR
    return primary


def csv_path() -> str:
    custom = (_runtime.get("output_csv") or "").strip()
    if custom:
        return _resolve_under_root(custom)
    return os.path.join(OUTPUT_DIR, CSV_BASENAME)


def json_path() -> str:
    custom = (_runtime.get("output_json") or "").strip()
    if custom:
        return _resolve_under_root(custom)
    return os.path.join(OUTPUT_DIR, JSON_BASENAME)


def xlsx_path() -> str:
    custom = (_runtime.get("output_xlsx") or "").strip()
    if custom:
        return _resolve_under_root(custom)
    return os.path.join(OUTPUT_DIR, XLSX_BASENAME)


def skip_log_path() -> str:
    custom = (_runtime.get("skip_log") or "").strip()
    if custom:
        return _resolve_under_root(custom)
    return os.path.join(LOGS_DIR, SKIP_LOG_BASENAME)


def ensure_project_dirs() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(articles_dir(), exist_ok=True)
