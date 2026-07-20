"""管理员全站学情分析。

两种视角（对应产品需求「看每个人 / 统计」）：
  - 全站统计  GET /admin/analytics/overview        —— 听/说/读/写/综合的聚合数据
  - 用户列表  GET /admin/analytics/users?search=   —— 供管理员挑选要下钻的用户
  - 用户下钻  GET /admin/analytics/user/<id>       —— 单个用户四科 + 综合明细

口径与用户自己的分析一致（见 api/analytics_views.py）：
  - reading/listening 只统计 subtype='full' 的 40 题全套卷；准确率逐题判定，
    band 用官方对照表换算（api/core/ielts_band.py，与前端同表）。
  - speaking / writing / mock 的 band 已在各自 ai_feedback_json / 批改结果里，直接取。
唯一差别是把 `user=request.user` 放开到「全站」或「指定用户」。
"""
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from api.models import AIQuestion, WritingServiceRecord
from api.analytics_views import _score_content
from api.core.ielts_band import raw_to_band, round_ielts_overall
from api.auth.admin_views import IsAdminUser

User = get_user_model()

RECENT_LIMIT = 20


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─────────────────────────── 全站统计 ───────────────────────────
def _skill_accuracy_overview(skill):
    """reading/listening 全站聚合：人次、参与人数、题数/答对、准确率、平均 band。"""
    qs = (
        AIQuestion.objects
        .filter(skill=skill, subtype='full')
        .exclude(user_answer_json__isnull=True)
        .only('content_json', 'user_answer_json', 'user_id')
    )
    attempts = questions = correct = 0
    band_sum = 0.0
    band_n = 0
    users = set()
    for aq in qs.iterator():
        c, t = _score_content(aq.content_json, aq.user_answer_json)
        attempts += 1
        questions += t
        correct += c
        users.add(aq.user_id)
        b = raw_to_band(skill, c, t)
        if b is not None:
            band_sum += b
            band_n += 1
    return {
        'attempts': attempts,
        'users': len(users),
        'questions': questions,
        'correct': correct,
        'accuracy': round(correct / questions, 4) if questions else 0.0,
        'avgBand': round(band_sum / band_n, 1) if band_n else None,
    }, users


def _band_overview(skill, count_key):
    """speaking / mock 全站聚合：从 ai_feedback_json.overall 取已存 band 求均值。"""
    qs = (
        AIQuestion.objects
        .filter(skill=skill, ai_feedback_json__isnull=False)
        .only('ai_feedback_json', 'user_id')
    )
    n = 0
    s = 0.0
    users = set()
    for q in qs.iterator():
        fb = q.ai_feedback_json
        if not isinstance(fb, dict):
            continue
        o = _f(fb.get('overall'))
        if o is None or o <= 0:
            continue
        n += 1
        s += o
        users.add(q.user_id)
    return {count_key: n, 'users': len(users), 'avgBand': round(s / n, 1) if n else None}, users


def _writing_overview():
    """writing 全站聚合：从批改结果 Overall_Band 求均值。"""
    qs = (
        WritingServiceRecord.objects
        .filter(service_type='correction')
        .only('content', 'user_id')
    )
    n = 0
    s = 0.0
    users = set()
    for rec in qs.iterator():
        c = rec.content
        if not isinstance(c, dict):
            continue
        res = c.get('result')
        if not isinstance(res, dict):
            continue
        o = _f(res.get('Overall_Band'))
        if o is None or o <= 0:
            continue
        n += 1
        s += o
        users.add(rec.user_id)
    return {'corrections': n, 'users': len(users), 'avgBand': round(s / n, 1) if n else None}, users


def compute_overview():
    active = set()
    reading, ru = _skill_accuracy_overview(AIQuestion.SKILL_READING)
    listening, lu = _skill_accuracy_overview(AIQuestion.SKILL_LISTENING)
    speaking, su = _band_overview(AIQuestion.SKILL_SPEAKING, 'sessions')
    writing, wu = _writing_overview()
    mock, mu = _band_overview(AIQuestion.SKILL_MOCK, 'exams')
    active |= ru | lu | su | wu | mu

    skill_bands = [x['avgBand'] for x in (reading, listening, speaking, writing) if x['avgBand'] is not None]
    overall_band = round_ielts_overall(sum(skill_bands) / len(skill_bands)) if skill_bands else None

    return {
        'users': {'total': User.objects.count(), 'active': len(active)},
        'reading': reading,
        'listening': listening,
        'speaking': speaking,
        'writing': writing,
        'mock': mock,
        'overall': {'avgBand': overall_band},
    }


class AdminAnalyticsOverviewView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(compute_overview())


