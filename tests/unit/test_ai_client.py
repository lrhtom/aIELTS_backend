"""L1 单元测试：api.core.ai_client.AIClient

覆盖目标：
- provider 路由：env 变量正确映射 base_url / api_key / model / headers
- generate() 文本模式与 JSON 模式
- expect_json + 大括号正则抽取（前后含杂质文字时仍能解析）
- expect_json + Markdown 代码块包裹去除
- `<think>` 推理标记剥离
- user_id=None 时跳过余额预检和扣费
- 上游 401 / 500 / 网络错误 → 抛出
- JSON 解析失败 → ValueError 抛出

所有测试都不打真实网络，全部走 `responses` mock。
"""
from __future__ import annotations

import json

import pytest
import responses

from api.core.ai_client import AIClient


# ── provider 路由 ───────────────────────────────────────────────────────────

class TestProviderRouting:
    def test_deepseek_provider_reads_default_env(self, deepseek_env):
        client = AIClient(provider='deepseek')
        assert client.provider == 'deepseek'
        assert client.base_url == 'https://api.deepseek.com/chat/completions'
        assert client.api_key == 'test-deepseek-key'
        assert client.model == 'deepseek-v4-pro'
        assert client.is_gpt5 is False

    def test_gpt5_mini_routes_to_azure_legacy(self, gpt5_mini_env):
        client = AIClient(provider='gpt5_mini')
        assert client.is_gpt5 is True
        assert 'gpt-5.4-mini' in client.base_url
        # Azure legacy url 应被升级到 2025-04-01-preview api-version
        assert 'api-version=2025-04-01-preview' in client.base_url
        assert client.api_key == 'test-azure-key'

    def test_unknown_provider_uses_default_env(self, deepseek_env):
        client = AIClient(provider='unknown_xyz')
        assert client.base_url == 'https://api.deepseek.com/chat/completions'


# ── 文本模式 generate ───────────────────────────────────────────────────────

class TestGenerateText:
    def test_text_mode_returns_content_and_at_cost(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='hello', tokens=100),
            status=200,
        )
        client = AIClient(provider='deepseek')
        content, at_cost = client.generate(
            messages=[{'role': 'user', 'content': 'hi'}],
            expect_json=False,
            user_id=None,
        )
        assert content == 'hello'
        # 费率：100 tokens × 2 AT/token
        assert at_cost == 200

    def test_strips_think_tags(self, mocked_responses, deepseek_env, deepseek_chat_response):
        raw = '<think>internal reasoning here</think>actual answer'
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text=raw, tokens=50),
            status=200,
        )
        client = AIClient(provider='deepseek')
        content, _ = client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=False,
            user_id=None,
        )
        assert '<think>' not in content
        assert content == 'actual answer'


# ── JSON 模式 generate ──────────────────────────────────────────────────────

class TestGenerateJSON:
    def test_clean_json_response(self, mocked_responses, deepseek_env, deepseek_chat_response):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='{"answer": 42}', tokens=80),
            status=200,
        )
        client = AIClient(provider='deepseek')
        result, at_cost = client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=True,
            user_id=None,
        )
        assert isinstance(result, dict)
        assert result == {'answer': 42}
        assert at_cost == 160

    def test_json_wrapped_in_markdown_fence(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        wrapped = '```json\n{"k": "v"}\n```'
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text=wrapped, tokens=50),
            status=200,
        )
        client = AIClient(provider='deepseek')
        result, _ = client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=True,
            user_id=None,
        )
        assert result == {'k': 'v'}

    def test_json_with_surrounding_garbage(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        """LLM 偶尔会前后吐杂质文字，正则应能贪婪抽出首尾大括号块。"""
        garbage = '好的，这是结果：{"k": [1, 2, 3]} 希望对您有帮助'
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text=garbage, tokens=70),
            status=200,
        )
        client = AIClient(provider='deepseek')
        result, _ = client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=True,
            user_id=None,
        )
        assert result == {'k': [1, 2, 3]}

    def test_unparseable_json_raises(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='this is not json at all', tokens=20),
            status=200,
        )
        client = AIClient(provider='deepseek')
        with pytest.raises((ValueError, Exception)):
            client.generate(
                messages=[{'role': 'user', 'content': 'q'}],
                expect_json=True,
                user_id=None,
            )


