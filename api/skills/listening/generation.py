"""
Listening Generation Skills — 听力出题相关 AI 技能模板

覆盖 IELTS Listening 官方 9 种题型 + 4 Section 综合套题.

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


# ══════════════════════════════════════════════════════════════════════
# ── v2 扩展: 场景池 + 5 种新题型 + 4-Section 综合套题 ──
# ══════════════════════════════════════════════════════════════════════

# ── 场景池 (按 Section 分组) ──────────────────────────
# 真雅思场景分布:
#   S1 双人对话 - 社会场景 (咨询/预订/登记)
#   S2 独白     - 社会场景 (介绍/导览)
#   S3 学术讨论 - 教育场景 (辅导/项目)
#   S4 学术独白 - 学术讲座 (研究/课程)
LISTENING_SCENARIO_POOL = {
    's1': {
        'accommodation':      'Accommodation enquiry (renting a flat / student housing)',
        'job_enquiry':        'Job enquiry (part-time role / summer job / volunteering)',
        'gym_signup':         'Gym or leisure centre membership registration',
        'travel_booking':     'Travel or holiday booking (tour / hotel / flight enquiry)',
        'library_signup':     'Library or club membership sign-up',
        'event_booking':      'Event booking (concert / theatre / conference)',
        'restaurant_booking': 'Restaurant reservation with special requirements',
        'phone_survey':       'Phone survey (consumer preferences / community feedback)',
    },
    's2': {
        'museum_tour':        'Museum or gallery tour introduction',
        'campus_orientation': 'University or college campus orientation talk',
        'park_intro':         'National park / botanical garden orientation talk',
        'facility_opening':   'New facility opening announcement (sports centre / community hall)',
        'radio_show':         'Local radio segment about a community event',
        'event_announcement': 'Event coordinator briefing volunteers',
    },
    's3': {
        'tutorial_discussion': 'Tutorial: two students + tutor discussing an assignment',
        'group_project':       'Group project meeting between students',
        'thesis_meeting':      'Student meeting with supervisor about dissertation',
        'assignment_review':   'Peer review of essay drafts',
        'research_planning':   'Planning a joint research task',
    },
    's4': {
        'history_lecture':       'History lecture (e.g., early industry, ancient trade)',
        'science_lecture':       'Science lecture (e.g., biology, physics, ecology)',
        'social_science_lecture':'Social science lecture (economics, sociology, education)',
        'business_lecture':      'Business or management lecture',
        'health_lecture':        'Health science / medicine lecture',
    },
}

# 综合模式各段题数 (真雅思 40 题 = 10 * 4)
LISTENING_FULL_SECTION_COUNT = 4
LISTENING_FULL_QUESTIONS_PER_SECTION = 10


# ── 共用 preamble ─────────────────────────────────────
LISTENING_COMMON_PREAMBLE = """You are an IELTS Listening examiner writing authentic Cambridge-style listening material.

TARGET LEVEL: IELTS Band {difficulty}
SCENARIO: {scenario_instruction}
SPEAKERS: {speakers_desc}

Tone requirement:
{tone_instruction}

{vocab_instruction}
{marker_rule}

PASSAGE (audio transcript) REQUIREMENTS:
- Length: {length_desc}
- Natural spoken register — contractions ("I've", "that's"), filler words sparingly ("well", "actually", "let me see"), self-corrections where appropriate ("no, sorry, it's actually...").
- For multi-speaker sections, prefix each turn with a bracketed speaker label on its own line: "[SPEAKER_A]", "[SPEAKER_B]". Do NOT invent character names inside the label — keep them as A/B/C.
- Never use words like "blank" or "underscore" that would give away answers.
- Numbers, dates, addresses, and spellings should be pronounced as they would be on tape (e.g., "double four seven" for 447).
"""

_ONE_SPEAKER = 'ONE speaker (monologue).'
_TWO_SPEAKERS = 'TWO speakers labelled A and B (turn-taking dialogue).'
_THREE_SPEAKERS = 'THREE speakers labelled A, B and C (natural interruptions allowed).'


# ── 5. Form Completion ────────────────────────────────
SKILL_LISTENING_FORM_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Form Completion — a filled-in form with 10 numbered blanks.
WORD LIMIT: {word_count_desc} for each blank (or a NUMBER).

Design a realistic form the listener would fill in during the conversation (e.g., Membership Application, Booking Form, Enquiry Log). Provide the form as a plain-text layout with numbered blanks (1)-(10).

Each answer MUST be a substring appearing VERBATIM in the audio transcript.

Output STRICTLY this JSON (no markdown, no comments):
{{
    "type": "form",
    "title": "Form Title (e.g., 'Fitness Centre Membership Form')",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript with [SPEAKER_A] / [SPEAKER_B] labels.",
    "form_intro": "Complete the form below. Write NO MORE THAN {word_count_desc_short} for each answer.",
    "form_content": "Applicant Name: Sarah Chen (given)\\nAddress: (1) _____\\nPostcode: (2) _____\\nDate of Birth: (3) _____\\nMembership Type: (4) _____\\nMonthly Fee: £(5) _____\\nPreferred Class: (6) _____\\nEmergency Contact: (7) _____\\nSpecial Requirements: (8) _____\\nHow did you hear about us: (9) _____\\nStart Date: (10) _____",
    "questions": [
        {{"id": 1, "answers": ["42 Church Lane"], "explanation": "中文: 音频原词 '42 Church Lane'."}}
    ]
}}
"""
)

