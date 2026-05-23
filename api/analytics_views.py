from collections import defaultdict

from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import LearningPlan, VocabFSRS


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
                .order_by('-created_at')
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
