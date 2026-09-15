"""微信读书公众号文章列表。"""
from __future__ import annotations

import base64
import binascii
import time
from typing import Any, Dict, List

from .auth import (
    MOBILE_HEADERS,
    REQUEST_TIMEOUT,
    WEREAD_MOBILE_BASE,
    get_http_session,
    response_json,
)


def fakeid_to_book_id(fakeid: str) -> str:
    value = str(fakeid or "").strip()
    if value.startswith("MP_WXS_") and value[len("MP_WXS_") :].isdigit():
        return value
    if value.isdigit():
        return f"MP_WXS_{value}"
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(value + padding, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        decoded = ""
    if not decoded.isdigit():
        raise ValueError(f"无法把公众号标识转换为微信读书 bookId：{value!r}")
    return f"MP_WXS_{decoded}"


def _first_present(mapping: Dict[str, Any], keys) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return ""


def _article_link(item: Dict[str, Any], book_id: str) -> str:
    direct = str(
        _first_present(item, ("link", "url", "articleUrl", "contentUrl", "doc_url")) or ""
    ).replace("\\", "")
    if direct.startswith("https://mp.weixin.qq.com/"):
        return direct

    review_id = str(_first_present(item, ("reviewId", "review_id")) or "")
    if review_id.startswith("http://") or review_id.startswith("https://"):
        return review_id

    prefix = f"{book_id}_"
    if review_id.startswith(prefix):
        token = review_id[len(prefix) :]
    elif review_id.startswith("MP_WXS_") and "_" in review_id:
        token = review_id.rsplit("_", 1)[-1]
    else:
        token = ""
    return f"https://mp.weixin.qq.com/s/{token}" if token else ""


def _normalize_publish_ts(value) -> int:
    if value in (None, ""):
        return 0
    try:
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        return int(timestamp)
    except (TypeError, ValueError):
        return 0


def extract_weread_articles(payload, book_id: str) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen_links = set()

    def visit(node):
        if isinstance(node, dict):
            title = str(_first_present(node, ("title", "articleTitle")) or "").strip()
            link = _article_link(node, book_id)
            if title and link and link not in seen_links:
                found.append(
                    {
                        "title": title,
                        "link": link,
                        "create_time": _normalize_publish_ts(
                            _first_present(
                                node,
                                (
                                    "publishTime",
                                    "createTime",
                                    "updateTime",
                                    "publish_time",
                                    "create_time",
                                    "time",
                                ),
                            )
                        ),
                        "digest": str(
                            _first_present(node, ("digest", "abstract", "summary")) or ""
                        ),
                    }
                )
                seen_links.add(link)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    found.sort(key=lambda a: a.get("create_time") or 0, reverse=True)
    return found


def raise_weread_list_error(payload: dict, response) -> None:
    err_code = payload.get("errCode", payload.get("errcode", 0))
    err_msg = str(payload.get("errMsg") or payload.get("errmsg") or "")
    if err_code == -2012:
        raise RuntimeError("微信读书登录已过期，请运行: python wechat_crawler_weread.py login")
    if err_code == -2014:
        raise RuntimeError("微信读书触发频率限制（-2014），请稍后再试，勿连续重跑。")
    if err_code == -2041:
        raise RuntimeError("微信读书要求在官方客户端完成人工验证（-2041）。")
    if err_code not in (None, "", 0, "0"):
        raise RuntimeError(f"微信读书接口返回错误：{err_code} {err_msg}".strip())
    if response.status_code >= 400:
        raise RuntimeError(f"读取公众号文章列表失败：HTTP {response.status_code}")


def fetch_articles(credentials: dict, fakeid: str, max_groups: int = 15) -> List[Dict[str, Any]]:
    book_id = fakeid_to_book_id(fakeid)
    session = get_http_session()
    headers = {
        **MOBILE_HEADERS,
        "vid": str(credentials["vid"]),
        "accessToken": str(credentials["accessToken"]),
    }
    response = session.get(
        f"{WEREAD_MOBILE_BASE}/mp/chapters",
        headers=headers,
        params={"bookId": book_id, "count": max(max_groups, 5), "synckey": 0},
        timeout=REQUEST_TIMEOUT,
    )
    payload = response_json(response, "读取公众号文章列表", allow_http_error=True)
    raise_weread_list_error(payload, response)

    entries = payload.get("data", []) if isinstance(payload, dict) else []
    details = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if extract_weread_articles(entry, book_id):
            continue
        review_id = str(entry.get("reviewId") or "").strip()
        if not review_id:
            continue
        detail_response = session.get(
            f"{WEREAD_MOBILE_BASE}/review/single",
            headers=headers,
            params={
                "reviewId": review_id,
                "commentsCount": 10,
                "commentsDirection": 0,
                "likesCount": 10,
                "likesDirection": 0,
                "synckey": 0,
            },
            timeout=REQUEST_TIMEOUT,
        )
        detail = response_json(detail_response, "读取公众号文章详情", allow_http_error=True)
        detail_err = detail.get("errCode", detail.get("errcode", 0))
        if detail_err == -2012:
            raise RuntimeError("微信读书登录已过期，请重新 login。")
        if detail_err == -2014:
            raise RuntimeError("微信读书触发频率限制（-2014），请稍后再试。")
        if detail_err not in (None, "", 0, "0") or detail_response.status_code >= 400:
            continue
        details.append(detail)
        time.sleep(0.4)

    return extract_weread_articles({"listing": payload, "details": details}, book_id)
