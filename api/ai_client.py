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
            self.api_key = os.environ.get('GEMINI_API_KEY')
            self.model = os.environ.get('GEMINI_MODEL', 'gemini-3.0-flash')
        elif provider == 'doubao':
            self.base_url = os.environ.get('AI_BASE_URL')
            self.api_key = os.environ.get('AI_API_KEY')
            self.model = "doubao-seed-2.0-lite"
        elif provider == 'qwen':
            self.base_url = os.environ.get('AI_BASE_URL')
            self.api_key = os.environ.get('AI_API_KEY')
            self.model = "qwen3.5-397b-a17b"
        else:
            self.base_url = os.environ.get('AI_BASE_URL')
            self.api_key = os.environ.get('AI_API_KEY')
            self.model = os.environ.get('AI_MODEL')

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

        # 检查AT币余额
        if user_id:
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
                # 计算消耗的AT币（基于消息长度）
                total_content_length = sum(len(msg.get('content', '')) for msg in messages)
                at_cost = max(1, min(5, int(total_content_length / 100)))  # 每100字符消耗1-5AT币

                if user.at_balance < at_cost:
                    print(f"[AIClient] ❌ AT币不足: 余额{user.at_balance}, 需要{at_cost}")
                    raise ValueError(f"AT币余额不足: {user.at_balance} < {at_cost}")

                print(f"[AIClient] ✅ AT币检查通过: 余额{user.at_balance}, 消耗{at_cost}")
                # 在这里不立即扣除，因为我们还不知道请求是否会成功
                # 在成功获取响应后再扣除AT币
            except Exception as e:
                print(f"[AIClient] ⚠️ AT币检查失败: {e}")
                raise e
        
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature
        }
        
        # 为了尽量迫使一些模型输出 JSON，这里加上 response_format 约束
        if expect_json:
            payload['response_format'] = {'type': 'json_object'}

        response = requests.post(
            self.base_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        ai_content = data['choices'][0]['message']['content']

        # 无论如何，均把各类模型自动带上的 <think> 推理过程给剔除
        ai_content = re.sub(r'<think>[\s\S]*?</think>', '', ai_content).strip()

        # 扣除AT币
        at_cost = 0
        if user_id:
            total_content_length = sum(len(msg.get('content', '')) for msg in messages)
            at_cost = max(1, min(5, int(total_content_length / 100)))  # 每100字符消耗1-5AT币

            User = get_user_model()
            user = User.objects.get(id=user_id)
            user.at_balance -= at_cost
            user.save()
            print(f"[AIClient] ✅ AT币扣除成功: 余额{user.at_balance}")

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
