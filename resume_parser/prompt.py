"""
提示词：要求 DeepSeek 严格输出 JSON，字段与 fc_user_profile / fc_resume 对齐。
"""

SYSTEM_PROMPT = """你是严谨的简历信息抽取助手。只根据用户提供的简历纯文本作答，禁止编造。
输出必须是单个 JSON 对象（不要 Markdown 代码围栏、不要前后说明文字）。
字符串字段缺失用 ""；数值型枚举字段缺失用 null（JSON null）；intention_city 无信息用 []。
不要猜测文本中未出现的电话、邮箱等信息。
"""

USER_PROMPT_TEMPLATE = """请阅读以下简历全文，抽取并归类到下列 JSON 字段。字段名必须完全一致。

【fc_user_profile】
- real_name (string)：姓名
- gender (tinyint)：1-男 2-女 3-其他，无法判断用 null
- birth_date (string)：出生年月 YYYY-MM，缺失用 ""
- political_status (tinyint)：1-群众 2-共青团员 3-中共党员 4-其他，无法判断用 null
- phone (string)：联系电话
- email (string)：邮箱
- wechat (string)：微信号
- hometown (string)：生源地（省市）
- grade (string)：年级，如 2022级
- major (string)：专业方向
- edu_level (tinyint)：1-本科生 2-学术硕士 3-专业硕士 4-博士研究生，无法判断用 null
- supervisor (string)：导师姓名
- intention_order (string)：毕业去向意向排序，如「学术教职,企业公司」
- intention_city (array)：意向城市，如 ["上海","北京"]，无则 []
- intention_dream (string)：梦中情岗描述
- mindset (tinyint)：1-比较有把握 2-谨慎乐观 3-信心不足 4-非常焦虑 5-佛系等待，无法判断用 null

【fc_resume — 长文本，简洁提取事实；personal_intro 尽量控制在 300 字以内】
- personal_intro：个人简况/自我评价
- basic_info：基础信息汇总（含未单独列出的字段）
- education：教育背景（按时间线）
- internship：实习经历
- campus：在校经历
- awards：荣誉奖励
- skills：掌握技能（多项用分号分隔）
- portfolio：作品集
- remark：其他备注（语言、证书等）

硬性要求：
1. 提取姓名时，优先从明确「姓名」标签、简历开头大字、邮箱前缀推断，有线索则不可留空。
2. 性别、政治面貌、学历层次等枚举：根据典型词语转数字（如「男」→1，「中共党员」→3，「本科生」→1）；无法判断用 null，不要编造。
3. 所有日期统一为 YYYY-MM 格式。
4. 长文本字段简洁提取，删语气词与重复，保留要点，不要有内容的遗漏。
5. 只返回一个 JSON 对象，所有上述 key 必须作为**顶层字段**平铺出现（不要嵌套在 fc_user_profile、fc_resume 等子对象里），不要 Markdown 标记或解释文字。

简历全文：
---
{resume_text}
---
"""


def build_user_prompt(resume_text: str) -> str:
    """将简历文本嵌入用户提示模板。"""
    return USER_PROMPT_TEMPLATE.format(resume_text=resume_text)
