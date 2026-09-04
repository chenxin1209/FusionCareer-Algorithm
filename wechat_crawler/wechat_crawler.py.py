import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time
import os
import re
import argparse
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

# macOS 自带 Python(LibreSSL) 与 urllib3>=2 易触发 SSLEOFError，见 urllib3#3020
_SESSION = None


def get_http_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    _SESSION = s
    return _SESSION


def http_get(url, *, headers=None, params=None, timeout=60):
    return get_http_session().get(
        url, headers=headers, params=params, timeout=timeout
    )

# 配置和数据文件路径
CONFIG_FILE = "config.json"
FAKEID_FILE = "gzh.txt"
ACCOUNT_NAMES_FILE = "公众号名字"
HISTORY_FILE = "history.json"
OUTPUT_FILE = "wx_poc.txt"
DEFAULT_ARTICLES_BASE_DIR = "公众号文章"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def get_articles_base_dir(config):
    """主存档目录（bootstrap / daily / watch 写入）。与当日增量目录 YYYYMMDD新增 区分。"""
    return config.get("articles_base_dir", DEFAULT_ARTICLES_BASE_DIR)


def get_daily_folder_basename(config):
    """当日增量目录名，如 20260517新增（仅 daily 使用）。"""
    suffix = config.get("daily_folder_suffix", "新增")
    return beijing_now().strftime("%Y%m%d") + suffix


def beijing_now():
    return datetime.now(BEIJING_TZ)


def get_daily_increment_dir(config, base_dir=None):
    """当日增量目录完整路径，如 .../20260517新增"""
    root = base_dir or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, get_daily_folder_basename(config))


