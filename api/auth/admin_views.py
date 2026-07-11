import os
import time
from pathlib import Path
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from api.models import Feedback, TransactionRecord, BannedIP
from api.serializers import FeedbackSerializer, AdminUserManageSerializer
from api.core.middleware import invalidate_ip_ban_cache

User = get_user_model()


class AdminFeedbackPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminUserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class IsAdminUser(permissions.BasePermission):
    """
    仅限管理员（is_staff）访问。
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

class AdminFeedbackListView(generics.ListAPIView):
    """
    管理员查看所有反馈的接口（分页）
    """
    queryset = Feedback.objects.all().order_by('-created_at')
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminFeedbackPagination

class AdminFeedbackUpdateView(generics.UpdateAPIView):
    """
    管理员更新反馈状态（如标记解决）
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]
    
    def patch(self, request, *args, **kwargs):
        # 仅允许更新 is_resolved 字段。
        instance = self.get_object()
        is_resolved = request.data.get('is_resolved')
        if is_resolved is not None:
            instance.is_resolved = is_resolved
            instance.save()
            return Response(FeedbackSerializer(instance).data)
        return Response({"error": "Missing is_resolved field"}, status=status.HTTP_400_BAD_REQUEST)

class AdminFeedbackDeleteView(generics.DestroyAPIView):
    """
    管理员删除反馈记录。
    """
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [IsAdminUser]


class AdminUserListView(generics.ListAPIView):
    """
    管理员查看用户列表（分页）。
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserManageSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminUserPagination


class AdminUserBanToggleView(APIView):
    """
    管理员封禁/解封用户。
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.is_staff or target_user.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_ADMIN'}, status=status.HTTP_403_FORBIDDEN)

        is_banned = request.data.get('is_banned')
        if is_banned is None:
            return Response({'error': 'MISSING_IS_BANNED'}, status=status.HTTP_400_BAD_REQUEST)

        target_user.is_banned = bool(is_banned)
        target_user.save(update_fields=['is_banned', 'updated_at'])
        return Response(AdminUserManageSerializer(target_user).data, status=status.HTTP_200_OK)


