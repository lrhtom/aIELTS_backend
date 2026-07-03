import json
import os
import re
import random
import hashlib
import html
import subprocess
import tempfile
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.utils import call_ai_api
from api.core.rate_limit import check_rate_limit
from api.models import AIQuestion
from api.practice.ai_question_views import create_ai_question
from api.skills.listening.generation import (
    SKILL_LISTENING_ARTICLE_TEMPLATE as ARTICLE_LISTENING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MULTIPLE_CHOICE_TEMPLATE as ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE,
    SKILL_LISTENING_SENTENCE_TEMPLATE as SENTENCE_LISTENING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MAP_TEMPLATE as MAP_LABELLING_PROMPT_TEMPLATE,
    SKILL_LISTENING_MAP_SUBTYPES as MAP_SUBTYPES,
)





@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_listening(request):
    """POST /api/listening/generate - 生成听力填空练习。"""
    try:
        limit_resp = check_rate_limit(request.user.id, 'listening_generate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        words = request.data.get('words', [])
        difficulty = request.data.get('difficulty', '7.0')
        word_count_min = request.data.get('wordCountMin', 1)
        word_count_max = request.data.get('wordCountMax', 2)
        practice_type = request.data.get('practiceType', 'article')
        is_map_mode = practice_type == 'map'
        absurd_mode = str(request.data.get('absurdMode', 'false')).lower() == 'true'
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe: no profanity, no sexual content, no harassment."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        print(f"\n{'='*60}", flush=True)
        print(f"[Listening] 📥 收到请求", flush=True)
        print(f"[Listening]   类型: {practice_type}", flush=True)
        print(f"[Listening]   难度: {difficulty}", flush=True)
        print(f"[Listening]   词数: {word_count_min}~{word_count_max}", flush=True)
        print(f"[Listening]   词汇: {words}", flush=True)

        if not words:
            vocab_instruction = ""
            marker_rule = ""
            mc_marker_rule = ""
            answer_priority_rule = ""
        else:
            word_str = ', '.join(words)
            vocab_instruction = f"incorporating the following vocabulary words as much as possible: {word_str}"
            marker_rule = "Wrap target vocabulary in double asterisks like **word**."
            mc_marker_rule = "IMPORTANT RULES:\\nWhenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else."
            answer_priority_rule = "IMPORTANT: Try to incorporate the provided vocabulary words as answers. If possible, make these words the primary answers in the answers array."

        # 生成更明确的词数描述和示例答案
        if word_count_min == word_count_max:
            if word_count_min == 1:
                word_count_desc = "exactly ONE word only (not two, not three, just one single word)"
                example_answer = "dedication"
            elif word_count_min == 2:
                word_count_desc = "exactly TWO words (a two-word phrase)"
                example_answer = "climate change"
            else:
                word_count_desc = f"exactly {word_count_min} words"
                example_answer = "rapidly growing population"
        else:
            word_count_desc = f"NO MORE THAN {word_count_max} words (between {word_count_min} and {word_count_max} words)"
            if word_count_max == 1:
                example_answer = "dedication"
            elif word_count_max == 2:
                example_answer = "climate change"
            else:
                example_answer = "growing population"

        
        if is_map_mode:
            subtype_key = random.choice(list(MAP_SUBTYPES.keys()))
            subtype = MAP_SUBTYPES[subtype_key]
            print(f"[Listening] 🗺️ 地图子类型: {subtype['name']}", flush=True)
            prompt = MAP_LABELLING_PROMPT_TEMPLATE.format(
                difficulty=difficulty,
                tone_instruction=tone_instruction,
                map_subtype=subtype['name'],
                subtype_instructions=subtype['instructions'],
            )
        elif practice_type == 'multiple_choice':
            prompt = ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                mc_marker_rule=mc_marker_rule,
                tone_instruction=tone_instruction,
            )
        elif practice_type == 'sentence':
            prompt = SENTENCE_LISTENING_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                word_count_desc=word_count_desc,
                example_answer=example_answer,
                marker_rule=marker_rule,
                answer_priority_rule=answer_priority_rule,
                tone_instruction=tone_instruction,
            )
        else:
            prompt = ARTICLE_LISTENING_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                word_count_desc=word_count_desc,
                example_answer=example_answer,
                marker_rule=marker_rule,
                answer_priority_rule=answer_priority_rule,
                tone_instruction=tone_instruction,
            )

        print(f"[Listening] 📝 AI 提示词\n{prompt[:500]}...\n", flush=True)
        result = call_ai_api(
            prompt,
            provider=provider,
            user_id=request.user.id,
            singleflight_scope='listening_generate',
        )
        print(f"[Listening] 🤖 AI 完整返回:\n{json.dumps(result, ensure_ascii=False, indent=2)[:2000]}...\n", flush=True)

        # 打印 AI 返回的关键信息
        print(f"[Listening] 📊 AI 返回数据:", flush=True)
        print(f"[Listening]   type: {result.get('type', '❌ 缺失')}", flush=True)
        print(f"[Listening]   title: {result.get('title', '❌ 缺失')}", flush=True)
        print(f"[Listening]   passage: {result.get('passage', '❌ 缺失')}", flush=True)
        print(f"[Listening]   passage 长度: {len(result.get('passage', ''))} 字符", flush=True)
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            print(f"[Listening]   blanked_passage 长度: {len(bp)} 字符", flush=True)
            print(f"[Listening]   blanked_passage 中 _____ 数量: {bp.count('_____')}", flush=True)
        raw_q = result.get('questions', [])
        print(f"[Listening]   questions 数量: {len(raw_q)}", flush=True)
        for q in raw_q:
            ans = q.get('answers', [])
            print(f"[Listening]     Q{q.get('id')}: answers={ans}, has_blank={'_____' in q.get('question', '')}", flush=True)

        # 强力后处理：确保数据结构完整
        # 确保 type 字段存在
        if 'type' not in result:
            result['type'] = practice_type

        # 确保 questions 数组存在且不为空
        questions = result.get('questions', [])
        if not questions:
            return JsonResponse({'error': 'AI failed to generate questions. Please try again.'}, status=500)

        # 截断为最多 10 个题目
        if len(questions) > 10:
            print(f"[Listening] ⚠️ 题目超过10个({len(questions)})，截断为10", flush=True)
            questions = questions[:10]
            result['questions'] = questions

        # 重新编号 id 为 1-10
        for i, q in enumerate(questions):
            q['id'] = i + 1

        # 强力后处理：标准化所有下划线（统一为 5 个）
        for q in questions:
            q['question'] = re.sub(r'_{2,}', '_____', q.get('question', ''))
        
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if bp:
                result['blanked_passage'] = re.sub(r'_{2,}', '_____', bp)

        # 句子模式：确保每个 question 都包含 _____
        if practice_type == 'sentence':
            for q in questions:
                if '_____' not in q.get('question', ''):
                    q['question'] = q['question'].rstrip('.') + ' _____.'

        # 文章填空模式：确保 blanked_passage 存在并包含 _____
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if not bp or '_____' not in bp:
                result['blanked_passage'] = result.get('passage', '')
            else:
                # 确保 blanked_passage 中的空格数量与 questions 数量一致
                blank_count = bp.count('_____')
                if blank_count < len(questions):
                    # 空格比题目少，截断题目数量以匹配
                    result['questions'] = questions[:blank_count]
                    for i, q in enumerate(result['questions']):
                        q['id'] = i + 1

        if is_map_mode:
            # 地图题后处理
            map_data = result.get('map', {})
            landmarks = map_data.get('landmarks', [])
            mw = map_data.get('width', 600)
            mh = map_data.get('height', 400)
            # 校验坐标范围
            for lm in landmarks:
                lm['x'] = max(30, min(mw - 30, lm.get('x', 300)))
                lm['y'] = max(30, min(mh - 30, lm.get('y', 200)))
            # 确保 questions 与 questionId 对应
            q_ids_in_map = {lm['questionId'] for lm in landmarks if 'questionId' in lm}
            result['questions'] = [q for q in result.get('questions', []) if q.get('id') in q_ids_in_map]
            # 确保 options 是列表
            if not isinstance(result.get('options'), list):
                result['options'] = []
            print(f"[Listening] 🗺️ 地图题: {len(landmarks)} 个地标, {len(result['questions'])} 个题目, {len(result['options'])} 个选项", flush=True)

        elif practice_type == 'multiple_choice':
            for q in result.get('questions', []):
                options_list = q.get('options')
                if isinstance(options_list, list) and len(options_list) >= 1:
                    correct_text = options_list[0]
                    shuffled = list(options_list)
                    random.shuffle(shuffled)
                    
                    letters = ['A', 'B', 'C', 'D']
                    options_dict = {}
                    correct_letter = 'A'
                    for idx, opt_text in enumerate(shuffled[:4]):
                        letter = letters[idx]
                        options_dict[letter] = opt_text
                        if opt_text == correct_text:
                            correct_letter = letter
                    
                    q['options'] = options_dict
                    q['answer'] = correct_letter

        print(f"[Listening] ✅ 最终返回 {len(result.get('questions', []))} 个题目", flush=True)
        
        # 禁用用户词汇答案优化，直接使用 AI 生成的答案
        print(f"[Listening] 📌 不执行词汇优化，使用 AI 生成的答案", flush=True)
        
        # 打印最终返回的答案和题目
        print(f"[Listening] 📤 最终返回的答案和题目", flush=True)
        final_questions = result.get('questions', [])
        for q in final_questions:
            print(f"[Listening]   Q{q.get('id')}: {q.get('question', '')}", flush=True)
            print(f"[Listening]      答案: {q.get('answers', [])}", flush=True)
            print(f"[Listening]      解析: {q.get('explanation', '')}", flush=True)
        
        print(f"[Listening] 📄 Passage:", flush=True)
        print(f"{result.get('passage', '')}", flush=True)
        
        print(f"{'='*60}\n", flush=True)

        try:
            listening_title = str(result.get('title') or '').strip() or '听力练习'
            content_to_save = {k: v for k, v in result.items() if k != 'atConsumed'}
            ai_question = create_ai_question(
                user=request.user,
                skill=AIQuestion.SKILL_LISTENING,
                subtype=practice_type,
                title=listening_title,
                content=content_to_save,
            )
            result['aiQuestionId'] = ai_question.id
        except Exception as save_err:
            print(f'[Listening] ⚠️ AIQuestion 入库失败: {save_err}', flush=True)
            result['aiQuestionId'] = None

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


