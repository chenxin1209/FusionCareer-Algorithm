"""
新闻学院相关性过滤。

老师口径：除专业外结合岗位名称判断；需要的是
宣传、行政、运营、市场、产品，以及新闻传播业务岗。
默认不保留（宁缺毋滥）。
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

# 复旦大学新闻学院（及同类新闻传播院系）开设/紧密相关专业关键词
OFFERED_MAJOR_KEYWORDS = (
    "新闻",
    "传播",
    "广告",
    "广播电视",
    "广电",
    "网络与新媒体",
    "新媒体",
    "编辑出版",
    "出版",
    "国际新闻",
    "国际传播",
    "传媒",
    "媒体",
    "数字媒体",
    "公共关系",
    "公关",
    "视听",
    "播音",
    "主持",
    "融媒体",
    "新闻与传播",
    "戏剧影视",
    "广播电视编导",
    "影视",
)

RELATED_MAJOR_KEYWORDS = (
    "中文",
    "汉语言",
    "文科",
    "人文",
    "社科",
    "社会学",
    "艺术",
    "视觉传达",
    "艺术设计",
    "平面设计",
    "广告设计",
    "市场营销",
    "外语",
    "英语",
    "翻译",
    "国际关系",
    "政治",
    "法学",
    "历史",
    "哲学",
)

UNRELATED_MAJOR_KEYWORDS = (
    "临床医学",
    "口腔",
    "护理",
    "药学",
    "医学检验",
    "船舶",
    "轮机",
    "航海",
    "土木工程",
    "建筑学",
    "给排水",
    "机械设计",
    "机械制造",
    "车辆工程",
    "电气工程",
    "自动化",
    "集成电路",
    "微电子",
    "半导体",
    "材料科学",
    "化学工程",
    "石油",
    "地质",
    "测绘",
    "矿",
    "农林",
    "园艺",
    "动物医学",
    "软件工程",
    "计算机科学",
    "计算机类",
    "电子信息工程",
    "通信工程",
    "光电",
    "测控",
    "能源动力",
    "核工程",
)

# 工科 / 医学 / 硬理工：即使岗位名带「产品/市场/运营」也默认删除
STEM_MEDICAL_MAJOR_KEYWORDS = UNRELATED_MAJOR_KEYWORDS + (
    "工科",
    "理工",
    "计算机",
    "软件",
    "电子信息",
    "电子",
    "电气",
    "机械",
    "自动化",
    "材料",
    "化工",
    "化学",
    "物理",
    "数学",
    "统计",
    "通信",
    "芯片",
    "光通信",
    "光传感",
    "光学",
    "车辆",
    "汽车",
    "生物医学",
    "生物医药",
    "生物",
    "医学",
    "药学",
    "中药",
    "临床",
    "护理",
    "兽医",
    "食品科学",
    "食品工程",
    "免疫",
    "生理",
    "动物模型",
)

# 新闻传播业务岗：专业是工科/医学也可以留
CORE_COMMS_KEYWORDS = (
    "新闻",
    "记者",
    "编辑",
    "编导",
    "主持",
    "媒体",
    "传媒",
    "融媒体",
    "新媒体",
    "内容",
    "公关",
    "广告",
    "传播",
    "宣传",
    "宣发",
    "美宣",
    "文案",
    "舆情",
    "采访",
    "报道",
    "校对",
    "短视频",
    "摄像",
    "摄影",
    "导演",
    "编剧",
    "企编",
    "全媒体",
    "出版",
    "品牌策划",
    "活动策划",
    "营销策划",
)

# 这些词才足以「带过」工科/医学专业；单靠 广告/传播/摄影 不够
STRONG_COMMS_KEYWORDS = (
    "新闻",
    "记者",
    "编辑",
    "编导",
    "主持",
    "媒体",
    "传媒",
    "融媒体",
    "新媒体",
    "内容",
    "公关",
    "传播",
    "宣传",
    "宣发",
    "美宣",
    "文案",
    "舆情",
    "采访",
    "报道",
    "短视频",
    "摄像",
    "企编",
    "全媒体",
    "出版",
    "品牌策划",
    "活动策划",
)

# 老师点名的相邻岗：专业不能是工科/医学
SOFT_BIZ_KEYWORDS = (
    "行政",
    "文秘",
    "办公室",
    "党务",
    "高校行政",
    "运营",
    "市场",
    "营销",
    "产品",
    "品牌",
    "视觉",
    "平面设计",
    "视频",
    "发行",
    "选调",
    "公务员",
    "事业编",
)

# 老师点名 + 新闻传播业务岗（岗位名白名单）
TARGET_POSITION_KEYWORDS = CORE_COMMS_KEYWORDS + SOFT_BIZ_KEYWORDS

# 带「运营/策划」但不属于宣传运营岗
WEAK_FALSE_FRIENDS = (
    "艺人",
    "主播",
    "培训运营",
    "学科运营",
    "教务运营",
    "仓储运营",
    "物流运营",
    "供应链运营",
    "智能运营",
    "体系运营",
    "分行运营",
    "运营培训生",
    "资金运营",
    "回款运营",
    "游戏视频",
    "游戏美术",
    "游戏策划",
    "关卡策划",
    "数值策划",
    "系统策划",
    "玩法策划",
    "技术策划",
)

# 岗位名里的工科/医学/销售硬信号（即使带了 产品/市场/传播）
STEM_TITLE_KEYWORDS = (
    "智能驾驶",
    "智能座舱",
    "车身域控",
    "域控",
    "智能底盘",
    "底盘",
    "产品验证",
    "产品平台",
    "计算摄影",
    "技术传播",
    "机器视觉",
    "售前技术",
    "算法工程师",
    "生成式算法",
    "研究算法",
    "技术管培",
    "数据管培",
    "教学管培",
    "服务管培",
    "外贸跟单",
    "内销业务员",
    "外销业务员",
    "业务员",
    "售后专员",
    "客诉",
    "集成供应链",
    "供应链体系",
    "精算",
    "负债评估",
    "专任教师",
    "专业课教师",
    "电子商务专业课",
    "工业设计",
    "产品教研",
    "学科产品",
    "招投标",
    "CCD视觉",
    "视觉应用",
)

IRRELEVANT_POSITION_KEYWORDS = (
    "船舶驾驶",
    "船舶轮机",
    "轮机员",
    "远洋船员",
    "集成电路",
    "芯片设计",
    "晶圆",
    "结构工程师",
    "土木工程师",
    "临床医师",
    "执业药师",
    "焊接",
    "数控",
    "机床",
    "算法",
    "嵌入式",
    "FPGA",
    "后端开发",
    "前端开发",
    "Java开发",
    "数据开发",
    "C++开发",
    "客户端开发",
    "开发工程师",
    "开发方向",
    "程序员",
    "硬件工程师",
    "电气工程师",
    "机械工程师",
    "工艺工程师",
    "质量工程师",
    "测试工程师",
    "技术支持",
    "大模型",
    "推荐算法",
    "自动驾驶",
    "数学老师",
    "物理老师",
    "化学老师",
    "英语老师",
    "语文老师",
    "班课老师",
    "伴学师",
    "教师管培",
    "售前方向",
    "财务",
    "会计",
    "法务",
    "律师",
    "人力",
    "HR",
    "招聘专员",
    "信用分析",
    "宏观策略",
    "销售助理",
    "销售管培",
    "KA销售",
    "偶像练习生",
    "才艺主播",
    "练习生",
    "原画",
    "角色原画",
    "游戏原画",
    "游戏客户端",
    "软件工程师",
    "电子工程师",
    "研发工程师",
    "产品工程师",
    "产品开发",
    "产品认证",
    "认证工程师",
    "运营工程师",
    "临床试验",
    "生信",
    "核酸",
    "测序",
    "兽药",
    "电芯",
    "微电子",
    "微流控",
    "工业设计工程师",
    "平面设计工程师",
    "项目工程师",
    "销售方向",
    "各团队综合",
    "综合职能",
)

_GENERIC_TITLES = (
    "实习生",
    "实习岗",
    "管培生",
    "校招生",
    "校园招聘",
    "探索者计划",
    "管培",
)

_BUNDLE_HINTS = ("类岗位", "等方向", "等多个", "岗位类别")
_TARGET_BUNDLE_HINTS = ("职能", "行政", "市场", "营销", "产品", "运营", "宣传", "媒体", "内容")
_TECH_BUNDLE_HINTS = ("产研", "研发", "技术类", "工程类", "业务类")

_UNLIMITED_HINTS = (
    "不限",
    "专业不限",
    "不限专业",
    "专业不限制",
    "不限学科",
    "不限院系",
    "均可",
    "不拘",
)

_SPLIT_RE = re.compile(r"[,，、/;；|｜和及与]+")


def _tokens(req_major: str) -> list[str]:
    s = (req_major or "").strip()
    if not s:
        return []
    return [t.strip() for t in _SPLIT_RE.split(s) if t.strip()]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _position_text(row: dict) -> str:
    # 只用岗位名判断。部门叫「产品事业群/营销体系」不能把工科岗洗进来。
    return str(row.get("positionName") or "").strip()


def _is_generic_title(title: str) -> bool:
    s = (title or "").strip()
    if not s:
        return True
    compact = re.sub(r"[\s（）()【】\[\]\-_|｜]+", "", s)
    return compact in {"实习生", "实习", "管培生", "校招生"} or s in _GENERIC_TITLES


def _is_watery_bundle(title: str) -> bool:
    """校招「一类里塞很多岗」：偏技术/销售的大礼包直接丢掉。"""
    if not title:
        return False
    if _contains_any(title, _TECH_BUNDLE_HINTS) and _contains_any(title, _BUNDLE_HINTS + ("（", "(")):
        return True
    if title.count("/") >= 3 and _contains_any(title, ("机械", "电气", "软件", "开发", "激光", "仿真")):
        return True
    if title.count("、") >= 3 and _contains_any(title, ("开发", "算法", "工程师", "销售")):
        return not _contains_any(title, _TARGET_BUNDLE_HINTS) or _contains_any(
            title, ("Java", "后端", "前端", "算法")
        )
    return False


def _is_stem_medical_major(req_major: str) -> bool:
    """专业明确偏向工科/医学（且未同时写新闻传播类）。"""
    s = (req_major or "").strip()
    if not s:
        return False
    if _contains_any(s, OFFERED_MAJOR_KEYWORDS):
        return False
    if _contains_any(s, STEM_MEDICAL_MAJOR_KEYWORDS):
        return True
    return False


def _major_is_mixed_stem_bundle(req_major: str) -> bool:
    """校招大礼包：新闻传播只是一长串理工专业里的一项。"""
    s = (req_major or "").strip()
    if not s or not _contains_any(s, OFFERED_MAJOR_KEYWORDS):
        return False
    tokens = _tokens(s)
    if len(tokens) < 6:
        return False
    stem_n = sum(1 for t in tokens if _contains_any(t, STEM_MEDICAL_MAJOR_KEYWORDS))
    return stem_n >= 4


def _is_stem_title(title: str) -> bool:
    s = title or ""
    if _contains_any(s, IRRELEVANT_POSITION_KEYWORDS + STEM_TITLE_KEYWORDS):
        return True
    if "工程师" in s or "研发" in s:
        return True
    if _contains_any(s, ("全栈", "算法类", "工程类", "网发", "产研")):
        return True
    return False


def _has_strong_comms(title: str) -> bool:
    return _contains_any(title or "", STRONG_COMMS_KEYWORDS)


def position_relevance(position_name: str) -> Optional[tuple[bool, str]]:
    """岗位名强信号。None 表示不足以单独裁决。"""
    s = (position_name or "").strip()
    if not s:
        return None
    if _contains_any(s, WEAK_FALSE_FRIENDS):
        return False, f"岗位名属于游戏/教务等非目标方向: {s}"
    primary = re.split(r"[（(]", s, 1)[0].strip()
    core = _contains_any(s, CORE_COMMS_KEYWORDS)
    if ("类岗位" in s or s.count("、") >= 2) and not _contains_any(primary, TARGET_POSITION_KEYWORDS):
        return False, f"岗位名为校招大类打包，不够具体: {s}"
    if _is_watery_bundle(s) and not core:
        return False, f"岗位名为校招大类打包，不够具体: {s}"
    if _is_stem_title(s) and not core:
        return False, f"岗位名偏工科/研发/医学技术: {s}"

    relevant = _contains_any(s, TARGET_POSITION_KEYWORDS)
    irrelevant = _contains_any(s, IRRELEVANT_POSITION_KEYWORDS + STEM_TITLE_KEYWORDS)

    if relevant and not irrelevant:
        return True, "岗位名命中宣传/行政/运营/市场/产品或新闻传播岗"
    if irrelevant and not relevant:
        return False, f"岗位名不属于目标方向: {s}"
    if relevant and irrelevant:
        if _has_strong_comms(s) and not _contains_any(
            s, ("算法", "工程师", "研发", "技术传播", "智能驾驶", "计算摄影")
        ):
            return True, "岗位名同时含技术词，但命中新闻传播岗"
        return False, f"岗位名技术属性更强: {s}"
    return None


def major_is_journalism(req_major: str, *, allow_related: bool = True) -> tuple[bool, str]:
    s = (req_major or "").strip()
    if not s:
        return False, "未写专业要求"
    if _contains_any(s, _UNLIMITED_HINTS):
        return False, "专业不限（需再看岗位名）"
    if _contains_any(s, OFFERED_MAJOR_KEYWORDS):
        return True, "命中新闻学院开设专业"
    if allow_related and _contains_any(s, RELATED_MAJOR_KEYWORDS) and not _contains_any(
        s, UNRELATED_MAJOR_KEYWORDS
    ):
        return True, "命中相邻人文社科专业"
    if _contains_any(s, UNRELATED_MAJOR_KEYWORDS):
        return False, f"专业要求不在新闻学院开设范围: {s}"
    tokens = _tokens(s)
    if not tokens:
        return False, "专业字段无法分词"
    return False, f"专业要求不在新闻学院开设范围: {s}"


def major_relevance(req_major: str) -> tuple[bool, str]:
    """兼容旧接口：仅看专业。新逻辑请用 should_keep_job。"""
    hit, reason = major_is_journalism(req_major, allow_related=True)
    if hit:
        return True, reason
    s = (req_major or "").strip()
    if not s or _contains_any(s, _UNLIMITED_HINTS):
        return True, reason
    return False, reason


def should_keep_job(row: dict, *, allow_related: bool = True) -> tuple[bool, str]:
    title = _position_text(row)
    req_major = str(row.get("reqMajor") or "")
    pos_hit = position_relevance(title)
    major_hit, major_reason = major_is_journalism(req_major, allow_related=allow_related)
    stem_major = _is_stem_medical_major(req_major)
    mixed_stem = _major_is_mixed_stem_bundle(req_major)
    core = _contains_any(title, CORE_COMMS_KEYWORDS)
    strong = _has_strong_comms(title)
    soft = _contains_any(title, SOFT_BIZ_KEYWORDS)

    if _is_stem_title(title) and not strong:
        return False, f"岗位名偏工科/研发/医学技术: {title}"

    if ("教师" in title or "老师" in title) and not strong:
        return False, f"教学岗且不是新闻传播类师资: {title}"

    admin = _contains_any(title, ("行政", "文秘", "办公室", "党务"))
    if (stem_major or mixed_stem) and not strong and not admin:
        return False, f"专业偏工科/医学且岗位不是新闻传播岗: {req_major[:40]}"

    if pos_hit is not None:
        if pos_hit[0]:
            if (stem_major or mixed_stem) and not strong and not admin:
                return False, f"专业偏工科/医学且岗位不是新闻传播岗: {req_major[:40]}"
            return True, pos_hit[1]
        return False, pos_hit[1]

    if _is_generic_title(str(row.get("positionName") or "")) and major_hit and not stem_major and not mixed_stem:
        return True, f"岗位名泛化，但{major_reason}"

    if major_hit and not _is_stem_title(title) and not mixed_stem:
        return True, major_reason

    if not title:
        return False, "无岗位名称，无法判断是否为目标方向"

    if soft and not stem_major and not mixed_stem and not _is_stem_title(title):
        return True, "岗位名命中行政/运营/市场/产品"

    return False, f"岗位名未命中宣传/行政/运营/市场/产品或新闻传播: {title}"


def filter_jobs(
    rows: list[dict],
    *,
    allow_related: bool = True,
) -> tuple[list[dict], list[dict]]:
    """返回 (保留, 删除)。删除项带 _filterReason。"""
    kept: list[dict] = []
    dropped: list[dict] = []
    for row in rows:
        keep, reason = should_keep_job(row, allow_related=allow_related)
        if keep:
            kept.append(row)
        else:
            dropped.append({**row, "_filterReason": reason})
    return kept, dropped


def refilter_structured_files(
    csv_path: Optional[str] = None,
    json_path: Optional[str] = None,
    *,
    allow_related: bool = True,
    log_path: Optional[str] = None,
) -> dict[str, Any]:
    """对已结构化 CSV/JSON 再跑一遍学院方向过滤，原地覆盖写回。"""
    import csv
    import json

    from job_structuring import paths
    from job_structuring.engine import POSITION_FIELDNAMES, format_position_row
    from job_structuring.normalize import collect_facets

    csv_path = csv_path or paths.csv_path()
    json_path = json_path or paths.json_path()
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"未找到 CSV: {csv_path}")

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            rows.append(format_position_row(raw))

    kept, dropped = filter_jobs(rows, allow_related=allow_related)
    if log_path:
        log_dropped(dropped, log_path)
    dropped_json = os.path.join(paths.LOGS_DIR, "filtered_out_jobs.json")
    os.makedirs(os.path.dirname(dropped_json) or ".", exist_ok=True)
    with open(dropped_json, "w", encoding="utf-8") as f:
        json.dump(dropped, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(POSITION_FIELDNAMES), extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)

    parent = os.path.dirname(json_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    return {
        "before": len(rows),
        "kept": len(kept),
        "dropped": len(dropped),
        "facets": collect_facets(kept),
    }


def log_dropped(dropped: list[dict], log_path: str) -> None:
    if not dropped:
        return
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for row in dropped:
            company = row.get("companyName") or ""
            position = row.get("positionName") or ""
            major = row.get("reqMajor") or ""
            reason = row.get("_filterReason") or ""
            f.write(f"{company}\t{position}\t{major}\t{reason}\n")
