"""
Assistant Skills — 智能助手 AI 技能（个人 Agent、ReAct 浏览器 Agent、DOM 上下文）
"""

MAX_SYSTEM_PROMPT_CHARS = 3000


def skill_assistant_system_prompt(custom_prompt: object, profile: object) -> str:
    """构建个人 Agent 的系统指令"""
    if isinstance(custom_prompt, str) and custom_prompt.strip():
        return custom_prompt.strip()[:MAX_SYSTEM_PROMPT_CHARS]

    profile_dict = profile if isinstance(profile, dict) else {}
    name = str(profile_dict.get('name', '')).strip() or 'Personal AI Agent'
    role = str(profile_dict.get('role', '')).strip() or 'You are a reliable and patient study coach.'
    goal = str(profile_dict.get('goal', '')).strip() or 'Help the user solve tasks with clear and practical steps.'
    style = str(profile_dict.get('style', '')).strip() or 'Answer in concise Chinese. Give conclusion first, then actions.'

    return (
        f"You are {name}.\n\n"
        f"Role:\n{role}\n\n"
        f"Goal:\n{goal}\n\n"
        f"Response style:\n{style}\n\n"
        "Rules:\n"
        "1) Always provide actionable guidance.\n"
        "2) If user context is insufficient, ask only the minimum questions.\n"
        "3) Use Markdown for readability.\n"
        "4) Keep harmful, illegal, or unsafe requests declined."
    )[:MAX_SYSTEM_PROMPT_CHARS]


def skill_assistant_react_browser_system_prompt(
    base_url: str,
    max_steps: int,
    has_dom_context: bool = False,
    ui_lang: str = 'zh',
) -> str:
    """构建 ReAct 浏览器 Agent 的系统指令"""
    final_action_example = (
        '{"action":"final","final_answer":"Provide a concise English answer based on observations."}\n\n'
        if ui_lang == 'en'
        else '{"action":"final","final_answer":"综合所有观察结果，给出对用户的中文回复"}\n\n'
    )

    final_lang_rule = (
        '5) final_answer must be in English and formatted as clear Markdown.\n'
        if ui_lang == 'en'
        else '5) final_answer 须使用中文，格式化为清晰的 Markdown。\n'
    )

    prompt = (
        '你是一个强大的 AI Agent 助手。你必须严格输出 JSON 对象，绝不要输出 Markdown 或纯文本。\n'
        f'最多执行步骤: {max_steps}\n\n'
        '你拥有以下工具，每次必须输出其中一个 JSON 动作：\n\n'
        '== 文件浏览工具 ==\n'
        '{"action":"list_frontend_dir","path":"src/components","reason":"查看前端代码结构"}\n'
        '{"action":"read_frontend_file","path":"src/App.tsx","reason":"读取代码内容以分析"}\n\n'
        '== 用户数据查询工具 ==\n'
        '{"action":"query_user_stats","reason":"获取当前用户的综合学习统计"}\n'
        '  → 返回: 学习计划数、笔记本数、词书进度、AT币余额、注册时间等\n'
        '{"action":"query_vocab_plans","reason":"查看用户的学习计划详情"}\n'
        '  → 返回: 所有学习计划名称、每日学词数、掌握目标等\n'
        '{"action":"query_notebooks","reason":"查看用户的笔记本列表"}\n'
        '  → 返回: 笔记本名称和每本包含的词条数量\n'
        '{"action":"search_words","keyword":"abandon","reason":"在用户词库中搜索某个词"}\n'
        '  → 返回: 匹配到的单词及其释义、所在笔记本\n\n'
        '== 终止动作 ==\n'
        + final_action_example
        + '规则：\n'
        '1) list_frontend_dir / read_frontend_file 的 path 必须是相对于 frontend 根目录的路径。\n'
        '2) 仔细阅读并理解观察结果后再做出判断，不要盲目猜测。\n'
        '3) 分析完成后或可以直接答复用户时，必须输出 action=final 并附带 final_answer。\n'
        '4) 尽量在最少步骤内完成任务。如果一次工具调用就能获取足够信息，不要重复调用。\n'
        + final_lang_rule
    )

    if has_dom_context:
        prompt += '6) 如果请求提供了"当前页面 DOM 摘要"，且信息足够，你可以直接输出 action=final，无需调用工具。\n'

    return prompt


def skill_assistant_dom_context_prompt(dom_context: dict | None, ui_lang: str = 'zh') -> str:
    """构建当前页面 DOM 上下文摘要"""
    if not dom_context:
        return ''

    lines = [
        '【System Add-on: Current page DOM summary (captured in frontend runtime, sanitized)】'
        if ui_lang == 'en'
        else '【系统附加：当前页面 DOM 摘要（由前端实时采集，已脱敏）】'
    ]

    if dom_context.get('url'):
        lines.append(f"URL: {dom_context['url']}")
    if dom_context.get('path'):
        lines.append(f"Path: {dom_context['path']}")
    if dom_context.get('title'):
        lines.append(f"Title: {dom_context['title']}")

    viewport = dom_context.get('viewport')
    if isinstance(viewport, dict) and viewport:
        w = viewport.get('width')
        h = viewport.get('height')
        if w and h:
            lines.append(f'Viewport: {w}x{h}')

    if dom_context.get('active_selector'):
        lines.append(
            f"Active element: {dom_context['active_selector']}"
            if ui_lang == 'en'
            else f"当前焦点元素: {dom_context['active_selector']}"
        )

    elements = dom_context.get('elements', [])
    if isinstance(elements, list) and elements:
        lines.append('Visible key elements (excerpt):' if ui_lang == 'en' else '可见关键元素（节选）:')
        for idx, element in enumerate(elements[:60], start=1):
            if not isinstance(element, dict):
                continue

            parts: list[str] = [f"{idx}. <{element.get('tag', 'div')}>"]
            selector = str(element.get('selector', '')).strip()
            if selector:
                parts.append(f'selector={selector}')

            role = str(element.get('role', '')).strip()
            if role:
                parts.append(f'role={role}')

            text = str(element.get('text', '')).strip()
            if text:
                parts.append(f'text={text}')

            attrs = element.get('attrs', {})
            if isinstance(attrs, dict) and attrs:
                attr_pairs = []
                for k, v in list(attrs.items())[:4]:
                    key = str(k).strip()
                    value = str(v).strip()
                    if key and value:
                        attr_pairs.append(f'{key}={value}')
                if attr_pairs:
                    parts.append('attrs[' + ', '.join(attr_pairs) + ']')

            lines.append(' | '.join(parts))

    lines.append(
        'Note: this summary is only for understanding current page structure, not backend database facts.'
        if ui_lang == 'en'
        else '说明：该摘要仅用于理解当前页面结构，不代表后端数据库事实。'
    )
    return '\n'.join(lines)[:3600]
