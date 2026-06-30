"""Root-level conftest.

- Django settings 由 pytest.ini 的 DJANGO_SETTINGS_MODULE 处理（pytest-django 接管）。
- fixture 定义集中在 tests/conftest.py，本文件只保留全局策略。
- 凡是没标 @pytest.mark.live_ai 的测试，禁止真实打 AI 上游 / Redis 上游。
"""
import pytest


def pytest_collection_modifyitems(config, items):
    """没标 live_ai 的测试若意外 import `requests` 直发请求，由 responses fixture
    在 tests/conftest.py 里强制激活的 `mocked_responses` fixture 兜底拦截。"""
    for item in items:
        if 'live_ai' not in item.keywords and 'integration' not in item.keywords:
            item.add_marker(pytest.mark.unit)
