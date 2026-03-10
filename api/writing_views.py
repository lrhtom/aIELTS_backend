import json
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .ai_client import AIClient

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
%s
\"\"\"

CRITICAL: Return ONLY valid JSON format. Do NOT wrap the JSON in ```json or any other markdown text!
"""

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_writing(request):
    """
    POST /api/writing/generate — 接收前端传来的文本和提供商，返回雅思写作批改结果 JSON
    """
    try:
        essay_text = request.data.get('text', '').strip()
        
        if not essay_text:
            return JsonResponse({'error': 'Essay text is required.'}, status=400)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        
        user_prompt_context = request.data.get('prompt', '').strip()
        
        if user_prompt_context:
            context_injection = f'''
The user was responding to the following specific IELTS task prompt:
"""
{user_prompt_context}
"""
Please evaluate the Task Response score with strict attention to whether the essay directly answers ALL parts of this specific prompt.
'''
            prompt = WRITING_CORRECTION_PROMPT % (context_injection + "\nUser Essay:\n\"\"\"\n" + essay_text)
        else:
            prompt = WRITING_CORRECTION_PROMPT % ("User Essay:\n\"\"\"\n" + essay_text)
        
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