LISTENING_AUDIO_SUBDIR = 'listening_audio'


@api_view(['POST'])
def generate_listening_audio(request):
    """POST /api/listening/audio - 生成 Edge-TTS 的 mp3 文件。

    音频按 md5(voice + speak_text) 落盘到 media/listening_audio/{hash}.mp3；
    同样文本 + 同样声音的后续请求直接从磁盘读回,不再走 edge-tts。
    好处: 一个题库题第一次点播放会生成一次 mp3,之后所有人所有次都命中缓存。
    """
    try:
        text = request.data.get('text', '')

        def markdown_to_tts_text(value: str) -> str:
            """
            Convert Markdown/GFM text to a clean plain-text string for TTS.
            Keep semantic content while removing formatting markers.
            """
            raw = html.unescape(str(value or ''))
            if not raw:
                return ''

            out = raw.replace('\r\n', '\n').replace('\r', '\n')

            # Remove fenced code block markers while keeping code content.
            out = re.sub(r'^\s*```[^\n]*\n?', '', out, flags=re.MULTILINE)
            out = out.replace('```', '')

            # Convert Markdown links/images to readable text.
            out = re.sub(r'!\[([^\]]*)\]\([^\)]*\)', r'\1', out)
            out = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', out)

            # Remove common Markdown prefixes.
            out = re.sub(r'^\s{0,3}#{1,6}\s*', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s{0,3}>\s?', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*[-*+]\s+', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*\d+\.\s+', '', out, flags=re.MULTILINE)

            # Remove emphasis/code markers but keep inner text.
            out = re.sub(r'\*\*([^*]+)\*\*', r'\1', out)
            out = re.sub(r'__([^_]+)__', r'\1', out)
            out = re.sub(r'\*([^*]+)\*', r'\1', out)
            out = re.sub(r'_([^_]+)_', r'\1', out)
            out = re.sub(r'~~([^~]+)~~', r'\1', out)
            out = re.sub(r'`([^`]*)`', r'\1', out)

            # Remove HTML tags and raw URLs that sound noisy in speech.
            out = re.sub(r'<[^>]+>', ' ', out)
            out = re.sub(r'https?://\S+', ' ', out)

            # Normalize whitespace/newlines.
            out = re.sub(r'[ \t]+', ' ', out)
            out = re.sub(r'\n{3,}', '\n\n', out)
            return out.strip()

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        speak_text = markdown_to_tts_text(text)
        if not speak_text:
            speak_text = str(text).strip()

        # 雅思听力常选用的声音: 英式 Sonia
        voice = request.data.get('voice') or "en-GB-SoniaNeural"

        cache_key = hashlib.md5(f'{voice}|{speak_text}'.encode('utf-8')).hexdigest()
        rel_path = f'{LISTENING_AUDIO_SUBDIR}/{cache_key}.mp3'
        abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)

        # Cache hit: return the on-disk mp3 without paying for edge-tts.
        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            with open(abs_path, 'rb') as f:
                resp = HttpResponse(f.read(), content_type='audio/mpeg')
            resp['X-Audio-Cache'] = 'HIT'
            return resp

        # Cache miss: generate + persist. Write to a temp file first so an
        # interrupted edge-tts doesn't leave a truncated mp3 masquerading as
        # a valid cache entry on the next request.
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir=os.path.dirname(abs_path)) as tmp:
            temp_path = tmp.name

        try:
            subprocess.run(
                ['edge-tts', '--voice', voice, '--text', speak_text, '--write-media', temp_path],
                check=True,
            )
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError('edge-tts produced empty output')
            # Atomic rename into the cache location so partial writes never win.
            os.replace(temp_path, abs_path)

            with open(abs_path, 'rb') as f:
                resp = HttpResponse(f.read(), content_type='audio/mpeg')
            resp['X-Audio-Cache'] = 'MISS'
            return resp
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _clean_answer_value(answer: any) -> str:
    """
    清理答案值：处理多种格式
    1. 如果是对象/字典，提取 answer 字段
    2. 移除括号和其他封装符号：(answer) -> answer
    3. 移除多个相关答案，只保留第一个：answer1/answer2 -> answer1
    4. 去除前后空格和标点
    """
    # 如果是字典对象，尝试提取 answer 字段
    if isinstance(answer, dict):
        answer = answer.get('answer', answer.get('value', str(answer)))
    
    answer = str(answer).strip()
    
    # 移除所有括号（圆括号、方括号、花括号）
    answer = answer.strip('()[]{}')
    
    # 处理多个相关答案，按优先级只保留第一个
    # 优先级：/ > , > ;
    for separator in ['/', ',', ';', ' or ', ' OR ', ' | ']:
        if separator in answer:
            answer = answer.split(separator)[0].strip()
            break
    
    # 移除结尾标点符号
    answer = answer.rstrip('.,;:!?')
    
    return answer.strip()


