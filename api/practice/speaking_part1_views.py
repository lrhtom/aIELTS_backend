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


def _clamp_multiplier(value):
    try:
        multiplier = float(value)
    except (TypeError, ValueError):
        return None
    if multiplier < 0.0 or multiplier > 1.0:
        return None
    return max(0.0, min(1.0, multiplier))

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
                "The test strictly consists of exactly 8 questions.\n"
                "Question 1: Greetings and identity check (e.g., 'Hello. Could you tell me your full name, please?').\n"
                "Questions 2-4: Choose ONE common topic (e.g., Hometown, Work/Study, Hobbies) and ask 3 related questions.\n"
                "Questions 5-8: Choose a SECOND DIFFERENT common topic and ask 4 related questions.\n"
                "CRITICAL: You MUST output a JSON object containing an array of exactly 8 items under the key 'questions'. "
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

        if not question or not user_answer:
            return JsonResponse({'error': 'Question and user_answer are required'}, status=400)

        # Time and Word length weight assessment
        tw = 1.0
        if duration_seconds <= 0:
            tw = 0.0
        elif duration_seconds <= 10:
            tw = (duration_seconds / 10.0) * 0.5
        elif duration_seconds <= 30:
            tw = 0.5 + ((duration_seconds - 10.0) / 20.0) * 0.5
        elif duration_seconds <= 35:
            tw = 1.0
        elif duration_seconds <= 100:
            tw = 1.0 - ((duration_seconds - 35.0) / 65.0) * 0.5
        else:
            tw = 0.5

        ww = 1.0
        if word_count <= 0:
            ww = 0.0
        elif word_count <= 80:
            ww = word_count / 80.0
        elif word_count <= 100:
            ww = 1.0
        elif word_count <= 200:
            ww = 1.0 - ((word_count - 100.0) / 100.0) * 0.5
        else:
            ww = 0.5

        local_multiplier = tw * ww
        local_percent_multiplier = int(local_multiplier * 100)
        local_length_feedback = f"({int(duration_seconds)}s, {word_count} words). Your algorithmic length penalty multiplier is {local_percent_multiplier}%."

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
                "   - E (Extension/Example): Did the candidate provide specific details or an example? Score 1-9.\n\n"
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
                "  \"corrected_text\": \"(A fully corrected or upgraded version of the user's answer)\"\n"
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

        def clamp_score(val):
            try:
                s = float(val)
                return max(0.0, min(9.0, s))
            except:
                return 0.0

        try:
            parsed = json.loads(json_str)
            
            raw_scores = [
                clamp_score(parsed.get('grammar_score', 0)),
                clamp_score(parsed.get('vocab_score', 0)),
                clamp_score(parsed.get('relevance_score', 0)),
                clamp_score(parsed.get('are_a_score', 0)),
                clamp_score(parsed.get('are_r_score', 0)),
                clamp_score(parsed.get('are_e_score', 0)),
            ]

            duration_raw = parsed.get('duration_score')
            word_raw = parsed.get('word_count_score')
            duration_score = clamp_score(duration_raw) if duration_raw is not None else 0.0
            word_count_score = clamp_score(word_raw) if word_raw is not None else 0.0

            final_multiplier = local_multiplier
            length_score_source = 'local'
            ai_multiplier = _clamp_multiplier(parsed.get('length_multiplier'))
            if ai_multiplier is not None:
                final_multiplier = ai_multiplier
                length_score_source = 'ai'
            elif duration_raw is not None and word_raw is not None:
                final_multiplier = max(0.0, min(1.0, (duration_score / 9.0) * (word_count_score / 9.0)))
                length_score_source = 'ai_derived'

            length_feedback = str(parsed.get('length_feedback', '')).strip() or local_length_feedback

            average_raw = sum(raw_scores) / 6.0 if raw_scores else 0.0
            weighted_total_score = clamp_score(average_raw * final_multiplier)

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


