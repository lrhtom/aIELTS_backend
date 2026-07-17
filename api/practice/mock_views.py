"""全套模拟 (Full Mock Exam) —— 生成编排 + 考试状态机端点。

数据结构（复用 AIQuestion，无新表）：
  父行 AIQuestion(skill='mock')
    content_json     = {'kind': 'mock', 'config': {...生成配置快照...},
                        'parts': {slot: {'questionId': int|None}}}
    user_answer_json = {'exam': {part: {'status', 'startedAt', 'deadline', ...}}}
                       —— 考试进度，服务端权威墙钟（刷新可续答、退出判 0 的依据）
    ai_feedback_json = 成绩单（finalize 写入，四科 band + 总分）
  子行 = 听力全套 / 阅读全套 / Task1 图表 / Task2 / 口语会话（parent FK，级联删除）。

生成槽位 (slot)  : listening / reading / writingTask1 / writingTask2 (+ speaking 懒创建)
考试部分 (part)  : listening → reading → writing (T1+T2 共用计时) → speaking，顺序强制。

考试规则（2026-07 用户规格）：
  听 32min / 读 60min / 写 60min（大小作文同一计时）；口语无总时限（前端 5 秒反应规则）；
  每科只能做一次；作答中可刷新续答（deadline 是服务端墙钟）；退出判 0（forfeit 端点）。
"""
import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.core.rate_limit import check_rate_limit
from api.models import AIQuestion
from api.practice.ai_question_views import _cleanup_question_files
from api.practice.listening_views import spawn_full_listening
from api.practice.reading_views import spawn_full_reading
from api.practice.writing_chart_views import spawn_chart_task1
from api.practice.writing_task2_views import spawn_task2

MOCK_PART_ORDER = ['listening', 'reading', 'writing', 'speaking']

# 各部分考试时长（秒）；speaking 为 None = 无总时限（只有前端的 5 秒反应规则）
MOCK_PART_DURATION_SEC = {
    'listening': 32 * 60,
    'reading': 60 * 60,
    'writing': 60 * 60,
    'speaking': None,
}
# 交卷宽限：deadline 之后仍接受提交的窗口（前端自动交卷 + 网络延迟的余量）
MOCK_DEADLINE_GRACE_SEC = 60

MOCK_GEN_SLOTS = ['listening', 'reading', 'writingTask1', 'writingTask2']

# Task1 随机池：常规图表占大头，map/flowchart 低频（贴近真题分布）
_TASK1_RANDOM_POOL = ['line', 'bar', 'pie', 'horizontal', 'table', 'mixed'] * 2 + ['flowchart', 'map']
_TASK1_VALID_TYPES = {'line', 'bar', 'pie', 'horizontal', 'table', 'mixed', 'flowchart', 'map'}

TERMINAL_STATES = {'submitted', 'forfeited', 'expired'}

# 子行 skill → 考试部分
_SKILL_TO_PART = {
    AIQuestion.SKILL_LISTENING: 'listening',
    AIQuestion.SKILL_READING: 'reading',
    AIQuestion.SKILL_WRITING: 'writing',
    AIQuestion.SKILL_SPEAKING: 'speaking',
}


# ── 内部工具 ──────────────────────────────────────────

def _get_parent(user, pk: int, *, for_update: bool = False) -> AIQuestion:
    qs = AIQuestion.objects.select_for_update() if for_update else AIQuestion.objects
    return qs.get(pk=pk, user=user, skill=AIQuestion.SKILL_MOCK)


def _children_map(parent: AIQuestion) -> dict[str, AIQuestion | None]:
    """slot → 子行。以 content_json.parts 里记录的 questionId 为准。"""
    parts = ((parent.content_json or {}).get('parts') or {})
    rows = {r.id: r for r in AIQuestion.objects.filter(parent=parent)}
    out: dict[str, AIQuestion | None] = {}
    for slot, meta in parts.items():
        qid = (meta or {}).get('questionId')
        out[slot] = rows.get(qid)
    return out


