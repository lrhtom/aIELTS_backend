from collections import defaultdict

from django.db.models import Count, F
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import LearningPlan, VocabFSRS, WritingServiceRecord, AIQuestion


# ── AIQuestion scoring helpers (shared by PracticeAnalyticsView) ─────
def _extract_questions_from_content(content):
    """Return a flat list of question dicts from an AIQuestion.content_json.

    Handles single-type reading/listening AND full-test formats (reading with
    `passages[].sections[].questions`; listening with `sections[]` that may
    hold flat `questions` or `subsections[].questions`).
    """
    if not isinstance(content, dict):
        return []
    out = []
    # Reading full-test
    if isinstance(content.get('passages'), list):
        for p in content['passages']:
            if not isinstance(p, dict):
                continue
            for sec in (p.get('sections') or []):
                if isinstance(sec, dict):
                    for q in (sec.get('questions') or []):
                        if isinstance(q, dict):
                            out.append(q)
        return out
    # Listening full-test
    if content.get('type') == 'full' and isinstance(content.get('sections'), list):
        for sec in content['sections']:
            if not isinstance(sec, dict):
                continue
            flat = sec.get('questions')
            if isinstance(flat, list) and flat:
                for q in flat:
                    if isinstance(q, dict):
                        out.append(q)
                continue
            subs = sec.get('subsections')
            if isinstance(subs, list):
                for sub in subs:
                    if isinstance(sub, dict):
                        for q in (sub.get('questions') or []):
                            if isinstance(q, dict):
                                out.append(q)
        return out
    # Single-type
    qs = content.get('questions')
    if isinstance(qs, list):
        return [q for q in qs if isinstance(q, dict)]
    return []


def _score_one(q, user_ans_str):
    """True if the user's answer matches the question's expected answer(s).

    Rules:
      - If q has `answers` list (text-answer types): case-insensitive match to any variant.
      - Else if q has `answer` (letter/keyword types): case-insensitive match.
    """
    if not user_ans_str:
        return False
    u = user_ans_str.strip().lower()
    if not u:
        return False
    ans_list = q.get('answers')
    if isinstance(ans_list, list) and ans_list:
        return any(str(a).strip().lower() == u for a in ans_list)
    correct = q.get('answer')
    if correct is not None:
        return str(correct).strip().lower() == u
    return False


def _score_content(content, user_answer):
    """Return (correct, total) for one AIQuestion attempt."""
    questions = _extract_questions_from_content(content)
    total = len(questions)
    if not isinstance(user_answer, dict) or total == 0:
        return 0, total
    correct = 0
    for q in questions:
        qid = q.get('id')
        if qid is None:
            continue
        # user_answer may be keyed by int or str depending on JSON path.
        ans = user_answer.get(qid)
        if ans is None:
            ans = user_answer.get(str(qid))
        if _score_one(q, str(ans or '')):
            correct += 1
    return correct, total


class VocabAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plan_id = request.query_params.get('plan_id')
        if not plan_id:
            plans = (
                LearningPlan.objects
                .filter(user=request.user)
                .annotate(word_count=Count('entries'))
                .values('id', 'name', 'word_count')
                # 收藏优先：已收藏排最前，后收藏的更靠前；其余按创建时间倒序（与前端下拉框口径一致）。
                .order_by(F('favorited_at').desc(nulls_last=True), '-created_at')
            )
            return Response({'plans': list(plans)})

        try:
            plan = LearningPlan.objects.get(id=int(plan_id), user=request.user)
        except (LearningPlan.DoesNotExist, ValueError):
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)

        total_words = plan.entries.count()

        if total_words == 0:
            return Response({
                'plan': {'id': plan.id, 'name': plan.name, 'word_count': 0},
                'scheduled_distribution': [],
                'state_distribution': [],
                'total_studied': 0,
            })

        # 只统计当前计划中实际存在的单词，排除已从计划删除但 FSRS 记录残留的幽灵卡片
        plan_words = set(plan.entries.values_list('word', flat=True))
        cards = VocabFSRS.objects.filter(
            user=request.user,
            plan_id=plan.id,
            word__in=plan_words,
        )

        total_studied = cards.exclude(state=0).count()

        # 复习间隔分布：距下次复习还剩多少天（due - now）
        # 负数 = 已过期待复习，0 = 今天，正数 = 未来
        import math
        from django.utils import timezone
        now = timezone.now()
        sched = defaultdict(int)
        for card in cards:
            if card.state == 0:
                continue
            diff_days = math.ceil((card.due - now).total_seconds() / 86400)
            sched[diff_days] += 1

        scheduled_distribution = [
            {'days': d, 'count': c}
            for d, c in sorted(sched.items())
        ]

        # 娴熟度分布：基于 FSRS stability（记忆稳定性天数）分级
        # stability 表示在当前稳定性下，记忆保留率降到 90% 时需要的天数
        MASTERY_LEVELS = [
            # (level, label, min_stability, max_stability)
            (0, 'unlearned',  None, None),   # 未学习（无 FSRS 记录或 state=0）
            (1, 'beginner',   0,    3),      # 初识：stability < 3天
            (2, 'familiar',   3,    14),     # 熟悉：3-14天
            (3, 'solid',      14,   60),     # 巩固：14-60天
            (4, 'mastered',   60,   150),    # 掌握：60-150天
            (5, 'expert',     150,  None),   # 精通：>150天
        ]
        mastery = {lvl: 0 for lvl in range(6)}

        fsrs_word_count = 0
        for card in cards:
            fsrs_word_count += 1
            if card.state == 0:
                mastery[0] += 1
                continue
            s = card.stability
            if s < 3:
                mastery[1] += 1
            elif s < 14:
                mastery[2] += 1
            elif s < 60:
                mastery[3] += 1
            elif s < 150:
                mastery[4] += 1
            else:
                mastery[5] += 1

        # 计划中没有 FSRS 记录的单词视为未学习
        if total_words > fsrs_word_count:
            mastery[0] += total_words - fsrs_word_count

        labels = ['unlearned', 'beginner', 'familiar', 'solid', 'mastered', 'expert']
        state_distribution = [
            {'state': lvl, 'label': labels[lvl], 'count': mastery[lvl]}
            for lvl in range(6)
        ]

        return Response({
            'plan': {'id': plan.id, 'name': plan.name, 'word_count': total_words},
            'total_studied': total_studied,
            'scheduled_distribution': scheduled_distribution,
            'state_distribution': state_distribution,
        })


class ScheduledWordsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            days_str = request.query_params.get('days')
            plan_id = request.query_params.get('plan_id')

            if days_str is None:
                return Response({'error': 'Missing days parameter'}, status=status.HTTP_400_BAD_REQUEST)
            days = int(days_str)
            
            now = timezone.now()
            
            qs = VocabFSRS.objects.filter(user=request.user).exclude(state=0)
            
            if plan_id:
                try:
                    plan = LearningPlan.objects.get(id=int(plan_id), user=request.user)
                    plan_words = set(plan.entries.values_list('word', flat=True))
                    qs = qs.filter(plan_id=plan.id, word__in=plan_words)
                except (LearningPlan.DoesNotExist, ValueError):
                    pass
            
            if days == 0:
                cards = qs.filter(due__lte=now)
            else:
                lower_bound = now + timezone.timedelta(days=days-1)
                upper_bound = now + timezone.timedelta(days=days)
                cards = qs.filter(due__gt=lower_bound, due__lte=upper_bound)
                
            words = list(cards.values('word', 'zh'))
            # deduplicate
            seen = set()
            unique_words = []
            for w in words:
                if w['word'] not in seen:
                    seen.add(w['word'])
                    unique_words.append(w)
            
            return Response({'words': unique_words}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class WritingAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = WritingServiceRecord.objects.filter(
            user=request.user,
            service_type='correction'
        ).order_by('created_at')

        task1_trend = []
        task2_trend = []
        
        t1_tr_sum = t1_cc_sum = t1_lr_sum = t1_gra_sum = 0
        t1_count = 0
        
        t2_tr_sum = t2_cc_sum = t2_lr_sum = t2_gra_sum = 0
        t2_count = 0

        for rec in records:
            content = rec.content
            if not isinstance(content, dict): continue
            res = content.get('result')
            if not res: continue
            
            task_type = content.get('task_type', 'task2')
            # format as MM-DD HH:MM
            date_str = rec.created_at.strftime('%m-%d %H:%M')
            score = res.get('Overall_Band', 0)
            
            # Use Task_Response or Task_Achievement based on what's available
            tr_score = res.get('Task_Response', 0) or res.get('Task_Achievement', 0)
            cc_score = res.get('Coherence_Cohesion', 0)
            lr_score = res.get('Lexical_Resource', 0)
            gra_score = res.get('Grammatical_Range', 0)
            
            if score > 0:
                record_data = {
                    'id': rec.id,
                    'date': date_str,
                    'overall': round(score, 1),
                    'tr': round(tr_score, 1) if tr_score else None,
                    'cc': round(cc_score, 1) if cc_score else None,
                    'lr': round(lr_score, 1) if lr_score else None,
                    'gra': round(gra_score, 1) if gra_score else None,
                }
                if task_type == 'task1':
                    task1_trend.append(record_data)
                else:
                    task2_trend.append(record_data)
            
            if tr_score > 0 and cc_score > 0 and lr_score > 0 and gra_score > 0:
                if task_type == 'task1':
                    t1_tr_sum += tr_score
                    t1_cc_sum += cc_score
                    t1_lr_sum += lr_score
                    t1_gra_sum += gra_score
                    t1_count += 1
                else:
                    t2_tr_sum += tr_score
                    t2_cc_sum += cc_score
                    t2_lr_sum += lr_score
                    t2_gra_sum += gra_score
                    t2_count += 1
                
        task1_skills_avg = {
            'tr': round(t1_tr_sum / t1_count, 1) if t1_count > 0 else 0,
            'cc': round(t1_cc_sum / t1_count, 1) if t1_count > 0 else 0,
            'lr': round(t1_lr_sum / t1_count, 1) if t1_count > 0 else 0,
            'gra': round(t1_gra_sum / t1_count, 1) if t1_count > 0 else 0,
        }
        
        task2_skills_avg = {
            'tr': round(t2_tr_sum / t2_count, 1) if t2_count > 0 else 0,
            'cc': round(t2_cc_sum / t2_count, 1) if t2_count > 0 else 0,
            'lr': round(t2_lr_sum / t2_count, 1) if t2_count > 0 else 0,
            'gra': round(t2_gra_sum / t2_count, 1) if t2_count > 0 else 0,
        }
        
        return Response({
            'task1_trend': task1_trend,
            'task2_trend': task2_trend,
            'task1_skills_avg': task1_skills_avg,
            'task2_skills_avg': task2_skills_avg,
            'total_corrections': t1_count + t2_count
        })


# ── Speaking session analytics ───────────────────────────────────────
class SpeakingAnalyticsView(APIView):
    """GET /api/analytics/speaking

    数据源 = AI 题库里的 speaking 会话，且只统计已生成 summary 报告的行
    （ai_feedback_json 非空）——聊到一半退出、没出总结界面的会话不计入。

    ai_feedback_json 由前端报告页写入，schema:
      { "mode": "part1", "overall": 6.5,
        "dims": {"accuracy":6,"pronunciation":6.5,...}, "rounds": 8 }

    Response:
    {
        "trend": [ {id, date, mode, overall, dims{...}} ... ]  # 时间升序
        "skills_avg": { dim: 均分 },   # 各维度跨会话平均（>0 的才计）
        "by_mode": { mode: 次数 },
        "total_sessions": N
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = AIQuestion.objects.filter(
            user=request.user,
            skill=AIQuestion.SKILL_SPEAKING,
            ai_feedback_json__isnull=False,
        ).order_by('created_at')

        trend = []
        dim_sums = defaultdict(float)
        dim_counts = defaultdict(int)
        by_mode = defaultdict(int)

        for q in rows:
            fb = q.ai_feedback_json
            if not isinstance(fb, dict):
                continue
            try:
                overall = float(fb.get('overall', 0))
            except (TypeError, ValueError):
                continue
            if overall <= 0:
                continue

            raw_dims = fb.get('dims')
            dims = {}
            if isinstance(raw_dims, dict):
                for k, v in raw_dims.items():
                    if isinstance(v, (int, float)):
                        dims[str(k)] = round(float(v), 1)

            mode = q.subtype or str(fb.get('mode') or '')
            when = q.last_attempt_at or q.answered_at or q.created_at
            trend.append({
                'id': q.id,
                'date': when.strftime('%m-%d %H:%M'),
                'mode': mode,
                'overall': round(overall, 1),
                'dims': dims,
            })
            by_mode[mode] += 1
            for k, v in dims.items():
                if v > 0:
                    dim_sums[k] += v
                    dim_counts[k] += 1

        skills_avg = {
            k: round(dim_sums[k] / dim_counts[k], 1)
            for k in dim_sums if dim_counts[k] > 0
        }

        return Response({
            'trend': trend,
            'skills_avg': skills_avg,
            'by_mode': dict(by_mode),
            'total_sessions': len(trend),
        })


# ── Reading + Listening practice accuracy analytics ──────────────────
class PracticeAnalyticsView(APIView):
    """GET /api/analytics/practice

    2026-07-17 起统计口径（用户规格）：听/读只统计**完整 40 题全套卷**
    （subtype='full'，含全套模拟的子卷），单题型/单篇/单 section 不计入；
    展示层按雅思 9 分制换算（换算表在前端 utils/ielts_band.ts，后端只给 correct/total）。

    Aggregates per-skill accuracy from full-set AIQuestion attempts:
      - Overall: total_questions, correct_questions, accuracy, attempts
      - By subtype: attempts, total, correct, accuracy
      - Recent attempts: last 20 with per-attempt correct/total/accuracy

    Response shape:
    {
        "reading":  { total_questions, correct_questions, accuracy, attempts,
                       by_type: [...], recent: [...] },
        "listening": { ... },
        "combined": { total_questions, correct_questions, accuracy, attempts },
        "mock": { "total": N, "reports": [ {id, title, date, overall, bands} ... ] }
    }
    """
    permission_classes = [IsAuthenticated]

    RECENT_LIMIT = 20

    def get(self, request):
        results = {}
        combined_total = 0
        combined_correct = 0
        combined_attempts = 0

        for skill in (AIQuestion.SKILL_READING, AIQuestion.SKILL_LISTENING):
            qs = (
                AIQuestion.objects
                .filter(user=request.user, skill=skill, subtype='full')
                .exclude(user_answer_json__isnull=True)
                .order_by('-answered_at')
            )
            attempts_list = list(qs)

            total_questions = 0
            total_correct = 0
            recent = []
            by_type = defaultdict(lambda: {'attempts': 0, 'correct': 0, 'total': 0})

            for aq in attempts_list:
                correct, total = _score_content(aq.content_json, aq.user_answer_json)
                total_questions += total
                total_correct += correct
                subtype = (aq.subtype or 'unknown').strip() or 'unknown'
                by_type[subtype]['attempts'] += 1
                by_type[subtype]['correct'] += correct
                by_type[subtype]['total'] += total
                if len(recent) < self.RECENT_LIMIT:
                    recent.append({
                        'id': aq.id,
                        'title': aq.title or '',
                        'subtype': subtype,
                        'date': aq.answered_at.isoformat() if aq.answered_at else None,
                        'correct': correct,
                        'total': total,
                        'accuracy': round(correct / total, 4) if total > 0 else 0.0,
                    })

            attempts_count = len(attempts_list)
            combined_total += total_questions
            combined_correct += total_correct
            combined_attempts += attempts_count

            # Sort by_type descending by attempts for stable display
            by_type_list = [
                {
                    'subtype': subtype,
                    'attempts': stats['attempts'],
                    'total': stats['total'],
                    'correct': stats['correct'],
                    'accuracy': round(stats['correct'] / stats['total'], 4) if stats['total'] > 0 else 0.0,
                }
                for subtype, stats in by_type.items()
            ]
            by_type_list.sort(key=lambda x: (-x['attempts'], x['subtype']))

            results[skill] = {
                'total_questions': total_questions,
                'correct_questions': total_correct,
                'accuracy': round(total_correct / total_questions, 4) if total_questions > 0 else 0.0,
                'attempts': attempts_count,
                'by_type': by_type_list,
                'recent': recent,
            }

        results['combined'] = {
            'total_questions': combined_total,
            'correct_questions': combined_correct,
            'accuracy': round(combined_correct / combined_total, 4) if combined_total > 0 else 0.0,
            'attempts': combined_attempts,
        }

        # ── 全套模拟总分统计：已 finalize 的成绩单（ai_feedback_json={bands, overall}）──
        mock_reports = []
        mock_qs = (
            AIQuestion.objects
            .filter(user=request.user, skill=AIQuestion.SKILL_MOCK)
            .exclude(ai_feedback_json__isnull=True)
            .order_by('-answered_at', '-id')
        )
        for q in mock_qs[:self.RECENT_LIMIT]:
            fb = q.ai_feedback_json if isinstance(q.ai_feedback_json, dict) else {}
            overall = fb.get('overall')
            if not isinstance(overall, (int, float)):
                continue
            raw_bands = fb.get('bands') if isinstance(fb.get('bands'), dict) else {}
            bands = {
                str(k): round(float(v), 1)
                for k, v in raw_bands.items()
                if isinstance(v, (int, float))
            }
            when = q.answered_at or q.created_at
            mock_reports.append({
                'id': q.id,
                'title': q.title or '',
                'date': when.isoformat() if when else None,
                'overall': round(float(overall), 1),
                'bands': bands,
            })
        results['mock'] = {
            'total': len(mock_reports),
            'reports': mock_reports,
        }
        return Response(results)
