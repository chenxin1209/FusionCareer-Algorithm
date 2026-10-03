#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按日 × 数据源 统计岗位提取线上情况（老师 2026-09 紧急需求）。

统计口径
--------
1. 文件数量：爬虫落到各数据源目录下的文章文件（.md/.html/.txt/.json 等）。
2. 岗位数量：从结构化结果（CSV/JSON/SQLite）中按来源聚合的岗位条数。
3. 新闻学院相关：岗位名称/描述/专业要求/岗位大类命中新闻传播关键词，或岗位大类为「新闻媒体」。

数据源
------
- 公众号：`公众号文章/<账号名>/`，以及 `YYYYMMDD新增/` 下按账号分子目录
- 官网：`官网文章/<站点名>/`
- 账号名即数据源名（复旦就业、武大就业…）

用法（在能读到数据根目录的机器上）::

  python pipeline/report_source_stats.py --root /data/wechat
  python pipeline/report_source_stats.py --root /data/wechat --out data/output/source_stats

Docker（Python 机）::

  docker cp pipeline/report_source_stats.py fc-python-agent-1:/tmp/report_source_stats.py
  docker exec fc-python-agent-1 python3 /tmp/report_source_stats.py --root /data/wechat --out /tmp/source_stats
  docker cp fc-python-agent-1:/tmp/source_stats ./source_stats
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional

ARTICLE_EXT = {".md", ".html", ".htm", ".txt", ".json", ".docx", ".pdf"}
SKIP_DIR_PREFIX = {".git", "__pycache__", "manifest"}
DAY_FOLDER_RE = re.compile(r"^(\d{8})新增$")

# 新闻学院开设方向的弱启发式：用于「相关岗位」计数，不是录取规则。
JOUR_HINTS = (
    "新闻",
    "传播",
    "广电",
    "广播电视",
    "广告",
    "出版",
    "编辑",
    "记者",
    "媒体",
    "融媒体",
    "新媒体",
    "传媒",
    "舆论",
    "主持",
    "播音",
    "影视",
    "纪录片",
    "公关",
    "品牌传播",
    "国际新闻",
    "网络与新媒体",
)
JOUR_CATEGORIES = {"新闻媒体", "NEWS_MEDIA", "MEDIA"}

Row = dict[str, Any]


def _is_article_file(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    return ext in ARTICLE_EXT


def _day_from_mtime(path: str) -> str:
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _day_from_folder(name: str) -> Optional[str]:
    m = DAY_FOLDER_RE.match(name)
    if not m:
        return None
    raw = m.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _walk_files(root: str) -> Iterable[str]:
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_PREFIX and not d.startswith(".")]
        for fn in filenames:
            if _is_article_file(fn):
                yield os.path.join(dirpath, fn)


def scan_archive_tree(base: str, source_type: str) -> list[Row]:
    """公众号文章/<源>/file 或 官网文章/<源>/file。"""
    rows: list[Row] = []
    if not os.path.isdir(base):
        return rows
    for source in sorted(os.listdir(base)):
        src_dir = os.path.join(base, source)
        if not os.path.isdir(src_dir) or source.startswith("."):
            continue
        for fp in _walk_files(src_dir):
            rows.append(
                {
                    "date": _day_from_mtime(fp),
                    "source_type": source_type,
                    "source_name": source,
                    "kind": "file",
                    "path": fp,
                }
            )
    return rows


def scan_daily_folders(root: str) -> list[Row]:
    """YYYYMMDD新增/ 下：若有子目录则子目录名=数据源，否则记为 daily_ungrouped。"""
    rows: list[Row] = []
    if not os.path.isdir(root):
        return rows
    for name in os.listdir(root):
        day = _day_from_folder(name)
        if not day:
            continue
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        subdirs = [
            d
            for d in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, d)) and not d.startswith(".")
        ]
        if subdirs:
            for src in subdirs:
                src_dir = os.path.join(folder, src)
                st = "official" if "官网" in src else "wechat"
                if src in ("官网文章", "公众号文章"):
                    for inner in scan_archive_tree(src_dir, "official" if src == "官网文章" else "wechat"):
                        inner["date"] = day
                        rows.append(inner)
                    continue
                for fp in _walk_files(src_dir):
                    rows.append(
                        {
                            "date": day,
                            "source_type": st,
                            "source_name": src,
                            "kind": "file",
                            "path": fp,
                        }
                    )
        else:
            for fp in _walk_files(folder):
                rows.append(
                    {
                        "date": day,
                        "source_type": "wechat",
                        "source_name": "daily_ungrouped",
                        "kind": "file",
                        "path": fp,
                    }
                )
    return rows


