"""AI 题库 REST 端点：列出 / 详情 / 提交作答（覆盖式）/ 删除。"""
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.models import AIQuestion


_VALID_SKILLS = {AIQuestion.SKILL_READING, AIQuestion.SKILL_LISTENING, AIQuestion.SKILL_WRITING}


def _serialize_summary(q: AIQuestion) -> dict:
    return {
        'id': q.id,
        'skill': q.skill,
        'subtype': q.subtype,
        'title': q.title,
        'isAnswered': q.user_answer_json is not None,
        'answeredAt': q.answered_at.isoformat() if q.answered_at else None,
        'lastAttemptAt': q.last_attempt_at.isoformat() if q.last_attempt_at else None,
        'createdAt': q.created_at.isoformat() if q.created_at else None,
    }


def _serialize_detail(q: AIQuestion) -> dict:
    data = _serialize_summary(q)
    data['content'] = q.content_json or {}
    data['userAnswer'] = q.user_answer_json
    data['aiFeedback'] = q.ai_feedback_json
    return data


def create_ai_question(*, user, skill: str, content: dict, title: str = '', subtype: str = '') -> AIQuestion:
    """供 reading/listening/writing 生成视图调用：持久化生成结果，返回入库后的 AIQuestion。"""
    if skill not in _VALID_SKILLS:
        raise ValueError(f'Invalid skill: {skill}')
    return AIQuestion.objects.create(
        user=user,
        skill=skill,
        subtype=(subtype or '')[:50],
        title=(title or '')[:300],
        content_json=content or {},
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_ai_questions(request):
    skill = (request.GET.get('skill') or '').strip().lower()
    qs = AIQuestion.objects.filter(user=request.user)
    if skill in _VALID_SKILLS:
        qs = qs.filter(skill=skill)

    answered_param = (request.GET.get('answered') or '').strip().lower()
    if answered_param == 'true':
        qs = qs.exclude(user_answer_json__isnull=True)
    elif answered_param == 'false':
        qs = qs.filter(user_answer_json__isnull=True)

    items = [_serialize_summary(q) for q in qs[:200]]
    return Response({'items': items, 'count': len(items)})


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def ai_question_detail(request, pk: int):
    try:
        q = AIQuestion.objects.get(pk=pk, user=request.user)
    except AIQuestion.DoesNotExist:
        return Response({'error': '题目不存在'}, status=404)

    if request.method == 'DELETE':
        q.delete()
        return Response({'ok': True})

    return Response(_serialize_detail(q))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_ai_question(request, pk: int):
    """提交作答，覆盖上一次结果。"""
    try:
        q = AIQuestion.objects.get(pk=pk, user=request.user)
    except AIQuestion.DoesNotExist:
        return Response({'error': '题目不存在'}, status=404)

    user_answer = request.data.get('userAnswer')
    if user_answer is None:
        return Response({'error': '缺少 userAnswer'}, status=400)

    ai_feedback = request.data.get('aiFeedback')

    now = timezone.now()
    q.user_answer_json = user_answer
    if ai_feedback is not None:
        q.ai_feedback_json = ai_feedback
    if q.answered_at is None:
        q.answered_at = now
    q.last_attempt_at = now
    q.save(update_fields=['user_answer_json', 'ai_feedback_json', 'answered_at', 'last_attempt_at'])

    return Response(_serialize_detail(q))
