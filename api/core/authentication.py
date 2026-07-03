from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


ACCESS_COOKIE_NAME = 'access_token'
REFRESH_COOKIE_NAME = 'refresh_token'
CSRF_COOKIE_NAME = 'aielts_csrf'
CSRF_HEADER_NAME = 'HTTP_X_CSRF_TOKEN'  # WSGI form of X-CSRF-Token
SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')


class SingleDeviceJWTAuthentication(JWTAuthentication):
    """
    Auth class with two responsibilities:
      1. Read the JWT from an httpOnly cookie (with a fallback to the Authorization
         header so legacy clients and curl-based debugging still work).
      2. Enforce single-device login by checking that the token's `jwt_token_id`
         matches the value persisted on the user row.

    When the token came from a cookie and the request is state-changing, we also
    enforce a double-submit CSRF token: the non-httpOnly `aielts_csrf` cookie
    must equal the `X-CSRF-Token` request header. This pattern is safe because
    a cross-origin attacker can plant the cookie via the browser but cannot read
    it (Same-Origin Policy), so cannot echo it back in the header.

    Cookies are AMBIENT — browsers attach them to every request whether the user
    is trying to authenticate or not — so a stale/expired/invalidated cookie is
    treated as "not authenticated" (return None) rather than a hard 401. That
    lets AllowAny endpoints (/auth/login, /auth/register, /auth/logout) keep
    working when the user's cookies have gone bad, so they don't have to
    manually clear cookies to recover. Protected endpoints still 401 through
    IsAuthenticated because request.user ends up as AnonymousUser.
    Header-based auth (Authorization: Bearer …) is the explicit path and stays
    strict — a bad header token is a hard 401.
    """

    def authenticate(self, request):
        cookie_token = request.COOKIES.get(ACCESS_COOKIE_NAME)
        if not cookie_token:
            return super().authenticate(request)

        try:
            validated_token = self.get_validated_token(cookie_token)
            user = self.get_user(validated_token)
        except (InvalidToken, AuthenticationFailed):
            return None

        if request.method not in SAFE_METHODS:
            cookie_csrf = request.COOKIES.get(CSRF_COOKIE_NAME, '')
            header_csrf = request.META.get(CSRF_HEADER_NAME, '')
            if not cookie_csrf or cookie_csrf != header_csrf:
                # Treat as anonymous — protected endpoints still reject via
                # IsAuthenticated, AllowAny endpoints (login) still work.
                return None

        return user, validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        # 校验 Token 内含的 jwt_token_id 是否与数据库一致（单设备登录）
        token_id_in_jwt = validated_token.get('jwt_token_id')
        if not token_id_in_jwt or str(user.jwt_token_id) != str(token_id_in_jwt):
            raise AuthenticationFailed('该账号已在其他设备登录，请重新登录', code='token_invalidated')
        return user
