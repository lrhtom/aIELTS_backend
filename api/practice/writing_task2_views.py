import json
import random
import re
import hashlib
from typing import Any
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.core.ai_client import AIClient
from api.core.rate_limit import check_rate_limit
from api.models import AIQuestion
from api.practice.ai_question_views import create_ai_question, spawn_ai_generation
from api.skills.writing.task2 import (
    skill_writing_task2_generate,
    skill_writing_task2_opinion_generate,
    skill_writing_task2_opinion_evaluate,
)

TASK2_TOPIC_AREAS = [
    "education and learning",
    "technology and the internet",
    "environment and climate change",
    "health and medicine",
    "crime and punishment",
    "work and employment",
    "government and politics",
    "media and advertising",
    "culture and tradition",
    "globalisation and international relations",
    "transport and urban planning",
    "family and social values",
    "sport and leisure",
    "arts and music",
    "science and space exploration",
    "animal rights and wildlife",
    "tourism and travel",
    "food and diet",
    "poverty and economic inequality",
    "language and communication",
]

TASK2_TOPIC_CATEGORY_MAP = {
    'education': 'education and learning',
    'technology': 'technology and the internet',
    'culture': 'culture and tradition',
    'urbanization': 'globalisation and international relations',
    'government': 'government and politics',
    'environment': 'environment and climate change',
    'media': 'media and advertising',
    'society': 'family and social values',
    'abstract': 'language and communication',
}

TASK2_TOPIC_ALL = 'all'
TASK2_TOPIC_RANDOM = 'random'
TASK2_TOPIC_INNOVATION = 'innovation'

OPINION_DRILL_CATEGORY_TOPICS = {
    'education': 'education and learning',
    'technology': 'technology and digital life',
    'culture': 'tradition and culture',
    'urbanization': 'urbanisation and globalisation',
    'government': 'government and public policy',
    'environment': 'environment and sustainability',
    'media': 'media and public opinion',
    'society': 'social life and community',
    'abstract': 'abstract social values and ethics',
}

OPINION_DRILL_QUESTION_STYLES = {
    1: 'Do you agree or disagree',
    2: 'Give your own opinion',
    3: 'What are the advantages',
    4: 'What are the disadvantages',
    5: 'What are the causes/reasons of this problem',
    6: 'What solutions can you suggest',
    7: 'Open-ended question format',
}

OPINION_DRILL_RANDOM_CATEGORY = 'random'


def _resolve_task2_topic_selection(topic_category: Any):
    normalized = str(topic_category or TASK2_TOPIC_ALL).strip().lower()

    if normalized == TASK2_TOPIC_RANDOM:
        sampled_category = random.choice(list(TASK2_TOPIC_CATEGORY_MAP.keys()))
        return normalized, sampled_category, TASK2_TOPIC_CATEGORY_MAP[sampled_category]

    if normalized in TASK2_TOPIC_CATEGORY_MAP:
        return normalized, normalized, TASK2_TOPIC_CATEGORY_MAP[normalized]

    if normalized == TASK2_TOPIC_INNOVATION:
        return normalized, normalized, ''

    return TASK2_TOPIC_ALL, TASK2_TOPIC_ALL, random.choice(TASK2_TOPIC_AREAS)


def _build_singleflight_scope(scope_prefix: str, payload: Any) -> str:
    try:
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_text = str(payload)
    digest = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:16]
    return f"{scope_prefix}:{digest}"