class AdminUserDeleteView(APIView):
    """
    管理员删除用户。
    """
    permission_classes = [IsAdminUser]

    def delete(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.is_staff or target_user.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_ADMIN'}, status=status.HTTP_403_FORBIDDEN)

        target_user.delete()
        return Response({'message': 'USER_DELETED'}, status=status.HTTP_200_OK)


class AdminUserPromoteToggleView(APIView):
    """
    管理员晋升/降级用户 (切换 is_staff)。
    - 不允许修改超级用户 (is_superuser)。
    - 不允许操作自己 (防止把自己降级)。
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target_user.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_SUPERUSER'}, status=status.HTTP_403_FORBIDDEN)

        if target_user.pk == request.user.pk:
            return Response({'error': 'CANNOT_MODIFY_SELF'}, status=status.HTTP_403_FORBIDDEN)

        target_user.is_staff = not target_user.is_staff
        target_user.save(update_fields=['is_staff', 'updated_at'])
        return Response(AdminUserManageSerializer(target_user).data, status=status.HTTP_200_OK)


class AdminUserAdjustATView(APIView):
    """管理员调整用户 AT 币余额。"""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        amount = request.data.get('amount')
        if amount is None:
            return Response({'error': 'MISSING_AMOUNT'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delta = int(amount)
        except (ValueError, TypeError):
            return Response({'error': 'INVALID_AMOUNT'}, status=status.HTTP_400_BAD_REQUEST)

        actual_delta = delta
        if target_user.at_balance + delta < 0:
            actual_delta = -target_user.at_balance
            
        from api.models import TransactionRecord
        TransactionRecord.record(target_user, TransactionRecord.Currency.AT_COIN, actual_delta, '管理员手动调整')
        target_user.save(update_fields=['updated_at'])

        return Response({
            'user_id': target_user.id,
            'username': target_user.username,
            'at_balance': target_user.at_balance,
            'delta': delta,
        }, status=status.HTTP_200_OK)


class AdminAIUsageView(APIView):
    """全站 AI 使用统计 (管理员)。

    GET /api/admin/ai-usage?mode=all&days=30
        → 全站每日 AT 币消耗 (所有用户求和)。
    GET /api/admin/ai-usage?mode=user&user_id=13&days=30
        → 指定用户每日 AT 币消耗。

    数据源: TransactionRecord 里所有 amount<0 的 AT_COIN 交易 (即消耗)。
    包含了 AI 生成 + 商店购买等所有 AT 出账 (AI 生成占绝大多数)。
    描述字段被回传前端,如果日后要按 description 拆细维度可以在前端做二次分组。

    响应格式:
    {
        "days": 30,
        "series": [
            {"date": "2026-06-04", "at_consumed": 1234, "call_count": 45},
            ...
        ],
        "totals": {"at_consumed": 45678, "call_count": 890}
    }

    单用户模式额外附带 user 摘要供前端展示。
    """
    permission_classes = [IsAdminUser]

    MAX_DAYS = 365
    DEFAULT_DAYS = 30

    def get(self, request):
        mode = request.query_params.get('mode', 'all')
        try:
            days = int(request.query_params.get('days', self.DEFAULT_DAYS))
        except ValueError:
            days = self.DEFAULT_DAYS
        days = max(1, min(self.MAX_DAYS, days))

        since = timezone.now() - timedelta(days=days - 1)
        # 只统计"负值 AT_COIN"(出账)。收入(签到/管理员发放)不算 AI 使用。
        qs = TransactionRecord.objects.filter(
            currency=TransactionRecord.Currency.AT_COIN,
            amount__lt=0,
            created_at__gte=since.replace(hour=0, minute=0, second=0, microsecond=0),
        )

        user_summary = None
        if mode == 'user':
            user_id = request.query_params.get('user_id')
            if not user_id:
                return Response({'error': 'MISSING_USER_ID'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                target = User.objects.get(pk=int(user_id))
            except (User.DoesNotExist, ValueError, TypeError):
                return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(user=target)
            user_summary = {
                'id': target.id,
                'username': target.username,
                'nickname': target.nickname or '',
                'at_balance': target.at_balance,
            }

        agg = (
            qs.annotate(day=TruncDate('created_at'))
              .values('day')
              .annotate(at_consumed=Sum('amount'), call_count=Count('id'))
              .order_by('day')
        )

        # Fill missing days with zeros so the chart doesn't have gaps.
        by_day = {row['day'].isoformat(): row for row in agg}
        series = []
        cursor = since.date()
        end = timezone.now().date()
        while cursor <= end:
            key = cursor.isoformat()
            if key in by_day:
                row = by_day[key]
                at_val = -int(row['at_consumed'] or 0)  # flip sign; expenses reported as positive
                cnt = int(row['call_count'] or 0)
            else:
                at_val, cnt = 0, 0
            series.append({'date': key, 'at_consumed': at_val, 'call_count': cnt})
            cursor += timedelta(days=1)

        totals = {
            'at_consumed': sum(s['at_consumed'] for s in series),
            'call_count': sum(s['call_count'] for s in series),
        }

        return Response({
            'mode': mode,
            'days': days,
            'user': user_summary,
            'series': series,
            'totals': totals,
        })


class AdminUserSearchView(APIView):
    """
    GET /api/admin/users/search?q=xxx&limit=20
    Lightweight user picker for the AI-usage single-user view. Returns id +
    username + nickname only — the paginated /admin/users list is too heavy
    for a live search-as-you-type input.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        q = (request.query_params.get('q') or '').strip()
        try:
            limit = min(50, max(1, int(request.query_params.get('limit', 20))))
        except ValueError:
            limit = 20

        qs = User.objects.all()
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(username__icontains=q) | Q(nickname__icontains=q) | Q(email__icontains=q))
        qs = qs.order_by('-date_joined')[:limit]

        return Response({
            'results': [
                {
                    'id': u.id,
                    'username': u.username,
                    'nickname': u.nickname or '',
                    'is_staff': u.is_staff,
                }
                for u in qs
            ],
        })


