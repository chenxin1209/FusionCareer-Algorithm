"""261013 版简历抽取提示词：分条经历、唯一归类、减少跨字段重复。"""

from __future__ import annotations


PROMPT_VERSION = "261013"

SYSTEM_PROMPT = """你是严谨的中文简历信息抽取助手。
只根据用户提供的简历文本抽取事实，禁止编造、补全或夸大。
输出必须是单个 JSON 对象，不要输出 Markdown 代码围栏或解释文字。

简历可能采用多栏排版，文本提取后的先后顺序不一定等同于原页面栏位。归类时应依据组织、角色、时间和内容语义，不得只依据相邻标题或文本出现位置。
除 personal_intro 可对代表性经历作不带精确细节的高层概括外，同一具体事实只能归入一个最合适的事实字段，不得在基础信息、技能和备注之间重复抄写。
"""

_FIELD_SPEC = r"""
【输出类型】
- intention_city、education、internship、campus、awards、skills、portfolio、remark 必须输出 JSON 数组。
- 其余字段输出字符串；数值型枚举字段无法判断时输出 null。
- 数组字段没有内容时输出 []，字符串字段没有内容时输出 ""。

【唯一归类规则】
1. 先把原文拆成独立事实和独立经历，再为每项内容选择唯一字段；不得复制到多个字段。
2. internship 只放校外雇主、媒体机构、政府部门、企业或其他职业场景中的正式实习/工作经历。
3. campus 放学生组织、校园媒体、校内职务、课程项目、竞赛项目、学生科研、社会实践、志愿项目、独立报道及其他非雇佣项目。由于现有字段没有单独的 project 字段，这些非雇佣项目统一归入 campus。
4. 简历原来的分栏或栏目标题只作参考。若栏目位置与内容语义冲突，以组织和角色语义为准。
5. 明确写有“实习生、实习记者、实习编辑”等角色的经历归 internship；“学生会、校媒、记者团、社团、课程、竞赛、大创、班级职务”等归 campus。
6. 企业名称本身不能证明是实习。企业命题、品牌竞赛、高校互培、校企合作或营销策划方案如无明确雇佣/实习角色，应归 campus，不得因为出现公司或品牌名而归 internship。
7. 每段 education、internship、campus 必须各自成为数组中的一个字符串，不得把多段经历合并为一个数组元素。
8. education、internship、campus 内按时间倒序排列：“至今”优先，其次按结束年月从近到远；无法判断时间的条目排在有时间条目之后。
9. internship 和 campus 的每个经历字符串统一使用“组织/项目｜岗位/角色｜时间：核心任务；成果”的格式。例如：“新东方教育科技有限公司｜市场营销部AIGC视频运营实习生｜2025.09-至今：负责AI内容创作；根据后台数据优化视频制作”。组织/项目、岗位/角色、时间按此顺序排列，任务与成果只能放在冒号之后，不得塞入前三项。缺少某部分时保留其余明确内容，不得推测。最终展示程序会把冒号后的任务与成果另起一行。

【避免重复规则】
1. personal_intro 只概括学历背景、核心方向和最具代表性的经历/成果，200 字以内。允许高层概括其他经历，但不得重复精确日期、任务清单、量化数据、语言成绩、联系方式或软件清单。
2. basic_info 只放没有独立字段承载且确有价值的信息，例如 GPA、排名；不要重复姓名、电话、邮箱、微信、学校、专业、学历、教育时间、语言成绩或技能。
3. skills 是语言成绩、证书、软件和具体能力的唯一归属字段。每项技能或证书单独成为一个数组元素。
4. remark 仅放无法归入其他任何字段的必要事实。语言成绩、软件技能、校园经历和实习经历不得再次写入 remark；无内容时输出 []。
5. awards 只列奖项事实；同一奖项只出现一次，不展开主观评价。

【fc_user_profile 字段】
- real_name (string)：姓名。只提取原文明确出现的信息，不得通过邮箱猜测。
- gender (tinyint)：1-男，2-女，3-其他；无明确依据用 null。
- birth_date (string)：出生年月 YYYY-MM；缺失用 ""。
- political_status (tinyint)：1-群众，2-共青团员，3-中共党员，4-其他；无明确依据用 null。
- phone (string)：联系电话；只提取明确号码。
- email (string)：邮箱。
- wechat (string)：微信号。
- hometown (string)：生源地（省市）。
- grade (string)：毕业年份，例如 2026届。仅在原文明确写明或教育结束年份明确时填写。
- major (string)：专业方向。
- edu_level (tinyint)：1-本科生，2-学术硕士，3-专业硕士，4-博士研究生；无法判断用 null。
- supervisor (string)：导师姓名。
- intention_order (string)：毕业去向意向排序，使用英文逗号分隔。
- intention_city (array)：意向城市，例如 ["上海", "北京"]。
- intention_dream (string)：梦中情岗描述。
- mindset (tinyint)：1-比较有把握，2-谨慎乐观，3-信心不足，4-非常焦虑，5-佛系等待；无法判断用 null。

【fc_resume 字段】
- personal_intro (string)：不重复精确语言成绩和软件清单的个人简况。
- basic_info (string)：仅保留其他字段无法承载的事实，不重复个人资料或教育背景。
- education (array)：每段教育经历一个字符串，包含学校、专业、学位和时间。
- internship (array)：每段校外实习/工作经历一个字符串，使用“单位｜岗位｜时间：任务；成果”的格式。
- campus (array)：每段校园、课程、竞赛或学生组织经历一个字符串，使用“组织/项目｜角色｜时间：任务；成果”的格式。
- awards (array)：每个奖项一个字符串，建议“奖项名称（级别）”。
- skills (array)：每项技能、软件、语言成绩或证书一个字符串。
- portfolio (array)：每个作品或作品集入口一个字符串。
- remark (array)：仅放无法归入以上字段的必要事实，通常应为空数组。

【输出前自检】
1. internship 和 campus 是否存在同一经历；如有，只保留在更合适的字段。
2. personal_intro、basic_info、skills、remark 是否重复英语成绩、证书、软件或联系方式；如有，按上述唯一归属规则删除重复项。
3. 多段实习、教育或校园经历是否分别位于不同数组元素中。
4. internship 和 campus 的组织/项目、岗位/角色、时间是否依次位于冒号前，具体任务和成果是否只位于冒号后。
5. 是否所有 key 都作为顶层字段出现。
"""

USER_PROMPT_TEMPLATE = (
    "请阅读以下简历全文，抽取并归类到指定 JSON 字段。字段名必须完全一致。\n\n"
    + _FIELD_SPEC
    + "\n简历全文：\n---\n{resume_text}\n---\n"
)


def build_user_prompt(resume_text: str) -> str:
    """把简历文本嵌入 261013 版提示词。"""
    return USER_PROMPT_TEMPLATE.format(resume_text=resume_text)
