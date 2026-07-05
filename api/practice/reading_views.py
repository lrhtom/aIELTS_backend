"""IELTS Academic Reading — AI 出题端点。

覆盖 11 种官方题型 (single-type) + 综合套题 (3 篇 passage) + 元数据端点。
Prompt 模板见 backend/api/skills/reading/generation.py。
"""
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.core.rate_limit import check_rate_limit
from api.core.utils import call_ai_api
from api.models import AIQuestion
from api.practice.ai_question_views import create_ai_question, spawn_ai_generation
from api.skills.reading.generation import (
    READING_FULL_PASSAGE_COUNT,
    READING_FULL_QUESTIONS_PER_PASSAGE,
    READING_QUESTION_COUNT_DEFAULT,
    READING_QUESTION_TYPES,
    READING_TOPIC_POOL,
    SKILL_READING_FULL_PASSAGE_TEMPLATE,
    get_paragraph_rule,
    get_topic_instruction,
)

# ── 常量 ─────────────────────────────────────────────
MCQ_OPTION_KEYS = ['A', 'B', 'C', 'D']
TF_MODE_EASY = 'easy'
TF_MODE_NORMAL = 'normal'

# 综合模式每篇 passage 的题型组合池 (2-3 种题型混合)
_FULL_MIX_POOLS = [
    ['matching_headings', 'multiple_choice', 'true_false'],
    ['matching_info', 'sentence_completion', 'yes_no'],
    ['multiple_choice', 'matching_features', 'summary_completion'],
    ['true_false', 'matching_sentence', 'short_answer'],
    ['matching_headings', 'note_completion', 'multiple_choice'],
]


# ── 参数归一化辅助 ────────────────────────────────────
def _norm_qtype(value: Any) -> str:
    v = str(value or '').strip().lower()
    if v in READING_QUESTION_TYPES:
        return v
    # 兼容旧枚举
    if v in {'mcq', 'multi_choice'}:
        return 'multiple_choice'
    if v in {'tfng', 'tf'}:
        return 'true_false'
    if v in {'ynng', 'yn'}:
        return 'yes_no'
    return 'multiple_choice'


def _norm_tf_mode(value: Any) -> str:
    v = str(value or '').strip().lower()
    return TF_MODE_EASY if v in {'easy', 'simple'} else TF_MODE_NORMAL


def _norm_topic(value: Any) -> tuple[str, str]:
    return get_topic_instruction(str(value or '').strip().lower() or 'random')


def _norm_word_limit(min_w: Any, max_w: Any) -> tuple[str, str]:
    """Return (long form for prompt, short form for on-page instruction)."""
    try:
        lo = max(1, int(min_w))
    except (TypeError, ValueError):
        lo = 1
    try:
        hi = max(lo, int(max_w))
    except (TypeError, ValueError):
        hi = max(2, lo)
    if lo == hi:
        long = f"EXACTLY {hi} word{'s' if hi > 1 else ''}"
        short = f"{hi} WORD{'S' if hi > 1 else ''}"
    else:
        long = f"NO MORE THAN {hi} WORDS (between {lo} and {hi})"
        short = f"{hi} WORDS"
    return long, short


def _build_common_context(
    *,
    difficulty: str,
    topic_instruction: str,
    tone_instruction: str,
    vocab_instruction: str,
    marker_rule: str,
    needs_labelled_paragraphs: bool,
    topic_key: str,
) -> dict:
    return {
        'difficulty': difficulty,
        'topic_instruction': topic_instruction,
        'tone_instruction': tone_instruction,
        'vocab_instruction': vocab_instruction or '(No specific vocabulary target.)',
        'marker_rule': marker_rule or '(No marker rule.)',
        'paragraph_rule': get_paragraph_rule(needs_labelled_paragraphs),
        'topic': topic_key,
    }


def _tfng_context(judgement_mode: str) -> dict:
    if judgement_mode == TF_MODE_EASY:
        return {
            'tfng_allowed': 'True / False',
            'ng_required': '',
            'tfng_options_json': '{"True": "Statement agrees with the passage.", "False": "Statement contradicts the passage."}',
            'judgement_mode': TF_MODE_EASY,
        }
    return {
        'tfng_allowed': 'True / False / Not Given',
        'ng_required': ', and at least one Not Given',
        'tfng_options_json': '{"True": "Statement agrees with the passage.", "False": "Statement contradicts the passage.", "Not Given": "Passage does not provide enough information."}',
        'judgement_mode': TF_MODE_NORMAL,
    }