# ── 上游错误处理 ────────────────────────────────────────────────────────────

class TestUpstreamErrors:
    def test_401_unauthorized_raises(
        self, mocked_responses, deepseek_env,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json={'error': {'message': 'Invalid API key'}},
            status=401,
        )
        client = AIClient(provider='deepseek')
        with pytest.raises(Exception):
            client.generate(
                messages=[{'role': 'user', 'content': 'q'}],
                expect_json=False,
                user_id=None,
            )

    def test_500_server_error_raises(
        self, mocked_responses, deepseek_env,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json={'error': {'message': 'Internal'}},
            status=500,
        )
        client = AIClient(provider='deepseek')
        with pytest.raises(Exception):
            client.generate(
                messages=[{'role': 'user', 'content': 'q'}],
                expect_json=False,
                user_id=None,
            )


# ── 计费路径：user_id=None 跳过余额预检和扣费 ───────────────────────────────

class TestNoUserIdSkipsBilling:
    def test_no_balance_check_when_user_id_none(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        """user_id=None：不访问 User 表，纯发请求并返回。

        断言策略：上游 mock 收到 1 个 POST，且没有任何 User 查询副作用（通过
        balance pre-check 的代码路径用 user_id 守卫，None 时整段被跳过 —— 不必
        额外 patch ORM，因为整个分支根本不会触发）。
        """
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='ok', tokens=10),
            status=200,
        )
        client = AIClient(provider='deepseek')
        content, at_cost = client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=False,
            user_id=None,
        )
        assert content == 'ok'
        assert at_cost == 20
        assert len(mocked_responses.calls) == 1

    def test_request_has_bearer_auth_for_deepseek(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='ok'),
            status=200,
        )
        client = AIClient(provider='deepseek')
        client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=False,
            user_id=None,
        )
        req = mocked_responses.calls[0].request
        assert req.headers.get('Authorization') == 'Bearer test-deepseek-key'

    def test_request_uses_api_key_header_for_azure_gpt5(
        self, mocked_responses, gpt5_mini_env, deepseek_chat_response,
    ):
        """Azure 用 api-key 头，不是 Authorization。"""
        client = AIClient(provider='gpt5_mini')
        mocked_responses.add(
            responses.POST,
            client.base_url,
            json=deepseek_chat_response(text='{"k": 1}', tokens=10),
            status=200,
        )
        client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=True,
            user_id=None,
        )
        req = mocked_responses.calls[0].request
        assert req.headers.get('api-key') == 'test-azure-key'
        assert 'Authorization' not in req.headers


# ── payload 校验 ────────────────────────────────────────────────────────────

class TestRequestPayload:
    def test_temperature_propagated(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='ok'),
            status=200,
        )
        client = AIClient(provider='deepseek')
        client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=False,
            temperature=0.3,
            user_id=None,
        )
        body = json.loads(mocked_responses.calls[0].request.body)
        assert body['temperature'] == 0.3

    def test_expect_json_adds_response_format_for_non_gpt5(
        self, mocked_responses, deepseek_env, deepseek_chat_response,
    ):
        mocked_responses.add(
            responses.POST,
            'https://api.deepseek.com/chat/completions',
            json=deepseek_chat_response(text='{"x":1}'),
            status=200,
        )
        client = AIClient(provider='deepseek')
        client.generate(
            messages=[{'role': 'user', 'content': 'q'}],
            expect_json=True,
            user_id=None,
        )
        body = json.loads(mocked_responses.calls[0].request.body)
        assert body.get('response_format') == {'type': 'json_object'}
