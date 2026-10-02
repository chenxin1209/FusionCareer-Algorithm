"""
企业公司规模分：查东方财富股票信息，用总市值做基础打分，避免小微企业排太前。

非上市 / 查不到：按小微处理（当前 -2）。阈值先保持，由推荐日志统计占比后再调。
机关、媒体、教职不走这套。结果写入本地缓存，避免推荐时反复打接口。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

import requests

from job_structuring import paths

_SUGGEST = "https://searchapi.eastmoney.com/api/suggest/get"
_VALUE = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?pageSize=1&pageNumber=1&reportName=RPT_VALUEANALYSIS_DET"
    "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,TOTAL_MARKET_CAP,CLOSE_PRICE"
    "&source=WEB&client=WEB"
)
_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
_CACHE_REL = os.path.join("logs", "company_cap_cache.json")
_TTL_SEC = 7 * 24 * 3600
_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FusionCareer/1.0",
    "Referer": "https://data.eastmoney.com/",
}

_STRIP_CO = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团公司|集团|公司|股份)$"
)


def _cache_path() -> str:
    return os.path.join(paths.PROJECT_ROOT, _CACHE_REL)


def _load_cache() -> dict[str, Any]:
    path = _cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    path = _cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, path)


def _norm_company(name: str) -> str:
    s = re.sub(r"\s+", "", (name or "").strip())
    s = _STRIP_CO.sub("", s)
    return s


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False  # 校园网代理常把 push2/行情域名掐掉
    s.headers.update(_UA)
    return s


def _to_yi(raw: Any) -> Optional[float]:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 10000:
        return round(v / 1e8, 2)
    return round(v, 2)


def _suggest(name: str) -> Optional[dict[str, str]]:
    q = (name or "").strip()[:30]
    if not q:
        return None
    try:
        resp = _session().get(
            _SUGGEST,
            params={"input": q, "type": 14, "token": _TOKEN, "count": 5},
            timeout=4,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return None
    table = (data or {}).get("QuotationCodeTable") or {}
    rows = table.get("Data") or []
    if not rows:
        return None
    needle = _norm_company(q)
    picked = rows[0]
    for row in rows:
        nm = _norm_company(str(row.get("Name") or ""))
        if needle and (needle in nm or nm in needle):
            picked = row
            break
    quote_id = str(picked.get("QuoteID") or "").strip()
    code = str(picked.get("Code") or "").strip()
    if not quote_id and code:
        mkt = str(picked.get("MktNum") or picked.get("MarketType") or "")
        if mkt:
            quote_id = f"{mkt}.{code}"
    if not quote_id:
        return None
    return {
        "quote_id": quote_id,
        "name": str(picked.get("Name") or ""),
        "code": code,
    }


def _quote_cap(code: str) -> Optional[float]:
    code = (code or "").strip()
    if not code:
        return None
    try:
        resp = _session().get(
            _VALUE + f"&filter=(SECURITY_CODE%3D%22{code}%22)",
            timeout=4,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        return None
    rows = ((data or {}).get("result") or {}).get("data") or []
    if not rows:
        return None
    return _to_yi(rows[0].get("TOTAL_MARKET_CAP"))


def lookup_company(name: str, *, cache: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    返回 listed / market_cap_yi / score_delta / label / source
    score_delta 供企业岗排序：上市大公司加分，小微或查不到减分。
    """
    empty = {
        "listed": False,
        "market_cap_yi": None,
        "score_delta": -2,
        "label": "未检索到上市信息，按小微企业处理",
        "source": "none",
        "matched_name": "",
    }
    key = _norm_company(name)
    if not key:
        return empty
    store = _load_cache()
    if cache:
        store.update(cache)
    hit = store.get(key)
    now = time.time()
    if isinstance(hit, dict) and now - float(hit.get("ts") or 0) < _TTL_SEC:
        out = dict(hit)
        out.pop("ts", None)
        return out

    found = _suggest(name) or _suggest(key)
    result = dict(empty)
    if found:
        cap = _quote_cap(found.get("code") or "")
        result["listed"] = cap is not None
        result["market_cap_yi"] = cap
        result["matched_name"] = found.get("name") or ""
        result["source"] = "eastmoney"
        if cap is None:
            result["score_delta"] = -1
            result["label"] = "已检索到证券代码，但暂无市值"
        elif cap >= 200:
            result["score_delta"] = 3
            result["label"] = f"上市公司，总市值约 {cap:.0f} 亿元，规模较稳"
        elif cap >= 50:
            result["score_delta"] = 2
            result["label"] = f"上市公司，总市值约 {cap:.0f} 亿元"
        elif cap >= 10:
            result["score_delta"] = 1
            result["label"] = f"上市公司，总市值约 {cap:.0f} 亿元"
        else:
            result["score_delta"] = -1
            result["label"] = f"已上市但市值约 {cap:.1f} 亿元，规模偏小"
    store[key] = {**result, "ts": now}
    if cache is None:
        try:
            _save_cache(store)
        except OSError:
            pass
    else:
        cache[key] = store[key]
    return result


def flush_company_cache(cache: dict[str, Any]) -> None:
    try:
        existing = _load_cache()
        existing.update(cache)
        _save_cache(existing)
    except OSError:
        pass


def score_enterprise(job: dict[str, Any], *, cache: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cat = str(job.get("jobCategory") or job.get("job_category") or "")
    if cat not in ("ENTERPRISE", "企业公司", ""):
        # 空大类也可能是企业，仍尝试；机关媒体明确跳过
        if cat in ("GOVERNMENT", "ACADEMIC", "MEDIA", "党政机关", "学术教职", "新闻媒体"):
            return {
                "listed": False,
                "market_cap_yi": None,
                "score_delta": 0,
                "label": "",
                "source": "skipped",
                "matched_name": "",
            }
    name = str(job.get("companyName") or job.get("company_name") or "")
    return lookup_company(name, cache=cache)
