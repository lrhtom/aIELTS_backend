from datetime import timedelta

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LearningPlan, LearningPlanEntry,
    Notebook, NotebookWord,
    VocabBook, Word, WordBookMembership,
    VocabFSRS,
)
from .vocab_views import _card_to_dict, _word_map as _build_word_map


# ──────────────────────────────────────────────────────────────────────────────
# Serialisers
# ──────────────────────────────────────────────────────────────────────────────

def _plan_dict(plan: LearningPlan, word_count: int | None = None) -> dict:
    return {
        'id':          plan.pk,
        'name':        plan.name,
        'daily_count': plan.daily_count,
        'word_count':  word_count if word_count is not None else plan.entries.count(),
        'created_at':  plan.created_at.isoformat(),
        'updated_at':  plan.updated_at.isoformat(),
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


# ──────────────────────────────────────────────────────────────────────────────
# Plan CRUD
# ──────────────────────────────────────────────────────────────────────────────

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
        return Response({'plans': [_plan_dict(p, p.wc) for p in plans]})

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
            plan = LearningPlan(user=request.user, name=name, daily_count=daily_count)
            plan.save()
        except Exception as e:
            msg = str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'plan': _plan_dict(plan, 0)}, status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    """GET / PATCH / DELETE  /plans/:id/"""
    permission_classes = [IsAuthenticated]

    def _get_plan(self, pk, user):
        return get_object_or_404(LearningPlan, pk=pk, user=user)

    def get(self, request, pk):
        plan = self._get_plan(pk, request.user)
        return Response({'plan': _plan_dict(plan)})

    def patch(self, request, pk):
        plan = self._get_plan(pk, request.user)
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
                plan.daily_count = daily_count
            except (TypeError, ValueError):
                return Response({'error': '每日学习词数必须在 1-200 之间'}, status=status.HTTP_400_BAD_REQUEST)
        # bypass full_clean (no new-plan limit check on update)
        LearningPlan.objects.filter(pk=plan.pk).update(
            name=plan.name, daily_count=plan.daily_count
        )
        plan.refresh_from_db()
        return Response({'plan': _plan_dict(plan)})

    def delete(self, request, pk):
        plan = self._get_plan(pk, request.user)
        plan_pk = plan.pk
        plan.delete()
        # Cards are plan-scoped; delete them all when plan is deleted
        VocabFSRS.objects.filter(user=request.user, plan_id=plan_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ──────────────────────────────────────────────────────────────────────────────
# Plan word list
# ──────────────────────────────────────────────────────────────────────────────

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

    # ── manual ──
    def _add_manual(self, plan, data):
        word_str = data.get('word', '').strip().lower()
        if not word_str:
            return Response({'error': '单词不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        zh = data.get('zh', '').strip()

        # Update optional Word enrichment data — only fill in fields that are currently empty
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

    # ── notebook ──
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

    # ── book_all ──
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

    # ── book_range ──
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

    # ── book_select ──
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


# ──────────────────────────────────────────────────────────────────────────────
# Plan word detail
# ──────────────────────────────────────────────────────────────────────────────

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

        if 'next_review_days' in request.data:
            try:
                days = int(request.data['next_review_days'])
                if days < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': 'next_review_days 必须为非负整数'}, status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now()
            fsrs, _ = VocabFSRS.objects.get_or_create(
                user=request.user,
                word=entry.word,
                plan_id=entry.plan_id,
                defaults={'zh': entry.zh, 'due': now},
            )
            fsrs.due            = now + timedelta(days=days)
            fsrs.scheduled_days = days
            if fsrs.reps > 0:
                fsrs.state = 2  # Review
            fsrs.save(update_fields=['due', 'scheduled_days', 'state'])

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


# ──────────────────────────────────────────────────────────────────────────────
# Plan start → sync + build session cards
# ──────────────────────────────────────────────────────────────────────────────

class PlanStartView(APIView):
    """POST  /plans/:id/start/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan    = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        user    = request.user
        entries = list(plan.entries.all())

        if not entries:
            return Response({'error': '计划中没有单词，请先添加单词'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()

        # 1. Sync plan entries → VocabFSRS, scoped to this plan
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

        # 3. Build session: due cards first, then new cards, capped at remaining daily quota
        today = now.date()

        # Words from this plan already reviewed today
        studied_today = sum(
            1 for c in all_cards
            if c.last_review is not None and c.last_review.date() == today
        )
        # Remaining quota: daily_count minus what's already done today
        remaining_today = max(0, plan.daily_count - studied_today)

        # Due: non-new state, due date is today or earlier, and not already reviewed today
        due_cards = [
            c for c in all_cards
            if c.state != 0
            and c.due.date() <= today
            and (c.last_review is None or c.last_review.date() < today)
        ]
        # New: never been reviewed (state == 0)
        new_cards = [c for c in all_cards if c.state == 0]
        # Pending: previously studied via another context, due in the future,
        # not yet reviewed today — sorted nearest-due first to minimise FSRS disruption
        pending_cards = sorted(
            [
                c for c in all_cards
                if c.state != 0
                and c.due.date() > today
                and (c.last_review is None or c.last_review.date() < today)
            ],
            key=lambda c: c.due,
        )

        session_cards = due_cards[:remaining_today]
        remaining = remaining_today - len(session_cards)
        if remaining > 0:
            fill = new_cards[:remaining]
            session_cards += fill
            remaining -= len(fill)
        if remaining > 0:
            session_cards += pending_cards[:remaining]

        total   = len(all_cards)
        due     = len(due_cards)
        new     = len(new_cards)
        pending = len(pending_cards)

        # 4. Enrich cards with Word data; use this plan's zh, not the shared FSRS card's zh
        wmap = _build_word_map([c.word for c in session_cards])
        cards = []
        for c in session_cards:
            d = _card_to_dict(c, wmap.get(c.word))
            d['zh']      = word_zh_map.get(c.word) or c.zh
            d['plan_id'] = c.plan_id
            cards.append(d)
        return Response({
            'cards': cards,
            'stats': {
                'total':           total,
                'due':             due,
                'new':             new,
                'pending':         pending,
                'studied_today':   studied_today,
                'remaining_today': remaining_today,
            },
        })


# ──────────────────────────────────────────────────────────────────────────────
# VocabBook browser
# ──────────────────────────────────────────────────────────────────────────────

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
