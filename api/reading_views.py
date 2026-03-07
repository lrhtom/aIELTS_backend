import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .utils import call_ai_api

READING_PROMPT_TEMPLATE = """
You are an IELTS examiner.
Create an IELTS Academic reading passage (Band {difficulty} difficulty) {vocab_instruction}

{marker_rule}

Then, create exactly 5 multiple-choice questions (A, B, C, D) based on the passage. Assign the correct answer for each question completely at random. Please ensure true randomness, which means it is entirely acceptable and expected if the distribution is uneven, and one option (A, B, C, or D) might not appear as the correct answer at all

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
        difficulty = body.get('difficulty', '7.0')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        if not words:
            vocab_instruction = ""
            marker_rule = ""
        else:
            word_str = ', '.join(words)
            vocab_instruction = f"using the following vocabulary words: {word_str}. You MUST use ALL of them!"
            marker_rule = "IMPORTANT RULES:\\nWhenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else."

        prompt = READING_PROMPT_TEMPLATE.format(vocab_instruction=vocab_instruction, difficulty=difficulty, marker_rule=marker_rule)

        result = call_ai_api(prompt, provider=provider)
        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
