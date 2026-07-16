"""Custom (bring-your-own) AI model management — CRUD + connectivity test.

A user registers an OpenAI-compatible endpoint (name + base URL + SK key). The key is
stored ENCRYPTED and only ever returned masked. Models are selected globally via the
``custom:<id>`` provider string (see :class:`api.core.ai_client.AIClient`).
"""
import os
import ipaddress
from urllib.parse import urlparse

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from api.models import CustomAIModel
from api.core.ai_client import AIClient
from api.core.rate_limit import check_rate_limit


def _allow_internal_urls() -> bool:
    """Whether localhost / private-IP model endpoints are permitted.

    Allowed by default so bring-your-own local models (e.g. Ollama on
    localhost:11434, or a LAN endpoint) work out of the box — this is the user's own
    configured endpoint. Security-conscious deployments can re-enable the SSRF block
    with CUSTOM_MODEL_BLOCK_INTERNAL=True.
    """
    return os.environ.get('CUSTOM_MODEL_BLOCK_INTERNAL', 'False') != 'True'


def _serialize(m: CustomAIModel) -> dict:
    """Client-safe view — never includes the decrypted key, only a mask."""
    return {
        'id': m.pk,
        'provider_id': m.provider_id,   # 'custom:<id>' — what the selector stores
        'name': m.name,
        'base_url': m.base_url,
        'key_masked': m.key_masked,
        'created_at': m.created_at.isoformat(),
        'updated_at': m.updated_at.isoformat(),
    }


def _validate_base_url(url: str) -> str:
    """Reject non-http(s) and obvious internal/loopback targets (light SSRF guard).

    Hostnames that aren't IP literals are allowed (we don't resolve DNS here), but any
    private/loopback/link-local IP literal or localhost-style name is refused.
    """
    url = (url or '').strip()
    if not url:
        raise ValueError('接口链接不能为空')
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('接口链接必须以 http:// 或 https:// 开头')
    host = (parsed.hostname or '').lower()
    if not host:
        raise ValueError('接口链接缺少主机名')
    # In dev (or with explicit opt-in) allow localhost/private so a local Ollama works.
    if _allow_internal_urls():
        return url
    if host == 'localhost' or host.endswith('.local') or host.endswith('.internal'):
        raise ValueError('不允许指向本机/内网地址')
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    ):
        raise ValueError('不允许指向本机/内网地址')
    return url


class CustomModelListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        models = CustomAIModel.objects.filter(user=request.user)
        return Response({'models': [_serialize(m) for m in models]})

    def post(self, request):
        name = str(request.data.get('name', '')).strip()[:120]
        base_url = str(request.data.get('base_url', '')).strip()[:500]
        api_key = str(request.data.get('api_key', '')).strip()

        if not name:
            return Response({'error': '模型名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_url = _validate_base_url(base_url)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if not api_key:
            return Response({'error': 'SK 密钥不能为空'}, status=status.HTTP_400_BAD_REQUEST)

        m = CustomAIModel(user=request.user, name=name, base_url=base_url)
        m.set_api_key(api_key)
        m.save()
        return Response({'model': _serialize(m)}, status=status.HTTP_201_CREATED)


class CustomModelDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk, user):
        return get_object_or_404(CustomAIModel, pk=pk, user=user)

    def patch(self, request, pk):
        m = self._get(pk, request.user)
        if 'name' in request.data:
            name = str(request.data['name']).strip()[:120]
            if not name:
                return Response({'error': '模型名称不能为空'}, status=status.HTTP_400_BAD_REQUEST)
            m.name = name
        if 'base_url' in request.data:
            try:
                m.base_url = _validate_base_url(str(request.data['base_url']).strip()[:500])
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        # Only rotate the key when a non-empty value is supplied (blank = keep existing).
        new_key = str(request.data.get('api_key', '')).strip()
        if new_key:
            m.set_api_key(new_key)
        m.save()
        return Response({'model': _serialize(m)})

    def delete(self, request, pk):
        m = self._get(pk, request.user)
        m.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CustomModelTestView(APIView):
    """Ping a saved model. Returns AIClient.ping()'s structured status (no billing)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        m = get_object_or_404(CustomAIModel, pk=pk, user=request.user)
        try:
            result = AIClient(m.provider_id).ping()
        except ValueError as e:
            result = {'status': 'unconfigured', 'http': None, 'body': None, 'error': str(e), 'tokens': None}
        return Response(result)


# 官方（平台密钥）模型白名单 — 与前端 AiModelSelector 的 BUILTIN_OPTIONS 保持一致。
OFFICIAL_PROVIDERS = (
    'deepseek', 'deepseek_flash', 'gemini', 'gpt5_4', 'gpt5_mini',
    'gpt5_6_sol', 'gpt5_6_terra', 'gpt5_6_luna',
)
# ping 成功但 provider 未返回 usage 时的计费下限（token 数）
OFFICIAL_TEST_MIN_TOKENS = 10


class OfficialModelTestView(APIView):
    """Ping an OFFICIAL (platform-key) provider — billed in AT on success.

    Custom-model tests are free because they burn the user's own key; an official
    ping burns the platform's quota, so a successful test bills tokens x 2 AT (the
    same rate ``generate()`` uses, floored at OFFICIAL_TEST_MIN_TOKENS). Failed
    pings (auth / ratelimited / network) cost nothing — those are our problem,
    not the user's.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        provider = str(request.data.get('provider', '')).strip().lower()
        if provider not in OFFICIAL_PROVIDERS:
            return Response({'error': '未知的官方模型'}, status=status.HTTP_400_BAD_REQUEST)

        limited = check_rate_limit(request.user.id, 'official_model_test', max_calls=5, window=60)
        if limited is not None:
            return limited

        min_cost = OFFICIAL_TEST_MIN_TOKENS * 2
        if request.user.at_balance < min_cost:
            return Response(
                {'error': f'AT币余额不足，测试需要至少 {min_cost} AT，当前余额 {request.user.at_balance} AT'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = AIClient(provider).ping()

        at_cost = 0
        if result.get('status') == 'ok':
            from api.models import TransactionRecord
            tokens = result.get('tokens') or 0
            at_cost = max(tokens, OFFICIAL_TEST_MIN_TOKENS) * 2
            TransactionRecord.record(
                request.user, TransactionRecord.Currency.AT_COIN, -at_cost,
                f'官方模型连通性测试 ({provider})',
            )
        return Response({**result, 'at_cost': at_cost})


class CustomModelTestConfigView(APIView):
    """Ping an UNSAVED config {name, base_url, api_key} — used by the add modal."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = str(request.data.get('name', '')).strip()
        api_key = str(request.data.get('api_key', '')).strip()
        try:
            base_url = _validate_base_url(str(request.data.get('base_url', '')).strip())
        except ValueError as e:
            return Response(
                {'status': 'reqerror', 'http': None, 'body': None, 'error': str(e), 'tokens': None}
            )
        if not name or not api_key:
            return Response(
                {'status': 'unconfigured', 'http': None, 'body': None, 'error': None, 'tokens': None}
            )
        result = AIClient.transient(base_url, api_key, name).ping()
        return Response(result)
