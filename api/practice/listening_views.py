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

# 前端在 fetchAudioForPassage 里给 passage 前加的引导语；后端预热音频时必须
# 用完全一致的拼接方式，才能让缓存 hash 命中，用户首次打开题目零等待。
LISTENING_AUDIO_INTRO = 'The IELTS listening test is about to begin. Please listen carefully.'
LISTENING_AUDIO_DEFAULT_VOICE = 'en-GB-SoniaNeural'


def _markdown_to_tts_text(value: str) -> str:
    """把 markdown 富文本清成纯 TTS 文本（供 hash 和 edge-tts 用）。

    与 generate_listening_audio 里的内嵌函数保持完全一致 —— 后者会调这个模块
    级实现，避免双份逻辑漂移导致 hash 不一致。
    """
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
    out = re.sub(r'\[SPEAKER[_\s]*[A-Z]\]\s*', '', out, flags=re.IGNORECASE)
    out = re.sub(r'\bSpeaker\s+[A-Z]\s*[:.-]\s*', '', out, flags=re.IGNORECASE)
    out = re.sub(r'\bSpeaker\s+\d+\s*[:.-]\s*', '', out, flags=re.IGNORECASE)
    out = re.sub(r'(?m)^\s*[A-Z]\s*:\s+', '', out)
    out = re.sub(
        r'(?m)^\s*(Tutor|Student\s*[A-Z]?|Interviewer|Interviewee|Examiner|Host|Guest|Presenter|Man|Woman|Lecturer|Professor|Customer|Agent|Staff|Assistant)\s*[:.-]\s+',
        '',
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r'[ \t]+', ' ', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


def _listening_audio_cache_path(voice: str, speak_text: str) -> str:
    cache_key = hashlib.md5(f'{voice}|{speak_text}'.encode('utf-8')).hexdigest()
    rel_path = f'{LISTENING_AUDIO_SUBDIR}/{cache_key}.mp3'
    return os.path.join(settings.MEDIA_ROOT, rel_path)


def ensure_listening_audio_cached(passage: str, voice: str = LISTENING_AUDIO_DEFAULT_VOICE) -> str | None:
    """确保给定 passage 对应的 mp3 已经落盘；返回绝对路径 (miss 时新生成)。

    daemon 在 AI 出题后立即调用一次，把首次访问的 TTS 等待时间从 ~15s 降到 0。
    与前端 fetchAudioForPassage 走的拼接方式一致：intro + '\\n\\n\\n\\n' + stripMarkers(passage)。
    """
    if not passage:
        return None
    raw_text = f'{LISTENING_AUDIO_INTRO}\n\n\n\n{passage}'
    speak_text = _markdown_to_tts_text(raw_text) or str(raw_text).strip()
    if not speak_text:
        return None
    abs_path = _listening_audio_cache_path(voice, speak_text)
    if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
        return abs_path
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=os.path.dirname(abs_path)) as tmp:
            tmp_path = tmp.name
        subprocess.run(
            ['edge-tts', '--voice', voice, '--text', speak_text, '--write-media', tmp_path],
            check=True,
        )
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError('edge-tts produced empty output')
        os.replace(tmp_path, abs_path)
        return abs_path
    except Exception as exc:  # noqa: BLE001 — pre-warm should never fail the AI generation
        print(f'[Listening] audio pre-warm failed: {exc}', flush=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


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


_LISTENING_SUBTYPE_ALIASES = {
    'mcq': 'multiple_choice',
    'multiplechoice': 'multiple_choice',
    'multiple-choice': 'multiple_choice',
    'multiple choice': 'multiple_choice',
    'match': 'matching',
    'matching': 'matching',
    'map_labelling': 'map',
    'maplabel': 'map',
    'maplabelling': 'map',
}


def _canonical_subtype(raw: Any) -> str:
    s = str(raw or '').strip().lower()
    if not s:
        return ''
    if s in _LISTENING_SUBTYPE_ALIASES:
        return _LISTENING_SUBTYPE_ALIASES[s]
    compact = s.replace(' ', '').replace('-', '').replace('_', '')
    return _LISTENING_SUBTYPE_ALIASES.get(compact, s)


def _pick_subsection(subs: list, want_type: str) -> dict:
    """按 canonical subtype 找 subsection，找不到就返回空 dict。"""
    for s in subs:
        if isinstance(s, dict) and _canonical_subtype(s.get('type')) == want_type:
            return s
    return {}


def _extract_questions(container: dict) -> list:
    """优先从 container['questions'] 取；空的话回退到 container['payload']['questions']。"""
    qs = container.get('questions')
    if isinstance(qs, list) and qs:
        return qs
    payload = container.get('payload') if isinstance(container.get('payload'), dict) else {}
    qs2 = payload.get('questions')
    return qs2 if isinstance(qs2, list) else []


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
                # Random pick only from the DETAILED subtype keys, not the
                # legacy short aliases (indoor/outdoor/street) — they point to
                # the same content and would just skew the distribution.
                _detailed_keys = [k for k in MAP_SUBTYPES if k not in ('indoor', 'outdoor', 'street')]
                subtype_key = random.choice(_detailed_keys)
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
                user_id=user_id,
            )
            title = str(result.get('title') or '').strip() or '听力练习'
            # 预热音频：题目一生成完就把 mp3 落盘，用户首次点开题目直接从缓存返回。
            passage = str(result.get('passage') or '').strip()
            if passage:
                ensure_listening_audio_cached(passage)
            payload = {k: v for k, v in result.items() if k != 'atConsumed'}
            if custom_description:
                payload['description'] = custom_description
            return title, payload

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_LISTENING,
            subtype=practice_type,
            placeholder_title=placeholder_title,
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


