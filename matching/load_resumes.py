"""加载老师提供的结构化简历（JSON 对象 / 数组 / 每文件一份）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_list(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("resumes", "data", "items"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return [data]
    return []


def load_resumes(path: str) -> list[dict]:
    p = Path(path)
    if p.is_file():
        return _as_list(json.loads(p.read_text(encoding="utf-8")))
    if p.is_dir():
        out: list[dict] = []
        for fp in sorted(p.glob("*.json")):
            out.extend(_as_list(json.loads(fp.read_text(encoding="utf-8"))))
        return out
    raise FileNotFoundError(f"找不到简历: {path}")
