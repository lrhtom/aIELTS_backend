import os
from upstash_redis import Redis

_client: Redis | None = None


def get_redis() -> Redis:
    """返回全局 Redis 单例（Upstash HTTP REST 协议，无需持久 socket 连接）。"""
    global _client
    if _client is None:
        _client = Redis(
            url=os.environ.get('REDIS_URL', ''),
            token=os.environ.get('REDIS_TOKEN', ''),
        )
    return _client
