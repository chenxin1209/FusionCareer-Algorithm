"""
与后端 fusioncareer-api 枚举 / JobPostRequest 对齐的单一来源。

以 Java 枚举常量为准（Jackson 默认按枚举名反序列化）。
docs/API_README.md 中 BACHELOR / DOCTORATE / BOTH 为过期写法，这里映射到
UNDERGRADUATE / DOCTORAL / HYBRID。
"""

from __future__ import annotations

# 与 JobPostRequest 对齐的 camelCase 列 + 溯源（不含 id/createdBy 等仅后端字段）
POSITION_FIELDNAMES = (
    "sourceType",
    "sourceUrl",
    "companyName",
    "department",
    "positionName",
    "jobCategory",
    "jobSubCategory",
    "recruitType",
    "headcount",
    "workStartDate",
    "workEndDate",
    "workDaysPerWeek",
    "workDurationType",
    "workPeriodType",
    "workMode",
    "workCity",
    "workProvince",
    "workLocation",
    "salaryMin",
    "salaryMax",
    "salaryDisplay",
    "jobDesc",
    "reqEduLevel",
    "reqMajor",
    "reqGradYear",
    "reqSkills",
    "reqOther",
    "status",
    "source_md",
)

JOB_POST_API_FIELDS = tuple(f for f in POSITION_FIELDNAMES if f != "source_md")

XLSX_HEADER_LABELS = (
    "来源类型",
    "来源链接",
    "单位名称",
    "部门",
    "岗位名称",
    "岗位大类",
    "岗位二级分类",
    "招聘类型",
    "招聘人数",
    "工作开始日",
    "工作结束日",
    "每周工作天数",
    "每周工作天数类型",
    "实习总时长类型",
    "工作形式",
    "工作城市",
    "工作省份",
    "工作地点原文",
    "薪资下限",
    "薪资上限",
    "薪资展示",
    "岗位描述",
    "学历要求",
    "专业要求",
    "届别要求",
    "技能要求",
    "其他要求/投递说明",
    "岗位状态",
    "来源 Markdown",
)

ZH_TO_CAMEL = {
    "来源类型": "sourceType",
    "来源链接": "sourceUrl",
    "单位名称": "companyName",
    "部门": "department",
    "岗位名称": "positionName",
    "岗位大类": "jobCategory",
    "岗位二级分类": "jobSubCategory",
    "招聘类型": "recruitType",
    "招聘人数": "headcount",
    "工作开始日": "workStartDate",
    "工作结束日": "workEndDate",
    "每周工作天数": "workDaysPerWeek",
    "每周工作天数类型": "workDurationType",
    "实习总时长类型": "workPeriodType",
    "工作形式": "workMode",
    "工作城市": "workCity",
    "工作省份": "workProvince",
    "工作地点原文": "workLocation",
    "薪资下限": "salaryMin",
    "薪资上限": "salaryMax",
    "薪资展示": "salaryDisplay",
    "岗位描述": "jobDesc",
    "学历要求": "reqEduLevel",
    "专业要求": "reqMajor",
    "届别要求": "reqGradYear",
    "技能要求": "reqSkills",
    "其他要求与投递说明": "reqOther",
    "岗位状态": "status",
}

ZH_JOB_CATEGORY = {
    "学术教职": "ACADEMIC",
    "党政机关": "GOVERNMENT",
    "新闻媒体": "MEDIA",
    "企业公司": "ENTERPRISE",
    "企业": "ENTERPRISE",
    "其他": "OTHER",
    " 其他": "OTHER",
    "国际组织": "GOVERNMENT",
    "事业单位": "GOVERNMENT",
}

