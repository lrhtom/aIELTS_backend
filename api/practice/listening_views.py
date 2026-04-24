import json
import os
import re
import random
import html
import subprocess
import tempfile
from django.http import JsonResponse, HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from api.core.utils import call_ai_api
from api.core.rate_limit import check_rate_limit

ARTICLE_LISTENING_PROMPT_TEMPLATE = """
You are an IELTS examiner. Create an IELTS listening passage (Band {difficulty} difficulty) {vocab_instruction}

Tone requirement:
{tone_instruction}

RULES:
1. CRITICAL WORD LIMIT: Each blank answer MUST be {word_count_desc}. Answers exceeding this word limit are WRONG.
2. "passage": the COMPLETE audio transcript. {marker_rule}
3. "blanked_passage": the EXACT SAME text as "passage", but replace exactly 10 key words/phrases with "_____". These 10 blanks are the questions. Each blank replaces {word_count_desc}.
4. "questions": an array of EXACTLY 10 objects (id 1-10). Each has "question" (include _____ in it), "answers" (at least 2 acceptable variations, each MUST be {word_count_desc}), and "explanation" in Chinese.
5. The passage should be a lecture, conversation, or monologue typical of IELTS listening.
{answer_priority_rule}

Output ONLY valid JSON, no markdown, no comments:
{{
    "type": "article",
    "title": "The Title",
    "passage": "Full text with **target** words marked...",
    "blanked_passage": "Same text with _____ replacing 10 words/phrases...",
    "questions": [
        {{"id": 1, "question": "Blank 1: The speaker mentions that _____ is important.", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 2, "question": "Blank 2: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 3, "question": "Blank 3: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 4, "question": "Blank 4: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 5, "question": "Blank 5: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 6, "question": "Blank 6: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 7, "question": "Blank 7: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 8, "question": "Blank 8: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 9, "question": "Blank 9: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 10, "question": "Blank 10: ...", "answers": ["{example_answer}"], "explanation": "解析?.."}}
    ]
}}
"""

ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE = """
You are an IELTS examiner.
Create an IELTS listening practice passage (Band {difficulty} difficulty) {vocab_instruction}

Tone requirement:
{tone_instruction}

{mc_marker_rule}

Then, create exactly 5 multiple-choice questions based on the passage.
For each question, provide 4 options as a JSON array. 
CRITICAL RULE: The VERY FIRST option in the "options" array (index 0) MUST ALWAYS BE THE CORRECT ANSWER. The remaining 3 options must be the incorrect distractors. 
Our system will shuffle them automatically later. Do not assign A, B, C, D letters yourself.

You MUST output your response strictly in the following JSON format without any markdown wrappers or extra text:
{{
    "type": "multiple_choice",
    "title": "Passage Title",
    "passage": "Full listening passage text here...",
    "questions": [
        {{
            "id": 1,
            "question": "Question text here",
            "options": [
                "The EXACT text of the CORRECT option goes here FIRST",
                "Wrong option distractor 1",
                "Wrong option distractor 2",
                "Wrong option distractor 3"
            ],
            "explanation": "Detailed explanation using 中文. Explain why the correct option is right."
        }}
    ]
}}
"""

SENTENCE_LISTENING_PROMPT_TEMPLATE = """
You are an IELTS examiner. Create an IELTS listening passage (Band {difficulty} difficulty) {vocab_instruction}

Tone requirement:
{tone_instruction}

RULES:
1. CRITICAL WORD LIMIT: Each blank answer MUST be {word_count_desc}. Answers exceeding this word limit are WRONG.
2. "passage": the COMPLETE audio transcript. {marker_rule}
3. "questions": an array of EXACTLY 10 independent fill-in-the-blank sentences. Each summarizes a key fact from the passage and contains exactly one "_____". These sentences do NOT form a paragraph.
4. Each "answers" array must have at least 2 acceptable variations, and each answer MUST be {word_count_desc}.
5. The passage should be a lecture, conversation, or monologue typical of IELTS listening.
{answer_priority_rule}

Output ONLY valid JSON, no markdown, no comments:
{{
    "type": "sentence",
    "title": "The Title",
    "passage": "Full text with **target** words marked...",
    "questions": [
        {{"id": 1, "question": "The researcher found that _____ plays a crucial role.", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 2, "question": "According to the speaker, _____ was the main cause.", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 3, "question": "The study revealed that _____ ...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 4, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 5, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 6, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 7, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 8, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 9, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}},
        {{"id": 10, "question": "...", "answers": ["{example_answer}"], "explanation": "解析?.."}}
    ]
}}
"""


