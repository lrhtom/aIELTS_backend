import hashlib
import json
import re

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.core.rate_limit import check_rate_limit

from api.core.ai_client import AIClient


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


def _resolve_length_scoring(parsed: dict, local_multiplier: float, local_feedback: str):
    duration_raw = parsed.get('duration_score')
    word_raw = parsed.get('word_count_score')
    duration_score = _clamp_score(duration_raw) if duration_raw is not None else 0.0
    word_count_score = _clamp_score(word_raw) if word_raw is not None else 0.0

    final_multiplier = local_multiplier
    length_score_source = 'local'

    ai_multiplier = _clamp_multiplier(parsed.get('length_multiplier'))
    if ai_multiplier is not None:
        final_multiplier = ai_multiplier
        length_score_source = 'ai'
    elif duration_raw is not None and word_raw is not None:
        # AI multiplier missing/invalid: derive from AI time+word scores.
        final_multiplier = max(0.0, min(1.0, (duration_score / 9.0) * (word_count_score / 9.0)))
        length_score_source = 'ai_derived'

    length_feedback = str(parsed.get('length_feedback', '')).strip() or local_feedback
    return final_multiplier, length_feedback, duration_score, word_count_score, length_score_source


def _calculate_multiplier(part_kind: str, duration_seconds: float, word_count: int):
    if part_kind == 'part2':
        if duration_seconds <= 20:
            time_weight = 0.30
        elif duration_seconds <= 60:
            time_weight = 0.30 + ((duration_seconds - 20.0) / 40.0) * 0.70
        elif duration_seconds <= 140:
            time_weight = 1.0
        elif duration_seconds <= 220:
            time_weight = 1.0 - ((duration_seconds - 140.0) / 80.0) * 0.35
        else:
            time_weight = 0.65

        if word_count <= 30:
            word_weight = 0.25
        elif word_count <= 120:
            word_weight = 0.25 + ((word_count - 30.0) / 90.0) * 0.75
        elif word_count <= 260:
            word_weight = 1.0
        elif word_count <= 420:
            word_weight = 1.0 - ((word_count - 260.0) / 160.0) * 0.35
        else:
            word_weight = 0.65
    else:
        if duration_seconds <= 10:
            time_weight = 0.35
        elif duration_seconds <= 35:
            time_weight = 0.35 + ((duration_seconds - 10.0) / 25.0) * 0.65
        elif duration_seconds <= 95:
            time_weight = 1.0
        elif duration_seconds <= 170:
            time_weight = 1.0 - ((duration_seconds - 95.0) / 75.0) * 0.35
        else:
            time_weight = 0.65

        if word_count <= 20:
            word_weight = 0.30
        elif word_count <= 70:
            word_weight = 0.30 + ((word_count - 20.0) / 50.0) * 0.70
        elif word_count <= 190:
            word_weight = 1.0
        elif word_count <= 300:
            word_weight = 1.0 - ((word_count - 190.0) / 110.0) * 0.35
        else:
            word_weight = 0.65

    multiplier = max(0.0, min(1.0, time_weight * word_weight))
    feedback = (
        f"({int(duration_seconds)}s, {word_count} words). "
        f"Length multiplier: {int(multiplier * 100)}%."
    )
    return multiplier, feedback


def _generate_questions(request, part_kind: str):
    if part_kind == 'part2':
        limit_resp = check_rate_limit(request.user.id, 'generate_part2', max_calls=20, window=60)
        if limit_resp:
            return limit_resp

        system_prompt = {
            'role': 'system',
            'content': (
                'You are an IELTS speaking examiner. Generate a Part 2 practice set. '\
                'Return strict raw JSON only with key "questions". '\
                'questions must be an array of exactly 4 objects. '\
                'Each object must have keys "topic" and "question". '\
                'Q1 must be a cue card with clear speaking points. '\
                'Each "question" value must be valid Markdown (GFM), and Q1 should include bullet points in Markdown. '\
                'Q2-Q4 are follow-up prompts to deepen the same topic. '\
                'Example: {"questions":[{"topic":"...","question":"..."}]}'
            ),
        }
        scope = 'speaking_part2_generate'
    else:
        limit_resp = check_rate_limit(request.user.id, 'generate_part3', max_calls=20, window=60)
        if limit_resp:
            return limit_resp

        system_prompt = {
            'role': 'system',
            'content': (
                'You are an IELTS speaking examiner. Generate a Part 3 discussion set. '\
                'Return strict raw JSON only with key "questions". '\
                'questions must be an array of exactly 6 objects. '\
                'Each object must have keys "topic" and "question". '\
                'Each "question" value must be valid Markdown (GFM). '\
                'Use abstract, society-level discussion style questions with increasing depth. '\
                'All questions should be around one coherent theme. '\
                'Example: {"questions":[{"topic":"...","question":"..."}]}'
            ),
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

    local_multiplier, local_length_feedback = _calculate_multiplier(part_kind, duration_seconds, word_count)

    system_instruction = {
        'role': 'system',
        'content': (
            f'You are an expert IELTS examiner evaluating a {label} answer. '\
            f'Duration seconds: {int(duration_seconds)}. Word count: {word_count}. '\
            'Return raw JSON only with these keys: '\
            '{"grammar_score":6.5,"vocab_score":6.5,"relevance_score":6.5,'
            '"coherence_score":6.5,"depth_score":6.5,'
            '"duration_score":6.5,"word_count_score":6.5,'
            '"length_multiplier":0.75,"length_feedback":"...",'
            '"feedback":"...","corrected_text":"..."}. '\
            'Scoring range: 0-9 with 0.5 step. '\
            'length_multiplier range: 0.0-1.0. '\
            'Prioritize realistic timing/length judgement using provided duration and word count. '\
            'feedback should be concise and actionable.'
        ),
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
                'content': (
                    f'Question:\n{question}\n\n'
                    f'Candidate Answer:\n{user_answer}\n\n'
                    f'Duration seconds: {int(duration_seconds)}\n'
                    f'Word count: {word_count}'
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
        final_multiplier,
        length_feedback,
        duration_score,
        word_count_score,
        length_score_source,
    ) = _resolve_length_scoring(parsed, local_multiplier, local_length_feedback)

    raw_avg = (grammar + vocab + relevance + coherence + depth) / 5.0
    weighted_total = _clamp_score(raw_avg * final_multiplier)

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
        'content': (
            f'You are an IELTS examiner. Provide a final summary for speaking {part_label}. '\
            'Return raw JSON only with keys: '\
            '{"overall_band_estimate":6.5,"strengths":"...","weaknesses":"...",'
            '"analysis":"...","advice":"..."}'
        ),
    }

    provider = request.headers.get('X-AI-Provider', 'deepseek')
    client = AIClient(provider=provider)
    summary_scope = _build_singleflight_scope(scope_prefix, {'history': history})

    ai_text, at_cost = client.generate(
        [
            system_instruction,
            {
                'role': 'user',
                'content': f'History:\n{history_text}',
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


