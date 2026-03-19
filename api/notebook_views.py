from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Notebook, NotebookWord, NotebookWordTag, Word, VocabBook, WordBookMembership

VALID_COLORS = {'indigo', 'teal', 'violet', 'rose', 'amber', 'emerald', 'sky', 'orange'}


def _nb_dict(nb: Notebook, word_count: int | None = None) -> dict:
    return {
        'id':          nb.pk,
        'title':       nb.title,
        'description': nb.description or '',
        'cover_color': nb.cover_color,
        'is_public':   nb.is_public,
        'word_count':  word_count if word_count is not None else nb.entries.count(),
        'created_at':  nb.created_at.isoformat(),
    }


def _entry_dict(entry: NotebookWord) -> dict:
    w = entry.word
    return {
        'id':            entry.pk,
        'word':          w.word,
        'phonetic':      w.phonetic or '',
        'grammar':       w.grammar or '',
        'definitions':   w.definitions,
        'examples':      w.examples,
        'custom_zh':     entry.custom_zh,
        'notes':         entry.notes or '',
        'mastery_level': entry.mastery_level,
        'tags':          [t.name for t in entry.tags.all()],
        'added_at':      entry.added_at.isoformat(),
        'last_reviewed': entry.last_reviewed.isoformat() if entry.last_reviewed else None,
    }


def _save_tags(entry: NotebookWord, raw_tags: list):
    """Replace all tags for a NotebookWord entry."""
    names = list({t.strip().lower() for t in raw_tags if t.strip()})
    with transaction.atomic():
        NotebookWordTag.objects.filter(notebook_word=entry).delete()
        if names:
            NotebookWordTag.objects.bulk_create(
                [NotebookWordTag(notebook_word=entry, name=n) for n in names],
                ignore_conflicts=True,
            )


def _extract_zh(word_obj: Word) -> str:
    """Extract the first zh meaning from definitions JSON."""
    defs = word_obj.definitions
    if isinstance(defs, list) and defs:
        return defs[0].get('meaning', '')
    return ''


