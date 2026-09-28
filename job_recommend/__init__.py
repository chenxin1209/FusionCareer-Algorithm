"""人岗推荐：多轮问询 → 筛选 JSON → 后端拉岗 → LLM 排序。"""
from job_recommend.dialogue import RecommendTurn, next_turn
from job_recommend.filters import JobFilterQuery, filter_to_backend_payload
from job_recommend.rank import rank_jobs

__all__ = [
    "RecommendTurn",
    "next_turn",
    "JobFilterQuery",
    "filter_to_backend_payload",
    "rank_jobs",
]
