"""推荐对话 / 排序 HTTP，供 Agent 或 Java 转发。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from job_recommend.dialogue import next_turn
from job_recommend.rank import rank_jobs

app = FastAPI(title="FusionCareer Job Recommend", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TurnRequest(BaseModel):
    user_text: str = ""
    slots: Optional[dict[str, Any]] = None
    resume: Optional[dict[str, Any]] = None
    # 选项卡片回传：{"recruitType":"BIG_INTERNSHIP","jobCategory":"ENTERPRISE"}
    selections: Optional[dict[str, Any]] = None


class RankRequest(BaseModel):
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    slots: Optional[dict[str, Any]] = None
    resume: Optional[dict[str, Any]] = None
    use_llm: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/job/recommend/turn")
def recommend_turn(req: TurnRequest):
    turn = next_turn(req.user_text, req.slots, req.resume, req.selections)
    return {"code": 200, "message": "success", "data": turn.to_dict()}


@app.post("/internal/job/recommend/rank")
def recommend_rank(req: RankRequest):
    data = rank_jobs(req.jobs, req.slots, req.resume, use_llm=req.use_llm)
    return {"code": 200, "message": "success", "data": data}
