import json
import re
import hashlib
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


def _clamp_score(value) -> float:
    """Clamp to 0-9 range and round to nearest 0.5."""
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


# ── Part 1 length assessment: additive penalty + floor score ────────────
PART1_FLOOR_SCORE = 3.0
PART1_MAX_DEDUCTION = 2.0


def _calculate_part1_length_penalty(duration_seconds: float, word_count: int):
    """
    Calculate a length-based penalty (0.0 = perfect, 1.0 = worst) for Part 1.
    Optimal: 15-45s duration, 25-80 words.
    Returns (penalty, feedback_string).
    """
    # ── Time fitness (0.0 = perfect, 1.0 = worst) ──
    if duration_seconds <= 0:
        time_penalty = 1.0
    elif duration_seconds < 15:
        time_penalty = max(0.0, 1.0 - duration_seconds / 15.0)  # 0s→1.0, 15s→0.0
    elif duration_seconds <= 45:
        time_penalty = 0.0  # Optimal window
    elif duration_seconds <= 90:
        time_penalty = min(1.0, (duration_seconds - 45.0) / 45.0)  # 45s→0.0, 90s→1.0
    else:
        time_penalty = 1.0

    # ── Word fitness (0.0 = perfect, 1.0 = worst) ──
    if word_count <= 0:
        word_penalty = 1.0
    elif word_count < 25:
        word_penalty = max(0.0, 1.0 - word_count / 25.0)
    elif word_count <= 80:
        word_penalty = 0.0  # Optimal window
    elif word_count <= 150:
        word_penalty = min(1.0, (word_count - 80.0) / 70.0)
    else:
        word_penalty = 1.0

    # Combined: average of both penalties
    combined_penalty = (time_penalty + word_penalty) / 2.0
    deduction = combined_penalty * PART1_MAX_DEDUCTION

    feedback = (
        f"({int(duration_seconds)}s, {word_count} words). "
        f"Length deduction: -{deduction:.1f} pts (max -{PART1_MAX_DEDUCTION})."
    )
    return combined_penalty, feedback

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part1_questions(request):
    try:
        limit_resp = check_rate_limit(request.user.id, 'generate_part1', max_calls=20, window=60)
        if limit_resp: return limit_resp

        system_instruction = {
            "role": "system",
            "content": (
                "You are an IELTS examiner generating a Part 1 speaking test for a candidate.\n"
                "The test strictly consists of exactly 10 questions covering 3 distinct topics.\n"
                "Question 1: Greetings and identity check (e.g., 'Hello. Could you tell me your full name, please?').\n"
                "Questions 2-4: Choose ONE common topic (Topic A, e.g., Hometown, Work/Study, Hobbies) and ask 3 related questions.\n"
                "Questions 5-7: Choose a SECOND DIFFERENT common topic (Topic B) and ask 3 related questions.\n"
                "Questions 8-10: Choose a THIRD DIFFERENT common topic (Topic C) and ask 3 related questions.\n"
                "CRITICAL: You MUST output a JSON object containing an array of exactly 10 items under the key 'questions'. "
                "Each item must be a JSON object with two keys: 'topic' and 'question'. "
                "Each 'question' value must be valid Markdown (GFM). "
                "{\n"
                "  \"questions\": [\n"
                "    {\"topic\": \"Intro\", \"question\": \"Good morning. Could you tell me your full name, please?\"},\n"
                "    {\"topic\": \"Work/Study\", \"question\": \"Do you work or are you a student?\"}\n"
                "  ]\n"
                "}\n"
                "Return RAW JSON only. Do not use markdown blocks."
            )
        }

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)
        
        ai_text, at_cost = client.generate(
            [system_instruction],
            expect_json=False,
            temperature=0.7,
            user_id=request.user.id,
            singleflight_scope='speaking_part1_generate',
        )
        
        json_match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = ai_text

        try:
            parsed = json.loads(json_str)
            return JsonResponse({'questions': parsed.get('questions', []), 'atConsumed': at_cost})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Failed to parse AI response.', 'raw': ai_text}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_part1_answer(request):
    try:
        limit_resp = check_rate_limit(request.user.id, 'eval_part1', max_calls=30, window=60)
        if limit_resp: return limit_resp

        question = request.data.get('question', '')
        user_answer = request.data.get('user_answer', '')
        duration_seconds = float(request.data.get('duration_seconds', 0) or 0)
        word_count = len(user_answer.split())
        next_plan = request.data.get('next_question_plan')

        if not question or not user_answer:
            return JsonResponse({'error': 'Question and user_answer are required'}, status=400)

        # Additive length penalty (replaces old multiplicative tw * ww)
        local_penalty, local_length_feedback = _calculate_part1_length_penalty(duration_seconds, word_count)

        dynamic_q_instruction = ""
        if next_plan and isinstance(next_plan, dict):
            n_topic = next_plan.get('topic', '')
            n_quest = next_plan.get('question', '')
            dynamic_q_instruction = (
                f"\n4. Dynamic Next Question: The planned next question is:\n"
                f"   - Topic: \"{n_topic}\"\n"
                f"   - Base Question: \"{n_quest}\"\n"
                "   Adapt this planned next question to make it a natural, conversational follow-up to the candidate's answer. "
                "If the topic changes, include a natural transition (e.g., 'Now let's talk about something else.'). "
                "Return this as 'next_question_dynamic'.\n"
            )

        system_instruction = {
            "role": "system",
            "content": (
                "You are an expert IELTS examiner evaluating a Part 1 answer.\n"
                f"Question asked: \"{question}\"\n"
                f"Candidate's answer: \"{user_answer}\"\n\n"
                "Evaluate the answer based on the following criteria:\n"
                "1. Grammar & Vocabulary (0-9 scale)\n"
                "2. Relevance (0-9 scale)\n"
                "3. The A.R.E. Method:\n"
                "   - A (Answer): Did the first sentence directly answer the question? Score 1-9.\n"
                "   - R (Reason): Did the candidate provide a reason or explanation? Score 1-9.\n"
                "   - E (Extension/Example): Did the candidate provide specific details or an example? Score 1-9.\n"
                f"{dynamic_q_instruction}\n"
                f"Timing signal: duration_seconds={int(duration_seconds)}, word_count={word_count}.\n"
                "Return a raw JSON object string ONLY, with these precise keys:\n"
                "{\n"
                "  \"grammar_score\": 6.5,\n"
                "  \"vocab_score\": 7.0,\n"
                "  \"relevance_score\": 8.0,\n"
                "  \"are_a_score\": 9.0,\n"
                "  \"are_r_score\": 7.5,\n"
                "  \"are_e_score\": 6.0,\n"
                "  \"duration_score\": 6.5,\n"
                "  \"word_count_score\": 6.5,\n"
                "  \"length_multiplier\": 0.75,\n"
                "  \"length_feedback\": \"(Brief comment on timing and length quality)\",\n"
                "  \"are_feedback\": \"(Brief feedback focusing purely on how well they used A, R, and E)\",\n"
                "  \"corrected_text\": \"(A fully corrected or upgraded version of the user's answer)\",\n"
                "  \"next_question_dynamic\": \"(The dynamically adapted next question, if requested. Or empty string)\"\n"
                "}"
            )
        }

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)
        eval_scope = _build_singleflight_scope(
            'speaking_part1_evaluate',
            {
                'question': question,
                'user_answer': user_answer,
                'duration_seconds': duration_seconds,
            },
        )
        
        ai_text, at_cost = client.generate(
            [system_instruction],
            expect_json=False,
            temperature=0.5,
            user_id=request.user.id,
            singleflight_scope=eval_scope,
        )
        
        json_match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        json_str = json_match.group(0) if json_match else ai_text

        try:
            parsed = json.loads(json_str)
            
            raw_scores = [
                _clamp_score(parsed.get('grammar_score', 0)),
                _clamp_score(parsed.get('vocab_score', 0)),
                _clamp_score(parsed.get('relevance_score', 0)),
                _clamp_score(parsed.get('are_a_score', 0)),
                _clamp_score(parsed.get('are_r_score', 0)),
                _clamp_score(parsed.get('are_e_score', 0)),
            ]

            duration_raw = parsed.get('duration_score')
            word_raw = parsed.get('word_count_score')
            duration_score = _clamp_score(duration_raw) if duration_raw is not None else 0.0
            word_count_score = _clamp_score(word_raw) if word_raw is not None else 0.0

            # Determine final penalty: prefer AI's assessment, fallback to local
            final_penalty = local_penalty
            length_score_source = 'local'
            ai_multiplier = _clamp_multiplier(parsed.get('length_multiplier'))
            if ai_multiplier is not None:
                # Convert AI multiplier (1.0=best) to penalty (0.0=best)
                final_penalty = 1.0 - ai_multiplier
                length_score_source = 'ai'
            elif duration_raw is not None and word_raw is not None:
                ai_derived_mult = max(0.0, min(1.0, (duration_score / 9.0) * (word_count_score / 9.0)))
                final_penalty = 1.0 - ai_derived_mult
                length_score_source = 'ai_derived'

            length_feedback = str(parsed.get('length_feedback', '')).strip() or local_length_feedback

            average_raw = sum(raw_scores) / 6.0 if raw_scores else 0.0
            deduction = final_penalty * PART1_MAX_DEDUCTION
            weighted_total_score = _clamp_score(max(PART1_FLOOR_SCORE, average_raw - deduction))
            # Keep final_multiplier for backwards compatibility in response
            final_multiplier = max(0.0, 1.0 - final_penalty)

            response_data = {
                'grammar_score': raw_scores[0],
                'vocab_score': raw_scores[1],
                'relevance_score': raw_scores[2],
                'are_a_score': raw_scores[3],
                'are_r_score': raw_scores[4],
                'are_e_score': raw_scores[5],
                'are_feedback': parsed.get('are_feedback', ''),
                'corrected_text': parsed.get('corrected_text', ''),
                'weighted_total_score': weighted_total_score,
                'final_multiplier': final_multiplier,
                'length_feedback': length_feedback,
                'duration_score': duration_score,
                'word_count_score': word_count_score,
                'length_score_source': length_score_source,
                'word_count': word_count,
                'duration_seconds': int(duration_seconds),
                'next_question_dynamic': parsed.get('next_question_dynamic', ''),
                'atConsumed': at_cost
            }
            return JsonResponse(response_data)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Failed to parse AI evaluation.', 'raw': ai_text}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_part1_summary(request):
    try:
        limit_resp = check_rate_limit(request.user.id, 'eval_part1_sum', max_calls=10, window=60)
        if limit_resp: return limit_resp

        history = request.data.get('history', [])
        # History format expected: [{"question": "...", "answer": "...", "scores": {...}}]
        
        if not history:
            return JsonResponse({'error': 'History is required'}, status=400)

        history_text = ""
        for i, item in enumerate(history):
            history_text += f"\n--- Q{i+1}: {item.get('question')} ---\nUser: {item.get('answer')}\nScores: ARE({item.get('scores', {}).get('are_a_score')}, {item.get('scores', {}).get('are_r_score')}, {item.get('scores', {}).get('are_e_score')})\n"

        system_instruction = {
            "role": "system",
            "content": (
                "You are an IELTS examiner. Provide a final summary of the candidate's Part 1 speaking performance.\n"
                f"Here is the dialogue history and their scores (ARE stands for Answer, Reason, Extension):\n{history_text}\n\n"
                "Analyze their strengths, weaknesses, and provide a constructive summary.\n"
                "Return a JSON object containing:\n"
                "{\n"
                "  \"overall_band_estimate\": 6.5,\n"
                "  \"strengths\": \"(string)\",\n"
                "  \"weaknesses\": \"(string)\",\n"
                "  \"are_analysis\": \"(string) General comment on their use of Answer, Reason, and Extension\",\n"
                "  \"advice\": \"(string: Actionable tips for improvement)\"\n"
                "}"
            )
        }

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)
        summary_scope = _build_singleflight_scope('speaking_part1_summary', {'history': history})
        
        ai_text, at_cost = client.generate(
            [system_instruction],
            expect_json=False,
            temperature=0.7,
            user_id=request.user.id,
            singleflight_scope=summary_scope,
        )
        
        json_match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        json_str = json_match.group(0) if json_match else ai_text

        try:
            parsed = json.loads(json_str)
            parsed['atConsumed'] = at_cost
            return JsonResponse(parsed)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Failed to parse AI summary.', 'raw': ai_text}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