def _post_process_listening_single(
    result: dict,
    *,
    practice_type: str,
    resolved_scenario: str,
    user_id: int | None = None,
) -> None:
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
            # New paradigm: enforce 10 letter landmarks A-J + strip questionId.
            _enforce_map_letter_landmarks(map_data)
            # Options must be exactly A-J (frontend grid header).
            result['options'] = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
            # Sanitize passage: neutralise 'building A' / 'block C' etc.
            if isinstance(result.get('passage'), str):
                result['passage'] = _sanitize_map_passage(result['passage'])

            # Force map image via FLUX.2-pro regardless of the user's chosen text model.
            # rel_path is a media-relative key (frontend prepends VITE_MEDIA_BASE via mediaUrl()).
            rel_path, _at = _generate_listening_map_image(
                map_data if isinstance(map_data, dict) else {},
                result.get('options') or [],
                user_id,
            )
            if rel_path:
                if isinstance(map_data, dict):
                    map_data['imagePath'] = rel_path
                    map_data['imageModel'] = 'FLUX.2-pro'
                    result['map'] = map_data
                # Also surface at the top level so _cleanup_question_files can
                # find it without walking the nested structure.
                result['mapImagePath'] = rel_path

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


_SECTION_TYPE_BY_NUM = {1: 'form', 2: 'mixed', 3: 'mixed', 4: 'note'}


# Regex: catches the common "letter leaks" — words like `building A`, `block C`,
# `letter D`, `labelled E`, `marked F`. Replacement neutralises the letter.
_LETTER_LEAK_RE = re.compile(
    r"\b(building|block|letter|labelled|labeled|marked|point|location)\s+([A-J])\b",
    re.IGNORECASE,
)


def _sanitize_map_passage(passage: str) -> str:
    """AI sometimes ignores 'never mention letter labels' rule. Strip leaked
    references so the listener isn't handed the answer verbatim. Best-effort —
    doesn't try to rewrite grammar, just removes the letter token.
    """
    if not passage:
        return passage
    return _LETTER_LEAK_RE.sub(lambda m: f"{m.group(1)} [—]", passage)


