import os
import json
import re
import hashlib
import time
import uuid
import requests
from django.contrib.auth import get_user_model

class AIClient:
    """
    通用 AI 模型客户端封装。
    支持对 DeepSeek, Gemini, Doubao, Qwen 等不同 Base URL 和密钥的管理。
    """
    def __init__(self, provider: str = 'deepseek'):
        self.provider = (provider or '').strip().lower()
        self.is_gpt5 = self.provider.startswith('gpt5')

        if self.provider == 'gemini':
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            self.api_key = os.environ.get('GEMINI_API_KEY', '')
            self.model = os.environ.get('GEMINI_MODEL', 'gemini-3.0-flash')
        elif self.is_gpt5:
            base_url = ""
            api_key = ""
            model = ""

            if self.provider == 'gpt5_4':
                base_url = os.environ.get('GPT54_BASE_URL', '')
                api_key = os.environ.get('GPT54_API_KEY', '')
                model = os.environ.get('GPT54_MODEL', 'gpt-5.4')
            elif self.provider == 'gpt5_mini':
                base_url = os.environ.get('GPT5MINI_BASE_URL', '')
                api_key = os.environ.get('GPT5MINI_API_KEY', '')
                model = os.environ.get('GPT5MINI_MODEL', 'gpt-5.4-mini')

            normalized_base_url = (base_url or '').strip()
            if normalized_base_url.rstrip('/').lower().endswith('/openai/v1'):
                # Allow v1 base endpoint; default to Responses API path.
                base_url = normalized_base_url.rstrip('/') + '/responses'
            self.base_url = base_url
            self.api_key = api_key
            self.model = model
        else:
            self.base_url = os.environ.get('AI_BASE_URL', '')
            self.api_key = os.environ.get('AI_API_KEY', '')
            self.model = os.environ.get('AI_MODEL', '')

    def generate(
        self,
        messages: list,
        expect_json: bool = False,
        temperature: float = 0.7,
        user_id: int = None,
        cache: bool = False,
        singleflight_scope: str | None = None,
    ) -> str | dict:
        """
        向 AI发起请求的通用函数。
        :param messages: OpenAI 格式的 messages 数组 [{'role': 'user', 'content': '...'}, ...]
        :param expect_json: 若为 True，则尝试使用正则提取大括号内容，并自动 json.loads() 转换为字典
        :param temperature: 温度参数
        :param cache: 若为 True 且 expect_json=True，则启用 Redis 缓存（命中时 AT 消耗为 0）
        :return: 字符串，或解析好的 dict (若 expect_json=True)
        """
        # 0. Redis 缓存检查（仅限 JSON 模式）
        cache_key = None
        if cache and expect_json:
            try:
                from api.core.redis_client import get_redis
                raw = json.dumps(messages, sort_keys=True, ensure_ascii=False)
                cache_key = f"ai_cache:{self.model}:{hashlib.md5(raw.encode()).hexdigest()}"
                cached = get_redis().get(cache_key)
                if cached:
                    print(f"[AIClient] ⚡ 缓存命中: {cache_key}")
                    return json.loads(cached), 0
            except Exception as ce:
                print(f"[AIClient] ⚠️ 缓存读取失败（跳过）: {ce}")

        # 0.5 单飞任务锁：同一用户同一 scope 在完成前只跑一次。
        sf_enabled = bool(singleflight_scope and user_id)
        sf_redis = None
        sf_is_leader = True
        sf_lock_key = None
        sf_lock_token = None
        sf_result_key = None
        sf_error_key = None

        if sf_enabled:
            try:
                from api.core.redis_client import get_redis

                sf_redis = get_redis()
                safe_scope = re.sub(r'[^a-zA-Z0-9:_-]', '_', str(singleflight_scope))
                sf_lock_key = f"ai_sf:lock:{safe_scope}:{user_id}"
                sf_result_key = f"ai_sf:result:{safe_scope}:{user_id}"
                sf_error_key = f"ai_sf:error:{safe_scope}:{user_id}"
                sf_lock_token = str(uuid.uuid4())

                acquired = sf_redis.set(sf_lock_key, sf_lock_token, ex=240, nx=True)
                sf_is_leader = bool(acquired)

                if not sf_is_leader:
                    print(f"[AIClient] ⏳ singleflight 等待已有任务: scope={safe_scope}, user={user_id}")
                    for _ in range(240):
                        cached_result = sf_redis.get(sf_result_key)
                        if cached_result:
                            payload = json.loads(cached_result) if isinstance(cached_result, str) else cached_result
                            content = payload.get('content') if isinstance(payload, dict) else None
                            payload_expect_json = bool(payload.get('expect_json')) if isinstance(payload, dict) else False
                            if payload_expect_json == expect_json:
                                print(f"[AIClient] ✅ singleflight 复用完成结果: scope={safe_scope}, user={user_id}")
                                return content, 0

                        err_msg = sf_redis.get(sf_error_key)
                        if err_msg:
                            raise ValueError(str(err_msg))

                        time.sleep(1)

                    raise ValueError("AI generation is still in progress. Please retry shortly.")

                # Leader 清理上一轮残留结果。
                sf_redis.delete(sf_result_key)
                sf_redis.delete(sf_error_key)

            except Exception as sf_err:
                # 单飞失败时降级为原逻辑，避免阻塞主流程。
                print(f"[AIClient] ⚠️ singleflight 初始化失败（降级执行）: {sf_err}")
                sf_enabled = False
                sf_redis = None
                sf_is_leader = True
                sf_lock_key = None
                sf_lock_token = None
                sf_result_key = None
                sf_error_key = None

        def _sf_write_result(content_value, expect_json_value: bool):
            if not (sf_enabled and sf_redis and sf_is_leader and sf_result_key):
                return
            try:
                sf_redis.set(
                    sf_result_key,
                    json.dumps({
                        'expect_json': expect_json_value,
                        'content': content_value,
                    }, ensure_ascii=False),
                    ex=120,
                )
                sf_redis.delete(sf_error_key)
            except Exception as sf_store_err:
                print(f"[AIClient] ⚠️ singleflight 结果写入失败: {sf_store_err}")

        def _sf_write_error(message: str):
            if not (sf_enabled and sf_redis and sf_is_leader and sf_error_key):
                return
            try:
                sf_redis.set(sf_error_key, str(message), ex=30)
            except Exception as sf_store_err:
                print(f"[AIClient] ⚠️ singleflight 错误写入失败: {sf_store_err}")

        try:
            print(f"[AIClient] 🚀 准备发送请求")
            print(f"[AIClient]   提供商: {self.provider}")
            print(f"[AIClient]   模  型: {self.model}")
            print(f"[AIClient]   地  址: {self.base_url}")
            print(f"[AIClient]   用户ID: {user_id}")

            # 1. 预检：检查余额是否已为负（5秒短路缓存减少 DB 压力）
            if user_id:
                User = get_user_model()
                try:
                    balance = None
                    try:
                        from api.core.redis_client import get_redis
                        _balance_key = f"balance:{user_id}"
                        _cached = get_redis().get(_balance_key)
                        if _cached is not None:
                            balance = float(_cached)
                    except Exception:
                        pass
                    if balance is None:
                        _user_obj = User.objects.get(id=user_id)
                        balance = _user_obj.at_balance
                        try:
                            from api.core.redis_client import get_redis
                            get_redis().setex(f"balance:{user_id}", 5, str(balance))
                        except Exception:
                            pass
                    if balance < 0:
                        print(f"[AIClient] 🚨 拦截负余额用户 id={user_id}, 余额: {balance}")
                        raise ValueError(f"您的AT币余额不足({balance})，请充值后重试。")
                except ValueError:
                    raise
                except Exception as e:
                    print(f"[AIClient] ⚠️ 预检失败: {e}")
                    raise e

            # 构建请求头
            headers = {'Content-Type': 'application/json'}
            if self.is_gpt5:
                headers['api-key'] = self.api_key
            else:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # Azure Responses API 和标准 Chat Completions 的格式区分
            is_responses_api = '/responses' in self.base_url.lower()
            if self.is_gpt5 and is_responses_api:
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
                _sf_write_error(str(e))
                raise e

            data = response.json()

            # 解析响应内容：Responses API 和 Chat Completions API 路径不同
            if self.is_gpt5 and is_responses_api:
                # Responses API: 遍历 output 找 type=='message'（第一项可能是 reasoning summary）
                print(f"[AIClient][{self.provider}] 原始响应 keys: {list(data.keys())}")
                try:
                    msg_block = next(
                        item for item in data['output'] if item.get('type') == 'message'
                    )
                    ai_content = msg_block['content'][0]['text']
                except (StopIteration, KeyError, IndexError, TypeError) as parse_err:
                    print(f"[AIClient] ❌ GPT-5 响应解析失败，output: {str(data.get('output', ''))[:800]}")
                    _sf_write_error(f"GPT-5 响应格式异常，无法提取内容: {parse_err}")
                    raise ValueError(f"GPT-5 响应格式异常，无法提取内容: {parse_err}") from parse_err
            else:
                ai_content = data['choices'][0]['message']['content']

            # 获取真实 Token 消耗（兼容 Chat Completions 和 Responses API 两种格式）
            usage = data.get('usage', {})
            if self.is_gpt5 and is_responses_api:
                # Responses API: input_tokens + output_tokens
                total_tokens = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
            else:
                # Chat Completions API: total_tokens
                total_tokens = usage.get('total_tokens', 0)
            # 费率：1 Token = 2 AT 币
            at_cost = total_tokens * 2

            # 剔除推理过程
            ai_content = re.sub(r'<think>[\s\S]*?</think>', '', ai_content).strip()

            # 2. 扣费（非 JSON 模式：立即扣费；JSON 模式：解析成功后再扣，失败不扣）
            def _deduct():
                if user_id:
                    User = get_user_model()
                    u = User.objects.get(id=user_id)
                    u.at_balance -= at_cost
                    u.save()
                    # 余额变化后失效余额缓存
                    try:
                        from api.core.redis_client import get_redis
                        get_redis().delete(f"balance:{user_id}")
                    except Exception:
                        pass
                    print(f"[AIClient] ✅ Token 计费成功: 消耗{total_tokens}T -> {at_cost}AT, 最终余额{u.at_balance}")

            if not expect_json:
                _deduct()
                _sf_write_result(ai_content, expect_json_value=False)
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
                _deduct()
                print(f"[AIClient] ✅ JSON 解析成功")
                if cache_key:
                    try:
                        from api.core.redis_client import get_redis
                        get_redis().setex(cache_key, 86400, json.dumps(parsed, ensure_ascii=False))
                        print(f"[AIClient] 💾 已写入缓存: {cache_key}")
                    except Exception as se:
                        print(f"[AIClient] ⚠️ 缓存写入失败（跳过）: {se}")
                _sf_write_result(parsed, expect_json_value=True)
                return parsed, at_cost
            except json.JSONDecodeError as e:
                print(f"[AIClient] ❌ JSON 解析崩溃: {e}")
                # 尝试修复常见 AI 格式错误：未关闭的数组（用 } 代替了 ]）
                repaired = _repair_json(json_str)
                if repaired != json_str:
                    try:
                        parsed = json.loads(repaired)
                        _deduct()
                        print(f"[AIClient] ✅ JSON 修复后解析成功")
                        if cache_key:
                            try:
                                from api.core.redis_client import get_redis
                                get_redis().setex(cache_key, 86400, json.dumps(parsed, ensure_ascii=False))
                            except Exception:
                                pass
                        _sf_write_result(parsed, expect_json_value=True)
                        return parsed, at_cost
                    except json.JSONDecodeError:
                        pass
                print(f"[AIClient] ⚠️ 失效的原始字符串: {repr(ai_content[:200])}")
                _sf_write_error("AI Client Failed to parse response as JSON.")
                # JSON 解析彻底失败 → 不扣费，抛出异常让上层处理
                raise ValueError("AI Client Failed to parse response as JSON. Raw: " + ai_content)
        except Exception as e:
            _sf_write_error(str(e))
            raise
        finally:
            if sf_enabled and sf_redis and sf_is_leader and sf_lock_key and sf_lock_token:
                try:
                    current_lock = sf_redis.get(sf_lock_key)
                    if current_lock == sf_lock_token:
                        sf_redis.delete(sf_lock_key)
                except Exception as sf_release_err:
                    print(f"[AIClient] ⚠️ singleflight 解锁失败: {sf_release_err}")



    def generate_stream(
        self,
        messages: list,
        temperature: float = 0.7,
        user_id: int = None,
    ):
        """
        以流式 Generator 方式请求大模型并逐字返回。
        适用于 SSE 不间断输出，请求完成后基于结果粗略计费。
        """
        # 计费预检
        if user_id:
            User = get_user_model()
            try:
                user_obj = User.objects.get(id=user_id)
                if user_obj.at_balance < 0:
                    yield f"🚨 拦截：您的AT币余额不足({user_obj.at_balance})，请充值后重试。"
                    return
            except Exception as e:
                yield f"🚨 账号预检异常: {e}"
                return

        headers = {'Content-Type': 'application/json'}
        if self.is_gpt5:
            headers['api-key'] = self.api_key
        else:
            headers['Authorization'] = f'Bearer {self.api_key}'

        is_responses_api = '/responses' in self.base_url.lower()
        if self.is_gpt5 and is_responses_api:
            # Azure / Custom GPT-5 Responses API 结构
            input_msgs = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
            payload = {
                'model': self.model,
                'input': input_msgs,
                'stream': True,
            }
        else:
            payload = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature,
                'stream': True,
            }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, stream=True, timeout=120)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            yield f"❌ HTTP Error: {e.response.status_code}\n{e.response.text}"
            return
        except Exception as e:
            yield f"❌ API 请求失败 ({str(e)})"
            return

        full_content = []
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8').strip()
                if not decoded_line:
                    continue
                if decoded_line.startswith('data: '):
                    data_str = decoded_line[6:].strip()
                else:
                    data_str = decoded_line

                if data_str == '[DONE]':
                    break

                try:
                    chunk = json.loads(data_str)
                    content_piece = ''
                    if self.is_gpt5 and is_responses_api:
                        if 'output' in chunk and len(chunk['output']) > 0:
                            content_piece = chunk['output'][0].get('text', '')
                    else:
                        choices = chunk.get('choices', [])
                        if len(choices) > 0:
                            content_piece = choices[0].get('delta', {}).get('content', '')

                    if content_piece:
                        # 剔除可能在流式中产生的 `<think>` 标签，为了简单处理，这里我们可以直接 emit，
                        # 但前端如果直接打印会有 think 标签。此处暂不处理完全清除 think，仅做透传
                        full_content.append(content_piece)
                        yield content_piece
                except json.JSONDecodeError:
                    pass

        # === 计费 ===
        if user_id:
            final_text = "".join(full_content)
            final_text_no_think = re.sub(r'<think>.*?</think>', '', final_text, flags=re.DOTALL)
            input_chars = sum(len(str(m.get('content', ''))) for m in messages)
            # 大约每 1 个汉字 = 1 Token（粗算）
            estimated_tokens = int((len(final_text_no_think) + input_chars) * 0.75)
            # 1 Token = 2 AT 会导致消耗略偏高，使用 1.5 比例进行流式费率换算
            at_cost = int(estimated_tokens * 1.5)
            
            if at_cost > 0:
                try:
                    User = get_user_model()
                    u = User.objects.get(id=user_id)
                    u.at_balance -= at_cost
                    u.save()
                    try:
                        from api.core.redis_client import get_redis
                        get_redis().delete(f"balance:{user_id}")
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[AIClient Stream] 💸 流式扣费失败: {e}")