def _gen_status_for_part(part: str, children: dict) -> str:
    """考试部分的生成状态：writing 需要 T1+T2 都 ready；speaking 抽题在开始时进行，恒 ready。"""
    if part == 'listening':
        rows = [children.get('listening')]
    elif part == 'reading':
        rows = [children.get('reading')]
    elif part == 'writing':
        rows = [children.get('writingTask1'), children.get('writingTask2')]
    else:
        return AIQuestion.STATUS_READY
    statuses = [r.status if r else AIQuestion.STATUS_FAILED for r in rows]
    if any(s == AIQuestion.STATUS_FAILED for s in statuses):
        return AIQuestion.STATUS_FAILED
    if all(s == AIQuestion.STATUS_READY for s in statuses):
        return AIQuestion.STATUS_READY
    return AIQuestion.STATUS_GENERATING


def _aggregate_parent_status(children: dict) -> str:
    statuses = [children[s].status if children.get(s) else AIQuestion.STATUS_FAILED for s in MOCK_GEN_SLOTS]
    if any(s == AIQuestion.STATUS_FAILED for s in statuses):
        return AIQuestion.STATUS_FAILED
    if all(s == AIQuestion.STATUS_READY for s in statuses):
        return AIQuestion.STATUS_READY
    return AIQuestion.STATUS_GENERATING


def _part_fully_answered(part: str, children: dict) -> bool:
    if part == 'listening' or part == 'reading':
        child = children.get(part)
        return bool(child and child.user_answer_json is not None)
    if part == 'writing':
        t1, t2 = children.get('writingTask1'), children.get('writingTask2')
        return bool(t1 and t1.user_answer_json is not None and t2 and t2.user_answer_json is not None)
    if part == 'speaking':
        child = children.get('speaking')
        return bool(child and child.ai_feedback_json is not None)
    return False


def _part_partially_answered(part: str, children: dict) -> bool:
    if part == 'writing':
        t1, t2 = children.get('writingTask1'), children.get('writingTask2')
        return bool((t1 and t1.user_answer_json is not None) or (t2 and t2.user_answer_json is not None))
    return _part_fully_answered(part, children)


def _settle_exam(parent: AIQuestion, children: dict) -> tuple[dict, bool]:
    """读时清算：
    - in_progress 且子行已全部交卷 → submitted（子行提交发生在各科端点，父行只能读时收敛）
    - in_progress 且过了 deadline + 宽限 → 有部分作答记 submitted（没答的按 0 算），全空记 expired
    speaking 无 deadline，只走「有 summary → submitted」的推进。
    返回 (exam, changed)。
    """
    exam = dict(((parent.user_answer_json or {}).get('exam')) or {})
    changed = False
    now = timezone.now()
    for part in MOCK_PART_ORDER:
        st = dict(exam.get(part) or {})
        if st.get('status') != 'in_progress':
            continue
        if _part_fully_answered(part, children):
            st['status'] = 'submitted'
            st['submittedAt'] = now.isoformat()
            exam[part] = st
            changed = True
            continue
        deadline_raw = st.get('deadline')
        deadline = parse_datetime(deadline_raw) if deadline_raw else None
        if deadline and now > deadline + timedelta(seconds=MOCK_DEADLINE_GRACE_SEC):
            if _part_partially_answered(part, children):
                st['status'] = 'submitted'
                st['submittedAt'] = now.isoformat()
            else:
                st['status'] = 'expired'
                st['expiredAt'] = now.isoformat()
            exam[part] = st
            changed = True
    return exam, changed


def _write_exam(parent: AIQuestion, exam: dict) -> None:
    ua = dict(parent.user_answer_json or {})
    ua['exam'] = exam
    parent.user_answer_json = ua
    parent.save(update_fields=['user_answer_json'])


def _effective_part_status(part: str, exam: dict, children: dict) -> str:
    """前端大厅直接可用的部分状态：
    in_progress / submitted / forfeited / expired（已有考试状态）
    generating / gen_failed（生成未完 / 失败）
    locked（前面部分未结束）/ ready（可开始）
    """
    st = (exam.get(part) or {}).get('status')
    if st in TERMINAL_STATES or st == 'in_progress':
        return st
    gen = _gen_status_for_part(part, children)
    if gen == AIQuestion.STATUS_FAILED:
        return 'gen_failed'
    if gen != AIQuestion.STATUS_READY:
        return 'generating'
    idx = MOCK_PART_ORDER.index(part)
    prev_done = all(
        (exam.get(p) or {}).get('status') in TERMINAL_STATES
        for p in MOCK_PART_ORDER[:idx]
    )
    return 'ready' if prev_done else 'locked'