ZH_JOB_SUB_CATEGORY = {
    "升学深造": "FURTHER_STUDY",
    "考取教职": "TEACHING_POSITION",
    "中学教师": "MIDDLE_SCHOOL_TEACHER",
    "选调生": "SELECTED_GRADUATE",
    "公务员": "CIVIL_SERVANT",
    "高校行政": "UNIVERSITY_ADMIN",
    "医院": "HOSPITAL",
    "银行": "BANK",
    "其他事业单位": "OTHER_PUBLIC_INSTITUTION",
    "党报央媒": "CENTRAL_MEDIA",
    "地区主流媒体": "REGIONAL_MEDIA",
    "其他媒体机构": "OTHER_MEDIA",
    "自媒体": "SELF_MEDIA",
    "国央企": "STATE_OWNED",
    "民企": "PRIVATE_ENTERPRISE",
    "外企": "FOREIGN_ENTERPRISE",
    "其他": "OTHER",
    "国际组织": "OTHER_PUBLIC_INSTITUTION",
    "国际机构": "OTHER_PUBLIC_INSTITUTION",
    "联合国": "OTHER_PUBLIC_INSTITUTION",
    "联合国系统": "OTHER_PUBLIC_INSTITUTION",
    "研究院": "OTHER_PUBLIC_INSTITUTION",
    "科研院所": "OTHER_PUBLIC_INSTITUTION",
    "实验室": "OTHER_PUBLIC_INSTITUTION",
    "民营企业": "PRIVATE_ENTERPRISE",
    "私营企业": "PRIVATE_ENTERPRISE",
    "外资企业": "FOREIGN_ENTERPRISE",
    "国有企业": "STATE_OWNED",
    "央企": "STATE_OWNED",
}

ZH_RECRUIT_TYPE = {
    "大实习": "BIG_INTERNSHIP",
    "小实习": "SMALL_INTERNSHIP",
    "日常实习": "DAILY_INTERNSHIP",
    "应届生招聘": "CAMPUS_RECRUITMENT",
    "应届生摸排": "CAMPUS_SCREENING",
    "其他": "OTHER",
    "校园招聘": "CAMPUS_RECRUITMENT",
    "校招": "CAMPUS_RECRUITMENT",
    "秋招": "CAMPUS_RECRUITMENT",
    "春招": "CAMPUS_RECRUITMENT",
    "提前批": "CAMPUS_RECRUITMENT",
    "实习生": "DAILY_INTERNSHIP",
    "实习": "DAILY_INTERNSHIP",
    "摸排": "CAMPUS_SCREENING",
}

ZH_WORK_DURATION = {
    "一周1-2天": "ONE_TO_TWO_DAYS",
    "一周3-4天": "THREE_TO_FOUR_DAYS",
    "一周5天": "FIVE_DAYS",
}

ZH_WORK_PERIOD = {
    "3个月以内": "LESS_THAN_THREE_MONTHS",
    "3-6个月": "THREE_TO_SIX_MONTHS",
    "6个月以上": "MORE_THAN_SIX_MONTHS",
}

ZH_WORK_MODE = {
    "线上": "ONLINE",
    "线下": "OFFLINE",
    "线上线下均可": "HYBRID",
}

ZH_EDU_LEVEL = {
    "本科生": "UNDERGRADUATE",
    "本科": "UNDERGRADUATE",
    "学术硕士研究生": "ACADEMIC_MASTER",
    "专业硕士研究生": "PROFESSIONAL_MASTER",
    "硕士研究生": "ACADEMIC_MASTER",
    "硕士": "ACADEMIC_MASTER",
    "博士研究生": "DOCTORAL",
    "博士": "DOCTORAL",
}

ZH_JOB_STATUS = {
    "已下线": "OFFLINE",
    "发布中": "PUBLISHED",
    "已截止": "EXPIRED",
}

ZH_SOURCE_TYPE = {
    "平台发布": "PLATFORM",
    "就业资讯源爬取": "CRAWL",
}

# 过期文档 / 模型误输出的英文别名 → Java 枚举名
EN_ALIASES = {
    "reqEduLevel": {
        "BACHELOR": "UNDERGRADUATE",
        "UNDERGRAD": "UNDERGRADUATE",
        "DOCTORATE": "DOCTORAL",
        "PHD": "DOCTORAL",
    },
    "workMode": {
        "BOTH": "HYBRID",
    },
}

