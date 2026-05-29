from datetime import timedelta

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import (
    LearningPlan, LearningPlanEntry,
    Notebook, NotebookWord,
    VocabBook, Word, WordBookMembership,
    VocabFSRS, UserDailyLearningTime,
    ArticleCopyCache, StoryModeCache,
)
from api.core.ai_client import AIClient
from api.core.rate_limit import check_rate_limit
import json
from api.vocab.vocab_views import (
    _card_to_dict,
    _sync_notebook_mastery,
    _word_map as _build_word_map,
)
from api.core.fsrs_utils import _USER_TZ, _next_day_midnight

def _user_today():
    """返回国际 0 点线（UTC+0）的今日 date。"""
    return timezone.now().astimezone(_USER_TZ).date()


def _has_activity_today(cards: list[VocabFSRS], today=None) -> bool:
    """是否存在今日已学习（有 last_review）的卡片，不区分 state。"""
    if today is None:
        today = _user_today()
    return any(
        c.last_review is not None and c.last_review.astimezone(_USER_TZ).date() == today
        for c in cards
    )


# 
# 核心 FSRS 选卡逻辑
# 

def _build_today_summary(plan: LearningPlan, all_cards: list[VocabFSRS]):
    """
        根据该计划下的所有卡片，按 FSRS 规则分发并截出「今日需学习计划」。
        返回：
      studied_today_cards : 今日已毕业的卡片(state=2)
            session_cards       : 接下来需要的卡片（受 daily_count 限制）
      stats               : 各类卡片统计
    """
    now = timezone.now()
    today = _user_today()
    start_of_today_utc = now.astimezone(_USER_TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    studied_today_cards = [
        c for c in all_cards
        if c.last_review is not None
        and c.last_review.astimezone(_USER_TZ).date() == today
        and c.state == 2
    ]
    studied_today = len(studied_today_cards)
    remaining_today = max(0, plan.daily_count - studied_today)

    due_cards = [c for c in all_cards if c.state != 0 and c.due <= now]
    carryover_cards = sorted(
        [
            c for c in all_cards
            if c.state in (1, 3) and c.due > now
            and c.last_review is not None and c.last_review >= start_of_today_utc
        ],
        key=lambda c: c.due,
    )
    new_cards = [c for c in all_cards if c.state == 0]
    pending_cards = sorted(
        [
            c for c in all_cards
            if c.state != 0 and c.due > now
            and (c.last_review is None or c.last_review < start_of_today_utc)
        ],
        key=lambda c: c.due,
    )

    # 组装 Session 队列
    session_cards = list(carryover_cards)
    
    # 还能塞入多少新卡/到期卡：当日剩余名额扣除已塞入的（如 carryover）
    remaining_space = remaining_today - len(session_cards)
    due_to_add = due_cards[:remaining_space] if remaining_space > 0 else []
    session_cards.extend(due_to_add)

    new_quota = remaining_today - len(session_cards)
    if new_quota > 0 and new_cards:
        sorted_new_cards = sorted(new_cards, key=lambda c: (c.due, c.word))
        session_cards.extend(sorted_new_cards[:new_quota])

    # 边界截断保护：队列最大长度理应为 remaining_today。只有 carryover 可能导致超出。
    # 若超出，则截断多余项（优先保留 carryover 和 due）。
    if len(session_cards) > remaining_today:
        def priority(card):
            if card in carryover_cards: return (0, card.due)
            if card in due_cards:       return (1, card.due)
            return (2, card.due)
        # 注意：如果 carryover 本身数量就 > remaining_today，我们不强行截掉 carryover。
        # 但如果是由于其他逻辑导致超标，则截掉优先级低的项。
        safe_limit = max(remaining_today, len(carryover_cards))
        session_cards = sorted(session_cards, key=priority)[:safe_limit]

    stats = {
        'total':           len(all_cards),
        'due':             len(due_cards),
        'carryover':       len(carryover_cards),
        'new':             len(new_cards),
        'pending':         len(pending_cards),
        'studied_today':   studied_today,
        'remaining_today': remaining_today,
    }
    return studied_today_cards, session_cards, stats


# 
# Serialisers
# 

def _plan_dict(plan: LearningPlan, word_count: int | None = None, user=None, detail=False) -> dict:
    today = _user_today()
    studied_today = 0
    studied_total = 0
    has_activity_today = False
    today_target = 0
    today_words: list[dict] = []
    
    if user:
        # 使用统一的 FSRS 分发逻辑，保证列表页和详情页口径一致。
        all_cards = list(VocabFSRS.objects.filter(user=user, plan_id=plan.pk).order_by('due'))
        studied_cards, session_cards, _ = _build_today_summary(plan, all_cards)
        has_activity_today = _has_activity_today(all_cards, today=today)

        studied_today = len(studied_cards)
        studied_total = sum(1 for c in all_cards if c.state != 0)
        today_target = studied_today + len(session_cards)

        # 计划尚未初始化 FSRS 卡片时，按词表规模裁剪今日目标（不改用户 daily_count 配置）。
        effective_word_count = word_count if word_count is not None else plan.entries.count()
        if not all_cards and effective_word_count > 0:
            today_target = min(plan.daily_count, effective_word_count)

        if detail:
            # 详情页：显示“今天的全部学习计划”（已学 + 待学队列）
            today_cards = studied_cards + session_cards

            # 获取发音
            words = [c.word for c in today_cards]
            wmap = _build_word_map(words) if words else {}

            today_words = [
                {
                    'word':     c.word,
                    'zh':       c.zh,
                    'state':    c.state,
                    'reps':     c.reps,
                    'phonetic': (wmap.get(c.word).phonetic or '') if wmap.get(c.word) else '',
                }
                for c in today_cards
            ]

    # 防御：显示目标至少不小于当日已学，避免出现“已学 > 目标”。
    today_target = max(today_target, studied_today)
    return {
        'id':             plan.pk,
        'name':           plan.name,
        'daily_count':    plan.daily_count,
        'has_activity_today': has_activity_today,
        'today_target':   today_target,
        'default_mode':   plan.default_mode,
        'mastery_target': plan.mastery_target,
        'copy_repetitions': plan.copy_repetitions,
        'copy_review_days': plan.copy_review_days,
        'article_review_days': plan.article_review_days,
        'word_count':     word_count if word_count is not None else plan.entries.count(),
        'studied_today':  studied_today,
        'studied_total':  studied_total,
        'today_words':    today_words,
        'created_at':     plan.created_at.isoformat(),
        'updated_at':     plan.updated_at.isoformat(),
    }


def _entry_dict(
    entry: LearningPlanEntry,
    fsrs_map: dict | None = None,
    word_map: dict | None = None,
) -> dict:
    fsrs = fsrs_map.get(entry.word) if fsrs_map is not None else None
    w    = word_map.get(entry.word) if word_map is not None else None
    return {
        'id':                   entry.pk,
        'word':                 entry.word,
        'zh':                   entry.zh,
        'added_at':             entry.added_at.isoformat(),
        'fsrs_due':             fsrs.due.isoformat() if fsrs else None,
        'fsrs_state':           fsrs.state if fsrs else 0,
        'fsrs_scheduled_days':  fsrs.scheduled_days if fsrs else 0,
        # Word enrichment
        'phonetic':             (w.phonetic or '') if w else '',
        'grammar':              (w.grammar or '') if w else '',
        'definitions':          w.definitions if w else [],
        'examples':             w.examples if w else [],
    }


def _build_fsrs_map(user, words: list[str], plan_id: int = 0) -> dict:
    """Return {word: VocabFSRS} for the given word list, scoped to plan_id."""
    return {c.word: c for c in VocabFSRS.objects.filter(user=user, word__in=words, plan_id=plan_id)}


class LearningTimeTodayView(APIView):
    """GET / POST /learning-time/today/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = _user_today()
        row = UserDailyLearningTime.objects.filter(
            user=request.user,
            study_date=today,
        ).only('total_seconds').first()
        return Response({
            'study_date': today.isoformat(),
            'total_seconds': row.total_seconds if row else 0,
        })

    def post(self, request):
        today = _user_today()

        try:
            elapsed_seconds = int(request.data.get('elapsed_seconds', 0))
        except (TypeError, ValueError):
            return Response({'error': 'elapsed_seconds 必须是非负整数'}, status=status.HTTP_400_BAD_REQUEST)

        if elapsed_seconds < 0:
            return Response({'error': 'elapsed_seconds 必须是非负整数'}, status=status.HTTP_400_BAD_REQUEST)

        # Guard against accidental huge payloads.
        elapsed_seconds = min(elapsed_seconds, 24 * 3600)

        row, _ = UserDailyLearningTime.objects.get_or_create(
            user=request.user,
            study_date=today,
            defaults={'total_seconds': 0},
        )

        if elapsed_seconds > 0:
            row.total_seconds += elapsed_seconds
            row.save(update_fields=['total_seconds', 'updated_at'])

        return Response({
            'study_date': today.isoformat(),
            'total_seconds': row.total_seconds,
        })


# 
# Plan CRUD
# 

class PlanListView(APIView):
    """GET / POST  /plans/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plans = (
            LearningPlan.objects
            .filter(user=request.user)
            .annotate(wc=Count('entries'))
            .order_by('created_at')
        )
        return Response({'plans': [_plan_dict(p, p.wc, user=request.user) for p in plans]})

    def post(self, request):
        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': '计划名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 50:
            return Response({'error': '计划名称不能超过50个字符'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            daily_count = int(request.data.get('daily_count', 20))
            if not (1 <= daily_count <= 200):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': '每日学习词数必须在 1-200 之间'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = LearningPlan(
                user=request.user,
                name=name,
                daily_count=daily_count,
                complete_difficulty='hint',
            )
            plan.save()
        except Exception as e:
            msg = str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'plan': _plan_dict(plan, 0, user=request.user)}, status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    """GET / PATCH / DELETE  /plans/:id/"""
    permission_classes = [IsAuthenticated]

    def _get_plan(self, pk, user):
        return get_object_or_404(LearningPlan, pk=pk, user=user)

    def get(self, request, pk):
        plan = self._get_plan(pk, request.user)
        return Response({'plan': _plan_dict(plan, user=request.user, detail=True)})

    def patch(self, request, pk):
        plan = self._get_plan(pk, request.user)

        today_lock_checked = False
        has_activity_today = False

        def _is_today_locked() -> bool:
            nonlocal today_lock_checked, has_activity_today
            if today_lock_checked:
                return has_activity_today

            cards = list(
                VocabFSRS.objects
                .filter(user=request.user, plan_id=plan.pk)
                .exclude(last_review__isnull=True)
                .only('last_review')
            )
            has_activity_today = _has_activity_today(cards)
            today_lock_checked = True
            return has_activity_today

        if 'name' in request.data:
            name = request.data['name'].strip()
            if not name:
                return Response({'error': '计划名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
            plan.name = name
        if 'daily_count' in request.data:
            try:
                daily_count = int(request.data['daily_count'])
                if not (1 <= daily_count <= 200):
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': '每日学习词数必须在 1-200 之间'}, status=status.HTTP_400_BAD_REQUEST)

            # 仅当“实际变更每日词数时”，才执行今日学习锁定规则。
            if daily_count != plan.daily_count:
                if _is_today_locked():
                    return Response(
                        {'error': '今日已学习过单词，今日不能修改每日词数，请明天再调整。'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                plan.daily_count = daily_count
        if 'default_mode' in request.data:
            default_mode = str(request.data['default_mode']).strip().lower()
            if default_mode not in {'flashcard', 'choice', 'write', 'copy', 'article_copy', 'story_mode'}:
                return Response({'error': 'default_mode 必须是 flashcard/choice/write/copy/article_copy/story_mode 之一'}, status=status.HTTP_400_BAD_REQUEST)
            plan.default_mode = default_mode
        if 'mastery_target' in request.data:
            try:
                target = int(request.data['mastery_target'])
                if not (1 <= target <= 5):
                    raise ValueError
                plan.mastery_target = target
            except (TypeError, ValueError):
                return Response({'error': '连续答对目标次数必须在 1-5 之间'}, status=status.HTTP_400_BAD_REQUEST)
        if 'copy_repetitions' in request.data:
            try:
                repeats = int(request.data['copy_repetitions'])
                if not (1 <= repeats <= 20):
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': '抄写次数必须在 1-20 之间'}, status=status.HTTP_400_BAD_REQUEST)

            if repeats != plan.copy_repetitions:
                plan.copy_repetitions = repeats

        if 'copy_review_days' in request.data:
            try:
                review_days = int(request.data['copy_review_days'])
                if not (0 <= review_days <= 365):
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': '复习间隔天数必须在 0-365 之间'}, status=status.HTTP_400_BAD_REQUEST)

            if review_days != plan.copy_review_days:
                if _is_today_locked():
                    return Response(
                        {'error': '今日已学习过单词，今日不能修改抄写配置，请明天再调整。'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                plan.copy_review_days = review_days

        if 'article_review_days' in request.data:
            try:
                article_days = int(request.data['article_review_days'])
                if not (0 <= article_days <= 365):
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': '文章抄写复习间隔天数必须在 0-365 之间'}, status=status.HTTP_400_BAD_REQUEST)
            plan.article_review_days = article_days

        # bypass full_clean (no new-plan limit check on update)
        LearningPlan.objects.filter(pk=plan.pk).update(
            name=plan.name, daily_count=plan.daily_count,
            default_mode=plan.default_mode,
            mastery_target=plan.mastery_target,
            copy_repetitions=plan.copy_repetitions,
            copy_review_days=plan.copy_review_days,
            article_review_days=plan.article_review_days,
        )
        plan.refresh_from_db()
        return Response({'plan': _plan_dict(plan, user=request.user)})

    def delete(self, request, pk):
        plan = self._get_plan(pk, request.user)
        plan_pk = plan.pk
        plan.delete()
        # Cards are plan-scoped; delete them all when plan is deleted
        VocabFSRS.objects.filter(user=request.user, plan_id=plan_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# Plan word list
# 

class PlanWordListView(APIView):
    """GET / POST  /plans/:id/words/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        entries = list(plan.entries.order_by('-added_at'))

        q = request.query_params.get('q', '').strip().lower()
        if q:
            entries = [e for e in entries if q in e.word or q in e.zh.lower()]

        words    = [e.word for e in entries]
        fsrs_map = _build_fsrs_map(request.user, words, plan_id=plan.pk)
        word_map = _build_word_map(words)
        return Response({'entries': [_entry_dict(e, fsrs_map, word_map) for e in entries]})

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        mode = request.data.get('mode', 'manual')

        if mode == 'manual':
            return self._add_manual(plan, request.data)
        elif mode == 'notebook':
            return self._add_from_notebook(plan, request.data, request.user)
        elif mode == 'book_all':
            return self._add_from_book_all(plan, request.data)
        elif mode == 'book_range':
            return self._add_from_book_range(plan, request.data)
        elif mode == 'book_select':
            return self._add_from_book_select(plan, request.data)
        else:
            return Response({'error': f'未知 mode: {mode}'}, status=status.HTTP_400_BAD_REQUEST)

    # manual
    def _add_manual(self, plan, data):
        word_str = data.get('word', '').strip().lower()
        if not word_str:
            return Response({'error': '单词不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        zh = data.get('zh', '').strip()

        # Update optional Word enrichment data - only fill in fields that are currently empty
        # to avoid overwriting official imported data with user-provided values
        word_obj, _ = Word.objects.get_or_create(word=word_str)
        word_fields = []
        if data.get('phonetic', '').strip() and not word_obj.phonetic:
            word_obj.phonetic = data['phonetic'].strip()
            word_fields.append('phonetic')
        if data.get('grammar', '').strip() and not word_obj.grammar:
            word_obj.grammar = data['grammar'].strip()
            word_fields.append('grammar')
        raw_examples = data.get('examples')
        if isinstance(raw_examples, list) and raw_examples and not word_obj.examples:
            word_obj.examples = raw_examples
            word_fields.append('examples')
        if word_fields:
            word_obj.save(update_fields=word_fields)

        entry, created = LearningPlanEntry.objects.get_or_create(
            plan=plan, word=word_str, defaults={'zh': zh}
        )
        if not created:
            return Response({'error': '该单词已在计划中'}, status=status.HTTP_409_CONFLICT)

        word_map = {word_str: word_obj}
        return Response({'entries_added': 1, 'entry': _entry_dict(entry, None, word_map)}, status=status.HTTP_201_CREATED)

    # notebook
    def _add_from_notebook(self, plan, data, user):
        notebook_id = data.get('notebook_id')
        nb = get_object_or_404(Notebook, pk=notebook_id, user=user)
        nw_qs = NotebookWord.objects.filter(notebook=nb).select_related('word')
        to_create = [
            LearningPlanEntry(plan=plan, word=nw.word.word, zh=nw.custom_zh)
            for nw in nw_qs
        ]
        created = LearningPlanEntry.objects.bulk_create(to_create, ignore_conflicts=True)
        return Response({'entries_added': len(created)})

    # book_all
    def _add_from_book_all(self, plan, data):
        book_id = data.get('book_id')
        get_object_or_404(VocabBook, pk=book_id)
        memberships = WordBookMembership.objects.filter(book_id=book_id).select_related('word')
        to_create = [
            LearningPlanEntry(plan=plan, word=m.word.word, zh=_extract_zh(m.word))
            for m in memberships
        ]
        created = LearningPlanEntry.objects.bulk_create(to_create, ignore_conflicts=True)
        return Response({'entries_added': len(created)})

    # book_range
    def _add_from_book_range(self, plan, data):
        book_id = data.get('book_id')
        get_object_or_404(VocabBook, pk=book_id)
        try:
            start = int(data.get('start', 1))
            end   = int(data.get('end', 50))
        except (TypeError, ValueError):
            return Response({'error': 'start/end 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)
        memberships = WordBookMembership.objects.filter(
            book_id=book_id, order__range=(start, end)
        ).select_related('word').order_by('order')
        to_create = [
            LearningPlanEntry(plan=plan, word=m.word.word, zh=_extract_zh(m.word))
            for m in memberships
        ]
        created = LearningPlanEntry.objects.bulk_create(to_create, ignore_conflicts=True)
        return Response({'entries_added': len(created)})

    # book_select
    def _add_from_book_select(self, plan, data):
        book_id  = data.get('book_id')
        word_ids = data.get('word_ids', [])
        get_object_or_404(VocabBook, pk=book_id)
        if not isinstance(word_ids, list) or not word_ids:
            return Response({'error': 'word_ids 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        memberships = WordBookMembership.objects.filter(
            book_id=book_id, word_id__in=word_ids
        ).select_related('word')
        to_create = [
            LearningPlanEntry(plan=plan, word=m.word.word, zh=_extract_zh(m.word))
            for m in memberships
        ]
        created = LearningPlanEntry.objects.bulk_create(to_create, ignore_conflicts=True)
        return Response({'entries_added': len(created)})


def _extract_zh(word_obj: Word) -> str:
    """Extract the first zh meaning from definitions JSON, fallback empty string."""
    defs = word_obj.definitions
    if isinstance(defs, list) and defs:
        return defs[0].get('meaning', '')
    return ''


def _parse_bool_field(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'1', 'true', 'yes', 'y', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'n', 'off', ''}:
            return False
    raise ValueError(f'{field_name} 必须为布尔值')


# 
# Plan word detail
# 

class PlanWordDetailView(APIView):
    """PATCH / DELETE  /plans/:id/words/:eid/"""
    permission_classes = [IsAuthenticated]

    def _get_entry(self, pk, eid, user):
        plan  = get_object_or_404(LearningPlan, pk=pk, user=user)
        return get_object_or_404(LearningPlanEntry, pk=eid, plan=plan)

    def patch(self, request, pk, eid):
        entry = self._get_entry(pk, eid, request.user)

        if 'zh' in request.data:
            entry.zh = request.data['zh'].strip()
            entry.save(update_fields=['zh'])

        has_next_review_days = 'next_review_days' in request.data
        has_increment_review_days = 'increment_review_days' in request.data

        if has_next_review_days and has_increment_review_days:
            return Response(
                {'error': 'next_review_days 与 increment_review_days 不能同时传入'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mark_reviewed = False
        if 'mark_reviewed' in request.data:
            try:
                mark_reviewed = _parse_bool_field(request.data.get('mark_reviewed'), 'mark_reviewed')
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if has_next_review_days or has_increment_review_days:
            try:
                raw_days = request.data['increment_review_days'] if has_increment_review_days else request.data['next_review_days']
                days = int(raw_days)
                if days < 0:
                    raise ValueError
            except (TypeError, ValueError):
                field_name = 'increment_review_days' if has_increment_review_days else 'next_review_days'
                return Response({'error': f'{field_name} 必须为非负整数'}, status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now()
            fsrs, _ = VocabFSRS.objects.get_or_create(
                user=request.user,
                word=entry.word,
                plan_id=entry.plan_id,
                defaults={'zh': entry.zh, 'due': now},
            )

            if has_increment_review_days:
                base_days = max(0, int(fsrs.scheduled_days or 0))
                days += base_days

            fsrs.scheduled_days = days
            if days > 0:
                fsrs.due   = _next_day_midnight(now, days)
                fsrs.state = 2  # Review
            else:
                fsrs.due   = now
                fsrs.state = 2 if (fsrs.reps > 0 or mark_reviewed) else 1  # due-now: review or learning

            update_fields = ['due', 'scheduled_days', 'state']

            # Avoid unstable REVIEW cards (stability=0 / difficulty=0) that can break later FSRS review math.
            if fsrs.state == 2:
                if fsrs.stability <= 0:
                    fsrs.stability = 1.0
                    update_fields.append('stability')
                if fsrs.difficulty <= 0:
                    fsrs.difficulty = 5.0
                    update_fields.append('difficulty')

            if mark_reviewed:
                fsrs.last_review = now
                fsrs.reps = max(1, int(fsrs.reps or 0) + 1)
                update_fields.extend(['last_review', 'reps'])

            fsrs.save(update_fields=update_fields)

            if mark_reviewed:
                _sync_notebook_mastery(request.user, entry.word, fsrs)

        fsrs_map = _build_fsrs_map(request.user, [entry.word], plan_id=entry.plan_id)
        word_map = _build_word_map([entry.word])
        return Response({'entry': _entry_dict(entry, fsrs_map, word_map)})

    def delete(self, request, pk, eid):
        entry = self._get_entry(pk, eid, request.user)
        word, plan_id = entry.word, entry.plan_id
        entry.delete()
        # Cards are plan-scoped; delete this plan's card for the word directly
        VocabFSRS.objects.filter(user=request.user, word=word, plan_id=plan_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# 
# Plan start -> sync + build session cards
# 

class PlanStartView(APIView):
    """POST  /plans/:id/start/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan    = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        user    = request.user
        entries = list(plan.entries.all())
        word_entry_id_map = {e.word: e.pk for e in entries}

        if not entries:
            return Response({'error': '计划中没有单词，请先添加单词'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        mode = request.data.get('mode', 'study')  # 'study' | 'review'

        # Review mode: return today's cards for read-only browsing
        if mode == 'review':
            today = now.date()
            word_zh_map = {e.word: e.zh for e in entries}
            today_cards = list(
                VocabFSRS.objects.filter(
                    user=user,
                    plan_id=plan.pk,
                    last_review__date=today,
                ).order_by('-last_review')
            )
            wmap = _build_word_map([c.word for c in today_cards])
            cards = []
            for c in today_cards:
                d = _card_to_dict(c, wmap.get(c.word))
                d['zh']      = word_zh_map.get(c.word) or c.zh
                d['plan_id'] = c.plan_id
                d['entry_id'] = word_entry_id_map.get(c.word)
                cards.append(d)
            studied_today = sum(1 for c in today_cards if c.state == 2)
            return Response({
                'cards': cards,
                'stats': {
                    'total':           len(entries),
                    'due':             0,
                    'carryover':       0,
                    'new':             0,
                    'pending':         0,
                    'studied_today':   studied_today,
                    'remaining_today': 0,
                },
                'review_mode': True,
            })

        # Normal study mode
        # 1. Sync plan entries -> VocabFSRS, scoped to this plan
        word_zh_map = {e.word: e.zh for e in entries}
        existing = {
            c.word: c
            for c in VocabFSRS.objects.filter(user=user, word__in=word_zh_map.keys(), plan_id=plan.pk)
        }
        to_create = [
            VocabFSRS(user=user, word=word, zh=zh, due=now, plan_id=plan.pk)
            for word, zh in word_zh_map.items()
            if word not in existing
        ]
        if to_create:
            VocabFSRS.objects.bulk_create(to_create, ignore_conflicts=True)

        # 2. Fetch all FSRS cards for this plan's words
        all_cards = list(
            VocabFSRS.objects.filter(user=user, word__in=word_zh_map.keys(), plan_id=plan.pk).order_by('due')
        )

        # 3. Build session: use shared logic
        _, session_cards, stats = _build_today_summary(plan, all_cards)


        # 4. Enrich cards with Word data; use this plan's zh, not the shared FSRS card's zh
        wmap = _build_word_map([c.word for c in session_cards])
        cards = []
        for c in session_cards:
            d = _card_to_dict(c, wmap.get(c.word))
            d['zh']      = word_zh_map.get(c.word) or c.zh
            d['plan_id'] = c.plan_id
            d['entry_id'] = word_entry_id_map.get(c.word)
            cards.append(d)
        return Response({
            'cards': cards,
            'stats': stats,
        })


# 
# VocabBook browser
# 

class VocabBookListView(APIView):
    """GET  /vocab/books/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = VocabBook.objects.all().order_by('id')
        data  = [
            {
                'id':          b.pk,
                'name':        b.name,
                'description': b.description,
                'word_count':  b.word_count,
            }
            for b in books
        ]
        return Response({'books': data})


class VocabBookWordsView(APIView):
    """GET  /vocab/books/:id/words/?page=1&page_size=20&q="""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        book = get_object_or_404(VocabBook, pk=pk)
        try:
            page      = max(1, int(request.query_params.get('page', 1)))
            page_size = max(1, min(100, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            page, page_size = 1, 20

        q = request.query_params.get('q', '').strip().lower()

        qs = WordBookMembership.objects.filter(book=book).select_related('word').order_by('order')
        if q:
            qs = qs.filter(word__word__icontains=q)

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = qs[offset: offset + page_size]

        words = []
        for m in items:
            w = m.word
            defs = w.definitions
            zh_brief = defs[0].get('meaning', '') if isinstance(defs, list) and defs else ''
            words.append({
                'id':       w.pk,
                'word':     w.word,
                'phonetic': w.phonetic or '',
                'zh_brief': zh_brief,
                'order':    m.order,
            })

        return Response({'words': words, 'total': total, 'page': page, 'page_size': page_size})


# ─────────────────────────────────────────────────────────────────
# Article Copy — AI-generated article for copying study mode
# ─────────────────────────────────────────────────────────────────

STORY_MODE_PROMPT = """
You are a creative writer. Write an entertaining, highly dramatic, and slightly silly Chinese web novel excerpt (e.g., "霸道总裁" CEO romance, or dog-blood drama) (300-500 words).
You MUST naturally embed ALL of the following IELTS target vocabulary words into the Chinese story: {words}

Rules:
1. The main narrative MUST be in Chinese.
2. Every target English word MUST appear exactly once.
3. When embedding a target word, you MUST wrap it in exact double brackets using the format [[English Word|Chinese Meaning]].
   For example, instead of writing "提案", write: "陆氏集团的 [[proposition|提案]] 放在桌上..."
4. Make the story highly engaging, exaggerated, and funny to help the student remember the words through dramatic context.
5. Do NOT use markdown formatting in the article text.

Return ONLY a JSON object (no markdown code block, no extra text) with these fields:
{{
    "story_title": "A funny dramatic title for the story in Chinese",
    "story_text": "the full Chinese story with embedded English words using the [[word|meaning]] syntax"
}}
"""


ARTICLE_COPY_PROMPT = """
You are an IELTS English teacher. Write a natural, cohesive short article (200-400 words)
that incorporates ALL of the following target vocabulary words: {words}

Requirements:
- The article must be natural English at IELTS Band 6-7 reading level
- Every target word MUST appear exactly once in the article
- The article should flow naturally as a coherent piece of writing on a single topic
- Do NOT use markdown formatting in the article text

Return ONLY a JSON object (no markdown code block, no extra text) with these three fields:
{{
    "article_title": "article title in English",
    "article_text": "the full article text in English",
    "article_translation": "Chinese translation of the full article"
}}
"""


ARTICLE_SEPARATOR = '\n\n\n\n'  # 4 blank lines between articles

def _build_boundaries(text: str, translations: str = '') -> list[dict]:
    """从拼接文本中重建 article_boundaries（含翻译）。"""
    boundaries = []
    parts = text.split(ARTICLE_SEPARATOR)
    trans_parts = translations.split(ARTICLE_SEPARATOR) if translations else []
    offset = 0
    sep_len = len(ARTICLE_SEPARATOR)
    for i, part in enumerate(parts):
        start = offset
        end = offset + len(part)
        translation = trans_parts[i] if i < len(trans_parts) else ''
        boundaries.append({'start': start, 'end': end, 'title': f'Article {i + 1}', 'translation': translation})
        offset = end + sep_len
    return boundaries


class ArticleCopyGenerateView(APIView):
    """GET /plans/:id/article-copy/ — generate or retrieve today's article(s)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        force_refresh = str(request.query_params.get('refresh', '')).strip().lower() in {'1', 'true', 'yes'}

        entries = list(plan.entries.all())
        word_zh_map = {e.word.lower(): e.zh for e in entries}

        # Check cache first
        if not force_refresh:
            cached = ArticleCopyCache.objects.filter(
                user=request.user, plan=plan, date=today,
            ).first()
            if cached:
                meanings = {w: word_zh_map.get(w.lower(), '') for w in cached.word_positions.keys()}
                boundaries = _build_boundaries(cached.article_text, cached.article_translation)
                # Fill in titles from cached article_title
                titles = cached.article_title.split('\n')
                for i, b in enumerate(boundaries):
                    if i < len(titles):
                        b['title'] = titles[i]
                return Response({
                    'article_title': cached.article_title,
                    'article_text': cached.article_text,
                    'article_translation': cached.article_translation,
                    'typed_text': cached.typed_text,
                    'word_positions': cached.word_positions,
                    'word_meanings': meanings,
                    'article_boundaries': boundaries,
                    'cached': True,
                    'atConsumed': 0,
                })

        # Rate limit for generation
        limit_resp = check_rate_limit(request.user.id, 'article_copy_generate', max_calls=5, window=300)
        if limit_resp:
            return limit_resp

        if not entries:
            return Response({'error': '计划中没有单词，请先添加单词'}, status=400)

        word_zh_map = {e.word: e.zh for e in entries}
        all_cards = list(
            VocabFSRS.objects.filter(user=request.user, word__in=word_zh_map.keys(), plan_id=plan.pk).order_by('due')
        )
        _, session_cards, _ = _build_today_summary(plan, all_cards)
        target_words = [c.word for c in session_cards]

        if not target_words:
            # 复习模式：今日额度已满，使用今日已复习的卡片生成
            today_cards = list(
                VocabFSRS.objects.filter(
                    user=request.user,
                    plan_id=plan.pk,
                    last_review__date=today,
                ).order_by('-last_review')
            )
            target_words = [c.word for c in today_cards]

        if not target_words:
            return Response({'error': '今天没有需要学习的单词'}, status=400)

        # ── 分组算法：1-200→1篇, 200-300→2篇, 300-400→3篇, ... ────────────
        word_count = len(target_words)
        num_groups = max(1, (word_count - 1) // 100)
        group_size = (word_count + num_groups - 1) // num_groups  # ceil division
        word_groups = [target_words[i:i + group_size] for i in range(0, word_count, group_size)]

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)

        import re
        all_titles = []
        all_texts = []
        all_translations = []
        merged_positions = {}
        total_at_cost = 0

        for gi, group_words in enumerate(word_groups):
            words_str = ', '.join(group_words)
            prompt = ARTICLE_COPY_PROMPT.format(words=words_str)
            scope = f'article_copy_{plan.pk}_{today.isoformat()}_g{gi}'

            try:
                response_data, at_cost = client.generate(
                    [{'role': 'user', 'content': prompt}],
                    expect_json=True,
                    temperature=0.7,
                    user_id=request.user.id,
                    singleflight_scope=scope,
                )
                total_at_cost += at_cost
            except Exception as e:
                return Response({'error': f'AI 生成第{gi + 1}组失败: {str(e)}'}, status=500)

            if not isinstance(response_data, dict):
                return Response({'error': f'AI 第{gi + 1}组返回的不是合法的 JSON 对象'}, status=500)

            title = str(response_data.get('article_title', f'Article {gi + 1}')).strip()
            text = str(response_data.get('article_text', '')).strip()
            translation = str(response_data.get('article_translation', '')).strip()

            if not text:
                print(f'[ArticleCopy] 第{gi + 1}组 article_text 为空。响应: {json.dumps(response_data, ensure_ascii=False)[:300]}')
                return Response({'error': f'AI 第{gi + 1}组返回内容不完整（缺少 article_text）'}, status=500)

            # Normalize line endings
            text = text.replace('\r\n', '\n').replace('\r', '\n')

            all_titles.append(title)
            all_texts.append(text)
            all_translations.append(translation)

            # Calculate word_positions for this group (local to this sub-article)
            for word in group_words:
                pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
                matches = [{'start': m.start(), 'end': m.end()} for m in pattern.finditer(text)]
                if matches:
                    merged_positions[word.lower()] = matches

            # Append missing words to this sub-article
            missing = [w for w in group_words if w.lower() not in merged_positions]
            if missing:
                text += "\n\nAdditional vocabulary: "
                for w in missing:
                    start_idx = len(text)
                    text += w
                    merged_positions[w.lower()] = [{'start': start_idx, 'end': len(text)}]
                    text += ", "
                text = text.rstrip(", ")
                all_texts[-1] = text  # update the stored text

        # ── 拼接所有文章 ───────────────────────────────────────────────────
        concatenated_text = ARTICLE_SEPARATOR.join(all_texts)
        concatenated_titles = '\n'.join(all_titles)
        concatenated_translations = ARTICLE_SEPARATOR.join(all_translations)

        # ── Offset word_positions for articles after the first ─────────────
        sep_len = len(ARTICLE_SEPARATOR)
        offset = 0
        for gi, text in enumerate(all_texts):
            if gi == 0:
                offset = len(text) + sep_len
                continue
            # Shift all positions in this group by offset
            for word in word_groups[gi]:
                key = word.lower()
                if key in merged_positions and merged_positions[key]:
                    merged_positions[key] = [
                        {'start': p['start'] + offset, 'end': p['end'] + offset}
                        for p in merged_positions[key]
                    ]
            offset += len(text) + sep_len

        # ── Build article_boundaries ───────────────────────────────────────
        boundaries = []
        pos = 0
        for gi, text in enumerate(all_texts):
            boundaries.append({
                'start': pos,
                'end': pos + len(text),
                'title': all_titles[gi],
                'translation': all_translations[gi],
            })
            pos += len(text) + sep_len

        # ── Persist to cache ───────────────────────────────────────────────
        ArticleCopyCache.objects.update_or_create(
            user=request.user,
            plan=plan,
            date=today,
            defaults={
                'article_title': concatenated_titles[:200],
                'article_text': concatenated_text,
                'article_translation': concatenated_translations,
                'word_positions': merged_positions,
                'ai_provider': provider,
            },
        )

        meanings = {w: word_zh_map.get(w.lower(), '') for w in merged_positions.keys()}

        return Response({
            'article_title': concatenated_titles,
            'article_text': concatenated_text,
            'article_translation': concatenated_translations,
            'word_positions': merged_positions,
            'word_meanings': meanings,
            'article_boundaries': boundaries,
            'cached': False,
            'atConsumed': total_at_cost,
        })


class ArticleCopyProgressView(APIView):
    """POST /plans/:id/article-copy/progress/ — save typed_text progress."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        typed_text = str(request.data.get('typed_text', '') or '')
        ArticleCopyCache.objects.filter(user=request.user, plan=plan, date=today).update(
            typed_text=typed_text,
        )
        return Response({'ok': True})


class ArticleCopyCompleteView(APIView):
    """POST /plans/:id/article-copy/complete/ — mark all today's words as reviewed."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        user = request.user

        try:
            review_days = int(request.data.get('review_days', 7))
            if not (0 <= review_days <= 365):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'review_days 必须在 0-365 之间'}, status=400)

        today = _user_today()

        # 修复问题3：从当日文章缓存的 word_positions 中读取实际目标单词
        # 而非重新计算当前队列，避免中途使用其他模式导致队列变化，结算错误。
        cached = ArticleCopyCache.objects.filter(
            user=user, plan=plan, date=today,
        ).first()

        if not cached:
            return Response({'error': '未找到今日文章，请先进入文章抄写模式'}, status=400)

        target_words = list(cached.word_positions.keys()) if isinstance(cached.word_positions, dict) else []

        if not target_words:
            return Response({'error': '文章中没有有效的目标单词'}, status=400)

        # 获取这些单词在本计划中对应的中文释义
        entries_map = {e.word: e.zh for e in plan.entries.filter(word__in=target_words)}

        now = timezone.now()
        due_map = {}
        marked_count = 0

        for word in target_words:
            zh = entries_map.get(word, '')
            fsrs, _ = VocabFSRS.objects.get_or_create(
                user=user,
                word=word,
                plan_id=plan.pk,
                defaults={'zh': zh, 'due': now},
            )

            fsrs.scheduled_days = review_days
            if review_days > 0:
                fsrs.due = _next_day_midnight(now, review_days)
                fsrs.state = 2  # Review
            else:
                fsrs.due = now
                fsrs.state = 2

            update_fields = ['due', 'scheduled_days', 'state']

            if fsrs.state == 2:
                if fsrs.stability <= 0:
                    fsrs.stability = 1.0
                    update_fields.append('stability')
                if fsrs.difficulty <= 0:
                    fsrs.difficulty = 5.0
                    update_fields.append('difficulty')

            fsrs.last_review = now
            fsrs.reps = max(1, int(fsrs.reps or 0) + 1)
            update_fields.extend(['last_review', 'reps'])

            fsrs.save(update_fields=update_fields)

            _sync_notebook_mastery(user, word, fsrs)
            due_map[word] = fsrs.due.isoformat()
            marked_count += 1

        return Response({
            'marked_count': marked_count,
            'due_map': due_map,
        })


# ─────────────────────────────────────────────────────────────────
# Story Mode — Click-to-learn story reading mode
# ─────────────────────────────────────────────────────────────────

class StoryModeGenerateView(APIView):
    """GET /plans/:id/story-mode/ — generate or retrieve today's story."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        force_refresh = str(request.query_params.get('refresh', '')).strip().lower() in {'1', 'true', 'yes'}

        entries = list(plan.entries.all())
        word_zh_map = {e.word.lower(): e.zh for e in entries}

        if not force_refresh:
            cached = StoryModeCache.objects.filter(
                user=request.user, plan=plan, date=today,
            ).first()
            if cached:
                boundaries = _build_boundaries(cached.story_text)
                titles = cached.story_title.split('\n')
                for i, b in enumerate(boundaries):
                    if i < len(titles):
                        b['title'] = titles[i]
                return Response({
                    'story_title': cached.story_title,
                    'story_text': cached.story_text,
                    'clicked_words': cached.clicked_words,
                    'target_words': cached.target_words,
                    'article_boundaries': boundaries,
                    'cached': True,
                    'atConsumed': 0,
                })

        limit_resp = check_rate_limit(request.user.id, 'story_mode_generate', max_calls=5, window=300)
        if limit_resp:
            return limit_resp

        if not entries:
            return Response({'error': '计划中没有单词，请先添加单词'}, status=400)

        all_cards = list(
            VocabFSRS.objects.filter(user=request.user, word__in=[e.word for e in entries], plan_id=plan.pk).order_by('due')
        )
        _, session_cards, _ = _build_today_summary(plan, all_cards)
        target_words = [c.word for c in session_cards]

        if not target_words:
            # 复习模式：今日额度已满，使用今日已复习的卡片生成
            today_cards = list(
                VocabFSRS.objects.filter(
                    user=request.user,
                    plan_id=plan.pk,
                    last_review__date=today,
                ).order_by('-last_review')
            )
            target_words = [c.word for c in today_cards]

        if not target_words:
            return Response({'error': '今天没有需要学习的单词'}, status=400)

        word_count = len(target_words)
        num_groups = max(1, (word_count - 1) // 100)
        group_size = (word_count + num_groups - 1) // num_groups
        word_groups = [target_words[i:i + group_size] for i in range(0, word_count, group_size)]

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)

        all_titles = []
        all_texts = []
        total_at_cost = 0

        for gi, group_words in enumerate(word_groups):
            words_str = ', '.join(group_words)
            prompt = STORY_MODE_PROMPT.format(words=words_str)
            scope = f'story_mode_{plan.pk}_{today.isoformat()}_g{gi}'

            try:
                response_data, at_cost = client.generate(
                    [{'role': 'user', 'content': prompt}],
                    expect_json=True,
                    temperature=0.8,
                    user_id=request.user.id,
                    singleflight_scope=scope,
                )
                total_at_cost += at_cost
            except Exception as e:
                return Response({'error': f'AI 生成第{gi + 1}组失败: {str(e)}'}, status=500)

            if not isinstance(response_data, dict):
                return Response({'error': f'AI 第{gi + 1}组返回的不是合法的 JSON 对象'}, status=500)

            title = str(response_data.get('story_title', f'Story {gi + 1}')).strip()
            text = str(response_data.get('story_text', '')).strip()

            if not text:
                return Response({'error': f'AI 第{gi + 1}组返回内容不完整（缺少 story_text）'}, status=500)

            text = text.replace('\r\n', '\n').replace('\r', '\n')

            # Validate missing words
            text_lower = text.lower()
            missing = [w for w in group_words if w.lower() not in text_lower]
            if missing:
                text += "\n\n[附加] "
                for w in missing:
                    text += f"[[{w}|{word_zh_map.get(w.lower(), '')}]], "
                text = text.rstrip(", ")

            all_titles.append(title)
            all_texts.append(text)

        concatenated_text = ARTICLE_SEPARATOR.join(all_texts)
        concatenated_titles = '\n'.join(all_titles)

        StoryModeCache.objects.update_or_create(
            user=request.user,
            plan=plan,
            date=today,
            defaults={
                'story_title': concatenated_titles,
                'story_text': concatenated_text,
                'target_words': target_words,
                'ai_provider': provider,
            }
        )
        
        boundaries = _build_boundaries(concatenated_text)
        titles = concatenated_titles.split('\n')
        for i, b in enumerate(boundaries):
            if i < len(titles):
                b['title'] = titles[i]

        return Response({
            'story_title': concatenated_titles,
            'story_text': concatenated_text,
            'clicked_words': [],
            'target_words': target_words,
            'article_boundaries': boundaries,
            'cached': False,
            'atConsumed': total_at_cost,
        })


class StoryModeSaveProgressView(APIView):
    """POST /plans/:id/story-mode/save/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        clicked_words = request.data.get('clicked_words', [])
        
        if not isinstance(clicked_words, list):
            return Response({'error': 'clicked_words must be a list'}, status=400)

        today = _user_today()
        cache = StoryModeCache.objects.filter(user=request.user, plan=plan, date=today).first()
        if cache:
            cache.clicked_words = clicked_words
            cache.save(update_fields=['clicked_words', 'updated_at'])
            return Response({'status': 'ok'})
        return Response({'error': 'No story generated today'}, status=404)


class StoryModeCompleteView(APIView):
    """POST /plans/:id/story-mode/complete/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        review_days = int(request.data.get('reviewDays', 0))

        cache = StoryModeCache.objects.filter(user=request.user, plan=plan, date=today).first()
        if not cache:
            return Response({'error': 'No story cache found for today'}, status=400)

        target_words = cache.target_words
        if not target_words:
            return Response({'error': 'No target words found'}, status=400)

        user = request.user
        entries = {e.word.lower(): e.zh for e in plan.entries.all()}
        
        now = timezone.now()
        marked_count = 0
        due_map = {}

        for w in target_words:
            w_low = w.lower()
            zh = entries.get(w_low, '')
            
            fsrs, _ = VocabFSRS.objects.get_or_create(
                user=user,
                plan=plan,
                word=w_low,
                defaults={'zh': zh, 'due': now},
            )

            fsrs.scheduled_days = review_days
            if review_days > 0:
                fsrs.due = _next_day_midnight(now, review_days)
                fsrs.state = 2  # Review
            else:
                fsrs.due = now
                fsrs.state = 2

            update_fields = ['due', 'scheduled_days', 'state']

            if fsrs.state == 2:
                if fsrs.stability <= 0:
                    fsrs.stability = 1.0
                    update_fields.append('stability')
                if fsrs.difficulty <= 0:
                    fsrs.difficulty = 5.0
                    update_fields.append('difficulty')

            fsrs.last_review = now
            fsrs.reps = max(1, int(fsrs.reps or 0) + 1)
            update_fields.extend(['last_review', 'reps'])

            fsrs.save(update_fields=update_fields)

            _sync_notebook_mastery(user, w_low, fsrs)
            due_map[w_low] = fsrs.due.isoformat()
            marked_count += 1

        return Response({
            'marked_count': marked_count,
            'due_map': due_map,
        })
