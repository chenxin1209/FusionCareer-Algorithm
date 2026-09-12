"""人岗 embedding 匹配：优先 OpenAI 兼容 embedding API，否则字符 n-gram TF-IDF。"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import numpy as np
import requests

from matching.text_builder import job_id, job_to_match_text, resume_to_match_text


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class EmbeddingBackend:
    def __init__(self, config: dict) -> None:
        self.model = (config.get("embedding_model") or os.environ.get("EMBEDDING_MODEL") or "").strip()
        self.base_url = (config.get("embedding_base_url") or os.environ.get("EMBEDDING_BASE_URL") or "").rstrip("/")
        self.api_key = (
            config.get("embedding_api_key")
            or os.environ.get("EMBEDDING_API_KEY")
            or ""
        ).strip()
        self.kind = "openai_compatible" if (self.base_url and self.model) else "lexical_tfidf"

    def embed_texts(self, texts: list[str]) -> tuple[np.ndarray, dict[str, Any]]:
        t0 = time.perf_counter()
        if self.kind == "openai_compatible":
            vecs = self._embed_openai(texts)
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer

            matrix = TfidfVectorizer(analyzer="char", ngram_range=(2, 4)).fit_transform(texts)
            vecs = np.asarray(matrix.toarray(), dtype=np.float32)
        return vecs, {
            "backend": self.kind,
            "model": self.model or "char-ngram-tfidf",
            "elapsedMs": int((time.perf_counter() - t0) * 1000),
            "dim": int(vecs.shape[1]) if vecs.size else 0,
        }

    def _embed_openai(self, texts: list[str]) -> np.ndarray:
        url = f"{self.base_url}/embeddings"
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        items = sorted((r.json().get("data") or []), key=lambda x: int(x.get("index") or 0))
        return np.asarray([it.get("embedding") or [] for it in items], dtype=np.float32)


def match_by_embedding(
    resume: dict[str, Any],
    jobs: list[dict[str, Any]],
    config: Optional[dict] = None,
    *,
    top_k: int = 10,
) -> dict[str, Any]:
    config = config or {}
    if not jobs:
        return {"method": "embedding", "results": [], "metrics": {}}
    texts = [resume_to_match_text(resume)] + [job_to_match_text(j) for j in jobs]
    vecs, meta = EmbeddingBackend(config).embed_texts(texts)
    scored = []
    for i, job in enumerate(jobs):
        scored.append({
            "jobId": job_id(job, i),
            "companyName": job.get("companyName") or "",
            "positionName": job.get("positionName") or "",
            "score": round(_cosine(vecs[0], vecs[i + 1]), 4),
            "job": job,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    k = max(1, int(top_k or 10))
    return {"method": "embedding", "results": scored[:k], "metrics": {**meta, "jobPoolSize": len(jobs), "topK": k}}
