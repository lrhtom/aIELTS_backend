import json
import random
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from api.ai_client import AIClient
from api.rate_limit import check_rate_limit

TASK2_TOPIC_AREAS = [
    "education and learning",
    "technology and the internet",
    "environment and climate change",
    "health and medicine",
    "crime and punishment",
    "work and employment",
    "government and politics",
    "media and advertising",
    "culture and tradition",
    "globalisation and international relations",
    "transport and urban planning",
    "family and social values",
    "sport and leisure",
    "arts and music",
    "science and space exploration",
    "animal rights and wildlife",
    "tourism and travel",
    "food and diet",
    "poverty and economic inequality",
    "language and communication",
]

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_task2(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'task2_generate', max_calls=10, window=60)
        if limit_resp: return limit_resp
        task_type = request.data.get('type', 'opinion')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        type_map = {
            'opinion': 'Opinion Essay (Agree/Disagree or To what extent do you agree/disagree)',
            'opinion_agree': 'Opinion Essay - Agree or Disagree (Ask the user to what extent they agree or disagree with a statement)',
            'opinion_discuss': 'Opinion Essay - Discuss both views and give your opinion',
            'opinion_advantages': 'Opinion Essay - Do the advantages outweigh the disadvantages?',
            'report': 'Report (Cause & Solution or Problem & Effect)',
            'mixed': 'Mixed Essay (Discuss both views and give your opinion, or multi-part questions)',
            'innovation': 'AI Innovation Prompt (A completely novel, cutting-edge, or futuristic social/tech issue that IELTS might test in the future)'
        }
        
        selected_desc = type_map.get(task_type, type_map['opinion'])
        topic_area = random.choice(TASK2_TOPIC_AREAS)

        system_prompt = f'''You are a senior IELTS examiner.
You need to generate a creative, authentic IELTS Task 2 writing prompt.
The requested type is: {selected_desc}.
The topic area must be: {topic_area}.

Return a JSON with EXACTLY this structure:
{{
  "prompt": "The full IELTS Task 2 question prompt. Make it look exactly like a real exam question (e.g., 'Some people think that... To what extent do you agree or disagree?')."
}}
'''
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate the Task 2 prompt."}
        ]
        
        response_data, at_cost = client.generate(messages, expect_json=True, user_id=user.id)
        prompt_text = response_data.get('prompt', '')
        
        return Response({
            'prompt': prompt_text,
            'atConsumed': at_cost
        })
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def evaluate_task2(request):
    try:
        user = request.user
        limit_resp = check_rate_limit(user.id, 'task2_evaluate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        prompt_text = request.data.get('prompt', '')
        user_answer = request.data.get('userAnswer', '')
        ui_lang = request.data.get('lang', 'en')
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        client = AIClient(provider=provider)

        lang_instruction = (
            'Write the "feedback" field in Simplified Chinese (中文).'
            if ui_lang == 'zh'
            else 'Write the "feedback" field in English.'
        )

        system_prompt = f'''You are an expert IELTS examiner evaluator.
Evaluate the user's Task 2 Writing based on the provided Prompt.
Return a JSON with EXACTLY this structure:
{{
  "scores": {{
    "ta": <0-9 float for Task Response>,
    "cc": <0-9 float for Coherence & Cohesion>,
    "lr": <0-9 float for Lexical Resource>,
    "gra": <0-9 float for Grammatical Range & Accuracy>
  }},
  "overall": <0-9 float for overall band score>,
  "feedback": "Detailed feedback..."
}}
LANGUAGE INSTRUCTION: {lang_instruction}'''
        user_msg = f"Prompt:\n{prompt_text}\n\nUser Answer:\n{user_answer}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ]
        
        response_data, at_cost = client.generate(messages, expect_json=True, user_id=user.id)
        response_data['atConsumed'] = at_cost
        return Response(response_data)
        
    except Exception as e:
        import traceback
        return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)
