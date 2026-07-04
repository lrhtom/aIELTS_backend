"""AI 题库 REST 端点：列出 / 详情 / 提交作答（覆盖式）/ 删除。

Async generation model
----------------------
`spawn_ai_generation` inserts a placeholder AIQuestion (status='generating')
and runs the actual AI call on a background daemon thread. The synchronous view
returns the question id immediately so the browser can navigate straight to the
AI bank; the bank polls and reveals the row when status flips to 'ready' (or
'failed' + `error_message` if AI blew up).

This makes the tab-close-during-generation problem go away — AT deduction and
content persistence happen entirely server-side, decoupled from whether the
client is still around.
"""
import os
import threading
import traceback
from datetime import timedelta
from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.models import AIQuestion


def _cleanup_question_files(q: AIQuestion) -> None:
    """Delete media files owned by this AIQuestion.

    Currently only raster-map questions (writing/chart:map with mapImagePath) hold
    on-disk artifacts — other question types embed base64 or SVG in content_json.
    Safe-path guard: only unlink files that resolve under MEDIA_ROOT/maps/.
    """
    content = q.content_json or {}
    rel_path = content.get('mapImagePath')
    if not rel_path:
        return
    try:
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        maps_root = os.path.realpath(os.path.join(media_root, 'maps'))
        target = os.path.realpath(os.path.join(media_root, rel_path))
        # Ensure target is strictly inside maps_root (defence against ../ paths)
        if not target.startswith(maps_root + os.sep) and target != maps_root:
            return
        if os.path.isfile(target):
            os.unlink(target)
            # Best-effort: remove empty user dir
            parent = os.path.dirname(target)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
    except Exception as e:
        # Never let cleanup failure block the delete of the DB row.
        print(f'[AIQuestion] [WARN] file cleanup failed for {rel_path}: {e}')


_VALID_SKILLS = {AIQuestion.SKILL_READING, AIQuestion.SKILL_LISTENING, AIQuestion.SKILL_WRITING}


def _serialize_summary(q: AIQuestion) -> dict:
    return {
        'id': q.id,
        'skill': q.skill,
        'subtype': q.subtype,
        'title': q.title,
        'status': q.status,
        'errorMessage': q.error_message or '',
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
        status=AIQuestion.STATUS_READY,
    )


def spawn_ai_generation(*, user, skill: str, subtype: str, placeholder_title: str, generator):
    """Insert a placeholder AIQuestion row, kick off `generator` on a background
    daemon thread, return the row synchronously.

    :param generator: callable that receives the AIQuestion row and must return
        a `(title, content_dict)` tuple on success. Any raised exception marks
        the row as failed and stores the message.

    Thread rules:
      - We're not in Celery-land, so we borrow a daemon thread. Daemon = True
        so gunicorn worker recycling doesn't get stuck waiting on a hung AI
        request.
      - `connections.close_all()` at the end returns the DB connection to the
        pool. Without it, thread-local connections leak until GC.
    """
    if skill not in _VALID_SKILLS:
        raise ValueError(f'Invalid skill: {skill}')

    question = AIQuestion.objects.create(
        user=user,
        skill=skill,
        subtype=(subtype or '')[:50],
        title=(placeholder_title or '生成中...')[:300],
        content_json={},
        status=AIQuestion.STATUS_GENERATING,
    )
    question_id = question.id

    def _run():
        try:
            title, content = generator(question)
            # Reload inside the thread — the caller may have moved on and
            # closed its own connection.
            AIQuestion.objects.filter(pk=question_id).update(
                title=(title or '')[:300] or question.title,
                content_json=content or {},
                status=AIQuestion.STATUS_READY,
                error_message='',
            )
        except Exception as exc:
            print(f'[AIQuestion async] generation failed q={question_id}: {exc!r}')
            traceback.print_exc()
            AIQuestion.objects.filter(pk=question_id).update(
                status=AIQuestion.STATUS_FAILED,
                error_message=str(exc)[:2000],
            )
        finally:
            try:
                connections.close_all()
            except Exception:
                pass

    thread = threading.Thread(target=_run, name=f'aigen-{question_id}', daemon=True)
    thread.start()
    return question


def _stale_generation_reap(user):
    """Sweep the caller's own rows: anything stuck in 'generating' for > 30 min
    is upgraded to 'failed' so the list endpoint never leaves the UI polling
    forever on a thread that died silently.
    """
    cutoff = timezone.now() - timedelta(minutes=30)
    AIQuestion.objects.filter(
        user=user,
        status=AIQuestion.STATUS_GENERATING,
        created_at__lt=cutoff,
    ).update(
        status=AIQuestion.STATUS_FAILED,
        error_message='生成超时（未在 30 分钟内完成）。',
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_ai_questions(request):
    # Auto-expire generations stuck in 'generating' for too long so the UI
    # never polls a dead row indefinitely.
    _stale_generation_reap(request.user)

    skill = (request.GET.get('skill') or '').strip().lower()
    qs = AIQuestion.objects.filter(user=request.user)
    if skill in _VALID_SKILLS:
        qs = qs.filter(skill=skill)

    answered_param = (request.GET.get('answered') or '').strip().lower()
    if answered_param == 'true':
        qs = qs.exclude(user_answer_json__isnull=True)
    elif answered_param == 'false':
        qs = qs.filter(user_answer_json__isnull=True)

    status_param = (request.GET.get('status') or '').strip().lower()
    if status_param in {'generating', 'ready', 'failed'}:
        qs = qs.filter(status=status_param)

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
        _cleanup_question_files(q)
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