# ── 6. Table Completion ────────────────────────────────
SKILL_LISTENING_TABLE_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Table Completion — a comparison table with 8 numbered blanks.
WORD LIMIT: {word_count_desc} for each blank.

Design a 2-4 column table that naturally captures the audio content (e.g., comparison of tour packages, class options, product plans). Some cells are pre-filled; 8 cells contain numbered blanks (1)-(8).

Provide the table as GitHub-flavoured markdown so a frontend can render it directly. Each answer MUST appear VERBATIM in the transcript.

Output STRICTLY this JSON:
{{
    "type": "table",
    "title": "Table Title",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript.",
    "table_intro": "Complete the table below. Write NO MORE THAN {word_count_desc_short} for each answer.",
    "table_content": "| Package | Duration | Cost | Includes |\\n| --- | --- | --- | --- |\\n| Basic | (1) _____ | £45 | (2) _____ |\\n| Standard | 2 days | (3) _____ | Lunch, guide |\\n| Premium | (4) _____ | £180 | (5) _____ |\\n| Deluxe | 5 days | (6) _____ | (7) _____ |\\n| Custom | Flexible | (8) _____ | All above |",
    "questions": [
        {{"id": 1, "answers": ["one day"], "explanation": "中文: 音频原词."}}
    ]
}}
"""
)

# ── 7. Flowchart Completion ────────────────────────────
SKILL_LISTENING_FLOWCHART_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Flowchart Completion — a sequential process diagram with 6 numbered blanks.
WORD LIMIT: {word_count_desc} for each blank.

Design a linear or branching flowchart (usually 6-8 steps) representing a procedure the speaker explains (e.g., how to apply for a scholarship, steps in a lab experiment, a customer complaint process).

Provide "flowchart_content" as plain text with arrows "→" between steps. Blanks numbered (1)-(6). Each answer MUST appear VERBATIM in the transcript.

Output STRICTLY this JSON:
{{
    "type": "flowchart",
    "title": "Process Title",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript.",
    "flowchart_intro": "Complete the flow-chart below. Write NO MORE THAN {word_count_desc_short} for each answer.",
    "flowchart_content": "Step 1: Submit (1) _____\\n↓\\nStep 2: Attend (2) _____\\n↓\\nStep 3: Prepare (3) _____\\n↓\\nStep 4: (4) _____ interview\\n↓\\nStep 5: Receive (5) _____ within 4 weeks\\n↓\\nStep 6: Sign (6) _____",
    "questions": [
        {{"id": 1, "answers": ["online application"], "explanation": "中文: 音频原词."}}
    ]
}}
"""
)

# ── 8. Matching (听力配对) ─────────────────────────────
SKILL_LISTENING_MATCHING_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Matching — match 5-6 items to a bank of options (A-G).

Common setups:
  - Match each speaker to their opinion
  - Match each course / product / activity to its feature or day
  - Match each location on a schedule to its purpose

Create EXACTLY 5 numbered items and EXACTLY 7 options (A-G). Options may be used more than once OR not at all.
Distractors should reference things ACTUALLY mentioned in the audio but incorrectly attributed.