def _child_view(child: AIQuestion | None) -> dict | None:
    if child is None:
        return None
    band = None
    fb = child.ai_feedback_json
    if isinstance(fb, dict):
        # 各科反馈键位不同：听/读 mock 提交存 band；写作批改存 Overall_Band；口语 summary 存 overall
        raw_band = fb.get('band') or fb.get('Overall_Band') or fb.get('overallBand') or fb.get('overall')
        try:
            band = float(raw_band) if raw_band is not None else None
        except (TypeError, ValueError):
            band = None
    return {
        'id': child.id,
        'skill': child.skill,
        'subtype': child.subtype,
        'title': child.title,
        'status': child.status,
        'errorMessage': child.error_message or '',
        'isAnswered': child.user_answer_json is not None,
        'hasFeedback': child.ai_feedback_json is not None,
        'band': band,
    }


def _sanitize_config(data) -> dict:
    """生成配置快照（白名单字段）。task1Type 的 random 在此处解析定型，
    这样单科重生成会拿到与首次相同的图表类型。"""
    difficulty = str(data.get('difficulty') or '7.0')
    absurd = 'true' if str(data.get('absurdMode', 'false')).lower() == 'true' else 'false'
    task1_type = str(data.get('task1Type') or 'random').strip().lower()
    if task1_type not in _TASK1_VALID_TYPES:
        task1_type = random.choice(_TASK1_RANDOM_POOL)
    config = {
        'difficulty': difficulty,
        'absurdMode': absurd,
        'customPrompt': str(data.get('customPrompt') or '')[:2000],
        'readingTopic': str(data.get('readingTopic') or 'random').strip().lower(),
        'task1Type': task1_type,
        'task2Type': str(data.get('task2Type') or 'opinion').strip().lower(),
        'task2TopicCategory': str(data.get('task2TopicCategory') or 'all').strip().lower(),
    }
    for i in (1, 2, 3, 4):
        config[f'scenarioS{i}'] = str(data.get(f'scenarioS{i}') or 'random').strip().lower()
    return config


def _child_params_from_config(config: dict) -> dict[str, dict]:
    base = {
        'difficulty': config.get('difficulty', '7.0'),
        'absurdMode': config.get('absurdMode', 'false'),
        'customPrompt': config.get('customPrompt') or '',
    }
    listening = dict(base)
    for i in (1, 2, 3, 4):
        listening[f'scenarioS{i}'] = config.get(f'scenarioS{i}') or 'random'
    reading = dict(base) | {'topic': config.get('readingTopic') or 'random'}
    writing1 = {'type': config.get('task1Type') or 'line', 'customPrompt': base['customPrompt']}
    writing2 = {
        'type': config.get('task2Type') or 'opinion',
        'topic_category': config.get('task2TopicCategory') or 'all',
        'customPrompt': base['customPrompt'],
    }
    return {'listening': listening, 'reading': reading, 'writingTask1': writing1, 'writingTask2': writing2}


_SLOT_SPAWNERS = {
    'listening': spawn_full_listening,
    'reading': spawn_full_reading,
    'writingTask1': spawn_chart_task1,
    'writingTask2': spawn_task2,
}


def check_mock_child_submittable(child: AIQuestion) -> str | None:
    """全套模拟子行的提交闸门（submit_ai_question 调用）。

    返回 None = 放行；返回字符串 = 拒收原因（调用方转 403）。
    - 部分 in_progress 且未超 deadline+宽限 → 放行
    - in_progress 但已超时 → 顺手清算，然后拒收
    - 部分已结束：仅允许「已交卷内容补挂 AI 反馈」（写作批改 / 口语 summary 迟到场景）
    - 部分未开始 → 拒收（不可提前做）
    """
    parent = child.parent
    if parent is None or parent.skill != AIQuestion.SKILL_MOCK:
        return None
    part = _SKILL_TO_PART.get(child.skill)
    if part is None:
        return None
    children = _children_map(parent)
    exam, changed = _settle_exam(parent, children)
    if changed:
        _write_exam(parent, exam)
    st = exam.get(part) or {}
    status = st.get('status')
    if status == 'in_progress':
        deadline_raw = st.get('deadline')
        deadline = parse_datetime(deadline_raw) if deadline_raw else None
        if deadline and timezone.now() > deadline + timedelta(seconds=MOCK_DEADLINE_GRACE_SEC):
            exam2, _ = _settle_exam(parent, children)
            _write_exam(parent, exam2)
            return '该部分已超时，无法提交。'
        return None
    if status in TERMINAL_STATES:
        # 迟到的 AI 反馈（写作批改结果 / 口语 summary）允许补挂到已交卷内容上
        return None if child.user_answer_json is not None else '该部分已结束，不能再作答。'
    return '该部分尚未开始，不能作答。'


