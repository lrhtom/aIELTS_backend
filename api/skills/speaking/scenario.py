"""
Speaking Scenario Skills — 口语场景角色扮演相关 AI 技能
"""

# ── 场景干扰选项 (真实难度增强) ──────────────────────────────────────────────
# 每个可选项注入一段行为指令，让 AI 角色模拟真实英语环境里的听说压力。
# 由前端"选择性开启"，每个选项还可多选"子选项"细化。传入形如
#   {'accent': ['brummie','scouse'], 'noise': ['pub','office'], 'smalltalk': []}
# 也兼容旧的列表形式 ['accent','noise'](等价于每项无子选项)。
INTERFERENCE_KEYS = ('accent', 'crosstalk', 'noise', 'audioquality', 'smalltalk')

# 每个干扰项的合法子选项（键须与前端 SCENARIO_SUBOPTIONS 一致）
INTERFERENCE_SUBOPTIONS = {
    'accent': ('brummie', 'eastmidlands', 'scouse', 'geordie', 'cockney'),
    'crosstalk': ('fast', 'interrupt', 'overlap'),
    'noise': ('pub', 'canteen', 'office', 'street'),
    'audioquality': ('phone', 'muffled', 'radio'),  # 音质干扰：前端对 TTS 语音加滤波
    'smalltalk': (),  # 仅开关，无子选项
}

# 子选项 → 注入 AI 提示里的英文描述
_SUB_LABELS = {
    'accent': {
        'brummie': "Birmingham 'Brummie'",
        'eastmidlands': "East Midlands / Nottingham",
        'scouse': "Liverpool 'Scouse'",
        'geordie': "Newcastle 'Geordie'",
        'cockney': "London 'Cockney'",
    },
    'crosstalk': {
        'fast': "talk noticeably fast",
        'interrupt': "interrupt and talk over the learner",
        'overlap': "use overlapping back-channels ('yeah yeah', 'mm-hm') while they speak",
    },
    'noise': {
        'pub': "a busy pub",
        'canteen': "a clattering canteen",
        'office': "an open-plan office",
        'street': "a noisy street",
    },
    'audioquality': {
        'phone': "a narrow, tinny telephone line",
        'muffled': "a muffled, low-fidelity channel (as if through a wall)",
        'radio': "a crackly two-way radio",
    },
    'smalltalk': {},  # 仅开关，无子选项
}

# 每个干扰项的基础行为指令（子选项在其后补充"Specifically: …"）
_BASE_FRAGMENTS = {
    'accent': (
        "ACCENT: Play a working-class British local with a strong REGIONAL accent (NOT BBC Received "
        "Pronunciation). Drop in regional dialect words and colloquialisms ('ta', 'ay up', 'innit', "
        "'gonna', 'proper' = very), conveying the accent through spelling and word choice while staying "
        "ultimately understandable"
    ),
    'crosstalk': (
        "PACE & INTERRUPTIONS: Speak at a fast native pace with contractions and fillers "
        "('erm', 'like', 'you know')"
    ),
    'noise': (
        "BACKGROUND NOISE: There is loud background noise; occasionally mishear the learner or ask them "
        "to repeat ('it's dead loud in here — say that again?') and reference the noise naturally"
    ),
    'audioquality': (
        "AUDIO QUALITY: The learner hears you through a degraded audio channel; enunciate clearly and be "
        "understanding if they mishear or ask you to repeat"
    ),
    'smalltalk': (
        "SMALL TALK: Weave in natural British small talk and expect the learner to reciprocate; if they "
        "are too abrupt, react as a real person would (mild surprise) but stay friendly"
    ),
}


def normalize_modifiers(modifiers):
    """把前端传来的干扰项（dict 或旧 list）归一化成 {option: [valid subs]}。

    - dict: {'accent': ['brummie', ...], ...}
    - list: ['accent', ...] → 每项子选项为空
    只保留白名单内的 option 和 sub，去重且保序（稳定 singleflight/缓存键）。
    """
    if isinstance(modifiers, dict):
        items = list(modifiers.items())
    elif isinstance(modifiers, (list, tuple)):
        items = [(k, []) for k in modifiers]
    else:
        return {}

    out = {}
    for opt in INTERFERENCE_KEYS:  # 固定顺序
        # 找出该 option 对应的原始子选项
        raw_subs = None
        for k, v in items:
            if k == opt:
                raw_subs = v
                break
        if raw_subs is None:
            continue
        allowed = set(INTERFERENCE_SUBOPTIONS.get(opt, ()))
        seen, valid = set(), []
        for s in (raw_subs or []):
            ks = str(s)
            if ks in allowed and ks not in seen:
                seen.add(ks)
                valid.append(ks)
        out[opt] = valid
    return out


