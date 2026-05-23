import hashlib
import json
import re

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.core.rate_limit import check_rate_limit

from api.core.ai_client import AIClient
from api.skills.speaking.part23 import (
    skill_speaking_part2_generate,
    skill_speaking_part3_generate,
    skill_speaking_part23_evaluate_system,
    skill_speaking_part23_evaluate_user_msg,
    skill_speaking_part23_summary_system,
    skill_speaking_part23_summary_user_msg,
)


def _build_singleflight_scope(scope_prefix: str, payload) -> str:
    try:
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_text = str(payload)
    digest = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:16]
    return f"{scope_prefix}:{digest}"


def _extract_json_payload(raw_text: str):
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    candidate = json_match.group(0) if json_match else raw_text
    return json.loads(candidate)


def _clamp_score(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    score = max(0.0, min(9.0, score))
    return round(score * 2) / 2


def _clamp_multiplier(value):
    try:
        multiplier = float(value)
    except (TypeError, ValueError):
        return None
    if multiplier < 0.0 or multiplier > 1.0:
        return None
    return max(0.0, min(1.0, multiplier))


def _resolve_length_scoring(parsed: dict, local_penalty: float, local_feedback: str):
    """Resolve length scoring: prefer AI's assessment, fallback to local penalty."""
    duration_raw = parsed.get('duration_score')
    word_raw = parsed.get('word_count_score')
    duration_score = _clamp_score(duration_raw) if duration_raw is not None else 0.0
    word_count_score = _clamp_score(word_raw) if word_raw is not None else 0.0

    final_penalty = local_penalty
    length_score_source = 'local'

    ai_multiplier = _clamp_multiplier(parsed.get('length_multiplier'))
    if ai_multiplier is not None:
        final_penalty = 1.0 - ai_multiplier
        length_score_source = 'ai'
    elif duration_raw is not None and word_raw is not None:
        ai_derived_mult = max(0.0, min(1.0, (duration_score / 9.0) * (word_count_score / 9.0)))
        final_penalty = 1.0 - ai_derived_mult
        length_score_source = 'ai_derived'

    length_feedback = str(parsed.get('length_feedback', '')).strip() or local_feedback
    return final_penalty, length_feedback, duration_score, word_count_score, length_score_source


# ── Floor score and max deduction constants ──────────────────────────────
PART2_FLOOR_SCORE = 3.0
PART2_MAX_DEDUCTION = 2.5
PART3_FLOOR_SCORE = 3.0
PART3_MAX_DEDUCTION = 2.0


def _calculate_length_penalty(part_kind: str, duration_seconds: float, word_count: int):
    """
    Calculate a length-based penalty (0.0 = perfect, 1.0 = worst).
    Returns (penalty, feedback_string).
    """
    if part_kind == 'part2':
        # Part 2: optimal 60-120s, 100-250 words
        if duration_seconds <= 0:
            time_penalty = 1.0
        elif duration_seconds < 60:
            time_penalty = max(0.0, 1.0 - duration_seconds / 60.0)
        elif duration_seconds <= 120:
            time_penalty = 0.0
        elif duration_seconds <= 200:
            time_penalty = min(1.0, (duration_seconds - 120.0) / 80.0)
        else:
            time_penalty = 1.0

        if word_count <= 0:
            word_penalty = 1.0
        elif word_count < 100:
            word_penalty = max(0.0, 1.0 - word_count / 100.0)
        elif word_count <= 250:
            word_penalty = 0.0
        elif word_count <= 400:
            word_penalty = min(1.0, (word_count - 250.0) / 150.0)
        else:
            word_penalty = 1.0

        max_deduction = PART2_MAX_DEDUCTION
    else:
        # Part 3: optimal 20-60s, 40-150 words
        if duration_seconds <= 0:
            time_penalty = 1.0
        elif duration_seconds < 20:
            time_penalty = max(0.0, 1.0 - duration_seconds / 20.0)
        elif duration_seconds <= 60:
            time_penalty = 0.0
        elif duration_seconds <= 120:
            time_penalty = min(1.0, (duration_seconds - 60.0) / 60.0)
        else:
            time_penalty = 1.0

        if word_count <= 0:
            word_penalty = 1.0
        elif word_count < 40:
            word_penalty = max(0.0, 1.0 - word_count / 40.0)
        elif word_count <= 150:
            word_penalty = 0.0
        elif word_count <= 280:
            word_penalty = min(1.0, (word_count - 150.0) / 130.0)
        else:
            word_penalty = 1.0

        max_deduction = PART3_MAX_DEDUCTION

    combined_penalty = (time_penalty + word_penalty) / 2.0
    deduction = combined_penalty * max_deduction

    feedback = (
        f"({int(duration_seconds)}s, {word_count} words). "
        f"Length deduction: -{deduction:.1f} pts (max -{max_deduction})."
    )
    return combined_penalty, feedback


def _generate_questions(request, part_kind: str):
    if part_kind == 'part2':
        limit_resp = check_rate_limit(request.user.id, 'generate_part2', max_calls=20, window=60)
        if limit_resp:
            return limit_resp

        system_prompt = {
            'role': 'system',
            'content': skill_speaking_part2_generate(),
        }
        scope = 'speaking_part2_generate'
    else:
        limit_resp = check_rate_limit(request.user.id, 'generate_part3', max_calls=20, window=60)
        if limit_resp:
            return limit_resp

        part2_topic = request.data.get('part2_topic', '')
        topic_instruction = f"The Part 2 topic was: '{part2_topic}'. Generate Part 3 discussion questions that naturally extend and abstract from this topic. " if part2_topic else "All questions should be around one coherent theme. "

        system_prompt = {
            'role': 'system',
            'content': skill_speaking_part3_generate(topic_instruction),
        }
        scope = 'speaking_part3_generate'

    provider = request.headers.get('X-AI-Provider', 'deepseek')
    client = AIClient(provider=provider)

    ai_text, at_cost = client.generate(
        [system_prompt],
        expect_json=False,
        temperature=0.7,
        user_id=request.user.id,
        singleflight_scope=scope,
    )

    try:
        parsed = _extract_json_payload(ai_text)
        questions = parsed.get('questions', []) if isinstance(parsed, dict) else []
        if not isinstance(questions, list):
            questions = []
        normalized = []
        for item in questions:
            if not isinstance(item, dict):
                continue
            topic = str(item.get('topic', '')).strip()
            question = str(item.get('question', '')).strip()
            if not question:
                continue
            normalized.append({'topic': topic or 'General Topic', 'question': question})
        return JsonResponse({'questions': normalized, 'atConsumed': at_cost})
    except Exception:
        return JsonResponse({'error': 'Failed to parse AI response', 'raw': ai_text}, status=500)


def _evaluate_answer(request, part_kind: str):
    if part_kind == 'part2':
        limit_resp = check_rate_limit(request.user.id, 'eval_part2', max_calls=30, window=60)
        label = 'Part 2'
        scope_prefix = 'speaking_part2_evaluate'
    else:
        limit_resp = check_rate_limit(request.user.id, 'eval_part3', max_calls=30, window=60)
        label = 'Part 3'
        scope_prefix = 'speaking_part3_evaluate'

    if limit_resp:
        return limit_resp

    question = str(request.data.get('question', '')).strip()
    user_answer = str(request.data.get('user_answer', '')).strip()
    duration_seconds = float(request.data.get('duration_seconds', 0) or 0)
    word_count = len(user_answer.split())

    if not question or not user_answer:
        return JsonResponse({'error': 'question and user_answer are required'}, status=400)

    local_penalty, local_length_feedback = _calculate_length_penalty(part_kind, duration_seconds, word_count)

    system_instruction = {
        'role': 'system',
        'content': skill_speaking_part23_evaluate_system(label, duration_seconds, word_count),
    }

    provider = request.headers.get('X-AI-Provider', 'deepseek')
    client = AIClient(provider=provider)
    eval_scope = _build_singleflight_scope(
        scope_prefix,
        {
            'question': question,
            'user_answer': user_answer,
            'duration_seconds': duration_seconds,
        },
    )

    ai_text, at_cost = client.generate(
        [
            system_instruction,
            {
                'role': 'user',
                'content': skill_speaking_part23_evaluate_user_msg(
                    question, user_answer, duration_seconds, word_count
                ),
            },
        ],
        expect_json=False,
        temperature=0.5,
        user_id=request.user.id,
        singleflight_scope=eval_scope,
    )

    try:
        parsed = _extract_json_payload(ai_text)
    except Exception:
        return JsonResponse({'error': 'Failed to parse AI evaluation', 'raw': ai_text}, status=500)

    grammar = _clamp_score(parsed.get('grammar_score'))
    vocab = _clamp_score(parsed.get('vocab_score'))
    relevance = _clamp_score(parsed.get('relevance_score'))
    coherence = _clamp_score(parsed.get('coherence_score'))
    depth = _clamp_score(parsed.get('depth_score'))

    (
        final_penalty,
        length_feedback,
        duration_score,
        word_count_score,
        length_score_source,
    ) = _resolve_length_scoring(parsed, local_penalty, local_length_feedback)

    raw_avg = (grammar + vocab + relevance + coherence + depth) / 5.0
    floor_score = PART2_FLOOR_SCORE if part_kind == 'part2' else PART3_FLOOR_SCORE
    max_deduction = PART2_MAX_DEDUCTION if part_kind == 'part2' else PART3_MAX_DEDUCTION
    deduction = final_penalty * max_deduction
    weighted_total = _clamp_score(max(floor_score, raw_avg - deduction))
    # Keep final_multiplier for backwards compatibility
    final_multiplier = max(0.0, 1.0 - final_penalty)

    feedback = str(parsed.get('feedback', '')).strip()
    corrected_text = str(parsed.get('corrected_text', '')).strip()

    return JsonResponse(
        {
            'grammar_score': grammar,
            'vocab_score': vocab,
            'relevance_score': relevance,
            'coherence_score': coherence,
            'depth_score': depth,
            'feedback': feedback,
            'corrected_text': corrected_text,
            'weighted_total_score': weighted_total,
            'final_multiplier': final_multiplier,
            'length_feedback': length_feedback,
            'duration_score': duration_score,
            'word_count_score': word_count_score,
            'length_score_source': length_score_source,
            'word_count': word_count,
            'duration_seconds': int(duration_seconds),
            'atConsumed': at_cost,
        }
    )


def _generate_summary(request, part_kind: str):
    if part_kind == 'part2':
        limit_resp = check_rate_limit(request.user.id, 'eval_part2_sum', max_calls=10, window=60)
        scope_prefix = 'speaking_part2_summary'
        part_label = 'Part 2'
    else:
        limit_resp = check_rate_limit(request.user.id, 'eval_part3_sum', max_calls=10, window=60)
        scope_prefix = 'speaking_part3_summary'
        part_label = 'Part 3'

    if limit_resp:
        return limit_resp

    history = request.data.get('history', [])
    if not isinstance(history, list) or not history:
        return JsonResponse({'error': 'history is required'}, status=400)

    history_text = ''
    for idx, item in enumerate(history):
        if not isinstance(item, dict):
            continue
        q = item.get('question', '')
        a = item.get('answer', '')
        scores = item.get('scores', {}) if isinstance(item.get('scores', {}), dict) else {}
        history_text += (
            f"\n--- Q{idx + 1}: {q} ---\n"
            f"User: {a}\n"
            f"Scores: G({scores.get('grammar_score')}), V({scores.get('vocab_score')}), "
            f"R({scores.get('relevance_score')}), C({scores.get('coherence_score')}), D({scores.get('depth_score')})\n"
        )

    system_instruction = {
        'role': 'system',
        'content': skill_speaking_part23_summary_system(part_label),
    }

    provider = request.headers.get('X-AI-Provider', 'deepseek')
    client = AIClient(provider=provider)
    summary_scope = _build_singleflight_scope(scope_prefix, {'history': history})

    ai_text, at_cost = client.generate(
        [
            system_instruction,
            {
                'role': 'user',
                'content': skill_speaking_part23_summary_user_msg(history_text),
            },
        ],
        expect_json=False,
        temperature=0.7,
        user_id=request.user.id,
        singleflight_scope=summary_scope,
    )

    try:
        parsed = _extract_json_payload(ai_text)
        parsed['atConsumed'] = at_cost
        return JsonResponse(parsed)
    except Exception:
        return JsonResponse({'error': 'Failed to parse AI summary', 'raw': ai_text}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part2_questions(request):
    try:
        return _generate_questions(request, 'part2')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_part2_answer(request):
    try:
        return _evaluate_answer(request, 'part2')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part2_summary(request):
    try:
        return _generate_summary(request, 'part2')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part3_questions(request):
    try:
        return _generate_questions(request, 'part3')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_part3_answer(request):
    try:
        return _evaluate_answer(request, 'part3')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part3_summary(request):
    try:
        return _generate_summary(request, 'part3')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


