import random
from typing import Any
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.utils import call_ai_api
from api.core.rate_limit import check_rate_limit

READING_QUESTION_TYPE_MCQ = 'multiple_choice'
READING_QUESTION_TYPE_TRUE_FALSE = 'true_false'
READING_TF_MODE_EASY = 'easy'
READING_TF_MODE_NORMAL = 'normal'
READING_QUESTION_COUNT = 5
MCQ_OPTION_KEYS = ['A', 'B', 'C', 'D']

READING_PROMPT_TEMPLATE = """
You are an IELTS examiner.
Create an IELTS Academic reading passage (Band {difficulty} difficulty) {vocab_instruction}

Tone requirement:
{tone_instruction}

{marker_rule}

{question_instruction}

You MUST output your response strictly in the following JSON format without any markdown wrappers or extra text:
{{
    "title": "Passage Title",
    "passage": "Full reading passage text here...",
    {question_schema}
}}
"""


def _normalize_question_type(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized == READING_QUESTION_TYPE_TRUE_FALSE:
        return READING_QUESTION_TYPE_TRUE_FALSE
    return READING_QUESTION_TYPE_MCQ


def _normalize_tf_mode(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'easy', 'simple'}:
        return READING_TF_MODE_EASY
    return READING_TF_MODE_NORMAL


def _build_tf_options(mode: str) -> dict[str, str]:
    if mode == READING_TF_MODE_EASY:
        return {
            'True': 'The statement agrees with the passage.',
            'False': 'The statement contradicts the passage.',
        }
    return {
        'True': 'The statement agrees with the passage.',
        'False': 'The statement contradicts the passage.',
        'Not Given': 'The passage does not provide enough information.',
    }


def _build_question_instruction(question_type: str, judgement_mode: str) -> tuple[str, str]:
    if question_type == READING_QUESTION_TYPE_TRUE_FALSE:
        options = _build_tf_options(judgement_mode)
        options_text = ', '.join(options.keys())
        question_instruction = (
            f"Then, create exactly {READING_QUESTION_COUNT} judgement questions based on the passage. "
            f"Allowed answers are ONLY: {options_text}. "
            "Make each statement clear and answerable by locating evidence in the passage. "
            "Ensure there is exactly one correct answer for each question."
        )
        question_schema = (
            '"questions": [\n'
            '        {\n'
            '            "id": 1,\n'
            '            "question": "Statement text here",\n'
            '            "options": {\n'
            + ''.join([f'                "{key}": "{val}"{"," if idx < len(options) - 1 else ""}\n' for idx, (key, val) in enumerate(options.items())])
            + '            },\n'
            f'            "answer": "{list(options.keys())[0]}",\n'
            '            "explanation": "Detailed explanation in Chinese (中文题解) with evidence from the passage."\n'
            '        }\n'
            '    ]'
        )
        return question_instruction, question_schema

    question_instruction = (
        f"Then, create exactly {READING_QUESTION_COUNT} multiple-choice questions (A, B, C, D) based on the passage. "
        "Assign the correct answer for each question completely at random. "
        "Please ensure true randomness, which means it is acceptable if one option does not appear as correct at all."
    )
    question_schema = (
        '"questions": [\n'
        '        {\n'
        '            "id": 1,\n'
        '            "question": "Question text here",\n'
        '            "options": {\n'
        '                "A": "Option A text",\n'
        '                "B": "Option B text",\n'
        '                "C": "Option C text",\n'
        '                "D": "Option D text"\n'
        '            },\n'
        '            "answer": "A",\n'
        '            "explanation": "Detailed explanation in Chinese (中文题解) for why the answer is correct."\n'
        '        }\n'
        '    ]'
    )
    return question_instruction, question_schema


def _normalize_mcq_options(raw_options: Any) -> dict[str, str]:
    if not isinstance(raw_options, dict):
        return {key: f'Option {key}' for key in MCQ_OPTION_KEYS}

    normalized: dict[str, str] = {}
    for key in MCQ_OPTION_KEYS:
        value = raw_options.get(key)
        if value is None:
            value = raw_options.get(key.lower())
        if value is None:
            value = raw_options.get(key.upper())
        value_text = str(value or '').strip()
        normalized[key] = value_text or f'Option {key}'
    return normalized


def _normalize_mcq_answer(raw_answer: Any) -> str:
    answer = str(raw_answer or '').strip().upper()
    if answer in MCQ_OPTION_KEYS:
        return answer
    return MCQ_OPTION_KEYS[0]


def _normalize_tf_answer(raw_answer: Any, judgement_mode: str) -> str:
    allowed = ['True', 'False'] if judgement_mode == READING_TF_MODE_EASY else ['True', 'False', 'Not Given']
    answer_text = str(raw_answer or '').strip()

    for item in allowed:
        if answer_text.lower() == item.lower():
            return item

    compact = answer_text.lower().replace(' ', '').replace('_', '').replace('-', '')
    alias_map = {
        'true': 'True',
        't': 'True',
        'false': 'False',
        'f': 'False',
        'notgiven': 'Not Given',
        'ng': 'Not Given',
    }
    normalized = alias_map.get(compact)
    if normalized in allowed:
        return normalized

    return allowed[0]


def _normalize_questions(raw_questions: Any, question_type: str, judgement_mode: str) -> list[dict[str, Any]]:
    source = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict[str, Any]] = []

    for idx in range(READING_QUESTION_COUNT):
        item = source[idx] if idx < len(source) and isinstance(source[idx], dict) else {}

        question_text = str(item.get('question') or '').strip()
        if not question_text:
            if question_type == READING_QUESTION_TYPE_TRUE_FALSE:
                question_text = f'Statement {idx + 1}: judge this statement according to the passage.'
            else:
                question_text = f'According to the passage, which option best answers question {idx + 1}?'

        explanation = str(item.get('explanation') or '').strip()
        if not explanation:
            explanation = '请结合原文定位证据，再判断该题选项。'

        if question_type == READING_QUESTION_TYPE_TRUE_FALSE:
            options = _build_tf_options(judgement_mode)
            answer = _normalize_tf_answer(item.get('answer'), judgement_mode)
        else:
            options = _normalize_mcq_options(item.get('options'))
            answer = _normalize_mcq_answer(item.get('answer'))

        normalized.append({
            'id': idx + 1,
            'question': question_text,
            'options': options,
            'answer': answer,
            'explanation': explanation,
        })

    return normalized

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_reading(request):
    """POST /api/reading/generate：接收词汇列表，返回 AI 生成的阅读材料。"""
    try:
        limit_resp = check_rate_limit(request.user.id, 'reading_generate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        words = request.data.get('words', [])
        difficulty = request.data.get('difficulty', '7.0')
        absurd_mode = str(request.data.get('absurdMode', 'false')).lower() == 'true'
        question_type = _normalize_question_type(
            request.data.get('question_type', request.data.get('questionType', READING_QUESTION_TYPE_MCQ))
        )
        judgement_mode = _normalize_tf_mode(
            request.data.get('judgement_mode', request.data.get('judgementMode', READING_TF_MODE_NORMAL))
        )
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe: no profanity, no sexual content, no harassment."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        if not words:
            vocab_instruction = ""
            marker_rule = ""
        else:
            word_str = ', '.join(words)
            vocab_instruction = f"using the following vocabulary words: {word_str}. You MUST use ALL of them!"
            marker_rule = "IMPORTANT RULES:\\nWhenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else."

        question_instruction, question_schema = _build_question_instruction(question_type, judgement_mode)

        prompt = READING_PROMPT_TEMPLATE.format(
            vocab_instruction=vocab_instruction,
            difficulty=difficulty,
            marker_rule=marker_rule,
            tone_instruction=tone_instruction,
            question_instruction=question_instruction,
            question_schema=question_schema,
        )

        result = call_ai_api(
            prompt,
            provider=provider,
            user_id=request.user.id,
            singleflight_scope='reading_generate',
        )

        title = str(result.get('title') or '').strip() or 'Reading Passage'
        passage = str(result.get('passage') or '').strip()
        if not passage:
            return JsonResponse({'error': 'AI 返回内容不完整（缺少 passage）'}, status=500)

        payload = {
            'title': title,
            'passage': passage,
            'questionType': question_type,
            'judgementMode': judgement_mode if question_type == READING_QUESTION_TYPE_TRUE_FALSE else None,
            'questions': _normalize_questions(result.get('questions'), question_type, judgement_mode),
            'atConsumed': result.get('atConsumed', 0),
        }

        return JsonResponse(payload)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