def _interference_block(modifiers) -> str:
    """把已开启的干扰项（含子选项）拼成一段系统指令；未开启则返回空串。"""
    norm = normalize_modifiers(modifiers)
    if not norm:
        return ""
    lines = []
    for opt in INTERFERENCE_KEYS:
        if opt not in norm:
            continue
        base = _BASE_FRAGMENTS[opt]
        labels = [_SUB_LABELS[opt][s] for s in norm[opt] if s in _SUB_LABELS[opt]]
        detail = f" Specifically: {'; '.join(labels)}." if labels else "."
        lines.append(f"- {base}{detail}")
    if not lines:
        return ""
    return (
        "\n\nREALISM MODIFIERS — you MUST stay fully in character and apply ALL of the following, "
        "while keeping the conversation ultimately intelligible and helpful for an English learner. "
        "These affect ONLY your own speech/behaviour, NOT how fairly you score the learner:\n"
        + "\n".join(lines)
    )


def skill_speaking_check_scenario():
    """场景内容审核 — 系统指令"""
    return (
        "You are a content moderation AI for an English learning platform. "
        "Analyze the following scenario description provided by a user for a role-play practice. "
        "Check if it contains any NSFW content, extreme violence, illegal activities, hate speech, or highly inappropriate topics. "
        "Output ONLY a raw JSON strictly matching: {\"valid\": true|false, \"reason\": \"If false, brief reason in Chinese, else empty string\"}"
    )


def skill_speaking_scenario_opening(scenario: str, modifiers=None):
    """场景开场白 — 系统指令"""
    return (
        "You are starting a role-play speaking practice with an English learner.\n"
        f"SCENARIO: {scenario}\n\n"
        "Begin the conversation naturally in character. You are the counterpart in this scenario.\n"
        "If the user uploaded reference images or files, use them as context to make your opening more relevant.\n"
        "Output ONLY a short, natural opening line (2-3 sentences) to start the conversation.\n"
        "Make it immersive — set the scene through your words, not by describing it.\n"
        "Reply in English only. Output raw text only, no quotes, no JSON, no markdown."
        + _interference_block(modifiers)
    )


def skill_speaking_scenario_chat(scenario: str, modifiers=None):
    """场景对话评估 — 系统指令"""
    return (
        f"You are engaging in a role-play speaking practice with an English learner.\n"
        f"SCENARIO: {scenario}\n\n"
        "Act as the counterpart in this scenario. Evaluate the user's latest message, keep the conversation moving naturally, "
        "and decide if the conversation has reached a natural conclusion or if the user explicitly ended it."
        + _interference_block(modifiers) +
        "\nCRITICAL INSTRUCTION: You MUST return your response as a raw JSON object and nothing else. "
        "Your JSON MUST contain exactly these six keys:\n"
        "{\n"
        "  \"reply\": \"(string, in Markdown/GFM) Your in-character conversational response\",\n"
        "  \"grammar_score\": (float 0.0-9.0, in 0.5 increments, e.g. 6.5) Grammar accuracy of the user's latest message,\n"
        "  \"vocab_score\": (float 0.0-9.0, in 0.5 increments) Vocabulary richness of the user's latest message,\n"
        "  \"relevance_score\": (float 0.0-9.0, in 0.5 increments) How relevant the user's message is to the topic,\n"
        "  \"is_continue\": (integer 1 or 0) Output 1 to continue the conversation, or 0 if the scenario is completely resolved/ended,\n"
        "  \"corrected_text\": \"(string, in Markdown/GFM) A corrected and improved version of the user's latest message, fixing grammar errors and upgrading vocabulary while preserving the original meaning. If already perfect, return it as-is.\"\n"
        "}"
        "\nIMPORTANT: The values of reply and corrected_text must be valid Markdown (GFM)."
    )


def skill_speaking_random_scenario(history_text: str):
    """随机场景生成 — 系统指令"""
    return (
        "You are an expert IELTS instructor. "
        "The user needs a random role-play scenario for IELTS Speaking practice. "
        "Generate a short, concise scenario description (1-2 sentences) in Chinese. "
        "Examples: '我在国外刚进门点汉堡，你是收银员，请引导我点餐', '我们是同学，正在讨论周末去哪里旅游'. "
        "Also provide a 'short_scenario' (2-5 words) summarizing the theme (e.g., '餐厅点餐', '周末旅游') to save token space in future history. "
        "Do NOT generate anything similar to the following previously used scenarios:\n"
        f"{history_text}\n\n"
        "CRITICAL: Output ONLY a raw JSON object with keys 'scenario' and 'short_scenario'. Do not use markdown. "
        "Example: {\"scenario\": \"我在书店想买一本关于编程的书，你是店员，请给我推荐并结账。\", \"short_scenario\": \"书店买书\"}"
    )
