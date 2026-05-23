"""
Speaking Part 2/3 Skills — 口语 Part 2-3 出题 / 评分 / 总结 AI 技能
"""


def skill_speaking_part2_generate():
    """Part 2 出题 — 系统指令"""
    return (
        'You are an IELTS speaking examiner. Generate a Part 2 practice set. '
        'Return strict raw JSON only with key "questions". '
        'questions must be an array of exactly 1 object. '
        'The object must have keys "topic" and "question". '
        'The "question" value MUST exactly follow this official IELTS Cue Card format using Markdown:\n'
        'Describe a/an [topic].\n'
        'You should say:\n'
        '- [point 1]\n'
        '- [point 2]\n'
        '- [point 3]\n'
        'and explain [reason/feeling].\n'
        'Example: {"questions":[{"topic":"A place","question":"Describe a place you visited..."}]}'
    )


def skill_speaking_part3_generate(topic_instruction: str):
    """Part 3 出题 — 系统指令"""
    return (
        'You are an IELTS speaking examiner. Generate a Part 3 discussion set. '
        f'{topic_instruction}'
        'Return strict raw JSON only with key "questions". '
        'questions must be an array of exactly 6 objects. '
        'Each object must have keys "topic" and "question". '
        'Each "question" value must be valid Markdown (GFM). '
        'Use abstract, society-level discussion style questions with increasing depth. '
        'Example: {"questions":[{"topic":"...","question":"..."}]}'
    )


def skill_speaking_part23_evaluate_system(label: str, duration_seconds: float, word_count: int):
    """Part 2/3 单题评分 — 系统指令"""
    return (
        f'You are an expert IELTS examiner evaluating a {label} answer. '
        f'Duration seconds: {int(duration_seconds)}. Word count: {word_count}. '
        'Return raw JSON only with these keys: '
        '{"grammar_score":6.5,"vocab_score":6.5,"relevance_score":6.5,'
        '"coherence_score":6.5,"depth_score":6.5,'
        '"duration_score":6.5,"word_count_score":6.5,'
        '"length_multiplier":0.75,"length_feedback":"...",'
        '"feedback":"...","corrected_text":"..."}. '
        'Scoring range: 0-9 with 0.5 step. '
        'length_multiplier range: 0.0-1.0. '
        'Prioritize realistic timing/length judgement using provided duration and word count. '
        'feedback should be concise and actionable.'
    )


def skill_speaking_part23_evaluate_user_msg(question: str, user_answer: str,
                                            duration_seconds: float, word_count: int):
    """Part 2/3 单题评分 — 用户消息"""
    return (
        f'Question:\n{question}\n\n'
        f'Candidate Answer:\n{user_answer}\n\n'
        f'Duration seconds: {int(duration_seconds)}\n'
        f'Word count: {word_count}'
    )


def skill_speaking_part23_summary_system(part_label: str):
    """Part 2/3 最终总结 — 系统指令"""
    return (
        f'You are an IELTS examiner. Provide a final summary for speaking {part_label}. '
        'Return raw JSON only with keys: '
        '{"overall_band_estimate":6.5,"strengths":"...","weaknesses":"...",'
        '"analysis":"...","advice":"..."}'
    )


def skill_speaking_part23_summary_user_msg(history_text: str):
    """Part 2/3 最终总结 — 用户消息"""
    return f'History:\n{history_text}'
