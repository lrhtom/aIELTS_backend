import json
from api.skills.speaking.chat import skill_speaking_chat_system
from api.skills.speaking.scenario import (
    skill_speaking_check_scenario,
    skill_speaking_scenario_opening,
    skill_speaking_scenario_chat,
    skill_speaking_random_scenario,
)
import re
import base64
import hashlib
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.rate_limit import check_rate_limit


def _build_singleflight_scope(scope_prefix: str, payload) -> str:
    try:
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        payload_text = str(payload)
    digest = hashlib.sha256(payload_text.encode('utf-8')).hexdigest()[:16]
    return f"{scope_prefix}:{digest}"

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def speaking_chat(request):
    """
    口语聊天接口，接收多轮对话历史，返回 AI 纯文本回复。
    Body: { "messages": [{"role": "...", "content": "..."}] }
    """
    try:
        limit_resp = check_rate_limit(request.user.id, 'speaking_chat', max_calls=15, window=60)
        if limit_resp: return limit_resp
        messages = request.data.get('messages', [])
        if not messages:
            return JsonResponse({'error': 'messages required'}, status=400)
        sf_scope = _build_singleflight_scope('speaking_chat', {'messages': messages})

        system_instruction = {
            "role": "system",
            "content": skill_speaking_chat_system()
        }
        messages.insert(0, system_instruction)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from api.core.ai_client import AIClient
        client = AIClient(provider=provider)
        
        # 使用 expect_json=False，让 AIClient 返回清理过 <think> 的原始文本。
        # speaking_chat 在这里有一套定制化的 parsed() key-fallback 逻辑。
        ai_text, at_cost = client.generate(
            messages,
            expect_json=False,
            temperature=0.75,
            user_id=request.user.id,
            singleflight_scope=sf_scope,
        )
        
        print(f"[AI RAW TEXT]: {repr(ai_text)}", flush=True)

        # Extract JSON using regex from first { to last }
        json_match = re.search(r'\{(.*?)\}', ai_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = ai_text

        try:
            parsed = json.loads(json_str)
            reply_text = parsed.get('reply') or parsed.get('response') or parsed.get('text') or parsed.get('message') or parsed.get('content')
            if not reply_text:
                reply_text = str(parsed)
                
            reply_text = str(reply_text).strip()
            
            # Ensure they are floats clamped to [0, 9], rounded to 0.5
            def clamp_score(val):
                try:
                    s = float(val)
                except (ValueError, TypeError):
                    return 0.0
                s = max(0.0, min(9.0, s))
                return round(s * 2) / 2  # round to nearest 0.5

            grammar_score = clamp_score(parsed.get('grammar_score', 0))
            vocab_score = clamp_score(parsed.get('vocab_score', 0))
            relevance_score = clamp_score(parsed.get('relevance_score', 0))
            corrected_text = str(parsed.get('corrected_text', '')).strip()
        except json.JSONDecodeError:
            print("[JSONDecodeError] Failed to parse AI JSON_STR", repr(json_str), flush=True)
            reply_text = ai_text.strip()
            grammar_score = 0.0
            vocab_score = 0.0
            relevance_score = 0.0
            corrected_text = ''

        print(f"[AI PARSED RESULT]: Reply='{reply_text[:20]}...', Grammar={grammar_score}, Vocab={vocab_score}, Relevance={relevance_score}", flush=True)

        return JsonResponse({
            'reply': reply_text,
            'grammar_score': grammar_score,
            'vocab_score': vocab_score,
            'relevance_score': relevance_score,
            'corrected_text': corrected_text,
            'atConsumed': at_cost
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def speaking_transcribe(request):
    """
    语音转文字接口：接收前端 MediaRecorder 录制的音频，
    使用 SpeechRecognition 库转写成英文文本。
    兼容 webm/wav 格式录音。
    """
    try:
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({'error': 'No audio file provided'}, status=400)

        reference_text = request.data.get('reference_text', '').strip()
        
        import io
        import tempfile
        import os
        import json
        import azure.cognitiveservices.speech as speechsdk

        raw_bytes = audio_file.read()
        print(f"\n[AZURE PRONUNCIATION DEBUG] 🎤 =========== START ASSESSMENT ===========", flush=True)
        print(f"[AZURE PRONUNCIATION DEBUG] 📦 Received audio file: {audio_file.name}", flush=True)
        print(f"[AZURE PRONUNCIATION DEBUG] 📏 Size: {len(raw_bytes)} bytes", flush=True)
        print(f"[AZURE PRONUNCIATION DEBUG] 📝 Reference text from frontend: '{reference_text}'", flush=True)

        # We temporarily save it to disk because Azure AudioConfig prefers file paths
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        try:
            # Azure Setup - Hardcoded keys explicitly provided by the user request
            speech_key = os.getenv("AZURE_SPEECH_KEY", "")
            service_region = os.getenv("AZURE_SPEECH_REGION", "switzerlandnorth")
            speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
            audio_config = speechsdk.audio.AudioConfig(filename=tmp_path)

            # Create pronunciation assessment config
            # If we have text from the frontend, it's a scripted assessment.
            # If empty, Azure can still do unscripted assessment (though passing empty string is sometimes restricted, so we use a dummy if empty or just evaluate the closest recognized text).
            eval_text = reference_text if reference_text else ""
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=eval_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=True
            )

            # Apply pronunciation config to speech recognizer
            speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
            pronunciation_config.apply_to(speech_recognizer)

            print(f"[AZURE PRONUNCIATION DEBUG] 📡 Sending to Azure server...", flush=True)
            # Evaluate using synchronous blocking call for now since it's an uploaded file
            speech_recognition_result = speech_recognizer.recognize_once()

            if speech_recognition_result.reason == speechsdk.ResultReason.RecognizedSpeech:
                pronunciation_result = speechsdk.PronunciationAssessmentResult(speech_recognition_result)
                
                # Fetch detailed JSON properties generated by Azure (contains syllable and words details)
                result_json = speech_recognition_result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)

                print(f"[AZURE PRONUNCIATION DEBUG] ✅ Recognized Speech: '{speech_recognition_result.text}'", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] 🎯 Accuracy Score: {pronunciation_result.accuracy_score}", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] 👄 Pronunciation Score: {pronunciation_result.pronunciation_score}", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] 🧩 Completeness Score: {pronunciation_result.completeness_score}", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] 🌊 Fluency Score: {pronunciation_result.fluency_score}", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] =================================================\n", flush=True)

                data = {
                    'text': speech_recognition_result.text,
                    'scores': {
                        'accuracy': pronunciation_result.accuracy_score,
                        'pronunciation': pronunciation_result.pronunciation_score,
                        'completeness': pronunciation_result.completeness_score,
                        'fluency': pronunciation_result.fluency_score,
                    },
                    'azure_json': json.loads(result_json) if result_json else None
                }
                return JsonResponse(data)
                
            elif speech_recognition_result.reason == speechsdk.ResultReason.NoMatch:
                print(f"[AZURE PRONUNCIATION DEBUG] ⚠️ No speech could be recognized.", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] =================================================\n", flush=True)
                return JsonResponse({'text': '', 'error': 'No speech recognized'})
                
            elif speech_recognition_result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = speech_recognition_result.cancellation_details
                err_msg = f"Speech Recognition canceled: {cancellation_details.reason}"
                print(f"[AZURE PRONUNCIATION DEBUG] ❌ {err_msg}", flush=True)
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    print(f"[AZURE PRONUNCIATION DEBUG] ❌ Error details: {cancellation_details.error_details}", flush=True)
                print(f"[AZURE PRONUNCIATION DEBUG] =================================================\n", flush=True)
                return JsonResponse({'error': err_msg}, status=500)

        except Exception as e:
            print(f"[AZURE PRONUNCIATION DEBUG] ❌ Azure Assessment Failed: {str(e)}", flush=True)
            return JsonResponse({'error': f'Azure API failed: {str(e)}'}, status=500)
            
        finally:
            # Explicitly force garbage collection of Azure objects to release the file handle in Windows
            if 'speech_recognizer' in locals():
                del speech_recognizer
            if 'audio_config' in locals():
                del audio_config
                
            import time
            # Retry mechanism for Windows file handle release delays
            for _ in range(3):
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    break
                except PermissionError:
                    time.sleep(0.5)
                except Exception:
                    break

    except Exception as e:
        print(f"[AZURE PRONUNCIATION DEBUG] ❌ Global unexpected error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_scenario(request):
    try:
        limit_resp = check_rate_limit(request.user.id, 'check_scenario', max_calls=20, window=60)
        if limit_resp: return limit_resp
        
        scenario = request.data.get('scenario', '').strip()
        if not scenario:
            return JsonResponse({'valid': False, 'reason': 'Scenario description is empty'})
        sf_scope = _build_singleflight_scope('check_scenario', {'scenario': scenario})
            
        system_instruction = {
            "role": "system",
            "content": skill_speaking_check_scenario()
        }
        
        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from api.core.ai_client import AIClient
        client = AIClient(provider=provider)
        
        ai_text, at_cost = client.generate(
            [system_instruction, {"role": "user", "content": scenario}],
            expect_json=False,
            temperature=0.1,
            user_id=request.user.id,
            singleflight_scope=sf_scope,
        )
        
        json_match = re.search(r'\{(.*?)\}', ai_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                return JsonResponse({
                    'valid': bool(parsed.get('valid', True)),
                    'reason': parsed.get('reason', ''),
                    'atConsumed': at_cost
                })
            except json.JSONDecodeError:
                pass
                
        # Fallback if AI fails to return strict JSON
        is_invalid = any(w in ai_text.lower() for w in ['false', 'nsfw', 'illegal', 'inappropriate'])
        return JsonResponse({'valid': not is_invalid, 'reason': '审核接口数据异常' if is_invalid else '', 'atConsumed': at_cost})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def scenario_opening(request):
    """Generate an AI-crafted opening line for a scenario role-play, with optional file context."""
    try:
        limit_resp = check_rate_limit(request.user.id, 'scenario_opening', max_calls=10, window=60)
        if limit_resp: return limit_resp

        scenario = request.data.get('scenario', '').strip()
        if not scenario:
            return JsonResponse({'error': 'scenario required'}, status=400)

        uploaded_files = request.FILES.getlist('files') if request.FILES else []

        system_msg = {
            "role": "system",
            "content": skill_speaking_scenario_opening(scenario)
        }

        user_content = "Please start the conversation."
        content_parts = [{"type": "text", "text": user_content}]

        for f in uploaded_files:
            if f.size > 5 * 1024 * 1024:
                continue
            ct = f.content_type or ''
            if ct.startswith('image/'):
                img_data = base64.b64encode(f.read()).decode('utf-8')
                content_parts.append({
                    'type': 'image_url',
                    'image_url': {'url': f'data:{ct};base64,{img_data}', 'detail': 'auto'}
                })
            else:
                try:
                    text_content = f.read().decode('utf-8', errors='replace')[:2000]
                    ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
                    content_parts[0]['text'] = (
                        f'[Reference file: {f.name}]\n```{ext}\n{text_content}\n```\n\n'
                        + content_parts[0]['text']
                    )
                except Exception:
                    pass

        user_msg = {"role": "user", "content": content_parts if len(content_parts) > 1 else content_parts[0]['text']}
        messages = [system_msg, user_msg]

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from api.core.ai_client import AIClient
        client = AIClient(provider=provider)

        ai_text, at_cost = client.generate(
            messages,
            expect_json=False,
            temperature=0.85,
            user_id=request.user.id,
        )

        opening = ai_text.strip().strip('"').strip("'").strip()

        return JsonResponse({
            'opening': opening,
            'atConsumed': at_cost,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def scenario_chat(request):
    try:
        limit_resp = check_rate_limit(request.user.id, 'scenario_chat', max_calls=15, window=60)
        if limit_resp: return limit_resp

        # ── Parse request: supports JSON and multipart/form-data ──
        is_multipart = request.content_type and 'multipart' in request.content_type
        if is_multipart:
            scenario = request.data.get('scenario', '').strip()
            messages_raw = request.data.get('messages', '[]')
            messages = json.loads(messages_raw) if isinstance(messages_raw, str) else messages_raw
            uploaded_files = request.FILES.getlist('files') if request.FILES else []
        else:
            messages = request.data.get('messages', [])
            scenario = request.data.get('scenario', '').strip()
            uploaded_files = []

        if not messages or not scenario:
            return JsonResponse({'error': 'messages and scenario required'}, status=400)

        # ── Augment the last user message with uploaded file content ──
        if uploaded_files:
            last_user_msg = None
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    last_user_msg = msg
                    break

            if last_user_msg:
                content_parts = []
                user_text = last_user_msg.get('content', '')
                text_attachments = []

                for f in uploaded_files:
                    if f.size > 5 * 1024 * 1024:
                        continue  # skip files > 5MB
                    ct = f.content_type or 'application/octet-stream'
                    if ct.startswith('image/'):
                        img_data = base64.b64encode(f.read()).decode('utf-8')
                        content_parts.append({
                            'type': 'image_url',
                            'image_url': {'url': f'data:{ct};base64,{img_data}', 'detail': 'auto'}
                        })
                    else:
                        try:
                            text_content = f.read().decode('utf-8', errors='replace')[:3000]
                            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
                            text_attachments.append(f'[Attached file: {f.name}]\n```{ext}\n{text_content}\n```')
                        except Exception:
                            text_attachments.append(f'[Attached file: {f.name}]')

                if text_attachments:
                    user_text = '\n\n'.join(text_attachments) + '\n\n' + user_text

                if content_parts:
                    content_parts.insert(0, {'type': 'text', 'text': user_text})
                    last_user_msg['content'] = content_parts
                else:
                    last_user_msg['content'] = user_text

        sf_scope = _build_singleflight_scope('scenario_chat', {'scenario': scenario, 'messages': messages})

        system_instruction = {
            "role": "system",
            "content": skill_speaking_scenario_chat(scenario)
        }
        messages.insert(0, system_instruction)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from api.core.ai_client import AIClient
        client = AIClient(provider=provider)

        ai_text, at_cost = client.generate(
            messages,
            expect_json=False,
            temperature=0.75,
            user_id=request.user.id,
            singleflight_scope=sf_scope,
        )

        json_match = re.search(r'\{(.*?)\}', ai_text, re.DOTALL)
        json_str = json_match.group(0) if json_match else ai_text

        try:
            parsed = json.loads(json_str)
            reply_text = parsed.get('reply') or str(parsed)
            reply_text = str(reply_text).strip()

            def clamp_score(val):
                try:
                    s = float(val)
                except (ValueError, TypeError):
                    return 0.0
                s = max(0.0, min(9.0, s))
                return round(s * 2) / 2

            grammar_score = clamp_score(parsed.get('grammar_score', 0))
            vocab_score = clamp_score(parsed.get('vocab_score', 0))
            relevance_score = clamp_score(parsed.get('relevance_score', 0))
            is_continue = int(parsed.get('is_continue', 1))
            corrected_text = str(parsed.get('corrected_text', '')).strip()
        except (json.JSONDecodeError, ValueError, TypeError):
            reply_text = ai_text.strip()
            grammar_score, vocab_score, relevance_score, is_continue = 0.0, 0.0, 0.0, 1
            corrected_text = ''

        return JsonResponse({
            'reply': reply_text,
            'grammar_score': grammar_score,
            'vocab_score': vocab_score,
            'relevance_score': relevance_score,
            'is_continue': is_continue,
            'corrected_text': corrected_text,
            'atConsumed': at_cost
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_random_scenario(request):
    """
    随机生成雅思口语练习场景，并防止重复。
    """
    try:
        limit_resp = check_rate_limit(request.user.id, 'generate_scenario', max_calls=20, window=60)
        if limit_resp: return limit_resp

        from api.models import SpeakingScenarioHistory
        
        # 获取最近 100 条历史场景，避免传给 AI 的上下文太长
        recent_history_qs = SpeakingScenarioHistory.objects.order_by('-created_at')[:100]
        recent_topics = [h.topic for h in recent_history_qs]
        
        history_text = "None."
        if recent_topics:
            history_text = "\n".join(f"- {topic}" for topic in recent_topics)

        system_instruction = {
            "role": "system",
            "content": skill_speaking_random_scenario(history_text)
        }

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from api.core.ai_client import AIClient
        client = AIClient(provider=provider)
        
        ai_text, at_cost = client.generate(
            [system_instruction],
            expect_json=True,
            temperature=0.8,
            user_id=request.user.id,
        )

        scenario_text = ""
        short_scenario_text = ""
        
        # expect_json=True 会自动解析 JSON，成功时返回 dict
        if isinstance(ai_text, dict):
            scenario_text = ai_text.get('scenario', '').strip()
            short_scenario_text = ai_text.get('short_scenario', '').strip()
        else:
            json_match = re.search(r'\{(.*?)\}', str(ai_text), re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                    scenario_text = parsed.get('scenario', '').strip()
                    short_scenario_text = parsed.get('short_scenario', '').strip()
                except json.JSONDecodeError:
                    pass

            # Fallback if json parse fails
            if not scenario_text:
                scenario_text_str = str(ai_text).strip()
                # Clean up if it returned markdown
                scenario_text_str = re.sub(r'^```json\n|```$', '', scenario_text_str).strip()
                # If it's still JSON string, parse it
                if scenario_text_str.startswith('{') and scenario_text_str.endswith('}'):
                    try:
                        parsed = json.loads(scenario_text_str)
                        scenario_text = parsed.get('scenario', '').strip()
                        short_scenario_text = parsed.get('short_scenario', '').strip()
                    except:
                        pass

        if scenario_text:
            if not short_scenario_text:
                short_scenario_text = scenario_text[:20]

            # 存入数据库短版本
            SpeakingScenarioHistory.objects.create(topic=short_scenario_text)
            
            # 检查总数是否超过 100 条
            total_count = SpeakingScenarioHistory.objects.count()
            if total_count > 100:
                # 获取最新的 100 条的 ID 集合之外的旧记录 ID 并删除
                excess_count = total_count - 100
                oldest_ids = SpeakingScenarioHistory.objects.order_by('created_at').values_list('id', flat=True)[:excess_count]
                SpeakingScenarioHistory.objects.filter(id__in=list(oldest_ids)).delete()

        return JsonResponse({
            'scenario': scenario_text,
            'atConsumed': at_cost
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)



