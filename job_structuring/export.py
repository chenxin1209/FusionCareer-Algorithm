"""结构化结果导出（CSV → JSON / Excel），不改变抽取与去重算法。"""
from __future__ import annotations

import csv
import json
import os
from typing import Optional

from job_structuring import paths
from job_structuring.engine import POSITION_FIELDNAMES, format_position_row


def export_positions_json(
    csv_path: Optional[str] = None,
    json_path: Optional[str] = None,
) -> str:
    """将岗位 CSV 导出为 JSON 数组，返回生成的 json 绝对路径。"""
    csv_path = csv_path or paths.csv_path()
    json_path = json_path or paths.json_path()

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"未找到 CSV: {csv_path}")

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(format_position_row(raw))

    parent = os.path.dirname(json_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    return os.path.abspath(json_path)