def write_daily_summary_md(
    summary_path, stats, run_time_str, daily_dir_name, articles_base_dir
):
    total = sum(stats.values())
    active = [(n, c) for n, c in stats.items() if c > 0]
    lines = [
        "# 公众号新增推文统计",
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
            "- 仅统计本次 `daily` 监测中新下载并写入本目录的文章。",
            f"- 主存档目录：`{articles_base_dir}/`（bootstrap 与 daily 均会写入）。",
            "- 本目录为当日增量副本，命名规则：`YYYYMMDD` + `daily_folder_suffix`（如 `20260517新增`）。",
            "- 若某号新增为 0，表示相对上次监测无新推文。",
        ]
    )
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filepath, data):
    # 保存 JSON 时保留中文
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_fakeids():
    if not os.path.exists(FAKEID_FILE):
        return []
    with open(FAKEID_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_account_names():
    if not os.path.exists(ACCOUNT_NAMES_FILE):
        return {}
    with open(ACCOUNT_NAMES_FILE, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    return {i: name for i, name in enumerate(names)}

def get_headers(cookie, token):
    return {
        "Host": "mp.weixin.qq.com",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
        "Cookie": cookie,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10&token={token}&lang=zh_CN",
        "Origin": "https://mp.weixin.qq.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

def get_articles(fakeid, token, cookie, begin=0, count=5):
    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    headers = get_headers(cookie, token)
    
    params = {
        "sub": "list",
        "begin": str(begin),
        "count": str(count),
        "fakeid": fakeid,
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1"
    }
    
    try:
        response = http_get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "base_resp" in data and data["base_resp"]["ret"] != 0:
            print(f"API Error: {data['base_resp']}")
            return [], 0, None
        
        # publish_page 是一个 JSON 字符串，需要再次解析
        if "publish_page" in data:
            publish_page = json.loads(data["publish_page"])
            publish_list = publish_page.get("publish_list", [])
            total_count = publish_page.get("total_count", 0)
            
            # 从 publish_list 中提取所有文章
            articles = []
            for publish_item in publish_list:
                publish_info = json.loads(publish_item.get("publish_info", "{}"))
                appmsg_info = publish_info.get("appmsg_info", [])
                for appmsg in appmsg_info:
                    articles.append({
                        "title": appmsg.get("title"),
                        "link": appmsg.get("content_url"),
                        "create_time": publish_info.get("sent_info", {}).get("time", 0),
                        "digest": appmsg.get("digest", ""),
                        "author": appmsg.get("author", "")
                    })
            
            return articles, total_count, None
        else:
            print("未找到 publish_page 字段")
            return [], 0, None
            
    except Exception as e:
        print(f"请求失败: {e}")
        return [], 0, None

def is_valid_article_link(link):
    """
    判断文章链接是否有效
    包含 tempkey= 的链接说明文章已删除或失效
    """
    if not link:
        return False
    # 检查是否包含 tempkey= 参数（说明文章已失效）
    if 'tempkey=' in link:
        return False
    return True

def clean_filename(title):
    # 去除非法字符
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def html_to_markdown(html):
    """
    Simple Regex-based HTML to Markdown converter.
    """
    # Remove style and script
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL)
    
    # Extract images: <img ... data-src="..."> or <img ... src="...">
    # Do this BEFORE removing any tags
    def replace_img(match):
        src = match.group(1) or match.group(2)
        return f"\n![]({src})\n"
    
    # Replace img tags with markdown images
    html = re.sub(r'<img[^>]+data-src="([^"]+)"[^>]*>', replace_img, html)
    html = re.sub(r'<img[^>]+src="([^"]+)"[^>]*>', replace_img, html)
    
    # Handle code blocks - <pre><code>...</code></pre> or <pre>...</pre>
    def replace_pre_code(match):
        code_content = match.group(1)
        # Remove inner <code> tags if present
        code_content = re.sub(r'<code[^>]*>(.*?)</code>', r'\1', code_content, flags=re.DOTALL)
        # Decode HTML entities in code
        code_content = code_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
        code_content = code_content.replace('&nbsp;', ' ')
        return f"\n```\n{code_content}\n```\n"
    
    html = re.sub(r'<pre[^>]*>(.*?)</pre>', replace_pre_code, html, flags=re.DOTALL)
    
    # Handle inline code - <code>...</code>
    html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL)
    
    # Remove lines that only contain HTML attributes (common in WeChat articles)
    html = re.sub(r'^\s*(class|data-|style|width|height|type|from|wx_fmt|data-ratio|data-type|data-w|data-imgfileid|data-aistatus|data-s)=[^>]*>\s*$', '', html, flags=re.MULTILINE)
    
    # Headers
    for i in range(6, 0, -1):
        html = re.sub(f'<h{i}[^>]*>(.*?)</h{i}>', '#' * i + r' \1\n', html)
        
    # Paragraphs and Breaks
    html = re.sub(r'<p[^>]*>', '\n', html)
    html = re.sub(r'</p>', '\n', html)
    html = re.sub(r'<br\s*/?>', '\n', html)
    
    # Bold/Strong
    html = re.sub(r'<(b|strong)[^>]*>(.*?)</\1>', r'**\2**', html)
    
    # Lists (Simple)
    html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html)
    
    # Remove all remaining tags (including self-closing)
    html = re.sub(r'<[^>]+>', '', html)
    
    # Decode entities (basic)
    html = html.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
    
    # Collapse multiple newlines and spaces
    html = re.sub(r'\n{3,}', '\n\n', html)
    html = re.sub(r' +', ' ', html)
    
    return html.strip()