# ── 单题型 prompt 构建 ────────────────────────────────
def _build_prompt(
    question_type: str,
    *,
    difficulty: str,
    topic_key: str,
    topic_instruction: str,
    tone_instruction: str,
    vocab_instruction: str,
    marker_rule: str,
    judgement_mode: str,
    word_count_min: int,
    word_count_max: int,
) -> str:
    template, needs_word_limit, needs_labelled = READING_QUESTION_TYPES[question_type]
    ctx = _build_common_context(
        difficulty=difficulty,
        topic_instruction=topic_instruction,
        tone_instruction=tone_instruction,
        vocab_instruction=vocab_instruction,
        marker_rule=marker_rule,
        needs_labelled_paragraphs=needs_labelled,
        topic_key=topic_key,
    )
    if question_type == 'true_false':
        ctx.update(_tfng_context(judgement_mode))
    if needs_word_limit:
        long, short = _norm_word_limit(word_count_min, word_count_max)
        ctx['word_count_desc'] = long
        ctx['word_count_desc_short'] = short
    return template.format(**ctx)


# ── 归一化 (每种题型独立函数) ─────────────────────────
def _norm_mcq_options(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {k: f'Option {k}' for k in MCQ_OPTION_KEYS}
    out = {}
    for k in MCQ_OPTION_KEYS:
        v = raw.get(k) or raw.get(k.lower()) or raw.get(k.upper())
        out[k] = str(v or '').strip() or f'Option {k}'
    return out


def _norm_mcq_answer(raw: Any) -> str:
    a = str(raw or '').strip().upper()
    return a if a in MCQ_OPTION_KEYS else 'A'


def _norm_tf_answer(raw: Any, judgement_mode: str) -> str:
    allowed = ['True', 'False'] if judgement_mode == TF_MODE_EASY else ['True', 'False', 'Not Given']
    text = str(raw or '').strip()
    for item in allowed:
        if text.lower() == item.lower():
            return item
    compact = text.lower().replace(' ', '').replace('_', '').replace('-', '')
    aliases = {'true': 'True', 't': 'True', 'false': 'False', 'f': 'False', 'notgiven': 'Not Given', 'ng': 'Not Given'}
    picked = aliases.get(compact)
    return picked if picked in allowed else allowed[0]


def _norm_yn_answer(raw: Any) -> str:
    text = str(raw or '').strip()
    for item in ['Yes', 'No', 'Not Given']:
        if text.lower() == item.lower():
            return item
    compact = text.lower().replace(' ', '').replace('_', '').replace('-', '')
    return {'yes': 'Yes', 'y': 'Yes', 'no': 'No', 'n': 'No', 'notgiven': 'Not Given', 'ng': 'Not Given'}.get(compact, 'Yes')


def _norm_answers_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if raw is None:
        return []
    return [str(raw).strip()]


def _norm_letter(raw: Any, letters: list[str], fallback: str) -> str:
    a = str(raw or '').strip().upper()
    return a if a in letters else fallback


def _norm_roman(raw: Any, valid: list[str]) -> str:
    a = str(raw or '').strip().lower()
    return a if a in valid else (valid[0] if valid else 'i')


def _default_explanation() -> str:
    return '请结合原文定位证据后再判断此题。'


def _normalize_questions(
    question_type: str,
    payload: dict,
    *,
    judgement_mode: str,
    expected_count: int = READING_QUESTION_COUNT_DEFAULT,
) -> dict:
    """针对不同题型对 questions 数组做归一化。返回原 payload (in-place 更新)."""
    raw_questions = payload.get('questions')
    source = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict] = []

    if question_type == 'multiple_choice':
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Question {idx + 1}',
                'options': _norm_mcq_options(item.get('options')),
                'answer': _norm_mcq_answer(item.get('answer')),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'true_false':
        allowed = ['True', 'False'] if judgement_mode == TF_MODE_EASY else ['True', 'False', 'Not Given']
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            options = {a: '' for a in allowed}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Statement {idx + 1}',
                'options': options,
                'answer': _norm_tf_answer(item.get('answer'), judgement_mode),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'yes_no':
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Statement {idx + 1}',
                'options': {'Yes': '', 'No': '', 'Not Given': ''},
                'answer': _norm_yn_answer(item.get('answer')),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'matching_headings':
        # AI 应该给 6 道题 (每段一题) — 我们不硬截断到 5
        bank = payload.get('headings_bank') if isinstance(payload.get('headings_bank'), dict) else {}
        valid_romans = list(bank.keys()) or ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix']
        for idx, item in enumerate(source[:6] or []):
            if not isinstance(item, dict):
                continue
            normalized.append({
                'id': idx + 1,
                'paragraph': str(item.get('paragraph') or chr(ord('A') + idx)).strip().upper()[:1],
                'answer': _norm_roman(item.get('answer'), valid_romans),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'matching_info':
        labels = payload.get('paragraph_labels') if isinstance(payload.get('paragraph_labels'), list) else ['A', 'B', 'C', 'D', 'E', 'F']
        letters = [str(x).strip().upper()[:1] for x in labels]
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Information item {idx + 1}',
                'answer': _norm_letter(item.get('answer'), letters, letters[0] if letters else 'A'),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'matching_features':
        bank = payload.get('features_bank') if isinstance(payload.get('features_bank'), dict) else {}
        letters = [k.upper() for k in bank.keys()] or ['A', 'B', 'C']
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Feature item {idx + 1}',
                'answer': _norm_letter(item.get('answer'), letters, letters[0]),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type == 'matching_sentence':
        bank = payload.get('endings_bank') if isinstance(payload.get('endings_bank'), dict) else {}
        letters = [k.upper() for k in bank.keys()] or ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Sentence beginning {idx + 1}',
                'answer': _norm_letter(item.get('answer'), letters, letters[0]),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    elif question_type in {'sentence_completion', 'short_answer', 'note_completion'}:
        # 数据结构相似：answers 是 list[str]
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            q = {
                'id': idx + 1,
                'answers': _norm_answers_list(item.get('answers')) or [''],
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            }
            # sentence_completion / short_answer 需要 question 字段, note_completion 不需要
            if question_type != 'note_completion':
                q['question'] = str(item.get('question') or '').strip() or f'Question {idx + 1}'
            normalized.append(q)

    elif question_type == 'summary_completion':
        bank = payload.get('word_bank') if isinstance(payload.get('word_bank'), dict) else {}
        letters = [k.upper() for k in bank.keys()] or ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for idx in range(expected_count):
            item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'answer': _norm_letter(item.get('answer'), letters, letters[0]),
                'explanation': str(item.get('explanation') or '').strip() or _default_explanation(),
            })

    payload['questions'] = normalized
    return payload


