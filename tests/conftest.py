"""tests/ 级 conftest：公共 fixtures。

提供给所有测试用的共享设施：
- `mocked_responses`: responses 库的 RequestsMock 实例（用于 HTTP mock）
- `frozen_now`: 固定时间锚点，用于 FSRS 等时间敏感测试
- `fake_redis`: fakeredis 实例 + monkeypatch 替换全局 redis client
- 各 provider 的 AI 响应样板（fixtures 形式）
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import responses


# ── HTTP mock ────────────────────────────────────────────────────────────────

@pytest.fixture
def mocked_responses():
    """所有要用 HTTP mock 的测试都依赖这个 fixture。

    用法：
        def test_xxx(mocked_responses):
            mocked_responses.add(
                responses.POST,
                'https://api.deepseek.com/chat/completions',
                json={'choices': [{'message': {'content': 'hi'}}]},
                status=200,
            )
            ...
    """
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


# ── 时间 ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def frozen_now():
    """统一时间锚：2026-06-27 12:00:00 UTC。

    FSRS 测试用这个推算 due / elapsed_days，避免依赖 datetime.now()。
    """
    return datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)


# ── Redis mock ───────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis(monkeypatch):
    """替换 api.core.redis_client.get_redis() 返回 fakeredis 实例。

    rate_limit / ai_cache / singleflight 测试用这个隔离上游 Upstash。
    """
    import fakeredis
    r = fakeredis.FakeStrictRedis(decode_responses=False)

    def _factory():
        return r

    monkeypatch.setattr('api.core.redis_client.get_redis', _factory)
    return r


# ── 各 provider 的 AI 响应样板 ──────────────────────────────────────────────

@pytest.fixture
def deepseek_chat_response():
    """DeepSeek / 标准 Chat Completions 响应骨架。`text` 由测试自行替换。"""
    def _build(text: str = '示例输出', tokens: int = 100):
        return {
            'id': 'chat-cmpl-test',
            'object': 'chat.completion',
            'choices': [
                {'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'},
            ],
            'usage': {'prompt_tokens': 50, 'completion_tokens': 50, 'total_tokens': tokens},
        }
    return _build


@pytest.fixture
def deepseek_env(monkeypatch):
    """注入 DeepSeek provider 的最小 env 变量。"""
    monkeypatch.setenv('AI_BASE_URL', 'https://api.deepseek.com/chat/completions')
    monkeypatch.setenv('AI_API_KEY', 'test-deepseek-key')
    monkeypatch.setenv('AI_MODEL', 'deepseek-v4-pro')


@pytest.fixture
def gpt5_mini_env(monkeypatch):
    """Azure GPT-5.4-mini provider 的最小 env 变量（legacy Chat Completions 路径）。"""
    monkeypatch.setenv(
        'GPT5MINI_BASE_URL',
        'https://aieltsai.openai.azure.com/openai/deployments/gpt-5.4-mini/'
        'chat/completions?api-version=2024-02-01',
    )
    monkeypatch.setenv('GPT5MINI_API_KEY', 'test-azure-key')
    monkeypatch.setenv('GPT5MINI_MODEL', 'gpt-5.4-mini')
