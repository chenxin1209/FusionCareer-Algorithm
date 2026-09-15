"""管理员端智能岗位解析，挂到现有算法服务上。"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_structuring.admin_parse import parse_job_text

router = APIRouter(prefix="/internal/job", tags=["internal-job"])


class JobParseRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, description="岗位原文")
    options: Optional[dict[str, Any]] = None


class JobParseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[dict[str, Any]] = None


@router.post("/parse", response_model=JobParseResponse)
def parse_job(req: JobParseRequest):
    try:
        data = parse_job_text(req.raw_text)
        err = (data.get("meta") or {}).get("error")
        if err == "llm_unavailable":
            return JobParseResponse(code=503, message="LLM unavailable", data=data)
        if err == "invalid_json":
            return JobParseResponse(code=502, message="invalid model json", data=data)
        if err == "empty_text":
            return JobParseResponse(code=400, message="empty text", data=data)
        return JobParseResponse(data=data)
    except Exception as e:
        return JobParseResponse(code=500, message=str(e), data=None)