def save_url_to_md(
    article,
    headers,
    account_name=None,
    mirror_base_dir=None,
    articles_base_dir=None,
):
    """
    保存文章为 Markdown。返回 saved | jump | error | skip。
    articles_base_dir：主存档根目录（config: articles_base_dir）。
    mirror_base_dir：当日增量目录完整路径（仅 daily，如 20260517新增）。
    """
    if articles_base_dir is None:
        articles_base_dir = DEFAULT_ARTICLES_BASE_DIR
    url = article.get("link")
    title = article.get("title")
    digest = article.get("digest", "")

    try:
        create_time = article.get("create_time")
        date_str = time.strftime("%Y-%m-%d", time.localtime(create_time))
    except Exception:
        date_str = "Unknown"

    if not url:
        return "skip"

    try:
        # Fetch article content
        resp = http_get(url, headers=headers, timeout=90)
        resp.encoding = "utf-8"
        content_html = resp.text
        
        # Use provided account name or try to extract from HTML
        folder_name = account_name if account_name else "Unknown_Account"
        
        if folder_name == "Unknown_Account":
            # Try to extract from HTML var nickname
            nick_match = re.search(r'var nickname = "([^"]+)"', content_html)
            if nick_match:
                folder_name = nick_match.group(1)
            elif "profile_meta_nickname" in content_html:
                nick_match_2 = re.search(r'class="profile_meta_value">([^<]+)<', content_html)
                if nick_match_2:
                    folder_name = nick_match_2.group(1).strip()

        if not os.path.exists(articles_base_dir):
            os.makedirs(articles_base_dir)

        safe_account_folder = clean_filename(folder_name)
        account_dir = os.path.join(articles_base_dir, safe_account_folder)
        if not os.path.exists(account_dir):
            os.makedirs(account_dir)
            
        safe_title = clean_filename(title)
        filename = os.path.join(account_dir, f"{date_str}_{safe_title}.md")
        
        if os.path.exists(filename):
            print(f"  [Jump] File exists: {filename}")
            return "jump"

        # Convert to Markdown
        # Only extract the main content container: id="js_content"
        main_content = ""
        content_match = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>', content_html, re.DOTALL)
        
        if content_match:
             main_content = content_match.group(1)
        else:
             # Fallback: parsing might be complex, use whole response body
             main_content = re.search(r'<body[^>]*>(.*?)</body>', content_html, re.DOTALL).group(1) if re.search(r'<body', content_html) else content_html

        markdown_content = f"# {title}\n\n"
        markdown_content += f"**Date:** {date_str}\n"
        markdown_content += f"**Link:** {url}\n"
        markdown_content += f"**Account:** {folder_name}\n"
        if digest:
            markdown_content += f"**Summary:** {digest}\n"
        markdown_content += "\n"
        markdown_content += html_to_markdown(main_content)
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        config = load_json(CONFIG_FILE)
        file_size = os.path.getsize(filename)
        min_kb = config.get("min_file_size_kb", 0)
        delete_small = config.get("delete_small_files", False)
        if delete_small and min_kb > 0:
            min_bytes = min_kb * 1024
            if file_size < min_bytes:
                print(f"  [Delete] File too small ({file_size} bytes): {filename}")
                os.remove(filename)
            else:
                print(f"  [Saved] {filename} ({file_size} bytes)")
        else:
            print(f"  [Saved] {filename} ({file_size} bytes)")

        if mirror_base_dir:
            mirror_account = os.path.join(mirror_base_dir, safe_account_folder)
            os.makedirs(mirror_account, exist_ok=True)
            mirror_file = os.path.join(mirror_account, os.path.basename(filename))
            shutil.copy2(filename, mirror_file)
            print(f"  [DailyCopy] {mirror_file}")

        time.sleep(1)
        return "saved"

    except Exception as e:
        print(f"  [Error] Failed to save {title}: {e}")
        return "error"

def load_account_latest_articles():
    """
    从 wx_poc.txt 中读取每个公众号的最新文章链接
    返回字典: {公众号名称: 最新文章链接}
    """
    account_latest = {}
    if not os.path.exists(OUTPUT_FILE):
        return account_latest
    
    current_account = None
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("文章名字："):
                # 提取公众号名称（从文件名中）
                title = line.replace("文章名字：", "")
                # 尝试从文件名中提取公众号名
                # 格式类似: 公众号文章/公众号名/日期_标题.md
                # 但这里只有标题，无法直接获取
                # 我们需要另一种方式
                pass
            elif line.startswith("文章链接："):
                link = line.replace("文章链接：", "")
                if current_account:
                    account_latest[current_account] = link
                    current_account = None
    
    return account_latest

def load_account_first_article_from_txt():
    """
    从 wx_poc.txt 中读取每个公众号的第一篇文章链接
    返回字典: {公众号名称: 第一篇文章链接}
    """
    account_first_articles = {}
    if not os.path.exists(OUTPUT_FILE):
        return account_first_articles
    
    current_account = None
    first_article_link = None
    
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("公众号："):
                current_account = line.replace("公众号：", "")
                first_article_link = None
            elif line.startswith("第一篇文章链接：") and current_account:
                first_article_link = line.replace("第一篇文章链接：", "")
                account_first_articles[current_account] = first_article_link
    
    return account_first_articles


