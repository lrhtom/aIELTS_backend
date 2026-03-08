"""
AI API 调用封装 — 将 prompt 发送到第三方 AI，返回解析后的 JSON
"""
import os
import json
import re
from .ai_client import AIClient


def call_ai_api(prompt: str, provider: str = 'deepseek', user_id: int = None) -> dict:
    """调用 AI API 并返回解析后的 JSON 对象，内部委托给 AIClient"""
    client = AIClient(provider=provider)
    messages = [{'role': 'user', 'content': prompt}]
    
    try:
        # expect_json=True will make generate() return a parsed dict AND the at_cost
        result, at_cost = client.generate(messages, expect_json=True, temperature=0.7, user_id=user_id)
        # 强制塞入 atConsumed 字段，让前面的拦截器捕获
        result['atConsumed'] = at_cost
        return result
    except ValueError as e:
        print(f"[AI] ❌ JSON 解析失败: {e}", flush=True)
        # 上层期望返回一个 dict 且可能会带有错误或容错处理机制
        # 原逻辑是解析报错时抛出异常或打印，并在 view 捕获 Exception
        # 我们这里直接将异常抛出，与原行为一致
        raise # 抛出异常，让调用方决定怎么处理，但我们用明确的信息包装它
        # The original instruction had a duplicate raise statement, keeping the first one.
        # raise ValueError(f"Failed to parse AI response as JSON: {e}")
