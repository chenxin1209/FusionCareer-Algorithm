#!/usr/bin/env python3
"""人岗匹配评测：结构化简历 × 结构化岗位。

  python pipeline/run_eval.py
  python pipeline/run_eval.py --resumes data/resumes --jobs data/output/all_positions.json
  python pipeline/run_eval.py --method both   # 需 DEEPSEEK_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from job_structuring.engine import load_config
from job_structuring.filter import filter_jobs, log_dropped
from job_structuring.normalize import normalize_job_row
from matching.embedding import match_by_embedding
from matching.load_resumes import load_resumes, summarize_resumes


def _load_jobs(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("岗位 JSON 须为数组")
    return [normalize_job_row(dict(x)) for x in data if isinstance(x, dict)]


def main() -> int:
    p = argparse.ArgumentParser(description="人岗匹配评测")
    p.add_argument("--resumes", default=os.path.join(PROJECT_ROOT, "data", "resumes"))
    p.add_argument("--jobs", default=os.path.join(PROJECT_ROOT, "data", "output", "all_positions.json"))
    p.add_argument("--method", default="embedding", choices=("embedding", "llm", "both"))
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--no-filter", action="store_true")
    p.add_argument("--out", default=os.path.join(PROJECT_ROOT, "logs", "match_eval.json"))
    args = p.parse_args()

    cfg = load_config()
    if not os.path.isfile(args.jobs):
        print(f"找不到岗位文件: {args.jobs}")
        print("请先抓取并结构化，或使用 sample_data/output/all_positions_sample.json")
        return 1

    resumes = load_resumes(args.resumes)
    summary = summarize_resumes(resumes)
    jobs = _load_jobs(args.jobs)
    dropped = []
    if not args.no_filter:
        jobs, dropped = filter_jobs(jobs)
        if dropped:
            log_dropped(dropped, os.path.join(PROJECT_ROOT, "logs", "filtered_jobs.log"))

    print(
        f"简历 {summary['count']} 份（无姓名 {summary['unnamed']}），"
        f"岗位池 {len(jobs)} 条（过滤删除 {len(dropped)}）；"
        f"实习填充率 {summary['fillRate'].get('internship', 0):.0%}，"
        f"技能 {summary['fillRate'].get('skills', 0):.0%}，"
        f"专业 {summary['fillRate'].get('major', 0):.0%}"
    )
    if not resumes or not jobs:
        print("简历或岗位为空，无法匹配")
        return 1

    reports = []
    for i, resume in enumerate(resumes, 1):
        name = resume.get("real_name") or f"resume-{i}"
        print(f"\n===== {name} =====")
        rec = {"resume": name, "embedding": None, "llm": None}
        emb = match_by_embedding(resume, jobs, cfg, top_k=args.top_k)
        rec["embedding"] = {
            "metrics": emb.get("metrics"),
            "top": [
                {
                    "companyName": x.get("companyName"),
                    "positionName": x.get("positionName"),
                    "score": x.get("score"),
                }
                for x in emb.get("results") or []
            ],
        }
        for x in rec["embedding"]["top"][:5]:
            print(f"  [emb {x['score']:.3f}] {x['companyName']} / {x['positionName']}")

        if args.method in ("llm", "both"):
            from matching.llm_score import match_by_llm

            try:
                llm = match_by_llm(resume, jobs, cfg, top_k=args.top_k)
                rec["llm"] = {
                    "metrics": llm.get("metrics"),
                    "top": [
                        {
                            "companyName": x.get("companyName"),
                            "positionName": x.get("positionName"),
                            "score": x.get("score"),
                            "recommendation": x.get("recommendation"),
                            "rationale": x.get("rationale"),
                        }
                        for x in llm.get("results") or []
                    ],
                }
                for x in rec["llm"]["top"][:5]:
                    print(f"  [llm {x['score']}] {x['companyName']} / {x['positionName']} {x.get('recommendation')}")
            except Exception as e:
                rec["llmError"] = str(e)
                print(f"  LLM 打分跳过: {e}")
        reports.append(rec)

    payload = {
        "comparedAt": datetime.now().isoformat(timespec="seconds"),
        "jobPoolSize": len(jobs),
        "filteredOut": len(dropped),
        "resumeCount": len(resumes),
        "method": args.method,
        "reports": reports,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    top1 = Counter()
    scores: list[float] = []
    backend = ""
    for rec in reports:
        emb = rec.get("embedding") or {}
        if not backend:
            backend = ((emb.get("metrics") or {}).get("backend") or "")
        top = emb.get("top") or []
        if not top:
            continue
        hit = top[0]
        top1[f"{hit.get('companyName') or ''} / {hit.get('positionName') or ''}"] += 1
        try:
            scores.append(float(hit.get("score") or 0))
        except (TypeError, ValueError):
            pass
    print("\n----- Top-1 分布 -----")
    if backend:
        print(f"backend: {backend}")
    for label, n in top1.most_common():
        print(f"  {n:3d}  {label}")
    if scores:
        print(
            "Top-1 分数 "
            f"min={min(scores):.3f} median={statistics.median(scores):.3f} "
            f"max={max(scores):.3f}"
        )
    print(f"\n已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