def _preserve_type_specific_fields(question_type: str, source: dict, target: dict) -> None:
    """把 AI 返回的题型专属字段透传到 target payload."""
    passthrough = {
        'matching_headings': ['headings_bank'],
        'matching_info': ['paragraph_labels'],
        'matching_features': ['features_bank'],
        'matching_sentence': ['endings_bank'],
        'summary_completion': ['summary_intro', 'summary_text', 'word_bank'],
        'note_completion': ['layout', 'note_intro', 'note_content'],
        'sentence_completion': ['wordLimit'],
        'short_answer': ['wordLimit'],
        'true_false': ['judgementMode'],
    }
    for field in passthrough.get(question_type, []):
        if field in source and source[field] is not None:
            target[field] = source[field]


# ── 单题型出题主入口 ──────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_reading(request):
    """POST /api/reading/generate — 生成单一题型的阅读练习 (含 topic 参数)."""
    try:
        limit = check_rate_limit(request.user.id, 'reading_generate', max_calls=5, window=60)
        if limit:
            return limit

        data = request.data
        words = data.get('words', []) or []
        difficulty = str(data.get('difficulty', '7.0'))
        absurd_mode = str(data.get('absurdMode', 'false')).lower() == 'true'
        question_type = _norm_qtype(data.get('questionType') or data.get('question_type'))
        judgement_mode = _norm_tf_mode(data.get('judgementMode') or data.get('judgement_mode'))
        topic_key, topic_instruction = _norm_topic(data.get('topic'))
        word_count_min = data.get('wordCountMin', 1)
        word_count_max = data.get('wordCountMax', 3)
        custom_title = (data.get('customName') or data.get('customTitle') or '').strip()
        custom_description = (data.get('customDescription') or data.get('description') or '').strip()
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe: no profanity, no sexual content, no harassment."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        if not words:
            vocab_instruction = ''
            marker_rule = ''
        else:
            vocab_instruction = f'Incorporate as many of these target words as possible: {", ".join(words)}. Preserve their surface forms where grammatically natural.'
            marker_rule = "Whenever you use one of the target vocabulary words (or its tense/plural variants) in either the passage OR the questions/options, wrap it in double asterisks like **word**. Do NOT use asterisks for anything else."

        prompt = _build_prompt(
            question_type,
            difficulty=difficulty,
            topic_key=topic_key,
            topic_instruction=topic_instruction,
            tone_instruction=tone_instruction,
            vocab_instruction=vocab_instruction,
            marker_rule=marker_rule,
            judgement_mode=judgement_mode,
            word_count_min=word_count_min,
            word_count_max=word_count_max,
        )

        print(f'[Reading] 📥 async spawn type={question_type} topic={topic_key} band={difficulty}', flush=True)

        user_id = request.user.id
        placeholder = f'📝 阅读生成中... ({question_type} / {topic_key})'

        def _generator(_row):
            result = call_ai_api(
                prompt,
                provider=provider,
                user_id=user_id,
                singleflight_scope=f'reading_generate:{question_type}',
            )
            title = str(result.get('title') or '').strip() or 'Reading Passage'
            passage = str(result.get('passage') or '').strip()
            if not passage:
                raise ValueError('AI returned no passage.')

            payload: dict[str, Any] = {
                'title': title,
                'passage': passage,
                'topic': topic_key,
                'questionType': question_type,
            }
            if question_type == 'true_false':
                payload['judgementMode'] = judgement_mode

            _preserve_type_specific_fields(question_type, result, payload)
            merged = {**payload, 'questions': result.get('questions')}
            merged = _normalize_questions(question_type, merged, judgement_mode=judgement_mode)
            payload['questions'] = merged['questions']

            if question_type in {'sentence_completion', 'short_answer', 'note_completion'}:
                missing = _count_answers_missing_from_passage(payload['questions'], passage)
                if missing:
                    payload['answerVerificationWarnings'] = missing
            if custom_description:
                payload['description'] = custom_description
            return title, payload

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_READING,
            subtype=question_type,
            placeholder_title=placeholder,
            generator=_generator,
            custom_title=custom_title,
        )
        return JsonResponse({
            'aiQuestionId': row.id,
            'status': row.status,
            'title': row.title,
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _count_answers_missing_from_passage(questions: list[dict], passage: str) -> int:
    """Return count of answers that don't appear verbatim (case-insensitive) in the passage."""
    passage_lc = passage.lower()
    missing = 0
    for q in questions:
        answers = q.get('answers') or []
        if not answers:
            continue
        # At least one variant should appear in passage
        if not any(str(a).strip().lower() in passage_lc for a in answers):
            missing += 1
    return missing


# ── 综合套题：3 篇 passage ────────────────────────────
def _pick_full_mix(seed: int) -> list[str]:
    rng = random.Random(seed)
    return list(rng.choice(_FULL_MIX_POOLS))


def _build_full_passage_prompt(
    passage_num: int,
    *,
    mix_types: list[str],
    difficulty: str,
    topic_key: str,
    topic_instruction: str,
    tone_instruction: str,
) -> tuple[str, list[dict]]:
    """Return (prompt, section_plan) where section_plan describes how questions split across types."""
    total = READING_FULL_QUESTIONS_PER_PASSAGE
    # Split total questions across mix (roughly balanced)
    per_type = total // len(mix_types)
    remainder = total - per_type * len(mix_types)
    section_plan: list[dict] = []
    start = 1
    for i, qt in enumerate(mix_types):
        count = per_type + (1 if i < remainder else 0)
        section_plan.append({
            'questionType': qt,
            'startId': start,
            'endId': start + count - 1,
            'count': count,
        })
        start += count

    needs_labelled = any(READING_QUESTION_TYPES[qt][2] for qt in mix_types)
    mix_desc_lines = []
    for sec in section_plan:
        mix_desc_lines.append(f'  - Questions {sec["startId"]}-{sec["endId"]} ({sec["count"]} items): {sec["questionType"]}')
    mix_desc = '\n'.join(mix_desc_lines)

    prompt = SKILL_READING_FULL_PASSAGE_TEMPLATE.format(
        difficulty=difficulty,
        topic_instruction=topic_instruction,
        tone_instruction=tone_instruction,
        vocab_instruction='(No specific vocabulary target — pick topic-appropriate academic vocabulary.)',
        marker_rule='(No marker rule for full-test mode.)',
        paragraph_rule=get_paragraph_rule(needs_labelled),
        topic=topic_key,
        passage_num=passage_num,
        question_mix_desc=mix_desc,
        total_questions=total,
    )
    return prompt, section_plan


_READING_QT_ALIASES = {
    'mcq': 'multiple_choice',
    'multiplechoice': 'multiple_choice',
    'multiple-choice': 'multiple_choice',
    'multiple choice': 'multiple_choice',
    'tf': 'true_false',
    't/f': 'true_false',
    'tfng': 'true_false',
    'true/false': 'true_false',
    'true false': 'true_false',
    'true_false_notgiven': 'true_false',
    'yn': 'yes_no',
    'y/n': 'yes_no',
    'yesno': 'yes_no',
    'yes/no': 'yes_no',
    'yes no': 'yes_no',
    'ynng': 'yes_no',
    'headings': 'matching_headings',
    'match_headings': 'matching_headings',
    'matching-headings': 'matching_headings',
    'matchingheadings': 'matching_headings',
    'info': 'matching_info',
    'match_info': 'matching_info',
    'features': 'matching_features',
    'match_features': 'matching_features',
    'sentence_endings': 'matching_sentence',
    'match_sentence': 'matching_sentence',
    'matching_sentence_endings': 'matching_sentence',
    'sentence': 'sentence_completion',
    'sentence_completion': 'sentence_completion',
    'summary': 'summary_completion',
    'summary_completion': 'summary_completion',
    'note': 'note_completion',
    'notes': 'note_completion',
    'note_completion': 'note_completion',
    'short': 'short_answer',
    'short_answer': 'short_answer',
    'shortanswer': 'short_answer',
}


def _canonical_qt(raw: Any) -> str:
    s = str(raw or '').strip().lower()
    if not s:
        return ''
    if s in _READING_QT_ALIASES:
        return _READING_QT_ALIASES[s]
    # Compact form (no separators) for fuzzy match
    compact = s.replace(' ', '').replace('-', '').replace('_', '')
    return _READING_QT_ALIASES.get(compact, s)


def _normalize_full_passage(result: dict, section_plan: list[dict], *, passage_num: int, topic_key: str) -> dict:
    title = str(result.get('title') or '').strip() or f'Passage {passage_num}'
    passage = str(result.get('passage') or '').strip()
    raw_sections = result.get('sections') if isinstance(result.get('sections'), list) else []

    # 建立 index: {canonical_qt: [raw_sec, ...]} 用来按题型顺序取；
    # 同题型可能被 AI 拆成多个 sub-section (e.g. 两组 MCQ)，用队列消费避免重复
    indexed_by_qt: dict[str, list[dict]] = {}
    unmatched_by_order: list[dict] = []
    for raw_sec in raw_sections:
        if not isinstance(raw_sec, dict):
            continue
        can = _canonical_qt(raw_sec.get('questionType'))
        if can:
            indexed_by_qt.setdefault(can, []).append(raw_sec)
        else:
            unmatched_by_order.append(raw_sec)

    sections_out: list[dict] = []
    for plan_idx, plan in enumerate(section_plan):
        qt = plan['questionType']
        bucket = indexed_by_qt.get(qt) or []
        raw_sec = bucket.pop(0) if bucket else {}
        # 位置兜底：AI 返回 sections 数量与 plan 一致但 questionType 全对不上时，
        # 按 plan 顺序取原始 sections 里的第 N 个。
        if not raw_sec and plan_idx < len(raw_sections) and isinstance(raw_sections[plan_idx], dict):
            fallback_sec = raw_sections[plan_idx]
            fallback_can = _canonical_qt(fallback_sec.get('questionType'))
            if fallback_can != qt:
                raw_sec = fallback_sec
        payload = raw_sec.get('payload') if isinstance(raw_sec.get('payload'), dict) else {}
        # 兼容 AI 把 questions 放到 payload 里的情况
        raw_qs = raw_sec.get('questions')
        if not (isinstance(raw_qs, list) and raw_qs):
            raw_qs = payload.get('questions') if isinstance(payload.get('questions'), list) else raw_qs
        if not (isinstance(raw_qs, list) and raw_qs):
            print(
                f'[Reading Full] ⚠️ passage {passage_num} section {plan_idx + 1} ({qt}): '
                f'AI 未提供 questions，将 fill placeholders ({plan["count"]} items). '
                f'raw_sections keys={[list(s.keys()) for s in raw_sections if isinstance(s, dict)]}',
                flush=True,
            )
        merged: dict[str, Any] = {'questions': raw_qs}
        for k, v in payload.items():
            if k == 'questions':
                continue  # 已上面处理过，别覆盖回去
            merged[k] = v
        # Lift specific fields into merged so preserve_fields can find them
        for k in ('headings_bank', 'paragraph_labels', 'features_bank', 'endings_bank',
                  'summary_intro', 'summary_text', 'word_bank',
                  'layout', 'note_intro', 'note_content', 'wordLimit'):
            if k in raw_sec and k not in merged:
                merged[k] = raw_sec[k]

        expected = plan['count']
        merged = _normalize_questions(qt, merged, judgement_mode=TF_MODE_NORMAL, expected_count=expected)

        # Rewrite ids so they are globally unique across the ENTIRE test.
        # Passage 1 => IDs 1..13, Passage 2 => 14..26, Passage 3 => 27..39.
        # Without this, all 3 passages restart from 1 and answers collide in the
        # frontend's single answers ref.
        passage_offset = (passage_num - 1) * READING_FULL_QUESTIONS_PER_PASSAGE
        start = plan['startId'] + passage_offset
        end = plan['endId'] + passage_offset
        for offset, q in enumerate(merged['questions']):
            q['id'] = start + offset

        sec_out: dict[str, Any] = {
            'questionType': qt,
            'instructions': str(raw_sec.get('instructions') or '').strip() or f'Questions {start}-{end}',
            'startId': start,
            'endId': end,
            'questions': merged['questions'],
        }
        # Carry over type-specific bank fields at the section level (frontend reads them here)
        _preserve_type_specific_fields(qt, merged, sec_out)
        sections_out.append(sec_out)

    return {
        'passageNum': passage_num,
        'title': title,
        'passage': passage,
        'topic': topic_key,
        'sections': sections_out,
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_reading_full(request):
    """POST /api/reading/full — 生成综合套题.

    默认生成 3 篇 passage; 可通过下列参数生成单篇:
      - passageNum: 1|2|3   仅生成指定序号的 passage
      - mixTypes: list[str] 覆盖该篇的题型组合 (2-3 种题型 key)
    如果只请求单篇, 响应仍走 `passages` 数组格式 (长度=1), 前端一致处理.
    """
    try:
        limit = check_rate_limit(request.user.id, 'reading_full', max_calls=3, window=120)
        if limit:
            return limit

        data = request.data
        difficulty = str(data.get('difficulty', '7.0'))
        absurd_mode = str(data.get('absurdMode', 'false')).lower() == 'true'
        topic_key, topic_instruction = _norm_topic(data.get('topic'))
        custom_title = (data.get('customName') or data.get('customTitle') or '').strip()
        custom_description = (data.get('customDescription') or data.get('description') or '').strip()
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        # ── 单篇 override ──
        raw_passage_num = data.get('passageNum')
        try:
            target_passage = int(raw_passage_num) if raw_passage_num is not None else None
        except (TypeError, ValueError):
            target_passage = None
        if target_passage is not None and target_passage not in (1, 2, 3):
            target_passage = None
        # 用户自定义 mix
        raw_mix = data.get('mixTypes')
        override_mix: list[str] | None = None
        if isinstance(raw_mix, list) and raw_mix:
            filtered = [str(x).strip().lower() for x in raw_mix if str(x).strip().lower() in READING_QUESTION_TYPES]
            if filtered:
                override_mix = filtered[:3]  # 最多 3 种

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        # 决定要生成哪些 passage 的编号
        if target_passage is not None:
            passage_nums = [target_passage]
        else:
            passage_nums = list(range(1, READING_FULL_PASSAGE_COUNT + 1))

        # 每篇的 mix
        mixes_per_passage: dict[int, list[str]] = {}
        for n in passage_nums:
            if override_mix:
                mixes_per_passage[n] = override_mix
            else:
                mixes_per_passage[n] = _pick_full_mix(seed=(n - 1) * 7919 + hash(topic_key) % 997)

        prompts_and_plans: list[tuple[int, list[str], str, list[dict]]] = []
        for n in passage_nums:
            mix_types = mixes_per_passage[n]
            prompt, plan = _build_full_passage_prompt(
                passage_num=n,
                mix_types=mix_types,
                difficulty=difficulty,
                topic_key=topic_key,
                topic_instruction=topic_instruction,
                tone_instruction=tone_instruction,
            )
            prompts_and_plans.append((n, mix_types, prompt, plan))

        print(f'[Reading] 🎯 async FULL topic={topic_key} band={difficulty} passages={passage_nums} mixes={list(mixes_per_passage.values())}', flush=True)

        is_single = len(prompts_and_plans) == 1
        subtype = f'full_p{target_passage}' if is_single else 'full'
        title_suffix = f' - Passage {target_passage}' if is_single else ''
        title = f'IELTS Reading Full Test ({topic_key}){title_suffix}'
        placeholder = f'📝 综合套题生成中... ({topic_key})'
        user_id = request.user.id
        # Snapshot into a plain-typed structure so the closure survives after the
        # HTTP request scope goes away.
        snapshot: list[tuple[int, str, list[dict]]] = [
            (num, prompt, plan) for num, _mx, prompt, plan in prompts_and_plans
        ]

        def _generator(_row):
            passages_out: list[dict] = []

            def _run(num, prompt, plan):
                r = call_ai_api(
                    prompt,
                    provider=provider,
                    user_id=user_id,
                    singleflight_scope=f'reading_full:{num}',
                )
                return num, r, plan

            if len(snapshot) == 1:
                num, prompt, plan = snapshot[0]
                n, r, p = _run(num, prompt, plan)
                passages_out.append(_normalize_full_passage(r, p, passage_num=n, topic_key=topic_key))
            else:
                results_by_num: dict[int, dict] = {}
                plans_by_num: dict[int, list[dict]] = {}
                with ThreadPoolExecutor(max_workers=len(snapshot)) as pool:
                    futures = [pool.submit(_run, num, prompt, plan) for num, prompt, plan in snapshot]
                    for fut in as_completed(futures):
                        n, r, p = fut.result()
                        results_by_num[n] = r
                        plans_by_num[n] = p
                for n, _p, _pl in snapshot:
                    passages_out.append(_normalize_full_passage(results_by_num[n], plans_by_num[n], passage_num=n, topic_key=topic_key))

            payload: dict[str, Any] = {
                'title': title,
                'topic': topic_key,
                'questionType': 'full',
                'singlePassage': is_single,
                'passages': passages_out,
            }
            if custom_description:
                payload['description'] = custom_description
            return title, payload

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_READING,
            subtype=subtype,
            placeholder_title=placeholder,
            generator=_generator,
            custom_title=custom_title,
        )
        return JsonResponse({
            'aiQuestionId': row.id,
            'status': row.status,
            'title': row.title,
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ── 元数据端点 (给前端下拉框用) ────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reading_meta(request):
    """GET /api/reading/meta — 返回题型清单和题材池, 给前端配置页."""
    return Response({
        'questionTypes': [
            {'key': k, 'needsWordLimit': needs_wl, 'needsLabelledParagraphs': needs_lp}
            for k, (_tmpl, needs_wl, needs_lp) in READING_QUESTION_TYPES.items()
        ],
        'topics': [{'key': k, 'name': v} for k, v in READING_TOPIC_POOL.items()],
        'difficulties': ['6.0', '6.5', '7.0', '7.5', '8.0', '8.5'],
        'judgementModes': [TF_MODE_NORMAL, TF_MODE_EASY],
        'fullMode': {
            'passageCount': READING_FULL_PASSAGE_COUNT,
            'questionsPerPassage': READING_FULL_QUESTIONS_PER_PASSAGE,
        },
    })