def load_daily_report(path: str) -> list[Row]:
    rows: list[Row] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = str(obj.get("time") or "")[:10]
            by_acc = obj.get("by_account") or {}
            if isinstance(by_acc, dict):
                for name, n in by_acc.items():
                    try:
                        cnt = int(n)
                    except (TypeError, ValueError):
                        cnt = 0
                    if cnt <= 0:
                        continue
                    rows.append(
                        {
                            "date": t,
                            "source_type": "wechat",
                            "source_name": str(name),
                            "kind": "report_files",
                            "count": cnt,
                        }
                    )
    return rows


def _text_blob(obj: dict) -> str:
    parts = []
    for k in (
        "positionName",
        "岗位名称",
        "companyName",
        "单位名称",
        "jobCategory",
        "岗位大类",
        "jobSubCategory",
        "专业要求",
        "majorRequirement",
        "岗位描述",
        "description",
        "reqMajor",
        "reqOther",
    ):
        v = obj.get(k)
        if v:
            parts.append(str(v))
    return " ".join(parts)


def is_journalism_related(obj: dict) -> bool:
    cat = str(obj.get("jobCategory") or obj.get("岗位大类") or "")
    if cat in JOUR_CATEGORIES or "新闻" in cat or "媒体" in cat:
        return True
    blob = _text_blob(obj)
    return any(h in blob for h in JOUR_HINTS)


def _source_from_job(obj: dict) -> tuple[str, str]:
    name = (
        obj.get("sourceName")
        or obj.get("account")
        or obj.get("公众号")
        or obj.get("source")
        or ""
    )
    url = str(obj.get("sourceUrl") or obj.get("source_md") or "")
    if not name:
        if "mp.weixin.qq.com" in url:
            name = "wechat_unknown"
        elif url:
            name = "web_unknown"
        else:
            name = "unknown"
    st = "wechat"
    if "官网" in str(name) or (url and "mp.weixin.qq.com" not in url and url.startswith("http")):
        if "mp.weixin.qq.com" not in url:
            st = "official"
    return st, str(name)


def _date_from_job(obj: dict) -> str:
    for k in ("extractedAt", "createdAt", "crawlDate", "date", "ts"):
        v = str(obj.get(k) or "")
        if len(v) >= 10 and v[4:5] == "-":
            return v[:10]
    return ""


