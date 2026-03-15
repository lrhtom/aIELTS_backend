import time
from rest_framework.response import Response
from api.redis_client import get_redis


def check_rate_limit(user_id: int, endpoint: str, max_calls: int, window: int) -> Response | None:
    """
    滑动窗口限流（固定窗口实现）。
    :param user_id:   当前用户 ID
    :param endpoint:  接口标识符，如 'writing_evaluate'
    :param max_calls: 窗口内允许的最大调用次数
    :param window:    窗口大小（秒）
    :return: None = 放行；Response(429) = 限流触发
    """
    try:
        r = get_redis()
        bucket = int(time.time()) // window
        key = f"rl:{endpoint}:{user_id}:{bucket}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, window * 2)   # TTL 稍大于窗口，避免边界问题
        if count > max_calls:
            return Response(
                {'error': f'请求过于频繁，每 {window} 秒最多 {max_calls} 次，请稍后再试。'},
                status=429,
            )
    except Exception as e:
        # Redis 不可用时放行，不影响正常服务
        print(f'[RateLimit] ⚠️ Redis 不可用，跳过限流: {e}')
    return None
