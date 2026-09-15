"""管理员端智能岗位解析 HTTP 服务。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from job_structuring.admin_parse import parse_job_text

app = FastAPI(title="FusionCareer Job Parse", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobParseRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, description="岗位原文")
    options: Optional[dict[str, Any]] = None


class JobParseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[dict[str, Any]] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/job/parse", response_model=JobParseResponse)
def parse_job(req: JobParseRequest):
    try:
        data = parse_job_text(req.raw_text)
        if data.get("meta", {}).get("error") == "llm_unavailable":
            return JobParseResponse(code=503, message="LLM unavailable", data=data)
        if data.get("meta", {}).get("error") == "invalid_json":
            return JobParseResponse(code=502, message="invalid model json", data=data)
        return JobParseResponse(data=data)
    except Exception as e:
        return JobParseResponse(code=500, message=str(e), data=None)
