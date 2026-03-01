"""
AI API 调用封装 — 将 prompt 发送到第三方 AI，返回解析后的 JSON
"""
import os
import json
import requests


def call_ai_api(prompt: str) -> dict:
    """调用 AI API 并返回解析后的 JSON 对象"""
    base_url = os.environ.get('AI_BASE_URL')
    api_key = os.environ.get('AI_API_KEY')
    model = os.environ.get('AI_MODEL')

    response = requests.post(
        base_url,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
        },
        timeout=120,
    )
    response.raise_for_status()

    data = response.json()
    ai_content = data['choices'][0]['message']['content']

    # 去掉可能的 markdown 代码块包裹
    cleaned = ai_content.replace('```json', '').replace('```', '').strip()
    return json.loads(cleaned)