MAP_LABELLING_PROMPT_TEMPLATE = """
You are an IELTS examiner. Create an IELTS Listening Section 2 map labelling exercise (Band {difficulty} difficulty).

MAP SUBTYPE: **{map_subtype}**

{subtype_instructions}

Tone requirement:
{tone_instruction}

RULES:
1. "passage": A monologue of ~200-300 words. The speaker describes a place while the listener follows on a map/floor plan. Use rich directional language matching the subtype above.
2. "map": A structured JSON object describing the map layout:
   - "name": name of the place
   - "width": 600, "height": 400 (fixed canvas size)
   - "landmarks": array of location objects. Each has:
     - "id": unique string like "L1", "L2", etc.
     - "label": the place name (set to "" for question locations)
     - "x", "y": center coordinates (must be within 30-570 for x, 30-370 for y)
     - "shape": "rect" or "circle"
     - For rect: "w" (width 40-100), "h" (height 30-70)
     - For circle: "r" (radius 15-35)
     - "questionId": integer (1-5) ONLY for unlabelled question locations
   - You MUST have exactly 5 landmarks with questionId (1 through 5) and at least 3 pre-labelled landmarks.
   - "paths": array of path objects, each with "points" (array of [x,y] pairs) and optional "label"
   - "decorations": array of decoration objects with "type" (one of: "tree", "lake", "garden", "parking", "fountain"), "x", "y", and optional "w", "h"
3. "options": An array of exactly 8 strings like ["A. Library", "B. Cafeteria", ...]. These are the answer choices.
4. "questions": An array of exactly 5 objects. Each has:
   - "id": 1-5 (matching the questionId in landmarks)
   - "answer": the correct option letter (A-H)
   - "explanation": explanation in Chinese
5. The landmarks should be spread across the map, not clustered in one area.
6. Include at least 2-3 paths connecting landmarks.
7. Include 2-4 decorations for visual interest.
8. Make sure the passage uses clear directional language that MATCHES the spatial layout of the map coordinates.

Output ONLY valid JSON, no markdown, no comments:
{{
    "type": "map",
    "title": "Tour of [Place Name]",
    "passage": "Welcome to ... As you enter through the main gate...",
    "map": {{
        "name": "[Place Name]",
        "width": 600,
        "height": 400,
        "landmarks": [
            {{"id": "L1", "label": "Main Entrance", "x": 300, "y": 370, "shape": "rect", "w": 80, "h": 25}},
            {{"id": "L2", "label": "", "x": 150, "y": 200, "shape": "rect", "w": 70, "h": 45, "questionId": 1}},
            {{"id": "L3", "label": "Car Park", "x": 500, "y": 350, "shape": "rect", "w": 60, "h": 40}}
        ],
        "paths": [
            {{"points": [[300, 370], [300, 200], [150, 200]], "label": "Main Corridor"}}
        ],
        "decorations": [
            {{"type": "tree", "x": 50, "y": 50}},
            {{"type": "fountain", "x": 450, "y": 100}}
        ]
    }},
    "options": ["A. Library", "B. Science Lab", "C. Cafeteria", "D. Sports Hall", "E. Art Studio", "F. Health Centre", "G. Student Union", "H. Book Shop"],
    "questions": [
        {{"id": 1, "answer": "A", "explanation": "解析：讲话说沿主路直走就能看到图书馆在左手边..."}},
        {{"id": 2, "answer": "C", "explanation": "解析?.."}},
        {{"id": 3, "answer": "E", "explanation": "解析?.."}},
        {{"id": 4, "answer": "D", "explanation": "解析?.."}},
        {{"id": 5, "answer": "F", "explanation": "解析?.."}}  
    ]
}}
"""