def mock_list_snapshot(parent: AIQuestion) -> dict:
    """题库卡片用的轻量快照：各槽位生成状态 + 四部分考试进度 + 派生总状态。"""
    children = _children_map(parent)
    exam = dict(((parent.user_answer_json or {}).get('exam')) or {})
    slots = {
        slot: (children[slot].status if children.get(slot) else AIQuestion.STATUS_FAILED)
        for slot in MOCK_GEN_SLOTS
    }
    fb = parent.ai_feedback_json
    return {
        'derivedStatus': _aggregate_parent_status(children),
        'slots': slots,
        'parts': {p: _effective_part_status(p, exam, children) for p in MOCK_PART_ORDER},
        'hasReport': fb is not None,
        'overall': fb.get('overall') if isinstance(fb, dict) else None,
    }


# ── 端点 ─────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mock_generate(request):
    """POST /api/mock/generate — 创建全套模拟：父行 + 点火 4 条 AI 生成（202）。

    口语不在此生成：真题库抽题免费且即时，开始口语部分时由会话建行流程完成。
    """
    try:
        limit = check_rate_limit(request.user.id, 'mock_full', max_calls=2, window=600)
        if limit:
            return limit
        # 粗余额预检：一套 = 4 条生成，欠费直接拦，避免生成半套
        if float(request.user.at_balance) <= 0:
            return Response({'error': f'AT 币余额不足({request.user.at_balance})，无法生成全套模拟。'}, status=400)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        config = _sanitize_config(request.data)
        custom_title = (request.data.get('customName') or request.data.get('customTitle') or '').strip()
        title = custom_title[:300] or f'IELTS 全套模拟 · {timezone.localdate().isoformat()}'

        parent = AIQuestion.objects.create(
            user=request.user,
            skill=AIQuestion.SKILL_MOCK,
            subtype='full',
            title=title,
            content_json={
                'kind': 'mock',
                'config': config,
                'parts': {slot: {'questionId': None} for slot in MOCK_GEN_SLOTS + ['speaking']},
            },
            status=AIQuestion.STATUS_GENERATING,
        )

        params_by_slot = _child_params_from_config(config)
        parts: dict[str, dict] = {}
        try:
            for slot in MOCK_GEN_SLOTS:
                row = _SLOT_SPAWNERS[slot](
                    user=request.user, provider=provider,
                    params=params_by_slot[slot], parent=parent,
                )
                parts[slot] = {'questionId': row.id}
        except Exception as exc:
            # 点火失败：父行标失败（已点火的子行让它跑完，整套删除时级联清理）
            AIQuestion.objects.filter(pk=parent.pk).update(
                status=AIQuestion.STATUS_FAILED,
                error_message=f'生成点火失败: {exc}'[:2000],
            )
            return Response({'error': f'生成启动失败: {exc}'}, status=500)

        parts['speaking'] = {'questionId': None}
        content = dict(parent.content_json or {})
        content['parts'] = parts
        parent.content_json = content
        parent.save(update_fields=['content_json'])

        return Response({'mockId': parent.id, 'status': parent.status, 'title': parent.title}, status=202)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mock_detail(request, pk: int):
    """GET /api/mock/<id> — 大厅数据：生成进度 + 考试状态机 + 各部分入口信息。

    读时收敛：生成聚合状态写回父行；超时的 in_progress 部分清算为 submitted/expired。
    """
    try:
        parent = _get_parent(request.user, pk)
    except AIQuestion.DoesNotExist:
        return Response({'error': '模拟考不存在'}, status=404)

    children = _children_map(parent)

    # 生成聚合写回（点火失败的父行保留手写 error_message）
    agg = _aggregate_parent_status(children)
    if agg != parent.status:
        AIQuestion.objects.filter(pk=parent.pk).update(status=agg)
        parent.status = agg

    exam, changed = _settle_exam(parent, children)
    if changed:
        _write_exam(parent, exam)

    parts_view: dict[str, dict] = {}
    for part in MOCK_PART_ORDER:
        st = dict(exam.get(part) or {})
        entry: dict = {
            'status': _effective_part_status(part, exam, children),
            'genStatus': _gen_status_for_part(part, children),
            'startedAt': st.get('startedAt'),
            'deadline': st.get('deadline'),
            'submittedAt': st.get('submittedAt'),
        }
        if part == 'writing':
            entry['task1'] = _child_view(children.get('writingTask1'))
            entry['task2'] = _child_view(children.get('writingTask2'))
        else:
            slot = part  # listening / reading / speaking 的 slot 与 part 同名
            entry['child'] = _child_view(children.get(slot))
        parts_view[part] = entry

    return Response({
        'id': parent.id,
        'title': parent.title,
        'status': parent.status,
        'errorMessage': parent.error_message or '',
        'createdAt': parent.created_at.isoformat() if parent.created_at else None,
        'config': (parent.content_json or {}).get('config') or {},
        'order': MOCK_PART_ORDER,
        'durations': MOCK_PART_DURATION_SEC,
        'graceSec': MOCK_DEADLINE_GRACE_SEC,
        'now': timezone.now().isoformat(),
        'parts': parts_view,
        'report': parent.ai_feedback_json,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mock_part_start(request, pk: int, part: str):
    """POST /api/mock/<id>/part/<part>/start — 开始（或续答）某部分。

    幂等：已 in_progress 时原样返回既有 deadline —— 刷新/断线重入不重置计时。
    校验：顺序强制（前面部分必须已结束）+ 该部分生成完毕 + 未做过。
    """
    if part not in MOCK_PART_ORDER:
        return Response({'error': f'未知部分: {part}'}, status=400)
    try:
        with transaction.atomic():
            parent = _get_parent(request.user, pk, for_update=True)
            children = _children_map(parent)
            exam, _ = _settle_exam(parent, children)

            st = dict(exam.get(part) or {})
            if st.get('status') == 'in_progress':
                _write_exam(parent, exam)  # 清算结果顺手落库
                return Response({
                    'part': part, 'exam': st, 'resumed': True,
                    'now': timezone.now().isoformat(),
                    'durationSec': MOCK_PART_DURATION_SEC[part],
                })
            if st.get('status') in TERMINAL_STATES:
                return Response({'error': '该部分已结束，不能再作答。'}, status=409)

            idx = MOCK_PART_ORDER.index(part)
            for prev in MOCK_PART_ORDER[:idx]:
                if (exam.get(prev) or {}).get('status') not in TERMINAL_STATES:
                    return Response({'error': '请按顺序作答：前面的部分尚未结束。'}, status=409)
            if _gen_status_for_part(part, children) != AIQuestion.STATUS_READY:
                return Response({'error': '该部分尚未生成完毕。'}, status=409)

            now = timezone.now()
            st = {'status': 'in_progress', 'startedAt': now.isoformat()}
            duration = MOCK_PART_DURATION_SEC[part]
            if duration:
                st['deadline'] = (now + timedelta(seconds=duration)).isoformat()
            exam[part] = st
            _write_exam(parent, exam)

        return Response({
            'part': part, 'exam': st, 'resumed': False,
            'now': timezone.now().isoformat(),
            'durationSec': duration,
        })
    except AIQuestion.DoesNotExist:
        return Response({'error': '模拟考不存在'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mock_part_forfeit(request, pk: int, part: str):
    """POST /api/mock/<id>/part/<part>/forfeit — 中途退出，该部分判 0。"""
    if part not in MOCK_PART_ORDER:
        return Response({'error': f'未知部分: {part}'}, status=400)
    try:
        with transaction.atomic():
            parent = _get_parent(request.user, pk, for_update=True)
            children = _children_map(parent)
            exam, _ = _settle_exam(parent, children)
            st = dict(exam.get(part) or {})
            if st.get('status') != 'in_progress':
                return Response({'error': '该部分不在作答中，无法弃权。'}, status=409)
            st['status'] = 'forfeited'
            st['forfeitedAt'] = timezone.now().isoformat()
            exam[part] = st
            _write_exam(parent, exam)
        return Response({'part': part, 'exam': st})
    except AIQuestion.DoesNotExist:
        return Response({'error': '模拟考不存在'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mock_finalize(request, pk: int):
    """POST /api/mock/<id>/finalize — 四部分全部结束后写入成绩单（幂等）。

    body: {'report': {'bands': {part: band}, 'overall': 6.5, ...}}
    分数由前端按各科结果计算（听/读换算表在前端，与单科结果页一致）。
    """
    try:
        with transaction.atomic():
            parent = _get_parent(request.user, pk, for_update=True)
            if parent.ai_feedback_json is not None:
                return Response({'report': parent.ai_feedback_json, 'already': True})

            children = _children_map(parent)
            exam, changed = _settle_exam(parent, children)
            if changed:
                _write_exam(parent, exam)
            unfinished = [
                p for p in MOCK_PART_ORDER
                if (exam.get(p) or {}).get('status') not in TERMINAL_STATES
            ]
            if unfinished:
                return Response({'error': f'尚有部分未结束: {", ".join(unfinished)}'}, status=409)

            report = request.data.get('report')
            if not isinstance(report, dict):
                return Response({'error': '缺少 report'}, status=400)
            bands = report.get('bands')
            if not isinstance(bands, dict):
                return Response({'error': 'report.bands 缺失'}, status=400)
            clean_bands = {}
            for p in MOCK_PART_ORDER:
                try:
                    clean_bands[p] = max(0.0, min(9.0, float(bands.get(p, 0) or 0)))
                except (TypeError, ValueError):
                    clean_bands[p] = 0.0
            try:
                overall = max(0.0, min(9.0, float(report.get('overall', 0) or 0)))
            except (TypeError, ValueError):
                overall = 0.0

            stored = {
                'bands': clean_bands,
                'overall': overall,
                'detail': report.get('detail') if isinstance(report.get('detail'), dict) else {},
                'finalizedAt': timezone.now().isoformat(),
            }
            now = timezone.now()
            parent.ai_feedback_json = stored
            if parent.answered_at is None:
                parent.answered_at = now
            parent.last_attempt_at = now
            parent.save(update_fields=['ai_feedback_json', 'answered_at', 'last_attempt_at'])
        return Response({'report': stored, 'already': False})
    except AIQuestion.DoesNotExist:
        return Response({'error': '模拟考不存在'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mock_part_regenerate(request, pk: int):
    """POST /api/mock/<id>/regenerate — 重新生成失败的槽位（body: {'slot': ...}）。

    仅允许：该槽位子行 failed（或缺失）、且对应考试部分尚未开始。
    用父行 config 快照重点火，保证与首次生成同配置（含已定型的 task1Type）。
    """
    slot = str(request.data.get('slot') or '')
    if slot not in MOCK_GEN_SLOTS:
        return Response({'error': f'未知槽位: {slot}'}, status=400)
    try:
        limit = check_rate_limit(request.user.id, 'mock_regen', max_calls=4, window=300)
        if limit:
            return limit
        with transaction.atomic():
            parent = _get_parent(request.user, pk, for_update=True)
            children = _children_map(parent)
            old = children.get(slot)
            if old is not None and old.status != AIQuestion.STATUS_FAILED:
                return Response({'error': '只允许重新生成失败的部分。'}, status=409)
            part = 'writing' if slot.startswith('writingTask') else slot
            exam = dict(((parent.user_answer_json or {}).get('exam')) or {})
            if (exam.get(part) or {}).get('status'):
                return Response({'error': '该部分已开始作答，不能重新生成。'}, status=409)

            config = (parent.content_json or {}).get('config') or {}
            params = _child_params_from_config(config)[slot]
            provider = request.headers.get('X-AI-Provider', 'deepseek')
            row = _SLOT_SPAWNERS[slot](user=request.user, provider=provider, params=params, parent=parent)

            content = dict(parent.content_json or {})
            parts = dict(content.get('parts') or {})
            parts[slot] = {'questionId': row.id}
            content['parts'] = parts
            parent.content_json = content
            parent.status = AIQuestion.STATUS_GENERATING
            parent.error_message = ''
            parent.save(update_fields=['content_json', 'status', 'error_message'])

        if old is not None:
            _cleanup_question_files(old)
            old.delete()
        return Response({'slot': slot, 'questionId': row.id, 'status': row.status}, status=202)
    except AIQuestion.DoesNotExist:
        return Response({'error': '模拟考不存在'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)
