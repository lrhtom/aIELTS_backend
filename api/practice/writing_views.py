import json
import hashlib
import base64
import re
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.ai_client import AIClient
from api.core.rate_limit import check_rate_limit

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

WORD_COUNT_GUARD_TEMPLATE = """Authoritative backend metrics (MUST be trusted):
- Essay_Word_Count: %d
- Minimum_Required_Words: %d
- Meets_Minimum_Words: %s

Strict rule:
- You MUST use these backend metrics when discussing essay length.
- If Meets_Minimum_Words is YES, do NOT claim the essay is below the minimum word requirement.
- If Meets_Minimum_Words is NO, clearly state that the essay is below the minimum requirement.
"""

TASK1_IMAGE_MAX_BYTES = 5 * 1024 * 1024
TASK1_IMAGE_DATA_URL_PATTERN = re.compile(r'^data:image/(png|jpeg|jpg|webp);base64,', re.IGNORECASE)


def _build_singleflight_scope(scope_prefix: str, payload) -> str:
    try:
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_text = str(payload)
    digest = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:16]
    return f"{scope_prefix}:{digest}"


def _count_words(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def _provider_supports_task1_image(provider: str) -> bool:
    return str(provider or '').strip().lower().startswith('gpt5')


def _validate_task1_image_data_url(raw_data_url: str) -> str:
    data_url = (raw_data_url or '').strip()
    if not data_url:
        return ''

    if not TASK1_IMAGE_DATA_URL_PATTERN.match(data_url):
        raise ValueError('Task 1 image must be PNG/JPG/JPEG/WEBP in data URL format.')

    try:
        _, b64_body = data_url.split(',', 1)
        decoded = base64.b64decode(b64_body, validate=True)
    except Exception as parse_err:
        raise ValueError('Task 1 image payload is invalid base64 data.') from parse_err

    if len(decoded) > TASK1_IMAGE_MAX_BYTES:
        raise ValueError('Task 1 image is too large. Maximum size is 5MB.')

    return data_url

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_writing(request):
    """
    POST /api/writing/generate：接收前端传来的文本和提供商，返回雅思写作批改结果 JSON。
    """
    try:
        limit_resp = check_rate_limit(request.user.id, 'writing_evaluate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        essay_text = request.data.get('text', '').strip()

        if not essay_text:
            return JsonResponse({'error': 'Essay text is required.'}, status=400)

        # Word count is calculated by backend from the submitted essay text
        # and sent to frontend, instead of trusting model output.
        essay_word_count = _count_words(essay_text)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        user_prompt_context = request.data.get('prompt', '').strip()
        task_type = request.data.get('task_type', 'task2')
        ui_lang = request.data.get('lang', 'en')
        raw_task1_image_data_url = request.data.get('task1_image_data_url', '')
        task1_image_data_url = ''
        if task_type == 'task1' and raw_task1_image_data_url and _provider_supports_task1_image(provider):
            task1_image_data_url = _validate_task1_image_data_url(raw_task1_image_data_url)

        task_extra = TASK1_EXTRA if task_type == 'task1' else TASK2_EXTRA
        min_required_words = 150 if task_type == 'task1' else 250
        meets_minimum_words = essay_word_count >= min_required_words
        word_count_guard = WORD_COUNT_GUARD_TEMPLATE % (
            essay_word_count,
            min_required_words,
            'YES' if meets_minimum_words else 'NO',
        )
        lang_instruction = (
            'Write the "Feedback" field in Simplified Chinese (中文).'
            if ui_lang == 'zh'
            else 'Write the "Feedback" field in English.'
        )
        image_instruction = (
            '\nTask 1 reference image is attached in this request. '
            'You MUST use the image as source evidence when assessing Task Achievement and accuracy.\n'
            if task1_image_data_url
            else ''
        )

        if user_prompt_context:
            context_injection = f'''The user was responding to the following specific IELTS task prompt:
"""
{user_prompt_context}
"""
Please evaluate the Task Response score with strict attention to whether the essay directly answers ALL parts of this specific prompt.

'''
            essay_block = f'{task_extra}{image_instruction}\n{word_count_guard}\n{context_injection}User Essay:\n"""\n{essay_text}\n"""'
        else:
            essay_block = f'{task_extra}{image_instruction}\n{word_count_guard}\nUser Essay:\n"""\n{essay_text}\n"""'

        prompt = WRITING_CORRECTION_PROMPT % (essay_block, lang_instruction)
        task1_image_digest = hashlib.sha256(task1_image_data_url.encode('utf-8')).hexdigest()[:16] if task1_image_data_url else ''
        correction_scope = _build_singleflight_scope(
            'writing_correction_generate',
            {
                'essay_text': essay_text,
                'task_type': task_type,
                'prompt': user_prompt_context,
                'lang': ui_lang,
                'task1_image_digest': task1_image_digest,
            },
        )
        
        client = AIClient(provider=provider)

        if task1_image_data_url:
            messages = [{
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': prompt},
                    {'type': 'input_image', 'image_url': task1_image_data_url},
                ],
            }]
        else:
            messages = [{"role": "user", "content": prompt}]
        
        # 强制 AIClient 期待 JSON 返回；其内部会用贪婪正则抽取 {} 后再 json.loads()。
        result_data, at_cost = client.generate(
            messages,
            expect_json=True,
            user_id=request.user.id,
            singleflight_scope=correction_scope,
        )

        # Force backend-calculated word_count to avoid AI-side counting drift.
        result_data.pop('word_count', None)
        result_data.pop('Word_Count', None)
        result_data.pop('wordCount', None)
        result_data['word_count'] = essay_word_count
        result_data['minimum_required_words'] = min_required_words
        result_data['minimum_word_requirement_met'] = meets_minimum_words
        result_data['atConsumed'] = at_cost
        return JsonResponse(result_data)

    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Failed to parse AI response: {str(e)}'}, status=500)
    except ValueError as ve:
        # 当 expect_json=True 且解析彻底失败时，AIClient 会抛出 ValueError。
        return JsonResponse({'error': str(ve)}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