Output STRICTLY this JSON:
{{
    "type": "matching",
    "title": "Matching Task Title",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript.",
    "matching_intro": "Which comment applies to each course? Write the correct letter A-G next to questions 1-5.",
    "options_bank": {{
        "A": "Popular with beginners",
        "B": "Requires previous experience",
        "C": "Held on weekends only",
        "D": "Includes a certificate",
        "E": "Currently unavailable",
        "F": "Suitable for young learners",
        "G": "Runs during term time"
    }},
    "questions": [
        {{"id": 1, "question": "Cookery basics", "answer": "A", "explanation": "中文: 音频中说 'popular with people who have never cooked before' 对应 A."}},
        {{"id": 2, "question": "Advanced photography", "answer": "B", "explanation": "..."}},
        {{"id": 3, "question": "Weekend jazz", "answer": "C", "explanation": "..."}},
        {{"id": 4, "question": "Spanish for children", "answer": "F", "explanation": "..."}},
        {{"id": 5, "question": "Digital drawing", "answer": "G", "explanation": "..."}}
    ]
}}
"""
)

# ── 9. Short Answer ────────────────────────────────────
SKILL_LISTENING_SHORT_ANSWER_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Short-Answer Questions — brief factual questions answered with words FROM the audio.
WORD LIMIT: {word_count_desc}.

Create EXACTLY 5 wh-questions (What, Where, When, Who, Why, How, How many). Each answer must appear VERBATIM in the transcript. Do NOT ask yes/no questions.

Output STRICTLY this JSON:
{{
    "type": "short_answer",
    "title": "Passage Title",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript.",
    "short_intro": "Answer the questions below. Write NO MORE THAN {word_count_desc_short} for each answer.",
    "questions": [
        {{"id": 1, "question": "What time does the tour start?", "answers": ["9.30 am", "9:30 am"], "explanation": "中文: 原词."}},
        {{"id": 2, "question": "How many participants can join?", "answers": ["twenty", "20"], "explanation": "..."}},
        {{"id": 3, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 4, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 5, "question": "...", "answers": ["..."], "explanation": "..."}}
    ]
}}
"""
)


# ── v2 题型注册表 (含新题型 + 现有 4 种) ───────────────
# key = subtype (存 AIQuestion); value = (template, num_speakers, length_words, needs_word_limit)
LISTENING_QUESTION_TYPES_V2 = {
    # 现有 4 种
    'article':         (SKILL_LISTENING_ARTICLE_TEMPLATE,           1, '250-350', True),
    'sentence':        (SKILL_LISTENING_SENTENCE_TEMPLATE,          1, '250-350', True),
    'multiple_choice': (SKILL_LISTENING_MULTIPLE_CHOICE_TEMPLATE,   1, '250-350', False),
    'map':             (SKILL_LISTENING_MAP_TEMPLATE,               1, '200-300', False),
    # 新增 5 种
    'form':            (SKILL_LISTENING_FORM_TEMPLATE,              2, '350-450', True),
    'table':           (SKILL_LISTENING_TABLE_TEMPLATE,             2, '350-450', True),
    'flowchart':       (SKILL_LISTENING_FLOWCHART_TEMPLATE,         1, '300-400', True),
    'matching':        (SKILL_LISTENING_MATCHING_TEMPLATE,          1, '300-400', False),
    'short_answer':    (SKILL_LISTENING_SHORT_ANSWER_TEMPLATE,      1, '250-350', True),
}


def get_speakers_desc(num: int) -> str:
    return {1: _ONE_SPEAKER, 2: _TWO_SPEAKERS, 3: _THREE_SPEAKERS}.get(num, _ONE_SPEAKER)


def get_listening_scenario(section_key: str, scenario_key: str) -> tuple[str, str]:
    """Return (resolved_key, human_instruction). Falls back to random pick from the section pool."""
    import random as _random
    pool = LISTENING_SCENARIO_POOL.get(section_key, {}) or {}
    if not pool:
        return 'general', 'A general listening scenario.'
    if not scenario_key or scenario_key == 'random' or scenario_key not in pool:
        scenario_key = _random.choice(list(pool.keys()))
    return scenario_key, pool[scenario_key]


# ── 4 Section 综合模板 ────────────────────────────────
# 每段独立生成 (view 层并发 4 次调 AI). 每段 10 题.
# Section 1 - form completion (双人对话)
SKILL_LISTENING_SECTION1_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
SECTION 1 of IELTS Listening full test.
QUESTION TYPE: Form Completion (10 blanks).
CONTEXT: A social everyday transaction. Speaker A is asking the questions (staff/agent); Speaker B is the applicant/customer.
WORD LIMIT: NO MORE THAN 2 WORDS AND/OR A NUMBER for each answer.

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 1,
    "sectionType": "form",
    "title": "Section 1 - <form title>",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript with [SPEAKER_A] / [SPEAKER_B] labels.",
    "form_intro": "Complete the form below. Write NO MORE THAN TWO WORDS AND/OR A NUMBER for each answer.",
    "form_content": "<multi-line form layout with (1)-(10) blanks>",
    "questions": [
        {{"id": 1, "answers": ["<verbatim>"], "explanation": "中文原词定位."}}
    ]
}}
"""
)

# Section 2 - map + MCQ (独白, 5 map + 5 MCQ)
SKILL_LISTENING_SECTION2_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
SECTION 2 of IELTS Listening full test.
QUESTION MIX: Split 10 questions into 2 sub-sections:
  - Questions 1-5: MULTIPLE CHOICE (4 options each A/B/C/D)
  - Questions 6-10: MAP LABELLING (assign locations from bank A-H)
CONTEXT: A monologue giving practical information (facility briefing / event orientation).

For the MAP sub-section, provide a "map" object identical in structure to the standalone map mode (landmarks with questionId 6-10, options bank A-H). The passage MUST include clear directional language matching the map layout.
For MCQ, put the CORRECT option first in each options list (frontend will shuffle).

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 2,
    "sectionType": "mixed",
    "title": "Section 2 - <topic>",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript.",
    "subsections": [
        {{
            "type": "multiple_choice",
            "instructions": "Questions 1-5: Choose the correct letter A, B, C or D.",
            "startId": 1,
            "endId": 5,
            "questions": [
                {{"id": 1, "question": "...", "options": ["CORRECT text first", "distractor 1", "distractor 2", "distractor 3"], "explanation": "中文."}}
            ]
        }},
        {{
            "type": "map",
            "instructions": "Questions 6-10: Label the map. Write the correct letter A-H.",
            "startId": 6,
            "endId": 10,
            "options": ["A. Library", "B. Cafeteria", "C. Sports Hall", "D. Art Studio", "E. Health Centre", "F. Book Shop", "G. Reception", "H. Auditorium"],
            "map": {{"name": "...", "width": 600, "height": 400, "landmarks": [], "paths": [], "decorations": []}},
            "questions": [
                {{"id": 6, "answer": "A", "explanation": "..."}}
            ]
        }}
    ]
}}
"""
)