def _repair_json(json_str: str) -> str:
    """
    修复 AI 返回的常见 JSON 格式错误。
    典型情形：数组末尾写了 } 而不是 ]，导致 [ 未关闭。
    修复方式：在最后一个 } 之前插入缺失的 ]。
    """
    open_brackets = 0
    in_string = False
    i = 0
    while i < len(json_str):
        ch = json_str[i]
        if in_string:
            if ch == '\\':
                i += 2  # skip escaped character
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '[':
                open_brackets += 1
            elif ch == ']':
                open_brackets -= 1

        i += 1

    if open_brackets <= 0:
        return json_str  # nothing to fix

    # Insert missing ] before the last }
    rstripped = json_str.rstrip()
    if rstripped.endswith('}'):
        return rstripped[:-1] + (']' * open_brackets) + '}'
    return json_str + ']' * open_brackets


def refund_at(user_id: int, at_cost: int) -> None:
    """将 at_cost 退还给 user_id 对应的用户。AI 操作失败后调用。"""
    if not user_id or at_cost <= 0:
        return
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)
        user.at_balance += at_cost
        user.save()
        print(f"[AIClient] ↩️ 退款成功: +{at_cost}AT → 用户 {user_id}，余额 {user.at_balance}")
    except Exception as e:
        print(f"[AIClient] ⚠️ 退款失败: {e}")


