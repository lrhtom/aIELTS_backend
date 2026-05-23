"""
Listening Generation Skills — 听力出题相关 AI 技能模板

所有模板均使用 .format() 插值，保持原样作为字符串常量。
"""


# ── 文章填空模式 ──
SKILL_LISTENING_ARTICLE_TEMPLATE = """
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

# ── 多选模式 ──
SKILL_LISTENING_MULTIPLE_CHOICE_TEMPLATE = """
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

# ── 句子填空模式 ──
SKILL_LISTENING_SENTENCE_TEMPLATE = """
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

# ── 地图标注模式 ──
SKILL_LISTENING_MAP_TEMPLATE = """
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

# ── 地图子类型定义（与 prompt 强耦合，一并提取）──
SKILL_LISTENING_MAP_SUBTYPES = {
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