# Section 3 - MCQ + Matching (2-3 人学术讨论)
SKILL_LISTENING_SECTION3_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
SECTION 3 of IELTS Listening full test.
QUESTION MIX:
  - Questions 1-5: MULTIPLE CHOICE (4 options each)
  - Questions 6-10: MATCHING (match items to options bank A-G)
CONTEXT: An educational conversation — tutorial, project meeting, or peer discussion. Speakers should express opinions and disagree politely.

For MCQ, correct option MUST be listed FIRST in options array. For Matching, provide 5 items + 7 options (A-G).

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 3,
    "sectionType": "mixed",
    "title": "Section 3 - <topic>",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript with [SPEAKER_A] / [SPEAKER_B] / [SPEAKER_C] labels.",
    "subsections": [
        {{
            "type": "multiple_choice",
            "instructions": "Questions 1-5: Choose the correct letter A, B, C or D.",
            "startId": 1,
            "endId": 5,
            "questions": [
                {{"id": 1, "question": "...", "options": ["CORRECT first", "d1", "d2", "d3"], "explanation": "中文."}}
            ]
        }},
        {{
            "type": "matching",
            "instructions": "Questions 6-10: Match each item to the correct opinion A-G.",
            "startId": 6,
            "endId": 10,
            "options_bank": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "...", "F": "...", "G": "..."}},
            "questions": [
                {{"id": 6, "question": "Item 1", "answer": "A", "explanation": "..."}}
            ]
        }}
    ]
}}
"""
)

# Section 4 - Note completion (学术讲座, 独白)
SKILL_LISTENING_SECTION4_TEMPLATE = (
    LISTENING_COMMON_PREAMBLE +
    """
SECTION 4 of IELTS Listening full test.
QUESTION TYPE: Note Completion (10 blanks).
CONTEXT: An academic monologue — lecture excerpt. Use hedged academic language ("research suggests", "one theory holds").
WORD LIMIT: NO MORE THAN 2 WORDS for each answer.

Design the notes as structured study notes with subheadings and bullet points. 10 blanks numbered (1)-(10). Each answer must appear VERBATIM in the transcript.

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 4,
    "sectionType": "note",
    "title": "Section 4 - <lecture topic>",
    "scenario": "{scenario_key}",
    "passage": "Full lecture transcript (350-500 words).",
    "note_intro": "Complete the notes below. Write NO MORE THAN TWO WORDS for each answer.",
    "note_content": "<subject heading>\\n\\nBackground\\n• Origin: (1) _____\\n• First studied in (2) _____\\n\\nKey findings\\n• Main mechanism: (3) _____\\n• Contradicted earlier work on (4) _____\\n...",
    "questions": [
        {{"id": 1, "answers": ["<verbatim>"], "explanation": "中文原词定位."}}
    ]
}}
"""
)


LISTENING_SECTION_TEMPLATES = {
    1: (SKILL_LISTENING_SECTION1_TEMPLATE, 2, '250-350'),  # 双人对话
    2: (SKILL_LISTENING_SECTION2_TEMPLATE, 1, '350-450'),  # 独白 (含地图)
    3: (SKILL_LISTENING_SECTION3_TEMPLATE, 3, '400-500'),  # 学术讨论
    4: (SKILL_LISTENING_SECTION4_TEMPLATE, 1, '350-500'),  # 学术讲座
}
