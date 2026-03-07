import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

@csrf_exempt
@require_POST
def speaking_chat(request):
    """
    口语聊天接口 — 接收多轮对话历史，返回 AI 纯文本回复
    Body: { "messages": [{"role": "...", "content": "..."}] }
    """
    try:
        body = json.loads(request.body)
        messages = body.get('messages', [])
        if not messages:
            return JsonResponse({'error': 'messages required'}, status=400)

        system_instruction = {
            "role": "system",
            "content": (
                "You are an IELTS speaking examiner. Evaluate the user's latest message and reply to it to continue the conversation.\n"
                "CRITICAL INSTRUCTION: You MUST return your response as a raw JSON object and nothing else. "
                "Do not use markdown blocks like ```json. Do not include any explanations. "
                "Your JSON MUST contain exactly these four keys with appropriate values:\n"
                "{\n"
                "  \"reply\": \"(string) Your conversational response to the user's latest statement\",\n"
                "  \"grammar_score\": (integer 0-100) Grammar accuracy of the user's latest message,\n"
                "  \"vocab_score\": (integer 0-100) Vocabulary richness of the user's latest message,\n"
                "  \"relevance_score\": (integer 0-100) How relevant the user's message is to the topic\n"
                "}\n"
                "Example of expected output:\n"
                "{\n"
                "  \"reply\": \"That sounds like a beautiful town. What do you like most about living there?\",\n"
                "  \"grammar_score\": 85,\n"
                "  \"vocab_score\": 75,\n"
                "  \"relevance_score\": 95\n"
                "}"
            )
        }
        messages.insert(0, system_instruction)

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        from .ai_client import AIClient
        client = AIClient(provider=provider)
        
        # 我们使用 expect_json=False 让 AIClient 返回清理过 <think> 的裸字符串
        # 因为 speaking_chat 这里有一套非常定制化的从 parsed() 中找不同 key 的 fallback 逻辑
        ai_text = client.generate(messages, expect_json=False, temperature=0.75)
        
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
                
            reply_text = re.sub(r'[*#`_]', '', str(reply_text)).strip()
            
            # Ensure they are integers, even if the model returns string "85"
            try:
                grammar_score = int(parsed.get('grammar_score', 0))
            except (ValueError, TypeError):
                grammar_score = 0
            try:
                vocab_score = int(parsed.get('vocab_score', 0))
            except (ValueError, TypeError):
                vocab_score = 0
            try:
                relevance_score = int(parsed.get('relevance_score', 0))
            except (ValueError, TypeError):
                relevance_score = 0
        except json.JSONDecodeError:
            print("[JSONDecodeError] Failed to parse AI JSON_STR", repr(json_str), flush=True)
            reply_text = re.sub(r'[*#`_]', '', ai_text).strip()
            grammar_score = 0
            vocab_score = 0
            relevance_score = 0

        print(f"[AI PARSED RESULT]: Reply='{reply_text[:20]}...', Grammar={grammar_score}, Vocab={vocab_score}, Relevance={relevance_score}", flush=True)

        return JsonResponse({
            'reply': reply_text,
            'grammar_score': grammar_score,
            'vocab_score': vocab_score,
            'relevance_score': relevance_score
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def speaking_transcribe(request):
    """
    语音转文字接口 — 接收前端 MediaRecorder 录制的音频，
    使用 SpeechRecognition 库转写成英文文本。
    兼容 webm/wav 格式录音。
    """
    try:
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({'error': 'No audio file provided'}, status=400)

        reference_text = request.POST.get('reference_text', '').strip()
        
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
