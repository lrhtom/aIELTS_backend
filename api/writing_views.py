import json
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .ai_client import AIClient
from api.rate_limit import check_rate_limit

WRITING_CORRECTION_PROMPT = """
You are an expert IELTS Writing Examiner.
Please evaluate the following IELTS essay (either Task 1 or Task 2) submitted by a user.
You MUST assess the essay exactly according to the official IELTS writing band descriptors (0-9).

Your evaluation MUST be returned as a raw JSON object containing EXACTLY these keys:
{
  "Task_Response": (float) Score for Task Response / Task Achievement,
  "Coherence_Cohesion": (float) Score for Coherence and Cohesion,
  "Lexical_Resource": (float) Score for Lexical Resource,
  "Grammatical_Range": (float) Score for Grammatical Range and Accuracy,
  "Overall_Band": (float) The overall band score (average of the 4 criteria, rounded to nearest 0.5),
  "Feedback": (string) Detailed examiner-style commentary covering all 4 criteria with specific examples from the essay,
  "Model_Essay": (string) A complete rewritten version of the user's essay targeting Band 8+. Keep the same topic, position and main arguments as the original. Fix ALL grammatical errors, significantly upgrade vocabulary range and accuracy, improve coherence, cohesion and task achievement. Write naturally and fluently as an expert writer would. Use \\n\\n to separate paragraphs.
}

%s

LANGUAGE INSTRUCTION: %s
The "Model_Essay" must always be written in English (it is a model English essay).

CRITICAL: Return ONLY valid JSON. Do NOT wrap in ```json or any markdown. The Model_Essay value must be a single JSON string with \\n\\n for paragraph breaks.
"""

TASK1_EXTRA = """This is an IELTS Task 1 (Academic) response. The minimum requirement is 150 words.
Evaluate "Task_Response" as Task Achievement: does the essay accurately describe and compare the KEY features and trends from the data/diagram, with no irrelevant information and no missing overview?
The essay should NOT include personal opinions. Focus on accurate data description, clear overview, and appropriate data selection.
"""

TASK2_EXTRA = """This is an IELTS Task 2 essay. The minimum requirement is 250 words.
Evaluate "Task_Response" as Task Response: does the essay fully address ALL parts of the question, present a clear position, and develop ideas with relevant, extended support?
"""

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_writing(request):
    """
    POST /api/writing/generate — 接收前端传来的文本和提供商，返回雅思写作批改结果 JSON
    """
    try:
        limit_resp = check_rate_limit(request.user.id, 'writing_evaluate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        essay_text = request.data.get('text', '').strip()

        if not essay_text:
            return JsonResponse({'error': 'Essay text is required.'}, status=400)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        user_prompt_context = request.data.get('prompt', '').strip()
        task_type = request.data.get('task_type', 'task2')
        ui_lang = request.data.get('lang', 'en')
        task_extra = TASK1_EXTRA if task_type == 'task1' else TASK2_EXTRA
        lang_instruction = (
            'Write the "Feedback" field in Simplified Chinese (中文).'
            if ui_lang == 'zh'
            else 'Write the "Feedback" field in English.'
        )

        if user_prompt_context:
            context_injection = f'''The user was responding to the following specific IELTS task prompt:
"""
{user_prompt_context}
"""
Please evaluate the Task Response score with strict attention to whether the essay directly answers ALL parts of this specific prompt.

'''
            essay_block = f'{task_extra}\n{context_injection}User Essay:\n"""\n{essay_text}\n"""'
        else:
            essay_block = f'{task_extra}\nUser Essay:\n"""\n{essay_text}\n"""'

        prompt = WRITING_CORRECTION_PROMPT % (essay_block, lang_instruction)
        
        client = AIClient(provider=provider)
        
        # 强制 AIClient 期待 JSON 返回，它内部会用完全贪婪正则抽取 {} 并 json.loads()
        result_data, at_cost = client.generate([{"role": "user", "content": prompt}], expect_json=True, user_id=request.user.id)
        
        result_data['atConsumed'] = at_cost
        return JsonResponse(result_data)

    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Failed to parse AI response: {str(e)}'}, status=500)
    except ValueError as ve:
        # 当 expect_json=True 且解析彻底失败时 AIClient 抛出
        return JsonResponse({'error': str(ve)}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
