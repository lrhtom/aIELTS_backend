"""IELTS Listening — AI 出题端点.

覆盖 9 种官方题型 (single-type) + 4 Section 综合套题 + 元数据端点.
Prompt 模板见 backend/api/skills/listening/generation.py.

保留原有 generate_listening_audio (edge-tts 单声道), full-test 使用同一音频端点分段调用.
"""
import hashlib
import html
import os
import random
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.core.rate_limit import check_rate_limit
from api.core.utils import call_ai_api
from api.models import AIQuestion
from api.practice.ai_question_views import create_ai_question, spawn_ai_generation
from api.skills.listening.generation import (
    # 现有 4 种模板
    SKILL_LISTENING_ARTICLE_TEMPLATE as ARTICLE_LISTENING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MULTIPLE_CHOICE_TEMPLATE as ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE,
    SKILL_LISTENING_SENTENCE_TEMPLATE as SENTENCE_LISTENING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MAP_TEMPLATE as MAP_LABELLING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MAP_SUBTYPES as MAP_SUBTYPES,
    # v2 新增
    LISTENING_QUESTION_TYPES_V2,
    LISTENING_SCENARIO_POOL,
    LISTENING_SECTION_TEMPLATES,
    LISTENING_FULL_SECTION_COUNT,
    LISTENING_FULL_QUESTIONS_PER_SECTION,
    get_listening_scenario,
    get_speakers_desc,
)


LISTENING_AUDIO_SUBDIR = 'listening_audio'
_LEGACY_TYPES = {'article', 'sentence', 'multiple_choice', 'map'}
_NEW_TYPES = {'form', 'table', 'flowchart', 'matching', 'short_answer'}


# ── 参数归一化 ─────────────────────────────────────────
def _norm_type(value: Any) -> str:
    v = str(value or 'article').strip().lower()
    if v in LISTENING_QUESTION_TYPES_V2:
        return v
    return 'article'


def _norm_word_limit(min_w: Any, max_w: Any) -> tuple[str, str]:
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


def _default_section_for_type(qt: str) -> str:
    """Which section pool this question type is most authentic in."""
    return {
        'form': 's1', 'table': 's1',
        'article': 's4', 'sentence': 's4', 'flowchart': 's4',
        'map': 's2',
        'multiple_choice': 's3', 'matching': 's3',
        'short_answer': 's1',
    }.get(qt, 's1')


def _build_new_type_prompt(
    question_type: str,
    *,
    difficulty: str,
    scenario_key: str,
    tone_instruction: str,
    vocab_instruction: str,
    marker_rule: str,
    word_count_min: int,
    word_count_max: int,
) -> tuple[str, str]:
    """Build prompt for one of the v2 new question types. Returns (prompt, resolved_scenario_key)."""
    tmpl, n_speakers, length_desc, needs_wl = LISTENING_QUESTION_TYPES_V2[question_type]
    section_bucket = _default_section_for_type(question_type)
    resolved_key, scenario_instruction = get_listening_scenario(section_bucket, scenario_key)
    long_wl, short_wl = _norm_word_limit(word_count_min, word_count_max)

    ctx = {
        'difficulty': difficulty,
        'scenario_instruction': scenario_instruction,
        'scenario_key': resolved_key,
        'speakers_desc': get_speakers_desc(n_speakers),
        'tone_instruction': tone_instruction,
        'vocab_instruction': vocab_instruction or '(No specific vocabulary target.)',
        'marker_rule': marker_rule or '(No marker rule.)',
        'length_desc': length_desc,
        'word_count_desc': long_wl,
        'word_count_desc_short': short_wl,
    }
    return tmpl.format(**ctx), resolved_key