def _enforce_map_letter_landmarks(map_data: dict) -> None:
    """Guarantee EXACTLY 10 letter landmarks A-J exist (each letter appears
    exactly once). If AI omitted letters, fill them in on a fallback grid;
    if AI duplicated a letter, keep only the FIRST occurrence and drop the
    rest. Non-letter (orientation feature) landmarks pass through unchanged.
    Also strip any lingering 'questionId' fields left over from legacy prompts.
    """
    if not isinstance(map_data, dict):
        return
    landmarks = map_data.get('landmarks')
    if not isinstance(landmarks, list):
        landmarks = []
        map_data['landmarks'] = landmarks

    kept: list[dict] = []
    seen_letters: set[str] = set()
    for lm in landmarks:
        if not isinstance(lm, dict):
            continue
        lm.pop('questionId', None)  # strip legacy
        label = str(lm.get('label') or '').strip()
        upper = label.upper()
        # Single-letter A-J landmark: dedupe (first-write-wins)
        if len(upper) == 1 and 'A' <= upper <= 'J':
            if upper in seen_letters:
                continue  # drop the duplicate
            lm['label'] = upper  # normalise to uppercase
            seen_letters.add(upper)
            kept.append(lm)
        else:
            # Orientation feature or any non-A..J label — keep as-is
            kept.append(lm)

    # Fill in whichever letters were missing entirely
    grid_positions = {
        'A': (100, 180), 'B': (200, 180), 'C': (300, 180), 'D': (400, 180), 'E': (500, 180),
        'F': (100, 280), 'G': (200, 280), 'H': (300, 280), 'I': (400, 280), 'J': (500, 280),
    }
    for letter in 'ABCDEFGHIJ':
        if letter not in seen_letters:
            x, y = grid_positions[letter]
            kept.append({
                'id': letter,
                'label': letter,
                'x': x, 'y': y,
                'shape': 'rect', 'w': 60, 'h': 45,
            })

    map_data['landmarks'] = kept


def _generate_listening_map_image(
    map_data: dict,
    options: list,
    user_id: int | None,
    *,
    question_id_offset: int = 0,
) -> tuple[str | None, int]:
    """Force map questions through FLUX.2-pro regardless of the user's chosen text model.

    Returns (rel_path, at_cost) — rel_path is the media-relative key
    (e.g. ``maps/2/abc.png``), NOT an absolute URL. Same convention as
    avatars / bg_image: the frontend `mediaUrl(rel_path)` prepends the
    env-driven `VITE_MEDIA_BASE`, so dev / prod paths stay unified.
    On any failure returns ``(None, 0)`` so listening generation still
    succeeds and the frontend falls back to the landmark-based SVG.

    :param question_id_offset: shift applied to landmark questionIds so the map
        image labels match the globally-numbered dropdowns (Section 2 map
        subsection uses offset 15 → local 1-5 becomes 16-20).
    """
    import uuid as _uuid

    from api.core.ai_client import AIClient as _AIClient

    if not isinstance(map_data, dict):
        return None, 0

    place_name = str(map_data.get('name') or 'a place').strip() or 'a place'
    landmarks = map_data.get('landmarks') if isinstance(map_data.get('landmarks'), list) else []

    # New paradigm (reference: real IELTS floor plan):
    #   - Each building is labelled with a SINGLE letter (A-J) — no names, no red markers.
    #   - Extra orientation features (Reception / Main Road / River / Access Road)
    #     may appear with descriptive labels; those are context, not answer options.
    letter_labels = []
    context_labels = []
    for lm in landmarks:
        if not isinstance(lm, dict):
            continue
        label = str(lm.get('label') or '').strip()
        if not label:
            continue
        if len(label) == 1 and label.isalpha() and label.isupper():
            letter_labels.append(label)
        else:
            context_labels.append(label)
    letter_labels = sorted(set(letter_labels))[:10]
    context_labels = context_labels[:6]

    image_prompt = (
        f"Clean IELTS listening exam floor plan / map of {place_name}. "
        f"Top-down architectural drawing style, thin black outlines on white background, "
        f"minimalist, exam-friendly, no perspective, no compass rose, no photo-realism, "
        f"no shading, no colour fills. "
        f"Draw {len(letter_labels) or 10} rectangular buildings arranged in a coherent layout, "
        f"each labelled with a SINGLE large bold uppercase letter in the centre of the building "
        f"(letters used: {', '.join(letter_labels) or 'A, B, C, D, E, F, G, H, I, J'}). "
        f"NO other text or names inside the buildings — ONLY the single letter. "
        f"Add orientation context around the buildings: {', '.join(context_labels) or 'Reception, Main Road'}. "
        f"Include a few connecting corridors or paths as thin lines. "
        f"ABSOLUTELY NO red circles, NO numbered markers, NO coloured dots — the map is unmarked. "
        f"Layout should be clearly readable at a glance."
    )

    print(f'[Listening Map Image] 🎨 start user={user_id} place={place_name!r} letters={letter_labels}', flush=True)
    try:
        image_client = _AIClient()
        png_bytes, at_cost = image_client.generate_image(
            prompt=image_prompt,
            size='1024x1024',
            user_id=user_id,
        )
    except Exception as e:
        import traceback
        print(f'[Listening Map Image] ❌ FLUX call failed: {e}\n{traceback.format_exc()}', flush=True)
        return None, 0

    rel_dir = os.path.join('maps', str(user_id or 0))
    abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    file_id = _uuid.uuid4().hex
    rel_path = os.path.join(rel_dir, f'{file_id}.png').replace('\\', '/')
    abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    try:
        with open(abs_path, 'wb') as f:
            f.write(png_bytes)
    except OSError as e:
        print(f'[Listening Map Image] save failed: {e}', flush=True)
        return None, int(at_cost or 0)

    print(f'[Listening Map Image] ✅ done user={user_id} path={rel_path} at_cost={at_cost}', flush=True)
    return rel_path, int(at_cost or 0)