# ── 真题题干骨架 (剑桥 4-21 二十年不变, 见 雅思资料/蒸馏/writing_skill.md) ──
def _wrap_task2_prompt(core: str) -> str:
    """把 AI 生成的核心题干包进真题固定骨架; 先剥掉 AI 可能自带的骨架句避免重复."""
    text = (core or '').strip()
    text = re.sub(r'(?i)you should spend about 40 minutes on this task\.?', '', text)
    text = re.sub(r'(?i)write about the following topic:?', '', text)
    text = re.sub(
        r'(?i)give reasons for your answer and include any relevant examples'
        r'( from your own knowledge or experience)?\.?',
        '', text)
    text = re.sub(r'(?i)write at least 250 words\.?', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        return core or ''
    return (
        'You should spend about 40 minutes on this task.\n\n'
        'Write about the following topic:\n\n'
        f'{text}\n\n'
        'Give reasons for your answer and include any relevant examples '
        'from your own knowledge or experience.\n\n'
        'Write at least 250 words.'
    )


def _build_opinion_drill_generation_plan(count: int, selected_categories: list[str]):
    style_pool = list(OPINION_DRILL_QUESTION_STYLES.keys())
    plan = []

    for i in range(count):
        if selected_categories:
            category = random.choice(selected_categories)
        else:
            category = OPINION_DRILL_RANDOM_CATEGORY

        plan.append({
            'id': i + 1,
            'category': category,
            'styleId': random.choice(style_pool),
        })

    return plan


def _fallback_prompt_for(category: str, style_id: int) -> str:
    topic = OPINION_DRILL_CATEGORY_TOPICS.get(category)
    if not topic:
        topic = random.choice(TASK2_TOPIC_AREAS)

    if style_id == 1:
        return (
            f"Some people believe that major decisions about {topic} should be made by governments rather than individuals. "
            "Do you agree or disagree?"
        )
    if style_id == 2:
        return (
            f"Many people claim that rapid change in {topic} is always beneficial for society. "
            "Give your own opinion."
        )
    if style_id == 3:
        return f"In many countries, new policies in {topic} are being introduced quickly. What are the advantages?"
    if style_id == 4:
        return f"In many countries, new policies in {topic} are being introduced quickly. What are the disadvantages?"
    if style_id == 5:
        return f"Problems connected with {topic} are becoming increasingly serious in many places. What are the causes/reasons of this problem?"
    if style_id == 6:
        return f"Many societies are facing persistent challenges in {topic}. What solutions can you suggest?"

    return f"How should modern societies balance fairness, efficiency, and long-term sustainability in {topic}?"


def _prompt_matches_style(prompt: str, style_id: int) -> bool:
    text = prompt.lower()
    if style_id == 1:
        return 'agree or disagree' in text
    if style_id == 2:
        return 'give your own opinion' in text or 'give your opinion' in text or 'your own opinion' in text
    if style_id == 3:
        return 'advantages' in text
    if style_id == 4:
        return 'disadvantages' in text
    if style_id == 5:
        return 'causes' in text or 'reasons' in text
    if style_id == 6:
        return 'solutions' in text
    if style_id == 7:
        return True
    return False


def _safe_band(value: Any, default: float = 6.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return round(default, 1)
    return round(max(0.0, min(9.0, score)), 1)


def _sanitize_reference_answer(text: str, max_words: int = 100) -> str:
    # Keep one paragraph and hard-limit the model answer length.
    cleaned = ' '.join(str(text or '').replace('\n', ' ').split())
    if not cleaned:
        return ''

    words = cleaned.split(' ')
    if len(words) <= max_words:
        return cleaned
    return ' '.join(words[:max_words])


def _normalize_opinion_drill_questions(raw_questions, count: int, generation_plan: list[dict[str, Any]]):
    normalized = []
    style_pool = list(OPINION_DRILL_QUESTION_STYLES.keys())
    raw_list = raw_questions if isinstance(raw_questions, list) else []

    for idx in range(count):
        plan_item = generation_plan[idx] if idx < len(generation_plan) else {}
        category = str(plan_item.get('category', OPINION_DRILL_RANDOM_CATEGORY)).strip().lower()
        if category not in OPINION_DRILL_CATEGORY_TOPICS and category != OPINION_DRILL_RANDOM_CATEGORY:
            category = OPINION_DRILL_RANDOM_CATEGORY

        style_id = plan_item.get('styleId')
        try:
            style_id = int(style_id)
        except (TypeError, ValueError):
            style_id = random.choice(style_pool)
        if style_id not in OPINION_DRILL_QUESTION_STYLES:
            style_id = random.choice(style_pool)

        raw_item = raw_list[idx] if idx < len(raw_list) else None
        if isinstance(raw_item, dict):
            prompt = str(raw_item.get('prompt', '')).strip()
        else:
            prompt = str(raw_item).strip() if raw_item is not None else ''

        if not prompt or not _prompt_matches_style(prompt, style_id):
            prompt = _fallback_prompt_for(category, style_id)

        normalized.append({
            'id': idx + 1,
            'category': category,
            'prompt': prompt,
            'styleId': style_id,
        })

    return normalized

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_task2(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'task2_generate', max_calls=10, window=60)
        if limit_resp: return limit_resp
        task_type = request.data.get('type', 'opinion')
        topic_category = request.data.get('topic_category', TASK2_TOPIC_ALL)
        custom_title = (request.data.get('customName') or request.data.get('customTitle') or '').strip()
        custom_description = (request.data.get('customDescription') or request.data.get('description') or '').strip()
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        type_map = {
            'opinion': 'Opinion Essay (Agree/Disagree or To what extent do you agree/disagree)',
            'opinion_agree': 'Opinion Essay - Agree or Disagree (Ask the user to what extent they agree or disagree with a statement)',
            'opinion_discuss': 'Opinion Essay - Discuss both views and give your opinion',
            'opinion_advantages': 'Opinion Essay - Do the advantages outweigh the disadvantages?',
            'report': 'Report (Cause & Solution or Problem & Effect)',
            'mixed': 'Mixed Essay (Discuss both views and give your opinion, or multi-part questions)',
            'innovation': 'AI Innovation Prompt (A completely novel, cutting-edge, or futuristic social/tech issue that IELTS might test in the future)'
        }
        
        selected_desc = type_map.get(task_type, type_map['opinion'])
        requested_topic_category, resolved_topic_category, topic_area = _resolve_task2_topic_selection(topic_category)

        if resolved_topic_category == TASK2_TOPIC_INNOVATION:
            topic_instruction = (
                'The topic area must be an original and plausible future IELTS category '
                'invented by you (not a standard textbook category).'
            )
        else:
            topic_instruction = f'The topic area must be: {topic_area}.'

        system_prompt = skill_writing_task2_generate(selected_desc, topic_instruction)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the Task 2 prompt."}
        ]

        user_id = user.id
        placeholder = f'✍️ Task 2 生成中... ({task_type})'

        def _generator(_row):
            response_data, _at_cost = client.generate(
                messages,
                expect_json=True,
                user_id=user_id,
                singleflight_scope='writing_task2_generate',
            )
            core_text = response_data.get('prompt', '')
            prompt_text = _wrap_task2_prompt(core_text)
            payload = {
                'prompt': prompt_text,
                'requestedTopicCategory': requested_topic_category,
                'topicCategory': resolved_topic_category,
                'topicArea': topic_area or 'innovation-generated',
                'writingKind': 'task2',
                'taskType': task_type,
            }
            if custom_description:
                payload['description'] = custom_description
            # title 取核心题干首行, 不带骨架句
            title = (core_text or 'Task 2').strip().splitlines()[0][:200] or 'Task 2'
            return title, payload

        row = spawn_ai_generation(
            user=user,
            skill=AIQuestion.SKILL_WRITING,
            subtype=f'task2:{task_type}',
            placeholder_title=placeholder,
            generator=_generator,
            custom_title=custom_title,
        )
        return Response({
            'aiQuestionId': row.id,
            'status': row.status,
            'title': row.title,
        }, status=202)
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_opinion_drill_questions(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'task2_opinion_drill_generate', max_calls=5, window=60)
        if limit_resp:
            return limit_resp

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)

        try:
            count = int(request.data.get('count', 5))
            if not (1 <= count <= 10):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'count 必须是 1-10 的整数'}, status=400)

        raw_categories = request.data.get('categories', [])
        if not isinstance(raw_categories, list):
            raw_categories = []

        selected_categories = [
            str(c).strip().lower()
            for c in raw_categories
            if str(c).strip().lower() in OPINION_DRILL_CATEGORY_TOPICS
        ]

        generation_plan = _build_opinion_drill_generation_plan(
            count=count,
            selected_categories=selected_categories,
        )

        if selected_categories:
            topic_scope = ', '.join(OPINION_DRILL_CATEGORY_TOPICS[c] for c in selected_categories)
            allowed_cats = ', '.join(selected_categories)
        else:
            topic_scope = 'random IELTS Task 2 topic areas'
            allowed_cats = OPINION_DRILL_RANDOM_CATEGORY

        style_desc = '; '.join([f"{k}) {v}" for k, v in OPINION_DRILL_QUESTION_STYLES.items()])
        generation_plan_json = json.dumps(generation_plan, ensure_ascii=False)

        system_prompt = skill_writing_task2_opinion_generate(
            count, allowed_cats, topic_scope, style_desc
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generation plan:\n{generation_plan_json}\n\nGenerate the question set now."},
        ]

        response_data, at_cost = client.generate(
            messages,
            expect_json=True,
            user_id=user.id,
            singleflight_scope='writing_task2_opinion_drill_generate',
        )
        questions = _normalize_opinion_drill_questions(
            response_data.get('questions', []),
            count=count,
            generation_plan=generation_plan,
        )

        return Response({
            'questions': questions,
            'atConsumed': at_cost,
        })
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_opinion_drill_answer(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'task2_opinion_drill_evaluate', max_calls=12, window=60)
        if limit_resp:
            return limit_resp

        prompt_text = str(request.data.get('prompt', '')).strip()
        user_answer = str(request.data.get('userAnswer', '')).strip()
        ui_lang = request.data.get('lang', 'en')
        provider = request.headers.get('X-AI-Provider', 'deepseek')
        eval_scope = _build_singleflight_scope(
            'writing_task2_opinion_drill_evaluate',
            {
                'prompt': prompt_text,
                'userAnswer': user_answer,
                'lang': ui_lang,
            },
        )

        if not prompt_text:
            return Response({'error': '缂哄皯棰樼洰 prompt'}, status=400)
        if not user_answer:
            return Response({'error': '答案不能为空'}, status=400)

        client = AIClient(provider=provider)

        lang_instruction = (
            'Write the feedback in Simplified Chinese.'
            if ui_lang == 'zh'
            else 'Write the feedback in English.'
        )

        system_prompt = skill_writing_task2_opinion_evaluate(lang_instruction)

        user_msg = f"Question:\n{prompt_text}\n\nCandidate Answer:\n{user_answer}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        response_data, at_cost = client.generate(
            messages,
            expect_json=True,
            user_id=user.id,
            singleflight_scope=eval_scope,
        )
        score_obj = response_data.get('scores', {}) if isinstance(response_data, dict) else {}

        grammar = _safe_band(score_obj.get('grammar'), default=6.0)
        relevance = _safe_band(score_obj.get('relevance'), default=6.0)
        vocabulary = _safe_band(score_obj.get('vocabulary'), default=6.0)
        avg_default = round((grammar + relevance + vocabulary) / 3, 1)
        overall = _safe_band(response_data.get('overall'), default=avg_default)

        feedback = ''
        if isinstance(response_data, dict):
            feedback = str(response_data.get('feedback', '')).strip()
        if not feedback:
            feedback = '评分完成。继续保持练习。' if ui_lang == 'zh' else 'Evaluation completed. Keep practicing.'

        reference_answer = ''
        if isinstance(response_data, dict):
            reference_answer = str(response_data.get('referenceAnswer', '')).strip()
        if not reference_answer:
            reference_answer = (
                'I mostly agree because effective change needs both policy direction and personal action. '
                'Governments can provide fair rules and resources, but progress happens only when individuals apply these rules in daily life. '
                'If either side is weak, results are limited and uneven. '
                'A balanced model, where public systems lead and citizens actively participate, is the most practical path to lasting improvement.'
            )
        reference_answer = _sanitize_reference_answer(reference_answer, max_words=100)

        return Response({
            'scores': {
                'grammar': grammar,
                'relevance': relevance,
                'vocabulary': vocabulary,
            },
            'overall': overall,
            'feedback': feedback,
            'referenceAnswer': reference_answer,
            'atConsumed': at_cost,
        })
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)


