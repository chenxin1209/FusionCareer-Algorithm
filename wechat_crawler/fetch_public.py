#!/usr/bin/env python3
"""
抓取公开网页为 Markdown（不需要公众平台 token/cookie）。

微信文章页 https://mp.weixin.qq.com/s/... 一般可直接打开；
公众号「历史消息列表」仍必须走 wechat_crawler.py.py range（需登录后台）。

用法（在 wechat_crawler/ 或仓库根目录）:
  python wechat_crawler/fetch_public.py --urls wechat_crawler/seed_urls.txt --out data/articles
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CRAWLER_FILE = ROOT / "wechat_crawler.py.py"


def _load_crawler():
    spec = importlib.util.spec_from_file_location("wechat_crawler_mod", CRAWLER_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clean_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title or "untitled").strip() or "untitled"


def _first(*matches):
    for m in matches:
        if m:
            return unescape(m.group(1)).strip()
    return ""


def parse_weixin(html: str, url: str) -> dict:
    title = _first(
        re.search(r'property="og:title"\s+content="([^"]+)"', html),
        re.search(r"var msg_title = htmlDecode\(\"([^\"]+)\"\)", html),
        re.search(r"<title>([^<]+)</title>", html),
    )
    account = _first(
        re.search(r'var nickname = htmlDecode\("([^"]+)"\)', html),
        re.search(r'var nickname = "([^"]+)"', html),
        re.search(r'id="js_name"[^>]*>([^<]+)<', html),
    ) or "未知公众号"
    ts = _first(
        re.search(r'var ct = "(\d+)"', html),
        re.search(r'id="publish_time"[^>]*>([^<]+)', html),
    )
    date_str = "unknown"
    if ts.isdigit():
        date_str = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
    elif re.match(r"\d{4}-\d{2}-\d{2}", ts):
        date_str = ts[:10]
    content_m = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', html, re.DOTALL)
    body = content_m.group(1) if content_m else html
    return {
        "title": title or url,
        "account": account,
        "date": date_str,
        "body_html": body,
        "url": url,
    }


def parse_generic(html: str, url: str) -> dict:
    title = _first(
        re.search(r"<title>([^<]+)</title>", html, re.I),
        re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.DOTALL),
    )
    title = re.sub(r"<[^>]+>", "", title)
    host = urlparse(url).netloc.replace("www.", "")
    date_m = re.search(r"(20\d{2}-\d{2}-\d{2})", html)
    date_str = date_m.group(1) if date_m else datetime.now().strftime("%Y-%m-%d")
    return {
        "title": title or url,
        "account": host or "web",
        "date": date_str,
        "body_html": html,
        "url": url,
    }


def load_urls(path: str) -> list[str]:
    urls = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            urls.append(s.split()[0])
    return urls


def save_markdown(parsed: dict, out_dir: Path, html_to_markdown) -> Path:
    account_dir = out_dir / _clean_filename(parsed["account"])
    account_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{parsed['date']}_{_clean_filename(parsed['title'])[:80]}.md"
    path = account_dir / fname
    md = (
        f"# {parsed['title']}\n\n"
        f"**Date:** {parsed['date']}\n"
        f"**Link:** {parsed['url']}\n"
        f"**Account:** {parsed['account']}\n\n"
        f"{html_to_markdown(parsed['body_html'])}\n"
    )
    path.write_text(md, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取公开招聘文为 Markdown")
    parser.add_argument("--urls", default=str(ROOT / "seed_urls.txt"))
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "articles"),
    )
    args = parser.parse_args()

    if not os.path.isfile(args.urls):
        print(f"找不到 URL 列表: {args.urls}")
        return 1

    crawler = _load_crawler()
    urls = load_urls(args.urls)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"抓取 {len(urls)} 条 → {out_dir}")

    ok = 0
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url}")
        try:
            resp = crawler.http_get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=40,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
            parsed = parse_weixin(html, url) if "mp.weixin.qq.com" in url else parse_generic(html, url)
            path = save_markdown(parsed, out_dir, crawler.html_to_markdown)
            print(f"  saved {path} ({path.stat().st_size} bytes)")
            ok += 1
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(1)
    print(f"完成: 成功 {ok}/{len(urls)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