# ─────────────────────────── 用户列表（供下钻挑人）───────────────────────────
class AdminAnalyticsUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminAnalyticsUserListView(APIView):
    """按活跃度（有作答的题数）倒序列出用户，支持 username/email/id 搜索。"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = (request.query_params.get('search') or '').strip()
        qs = User.objects.all()
        if search:
            cond = Q(username__icontains=search) | Q(email__icontains=search)
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)

        qs = qs.annotate(
            attempts=Count('ai_questions', filter=Q(ai_questions__answered_at__isnull=False)),
        ).order_by('-attempts', 'username')

        paginator = AdminAnalyticsUserPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [
            {
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'attempts': u.attempts,
                'date_joined': u.date_joined.isoformat() if u.date_joined else None,
                'last_login': u.last_login.isoformat() if u.last_login else None,
            }
            for u in page
        ]
        return paginator.get_paginated_response(data)


# ─────────────────────────── 单用户下钻 ───────────────────────────
def _skill_detail_for_user(user, skill):
    qs = (
        AIQuestion.objects
        .filter(user=user, skill=skill, subtype='full')
        .exclude(user_answer_json__isnull=True)
        .order_by('-answered_at')
    )
    attempts = questions = correct = 0
    band_sum = 0.0
    band_n = 0
    recent = []
    for aq in qs:
        c, t = _score_content(aq.content_json, aq.user_answer_json)
        attempts += 1
        questions += t
        correct += c
        b = raw_to_band(skill, c, t)
        if b is not None:
            band_sum += b
            band_n += 1
        if len(recent) < RECENT_LIMIT:
            recent.append({
                'id': aq.id,
                'title': aq.title or '',
                'date': aq.answered_at.isoformat() if aq.answered_at else None,
                'correct': c,
                'total': t,
                'band': b,
            })
    return {
        'attempts': attempts,
        'questions': questions,
        'correct': correct,
        'accuracy': round(correct / questions, 4) if questions else 0.0,
        'band': round(band_sum / band_n, 1) if band_n else None,
        'recent': recent,
    }


def _speaking_detail_for_user(user):
    qs = (
        AIQuestion.objects
        .filter(user=user, skill=AIQuestion.SKILL_SPEAKING, ai_feedback_json__isnull=False)
        .order_by('created_at')
    )
    trend = []
    s = 0.0
    n = 0
    dim_sums = defaultdict(float)
    dim_n = defaultdict(int)
    by_mode = defaultdict(int)
    for q in qs:
        fb = q.ai_feedback_json
        if not isinstance(fb, dict):
            continue
        o = _f(fb.get('overall'))
        if o is None or o <= 0:
            continue
        dims = {}
        rd = fb.get('dims')
        if isinstance(rd, dict):
            for k, v in rd.items():
                if isinstance(v, (int, float)):
                    dims[str(k)] = round(float(v), 1)
        mode = q.subtype or str(fb.get('mode') or '')
        when = q.last_attempt_at or q.answered_at or q.created_at
        trend.append({
            'id': q.id,
            'date': when.strftime('%m-%d %H:%M'),
            'mode': mode,
            'overall': round(o, 1),
            'dims': dims,
        })
        by_mode[mode] += 1
        s += o
        n += 1
        for k, v in dims.items():
            if v > 0:
                dim_sums[k] += v
                dim_n[k] += 1
    return {
        'sessions': n,
        'avgBand': round(s / n, 1) if n else None,
        'skills_avg': {k: round(dim_sums[k] / dim_n[k], 1) for k in dim_sums if dim_n[k] > 0},
        'by_mode': dict(by_mode),
        'trend': trend,
    }


def _writing_detail_for_user(user):
    records = (
        WritingServiceRecord.objects
        .filter(user=user, service_type='correction')
        .order_by('created_at')
    )
    trend = []
    band_sum = 0.0
    band_n = 0
    for rec in records:
        content = rec.content
        if not isinstance(content, dict):
            continue
        res = content.get('result')
        if not isinstance(res, dict):
            continue
        overall = _f(res.get('Overall_Band'))
        if overall is None or overall <= 0:
            continue
        band_sum += overall
        band_n += 1
        trend.append({
            'id': rec.id,
            'date': rec.created_at.strftime('%m-%d %H:%M'),
            'task': content.get('task_type', 'task2'),
            'overall': round(overall, 1),
        })
    return {
        'corrections': band_n,
        'avgBand': round(band_sum / band_n, 1) if band_n else None,
        'trend': trend,
    }


def _mock_detail_for_user(user):
    qs = (
        AIQuestion.objects
        .filter(user=user, skill=AIQuestion.SKILL_MOCK, ai_feedback_json__isnull=False)
        .order_by('-answered_at', '-id')
    )
    reports = []
    s = 0.0
    n = 0
    for q in qs[:RECENT_LIMIT]:
        fb = q.ai_feedback_json if isinstance(q.ai_feedback_json, dict) else {}
        overall = _f(fb.get('overall'))
        if overall is None:
            continue
        raw_bands = fb.get('bands') if isinstance(fb.get('bands'), dict) else {}
        bands = {str(k): round(float(v), 1) for k, v in raw_bands.items() if isinstance(v, (int, float))}
        when = q.answered_at or q.created_at
        reports.append({
            'id': q.id,
            'title': q.title or '',
            'date': when.isoformat() if when else None,
            'overall': round(overall, 1),
            'bands': bands,
        })
        s += overall
        n += 1
    return {
        'exams': n,
        'avgOverall': round(s / n, 1) if n else None,
        'reports': reports,
    }


def compute_user_detail(user):
    reading = _skill_detail_for_user(user, AIQuestion.SKILL_READING)
    listening = _skill_detail_for_user(user, AIQuestion.SKILL_LISTENING)
    speaking = _speaking_detail_for_user(user)
    writing = _writing_detail_for_user(user)
    mock = _mock_detail_for_user(user)

    summary = {
        'readingBand': reading['band'],
        'listeningBand': listening['band'],
        'speakingBand': speaking['avgBand'],
        'writingBand': writing['avgBand'],
    }
    bands = [b for b in summary.values() if b is not None]
    summary['overallBand'] = round_ielts_overall(sum(bands) / len(bands)) if bands else None

    return {
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'date_joined': user.date_joined.isoformat() if user.date_joined else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
        'reading': reading,
        'listening': listening,
        'speaking': speaking,
        'writing': writing,
        'mock': mock,
        'summary': summary,
    }


class AdminAnalyticsUserDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, user_id):
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        return Response(compute_user_detail(target))
