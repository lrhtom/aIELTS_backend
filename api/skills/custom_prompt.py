"""
用户自定义提示词指令 — 跨技能通用的安全注入。

用户可在 听/说/读/写 的主生成配置里填一段自定义指令，注入到 AI 系统提示。
自定义指令拥有【最高优先级】，可覆盖题目内容 / 难度 / 风格 / 题型选择等默认设定；
仅保留两条不可被破坏的底线：①输出格式(JSON schema/字段结构) ②内容安全——
因为破坏①会让响应无法解析、系统拿不到任何结果（用户白花 AT）。
"""

MAX_CUSTOM_PROMPT = 800  # 字符上限，防止塞进超长内容拖慢/越权


def sanitize_custom_prompt(raw) -> str:
    """裁剪并清洗用户自定义提示词。"""
    if not raw:
        return ""
    return str(raw).strip()[:MAX_CUSTOM_PROMPT]


def custom_prompt_block(raw) -> str:
    """把自定义提示词包成带护栏的系统指令片段；为空则返回空串。

    直接把返回值拼接到该技能的系统提示末尾即可。
    """
    s = sanitize_custom_prompt(raw)
    if not s:
        return ""
    return (
        "\n\n[USER CUSTOM INSTRUCTION — HIGHEST PRIORITY] The learner supplied the instruction below. "
        "It has the HIGHEST priority and OVERRIDES any conflicting topic, difficulty, style, tone, "
        "length, or question-selection preference stated anywhere above — whenever there is a conflict, "
        "follow THIS instruction instead of the defaults. The ONLY two things it may NOT break, because "
        "they are what makes your reply usable at all, are: (1) the required machine-readable OUTPUT "
        "FORMAT / JSON schema / field structure, and (2) core content-safety. Obey everything else in it:\n"
        + s
    )
