import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .utils import call_ai_api


READING_PROMPT_TEMPLATE = """
You are an IELTS examiner.
Create an IELTS Academic reading passage (Band 7.0 - 7.5 difficulty) using the following vocabulary words: {words}. You MUST use ALL of them!

IMPORTANT RULES:
Whenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else.

Then, create exactly 5 multiple-choice questions (A, B, C, D) based on the passage.

You MUST output your response strictly in the following JSON format without any markdown wrappers or extra text:
{{
    "title": "Passage Title",
    "passage": "Full reading passage text here...",
    "questions": [
        {{
            "id": 1,
            "question": "Question text here",
            "options": {{
                "A": "Option A text",
                "B": "Option B text",
                "C": "Option C text",
                "D": "Option D text"
            }},
            "answer": "A",
            "explanation": "Detailed explanation of why A is correct and others are wrong. explanation使用中文题解"
        }}
    ]
}}
"""


@csrf_exempt
@require_POST
def generate_reading(request):
    """POST /api/reading/generate — 接收词汇列表，返回 AI 生成的阅读材料"""
    try:
        body = json.loads(request.body)
        words = body.get('words', [])

        if not words:
            return JsonResponse({'error': 'No words provided'}, status=400)

        word_str = ', '.join(words)
        prompt = READING_PROMPT_TEMPLATE.format(words=word_str)

        result = call_ai_api(prompt)
        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
