"""Middleware: IP ban enforcement + last_ip tracking.

Order matters — install BEFORE `AuthenticationMiddleware` so we can reject
banned IPs without touching the DB session; put it AFTER the CORS middleware so
CORS preflights still succeed (browsers won't retry OPTIONS on 403).

Ban lookups hit Redis (`banned_ip:<ip>`) first with a 60-second cache, then
fall back to the `banned_ips` table. Admin views bust the cache on add/remove.
"""
from django.http import JsonResponse

from api.models import BannedIP

_BAN_CACHE_TTL = 60          # seconds — short enough that unbanning takes effect fast
_LAST_IP_UPDATE_TTL = 600    # rate-limit last_ip DB writes to once per 10 min per user


def get_client_ip(request) -> str | None:
    """Best-effort client IP extraction.

    - Trusts `X-Forwarded-For` and takes the *first* entry (Nginx/BT panel
      appends the real client to the front). If nginx is misconfigured a client
      can spoof this — the ban list is thus a soft control, not a security
      boundary. If you deploy behind a proxy chain, tighten this by counting
      known proxies.
    - Falls back to REMOTE_ADDR.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '').strip()
    if xff:
        first = xff.split(',')[0].strip()
        if first:
            return first
    ip = request.META.get('REMOTE_ADDR', '').strip()
    return ip or None


def _is_ip_banned(ip: str) -> bool:
    if not ip:
        return False
    # Redis first — avoids one DB query per request under normal load.
    try:
        from api.core.redis_client import get_redis
        r = get_redis()
        cached = r.get(f'banned_ip:{ip}')
        if cached is not None:
            val = cached.decode('utf-8') if isinstance(cached, bytes) else str(cached)
            return val == '1'
    except Exception:
        pass  # Redis down → fall through to DB.

    banned = BannedIP.objects.filter(ip_address=ip).exists()
    try:
        from api.core.redis_client import get_redis
        get_redis().setex(f'banned_ip:{ip}', _BAN_CACHE_TTL, '1' if banned else '0')
    except Exception:
        pass
    return banned


def invalidate_ip_ban_cache(ip: str) -> None:
    """Called by admin views after adding / removing an entry."""
    if not ip:
        return
    try:
        from api.core.redis_client import get_redis
        get_redis().delete(f'banned_ip:{ip}')
    except Exception:
        pass


class IPBanMiddleware:
    """Reject requests from banned IPs (403).

    Runs before authentication so banned actors can't waste DB CPU on JWT
    validation. Also opportunistically records `user.last_ip` on authenticated
    responses — behind a Redis rate-limit so we don't hammer the row on every
    request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = get_client_ip(request)
        request.client_ip = ip  # exposed for downstream views

        if ip and _is_ip_banned(ip):
            # CORS preflights get a normal 200 so the browser can surface the
            # real 403 on the actual request; skipping this trips the browser
            # into a generic network error and hides the ban from the user.
            if request.method == 'OPTIONS':
                return self.get_response(request)
            return JsonResponse(
                {'error': 'IP_BANNED', 'detail': '该 IP 已被封禁，如有异议请联系管理员。'},
                status=403,
            )

        response = self.get_response(request)

        # Post-response: opportunistic last_ip tracking. Auth may have populated
        # request.user during view execution. Guard against AnonymousUser +
        # missing attributes for early middleware failures.
        try:
            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False) and ip:
                self._maybe_track_last_ip(user, ip)
        except Exception:
            pass

        return response

    @staticmethod
    def _maybe_track_last_ip(user, ip: str) -> None:
        # Cheap fast path — no write if last_ip is already this value AND we
        # updated recently. The Redis key doubles as the rate limiter.
        try:
            from api.core.redis_client import get_redis
            r = get_redis()
            key = f'last_ip_seen:{user.id}'
            cached = r.get(key)
            cached_val = cached.decode('utf-8') if isinstance(cached, bytes) else (cached or '')
            if cached_val == ip:
                return
            r.setex(key, _LAST_IP_UPDATE_TTL, ip)
        except Exception:
            # If Redis is unavailable, we still write — but at least skip when
            # the DB already has the right value.
            if getattr(user, 'last_ip', None) == ip:
                return

        if getattr(user, 'last_ip', None) == ip:
            return
        try:
            user.__class__.objects.filter(pk=user.pk).update(last_ip=ip)
        except Exception:
            pass
