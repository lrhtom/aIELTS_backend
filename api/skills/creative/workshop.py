"""
Creative Workshop Skills — 创意工坊 AI 技能
"""


def skill_creative_generate(method_prompt: str, preferred_title: str) -> str:
    """创意工坊页面生成 — 用户消息"""
    title_instruction = (
        f'Use this page title if appropriate: "{preferred_title}".' if preferred_title else
        'Create a concise and clear page title for this learning method.'
    )
    return (
        'You are an elite education product designer and front-end engineer.\n'
        'Generate a complete, standalone HTML learning page that helps a student practice based on their custom method.\n'
        'Output ONLY raw HTML, no markdown fences and no extra explanation.\n\n'
        'Hard requirements:\n'
        '1) Return a full HTML document with <!doctype html>, <html>, <head>, <body>.\n'
        '2) Include inline CSS and JavaScript in the same file (no external CDN or external assets).\n'
        '3) The page must be responsive for mobile and desktop.\n'
        '4) The page should be practical for studying: include clear sections, one interactive exercise area, and progress feedback.\n'
        '5) Keep wording in Chinese by default unless the method explicitly asks another language.\n'
        '6) Avoid offensive or unsafe content.\n'
        f'7) {title_instruction}\n\n'
        'User custom learning method:\n'
        f'{method_prompt}'
    )


def skill_creative_edit(instruction: str, existing_html: str) -> str:
    """创意工坊页面编辑 — 用户消息"""
    return (
        'You are an elite education product designer and front-end engineer.\n'
        'The user wants to modify an existing HTML document based on an instruction.\n'
        'Output ONLY the fully complete, modified raw HTML document. No markdown fences, no extra explanation.\n'
        'Ensure the document remains a standalone HTML file with inline CSS and JS.\n'
        f'User Instruction: {instruction}\n\n'
        '--- Existing HTML below ---\n'
        f'{existing_html}'
    )