class NotebookListView(APIView):
    """GET/POST /notebooks/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notebooks = (
            Notebook.objects
            .filter(user=request.user)
            .annotate(wc=Count('entries'))
            .order_by('-created_at')
        )
        return Response({'notebooks': [_nb_dict(nb, nb.wc) for nb in notebooks]})

    def post(self, request):
        title = request.data.get('title', '').strip()
        if not title:
            return Response({'error': '标题不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        description = request.data.get('description', '').strip()
        cover_color = request.data.get('cover_color', 'indigo')
        if cover_color not in VALID_COLORS:
            cover_color = 'indigo'
        is_public = bool(request.data.get('is_public', False))

        try:
            nb = Notebook(
                user=request.user,
                title=title,
                description=description,
                cover_color=cover_color,
                is_public=is_public,
            )
            nb.full_clean()
            nb.save()
        except Exception as e:
            msg = str(e)
            if '最多创建' in msg:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': '创建失败'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'notebook': _nb_dict(nb, 0)}, status=status.HTTP_201_CREATED)


class NotebookDetailView(APIView):
    """GET/PATCH/DELETE /notebooks/:id/"""
    permission_classes = [IsAuthenticated]

    def _get_notebook(self, pk, user):
        return get_object_or_404(Notebook, pk=pk, user=user)

    def get(self, request, pk):
        nb = self._get_notebook(pk, request.user)
        return Response({'notebook': _nb_dict(nb)})

    def patch(self, request, pk):
        nb = self._get_notebook(pk, request.user)

        if 'title' in request.data:
            title = request.data['title'].strip()
            if not title:
                return Response({'error': '标题不能为空'}, status=status.HTTP_400_BAD_REQUEST)
            nb.title = title
        if 'description' in request.data:
            nb.description = request.data['description'].strip()
        if 'cover_color' in request.data:
            color = request.data['cover_color']
            nb.cover_color = color if color in VALID_COLORS else nb.cover_color
        if 'is_public' in request.data:
            nb.is_public = bool(request.data['is_public'])

        nb.save()
        return Response({'notebook': _nb_dict(nb)})

    def delete(self, request, pk):
        nb = self._get_notebook(pk, request.user)
        nb.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotebookWordListView(APIView):
    """GET/POST /notebooks/:pk/words/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        nb = get_object_or_404(Notebook, pk=pk, user=request.user)
        qs = nb.entries.select_related('word').prefetch_related('tags').order_by('-added_at')

        tag = request.query_params.get('tag', '').strip().lower()
        if tag:
            qs = qs.filter(tags__name=tag)

        search = request.query_params.get('q', '').strip().lower()
        if search:
            qs = qs.filter(word__word__icontains=search) | qs.filter(custom_zh__icontains=search)

        return Response({'entries': [_entry_dict(e) for e in qs]})

    def post(self, request, pk):
        nb = get_object_or_404(Notebook, pk=pk, user=request.user)
        mode = request.data.get('mode', 'manual')

        if mode == 'manual':
            return self._add_manual(nb, request.data)
        elif mode == 'book_all':
            return self._add_from_book(nb, request.data, 'all')
        elif mode == 'book_range':
            return self._add_from_book(nb, request.data, 'range')
        elif mode == 'book_select':
            return self._add_from_book(nb, request.data, 'select')
        else:
            return Response({'error': f'未知 mode: {mode}'}, status=status.HTTP_400_BAD_REQUEST)

    # ── manual (original single-word logic) ──────────────────────────────
    def _add_manual(self, nb, data):
        word_str = data.get('word', '').strip().lower()
        if not word_str:
            return Response({'error': '英文单词不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        custom_zh = data.get('custom_zh', '').strip()
        notes     = data.get('notes', '').strip()
        tags      = data.get('tags', [])
        if not isinstance(tags, list):
            tags = [str(tags)]

        word_obj, _ = Word.objects.get_or_create(word=word_str)

        word_fields = []
        if data.get('phonetic', '').strip():
            word_obj.phonetic = data['phonetic'].strip()
            word_fields.append('phonetic')
        if data.get('grammar', '').strip():
            word_obj.grammar = data['grammar'].strip()
            word_fields.append('grammar')
        raw_examples = data.get('examples')
        if isinstance(raw_examples, list) and raw_examples:
            word_obj.examples = raw_examples
            word_fields.append('examples')
        if word_fields:
            word_obj.save(update_fields=word_fields)

        entry, created = NotebookWord.objects.get_or_create(notebook=nb, word=word_obj)
        if not created:
            return Response({'error': '该单词已在笔记本中'}, status=status.HTTP_409_CONFLICT)

        entry.custom_zh = custom_zh
        entry.notes = notes
        entry.save(update_fields=['custom_zh', 'notes'])
        _save_tags(entry, tags)

        entry = nb.entries.select_related('word').prefetch_related('tags').get(pk=entry.pk)
        return Response({'entry': _entry_dict(entry)}, status=status.HTTP_201_CREATED)

    # ── bulk import from vocab book ──────────────────────────────────────
    def _add_from_book(self, nb, data, sub_mode):
        book_id = data.get('book_id')
        book = get_object_or_404(VocabBook, pk=book_id)

        qs = WordBookMembership.objects.filter(book=book).select_related('word')

        if sub_mode == 'range':
            try:
                start = int(data.get('start', 1))
                end   = int(data.get('end', 50))
            except (TypeError, ValueError):
                return Response({'error': 'start/end 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(order__range=(start, end))
        elif sub_mode == 'select':
            word_ids = data.get('word_ids', [])
            if not isinstance(word_ids, list) or not word_ids:
                return Response({'error': 'word_ids 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(word_id__in=word_ids)

        existing = set(nb.entries.values_list('word_id', flat=True))
        to_create = []
        for m in qs.order_by('order'):
            if m.word_id not in existing:
                to_create.append(NotebookWord(
                    notebook=nb,
                    word=m.word,
                    custom_zh=_extract_zh(m.word),
                ))
                existing.add(m.word_id)

        if to_create:
            NotebookWord.objects.bulk_create(to_create, ignore_conflicts=True)

        return Response({'entries_added': len(to_create)})


class NotebookWordDetailView(APIView):
    """PATCH/DELETE /notebooks/:pk/words/:eid/"""
    permission_classes = [IsAuthenticated]

    def _get_entry(self, pk, eid, user):
        nb = get_object_or_404(Notebook, pk=pk, user=user)
        return get_object_or_404(
            NotebookWord.objects.select_related('word').prefetch_related('tags'),
            pk=eid, notebook=nb,
        )

    def patch(self, request, pk, eid):
        entry = self._get_entry(pk, eid, request.user)

        update_fields = []
        if 'custom_zh' in request.data:
            entry.custom_zh = request.data['custom_zh'].strip()
            update_fields.append('custom_zh')
        if 'notes' in request.data:
            entry.notes = request.data['notes'].strip()
            update_fields.append('notes')
        if 'mastery_level' in request.data:
            level = int(request.data['mastery_level'])
            entry.mastery_level = max(0, min(5, level))
            update_fields.append('mastery_level')

        if update_fields:
            entry.save(update_fields=update_fields)

        if 'tags' in request.data:
            tags = request.data['tags']
            if not isinstance(tags, list):
                tags = [str(tags)]
            _save_tags(entry, tags)

        entry = (
            NotebookWord.objects
            .select_related('word')
            .prefetch_related('tags')
            .get(pk=entry.pk)
        )
        return Response({'entry': _entry_dict(entry)})

    def delete(self, request, pk, eid):
        entry = self._get_entry(pk, eid, request.user)
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
