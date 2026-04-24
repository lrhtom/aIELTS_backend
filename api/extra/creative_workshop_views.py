import hashlib
import re

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.core.rate_limit import check_rate_limit

from api.core.ai_client import AIClient
from api.models import CreativeWorkshopPage


def _strip_code_fence(content: str) -> str:
    text = str(content or '').strip()
    text = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _extract_title_from_html(content: str) -> str:
    match = re.search(r'<title>(.*?)</title>', content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ''
    return re.sub(r'\s+', ' ', match.group(1)).strip()


def _normalize_html(content: str, fallback_title: str) -> str:
    cleaned = _strip_code_fence(content)
    lowered = cleaned.lower()

    if '<html' in lowered:
        if '<!doctype' not in lowered:
            cleaned = '<!doctype html>\n' + cleaned
        return cleaned

    safe_title = fallback_title or 'Creative Workshop Page'
    return (
        '<!doctype html>\n'
        '<html lang="zh-CN">\n'
        '<head>\n'
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'  <title>{safe_title}</title>\n'
        '</head>\n'
        '<body>\n'
        f'{cleaned}\n'
        '</body>\n'
        '</html>'
    )


def _build_prompt(method_prompt: str, preferred_title: str) -> str:
    title_instruction = (
        f'Use this page title if appropriate: "{preferred_title}".' if preferred_title else
        'Create a concise and clear page title for this learning method.'
    )
    return (
        'You are an elite education product designer and front-end engineer.\n'
        'Generate a complete, standalone HTML learning page that helps a student practice based on their custom method.\n'
        'Output ONLY raw HTML, no markdown fences and no extra explanation.\n\n'
        'Hard requirements:\n'
        '1) Return a full HTML document with <!doctype html>, <html>, <head>, <body>.\n'
        '2) Include inline CSS and JavaScript in the same file (no external CDN or external assets).\n'
        '3) The page must be responsive for mobile and desktop.\n'
        '4) The page should be practical for studying: include clear sections, one interactive exercise area, and progress feedback.\n'
        '5) Keep wording in Chinese by default unless the method explicitly asks another language.\n'
        '6) Avoid offensive or unsafe content.\n'
        f'7) {title_instruction}\n\n'
        'User custom learning method:\n'
        f'{method_prompt}'
    )


def _serialize_project(project: CreativeWorkshopPage, include_html: bool = False) -> dict:
    payload = {
        'id': project.pk,
        'title': project.title,
        'method_prompt': project.method_prompt,
        'is_favorited': project.is_favorited,
        'ai_provider': project.ai_provider,
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
    }
    if include_html:
        payload['generated_html'] = project.generated_html
    return payload


class CreativeWorkshopProjectListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        favorited_raw = str(request.query_params.get('favorited', '')).strip().lower()
        only_favorited = favorited_raw in {'1', 'true', 'yes', 'on'}

        qs = CreativeWorkshopPage.objects.filter(user=request.user)
        if only_favorited:
            qs = qs.filter(is_favorited=True)

        projects = [_serialize_project(p) for p in qs.order_by('-updated_at')]
        return Response({'projects': projects})


class CreativeWorkshopProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = get_object_or_404(CreativeWorkshopPage, pk=pk, user=request.user)
        return Response({'project': _serialize_project(project, include_html=True)})

    def delete(self, request, pk):
        project = get_object_or_404(CreativeWorkshopPage, pk=pk, user=request.user)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreativeWorkshopProjectGenerateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        limit_resp = check_rate_limit(request.user.id, 'creative_workshop_generate', max_calls=6, window=300)
        if limit_resp:
            return limit_resp

        method_prompt = str(request.data.get('method_prompt', '')).strip()
        preferred_title = str(request.data.get('title', '')).strip()

        if not method_prompt:
            return Response({'error': 'method_prompt is required'}, status=status.HTTP_400_BAD_REQUEST)

        if len(method_prompt) > 3000:
            return Response({'error': 'method_prompt is too long (max 3000 chars)'}, status=status.HTTP_400_BAD_REQUEST)

        if preferred_title and len(preferred_title) > 120:
            preferred_title = preferred_title[:120]

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        prompt = _build_prompt(method_prompt, preferred_title)
        scope_hash = hashlib.md5(method_prompt.encode('utf-8')).hexdigest()[:12]

        client = AIClient(provider=provider)
        html_content, at_cost = client.generate(
            [{'role': 'user', 'content': prompt}],
            expect_json=False,
            temperature=0.7,
            user_id=request.user.id,
            singleflight_scope=f'creative_workshop_generate_{scope_hash}',
        )

        normalized_html = _normalize_html(html_content, preferred_title)
        final_title = preferred_title or _extract_title_from_html(normalized_html) or '鍒涙剰瀛︿範椤甸潰'

        project = CreativeWorkshopPage.objects.create(
            user=request.user,
            title=final_title[:120],
            method_prompt=method_prompt,
            generated_html=normalized_html,
            ai_provider=provider,
        )

        return Response(
            {
                'project': _serialize_project(project, include_html=True),
                'atConsumed': at_cost,
            },
            status=status.HTTP_201_CREATED,
        )


class CreativeWorkshopProjectFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = get_object_or_404(CreativeWorkshopPage, pk=pk, user=request.user)
        value = request.data.get('is_favorited', None)

        if value is None:
            project.is_favorited = not project.is_favorited
        else:
            project.is_favorited = str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

        project.save(update_fields=['is_favorited', 'updated_at'])

        return Response(
            {
                'is_favorited': project.is_favorited,
                'project': _serialize_project(project),
            }
        )


