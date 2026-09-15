"""
管理员端「智能解析岗位描述」：从粘贴的岗位原文抽取表单字段。

与爬虫抽取共用字段映射，提示词针对辅导员粘贴文本单独缩短：
- 学院内推 / 大实习 / 小实习
- 无年份日期按当前日期补全
- 非推理模型 + JSON 模式，缩短等待
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from job_structuring import paths
from job_structuring.dates import current_date_prompt_line
from job_structuring.engine import (
    _extract_positions_list,
    _llm_chat,
    _zh_item_to_job_row,
    load_config,
)

# 专供「新建岗位」表单：比爬虫提示词短，减少等待。
ADMIN_SYSTEM_PROMPT = """你是管理后台「新建岗位」表单填写助手。只根据岗位原文抽取，禁止编造。
直接输出 JSON：{"岗位列表":[{...}]}，不要思考过程、不要解释。

一文多岗则拆成多条（后台用第一条回填表单）。键名必须用下列中文。
来源类型固定「平台发布」。数字不详用 null；「若干」人数用 null。日期 YYYY-MM-DD。

键：来源类型,单位名称,部门,岗位名称,岗位大类,岗位二级分类,招聘类型,招聘人数,工作开始日,工作结束日,投递截止日期,每周工作天数,每周工作天数类型,实习总时长类型,工作形式,工作城市,工作省份,工作地点原文,薪资下限,薪资上限,薪资展示,岗位描述,学历要求,专业要求,届别要求,技能要求,其他要求与投递说明,岗位状态

枚举：
- 岗位大类：学术教职 | 党政机关 | 新闻媒体 | 企业公司 | 其他
- 岗位二级分类：升学深造 | 考取教职 | 中学教师 | 选调生 | 公务员 | 高校行政 | 医院 | 银行 | 其他事业单位 | 党报央媒 | 地区主流媒体 | 其他媒体机构 | 自媒体 | 国央企 | 民企 | 外企 | 其他
- 招聘类型：大实习 | 小实习 | 日常实习 | 应届生招聘 | 应届生摸排 | 其他
- 每周工作天数类型：一周1-2天 | 一周3-4天 | 一周5天
- 实习总时长类型：3个月以内 | 3-6个月 | 6个月以上
- 工作形式：线上 | 线下 | 线上线下均可
- 学历要求：本科生 | 学术硕士研究生 | 专业硕士研究生 | 硕士研究生 | 博士研究生
- 岗位状态：发布中 | 已截止

规则：
1. 「大实习」「小实习」必须写入招聘类型对应项。
2. 「学院内推」写入其他要求与投递说明（如「来源：学院内推」），不是单位名或岗位名。
3. 日期只有月日时，按用户消息中的当前日期补年份：投递截止今年该月日已过则用明年。
4. 岗位名称要具体；单位名称用用人单位名，去掉「校园招聘/招聘简章」后缀。
5. 原文有的表单信息尽量填；没有的留空，不要编造薪资、邮箱、截止日期。
"""

_ADMIN_USER_HINT = (
    "请抽取与新建岗位表单相关的全部字段。"
    "来源类型填「平台发布」。直接输出 {\"岗位列表\":[...]}。"
)


def parse_job_text(
    raw_text: str,
    config: Optional[dict] = None,
    *,
    source: str = "admin",
) -> dict[str, Any]:
    """
    解析管理员粘贴的岗位原文。
    返回表单字段（顶层 camelCase）+ position/positions/meta。
    """
    text = (raw_text or "").strip()
    empty_meta = {"parsed_count": 0}
    if not text:
        return _http_payload([], {**empty_meta, "error": "empty_text"})

    if config is None:
        config = load_config()
    paths.configure(config)

    title_guess = _first_line_title(text)
    user = "\n\n".join(
        [
            current_date_prompt_line(),
            _ADMIN_USER_HINT,
            f"文本首行参考：{title_guess}",
            f"岗位原文：\n\n{text[:20000]}",
        ]
    )
    messages = [
        {"role": "system", "content": ADMIN_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    content = _llm_chat(
        messages,
        config,
        json_object=True,
        max_tokens=int(config.get("admin_llm_max_tokens") or 3072),
        prefer_fast=True,
        log_channel="admin",
        log_title=title_guess,
        log_source=source,
        timeout=int(config.get("admin_llm_timeout_seconds") or 60),
    )
    if content is None:
        return _http_payload([], {**empty_meta, "error": "llm_unavailable", "title_guess": title_guess})

    items = _extract_positions_list(content)
    if items is None:
        return _http_payload(
            [],
            {
                **empty_meta,
                "error": "invalid_json",
                "title_guess": title_guess,
                "raw": content[:2000],
            },
        )

    rows: list[dict] = []
    for zh_item in items:
        row = _zh_item_to_job_row(zh_item, "", source, title_guess)
        row["sourceType"] = "PLATFORM"
        if not row.get("companyName") and not row.get("positionName"):
            continue
        rows.append(_form_row(row))

    return _http_payload(
        rows,
        {"parsed_count": len(rows), "title_guess": title_guess},
    )


def _http_payload(rows: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    first = rows[0] if rows else None
    payload: dict[str, Any] = {
        "position": first,
        "positions": rows,
        "meta": meta,
    }
    if first:
        payload.update(first)
    return payload


def _form_row(row: dict) -> dict:
    """表单回填用：去掉爬虫溯源列，补投递截止日期别名。"""
    out = {k: v for k, v in row.items() if k != "source_md"}
    deadline = out.get("applyDeadline") or out.get("workEndDate") or ""
    if deadline:
        out["applyDeadline"] = deadline
    return out


def _first_line_title(text: str) -> str:
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:80]
    return ""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="管理员端岗位原文解析")
    parser.add_argument("text", nargs="?", help="岗位原文；省略则读 stdin")
    parser.add_argument("--file", help="从文件读取岗位原文")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw = f.read()
    elif args.text:
        raw = args.text
    else:
        raw = sys.stdin.read()

    result = parse_job_text(raw)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("position") else 1


if __name__ == "__main__":
    raise SystemExit(main())
