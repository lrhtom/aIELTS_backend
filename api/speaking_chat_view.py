

@csrf_exempt
@require_POST
def speaking_chat(request):
    """
    口语聊天接口 — 接收多轮对话历史，返回 AI 纯文本回复
    Body: { "messages": [{"role": "...", "content": "..."}] }
    """
    try:
        import requests as req_lib
        body = json.loads(request.body)
        messages = body.get('messages', [])
        if not messages:
            return JsonResponse({'error': 'messages required'}, status=400)

        base_url = os.environ.get('AI_BASE_URL')
        api_key = os.environ.get('AI_API_KEY')
        model = os.environ.get('AI_MODEL')

        response = req_lib.post(
            base_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            },
            json={
                'model': model,
                'messages': messages,
                'temperature': 0.75,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        ai_text = data['choices'][0]['message']['content']
        # Strip <think> tags (for reasoning models)
        ai_text = re.sub(r'<think>[\s\S]*?</think>', '', ai_text).strip()
        # Strip markdown symbols
        ai_text = re.sub(r'[*#`_]', '', ai_text).strip()
        return JsonResponse({'reply': ai_text})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