# ── 归一化 v2 题型返回 ────────────────────────────────
def _norm_answers(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if raw is None:
        return []
    return [str(raw).strip()]


def _norm_letter(raw: Any, letters: list[str], fallback: str) -> str:
    a = str(raw or '').strip().upper()
    return a if a in letters else fallback


def _normalize_new_type(question_type: str, result: dict) -> dict:
    """Normalize AI response for v2 new question types."""
    questions = result.get('questions')
    if not isinstance(questions, list):
        questions = []

    if question_type in {'form', 'table', 'flowchart', 'short_answer'}:
        expected = {'form': 10, 'table': 8, 'flowchart': 6, 'short_answer': 5}[question_type]
        normalized = []
        for idx in range(expected):
            item = questions[idx] if idx < len(questions) and isinstance(questions[idx], dict) else {}
            q = {
                'id': idx + 1,
                'answers': _norm_answers(item.get('answers')) or [''],
                'explanation': str(item.get('explanation') or '').strip() or '请结合音频原词判断.',
            }
            if question_type == 'short_answer':
                q['question'] = str(item.get('question') or '').strip() or f'Question {idx + 1}'
            normalized.append(q)
        result['questions'] = normalized

    elif question_type == 'matching':
        bank = result.get('options_bank') if isinstance(result.get('options_bank'), dict) else {}
        letters = [k.upper() for k in bank.keys()] or ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        normalized = []
        for idx in range(5):
            item = questions[idx] if idx < len(questions) and isinstance(questions[idx], dict) else {}
            normalized.append({
                'id': idx + 1,
                'question': str(item.get('question') or '').strip() or f'Item {idx + 1}',
                'answer': _norm_letter(item.get('answer'), letters, letters[0]),
                'explanation': str(item.get('explanation') or '').strip() or '请结合音频判断.',
            })
        result['questions'] = normalized

    return result


# ── 主入口: 单题型 ────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_listening(request):
    """POST /api/listening/generate — 单题型练习 (9 种题型)."""
    try:
        limit = check_rate_limit(request.user.id, 'listening_generate', max_calls=5, window=60)
        if limit:
            return limit

        data = request.data
        words = data.get('words', []) or []
        difficulty = str(data.get('difficulty', '7.0'))
        word_count_min = data.get('wordCountMin', 1)
        word_count_max = data.get('wordCountMax', 2)
        practice_type = _norm_type(data.get('practiceType'))
        absurd_mode = str(data.get('absurdMode', 'false')).lower() == 'true'
        scenario_key = str(data.get('scenario', '') or 'random').strip().lower()
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe: no profanity, no sexual content, no harassment."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        if not words:
            vocab_instruction = ''
            marker_rule = ''
            mc_marker_rule = ''
            answer_priority_rule = ''
        else:
            word_str = ', '.join(words)
            vocab_instruction = f"incorporating the following vocabulary words as much as possible: {word_str}"
            marker_rule = "Wrap target vocabulary in double asterisks like **word**."
            mc_marker_rule = "IMPORTANT RULES:\\nWhenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else."
            answer_priority_rule = "IMPORTANT: Try to incorporate the provided vocabulary words as answers. If possible, make these words the primary answers in the answers array."

        long_wl, short_wl = _norm_word_limit(word_count_min, word_count_max)
        if word_count_min == word_count_max:
            example_answer = {1: 'dedication', 2: 'climate change'}.get(word_count_min, 'rapidly growing population')
        else:
            example_answer = {1: 'dedication', 2: 'climate change'}.get(word_count_max, 'growing population')

        print(f'[Listening] 📥 type={practice_type} band={difficulty} scenario={scenario_key}', flush=True)

        # ── Legacy path (4 old types keep old prompt structure) ──
        resolved_scenario = scenario_key
        if practice_type in _LEGACY_TYPES:
            if practice_type == 'map':
                subtype_key = random.choice(list(MAP_SUBTYPES.keys()))
                subtype = MAP_SUBTYPES[subtype_key]
                prompt = MAP_LABELLING_PROMPT_TEMPLATE.format(
                    difficulty=difficulty,
                    tone_instruction=tone_instruction,
                    map_subtype=subtype['name'],
                    subtype_instructions=subtype['instructions'],
                )
            elif practice_type == 'multiple_choice':
                prompt = ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE.format(
                    vocab_instruction=vocab_instruction,
                    difficulty=difficulty,
                    mc_marker_rule=mc_marker_rule,
                    tone_instruction=tone_instruction,
                )
            elif practice_type == 'sentence':
                prompt = SENTENCE_LISTENING_PROMPT_TEMPLATE.format(
                    vocab_instruction=vocab_instruction,
                    difficulty=difficulty,
                    word_count_desc=long_wl,
                    example_answer=example_answer,
                    marker_rule=marker_rule,
                    answer_priority_rule=answer_priority_rule,
                    tone_instruction=tone_instruction,
                )
            else:  # article
                prompt = ARTICLE_LISTENING_PROMPT_TEMPLATE.format(
                    vocab_instruction=vocab_instruction,
                    difficulty=difficulty,
                    word_count_desc=long_wl,
                    example_answer=example_answer,
                    marker_rule=marker_rule,
                    answer_priority_rule=answer_priority_rule,
                    tone_instruction=tone_instruction,
                )
        else:
            # ── v2 new types ──
            prompt, resolved_scenario = _build_new_type_prompt(
                practice_type,
                difficulty=difficulty,
                scenario_key=scenario_key,
                tone_instruction=tone_instruction,
                vocab_instruction=vocab_instruction,
                marker_rule=marker_rule,
                word_count_min=word_count_min,
                word_count_max=word_count_max,
            )

        # Bind everything the generator needs into local values so the closure
        # runs safely on a background thread after the request scope closes.
        user_id = request.user.id
        prompt_snapshot = prompt
        resolved_scenario_snapshot = resolved_scenario
        practice_type_snapshot = practice_type
        provider_snapshot = provider
        placeholder_title = f'🎧 听力生成中... ({practice_type})'

        def _generator(_row):
            result = call_ai_api(
                prompt_snapshot,
                provider=provider_snapshot,
                user_id=user_id,
                singleflight_scope=f'listening_generate:{practice_type_snapshot}',
            )
            _post_process_listening_single(
                result,
                practice_type=practice_type_snapshot,
                resolved_scenario=resolved_scenario_snapshot,
            )
            title = str(result.get('title') or '').strip() or '听力练习'
            return title, {k: v for k, v in result.items() if k != 'atConsumed'}

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_LISTENING,
            subtype=practice_type,
            placeholder_title=placeholder_title,
            generator=_generator,
        )
        return JsonResponse({
            'aiQuestionId': row.id,
            'status': row.status,
            'title': row.title,
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _post_process_listening_single(result: dict, *, practice_type: str, resolved_scenario: str) -> None:
    """Extracted so the async worker can run the same normalisation pipeline
    that used to live inline in generate_listening. Mutates result in place.
    """
    if practice_type in _LEGACY_TYPES:
        if 'type' not in result:
            result['type'] = practice_type

        questions = result.get('questions', [])
        if not questions:
            raise ValueError('AI failed to generate questions. Please try again.')

        if len(questions) > 10:
            questions = questions[:10]
            result['questions'] = questions

        for i, q in enumerate(questions):
            q['id'] = i + 1

        for q in questions:
            q['question'] = re.sub(r'_{2,}', '_____', q.get('question', ''))

        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if bp:
                result['blanked_passage'] = re.sub(r'_{2,}', '_____', bp)

        if practice_type == 'sentence':
            for q in questions:
                if '_____' not in q.get('question', ''):
                    q['question'] = q['question'].rstrip('.') + ' _____.'

        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if not bp or '_____' not in bp:
                result['blanked_passage'] = result.get('passage', '')
            else:
                blank_count = bp.count('_____')
                if blank_count < len(questions):
                    result['questions'] = questions[:blank_count]
                    for i, q in enumerate(result['questions']):
                        q['id'] = i + 1

        if practice_type == 'map':
            map_data = result.get('map', {})
            landmarks = map_data.get('landmarks', [])
            mw = map_data.get('width', 600)
            mh = map_data.get('height', 400)
            for lm in landmarks:
                lm['x'] = max(30, min(mw - 30, lm.get('x', 300)))
                lm['y'] = max(30, min(mh - 30, lm.get('y', 200)))
            q_ids_in_map = {lm['questionId'] for lm in landmarks if 'questionId' in lm}
            result['questions'] = [q for q in result.get('questions', []) if q.get('id') in q_ids_in_map]
            if not isinstance(result.get('options'), list):
                result['options'] = []

        elif practice_type == 'multiple_choice':
            for q in result.get('questions', []):
                options_list = q.get('options')
                if isinstance(options_list, list) and len(options_list) >= 1:
                    correct_text = options_list[0]
                    shuffled = list(options_list)
                    random.shuffle(shuffled)
                    letters = ['A', 'B', 'C', 'D']
                    options_dict = {}
                    correct_letter = 'A'
                    for idx, opt_text in enumerate(shuffled[:4]):
                        letter = letters[idx]
                        options_dict[letter] = opt_text
                        if opt_text == correct_text:
                            correct_letter = letter
                    q['options'] = options_dict
                    q['answer'] = correct_letter
    else:
        # ── v2 new type post-processing ──
        if 'type' not in result:
            result['type'] = practice_type
        if 'scenario' not in result:
            result['scenario'] = resolved_scenario
        # _normalize_new_type mutates in-place but historically returned a new
        # dict; assign back so caller sees the same reference.
        normalized = _normalize_new_type(practice_type, result)
        if normalized is not result:
            result.clear()
            result.update(normalized)


# ── 4-Section 综合套题 ────────────────────────────────
def _build_section_prompt(
    section_num: int,
    *,
    difficulty: str,
    scenario_key: str,
    tone_instruction: str,
) -> tuple[str, str]:
    tmpl, n_speakers, length_desc = LISTENING_SECTION_TEMPLATES[section_num]
    section_bucket = f's{section_num}'
    resolved_key, scenario_instruction = get_listening_scenario(section_bucket, scenario_key)
    ctx = {
        'difficulty': difficulty,
        'scenario_instruction': scenario_instruction,
        'scenario_key': resolved_key,
        'speakers_desc': get_speakers_desc(n_speakers),
        'tone_instruction': tone_instruction,
        'vocab_instruction': '(Full-test mode — pick scenario-appropriate spoken vocabulary.)',
        'marker_rule': '(No marker rule for full-test mode.)',
        'length_desc': length_desc,
    }
    return tmpl.format(**ctx), resolved_key


def _normalize_section(section_num: int, result: dict, *, id_offset: int) -> dict:
    """Normalize AI response for a full-test section. Rewrites IDs to be globally unique."""
    st = result.get('sectionType') or 'note'
    passage = str(result.get('passage') or '').strip()
    title = str(result.get('title') or f'Section {section_num}').strip()

    out: dict[str, Any] = {
        'sectionNum': section_num,
        'sectionType': st,
        'title': title,
        'passage': passage,
        'scenario': str(result.get('scenario') or '').strip(),
    }

    if section_num == 1:
        out['form_intro'] = result.get('form_intro') or 'Complete the form.'
        out['form_content'] = result.get('form_content') or ''
        questions = result.get('questions') if isinstance(result.get('questions'), list) else []
        normalized = []
        for idx in range(LISTENING_FULL_QUESTIONS_PER_SECTION):
            item = questions[idx] if idx < len(questions) and isinstance(questions[idx], dict) else {}
            normalized.append({
                'id': id_offset + idx + 1,
                'answers': _norm_answers(item.get('answers')) or [''],
                'explanation': str(item.get('explanation') or '').strip() or '请结合音频原词判断.',
            })
        out['questions'] = normalized

    elif section_num == 2:
        subsections = result.get('subsections') if isinstance(result.get('subsections'), list) else []
        norm_subs = []
        # sub 1: MCQ (5 questions, ids 1-5 relative → offset+1..offset+5)
        mcq_sub = next((s for s in subsections if isinstance(s, dict) and s.get('type') == 'multiple_choice'), {})
        mcq_qs = mcq_sub.get('questions') if isinstance(mcq_sub.get('questions'), list) else []
        mcq_norm = []
        for idx in range(5):
            item = mcq_qs[idx] if idx < len(mcq_qs) and isinstance(mcq_qs[idx], dict) else {}
            options_list = item.get('options')
            if isinstance(options_list, list) and options_list:
                correct_text = options_list[0]
                shuffled = list(options_list)
                random.shuffle(shuffled)
                letters = ['A', 'B', 'C', 'D']
                options_dict = {}
                correct_letter = 'A'
                for oi, opt_text in enumerate(shuffled[:4]):
                    options_dict[letters[oi]] = opt_text
                    if opt_text == correct_text:
                        correct_letter = letters[oi]
                item_out = {
                    'id': id_offset + idx + 1,
                    'question': str(item.get('question') or '').strip() or f'MCQ {idx + 1}',
                    'options': options_dict,
                    'answer': correct_letter,
                    'explanation': str(item.get('explanation') or '').strip() or '',
                }
            else:
                item_out = {
                    'id': id_offset + idx + 1,
                    'question': f'MCQ {idx + 1}',
                    'options': {k: f'Option {k}' for k in 'ABCD'},
                    'answer': 'A',
                    'explanation': '',
                }
            mcq_norm.append(item_out)
        norm_subs.append({
            'type': 'multiple_choice',
            'instructions': mcq_sub.get('instructions') or 'Questions 1-5: Choose A, B, C or D.',
            'startId': id_offset + 1,
            'endId': id_offset + 5,
            'questions': mcq_norm,
        })

        # sub 2: MAP (5 questions, ids 6-10 relative → offset+6..offset+10)
        map_sub = next((s for s in subsections if isinstance(s, dict) and s.get('type') == 'map'), {})
        map_data = map_sub.get('map') if isinstance(map_sub.get('map'), dict) else {}
        landmarks = map_data.get('landmarks') if isinstance(map_data.get('landmarks'), list) else []
        mw = map_data.get('width', 600)
        mh = map_data.get('height', 400)
        for lm in landmarks:
            lm['x'] = max(30, min(mw - 30, lm.get('x', 300)))
            lm['y'] = max(30, min(mh - 30, lm.get('y', 200)))
        map_qs = map_sub.get('questions') if isinstance(map_sub.get('questions'), list) else []
        map_norm = []
        options = map_sub.get('options') if isinstance(map_sub.get('options'), list) else []
        letters_available = [str(opt).strip()[:1].upper() for opt in options if str(opt).strip()][:8] or ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for idx in range(5):
            item = map_qs[idx] if idx < len(map_qs) and isinstance(map_qs[idx], dict) else {}
            map_norm.append({
                'id': id_offset + 6 + idx,
                'answer': _norm_letter(item.get('answer'), letters_available, letters_available[0]),
                'explanation': str(item.get('explanation') or '').strip() or '',
            })
        norm_subs.append({
            'type': 'map',
            'instructions': map_sub.get('instructions') or 'Questions 6-10: Label the map.',
            'startId': id_offset + 6,
            'endId': id_offset + 10,
            'options': options,
            'map': {**map_data, 'landmarks': landmarks},
            'questions': map_norm,
        })

        out['subsections'] = norm_subs
        out['questions'] = [q for sub in norm_subs for q in sub['questions']]

    elif section_num == 3:
        subsections = result.get('subsections') if isinstance(result.get('subsections'), list) else []
        norm_subs = []
        # MCQ 1-5
        mcq_sub = next((s for s in subsections if isinstance(s, dict) and s.get('type') == 'multiple_choice'), {})
        mcq_qs = mcq_sub.get('questions') if isinstance(mcq_sub.get('questions'), list) else []
        mcq_norm = []
        for idx in range(5):
            item = mcq_qs[idx] if idx < len(mcq_qs) and isinstance(mcq_qs[idx], dict) else {}
            options_list = item.get('options')
            if isinstance(options_list, list) and options_list:
                correct_text = options_list[0]
                shuffled = list(options_list)
                random.shuffle(shuffled)
                letters = ['A', 'B', 'C', 'D']
                options_dict = {}
                correct_letter = 'A'
                for oi, opt_text in enumerate(shuffled[:4]):
                    options_dict[letters[oi]] = opt_text
                    if opt_text == correct_text:
                        correct_letter = letters[oi]
                mcq_norm.append({
                    'id': id_offset + idx + 1,
                    'question': str(item.get('question') or '').strip() or f'MCQ {idx + 1}',
                    'options': options_dict,
                    'answer': correct_letter,
                    'explanation': str(item.get('explanation') or '').strip() or '',
                })
            else:
                mcq_norm.append({
                    'id': id_offset + idx + 1,
                    'question': f'MCQ {idx + 1}',
                    'options': {k: f'Option {k}' for k in 'ABCD'},
                    'answer': 'A',
                    'explanation': '',
                })
        norm_subs.append({
            'type': 'multiple_choice',
            'instructions': mcq_sub.get('instructions') or 'Questions 1-5: Choose A, B, C or D.',
            'startId': id_offset + 1,
            'endId': id_offset + 5,
            'questions': mcq_norm,
        })

        # Matching 6-10
        match_sub = next((s for s in subsections if isinstance(s, dict) and s.get('type') == 'matching'), {})
        bank = match_sub.get('options_bank') if isinstance(match_sub.get('options_bank'), dict) else {}
        letters_available = [k.upper() for k in bank.keys()] or ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        match_qs = match_sub.get('questions') if isinstance(match_sub.get('questions'), list) else []
        match_norm = []
        for idx in range(5):
            item = match_qs[idx] if idx < len(match_qs) and isinstance(match_qs[idx], dict) else {}
            match_norm.append({
                'id': id_offset + 6 + idx,
                'question': str(item.get('question') or '').strip() or f'Item {idx + 1}',
                'answer': _norm_letter(item.get('answer'), letters_available, letters_available[0]),
                'explanation': str(item.get('explanation') or '').strip() or '',
            })
        norm_subs.append({
            'type': 'matching',
            'instructions': match_sub.get('instructions') or 'Questions 6-10: Match to A-G.',
            'startId': id_offset + 6,
            'endId': id_offset + 10,
            'options_bank': bank,
            'questions': match_norm,
        })

        out['subsections'] = norm_subs
        out['questions'] = [q for sub in norm_subs for q in sub['questions']]

    elif section_num == 4:
        out['note_intro'] = result.get('note_intro') or 'Complete the notes.'
        out['note_content'] = result.get('note_content') or ''
        questions = result.get('questions') if isinstance(result.get('questions'), list) else []
        normalized = []
        for idx in range(LISTENING_FULL_QUESTIONS_PER_SECTION):
            item = questions[idx] if idx < len(questions) and isinstance(questions[idx], dict) else {}
            normalized.append({
                'id': id_offset + idx + 1,
                'answers': _norm_answers(item.get('answers')) or [''],
                'explanation': str(item.get('explanation') or '').strip() or '请结合音频原词判断.',
            })
        out['questions'] = normalized

    return out


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_listening_full(request):
    """POST /api/listening/full — 生成综合套题.

    默认 4 Section 全部生成; 可通过下列参数生成单段:
      - sectionNum: 1|2|3|4  仅生成指定 Section
    响应总是走 `sections` 数组 (单段时长度=1), 前端一致处理.
    """
    try:
        limit = check_rate_limit(request.user.id, 'listening_full', max_calls=3, window=180)
        if limit:
            return limit

        data = request.data
        difficulty = str(data.get('difficulty', '7.0'))
        absurd_mode = str(data.get('absurdMode', 'false')).lower() == 'true'
        # 允许分别指定每段的场景; 未指定则随机
        scenario_map = {
            1: str(data.get('scenarioS1') or 'random').strip().lower(),
            2: str(data.get('scenarioS2') or 'random').strip().lower(),
            3: str(data.get('scenarioS3') or 'random').strip().lower(),
            4: str(data.get('scenarioS4') or 'random').strip().lower(),
        }
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        # ── 单段 override ──
        raw_sn = data.get('sectionNum')
        try:
            target_section = int(raw_sn) if raw_sn is not None else None
        except (TypeError, ValueError):
            target_section = None
        if target_section is not None and target_section not in (1, 2, 3, 4):
            target_section = None

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        section_nums = [target_section] if target_section is not None else list(range(1, LISTENING_FULL_SECTION_COUNT + 1))

        print(f'[Listening] 🎯 async FULL band={difficulty} sections={section_nums} scenarios={scenario_map}', flush=True)

        prompts: list[tuple[int, str, str]] = []
        for n in section_nums:
            p, resolved = _build_section_prompt(
                section_num=n,
                difficulty=difficulty,
                scenario_key=scenario_map[n],
                tone_instruction=tone_instruction,
            )
            prompts.append((n, p, resolved))

        is_single = len(prompts) == 1
        subtype = f'full_s{target_section}' if is_single else 'full'
        title_suffix = f' - Section {target_section}' if is_single else ''
        title = f'IELTS Listening Full Test{title_suffix}'
        user_id = request.user.id
        provider_snapshot = provider
        prompts_snapshot = list(prompts)
        section_nums_snapshot = list(section_nums)
        placeholder = f'🎧 综合听力生成中... ({title_suffix.strip(" -") or "全套"})'

        def _generator(_row):
            sections_out: list[dict] = []

            def _run(num: int, prompt: str):
                r = call_ai_api(
                    prompt,
                    provider=provider_snapshot,
                    user_id=user_id,
                    singleflight_scope=f'listening_full:{num}',
                )
                return num, r

            if len(prompts_snapshot) == 1:
                num, prompt = prompts_snapshot[0][0], prompts_snapshot[0][1]
                _n, r = _run(num, prompt)
                id_offset = (num - 1) * LISTENING_FULL_QUESTIONS_PER_SECTION
                sections_out.append(_normalize_section(num, r, id_offset=id_offset))
            else:
                results_by_num: dict[int, dict] = {}
                with ThreadPoolExecutor(max_workers=len(prompts_snapshot)) as pool:
                    futures = [pool.submit(_run, num, p) for (num, p, _) in prompts_snapshot]
                    for fut in as_completed(futures):
                        n, r = fut.result()
                        results_by_num[n] = r
                for n in section_nums_snapshot:
                    id_offset = (n - 1) * LISTENING_FULL_QUESTIONS_PER_SECTION
                    sections_out.append(_normalize_section(n, results_by_num[n], id_offset=id_offset))

            payload: dict[str, Any] = {
                'type': 'full',
                'title': title,
                'singleSection': is_single,
                'sections': sections_out,
            }
            return title, payload

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_LISTENING,
            subtype=subtype,
            placeholder_title=placeholder,
            generator=_generator,
        )
        return JsonResponse({
            'aiQuestionId': row.id,
            'status': row.status,
            'title': row.title,
        }, status=202)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ── 元数据端点 ────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listening_meta(request):
    """GET /api/listening/meta — 返回题型清单和场景池."""
    types_out = []
    for qt, (_tmpl, n_speakers, length_desc, needs_wl) in LISTENING_QUESTION_TYPES_V2.items():
        types_out.append({
            'key': qt,
            'speakers': n_speakers,
            'lengthDesc': length_desc,
            'needsWordLimit': needs_wl,
            'legacy': qt in _LEGACY_TYPES,
        })
    scenarios_out = {}
    for section_key, pool in LISTENING_SCENARIO_POOL.items():
        scenarios_out[section_key] = [{'key': k, 'name': v} for k, v in pool.items()]
    return Response({
        'questionTypes': types_out,
        'scenarios': scenarios_out,
        'difficulties': ['6.0', '6.5', '7.0', '7.5', '8.0', '8.5'],
        'fullMode': {
            'sectionCount': LISTENING_FULL_SECTION_COUNT,
            'questionsPerSection': LISTENING_FULL_QUESTIONS_PER_SECTION,
        },
    })


# ══════════════════════════════════════════════════════════════════════
# ── 音频生成 (保留原实现) ────────────────────────────
# ══════════════════════════════════════════════════════════════════════

@api_view(['POST'])
def generate_listening_audio(request):
    """POST /api/listening/audio - 生成 Edge-TTS 的 mp3 文件.

    音频按 md5(voice + speak_text) 落盘到 media/listening_audio/{hash}.mp3;
    同样文本 + 同样声音的后续请求直接从磁盘读回, 不再走 edge-tts.
    """
    try:
        text = request.data.get('text', '')

        def markdown_to_tts_text(value: str) -> str:
            raw = html.unescape(str(value or ''))
            if not raw:
                return ''
            out = raw.replace('\r\n', '\n').replace('\r', '\n')
            out = re.sub(r'^\s*```[^\n]*\n?', '', out, flags=re.MULTILINE)
            out = out.replace('```', '')
            out = re.sub(r'!\[([^\]]*)\]\([^\)]*\)', r'\1', out)
            out = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', out)
            out = re.sub(r'^\s{0,3}#{1,6}\s*', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s{0,3}>\s?', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*[-*+]\s+', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*\d+\.\s+', '', out, flags=re.MULTILINE)
            out = re.sub(r'\*\*([^*]+)\*\*', r'\1', out)
            out = re.sub(r'__([^_]+)__', r'\1', out)
            out = re.sub(r'\*([^*]+)\*', r'\1', out)
            out = re.sub(r'_([^_]+)_', r'\1', out)
            out = re.sub(r'~~([^~]+)~~', r'\1', out)
            out = re.sub(r'`([^`]*)`', r'\1', out)
            out = re.sub(r'<[^>]+>', ' ', out)
            out = re.sub(r'https?://\S+', ' ', out)
            # v2: strip speaker labels so TTS doesn't read them aloud.
            # Covers: [SPEAKER_A]  Speaker A:  Speaker 1:  A:  (single-letter at line start)
            out = re.sub(r'\[SPEAKER[_\s]*[A-Z]\]\s*', '', out, flags=re.IGNORECASE)
            out = re.sub(r'\bSpeaker\s+[A-Z]\s*[:.-]\s*', '', out, flags=re.IGNORECASE)
            out = re.sub(r'\bSpeaker\s+\d+\s*[:.-]\s*', '', out, flags=re.IGNORECASE)
            # Line-leading single-letter speaker markers: "A:", "B:", "C:" at start of a line
            out = re.sub(r'(?m)^\s*[A-Z]\s*:\s+', '', out)
            # "Tutor:", "Student A:", "Interviewer:" — role labels
            out = re.sub(r'(?m)^\s*(Tutor|Student\s*[A-Z]?|Interviewer|Interviewee|Examiner|Host|Guest|Presenter|Man|Woman|Lecturer|Professor|Customer|Agent|Staff|Assistant)\s*[:.-]\s+', '', out, flags=re.IGNORECASE)
            out = re.sub(r'[ \t]+', ' ', out)
            out = re.sub(r'\n{3,}', '\n\n', out)
            return out.strip()

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        speak_text = markdown_to_tts_text(text)
        if not speak_text:
            speak_text = str(text).strip()

        voice = request.data.get('voice') or "en-GB-SoniaNeural"

        cache_key = hashlib.md5(f'{voice}|{speak_text}'.encode('utf-8')).hexdigest()
        rel_path = f'{LISTENING_AUDIO_SUBDIR}/{cache_key}.mp3'
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)

        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            with open(abs_path, 'rb') as f:
                resp = HttpResponse(f.read(), content_type='audio/mpeg')
            resp['X-Audio-Cache'] = 'HIT'
            return resp

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=os.path.dirname(abs_path)) as tmp:
            temp_path = tmp.name

        try:
            subprocess.run(
                ['edge-tts', '--voice', voice, '--text', speak_text, '--write-media', temp_path],
                check=True,
            )
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError('edge-tts produced empty output')
            os.replace(temp_path, abs_path)

            with open(abs_path, 'rb') as f:
                resp = HttpResponse(f.read(), content_type='audio/mpeg')
            resp['X-Audio-Cache'] = 'MISS'
            return resp
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _clean_answer_value(answer: Any) -> str:
    """Legacy helper kept for backward compatibility (used nowhere else in this module)."""
    if isinstance(answer, dict):
        answer = answer.get('answer', answer.get('value', str(answer)))
    answer = str(answer).strip()
    answer = answer.strip('()[]{}')
    for separator in ['/', ',', ';', ' or ', ' OR ', ' | ']:
        if separator in answer:
            answer = answer.split(separator)[0].strip()
            break
    answer = answer.rstrip('.,;:!?')
    return answer.strip()