def mode_bootstrap(
    fakeids, token, cookie, account_names, article_limit, articles_base_dir
):
    """
    每个公众号只拉取列表最前面的 article_limit 篇（最新），
    写入 wx_poc、保存 Markdown，并写入 history.json。
    已在 wx_poc 中的链接会跳过追加记录；本地已有 md 会 [Jump]。
    """
    print(f"--- Bootstrap：每号最新 {article_limit} 条 ---")
    print(f"主存档目录: {articles_base_dir}/")
    headers = get_headers(cookie, token)
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("文章链接："):
                    link = line.strip().replace("文章链接：", "")
                    existing_links.add(link)

    history = load_json(HISTORY_FILE)
    if not os.path.exists(articles_base_dir):
        os.makedirs(articles_base_dir)

    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, "Unknown_Account")
        print(f"Bootstrap: {fakeid} ({account_name})")

        articles, _, _ = get_articles(
            fakeid, token, cookie, begin=0, count=max(article_limit, 10)
        )
        if not articles:
            print("  获取列表失败或无文章")
            continue

        if articles:
            history[fakeid] = {
                "last_article_title": articles[0].get("title"),
                "last_article_url": articles[0].get("link"),
            }

        collected = []
        for article in articles:
            if len(collected) >= article_limit:
                break
            if is_valid_article_link(article.get("link")):
                collected.append(article)

        if not collected:
            print("  最新列表中无有效文章")
            continue

        new_for_log = [a for a in collected if a.get("link") not in existing_links]
        if new_for_log:
            with open(OUTPUT_FILE, "a+", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write(f"公众号：{account_name}\n")
                f.write(f"文章数量：{len(new_for_log)}篇\n")
                f.write(f"第一篇文章：{new_for_log[0].get('title')}\n")
                f.write(f"第一篇文章链接：{new_for_log[0].get('link')}\n")
                f.write("=" * 60 + "\n")
                for article in new_for_log:
                    f.write(f"文章名字：{article.get('title')}\n")
                    f.write(f"文章链接：{article.get('link')}\n")
                    f.write("-" * 50 + "\n")
                    existing_links.add(article.get("link"))

        for article in collected:
            save_url_to_md(
                article, headers, account_name, articles_base_dir=articles_base_dir
            )
        print(f"  处理最新 {len(collected)} 篇（wx_poc 新增 {len(new_for_log)} 条记录）")
        time.sleep(2)

    save_json(HISTORY_FILE, history)
    print("--- Bootstrap 完成，已保存 history.json ---")


def mode_archive(fakeids, token, cookie, account_names, articles_base_dir):
    """存档模式：爬取所有文章"""
    print("--- 启动存档模式 ---")
    print(f"主存档目录: {articles_base_dir}/")
    headers = get_headers(cookie, token)
    
    # Load existing links from wx_poc.txt to avoid duplicates
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("文章链接："):
                    link = line.strip().replace("文章链接：", "")
                    existing_links.add(link)
    
    # Load first articles from wx_poc.txt for comparison
    account_first_articles = load_account_first_article_from_txt()
    print(f"已加载 {len(account_first_articles)} 个公众号的第一篇文章记录")
    
    if not os.path.exists(articles_base_dir):
        os.makedirs(articles_base_dir)

    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, "Unknown_Account")
        print(f"正在处理 fakeid: {fakeid} ({account_name})")
        
        # Get first article to check if already archived
        articles_first, _, _ = get_articles(fakeid, token, cookie, 0, 1)
        if articles_first:
            first_article_link = articles_first[0].get('link')
            
            # Check if this account has archived articles in wx_poc.txt
            if account_name in account_first_articles:
                archived_first_link = account_first_articles[account_name]
                if first_article_link == archived_first_link:
                    print(f"  [Skip] 公众号第一篇文章已存档，跳过: {account_name}")
                    continue
                else:
                    print(f"  [New] 发现新内容，开始爬取: {account_name}")
            else:
                print(f"  [New] 首次爬取，开始处理: {account_name}")
        
        begin = 0
        count = 10
        should_stop = False
        account_articles = []
        
        while not should_stop:
            articles, total, _ = get_articles(fakeid, token, cookie, begin, count)
            if not articles:
                print(f"  没有更多文章或获取失败")
                break
                
            print(f"  获取到 {len(articles)} 篇文章 (当前进度: {begin})")
            
            for article in articles:
                link = article.get('link')
                # Check if this article is already archived in wx_poc.txt
                if account_name in account_first_articles:
                    if link == account_first_articles[account_name]:
                        print(f"  [Stop] 找到已存档文章，停止爬取: {article.get('title')}")
                        should_stop = True
                        break
                # Skip invalid articles (deleted or expired)
                if not is_valid_article_link(link):
                    print(f"  [Skip] 文章已失效，跳过: {article.get('title')}")
                    continue
                # Only collect if not already archived
                if link not in existing_links:
                    account_articles.append(article)
            
            if should_stop:
                break
                
            if len(articles) < count:
                print("  已到达最后一页")
                break
                
            begin += count
            time.sleep(3)
        
        # Save to txt with account header
        if account_articles:
            # Filter out invalid articles before saving
            valid_articles = [a for a in account_articles if is_valid_article_link(a.get('link'))]
            
            if valid_articles:
                with open(OUTPUT_FILE, "a+", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write(f"公众号：{account_name}\n")
                    f.write(f"文章数量：{len(valid_articles)}篇\n")
                    f.write(f"第一篇文章：{valid_articles[0].get('title')}\n")
                    f.write(f"第一篇文章链接：{valid_articles[0].get('link')}\n")
                    f.write("=" * 60 + "\n")
                    for article in valid_articles:
                        f.write(f"文章名字：{article.get('title')}\n")
                        f.write(f"文章链接：{article.get('link')}\n")
                        f.write("-" * 50 + "\n")
                        existing_links.add(article.get('link'))
                
                # Save to Markdown (only valid articles)
                for article in valid_articles:
                    save_url_to_md(
                        article,
                        headers,
                        account_name,
                        articles_base_dir=articles_base_dir,
                    )

def mode_update(
    fakeids,
    token,
    cookie,
    history,
    account_names,
    articles_base_dir,
    daily_mirror_dir=None,
):
    """更新模式：增量爬取。返回 {公众号名称: 本次新增篇数}。"""
    print("--- 启动更新模式 ---")
    print(f"主存档目录: {articles_base_dir}/")
    if daily_mirror_dir:
        os.makedirs(daily_mirror_dir, exist_ok=True)
        print(f"当日增量目录: {daily_mirror_dir}/")
    headers = get_headers(cookie, token)
    stats = {}
    
    # Load existing links to avoid duplicates
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("文章链接："):
                    link = line.strip().replace("文章链接：", "")
                    existing_links.add(link)
    
    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, "Unknown_Account")
        stats[account_name] = 0
        print(f"正在检查 fakeid: {fakeid} ({account_name})")
        
        last_article_info = history.get(fakeid, {})
        last_title = last_article_info.get("last_article_title")
        if not last_title:
            print("  [Skip] history.json 中无该 fakeid 记录，请先运行: python wechat_crawler.py.py bootstrap")
            continue

        begin = 0
        count = 10
        new_articles = []
        found_overlap = False
        
        while not found_overlap:
            articles, total, _ = get_articles(fakeid, token, cookie, begin, count)
            if not articles:
                break
                
            for article in articles:
                title = article.get("title")
                link = article.get('link')
                
                if title == last_title:
                    print(f"  找到上次最后更新的文章: {title}，停止本号更新")
                    found_overlap = True
                    break
                
                # Skip invalid articles (deleted or expired)
                if not is_valid_article_link(link):
                    print(f"  [Skip] 文章已失效，跳过: {title}")
                    continue
                
                new_articles.append(article)
            
            if len(articles) < count or found_overlap:
                break
                
            begin += count
            time.sleep(3)
            
        if new_articles:
            # Filter out invalid articles
            valid_articles = [a for a in new_articles if is_valid_article_link(a.get('link'))]
            
            if valid_articles:
                print(f"  发现 {len(valid_articles)} 篇新文章（待下载）")

                # Save to txt log with account header (new format)
                with open(OUTPUT_FILE, "a+", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n")
                    f.write(f"公众号：{account_name}\n")
                    f.write(f"文章数量：{len(valid_articles)}篇\n")
                    f.write(f"第一篇文章：{valid_articles[0].get('title')}\n")
                    f.write(f"第一篇文章链接：{valid_articles[0].get('link')}\n")
                    f.write("=" * 60 + "\n")
                    for article in valid_articles:
                        f.write(f"文章名字：{article.get('title')}\n")
                        f.write(f"文章链接：{article.get('link')}\n")
                        f.write("-" * 50 + "\n")
                        existing_links.add(article.get('link'))
                
                saved_count = 0
                for article in valid_articles:
                    status = save_url_to_md(
                        article,
                        headers,
                        account_name,
                        mirror_base_dir=daily_mirror_dir,
                        articles_base_dir=articles_base_dir,
                    )
                    if status == "saved":
                        saved_count += 1
                stats[account_name] = saved_count

                # Update history with the NEWEST article
                newest = valid_articles[0]
                history[fakeid] = {
                    "last_article_title": newest.get("title"),
                    "last_article_url": newest.get("link")
                }
            else:
                print("  发现的新文章均已失效")
        else:
            print("  无新文章")

    save_json(HISTORY_FILE, history)
    return stats


def _article_ts(article):
    try:
        return int(article.get("create_time") or 0)
    except (TypeError, ValueError):
        return 0


def mode_range(
    fakeids,
    token,
    cookie,
    account_names,
    articles_base_dir,
    since_ts,
    until_ts,
    max_pages_per_account=40,
):
    """
    按发布时间窗口抓取（需公众平台 token/cookie）。
    列表按时间倒序，翻页直到早于 since_ts 即停。
    """
    print("--- 日期区间抓取 ---")
    print(f"窗口: {datetime.fromtimestamp(since_ts, BEIJING_TZ).date()} ~ {datetime.fromtimestamp(until_ts, BEIJING_TZ).date()}")
    print(f"主存档目录: {articles_base_dir}/")
    headers = get_headers(cookie, token)
    os.makedirs(articles_base_dir, exist_ok=True)

    stats = {}
    for idx, fakeid in enumerate(fakeids):
        account_name = account_names.get(idx, f"account_{idx+1:02d}")
        stats[account_name] = 0
        print(f"Range: {fakeid} ({account_name})")
        begin = 0
        count = 10
        collected = []
        for _page in range(max_pages_per_account):
            articles, _, _ = get_articles(fakeid, token, cookie, begin, count)
            if not articles:
                break
            stop = False
            for article in articles:
                ts = _article_ts(article)
                if ts and ts > until_ts:
                    continue
                if ts and ts < since_ts:
                    stop = True
                    break
                if is_valid_article_link(article.get("link")):
                    collected.append(article)
            if stop or len(articles) < count:
                break
            begin += count
            time.sleep(2)

        saved = 0
        for article in collected:
            status = save_url_to_md(
                article, headers, account_name, articles_base_dir=articles_base_dir
            )
            if status == "saved":
                saved += 1
        stats[account_name] = saved
        print(f"  窗口内 {len(collected)} 篇，新写入 {saved} 篇")
        time.sleep(1)

    total = sum(stats.values())
    print(f"--- 区间抓取完成，新写入 {total} 篇 ---")
    return stats


def _append_daily_report(report_path, stats):
    """将本次各号新增篇数追加写入 JSONL。"""
    line = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_new": sum(stats.values()),
        "by_account": stats,
    }
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _parse_day(s, end=False):
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)
    if end:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