MAP_SUBTYPES = {
    'indoor': {
        'name': 'Indoor Plan (室内布局图)',
        'instructions': """INDOOR PLAN SCENARIO:
Setting: A library, museum, sports centre, gallery, exhibition hall, or new office building.
Layout elements: Clear entrance (Entrance / Main Door), corridors, foyer/lobby, reception desk, rooms, halls.

DIRECTIONAL LANGUAGE - DO NOT use compass directions (N/S/E/W). Use ONLY relative positions:
- "on your left / right", "straight ahead", "at the far end"
- "opposite", "next to", "beside", "adjacent to"
- "in the corner", "at the back of", "behind the reception"
- "through the double doors", "along the corridor", "past the lifts"
- "on the first/second floor", "upstairs", "at the top of the stairs"

Decorations: Use "fountain" for indoor water features, "garden" for indoor plants/atrium.
Paths: Represent corridors and hallways. Label them (e.g. "Main Corridor", "East Wing").
The passage should describe a route walking through the building from the entrance."""
    },
    'outdoor': {
        'name': 'Outdoor Map (室外平面图)',
        'instructions': """OUTDOOR MAP SCENARIO:
Setting: A park, university campus, holiday resort, farm, or tourist attraction.
Layout elements: Large open area with natural and man-made features.

DIRECTIONAL LANGUAGE - Use BOTH compass directions AND relative positions:
- Compass: "to the north/south/east/west of", "in the north-east corner"
- Relative: "next to", "opposite", "beyond", "across from"
- Movement: "if you follow the path", "heading towards", "as you walk along"
- Reference landmarks: "the lake in the north", "behind the main building"

Decorations: Use trees, lakes, gardens, parking lots, fountains generously.
Paths: Represent walkways, trails, roads. Label them (e.g. "Main Path", "Lakeside Trail").
The passage should use a prominent natural landmark (lake, hill, river) as a reference point for positioning."""
    },
    'street': {
        'name': 'Street Map (街道街区图)',
        'instructions': """STREET MAP SCENARIO:
Setting: A town centre, newly developed neighbourhood, or traffic improvement area.
Layout elements: Named roads, intersections (crossroads / T-junctions), traffic lights, zebra crossings, bridges, roundabouts.

DIRECTIONAL LANGUAGE - Dense movement-oriented vocabulary:
- "go straight along [Road Name]", "turn left/right at the junction"
- "take the first/second turning on the left"
- "cross the bridge", "go past the traffic lights"
- "on the corner of [Road A] and [Road B]"
- "it's between [Place A] and [Place B]"
- "continue down the road until you reach..."

Decorations: Use "parking" for car parks, "tree" for roadside trees, "fountain" for town square features.
Paths: Represent ROADS and STREETS. Label all paths with street names (e.g. "High Street", "Park Road", "Bridge Lane").
The passage should give a walking route with CONSECUTIVE turning instructions, mentioning road names and intersections."""
    }
}



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_listening(request):
    """POST /api/listening/generate - 生成听力填空练习。"""
    try:
        limit_resp = check_rate_limit(request.user.id, 'listening_generate', max_calls=5, window=60)
        if limit_resp: return limit_resp
        words = request.data.get('words', [])
        difficulty = request.data.get('difficulty', '7.0')
        word_count_min = request.data.get('wordCountMin', 1)
        word_count_max = request.data.get('wordCountMax', 2)
        practice_type = request.data.get('practiceType', 'article')
        is_map_mode = practice_type == 'map'
        absurd_mode = str(request.data.get('absurdMode', 'false')).lower() == 'true'
        provider = request.headers.get('X-AI-Provider', 'deepseek')

        tone_instruction = (
            "Use an absurd, playful, joke-rich tone that helps memorization. Keep content classroom-safe: no profanity, no sexual content, no harassment."
            if absurd_mode else
            "Use a standard academic IELTS tone."
        )

        print(f"\n{'='*60}", flush=True)
        print(f"[Listening] 📥 收到请求", flush=True)
        print(f"[Listening]   类型: {practice_type}", flush=True)
        print(f"[Listening]   难度: {difficulty}", flush=True)
        print(f"[Listening]   词数: {word_count_min}~{word_count_max}", flush=True)
        print(f"[Listening]   词汇: {words}", flush=True)

        if not words:
            vocab_instruction = ""
            marker_rule = ""
            mc_marker_rule = ""
            answer_priority_rule = ""
        else:
            word_str = ', '.join(words)
            vocab_instruction = f"incorporating the following vocabulary words as much as possible: {word_str}"
            marker_rule = "Wrap target vocabulary in double asterisks like **word**."
            mc_marker_rule = "IMPORTANT RULES:\\nWhenever you use one of the target vocabulary words (or its tense/plural variations) in either the passage OR the questions/options, you MUST wrap it in double asterisks, like **word**. Do NOT use asterisks for anything else."
            answer_priority_rule = "IMPORTANT: Try to incorporate the provided vocabulary words as answers. If possible, make these words the primary answers in the answers array."

        # 生成更明确的词数描述和示例答案
        if word_count_min == word_count_max:
            if word_count_min == 1:
                word_count_desc = "exactly ONE word only (not two, not three, just one single word)"
                example_answer = "dedication"
            elif word_count_min == 2:
                word_count_desc = "exactly TWO words (a two-word phrase)"
                example_answer = "climate change"
            else:
                word_count_desc = f"exactly {word_count_min} words"
                example_answer = "rapidly growing population"
        else:
            word_count_desc = f"NO MORE THAN {word_count_max} words (between {word_count_min} and {word_count_max} words)"
            if word_count_max == 1:
                example_answer = "dedication"
            elif word_count_max == 2:
                example_answer = "climate change"
            else:
                example_answer = "growing population"

        
        if is_map_mode:
            subtype_key = random.choice(list(MAP_SUBTYPES.keys()))
            subtype = MAP_SUBTYPES[subtype_key]
            print(f"[Listening] 🗺️ 地图子类型: {subtype['name']}", flush=True)
            prompt = MAP_LABELLING_PROMPT_TEMPLATE.format(
                difficulty=difficulty,
                tone_instruction=tone_instruction,
                map_subtype=subtype['name'],
                subtype_instructions=subtype['instructions'],
            )
        elif practice_type == 'multiple_choice':
            prompt = ARTICLE_LISTENING_MULTIPLE_CHOICE_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                mc_marker_rule=mc_marker_rule,
                tone_instruction=tone_instruction,
            )
        elif practice_type == 'sentence':
            prompt = SENTENCE_LISTENING_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                word_count_desc=word_count_desc,
                example_answer=example_answer,
                marker_rule=marker_rule,
                answer_priority_rule=answer_priority_rule,
                tone_instruction=tone_instruction,
            )
        else:
            prompt = ARTICLE_LISTENING_PROMPT_TEMPLATE.format(
                vocab_instruction=vocab_instruction,
                difficulty=difficulty,
                word_count_desc=word_count_desc,
                example_answer=example_answer,
                marker_rule=marker_rule,
                answer_priority_rule=answer_priority_rule,
                tone_instruction=tone_instruction,
            )

        print(f"[Listening] 📝 AI 提示词\n{prompt[:500]}...\n", flush=True)
        result = call_ai_api(
            prompt,
            provider=provider,
            user_id=request.user.id,
            singleflight_scope='listening_generate',
        )
        print(f"[Listening] 🤖 AI 完整返回:\n{json.dumps(result, ensure_ascii=False, indent=2)[:2000]}...\n", flush=True)

        # 打印 AI 返回的关键信息
        print(f"[Listening] 📊 AI 返回数据:", flush=True)
        print(f"[Listening]   type: {result.get('type', '❌ 缺失')}", flush=True)
        print(f"[Listening]   title: {result.get('title', '❌ 缺失')}", flush=True)
        print(f"[Listening]   passage: {result.get('passage', '❌ 缺失')}", flush=True)
        print(f"[Listening]   passage 长度: {len(result.get('passage', ''))} 字符", flush=True)
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            print(f"[Listening]   blanked_passage 长度: {len(bp)} 字符", flush=True)
            print(f"[Listening]   blanked_passage 中 _____ 数量: {bp.count('_____')}", flush=True)
        raw_q = result.get('questions', [])
        print(f"[Listening]   questions 数量: {len(raw_q)}", flush=True)
        for q in raw_q:
            ans = q.get('answers', [])
            print(f"[Listening]     Q{q.get('id')}: answers={ans}, has_blank={'_____' in q.get('question', '')}", flush=True)

        # 强力后处理：确保数据结构完整
        # 确保 type 字段存在
        if 'type' not in result:
            result['type'] = practice_type

        # 确保 questions 数组存在且不为空
        questions = result.get('questions', [])
        if not questions:
            return JsonResponse({'error': 'AI failed to generate questions. Please try again.'}, status=500)

        # 截断为最多 10 个题目
        if len(questions) > 10:
            print(f"[Listening] ⚠️ 题目超过10个({len(questions)})，截断为10", flush=True)
            questions = questions[:10]
            result['questions'] = questions

        # 重新编号 id 为 1-10
        for i, q in enumerate(questions):
            q['id'] = i + 1

        # 强力后处理：标准化所有下划线（统一为 5 个）
        for q in questions:
            q['question'] = re.sub(r'_{2,}', '_____', q.get('question', ''))
        
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if bp:
                result['blanked_passage'] = re.sub(r'_{2,}', '_____', bp)

        # 句子模式：确保每个 question 都包含 _____
        if practice_type == 'sentence':
            for q in questions:
                if '_____' not in q.get('question', ''):
                    q['question'] = q['question'].rstrip('.') + ' _____.'

        # 文章填空模式：确保 blanked_passage 存在并包含 _____
        if practice_type == 'article':
            bp = result.get('blanked_passage', '')
            if not bp or '_____' not in bp:
                result['blanked_passage'] = result.get('passage', '')
            else:
                # 确保 blanked_passage 中的空格数量与 questions 数量一致
                blank_count = bp.count('_____')
                if blank_count < len(questions):
                    # 空格比题目少，截断题目数量以匹配
                    result['questions'] = questions[:blank_count]
                    for i, q in enumerate(result['questions']):
                        q['id'] = i + 1

        if is_map_mode:
            # 地图题后处理
            map_data = result.get('map', {})
            landmarks = map_data.get('landmarks', [])
            mw = map_data.get('width', 600)
            mh = map_data.get('height', 400)
            # 校验坐标范围
            for lm in landmarks:
                lm['x'] = max(30, min(mw - 30, lm.get('x', 300)))
                lm['y'] = max(30, min(mh - 30, lm.get('y', 200)))
            # 确保 questions 与 questionId 对应
            q_ids_in_map = {lm['questionId'] for lm in landmarks if 'questionId' in lm}
            result['questions'] = [q for q in result.get('questions', []) if q.get('id') in q_ids_in_map]
            # 确保 options 是列表
            if not isinstance(result.get('options'), list):
                result['options'] = []
            print(f"[Listening] 🗺️ 地图题: {len(landmarks)} 个地标, {len(result['questions'])} 个题目, {len(result['options'])} 个选项", flush=True)

        elif practice_type == 'multiple_choice':
            for q in result.get('questions', []):
                options_list = q.get('options')
                if isinstance(options_list, list) and len(options_list) >= 1:
                    correct_text = options_list[0]
                    shuffled = list(options_list)
                    random.shuffle(shuffled)
                    
                    letters = ['A', 'B', 'C', 'D']
                    options_dict = {}
                    correct_letter = 'A'
                    for idx, opt_text in enumerate(shuffled[:4]):
                        letter = letters[idx]
                        options_dict[letter] = opt_text
                        if opt_text == correct_text:
                            correct_letter = letter
                    
                    q['options'] = options_dict
                    q['answer'] = correct_letter

        print(f"[Listening] ✅ 最终返回 {len(result.get('questions', []))} 个题目", flush=True)
        
        # 禁用用户词汇答案优化，直接使用 AI 生成的答案
        print(f"[Listening] 📌 不执行词汇优化，使用 AI 生成的答案", flush=True)
        
        # 打印最终返回的答案和题目
        print(f"[Listening] 📤 最终返回的答案和题目", flush=True)
        final_questions = result.get('questions', [])
        for q in final_questions:
            print(f"[Listening]   Q{q.get('id')}: {q.get('question', '')}", flush=True)
            print(f"[Listening]      答案: {q.get('answers', [])}", flush=True)
            print(f"[Listening]      解析: {q.get('explanation', '')}", flush=True)
        
        print(f"[Listening] 📄 Passage:", flush=True)
        print(f"{result.get('passage', '')}", flush=True)
        
        print(f"{'='*60}\n", flush=True)
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
def generate_listening_audio(request):
    """POST /api/listening/audio - 生成 Edge-TTS 的 mp3 文件。"""
    try:
        text = request.data.get('text', '')

        def markdown_to_tts_text(value: str) -> str:
            """
            Convert Markdown/GFM text to a clean plain-text string for TTS.
            Keep semantic content while removing formatting markers.
            """
            raw = html.unescape(str(value or ''))
            if not raw:
                return ''

            out = raw.replace('\r\n', '\n').replace('\r', '\n')

            # Remove fenced code block markers while keeping code content.
            out = re.sub(r'^\s*```[^\n]*\n?', '', out, flags=re.MULTILINE)
            out = out.replace('```', '')

            # Convert Markdown links/images to readable text.
            out = re.sub(r'!\[([^\]]*)\]\([^\)]*\)', r'\1', out)
            out = re.sub(r'\[([^\]]+)\]\([^\)]*\)', r'\1', out)

            # Remove common Markdown prefixes.
            out = re.sub(r'^\s{0,3}#{1,6}\s*', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s{0,3}>\s?', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*[-*+]\s+', '', out, flags=re.MULTILINE)
            out = re.sub(r'^\s*\d+\.\s+', '', out, flags=re.MULTILINE)

            # Remove emphasis/code markers but keep inner text.
            out = re.sub(r'\*\*([^*]+)\*\*', r'\1', out)
            out = re.sub(r'__([^_]+)__', r'\1', out)
            out = re.sub(r'\*([^*]+)\*', r'\1', out)
            out = re.sub(r'_([^_]+)_', r'\1', out)
            out = re.sub(r'~~([^~]+)~~', r'\1', out)
            out = re.sub(r'`([^`]*)`', r'\1', out)

            # Remove HTML tags and raw URLs that sound noisy in speech.
            out = re.sub(r'<[^>]+>', ' ', out)
            out = re.sub(r'https?://\S+', ' ', out)

            # Normalize whitespace/newlines.
            out = re.sub(r'[ \t]+', ' ', out)
            out = re.sub(r'\n{3,}', '\n\n', out)
            return out.strip()

        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        speak_text = markdown_to_tts_text(text)
        if not speak_text:
            speak_text = str(text).strip()

        # 雅听力常选用的声音：英(鑻卞浗) Sonia
        voice = "en-GB-SoniaNeural"

        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_path = f.name

        try:
            cmd = ["edge-tts", "--voice", voice, "--text", speak_text, "--write-media", temp_path]
            subprocess.run(cmd, check=True)
            
            with open(temp_path, "rb") as f:
                audio_data = f.read()
                
            return HttpResponse(audio_data, content_type="audio/mpeg")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _clean_answer_value(answer: any) -> str:
    """
    清理答案值：处理多种格式
    1. 如果是对象/字典，提取 answer 字段
    2. 移除括号和其他封装符号：(answer) -> answer
    3. 移除多个相关答案，只保留第一个：answer1/answer2 -> answer1
    4. 去除前后空格和标点
    """
    # 如果是字典对象，尝试提取 answer 字段
    if isinstance(answer, dict):
        answer = answer.get('answer', answer.get('value', str(answer)))
    
    answer = str(answer).strip()
    
    # 移除所有括号（圆括号、方括号、花括号）
    answer = answer.strip('()[]{}')
    
    # 处理多个相关答案，按优先级只保留第一个
    # 优先级：/ > , > ;
    for separator in ['/', ',', ';', ' or ', ' OR ', ' | ']:
        if separator in answer:
            answer = answer.split(separator)[0].strip()
            break
    
    # 移除结尾标点符号
    answer = answer.rstrip('.,;:!?')
    
    return answer.strip()


