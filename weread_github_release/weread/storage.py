"""文章正文下载与 Markdown 存档。"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .auth import http_get


def is_valid_article_link(link: Optional[str]) -> bool:
    return bool(link) and "tempkey=" not in link


def clean_filename(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title or "").strip()


def html_to_markdown(html: str) -> str:
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL)

    def replace_img(match):
        src = match.group(1) or match.group(2)
        return f"\n![]({src})\n"

    html = re.sub(r'<img[^>]+data-src="([^"]+)"[^>]*>', replace_img, html)
    html = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', replace_img, html)

    def replace_pre_code(match):
        code_content = match.group(1)
        code_content = re.sub(r"<code[^>]*>(.*?)</code>", r"\1", code_content, flags=re.DOTALL)
        code_content = (
            code_content.replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&nbsp;", " ")
        )
        return f"\n```\n{code_content}\n```\n"

    html = re.sub(r"<pre[^>]*>(.*?)</pre>", replace_pre_code, html, flags=re.DOTALL)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n\n", html, flags=re.I)
    html = re.sub(r"</div>", "\n", html, flags=re.I)
    html = re.sub(r"</h[1-6]>", "\n\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = (
        html.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )
    html = re.sub(r"\n{3,}", "\n\n", html)
    html = re.sub(r" +", " ", html)
    return html.strip()


def article_page_headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def save_url_to_md(
    article: Dict[str, Any],
    account_name: str,
    articles_base_dir: str,
    mirror_base_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """返回 saved | jump | error | skip。"""
    config = config or {}
    url = article.get("link")
    title = article.get("title")
    digest = article.get("digest", "")
    create_time = int(article.get("create_time") or 0)
    try:
        date_str = (
            time.strftime("%Y-%m-%d", time.localtime(create_time)) if create_time else "Unknown"
        )
    except Exception:
        date_str = "Unknown"

    if not is_valid_article_link(url):
        return "skip"

    try:
        resp = http_get(url, headers=article_page_headers(), timeout=90)
        resp.encoding = "utf-8"
        content_html = resp.text
        folder_name = account_name or "Unknown_Account"
        os.makedirs(articles_base_dir, exist_ok=True)
        safe_account = clean_filename(folder_name)
        account_dir = os.path.join(articles_base_dir, safe_account)
        os.makedirs(account_dir, exist_ok=True)
        filename = os.path.join(account_dir, f"{date_str}_{clean_filename(title)}.md")
        if os.path.exists(filename):
            print(f"  [Jump] File exists: {filename}")
            return "jump"

        match = re.search(
            r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', content_html, re.DOTALL
        )
        if match:
            main_content = match.group(1)
        else:
            body = re.search(r"<body[^>]*>(.*?)</body>", content_html, re.DOTALL)
            main_content = body.group(1) if body else content_html

        lines = [
            f"# {title}",
            "",
            f"**Date:** {date_str}",
            f"**Link:** {url}",
            f"**Account:** {folder_name}",
        ]
        if digest:
            lines.append(f"**Summary:** {digest}")
        lines.extend(["", html_to_markdown(main_content)])
        Path(filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

        file_size = os.path.getsize(filename)
        min_kb = int(config.get("min_file_size_kb") or 0)
        if config.get("delete_small_files") and min_kb > 0 and file_size < min_kb * 1024:
            print(f"  [Delete] File too small ({file_size} bytes): {filename}")
            os.remove(filename)
            return "error"

        print(f"  [Saved] {filename} ({file_size} bytes)")
        if mirror_base_dir:
            mirror_account = os.path.join(mirror_base_dir, safe_account)
            os.makedirs(mirror_account, exist_ok=True)
            mirror_file = os.path.join(mirror_account, os.path.basename(filename))
            shutil.copy2(filename, mirror_file)
            print(f"  [DailyCopy] {mirror_file}")

        time.sleep(1)
        return "saved"
    except Exception as e:
        print(f"  [Error] Failed to save {title}: {e}")
        return "error"