class AdminRoutesView(APIView):
    """
    管理员专用：实时返回后端所有 URL 路由（通过 Django URL resolver 自省）。
    前端路由可视化页面用此接口替代手写的静态数据文件。
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.urls import get_resolver
        import re

        def _method_label(callback) -> str:
            """从 View 类猜测支持的 HTTP 方法。"""
            http_methods = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
            if hasattr(callback, 'view_class'):
                cls = callback.view_class
                supported = [m.upper() for m in http_methods if hasattr(cls, m)]
                return '|'.join(supported) if supported else 'GET'
            if hasattr(callback, 'actions'):
                # ViewSet
                return '|'.join(v.upper() for v in callback.actions.values())
            return 'GET'

        def _handler_name(callback) -> str:
            if hasattr(callback, 'view_class'):
                return callback.view_class.__name__
            return getattr(callback, '__name__', str(callback))

        def _walk(resolver, prefix=''):
            endpoints = []
            for pattern in resolver.url_patterns:
                try:
                    raw = str(pattern.pattern)
                    # Strip regex anchors from older-style patterns
                    raw = re.sub(r'^\^', '', raw).rstrip('$')
                    path = prefix + raw
                except Exception:
                    continue

                if hasattr(pattern, 'url_patterns'):
                    # URLResolver — recurse
                    endpoints.extend(_walk(pattern, prefix=path))
                else:
                    # URLPattern — leaf endpoint
                    cb = pattern.callback
                    endpoints.append({
                        'method':  _method_label(cb),
                        'path':    '/' + path.lstrip('/'),
                        'handler': _handler_name(cb),
                        'name':    pattern.name or '',
                    })
            return endpoints

        resolver = get_resolver()
        # Only expose routes under /api/
        all_routes = _walk(resolver)
        api_routes = [r for r in all_routes if r['path'].startswith('/api/')]

        # Group by second segment (e.g. /api/auth/…  → "auth")
        groups: dict[str, list] = {}
        for r in api_routes:
            parts = r['path'].lstrip('/').split('/')
            # parts[0] = 'api', parts[1] = module name
            module = parts[1] if len(parts) > 1 else 'root'
            groups.setdefault(module, []).append(r)

        return Response({
            'total': len(api_routes),
            'groups': [
                {
                    'module': mod,
                    'count': len(routes),
                    'endpoints': routes,
                }
                for mod, routes in sorted(groups.items())
            ],
        })


def _serialize_banned_ip(row: BannedIP) -> dict:
    return {
        'id': row.id,
        'ip_address': row.ip_address,
        'reason': row.reason,
        'banned_at': row.banned_at.isoformat() if row.banned_at else None,
        'banned_by': row.banned_by.username if row.banned_by_id else None,
    }


class AdminBannedIPListView(APIView):
    """GET → list all banned IPs; POST → add a new one (idempotent)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        rows = BannedIP.objects.select_related('banned_by').all()
        return Response({
            'count': rows.count(),
            'items': [_serialize_banned_ip(r) for r in rows],
        })

    def post(self, request):
        ip = str(request.data.get('ip_address') or '').strip()
        reason = str(request.data.get('reason') or '').strip()[:200]
        if not ip:
            return Response({'error': 'MISSING_IP'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate via GenericIPAddressField's built-in cleaner. Reject junk
        # early so the DB doesn't have to.
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_ipv46_address
        try:
            validate_ipv46_address(ip)
        except ValidationError:
            return Response({'error': 'INVALID_IP'}, status=status.HTTP_400_BAD_REQUEST)

        row, created = BannedIP.objects.get_or_create(
            ip_address=ip,
            defaults={'reason': reason, 'banned_by': request.user},
        )
        # If the row already existed but the admin wants to update the reason,
        # let them — it's a small quality-of-life detail so audit trail matches.
        if not created and reason and row.reason != reason:
            row.reason = reason
            row.banned_by = request.user
            row.save(update_fields=['reason', 'banned_by'])

        invalidate_ip_ban_cache(ip)
        return Response(
            _serialize_banned_ip(row),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AdminBannedIPDeleteView(APIView):
    """DELETE /admin/banned-ips/<pk> — remove a ban entry."""
    permission_classes = [IsAdminUser]

    def delete(self, request, pk: int):
        try:
            row = BannedIP.objects.get(pk=pk)
        except BannedIP.DoesNotExist:
            return Response({'error': 'NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)
        ip = row.ip_address
        row.delete()
        invalidate_ip_ban_cache(ip)
        return Response({'message': 'DELETED', 'ip_address': ip})


class AdminUserBanIPView(APIView):
    """POST /admin/users/<pk>/ban-ip — ban the user's `last_ip` in one click.

    Body: {"reason": "optional string"}. If the target user has never logged in
    (no last_ip) we return 400 rather than silently no-op.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk: int):
        try:
            target = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'USER_NOT_FOUND'}, status=status.HTTP_404_NOT_FOUND)

        if target.is_staff or target.is_superuser:
            return Response({'error': 'CANNOT_MODIFY_ADMIN'}, status=status.HTTP_403_FORBIDDEN)

        ip = (target.last_ip or '').strip()
        if not ip:
            return Response({'error': 'USER_HAS_NO_IP'}, status=status.HTTP_400_BAD_REQUEST)

        reason = str(request.data.get('reason') or f'关联用户 {target.username} (#{target.id})').strip()[:200]
        row, created = BannedIP.objects.get_or_create(
            ip_address=ip,
            defaults={'reason': reason, 'banned_by': request.user},
        )
        invalidate_ip_ban_cache(ip)
        return Response(_serialize_banned_ip(row),
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

# ══════════════════════════════════════════════════════════════════════════
# 项目代码统计（管理员实时看板）
# 扫描仓库根下的 frontend/ 与 backend/ 源码，按语言 / 层级 / 目录汇总文件数与行数。
# 生产环境若未部署前端源码，则只统计到后端（优雅降级）。
# ══════════════════════════════════════════════════════════════════════════

_CODE_LANGUAGES = {
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript React',
    '.js': 'JavaScript',
    '.jsx': 'JavaScript React',
    '.mjs': 'JavaScript',
    '.cjs': 'JavaScript',
    '.py': 'Python',
    '.css': 'CSS',
    '.scss': 'SCSS',
    '.html': 'HTML',
    '.json': 'JSON',
    '.md': 'Markdown',
    '.sql': 'SQL',
    '.sh': 'Shell',
    '.yml': 'YAML',
    '.yaml': 'YAML',
    '.toml': 'TOML',
}

# 扫描时跳过的目录（依赖 / 构建产物 / 缓存 / 静态资产 / 非源码）
# 'public' 内多为静态资源与第三方 vendored 脚本（如 webgazer.js），不计入源码。
_SKIP_DIRS = {
    'node_modules', 'dist', 'dist-ssr', 'build', '__pycache__', 'public',
    'venv', 'env', 'staticfiles', 'media', 'evidence', 'coverage',
    '.next', '.turbo', '.cache',
}

# 明确跳过的巨型非源码文件
_SKIP_FILES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'}

_MAX_FILE_BYTES = 3_000_000  # 超大文件（多为生成物）跳过，避免拖慢扫描

_CODE_STATS_CACHE = {'ts': 0.0, 'data': None}
_CODE_STATS_TTL = 20  # 秒；准实时，避免频繁重复扫描


def _scan_code_stats():
    started = time.time()
    root = Path(settings.BASE_DIR).parent  # 仓库根：含 frontend/ 与 backend/
    layers = [('frontend', root / 'frontend'), ('backend', root / 'backend')]

    by_lang, by_layer, by_dir = {}, {}, {}
    largest = []
    totals = {'files': 0, 'lines': 0, 'blank': 0, 'size_bytes': 0}

    for layer_name, layer_path in layers:
        if not layer_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(layer_path):
            # 原地剪枝：跳过依赖/缓存/隐藏目录
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]
            for fn in filenames:
                if fn in _SKIP_FILES:
                    continue
                ext = os.path.splitext(fn)[1].lower()
                lang = _CODE_LANGUAGES.get(ext)
                if not lang:
                    continue

                fpath = Path(dirpath) / fn
                try:
                    size = fpath.stat().st_size
                    if size > _MAX_FILE_BYTES:
                        continue
                    lines = blank = 0
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                        for line in fh:
                            lines += 1
                            if not line.strip():
                                blank += 1
                except OSError:
                    continue

                totals['files'] += 1
                totals['lines'] += lines
                totals['blank'] += blank
                totals['size_bytes'] += size

                lb = by_lang.setdefault(lang, {'files': 0, 'lines': 0})
                lb['files'] += 1
                lb['lines'] += lines

                la = by_layer.setdefault(layer_name, {'files': 0, 'lines': 0})
                la['files'] += 1
                la['lines'] += lines

                rel = fpath.relative_to(root)
                parts = rel.parts
                # 目录桶：取到前 3 段（layer/子目录/子子目录），够细又不过散
                dir_key = '/'.join(parts[:3]) if len(parts) > 3 else '/'.join(parts[:-1])
                db = by_dir.setdefault(dir_key, {'files': 0, 'lines': 0})
                db['files'] += 1
                db['lines'] += lines

                largest.append((lines, rel.as_posix()))

    largest.sort(reverse=True)

    def _rows(mapping, key_name):
        return [
            {key_name: k, 'files': v['files'], 'lines': v['lines']}
            for k, v in sorted(mapping.items(), key=lambda kv: -kv[1]['lines'])
        ]

    return {
        'generated_at': timezone.now().isoformat(),
        'scan_seconds': round(time.time() - started, 3),
        'totals': {
            'files': totals['files'],
            'lines': totals['lines'],
            'blank': totals['blank'],
            'code': totals['lines'] - totals['blank'],
            'size_bytes': totals['size_bytes'],
        },
        'by_language': _rows(by_lang, 'language'),
        'by_layer': _rows(by_layer, 'layer'),
        'by_directory': _rows(by_dir, 'dir')[:12],
        'largest_files': [{'path': p, 'lines': ln} for ln, p in largest[:10]],
    }


class AdminCodeStatsView(APIView):
    """管理员：实时扫描项目源码，返回文件数/行数的多维统计。"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        force = str(request.query_params.get('refresh', '')).lower() in ('1', 'true', 'yes')
        now = time.time()
        fresh = (
            _CODE_STATS_CACHE['data'] is not None
            and (now - _CODE_STATS_CACHE['ts']) < _CODE_STATS_TTL
        )
        if force or not fresh:
            _CODE_STATS_CACHE['data'] = _scan_code_stats()
            _CODE_STATS_CACHE['ts'] = now
            fresh = False

        data = dict(_CODE_STATS_CACHE['data'])
        data['cached'] = bool(fresh and not force)
        return Response(data)
