"""
API认证装饰器

提供基于API密钥的简单认证机制。
"""
from functools import wraps
from django.http import JsonResponse
from django.conf import settings


def api_key_required(view_func):
    """
    要求API密钥的装饰器。

    在请求头中需要提供 X-API-Key，其值必须与 settings.API_KEY 匹配。

    如果 settings.API_KEY 未设置（开发环境），则跳过认证检查。
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # 如果API_KEY未设置，跳过认证（开发环境）
        if not settings.API_KEY:
            return view_func(request, *args, **kwargs)

        # 从请求头获取API密钥
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return JsonResponse(
                {'error': 'Missing X-API-Key header'},
                status=401
            )

        # 验证API密钥
        if api_key != settings.API_KEY:
            return JsonResponse(
                {'error': 'Invalid API key'},
                status=403
            )

        return view_func(request, *args, **kwargs)

    return wrapped_view