def load_jobs_json(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("positions", "岗位列表", "jobs", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def load_jobs_csv(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sqlite_jobs(db_path: str) -> list[dict]:
    if not os.path.isfile(db_path):
        return []
    out: list[dict] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        prefer = [t for t in tables if re.search(r"job|position|post|struct", t, re.I)]
        use = prefer or tables
        for table in use:
            try:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            except sqlite3.Error:
                continue
            if not any(
                re.search(r"position|岗位|title|company|单位", c, re.I) for c in cols
            ):
                continue
            try:
                cur = conn.execute(f"SELECT * FROM {table}")
            except sqlite3.Error:
                continue
            for row in cur:
                d = {k: row[k] for k in row.keys()}
                d["_table"] = table
                out.append(d)
            if out:
                break
    finally:
        conn.close()
    return out


def sqlite_file_rows(db_path: str) -> list[Row]:
    """若库里有文章表，按账号+日期计文件。"""
    rows: list[Row] = []
    if not os.path.isfile(db_path):
        return rows
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return rows
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            if not re.search(r"article|post|wechat|file", table, re.I):
                continue
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            name_col = next((c for c in cols if re.search(r"account|source|gzh|公众号|name", c, re.I)), None)
            date_col = next((c for c in cols if re.search(r"date|time|created|ts", c, re.I)), None)
            if not name_col:
                continue
            q = f"SELECT {name_col}" + (f", {date_col}" if date_col else "") + f" FROM {table}"
            try:
                cur = conn.execute(q)
            except sqlite3.Error:
                continue
            for row in cur:
                day = ""
                if date_col:
                    day = str(row[date_col] or "")[:10]
                    if len(day) == 8 and day.isdigit():
                        day = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
                rows.append(
                    {
                        "date": day or "unknown",
                        "source_type": "wechat",
                        "source_name": str(row[name_col] or "unknown"),
                        "kind": "db_article",
                        "count": 1,
                    }
                )
    finally:
        conn.close()
    return rows


def dump_sqlite_schema(db_path: str, out_path: str) -> None:
    if not os.path.isfile(db_path):
        return
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        schema = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    with open(out_path, "w", encoding="utf-8") as f:
        for name, sql in schema:
            f.write(f"-- {name}\n{sql}\n\n")


def aggregate(file_rows: list[Row], jobs: list[dict]) -> list[Row]:
    files: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in file_rows:
        cnt = int(r.get("count") or 1)
        key = (r.get("date") or "unknown", r.get("source_type") or "", r.get("source_name") or "")
        files[key] += cnt

    job_n: dict[tuple[str, str, str], int] = defaultdict(int)
    jour_n: dict[tuple[str, str, str], int] = defaultdict(int)
    for job in jobs:
        st, name = _source_from_job(job)
        day = _date_from_job(job) or "unknown"
        key = (day, st, name)
        job_n[key] += 1
        if is_journalism_related(job):
            jour_n[key] += 1

    keys = set(files) | set(job_n) | set(jour_n)
    out = []
    for date, st, name in sorted(keys):
        out.append(
            {
                "date": date,
                "source_type": st,
                "source_name": name,
                "file_count": files.get((date, st, name), 0),
                "job_count": job_n.get((date, st, name), 0),
                "journalism_job_count": jour_n.get((date, st, name), 0),
            }
        )
    return out


def write_csv(path: str, rows: list[Row], fieldnames: list[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collect_jobs(root: str) -> list[dict]:
    jobs: list[dict] = []
    candidates = [
        os.path.join(root, "all_positions.json"),
        os.path.join(root, "output", "all_positions.json"),
        os.path.join(root, "all_positions.csv"),
        os.path.join(root, "output", "all_positions.csv"),
        os.path.join(root, "wechat.db"),
    ]
    for dirpath, _, filenames in os.walk(root):
        if dirpath.count(os.sep) - root.count(os.sep) > 3:
            continue
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            if fn.endswith(".json") and "position" in fn.lower():
                candidates.append(fp)
            if fn.endswith(".csv") and "position" in fn.lower():
                candidates.append(fp)
    seen = set()
    for fp in candidates:
        if fp in seen or not os.path.isfile(fp):
            continue
        seen.add(fp)
        if fp.endswith(".json"):
            jobs.extend(load_jobs_json(fp))
        elif fp.endswith(".csv"):
            jobs.extend(load_jobs_csv(fp))
        elif fp.endswith(".db"):
            jobs.extend(sqlite_jobs(fp))
    return jobs


def run(root: str, out_dir: str) -> int:
    root = os.path.abspath(root)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    file_rows: list[Row] = []
    file_rows.extend(scan_archive_tree(os.path.join(root, "公众号文章"), "wechat"))
    file_rows.extend(scan_archive_tree(os.path.join(root, "官网文章"), "official"))
    file_rows.extend(scan_daily_folders(root))
    file_rows.extend(load_daily_report(os.path.join(root, "daily_report.jsonl")))
    db = os.path.join(root, "wechat.db")
    file_rows.extend(sqlite_file_rows(db))
    dump_sqlite_schema(db, os.path.join(out_dir, "wechat_db_schema.sql"))

    jobs = collect_jobs(root)
    daily = aggregate(file_rows, jobs)

    write_csv(
        os.path.join(out_dir, "daily_source_stats.csv"),
        daily,
        [
            "date",
            "source_type",
            "source_name",
            "file_count",
            "job_count",
            "journalism_job_count",
        ],
    )

    # 数据源合计，便于删减低质量源
    totals: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"file_count": 0, "job_count": 0, "journalism_job_count": 0}
    )
    for r in daily:
        k = (r["source_type"], r["source_name"])
        for f in ("file_count", "job_count", "journalism_job_count"):
            totals[k][f] += int(r[f])
    tot_rows = [
        {
            "source_type": st,
            "source_name": name,
            **vals,
            "journalism_ratio": (
                round(vals["journalism_job_count"] / vals["job_count"], 4)
                if vals["job_count"]
                else 0
            ),
        }
        for (st, name), vals in sorted(totals.items())
    ]
    write_csv(
        os.path.join(out_dir, "source_totals.csv"),
        tot_rows,
        [
            "source_type",
            "source_name",
            "file_count",
            "job_count",
            "journalism_job_count",
            "journalism_ratio",
        ],
    )

    meta = {
        "root": root,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_events": len(file_rows),
        "jobs_loaded": len(jobs),
        "daily_rows": len(daily),
        "sources": len(tot_rows),
        "note": "journalism_job_count 为关键词启发式，需人工抽检后再删数据源",
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"wrote {out_dir}/daily_source_stats.csv")
    print(f"wrote {out_dir}/source_totals.csv")
    if os.path.isfile(db):
        print(f"wrote {out_dir}/wechat_db_schema.sql （对照表结构，便于补全岗位字段）")
    if not jobs:
        print("警告: 未读到岗位 JSON/CSV/SQLite，job_count 可能为 0。请把结构化结果路径告诉脚本或检查 wechat.db 表名。")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="按日×数据源统计爬虫文件与岗位提取")
    p.add_argument("--root", default="", help="数据根目录，如 /data/wechat")
    p.add_argument("--out", default="data/output/source_stats", help="输出目录")
    args = p.parse_args(argv)
    root = args.root.strip() or os.environ.get("WECHAT_DATA_ROOT", "")
    if not root:
        print("请指定 --root /data/wechat", file=sys.stderr)
        return 2
    if not os.path.isdir(root):
        print(f"目录不存在: {root}", file=sys.stderr)
        return 1
    return run(root, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
