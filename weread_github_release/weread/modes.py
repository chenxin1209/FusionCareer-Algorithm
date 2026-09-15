"""bootstrap / daily 业务模式。"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List

from .client import fetch_articles
from .paths import (
    HISTORY_FILE,
    ROOT,
    beijing_now,
    get_daily_increment_dir,
    load_json,
    save_json,
)
from .storage import is_valid_article_link, save_url_to_md


def write_daily_summary_md(
    summary_path: str,
    stats: Dict[str, int],
    run_time_str: str,
    daily_dir_name: str,
    articles_base_dir: str,
) -> None:
    total = sum(stats.values())
    active = [(n, c) for n, c in stats.items() if c > 0]
    lines = [
        "# 公众号新增推文统计（微信读书版）",
        "",
        f"**统计日期（北京时间）**：{beijing_now().strftime('%Y-%m-%d')}",
        f"**执行时间**：{run_time_str}",
        f"**增量目录**：`{daily_dir_name}`",
        f"**新增合计**：{total} 篇",
        f"**有更新的公众号数**：{len(active)} / {len(stats)}",
        "",
        "## 分号统计",
        "",
        "| 序号 | 公众号 | 新增篇数 |",
        "|------|--------|----------|",
    ]
    for i, (name, count) in enumerate(
        sorted(stats.items(), key=lambda x: (-x[1], x[0])), start=1
    ):
        lines.append(f"| {i} | {name} | {count} |")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本统计由 `wechat_crawler_weread.py daily` 生成。",
            f"- 主存档目录：`{articles_base_dir}/`",
            "- 鉴权方式：微信读书扫码。",
        ]
    )
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _history_entry(article: Dict[str, Any], account: str) -> Dict[str, Any]:
    return {
        "title": article.get("title"),
        "link": article.get("link"),
        "create_time": article.get("create_time"),
        "account": account,
    }


def mode_bootstrap(
    credentials: dict,
    fakeids: List[str],
    account_names: Dict[int, str],
    article_limit: int,
    articles_base_dir: str,
    config: dict,
) -> None:
    print(f"--- Bootstrap（微信读书）：每号最新 {article_limit} 条 ---")
    print(f"主存档目录: {articles_base_dir}/")
    history = load_json(HISTORY_FILE)
    os.makedirs(articles_base_dir, exist_ok=True)

    for idx, fakeid in enumerate(fakeids):
        name = account_names.get(idx, "Unknown_Account")
        print(f"[{idx + 1}/{len(fakeids)}] Bootstrap: {name} ({fakeid})")
        try:
            articles = fetch_articles(credentials, fakeid, max_groups=max(article_limit, 10))
        except Exception as e:
            print(f"  [Error] 列表失败: {e}")
            time.sleep(random.uniform(8, 12))
            continue

        collected = [a for a in articles if is_valid_article_link(a.get("link"))][:article_limit]
        if not collected:
            print("  未返回可解析文章")
        else:
            kept = []
            for article in collected:
                status = save_url_to_md(
                    article, name, articles_base_dir, config=config
                )
                if status in ("saved", "jump"):
                    kept.append(article)
            if kept:
                # 列表按新→旧，history 指向最新成功保留的一篇
                history[fakeid] = _history_entry(kept[0], name)
            print(f"  处理最新 {len(collected)} 篇（有效落盘/已存在 {len(kept)}）")

        if idx < len(fakeids) - 1:
            time.sleep(random.uniform(8, 15))

    save_json(HISTORY_FILE, history)
    print(f"--- Bootstrap 完成，已保存 {HISTORY_FILE.name} ---")


def mode_daily(
    credentials: dict,
    fakeids: List[str],
    account_names: Dict[int, str],
    articles_base_dir: str,
    config: dict,
) -> None:
    print("--- Daily（微信读书）：增量监测 ---")
    print(f"主存档目录: {articles_base_dir}/")
    history = load_json(HISTORY_FILE)
    run_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    daily_dir = None
    if config.get("daily_mirror_to_dated_folder", True):
        daily_dir = get_daily_increment_dir(config)
        os.makedirs(daily_dir, exist_ok=True)
        print(f"当日增量目录: {daily_dir}/")

    stats: Dict[str, int] = {}
    for idx, fakeid in enumerate(fakeids):
        name = account_names.get(idx, "Unknown_Account")
        print(f"[{idx + 1}/{len(fakeids)}] 检查: {name} ({fakeid})")
        last = history.get(fakeid, {})
        last_link = last.get("link")
        last_ts = int(last.get("create_time") or 0)

        if not last_link:
            print("  [Skip] history 中无记录，请先 bootstrap")
            stats[name] = 0
            time.sleep(2)
            continue

        try:
            articles = fetch_articles(credentials, fakeid, max_groups=12)
        except Exception as e:
            print(f"  [Error] 列表失败: {e}")
            stats[name] = 0
            time.sleep(random.uniform(8, 12))
            continue

        new_articles = []
        for article in articles:
            link = article.get("link")
            if not is_valid_article_link(link):
                continue
            ts = int(article.get("create_time") or 0)
            if link == last_link:
                break
            if last_ts and ts and ts < last_ts:
                break
            new_articles.append(article)

        saved = 0
        if not new_articles:
            print("  无新增")
        else:
            print(f"  发现 {len(new_articles)} 篇候选，开始下载…")
            confirmed = []
            for article in reversed(new_articles):
                status = save_url_to_md(
                    article,
                    name,
                    articles_base_dir,
                    mirror_base_dir=daily_dir,
                    config=config,
                )
                if status == "saved":
                    saved += 1
                    confirmed.append(article)
                elif status == "jump":
                    confirmed.append(article)
            # 仅在成功保存或本地已存在时推进 history，避免下载失败导致漏文
            if confirmed:
                confirmed_links = {c.get("link") for c in confirmed}
                if new_articles[0].get("link") in confirmed_links:
                    newest = new_articles[0]
                else:
                    newest = max(
                        confirmed, key=lambda a: int(a.get("create_time") or 0)
                    )
                history[fakeid] = _history_entry(newest, name)
            print(f"  完成: 新保存 {saved}")

        stats[name] = saved
        if idx < len(fakeids) - 1:
            time.sleep(random.uniform(8, 15))

    save_json(HISTORY_FILE, history)

    report_path = config.get("daily_report_path", "daily_report.jsonl")
    report_line = {
        "time": run_time,
        "source": "weread",
        "total_new": sum(stats.values()),
        "by_account": stats,
    }
    if daily_dir:
        report_line["daily_folder"] = os.path.basename(daily_dir)
    with open(ROOT / report_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(report_line, ensure_ascii=False) + "\n")

    if daily_dir:
        summary_name = config.get("daily_summary_filename", "新增统计.md")
        summary_path = os.path.join(daily_dir, summary_name)
        write_daily_summary_md(
            summary_path, stats, run_time, os.path.basename(daily_dir), articles_base_dir
        )
        print(f"统计文件: {summary_path}")

    print(f"--- Daily 完成，合计新增 {sum(stats.values())} 篇 ---")
