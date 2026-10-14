"""261013 版简历解析器：经历分段、保守重分类、跨字段去重和调用追踪。"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from resume_parser.extractors.docx_extractor import extract_text_from_docx
from resume_parser.extractors.image_extractor import extract_text_from_image
from resume_parser.extractors.pdf_extractor_261013 import (
    extract_text_from_pdf_with_meta_261013,
)
from resume_parser.llm.deepseek_client_261013 import DeepSeekClient261013
from resume_parser.llm.io_log_261013 import (
    ModelIOLogger261013,
    TraceContext261013,
    hash_actor,
    hash_text,
    new_request_id,
)


FIELD_NAMES: list[str] = [
    "real_name",
    "gender",
    "birth_date",
    "political_status",
    "phone",
    "email",
    "wechat",
    "hometown",
    "grade",
    "major",
    "edu_level",
    "supervisor",
    "intention_order",
    "intention_city",
    "intention_dream",
    "mindset",
    "personal_intro",
    "basic_info",
    "education",
    "internship",
    "campus",
    "awards",
    "skills",
    "portfolio",
    "remark",
]

_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
_NUMERIC_FIELDS = frozenset({"gender", "political_status", "edu_level", "mindset"})
_SECTION_HEADING_RE = re.compile(
    r"^(?:教育背景|教育经历|实习经历|工作经历|实践经历|校园经历|在校经历|"
    r"项目经历|获奖经历|荣誉奖励|专业技能|技能证书|作品集|个人信息|基本信息|"
    r"自我评价|个人简况|education|internships?|work experience|campus experience|"
    r"projects?|skills?|awards?|profile|summary)\s*[:：]?$",
    re.I,
)
_CAMPUS_RE = re.compile(
    r"学生会|校媒|校园媒体|校级组织|记者团|广播台|校电视台|校(?:园)?融媒体中心|"
    r"校(?:园)?新媒体中心|院(?:系)?融媒体中心|社团|团支书|班级|"
    r"课程项目|课程作业|竞赛项目|比赛项目|大创|创新杯|案例库团队|校园活动|"
    r"高校互培|品牌精英|企业命题|校企(?:合作)?|社会实践|志愿(?:项目|服务)|"
    r"独立(?:报道|项目)|外部合作项目|营销策划方案|整合营销策划方案|"
    r"(?:大学|学院).{0,12}(?:学生|编辑部|新媒体中心|融媒体中心|媒体中心|团队)"
)
_CAMPUS_STRONG_RE = re.compile(
    r"学生会|校媒|校园|校级|记者团|校电视台|校(?:园)?(?:融媒体|新媒体)中心|"
    r"院(?:系)?融媒体中心|社团|团支书|班级|课程|竞赛|比赛|大创|创新杯|"
    r"高校互培|品牌精英|企业命题|校企(?:合作)?|社会实践|志愿(?:项目|服务)|"
    r"(?:大学|学院).{0,12}(?:学生|编辑部|新媒体中心|融媒体中心|媒体中心|团队)"
)
_PROFESSIONAL_RE = re.compile(
    r"实习(?:生|记者|编辑|运营|岗位)?|(?:任职|就职|受雇|全职|兼职)(?:于|为)?|"
    r"(?:工作|职业)经历"
)
_ENTRY_START_RE = re.compile(
    r"^(?:[-*•·]\s*)?(?:(?:19|20)\d{2}(?:[./年-]\d{1,2})?|至今)"
)
_INLINE_DATE_BOUNDARY_RE = re.compile(
    r"(?<=[。！？])\s*(?=(?:19|20)\d{2}(?:[./年-]\d{1,2}))"
)
_BASIC_INFO_OWNED_LABEL_RE = re.compile(
    r"^(?:姓名|性别|出生(?:日期|年月)?|年龄|手机(?:号码)?|电话|邮箱|微信(?:号)?|"
    r"学校|就读院校|毕业院校|专业|学历|学位|毕业年份|年级|政治面貌|生源地|"
    r"籍贯|导师)\s*[:：]"
)
_LANGUAGE_SCORE_RE = re.compile(
    r"(?:雅思|IELTS|托福|TOEFL|英语(?:专业)?[四六]级|大学英语[四六]级|CET[- ]?[46])"
    r"\s*[:：]?\s*\d+(?:\.\d+)?(?:分)?",
    re.I,
)
_LANGUAGE_TOPIC_RE = re.compile(
    r"雅思|IELTS|托福|TOEFL|英语|CET[- ]?[46]|外语|听说读写|工作语言", re.I
)
_EXPERIENCE_PIPE_RE = re.compile(r"\s*[|｜│]\s*")
_EXPERIENCE_DETAIL_RE = re.compile(r"[:：]")
_EXPERIENCE_DETAIL_SIGNAL_RE = re.compile(
    r"负责|参与|完成|协助|主导|撰写|策划|运营|制作|对接|调研|研究|分析|"
    r"设计|开发|执行|组织|管理|维护|发布|产出|承担|牵头|统筹|开展|推进|"
    r"提供|担任|具备|成果|获(?:得|评)|提升|实现"
)
_EXPERIENCE_DATE_TOKEN = r"(?:19|20)\d{2}(?:[./年-]\d{1,2}(?:月)?)?"
_EXPERIENCE_TIME_RE = re.compile(
    rf"^(?:时间\s*[:：]\s*)?(?:"
    rf"{_EXPERIENCE_DATE_TOKEN}"
    rf"(?:\s*(?:"
    rf"[-–—~～/]\s*(?:{_EXPERIENCE_DATE_TOKEN}|至今|现在|present)"
    rf"|(?:至|到)\s*(?:{_EXPERIENCE_DATE_TOKEN}|今|现在|present)"
    rf"|(?:、|,|，|和|及)\s*{_EXPERIENCE_DATE_TOKEN}"
    rf"))*"
    rf"|至今|现在|present)"
    rf"(?:\s*[（(][^）)\n]{{0,20}}[）)])?$",
    re.I,
)
_EXPERIENCE_LEADING_TIME_RE = re.compile(
    rf"^(?P<time>{_EXPERIENCE_DATE_TOKEN}(?:\s*(?:"
    rf"[-–—~～/]\s*(?:{_EXPERIENCE_DATE_TOKEN}|至今|现在|present)"
    rf"|(?:至|到)\s*(?:{_EXPERIENCE_DATE_TOKEN}|今|现在|present)"
    rf"|(?:、|,|，|和|及)\s*{_EXPERIENCE_DATE_TOKEN}"
    rf"))*)\s+(?P<header>.+)$",
    re.I,
)
_EXPERIENCE_TIME_AT_START_RE = re.compile(
    rf"^(?:时间\s*[:：]\s*)?{_EXPERIENCE_DATE_TOKEN}", re.I
)


@dataclass(frozen=True)
class ExperienceDisplayParts261013:
    """一段经历的展示字段；fallback_header 用于无法可靠判断顺序的输入。"""

    organization: str = ""
    role: str = ""
    time: str = ""
    detail: str = ""
    fallback_header: tuple[str, ...] = ()


class _LLMClient(Protocol):
    last_usage: dict[str, int]

    def parse_resume_to_dict(
        self,
        resume_text: str,
        *,
        trace: TraceContext261013 | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


def _empty_record() -> dict[str, Any]:
    return {key: [] if key == "intention_city" else "" for key in FIELD_NAMES}


def _clean_scalar(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value)).strip()


def _canonical(value: str) -> str:
    key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())
    key = key.replace("ielts", "雅思").replace("toefl", "托福")
    key = re.sub(r"(?:cet6|大学英语六级)", "英语六级", key)
    key = re.sub(r"(?:cet4|大学英语四级)", "英语四级", key)
    return key


def _strip_bullet(value: str) -> str:
    # 序号通常为 1-2 位，不能把“2026.03”误当作编号并删掉年份。
    return re.sub(r"^\s*(?:[-*•·]|\d{1,2}[.)、])\s*", "", value).strip()


def _unique_items(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _strip_bullet(_clean_scalar(item))
        key = _canonical(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _dict_to_item(value: dict[str, Any]) -> str:
    if isinstance(value.get("text"), str):
        return _clean_scalar(value["text"])
    ordered_keys = ("time", "organization", "role", "tasks", "results")
    parts: list[str] = []
    for key in ordered_keys:
        item = value.get(key)
        if isinstance(item, list):
            text = "；".join(
                _clean_scalar(entry) for entry in item if _clean_scalar(entry)
            )
        else:
            text = _clean_scalar(item)
        if text:
            parts.append(text)
    if parts:
        return "｜".join(parts)
    return "｜".join(
        _clean_scalar(item) for item in value.values() if _clean_scalar(item)
    )


def _as_items(value: Any, *, split_semicolons: bool = False) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, dict):
                values.append(_dict_to_item(item))
            else:
                text = _clean_scalar(item)
                if split_semicolons:
                    values.extend(re.split(r"(?:\n+|[；;]+)", text))
                else:
                    values.extend(re.split(r"\n+", text))
        return _unique_items(values)
    if isinstance(value, dict):
        return _unique_items([_dict_to_item(value)])

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return _as_items(decoded, split_semicolons=split_semicolons)

    pattern = r"\n+"
    if split_semicolons:
        pattern = r"(?:\n+|[；;]+)"
    return _unique_items(re.split(pattern, text))


def _as_experience_items(value: Any) -> tuple[list[str], int]:
    """兼容模型把多段经历塞进一个值，同时保留单段经历内部的换行。"""
    if value is None or value == "":
        return [], 0

    items: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                text = _dict_to_item(item)
            else:
                text = str(item or "").replace("\r\n", "\n").replace("\r", "\n")
            if text.strip():
                items.append(text.strip())
    elif isinstance(value, dict):
        items.append(_dict_to_item(value))
    else:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                return _as_experience_items(decoded)
        # 最终展示格式用单换行分隔标题与详情，用双换行分隔不同经历。
        items.extend(part.strip() for part in re.split(r"\n{2,}", text) if part.strip())

    result: list[str] = []
    split_count = 0
    for item in items:
        parts = [
            part.strip()
            for part in _INLINE_DATE_BOUNDARY_RE.split(item)
            if part.strip()
        ]
        if len(parts) > 1:
            split_count += len(parts) - 1
        result.extend(parts)
    return _unique_items(result), split_count


def _looks_like_experience_time(value: str) -> bool:
    candidate = value.strip()
    if len(candidate) >= 2 and (
        (candidate[0], candidate[-1]) in {("(", ")"), ("（", "）")}
    ):
        candidate = candidate[1:-1].strip()
    return bool(_EXPERIENCE_TIME_RE.fullmatch(candidate))


def _split_experience_detail(
    value: str, *, expected_time: bool = False, confident: bool = False
) -> tuple[str, str]:
    """只在可靠位置拆首个详情冒号，避免误拆公司名和 URL。"""
    source = value.strip()
    for match in _EXPERIENCE_DETAIL_RE.finditer(source):
        if source[match.start() : match.start() + 3] == "://":
            continue
        head = source[: match.start()].strip()
        detail = source[match.end() :].strip()
        if not head or not detail:
            continue
        if expected_time:
            if _looks_like_experience_time(head):
                return head, detail
            continue
        if confident or _EXPERIENCE_DETAIL_SIGNAL_RE.search(detail):
            return head, detail
    return source, ""


def _time_and_detail(value: str) -> tuple[str, str]:
    if _looks_like_experience_time(value):
        return value.strip(), ""
    head, detail = _split_experience_detail(value, expected_time=True)
    if detail:
        return head, detail
    return "", ""


def _join_experience_details(*values: str) -> str:
    parts: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in parts:
            parts.append(clean)
    return "\n".join(parts)


def parse_experience_display_261013(value: str) -> ExperienceDisplayParts261013:
    """保守解析旧/新经历文本，为统一展示顺序提供结构化字段。"""
    source = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in source.split("\n") if line.strip()]
    if not lines:
        return ExperienceDisplayParts261013()

    header = _strip_bullet(lines[0])
    trailing_detail = "\n".join(lines[1:])
    pipe_parts = _EXPERIENCE_PIPE_RE.split(header)

    if len(pipe_parts) > 1:
        parts = [part.strip() for part in pipe_parts]
        first_is_time = _looks_like_experience_time(parts[0])
        last_time, last_detail = _time_and_detail(parts[-1])
        last_is_time = bool(last_time)

        if first_is_time and not last_is_time:
            organization = parts[1] if len(parts) >= 2 else ""
            role_source = parts[2] if len(parts) >= 3 else ""
            role, role_detail = _split_experience_detail(role_source, confident=True)
            extra_detail = "；".join(part for part in parts[3:] if part)
            return ExperienceDisplayParts261013(
                organization=organization,
                role=role,
                time=parts[0],
                detail=_join_experience_details(
                    role_detail, extra_detail, trailing_detail
                ),
            )

        if last_is_time and not first_is_time:
            organization = parts[0]
            role = " | ".join(part for part in parts[1:-1] if part)
            return ExperienceDisplayParts261013(
                organization=organization,
                role=role,
                time=last_time,
                detail=_join_experience_details(last_detail, trailing_detail),
            )

        # 时间缺失或首尾同时像时间时不猜顺序，只标准化分隔符。
        last_head, inferred_detail = _split_experience_detail(parts[-1])
        if inferred_detail:
            parts[-1] = last_head
        return ExperienceDisplayParts261013(
            detail=_join_experience_details(inferred_detail, trailing_detail),
            fallback_header=tuple(parts),
        )

    colon_left = _EXPERIENCE_DETAIL_RE.split(header, maxsplit=1)[0].strip()
    last_token_before_colon = colon_left.rsplit(maxsplit=1)[-1]
    time_anchored = bool(_EXPERIENCE_TIME_AT_START_RE.match(header)) or (
        _looks_like_experience_time(last_token_before_colon)
    )
    head, inline_detail = _split_experience_detail(header, confident=time_anchored)
    leading_match = _EXPERIENCE_LEADING_TIME_RE.fullmatch(head)
    if leading_match:
        remainder = leading_match.group("header").strip()
        remainder_parts = remainder.split(maxsplit=1)
        return ExperienceDisplayParts261013(
            organization=remainder_parts[0] if remainder_parts else "",
            role=remainder_parts[1] if len(remainder_parts) > 1 else "",
            time=leading_match.group("time").strip(),
            detail=_join_experience_details(inline_detail, trailing_detail),
        )

    tokens = head.rsplit(maxsplit=1)
    if len(tokens) == 2 and _looks_like_experience_time(tokens[-1]):
        organization_and_role = tokens[0].split(maxsplit=1)
        return ExperienceDisplayParts261013(
            organization=organization_and_role[0],
            role=(organization_and_role[1] if len(organization_and_role) > 1 else ""),
            time=tokens[-1],
            detail=_join_experience_details(inline_detail, trailing_detail),
        )

    return ExperienceDisplayParts261013(
        detail=_join_experience_details(inline_detail, trailing_detail),
        fallback_header=(head,),
    )


def format_experience_display_261013(value: str) -> str:
    """输出“单位/项目 | 岗位/角色 | 时间”，并把详情放到下一行。"""
    parts = parse_experience_display_261013(value)
    if parts.fallback_header:
        header_values = parts.fallback_header
    else:
        header_values = (parts.organization, parts.role, parts.time)
    header = " | ".join(item.strip() for item in header_values if item.strip())
    if header and parts.detail:
        return f"{header}\n{parts.detail}"
    return header or parts.detail


def _date_tokens(value: str) -> set[str]:
    return {
        f"{year}{int(month or 0):02d}"
        for year, month in re.findall(r"((?:19|20)\d{2})(?:[./年-](\d{1,2}))?", value)
    }


def _same_experience(left: str, right: str) -> bool:
    left_key = _canonical(left)
    right_key = _canonical(right)
    if not left_key or not right_key:
        return False
    if min(len(left_key), len(right_key)) >= 10 and (
        left_key in right_key or right_key in left_key
    ):
        return True

    left_dates = _date_tokens(left)
    right_dates = _date_tokens(right)
    if left_dates and right_dates and left_dates.isdisjoint(right_dates):
        return False
    if min(len(left_key), len(right_key)) < 12:
        return False
    left_pairs = {left_key[index : index + 2] for index in range(len(left_key) - 1)}
    right_pairs = {right_key[index : index + 2] for index in range(len(right_key) - 1)}
    denominator = min(len(left_pairs), len(right_pairs))
    return bool(denominator and len(left_pairs & right_pairs) / denominator >= 0.68)


def _unique_experiences(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in _unique_items(items):
        if any(_same_experience(item, existing) for existing in result):
            continue
        result.append(item)
    return result


def _reverse_chronological(items: list[str]) -> list[str]:
    """有明确日期的经历倒序排列；无日期条目保持原相对顺序并置于其后。"""
    decorated: list[tuple[tuple[int, int, int], str]] = []
    for index, item in enumerate(items):
        dates = _date_tokens(item)
        newest = max((int(value) for value in dates), default=0)
        ongoing = 1 if "至今" in item else 0
        decorated.append(((ongoing, newest, -index), item))
    return [
        item for _, item in sorted(decorated, key=lambda pair: pair[0], reverse=True)
    ]


def _format_items(items: list[str], *, multiline: bool) -> str:
    if not items:
        return ""
    if multiline:
        return "\n\n".join(f"• {item}" for item in items)
    return "；".join(items)


def _format_experience_items(items: list[str]) -> str:
    formatted = [format_experience_display_261013(item) for item in items]
    return "\n\n".join(item for item in formatted if item)


def clean_ocr_text_261013(text: str) -> str:
    """清洗 OCR 断行，同时保留简历栏目标题作为分段边界。"""
    if not text:
        return ""
    source_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    for raw_line in source_lines:
        line = re.sub(r"[ \t]+", " ", raw_line.strip())
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        is_heading = bool(_SECTION_HEADING_RE.fullmatch(line))
        is_entry_start = bool(_ENTRY_START_RE.match(line))
        previous = output[-1] if output else ""
        previous_is_heading = bool(_SECTION_HEADING_RE.fullmatch(previous))
        if is_heading:
            if output and output[-1] != "":
                output.append("")
            output.append(line)
            output.append("")
            continue
        if (
            previous
            and not previous_is_heading
            and not is_entry_start
            and len(line) <= 40
            and not previous.endswith(("。", "！", "？", "：", "；", ".", "!", "?"))
        ):
            output[-1] = f"{previous} {line}".strip()
        else:
            output.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(output)).strip()


def _flatten_raw(raw: dict[str, Any]) -> dict[str, Any]:
    flat = {key: value for key, value in raw.items() if key in FIELD_NAMES}
    for nested_key in ("fc_user_profile", "fc_resume"):
        nested = raw.get(nested_key)
        if isinstance(nested, dict):
            for key, value in nested.items():
                if key in FIELD_NAMES:
                    flat[key] = value
    return flat if flat else raw


def _coerce_numeric(value: Any) -> str:
    if value is None or value == "" or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(int(value))
    text = str(value).strip()
    return text if text.isdigit() else ""


def _normalize_cities(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique_items([_clean_scalar(item) for item in value])
    text = _clean_scalar(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return _unique_items([_clean_scalar(item) for item in decoded])
    return _unique_items(re.split(r"[,，、；;\n]+", text))


def _is_campus(item: str) -> bool:
    return bool(_CAMPUS_RE.search(item))


def _is_strong_campus(item: str) -> bool:
    return bool(_CAMPUS_STRONG_RE.search(item))


def _is_professional(item: str) -> bool:
    return bool(_PROFESSIONAL_RE.search(item))


def _normalize_experiences(
    internship_value: Any, campus_value: Any
) -> tuple[list[str], list[str], list[str]]:
    internships: list[str] = []
    campus_items: list[str] = []
    warnings: list[str] = []

    internship_source, internship_splits = _as_experience_items(internship_value)
    campus_source, campus_splits = _as_experience_items(campus_value)
    if internship_splits or campus_splits:
        warnings.append("split_merged_experience_item")

    for item in internship_source:
        campus_signal = _is_campus(item)
        professional_signal = _is_professional(item)
        if campus_signal and professional_signal:
            warnings.append("classification_conflict_kept_original")
        if _is_strong_campus(item) and not professional_signal:
            campus_items.append(item)
            warnings.append("moved_internship_item_to_campus")
        else:
            internships.append(item)
    for item in campus_source:
        campus_signal = _is_campus(item)
        professional_signal = _is_professional(item)
        if campus_signal and professional_signal:
            warnings.append("classification_conflict_kept_original")
        if professional_signal and not campus_signal:
            internships.append(item)
            warnings.append("moved_campus_item_to_internship")
        else:
            campus_items.append(item)

    internships = _unique_experiences(internships)
    deduped_campus: list[str] = []
    for item in _unique_experiences(campus_items):
        if any(_same_experience(item, internship) for internship in internships):
            warnings.append("removed_cross_field_experience_duplicate")
            continue
        deduped_campus.append(item)
    return (
        _reverse_chronological(internships),
        _reverse_chronological(deduped_campus),
        sorted(set(warnings)),
    )


def _clean_basic_info(value: Any) -> str:
    clauses = _as_items(value, split_semicolons=True)
    fragments = [
        fragment.strip()
        for clause in clauses
        for fragment in re.split(r"[，,|｜]+", clause)
        if fragment.strip()
    ]
    kept = [
        fragment
        for fragment in fragments
        if not _BASIC_INFO_OWNED_LABEL_RE.match(fragment)
    ]
    return "；".join(kept)


def _remove_intro_language_scores(intro: str, skills: str) -> str:
    result = intro
    skill_key = _canonical(skills)
    for match in list(_LANGUAGE_SCORE_RE.finditer(intro)):
        if _canonical(match.group(0)) in skill_key:
            result = result.replace(match.group(0), "")
    result = re.sub(r"[，、；]\s*[，、；]+", "，", result)
    result = re.sub(r"[，；]\s*([。！？])", r"\1", result)
    result = re.sub(r"\s+([，。；])", r"\1", result)
    return result.strip(" ，、；。")


def _clean_remark(value: Any, other_fields: list[str], skills: str) -> str:
    references = [_canonical(item) for item in other_fields if _canonical(item)]
    has_language_skill = bool(_LANGUAGE_TOPIC_RE.search(skills))
    kept: list[str] = []
    for item in _as_items(value, split_semicolons=True):
        key = _canonical(item)
        if len(key) >= 4 and any(key in reference for reference in references):
            continue
        if has_language_skill and _LANGUAGE_TOPIC_RE.search(item):
            continue
        kept.append(item)
    return "；".join(_unique_items(kept))


def _normalize_model_output_261013(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = _flatten_raw(raw)
    output = _empty_record()

    for key in FIELD_NAMES[:16]:
        value = source.get(key)
        if key == "intention_city":
            output[key] = _normalize_cities(value)
        elif key in _NUMERIC_FIELDS:
            output[key] = _coerce_numeric(value)
        else:
            output[key] = _clean_scalar(value)

    internships, campus_items, warnings = _normalize_experiences(
        source.get("internship"), source.get("campus")
    )
    education_items = _reverse_chronological(_as_items(source.get("education")))
    award_items = _as_items(source.get("awards"), split_semicolons=True)
    skill_items = _as_items(source.get("skills"), split_semicolons=True)
    portfolio_items = _as_items(source.get("portfolio"))

    output["education"] = _format_items(education_items, multiline=True)
    output["internship"] = _format_experience_items(internships)
    output["campus"] = _format_experience_items(campus_items)
    output["awards"] = _format_items(award_items, multiline=False)
    output["skills"] = _format_items(skill_items, multiline=False)
    output["portfolio"] = _format_items(portfolio_items, multiline=True)
    output["basic_info"] = _clean_basic_info(source.get("basic_info"))
    output["personal_intro"] = _remove_intro_language_scores(
        _clean_scalar(source.get("personal_intro")), output["skills"]
    )
    output["remark"] = _clean_remark(
        source.get("remark"),
        [
            output["personal_intro"],
            output["basic_info"],
            output["education"],
            output["internship"],
            output["campus"],
            output["awards"],
            output["skills"],
            output["portfolio"],
        ],
        output["skills"],
    )

    diagnostics = {
        "entry_counts": {
            "education": len(education_items),
            "internship": len(internships),
            "campus": len(campus_items),
            "awards": len(award_items),
            "skills": len(skill_items),
            "portfolio": len(portfolio_items),
        },
        "normalization_warnings": warnings,
        "output_fields": sorted(
            key for key, value in output.items() if value not in ("", [])
        ),
    }
    return output, diagnostics


def _extract_plain_text_261013(file_path: str) -> tuple[str, bool, dict[str, Any]]:
    path = Path(file_path)
    extension = path.suffix.lower()
    if extension in _IMAGE_SUFFIXES:
        text = extract_text_from_image(str(path))
        return (
            text,
            True,
            {
                "extractor": "image_ocr",
                "input_chars": len(text),
                "input_lines": len(text.splitlines()),
            },
        )
    if extension == ".docx":
        text = extract_text_from_docx(str(path))
        return (
            text,
            False,
            {
                "extractor": "docx",
                "input_chars": len(text),
                "input_lines": len(text.splitlines()),
            },
        )
    if extension == ".pdf":
        text, diagnostics = extract_text_from_pdf_with_meta_261013(str(path))
        return text, False, {"extractor": "pdfplumber_261013", **diagnostics}
    raise ValueError(
        f"Unsupported file format: {extension or '(no extension)'}. "
        "Supported: .docx, .pdf, .png, .jpg, .jpeg"
    )


def _row_for_csv(record: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for key in FIELD_NAMES:
        value = record.get(key, [] if key == "intention_city" else "")
        if key == "intention_city":
            row[key] = json.dumps(value, ensure_ascii=False) if value else ""
        else:
            row[key] = "" if value is None else str(value)
    return row


class ResumeParser261013:
    def __init__(
        self,
        api_key: str = "",
        *,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        llm_client: _LLMClient | None = None,
        io_logger: ModelIOLogger261013 | None = None,
        actor_hmac_secret: str = "",
    ) -> None:
        self._io_logger = io_logger or ModelIOLogger261013()
        self._llm: _LLMClient = llm_client or DeepSeekClient261013(
            api_key=api_key,
            model=model,
            base_url=base_url,
            io_logger=self._io_logger,
        )
        self._actor_hmac_secret = actor_hmac_secret
        self.last_metrics: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_calls": 0,
            "elapsed_seconds": 0.0,
            "request_id": "",
            "normalization": {},
        }

    def _trace(
        self, *, request_id: str, actor_id: str, source_kind: str, source_text: str
    ) -> TraceContext261013:
        return TraceContext261013(
            request_id=request_id,
            actor_hash=hash_actor(actor_id, self._actor_hmac_secret),
            source_kind=source_kind,
            source_sha256=hash_text(source_text),
        )

    def _record_metrics(
        self, started_at: float, request_id: str, normalization: dict[str, Any]
    ) -> None:
        usage = getattr(self._llm, "last_usage", {}) or {}
        self.last_metrics = {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "api_calls": int(usage.get("api_calls", 0) or 0),
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "request_id": request_id,
            "normalization": normalization,
        }

    def parse(
        self, file_path: str, *, actor_id: str = "", request_id: str = ""
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        current_request_id = request_id or new_request_id()
        normalization: dict[str, Any] = {}
        source_kind = Path(file_path).suffix.lower().lstrip(".") or "file"
        trace = self._trace(
            request_id=current_request_id,
            actor_id=actor_id,
            source_kind=source_kind,
            source_text="",
        )
        stage = "extract"
        extraction: dict[str, Any] = {"file_extension": source_kind}
        try:
            text, from_ocr, extraction = _extract_plain_text_261013(file_path)
            text = clean_ocr_text_261013(text) if from_ocr else text.strip()
            if not text:
                raise ValueError(
                    "未从简历文件中提取到文本；扫描版 PDF 请先转为图片或执行 OCR。"
                )
            trace = self._trace(
                request_id=current_request_id,
                actor_id=actor_id,
                source_kind=source_kind,
                source_text=text,
            )
            stage = "model"
            raw = self._llm.parse_resume_to_dict(
                text,
                trace=trace,
                diagnostics=extraction,
            )
            stage = "normalize"
            result, normalization = _normalize_model_output_261013(raw)
            self._io_logger.log_normalized(
                trace=trace,
                model=str(getattr(self._llm, "_model", "unknown")),
                normalized_output=result,
                diagnostics={**extraction, **normalization},
            )
            return result
        except Exception as exc:
            self._io_logger.log_pipeline_error(
                trace=trace,
                model=str(getattr(self._llm, "_model", "unknown")),
                error_type=type(exc).__name__,
                stage=stage,
                diagnostics=extraction,
            )
            raise
        finally:
            self._record_metrics(started_at, current_request_id, normalization)

    def parse_text(
        self, text: str, *, actor_id: str = "", request_id: str = ""
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        current_request_id = request_id or new_request_id()
        normalization: dict[str, Any] = {}
        clean_text = str(text or "").strip()
        trace = self._trace(
            request_id=current_request_id,
            actor_id=actor_id,
            source_kind="raw_text",
            source_text=clean_text,
        )
        stage = "validate"
        extraction = {
            "extractor": "raw_text",
            "input_chars": len(clean_text),
            "input_lines": len(clean_text.splitlines()),
        }
        try:
            if not clean_text:
                raise ValueError("简历文本不能为空")
            stage = "model"
            raw = self._llm.parse_resume_to_dict(
                clean_text,
                trace=trace,
                diagnostics=extraction,
            )
            stage = "normalize"
            result, normalization = _normalize_model_output_261013(raw)
            self._io_logger.log_normalized(
                trace=trace,
                model=str(getattr(self._llm, "_model", "unknown")),
                normalized_output=result,
                diagnostics={**extraction, **normalization},
            )
            return result
        except Exception as exc:
            self._io_logger.log_pipeline_error(
                trace=trace,
                model=str(getattr(self._llm, "_model", "unknown")),
                error_type=type(exc).__name__,
                stage=stage,
                diagnostics=extraction,
            )
            raise
        finally:
            self._record_metrics(started_at, current_request_id, normalization)

    def parse_batch_to_csv(self, file_paths: list[str], output_csv: str) -> None:
        rows = [_row_for_csv(self.parse(file_path)) for file_path in file_paths]
        output_path = Path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=FIELD_NAMES, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def extract_plain_text(file_path: str) -> tuple[str, bool]:
        """兼容旧版公共方法的二元返回值。"""
        text, from_ocr, _ = _extract_plain_text_261013(file_path)
        return text, from_ocr

    @staticmethod
    def extract_plain_text_with_meta(
        file_path: str,
    ) -> tuple[str, bool, dict[str, Any]]:
        return _extract_plain_text_261013(file_path)


ResumeParser = ResumeParser261013
