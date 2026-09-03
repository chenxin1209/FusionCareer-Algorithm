#!/usr/bin/env python3
"""
从已登录的微信公众平台页面同步 token 与 cookie 到 config.json。

重要说明：
  - 后台 API 需要的是 mp.weixin.qq.com 的 Cookie + URL 中的 token（如 home 页 ?token=1608520353）
  - 文章页里的 var biz = "..." 是 __biz，与后台列表接口的 fakeid 不是同一字段

用法:
  # 方式 1：内置浏览器（推荐首次使用，登录态会保存在 .wechat_browser_profile/）
  python sync_wechat_session.py

  # 方式 2：接管你已打开的 Chrome（需先用远程调试端口启动 Chrome，见脚本末尾说明）
  python sync_wechat_session.py --cdp http://127.0.0.1:9222

  # 仅写入 config，不调用接口校验
  python sync_wechat_session.py --no-verify
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("请先安装: pip install playwright && playwright install chromium")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
PROFILE_DIR = ROOT / ".wechat_browser_profile"
MP_HOME = "https://mp.weixin.qq.com/"
MP_HOST_SUFFIX = "weixin.qq.com"

# 登录后常见落地页（含 token 参数）
TOKEN_URL_PATTERN = re.compile(
    r"mp\.weixin\.qq\.com.*[?&]token=(\d+)",
    re.I,
)


def load_config():
    if CONFIG_FILE.is_file():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        f.write("\n")


def token_from_url(url: str):
    m = TOKEN_URL_PATTERN.search(url or "")
    if m:
        return m.group(1)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    tok = qs.get("token", [None])[0]
    return tok if tok and str(tok).isdigit() else None


def cookies_for_mp(context_cookies):
    """组装 Request Headers 用的 Cookie 字符串。"""
    picked = []
    for c in context_cookies:
        domain = (c.get("domain") or "").lstrip(".")
        if not domain.endswith(MP_HOST_SUFFIX):
            continue
        name, value = c.get("name"), c.get("value")
        if name is None:
            continue
        picked.append((name, value or ""))
    # 去重：同名 cookie 保留后者
    seen = {}
    for name, value in picked:
        seen[name] = value
    return "; ".join(f"{k}={v}" for k, v in seen.items())


def pick_token_from_pages(pages):
    for page in pages:
        try:
            t = token_from_url(page.url)
            if t:
                return t, page.url
        except Exception:
            continue
    return None, None


def wait_for_logged_in(page, timeout_ms=300_000):
    """等待进入带 token 的后台页面。"""
    deadline = time.time() + timeout_ms / 1000
    tried_nav = False
    while time.time() < deadline:
        url = page.url or ""
        t = token_from_url(url)
        if t:
            return t
        if "mp.weixin.qq.com" in url and "login" not in url.lower() and not tried_nav:
            tried_nav = True
            try:
                page.goto(
                    "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                time.sleep(2)
                t = token_from_url(page.url)
                if t:
                    return t
            except Exception:
                pass
        time.sleep(1)
    return None


def verify_session(token, cookie):
    """用与爬虫相同的接口探测会话是否有效。"""
    import requests

    gzh = ROOT / "gzh.txt"
    if not gzh.is_file():
        return True, "未找到 gzh.txt，跳过接口校验"
    fakeid = next(
        (ln.strip() for ln in gzh.read_text(encoding="utf-8").splitlines() if ln.strip()),
        None,
    )
    if not fakeid:
        return True, "gzh.txt 为空，跳过接口校验"

    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie,
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/home?token={token}&lang=zh_CN",
    }
    params = {
        "sub": "list",
        "begin": "0",
        "count": "1",
        "fakeid": fakeid,
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": "1",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        data = r.json()
        base = data.get("base_resp") or {}
        if base.get("ret") == 0:
            return True, "接口校验通过"
        return False, f"接口返回: {base}"
    except Exception as e:
        return False, f"校验请求失败: {e}"


def sync_from_context(context, pages, no_verify=False):
    token, src_url = pick_token_from_pages(pages)
    if not token and pages:
        token = wait_for_logged_in(pages[0])
        src_url = pages[0].url if pages else None
    if not token:
        print("未能从页面 URL 解析 token。请确认已登录后台，且地址栏含 token=数字。")
        return False

    cookies = context.cookies()
    cookie_header = cookies_for_mp(cookies)
    if len(cookie_header) < 50:
        print("Cookie 过短，可能未登录成功。")
        return False

    cfg = load_config()
    cfg["token"] = token
    cfg["cookie"] = cookie_header
    save_config(cfg)

    print(f"已写入 {CONFIG_FILE.name}")
    print(f"  token  = {token}")
    if src_url:
        print(f"  来源页 = {src_url[:100]}...")
    print(f"  cookie 长度 = {len(cookie_header)} 字符")

    if no_verify:
        return True
    ok, msg = verify_session(token, cookie_header)
    print(f"  校验: {msg}")
    return ok


def run_interactive_browser(headless=False, no_verify=False):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print("正在启动浏览器（登录态目录: .wechat_browser_profile/）")
    print("请在打开的窗口中登录 mp.weixin.qq.com；若已登录，等待自动跳转即可。\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(MP_HOME, wait_until="domcontentloaded", timeout=120_000)

        print("若未自动完成，请在浏览器中打开后台首页（地址栏含 token=...），")
        print("然后回到本终端按 Enter 继续抓取 Cookie …")
        try:
            wait_for_logged_in(page, timeout_ms=120_000)
        except PlaywrightTimeout:
            pass
        input()

        pages = context.pages
        ok = sync_from_context(context, pages, no_verify=no_verify)
        context.close()
        return ok


def run_cdp(cdp_url: str, no_verify=False):
    print(f"正在连接 Chrome: {cdp_url}")
    print("请确保 Chrome 已用远程调试启动，且当前标签页为已登录的公众平台。\n")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            print("未找到浏览器上下文")
            return False
        context = browser.contexts[0]
        pages = context.pages
        if not pages:
            print("没有打开的标签页，请先打开 mp.weixin.qq.com 后台")
            return False
        ok = sync_from_context(context, pages, no_verify=no_verify)
        return ok


def main():
    parser = argparse.ArgumentParser(description="同步微信公众平台 token/cookie 到 config.json")
    parser.add_argument(
        "--cdp",
        metavar="URL",
        help="连接已打开的 Chrome，例如 http://127.0.0.1:9222",
    )
    parser.add_argument("--headless", action="store_true", help="无头模式（首次登录不要用）")
    parser.add_argument("--no-verify", action="store_true", help="跳过接口校验")
    args = parser.parse_args()

    if args.cdp:
        ok = run_cdp(args.cdp, no_verify=args.no_verify)
    else:
        ok = run_interactive_browser(headless=args.headless, no_verify=args.no_verify)

    if ok:
        print("\n下一步: python wechat_crawler.py.py bootstrap")
    else:
        print("\n同步失败。请重新登录后台后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