def _normalize_section(
    section_num: int,
    result: dict,
    *,
    id_offset: int,
    user_id: int | None = None,
) -> dict:
    """Normalize AI response for a full-test section. Rewrites IDs to be globally unique.

    sectionType is derived from section_num rather than trusting the AI response —
    if the model omits or fabricates the field the frontend would route the data
    into the wrong renderer (e.g. note-renderer on a mixed section = blank UI).
    """
    st = _SECTION_TYPE_BY_NUM.get(section_num, 'note')
    passage = str(result.get('passage') or '').strip()
    # Only Section 2 hosts the map subsection — that's where letter leaks bite.
    # For other sections the sub is a no-op (regex hits nothing).
    if section_num == 2:
        passage = _sanitize_map_passage(passage)
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
        questions = _extract_questions(result)
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
        mcq_sub = _pick_subsection(subsections, 'multiple_choice')
        mcq_qs = _extract_questions(mcq_sub)
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
        map_sub = _pick_subsection(subsections, 'map')
        map_data = map_sub.get('map') if isinstance(map_sub.get('map'), dict) else {}
        landmarks = map_data.get('landmarks') if isinstance(map_data.get('landmarks'), list) else []
        mw = map_data.get('width', 600)
        mh = map_data.get('height', 400)
        for lm in landmarks:
            lm['x'] = max(30, min(mw - 30, lm.get('x', 300)))
            lm['y'] = max(30, min(mh - 30, lm.get('y', 200)))

        # New paradigm: enforce all 10 letter landmarks A-J are present, strip
        # legacy questionId, and neutralise any letter leaks the AI slipped
        # into the passage (e.g. "next to building A").
        _enforce_map_letter_landmarks(map_data)
        landmarks = map_data.get('landmarks', landmarks)

        map_qs = _extract_questions(map_sub)
        map_norm = []
        # New paradigm: options must be exactly the 10 letters A-J. Ignore
        # anything the AI actually returned — the FE grid header must match
        # the enforced landmark letters (also A-J).
        options = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        letters_available = list(options)
        for idx in range(5):
            item = map_qs[idx] if idx < len(map_qs) and isinstance(map_qs[idx], dict) else {}
            map_norm.append({
                'id': id_offset + 6 + idx,
                'question': str(item.get('question') or '').strip(),
                'answer': _norm_letter(item.get('answer'), letters_available, letters_available[0]),
                'explanation': str(item.get('explanation') or '').strip() or '',
            })
        # Force map image via FLUX.2-pro. No offset needed — landmarks are
        # letter-labelled (A-J) and FLUX renders those letters directly.
        final_map = {**map_data, 'landmarks': landmarks}
        map_image_path, _at = _generate_listening_map_image(
            final_map,
            options,
            user_id,
        )
        if map_image_path:
            final_map['imagePath'] = map_image_path
            final_map['imageModel'] = 'FLUX.2-pro'
            out['mapImagePath'] = map_image_path
        norm_subs.append({
            'type': 'map',
            'instructions': map_sub.get('instructions') or 'Questions 6-10: Label the map.',
            'startId': id_offset + 6,
            'endId': id_offset + 10,
            'options': options,
            'map': final_map,
            'questions': map_norm,
        })

        out['subsections'] = norm_subs
        out['questions'] = [q for sub in norm_subs for q in sub['questions']]

    elif section_num == 3:
        subsections = result.get('subsections') if isinstance(result.get('subsections'), list) else []
        norm_subs = []
        # MCQ 1-5
        mcq_sub = _pick_subsection(subsections, 'multiple_choice')
        mcq_qs = _extract_questions(mcq_sub)
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
        match_sub = _pick_subsection(subsections, 'matching')
        bank = match_sub.get('options_bank') if isinstance(match_sub.get('options_bank'), dict) else {}
        letters_available = [k.upper() for k in bank.keys()] or ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        match_qs = _extract_questions(match_sub)
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
        questions = _extract_questions(result)
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
        custom_title = (data.get('customName') or data.get('customTitle') or '').strip()
        custom_description = (data.get('customDescription') or data.get('description') or '').strip()
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
                sections_out.append(_normalize_section(num, r, id_offset=id_offset, user_id=user_id))
            else:
                results_by_num: dict[int, dict] = {}
                with ThreadPoolExecutor(max_workers=len(prompts_snapshot)) as pool:
                    futures = [pool.submit(_run, num, p) for (num, p, _) in prompts_snapshot]
                    for fut in as_completed(futures):
                        n, r = fut.result()
                        results_by_num[n] = r
                for n in section_nums_snapshot:
                    id_offset = (n - 1) * LISTENING_FULL_QUESTIONS_PER_SECTION
                    sections_out.append(_normalize_section(n, results_by_num[n], id_offset=id_offset, user_id=user_id))

            payload: dict[str, Any] = {
                'type': 'full',
                'title': title,
                'singleSection': is_single,
                'sections': sections_out,
            }
            # Surface any map image path at the top level so the delete-cleanup
            # hook (which only reads content_json.mapImagePath) finds it.
            for _sec in sections_out:
                _mp = _sec.get('mapImagePath')
                if _mp:
                    payload['mapImagePath'] = _mp
                    break
            if custom_description:
                payload['description'] = custom_description
            # 预热每个 section 的音频；用户切 Section 时也秒开。
            # 并行合成 —— edge-tts 是子进程各自跑不共享全局锁，4 个 section
            # 并行大概能把 ~60s 串行压缩到 ~15s (取决于最慢那段)。
            passages_to_warm = [
                str(sec.get('passage') or '').strip()
                for sec in sections_out
            ]
            passages_to_warm = [p for p in passages_to_warm if p]
            if len(passages_to_warm) == 1:
                ensure_listening_audio_cached(passages_to_warm[0])
            elif passages_to_warm:
                with ThreadPoolExecutor(max_workers=len(passages_to_warm)) as pool:
                    list(pool.map(ensure_listening_audio_cached, passages_to_warm))
            return title, payload

        row = spawn_ai_generation(
            user=request.user,
            skill=AIQuestion.SKILL_LISTENING,
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
    """POST /api/listening/audio - 从磁盘/缓存返回 mp3；miss 时现合成。

    daemon 端在题目生成后已经预热了同一文本的音频，正常调用是 100% HIT。
    仍保留 miss 分支作为回退（旧题、缓存被清等场景）。
    """
    try:
        text = request.data.get('text', '')
        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        voice = request.data.get('voice') or LISTENING_AUDIO_DEFAULT_VOICE
        speak_text = _markdown_to_tts_text(text) or str(text).strip()
        abs_path = _listening_audio_cache_path(voice, speak_text)

        was_hit = os.path.exists(abs_path) and os.path.getsize(abs_path) > 0
        if not was_hit:
            # 与 daemon 预热走完全相同的合成路径（用 raw text 让 helper 自己做 intro 拼接兼容），
            # 但这里 text 已经是完整前端拼接过的了，所以直接落到 abs_path。
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
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

        with open(abs_path, 'rb') as f:
            resp = HttpResponse(f.read(), content_type='audio/mpeg')
        resp['X-Audio-Cache'] = 'HIT' if was_hit else 'MISS'
        return resp
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
