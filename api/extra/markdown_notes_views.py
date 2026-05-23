from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from api.models import MarkdownNote


def _serialize(note: MarkdownNote) -> dict:
    return {
        'id': note.pk,
        'title': note.title,
        'tags': note.tags,
        'content': note.content,
        'created_at': note.created_at.isoformat(),
        'updated_at': note.updated_at.isoformat(),
    }


class MarkdownNoteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notes = MarkdownNote.objects.filter(user=request.user).order_by('-updated_at')
        return Response({'notes': [_serialize(n) for n in notes]})

    def post(self, request):
        title = str(request.data.get('title', '')).strip()[:200]
        tags = request.data.get('tags', [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip().lower() for t in tags if str(t).strip()]
        content = str(request.data.get('content', ''))

        note = MarkdownNote.objects.create(
            user=request.user,
            title=title,
            tags=tags,
            content=content,
        )
        return Response({'note': _serialize(note)}, status=status.HTTP_201_CREATED)


class MarkdownNoteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_note(self, pk, user):
        return get_object_or_404(MarkdownNote, pk=pk, user=user)

    def get(self, request, pk):
        note = self._get_note(pk, request.user)
        return Response({'note': _serialize(note)})

    def patch(self, request, pk):
        note = self._get_note(pk, request.user)

        if 'title' in request.data:
            note.title = str(request.data['title']).strip()[:200]

        if 'tags' in request.data:
            tags = request.data['tags']
            if not isinstance(tags, list):
                tags = []
            note.tags = [str(t).strip().lower() for t in tags if str(t).strip()]

        if 'content' in request.data:
            note.content = str(request.data.get('content', ''))

        note.save()
        return Response({'note': _serialize(note)})

    def delete(self, request, pk):
        note = self._get_note(pk, request.user)
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
