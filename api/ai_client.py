import os
import json
import re
import requests
from django.contrib.auth import get_user_model

class AIClient:
    """
    通用 AI 模型客户端封装。
    支持对 DeepSeek, Gemini, Doubao, Qwen 等不同 Base URL 和密钥的管理。
    """
    def __init__(self, provider: str = 'deepseek'):
        self.provider = provider
        
        if provider == 'gemini':
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            self.api_key = os.environ.get('GEMINI_API_KEY', '')
            self.model = os.environ.get('GEMINI_MODEL', 'gemini-3.0-flash')
        elif provider == 'gpt5':
            self.base_url = os.environ.get('GPT5_BASE_URL', '')
            self.api_key = os.environ.get('GPT5_API_KEY', '')
            self.model = os.environ.get('GPT5_MODEL', 'gpt-5.3-chat')
        else:
            self.base_url = os.environ.get('AI_BASE_URL', '')
            self.api_key = os.environ.get('AI_API_KEY', '')
            self.model = os.environ.get('AI_MODEL', '')

    def generate(self, messages: list, expect_json: bool = False, temperature: float = 0.7, user_id: int = None) -> str | dict:
        """
        向 AI发起请求的通用函数。
        :param messages: OpenAI 格式的 messages 数组 [{'role': 'user', 'content': '...'}, ...]
        :param expect_json: 若为 True，则尝试使用正则提取大括号内容，并自动 json.loads() 转换为字典
        :param temperature: 温度参数
        :return: 字符串，或解析好的 dict (若 expect_json=True)
        """
        print(f"[AIClient] 🚀 准备发送请求")
        print(f"[AIClient]   提供商: {self.provider}")
        print(f"[AIClient]   模  型: {self.model}")
        print(f"[AIClient]   地  址: {self.base_url}")
        print(f"[AIClient]   用户ID: {user_id}")

        # 1. 预检：检查余额是否已为负
        if user_id:
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
                if user.at_balance < 0:
                    print(f"[AIClient] 🚨 拦截负余额用户: {user.username}, 余额: {user.at_balance}")
                    raise ValueError(f"您的AT币余额不足({user.at_balance})，请充值后重试。")
            except Exception as e:
                print(f"[AIClient] ⚠️ 预检失败: {e}")
                raise e
        
        # 构建请求头
        headers = {'Content-Type': 'application/json'}
        if self.provider == 'gpt5':
            headers['api-key'] = self.api_key
        else:
            headers['Authorization'] = f'Bearer {self.api_key}'

        # Azure Responses API (gpt5) 使用不同的请求格式
        if self.provider == 'gpt5':
            # Responses API 格式：input 数组，每条 message 包含 role 和 content
            gpt5_input = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
            # gpt5 不支持 response_format，用 system 消息强制 JSON 输出
            if expect_json:
                gpt5_input.insert(0, {
                    'role': 'system',
                    'content': (
                        'You MUST respond with ONLY a valid JSON object. '
                        'Do NOT include any markdown, code fences, or extra text. '
                        'Output raw JSON only.'
                    )
                })
            payload = {
                'model': self.model,
                'input': gpt5_input,
            }
        else:
            payload = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature,
            }
            if expect_json:
                payload['response_format'] = {'type': 'json_object'}

        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"[AIClient] ❌ HTTP Error: {e.response.status_code}")
            print(f"[AIClient]   Response: {e.response.text}")
            raise e

        data = response.json()

        # 解析响应内容：Responses API 和 Chat Completions API 路径不同
        if self.provider == 'gpt5':
            # Responses API: 遍历 output 找 type=='message'（第一项可能是 reasoning summary）
            print(f"[AIClient][gpt5] 原始响应 keys: {list(data.keys())}")
            try:
                msg_block = next(
                    item for item in data['output'] if item.get('type') == 'message'
                )
                ai_content = msg_block['content'][0]['text']
            except (StopIteration, KeyError, IndexError, TypeError) as parse_err:
                print(f"[AIClient] ❌ gpt5 响应解析失败，output: {str(data.get('output', ''))[:800]}")
                raise ValueError(f"gpt5 响应格式异常，无法提取内容: {parse_err}") from parse_err
        else:
            ai_content = data['choices'][0]['message']['content']
        
        # 获取真实 Token 消耗（兼容 Chat Completions 和 Responses API 两种格式）
        usage = data.get('usage', {})
        if self.provider == 'gpt5':
            # Responses API: input_tokens + output_tokens
            total_tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
        else:
            # Chat Completions API: total_tokens
            total_tokens = usage.get('total_tokens', 0)
        # 费率：1 Token = 2 AT 币
        at_cost = total_tokens * 2

        # 剔除推理过程
        ai_content = re.sub(r'<think>[\s\S]*?</think>', '', ai_content).strip()

        # 2. 扣费（允许穿透到负数）
        if user_id:
            User = get_user_model()
            user = User.objects.get(id=user_id)
            user.at_balance -= at_cost
            user.save()
            print(f"[AIClient] ✅ Token 计费成功: 消耗{total_tokens}T -> {at_cost}AT, 最终余额{user.at_balance}")

        if not expect_json:
            return ai_content, at_cost

        print(f"[AIClient]   尝试提取与解析 JSON...")
        # 去掉可能的 markdown 代码块包裹
        ai_content = ai_content.replace('```json', '').replace('```', '').strip()
        
        # 强制抽取首尾大括号的内容（贪婪匹配），避免前后多余文字导致解析失败
        json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = ai_content

        try:
            parsed = json.loads(json_str)
            print(f"[AIClient] ✅ JSON 解析成功")
            return parsed, at_cost
        except json.JSONDecodeError as e:
            print(f"[AIClient] ❌ JSON 解析崩溃: {e}")
            print(f"[AIClient] ⚠️ 失效的原始字符串: {repr(ai_content[:200])}")
            # 如果强制要求 JSON 却解析失败，则抛出异常让上层函数进行异常处理
            raise ValueError("AI Client Failed to parse response as JSON. Raw: " + ai_content)
