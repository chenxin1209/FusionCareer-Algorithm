"""
提示词：要求 DeepSeek 严格输出 JSON，字段与 fc_user_profile / fc_resume 对齐。
"""

SYSTEM_PROMPT = """你是严谨的简历信息抽取助手。只根据用户提供的简历纯文本作答，禁止编造。
输出必须是单个 JSON 对象（不要 Markdown 代码围栏、不要前后说明文字）。
字符串字段缺失用 ""；数值型枚举字段缺失用 null（JSON null）；intention_city 无信息用 []。
不要猜测文本中未出现的电话、邮箱等信息。
"""

_FIELD_SPEC = """
【核心抽取规则（嵌入你的硬性要求）】
1. 提取姓名时，优先从明确「姓名」标签、简历开头大字、邮箱前缀推断，有线索则不可留空。
2. 性别、政治面貌、学历层次等枚举：根据典型词语转数字（如「男」→1，「中共党员」→3，「本科生」→1）；无法判断用 null。
3. 所有日期统一为 YYYY-MM 格式。
4. 长文本字段（如 internship, awards）必须极其简洁：去掉所有形容性、自我评价性的虚词（如“性格外向”“善于沟通”等主观描述全部删除）；每条经历最多包含：角色/公司，核心任务，量化成果（如果有）；荣誉奖项格式为“奖项名称（级别）”，用分号分隔，不展开描述。

--- fc_user_profile 字段 ---
- real_name (string)：姓名
- gender (tinyint)：1-男 2-女 3-其他，无法判断用 null
- birth_date (string)：出生年月 YYYY-MM，缺失用 ""
- political_status (tinyint)：1-群众 2-共青团员 3-中共党员 4-其他，无法判断用 null
- phone (string)：联系电话（只提取明确数字，不编造）
- email (string)：邮箱
- wechat (string)：微信号
- hometown (string)：生源地（省市）
- grade (string)：毕业年份，如 2026届（若未写明，则硕士生入学年份+3，博士生+4，否则留空）
- major (string)：专业方向
- edu_level (tinyint)：1-本科生 2-学术硕士 3-专业硕士 4-博士研究生，无法判断用 null
- supervisor (string)：导师姓名
- intention_order (string)：毕业去向意向排序，如「学术教职,企业公司」（用英文逗号分隔）
- intention_city (array)：意向城市，如 ["上海","北京"]，无则 []
- intention_dream (string)："梦中情岗"描述
- mindset (tinyint)：1-比较有把握 2-谨慎乐观 3-信心不足 4-非常焦虑 5-佛系等待，无法判断用 null

--- fc_resume 长文本字段（简洁提取事实，严格遵守上述第4条风格规则） ---
- personal_intro (string)：个人简况（仅概括学历背景、核心技能和成就，300字以内）
- basic_info (string)：基础信息汇总（含未单独列出的字段）
- education (string)：教育背景（学校、专业、学位、时间，不含课程列表）
- internship (string)：实习经历（公司/岗位/核心任务/量化成果）
- campus (string)：在校经历（角色/组织/项目成果）
- awards (string)：荣誉奖励（格式：奖项名(级别)，分号分隔，不展开）
- skills (string)：掌握技能（分号分隔，只写具体技能或证书名称）
- portfolio (string)：作品集（链接或简述）
- remark (string)：备注（语言、证书等补充信息）

硬性输出约束：
- 只返回一个 JSON 对象，所有上述 key 必须作为**顶层字段**平铺出现（不要嵌套在 fc_user_profile、fc_resume 等子对象里）。
- 不要 Markdown 标记或解释文字。
"""

USER_PROMPT_TEMPLATE = (
    """请阅读以下简历全文，抽取并归类到下列 JSON 字段。字段名必须完全一致。

"""
    + _FIELD_SPEC
    + """
简历全文：
---
{resume_text}
---
"""
)


def build_user_prompt(resume_text: str) -> str:
    """将简历文本嵌入用户提示模板。"""
    return USER_PROMPT_TEMPLATE.format(resume_text=resume_text)