def main():
    parser = argparse.ArgumentParser(
        description="微信公众号爬虫：bootstrap / daily / watch / range",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="watch",
        choices=("bootstrap", "daily", "watch", "range"),
        help="bootstrap=每号抓取前若干条并初始化 history；daily=增量一次并报告数量；watch=按间隔循环全量存档检查（旧行为）；range=按日期窗口抓取",
    )
    parser.add_argument("--since", default="2026-07-01", help="range 起始日 YYYY-MM-DD（含）")
    parser.add_argument("--until", default="2026-08-31", help="range 结束日 YYYY-MM-DD（含）")
    args = parser.parse_args()

    config = load_json(CONFIG_FILE)
    token = config.get("token")
    cookie = config.get("cookie")

    if not token or not cookie:
        print("错误: config.json 中缺少 token 或 cookie")
        print("请先在有浏览器的机器上执行: python sync_wechat_session.py")
        print("无后台登录时可用公开链接抓取: python fetch_public.py")
        return

    fakeids = load_fakeids()
    if not fakeids:
        print("错误: gzh.txt 为空或不存在")
        return
    print(f"加载了 {len(fakeids)} 个公众号")

    account_names = load_account_names()
    print(f"加载了 {len(account_names)} 个公众号名称")

    articles_base_dir = get_articles_base_dir(config)

    if args.command == "range":
        since_ts = _parse_day(args.since, end=False)
        until_ts = _parse_day(args.until, end=True)
        mode_range(
            fakeids,
            token,
            cookie,
            account_names,
            articles_base_dir,
            since_ts,
            until_ts,
        )
        return

    if args.command == "bootstrap":
        limit = int(config.get("bootstrap_article_limit", 10))
        mode_bootstrap(
            fakeids, token, cookie, account_names, limit, articles_base_dir
        )
        return

    if args.command == "daily":
        history = load_json(HISTORY_FILE)
        run_time = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        daily_dir = None
        if config.get("daily_mirror_to_dated_folder", True):
            daily_dir = get_daily_increment_dir(config)
            os.makedirs(daily_dir, exist_ok=True)
            print(
                f"目录说明: 主存档={articles_base_dir}/ | "
                f"当日增量={os.path.basename(daily_dir)}/"
            )

        stats = mode_update(
            fakeids,
            token,
            cookie,
            history,
            account_names,
            articles_base_dir,
            daily_mirror_dir=daily_dir,
        )
        total = sum(stats.values())
        print("\n" + "=" * 60)
        print(f"【日报】本次新增文章合计: {total} 篇（北京时间 {run_time}）")
        for name, n in sorted(stats.items(), key=lambda x: (-x[1], x[0])):
            if n > 0:
                print(f"  {name}: {n}")
        print("=" * 60 + "\n")

        report_path = config.get("daily_report_path", "daily_report.jsonl")
        report_line = {
            "time": run_time,
            "total_new": total,
            "by_account": stats,
        }
        if daily_dir:
            report_line["daily_folder"] = os.path.basename(daily_dir)
        with open(report_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report_line, ensure_ascii=False) + "\n")
        print(f"已追加写入: {report_path}")

        if daily_dir:
            summary_name = config.get("daily_summary_filename", "新增统计.md")
            summary_path = os.path.join(daily_dir, summary_name)
            write_daily_summary_md(
                summary_path,
                stats,
                run_time,
                os.path.basename(daily_dir),
                articles_base_dir,
            )
            print(f"已写入统计: {summary_path}")
            print(f"当日增量文章目录: {daily_dir}")
        return

    # watch：持续监控（沿用 mode_archive）
    check_interval_minutes = config.get("check_interval_minutes", 60)
    check_interval_seconds = check_interval_minutes * 60

    print("启动持续监控模式（watch，按 wx_poc 比对第一篇）...")
    print(f"每{check_interval_minutes}分钟检查一次公众号更新\n")

    while True:
        try:
            print(f"\n{'='*60}")
            print(f"开始检查更新 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}\n")

            mode_archive(fakeids, token, cookie, account_names, articles_base_dir)

            print(f"\n{'='*60}")
            print(f"检查完成 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            next_check_time = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(time.time() + check_interval_seconds),
            )
            print(f"下次检查时间: {next_check_time}")
            print(f"{'='*60}\n")

            print(f"等待{check_interval_minutes}分钟后进行下一次检查...")
            time.sleep(check_interval_seconds)

        except KeyboardInterrupt:
            print("\n\n监控已停止")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            retry_interval_minutes = config.get("retry_interval_minutes", 5)
            print(f"{retry_interval_minutes}分钟后重试...")
            time.sleep(retry_interval_minutes * 60)


if __name__ == "__main__":
    main()