VALID_ENUM_VALUES: dict[str, set[str]] = {
    "sourceType": {"PLATFORM", "CRAWL"},
    "jobCategory": {
        "ACADEMIC",
        "GOVERNMENT",
        "MEDIA",
        "ENTERPRISE",
        "OTHER",
    },
    "jobSubCategory": {
        "FURTHER_STUDY",
        "TEACHING_POSITION",
        "MIDDLE_SCHOOL_TEACHER",
        "SELECTED_GRADUATE",
        "CIVIL_SERVANT",
        "UNIVERSITY_ADMIN",
        "HOSPITAL",
        "BANK",
        "OTHER_PUBLIC_INSTITUTION",
        "CENTRAL_MEDIA",
        "REGIONAL_MEDIA",
        "OTHER_MEDIA",
        "SELF_MEDIA",
        "STATE_OWNED",
        "PRIVATE_ENTERPRISE",
        "FOREIGN_ENTERPRISE",
        "OTHER",
    },
    "recruitType": {
        "BIG_INTERNSHIP",
        "SMALL_INTERNSHIP",
        "DAILY_INTERNSHIP",
        "CAMPUS_RECRUITMENT",
        "CAMPUS_SCREENING",
        "OTHER",
    },
    "workDurationType": {"ONE_TO_TWO_DAYS", "THREE_TO_FOUR_DAYS", "FIVE_DAYS"},
    "workPeriodType": {
        "LESS_THAN_THREE_MONTHS",
        "THREE_TO_SIX_MONTHS",
        "MORE_THAN_SIX_MONTHS",
    },
    "workMode": {"ONLINE", "OFFLINE", "HYBRID"},
    "reqEduLevel": {
        "UNDERGRADUATE",
        "ACADEMIC_MASTER",
        "PROFESSIONAL_MASTER",
        "DOCTORAL",
    },
    "status": {"OFFLINE", "PUBLISHED", "EXPIRED"},
}

JOB_SUB_TO_PARENT = {
    "FURTHER_STUDY": "ACADEMIC",
    "TEACHING_POSITION": "ACADEMIC",
    "MIDDLE_SCHOOL_TEACHER": "ACADEMIC",
    "SELECTED_GRADUATE": "GOVERNMENT",
    "CIVIL_SERVANT": "GOVERNMENT",
    "UNIVERSITY_ADMIN": "GOVERNMENT",
    "HOSPITAL": "GOVERNMENT",
    "BANK": "GOVERNMENT",
    "OTHER_PUBLIC_INSTITUTION": "GOVERNMENT",
    "CENTRAL_MEDIA": "MEDIA",
    "REGIONAL_MEDIA": "MEDIA",
    "OTHER_MEDIA": "MEDIA",
    "SELF_MEDIA": "MEDIA",
    "STATE_OWNED": "ENTERPRISE",
    "PRIVATE_ENTERPRISE": "ENTERPRISE",
    "FOREIGN_ENTERPRISE": "ENTERPRISE",
    "OTHER": "OTHER",
}

ZH_ENUM_MAPS = {
    "sourceType": ZH_SOURCE_TYPE,
    "jobCategory": ZH_JOB_CATEGORY,
    "jobSubCategory": ZH_JOB_SUB_CATEGORY,
    "recruitType": ZH_RECRUIT_TYPE,
    "workDurationType": ZH_WORK_DURATION,
    "workPeriodType": ZH_WORK_PERIOD,
    "workMode": ZH_WORK_MODE,
    "reqEduLevel": ZH_EDU_LEVEL,
    "status": ZH_JOB_STATUS,
}

ENUM_FIELDS = frozenset(VALID_ENUM_VALUES.keys())
INT_FIELDS = frozenset({"headcount", "workDaysPerWeek", "salaryMin", "salaryMax"})
DATE_FIELDS = frozenset({"workStartDate", "workEndDate"})
