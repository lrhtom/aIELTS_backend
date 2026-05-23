import json
import hashlib
import base64
import re
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.ai_client import AIClient
from api.core.rate_limit import check_rate_limit
from api.skills.writing.correction import (
    SKILL_WRITING_CORRECTION as WRITING_CORRECTION_PROMPT,
    SKILL_WRITING_TASK1_EXTRA as TASK1_EXTRA,
    SKILL_WRITING_TASK2_EXTRA as TASK2_EXTRA,
    SKILL_WRITING_WORD_COUNT_GUARD as WORD_COUNT_GUARD_TEMPLATE,
    SKILL_WRITING_WORD_FREQUENCY as WORD_FREQUENCY_TEMPLATE,
)
from api.skills.writing.chat import skill_writing_chat_system



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


def _word_frequencies(text: str, top_n: int = 10) -> dict:
    """Count per-word frequency for Lexical Resource assessment.

    Splits identically to _count_words, then strips leading/trailing
    punctuation from each token and lowercases for clean grouping.
    Internal apostrophes and hyphens are preserved (don't, well-known).
    """
    stripped = text.strip()
    if not stripped:
        return {'total_words': 0, 'unique_words': 0, 'top_words': []}

    tokens = stripped.split()
    total_words = len(tokens)

    freq: dict[str, int] = {}
    for t in tokens:
        # strip leading/trailing punctuation but keep internal apostrophes/hyphens
        clean = t.strip(""",.!?;:'"()[]{}“”‘’—…–-/%""")
        if not clean:
            continue
        clean = clean.lower()
        freq[clean] = freq.get(clean, 0) + 1

    # Sort by count desc, then alphabetically for ties
    sorted_freq = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    top_words = sorted_freq[:top_n]

    return {
        'total_words': total_words,
        'unique_words': len(freq),
        'top_words': top_words,
    }


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

        freq_data = _word_frequencies(essay_text, top_n=10)
        lexical_density = (freq_data['unique_words'] / freq_data['total_words'] * 100.0) if freq_data['total_words'] > 0 else 0.0
        top_freq_str = ', '.join(f'{w}({c})' for w, c in freq_data['top_words'])
        word_freq_block = WORD_FREQUENCY_TEMPLATE % (
            freq_data['total_words'],
            freq_data['unique_words'],
            lexical_density,
            len(freq_data['top_words']),
            top_freq_str,
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
            essay_block = f'{task_extra}{image_instruction}\n{word_count_guard}\n{word_freq_block}\n{context_injection}User Essay:\n"""\n{essay_text}\n"""'
        else:
            essay_block = f'{task_extra}{image_instruction}\n{word_count_guard}\n{word_freq_block}\nUser Essay:\n"""\n{essay_text}\n"""'

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
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': task1_image_data_url}},
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def writing_chat(request):
    """
    Writing chat endpoint — multi-turn conversation with AI writing partner.
    Supports JSON body or multipart/form-data with optional file attachments.
    """
    try:
        limit_resp = check_rate_limit(request.user.id, 'writing_chat', max_calls=15, window=60)
        if limit_resp:
            return limit_resp

        # ── Parse request: supports JSON and multipart/form-data ──
        is_multipart = request.content_type and 'multipart' in request.content_type
        if is_multipart:
            messages_raw = request.data.get('messages', '[]')
            messages = json.loads(messages_raw) if isinstance(messages_raw, str) else messages_raw
            uploaded_files = request.FILES.getlist('files') if request.FILES else []
        else:
            messages = request.data.get('messages', [])
            uploaded_files = []

        if not messages:
            return JsonResponse({'error': 'messages required'}, status=400)

        # ── Augment the last user message with uploaded file content ──
        if uploaded_files:
            last_user_msg = None
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    last_user_msg = msg
                    break

            if last_user_msg:
                content_parts = []
                user_text = last_user_msg.get('content', '')
                text_attachments = []

                for f in uploaded_files:
                    if f.size > 5 * 1024 * 1024:
                        continue
                    ct = f.content_type or 'application/octet-stream'
                    if ct.startswith('image/'):
                        img_data = base64.b64encode(f.read()).decode('utf-8')
                        content_parts.append({
                            'type': 'image_url',
                            'image_url': {'url': f'data:{ct};base64,{img_data}', 'detail': 'auto'}
                        })
                    else:
                        try:
                            text_content = f.read().decode('utf-8', errors='replace')[:3000]
                            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
                            text_attachments.append(f'[Attached file: {f.name}]\n```{ext}\n{text_content}\n```')
                        except Exception:
                            text_attachments.append(f'[Attached file: {f.name}]')

                if text_attachments:
                    user_text = '\n\n'.join(text_attachments) + '\n\n' + user_text

                if content_parts:
                    content_parts.insert(0, {'type': 'text', 'text': user_text})
                    last_user_msg['content'] = content_parts
                else:
                    last_user_msg['content'] = user_text

        sf_scope = _build_singleflight_scope('writing_chat', {'messages': messages})

        system_instruction = {
            "role": "system",
            "content": skill_writing_chat_system()
        }
        messages.insert(0, system_instruction)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)

        ai_text, at_cost = client.generate(
            messages,
            expect_json=False,
            temperature=0.75,
            user_id=request.user.id,
            singleflight_scope=sf_scope,
        )

        json_match = re.search(r'\{(.*?)\}', ai_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = ai_text

        try:
            parsed = json.loads(json_str)
            reply_text = parsed.get('reply') or parsed.get('response') or parsed.get('text') or parsed.get('message') or parsed.get('content')
            if not reply_text:
                reply_text = str(parsed)

            reply_text = str(reply_text).strip()

            def clamp_score(val):
                try:
                    s = float(val)
                except (ValueError, TypeError):
                    return 0.0
                s = max(0.0, min(9.0, s))
                return round(s * 2) / 2

            grammar_score = clamp_score(parsed.get('grammar_score', 0))
            vocab_score = clamp_score(parsed.get('vocab_score', 0))
            relevance_score = clamp_score(parsed.get('relevance_score', 0))
            corrected_text = str(parsed.get('corrected_text', '')).strip()
        except json.JSONDecodeError:
            reply_text = ai_text.strip()
            grammar_score = 0.0
            vocab_score = 0.0
            relevance_score = 0.0
            corrected_text = ''

        return JsonResponse({
            'reply': reply_text,
            'grammar_score': grammar_score,
            'vocab_score': vocab_score,
            'relevance_score': relevance_score,
            'corrected_text': corrected_text,
            'atConsumed': at_cost
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
