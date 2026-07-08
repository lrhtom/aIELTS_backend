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
For each question, provide EXACTLY 3 options as a JSON array — authentic IELTS Listening MCQ is "Choose the correct letter, A, B or C" (3 options, NOT 4).
CRITICAL RULE: The VERY FIRST option in the "options" array (index 0) MUST ALWAYS BE THE CORRECT ANSWER. The remaining 2 options must be incorrect distractors that ARE mentioned in the audio but are wrong (self-corrected by the speaker, rejected by another speaker, or attributed to the wrong thing).
Our system will shuffle them automatically later. Do not assign A, B, C letters yourself.

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
                "Wrong option distractor 2"
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
1. "passage": A monologue of ~200-300 words. The speaker describes where each THING in "questions" is located.
   ── **HARD CONSTRAINT (zero tolerance): the passage MUST NOT contain ANY of the letters A, B, C, D, E, F, G, H, I, J used as a building reference**. Do NOT write phrases like "building A", "block C", "letter D", "labelled E", "next to F". The letter names of the buildings must NEVER be spoken.
   ── The ONLY way to describe a location is by using ORIENTATION FEATURES (real English words like "reception", "main road", "river") and directional / spatial language ("opposite", "behind", "at the far end of", "on your left as you enter", "across the bridge").
   ── **Every orientation feature you use in the passage MUST also exist as a text-labelled landmark on the map** (rule 2b). And **every text-labelled orientation feature on the map MUST be mentioned in the passage at least once** (both directions of the constraint).
   ── Example acceptable phrasing: "The coffee room is opposite the reception, along the main corridor" (uses "reception" + "main corridor" — both must be on the map).
   ── Example FORBIDDEN phrasing: "The coffee room is at building A" — mentions letter A. Reject and rewrite.
2. "map": A structured JSON object describing the map layout:
   - "name": name of the place
   - "width": 600, "height": 400 (fixed canvas size)
   - "landmarks": TWO KINDS of items in this single array:
     a) LETTERED BUILDINGS: **exactly 10 items, one per letter — A, B, C, D, E, F, G, H, I, and J. All ten must be present. Each letter appears EXACTLY ONCE — no duplicates.** These are the answer candidates.
        - "id": the letter (e.g. "A")
        - "label": SINGLE UPPERCASE LETTER "A"-"J"
        - "x","y","shape","w","h" or "r" as before
     b) ORIENTATION FEATURES: 3-6 items, NOT answer options. Text labels the listener uses to reason about position. Examples: "Reception", "Main Entrance", "Main Road", "River", "Access Road", "Car Park", "Lake", "Bridge", "Playground".
        - "id": lowercase kebab-case (e.g. "reception")
        - "label": human-readable ENGLISH WORD(S) (e.g. "RECEPTION", "MAIN ROAD"). Must be at least 2 characters — never a single letter. This signals to the frontend it's an orientation feature, not an answer letter.
        - Same coordinate/shape fields as (a).
     DO NOT set "questionId" on ANY landmark.
     Landmarks must NOT overlap: keep letter buildings spatially distinct from each other and from orientation features.
   - "paths": array of path objects, each with "points" (array of [x,y] pairs) and optional "label" (e.g. "Access Road")
   - "decorations": array of decoration objects with "type" (one of: "tree", "lake", "garden", "parking", "fountain"), "x", "y", and optional "w", "h"
3. "options": exactly ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"] (all ten letters, matching rule 2a).
4. "questions": exactly 5 objects. Each has:
   - "id": 1-5
   - "question": short lowercase phrase describing the thing to LOCATE (e.g. "coffee room")
   - "answer": one letter A-J
   - "explanation": Chinese explanation citing the ORIENTATION cue from the passage. It's OK for the explanation (Chinese, not spoken) to reference the letter — because the explanation is shown AFTER the user answers, so it can name the building. e.g. "解析:passage 说 opposite the reception, along the main corridor. Reception 在图正下方中央,正对面为 C."
5. Layout must be COHERENT — the positions of the letter buildings and the orientation features must make the directional cues in the passage unambiguously point to exactly ONE letter for each answer.
6. NEVER draw numbered markers or red circles.

Self-check before returning:
  (i) Do all 10 letters A-J appear as `label` in landmarks? If not, add the missing ones.
  (ii) Scan the "passage" text: does it contain any standalone capital letters A-J used as building references? If YES, rewrite that sentence using orientation features instead.
  (iii) For every orientation feature mentioned in the passage, is there a matching text-labelled landmark? For every text-labelled landmark, is it mentioned in the passage? Both directions.

Output ONLY valid JSON, no markdown, no comments:
{{
    "type": "map",
    "title": "Plan of [Place Name]",
    "passage": "Good morning everyone, welcome to the new site. As you enter through the main gate on the south side, the reception is directly ahead of you. The coffee room is the building right opposite the reception, along the main corridor. Now, if you look to your right, past the main road, you'll see the warehouse — it's the larger block backing onto the river...",
    "map": {{
        "name": "[Place Name]",
        "width": 600,
        "height": 400,
        "landmarks": [
            {{"id": "A", "label": "A", "x": 100, "y": 200, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "B", "label": "B", "x": 200, "y": 200, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "C", "label": "C", "x": 300, "y": 200, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "D", "label": "D", "x": 400, "y": 200, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "E", "label": "E", "x": 500, "y": 200, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "F", "label": "F", "x": 100, "y": 300, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "G", "label": "G", "x": 200, "y": 300, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "H", "label": "H", "x": 300, "y": 300, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "I", "label": "I", "x": 400, "y": 300, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "J", "label": "J", "x": 500, "y": 300, "shape": "rect", "w": 60, "h": 45}},
            {{"id": "reception", "label": "RECEPTION", "x": 300, "y": 370, "shape": "rect", "w": 100, "h": 25}},
            {{"id": "main-road", "label": "MAIN ROAD", "x": 300, "y": 50, "shape": "rect", "w": 500, "h": 18}},
            {{"id": "river", "label": "RIVER", "x": 570, "y": 250, "shape": "rect", "w": 20, "h": 200}}
        ],
        "paths": [
            {{"points": [[300, 370], [300, 250]], "label": "Main Corridor"}},
            {{"points": [[50, 380], [550, 380]], "label": "Access Road"}}
        ],
        "decorations": [
            {{"type": "tree", "x": 50, "y": 50}}
        ]
    }},
    "options": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
    "questions": [
        {{"id": 1, "question": "coffee room", "answer": "C", "explanation": "解析:passage 说 opposite the reception, along the main corridor. Reception 在图正下方中央,正对面为 C."}},
        {{"id": 2, "question": "warehouse", "answer": "J", "explanation": "解析:passage 说 past the main road, larger block backing onto the river. 靠河一侧的下排是 J."}},
        {{"id": 3, "question": "staff canteen", "answer": "F", "explanation": "解析?.."}},
        {{"id": 4, "question": "meeting room", "answer": "D", "explanation": "解析?.."}},
        {{"id": 5, "question": "human resources", "answer": "H", "explanation": "解析?.."}}
    ]
}}
"""

# ── 地图子类型定义（与 prompt 强耦合，一并提取）──
# ── 通用规则：passage 描述位置时**只用参照物 + 方位**，绝不出现 "building A / letter B" 这种字母提示。
#             参照物（Reception / Main Road / River / Car Park 等）以英文文本标在图上，不参与答案选项。
SKILL_LISTENING_MAP_SUBTYPES = {
    # ── 室内 (Indoor) ──
    'indoor_office': {
        'name': 'Indoor — Office / Workplace (办公楼)',
        'instructions': """INDOOR OFFICE PLAN:
Setting: A newly built office building / open-plan workplace / corporate HQ / co-working space.
Orientation features (add to landmarks as text-labelled): "MAIN ENTRANCE", "RECEPTION", "LIFT LOBBY", "STAIRCASE", "MAIN CORRIDOR", possibly "CAR PARK" outside.
Things to locate (candidates for questions): meeting room, boardroom, staff canteen, coffee room, IT support, human resources, mail room, printing room, storeroom, quiet zone.
DIRECTIONAL LANGUAGE (no compass; strictly relative + reference features):
- "on your left / right as you enter", "at the far end of the main corridor"
- "opposite the reception", "just past the lift lobby", "next to the staircase"
- "the block behind reception, backing onto the car park"
- NEVER: "building A" / "block C" / "labelled D" — the letter must be INFERRED."""
    },
    'indoor_public': {
        'name': 'Indoor — Public Building (公共室内)',
        'instructions': """INDOOR PUBLIC BUILDING PLAN:
Setting: A library, museum, gallery, exhibition hall, sports centre, or community centre.
Orientation features: "MAIN ENTRANCE", "INFORMATION DESK", "LOCKERS", "MAIN HALL", "CAFÉ AREA", "STAIRS", "LIFT".
Things to locate: reading room, children's section, temporary exhibition, gift shop, cloakroom, changing rooms, activity hall, computer area, quiet study, first-aid room.
DIRECTIONAL LANGUAGE:
- "as you come through the main entrance", "just to the left of the information desk"
- "behind the café area", "through the double doors at the back of the main hall"
- "in the corner where the two wings meet"
- Letters NEVER named directly."""
    },
    # ── 室外 (Outdoor) ──
    'outdoor_campus': {
        'name': 'Outdoor — Campus (校园平面图)',
        'instructions': """OUTDOOR CAMPUS MAP:
Setting: A university campus, school grounds, training centre.
Orientation features: "MAIN GATE", "SPORTS FIELD", "CAR PARK", "MAIN ROAD", "STUDENT UNION", "LIBRARY BLOCK" (if it's an orientation feature, not an answer).
Things to locate: lecture theatre, dorm, refectory, health centre, admin office, science lab, art studio, chapel, bookshop, laundry.
DIRECTIONAL LANGUAGE:
- BOTH compass ("in the north-east corner") AND relative ("behind the sports field")
- "if you follow the main path from the gate", "the closer of the two blocks near the car park"
- "across from the main road, backing onto the field"
- Letters NEVER named directly."""
    },
    'outdoor_park': {
        'name': 'Outdoor — Park / Nature (公园/自然)',
        'instructions': """OUTDOOR PARK MAP:
Setting: A public park, botanical garden, nature reserve, farm, or country park.
Orientation features: "LAKE", "RIVER", "CAR PARK", "MAIN ENTRANCE", "PLAYGROUND", "PICNIC AREA", "BANDSTAND".
Things to locate: café, toilets, bicycle hire, information centre, wildlife hide, boat rental, adventure trail start, souvenir shop, tea room, memorial statue.
DIRECTIONAL LANGUAGE:
- "on the north shore of the lake", "just across the small bridge over the river"
- "beyond the playground on the west side", "in the wooded area behind the picnic tables"
- "at the far end of the main path"
- Letters NEVER named directly."""
    },
    'outdoor_resort': {
        'name': 'Outdoor — Resort / Attraction (度假区/景区)',
        'instructions': """OUTDOOR RESORT / ATTRACTION MAP:
Setting: A holiday resort, theme park, seaside town, hotel complex, campsite.
Orientation features: "BEACH", "POOL", "MAIN LODGE", "MARINA", "MAIN GATE", "CAR PARK", "MAIN PATH".
Things to locate: bike rental, restaurant, spa, snack bar, kids' club, laundry, souvenir shop, boat hire, tennis court, mini-golf.
DIRECTIONAL LANGUAGE:
- "right on the seafront", "the second building along the main path from the lodge"
- "opposite the pool, next to the main gate"
- "in the north-west corner of the site, behind the tennis court"
- Letters NEVER named directly."""
    },
    'outdoor_street': {
        'name': 'Outdoor — Street / Neighbourhood (街道街区)',
        'instructions': """STREET / NEIGHBOURHOOD MAP:
Setting: Town centre, redeveloped neighbourhood, high street.
Orientation features: named roads ("HIGH STREET", "PARK ROAD", "BRIDGE LANE"), "TRAFFIC LIGHTS", "ROUNDABOUT", "BRIDGE".
Things to locate: post office, chemist, bank, community hall, cinema, bakery, launderette, art gallery, dentist, tourist office.
DIRECTIONAL LANGUAGE:
- "go straight along High Street", "turn left at the traffic lights"
- "on the corner of Park Road and Bridge Lane"
- "the third shop after the roundabout on the right"
- Letters NEVER named directly."""
    },
    # Legacy short keys kept as aliases for backwards compat
    'indoor':  {'name': 'Indoor Plan (室内布局图)', 'instructions': ''},
    'outdoor': {'name': 'Outdoor Map (室外平面图)', 'instructions': ''},
    'street':  {'name': 'Street Map (街道街区图)', 'instructions': ''},
}
# alias legacy short keys to new detailed variants
SKILL_LISTENING_MAP_SUBTYPES['indoor']  = SKILL_LISTENING_MAP_SUBTYPES['indoor_public']
SKILL_LISTENING_MAP_SUBTYPES['outdoor'] = SKILL_LISTENING_MAP_SUBTYPES['outdoor_park']
SKILL_LISTENING_MAP_SUBTYPES['street']  = SKILL_LISTENING_MAP_SUBTYPES['outdoor_street']


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
WORD LIMIT: ONE WORD AND/OR A NUMBER for each answer (authentic recent Cambridge convention for Part 1).
AUTHENTIC DETAILS: at least one answer should be a name/address SPELLED OUT letter-by-letter in the audio ("that's B-R-A-X-T-O-N"), and at least two should be numbers/prices/dates pronounced naturally ("double four seven"). The form starts with ONE pre-filled example row marked "(Example)" whose value is already given — it is NOT one of the 10 numbered blanks.

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 1,
    "sectionType": "form",
    "title": "Section 1 - <form title>",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript with [SPEAKER_A] / [SPEAKER_B] labels.",
    "form_intro": "Complete the form below. Write ONE WORD AND/OR A NUMBER for each answer.",
    "form_content": "<multi-line form layout: first a pre-filled '(Example)' row, then (1)-(10) blanks>",
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
  - Questions 1-5: MULTIPLE CHOICE (EXACTLY 3 options each — authentic IELTS Listening is "A, B or C")
  - Questions 6-10: MAP LABELLING (locate a THING on a floor-plan whose buildings are labelled A-J)
CONTEXT: A monologue giving practical information (facility briefing / event orientation).

MAP SUB-SECTION FORMAT (CRITICAL — new paradigm, DO NOT emit red numbered markers):
  - The map has **exactly 10** buildings labelled A, B, C, D, E, F, G, H, I, J. ALL TEN letters MUST appear as landmarks — none may be omitted AND each letter appears EXACTLY ONCE (no duplicates).
  - Each lettered landmark object in "map.landmarks" has "label" set to a SINGLE UPPERCASE LETTER — "A" through "J" — and NO "questionId" field.
  - You MUST include additionally 3-6 ORIENTATION FEATURES as extra landmarks (NOT answer options). Their "label" is a real English word or phrase (>=2 chars), never a single letter. Examples: "Reception", "Main Entrance", "Main Road", "River", "Access Road", "Car Park", "Lake", "Bridge", "Playground".
  - "options" MUST be exactly ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].
  - Each of the 5 questions asks WHERE a specific thing is (e.g. "coffee room", "warehouse"). Fields:
      "id": 6-10, "question": short thing-to-locate phrase, "answer": one letter A-J, "explanation": Chinese.
  - The passage MUST describe where each thing is located using ONLY orientation features + directional / spatial language.
  - **HARD CONSTRAINT (zero tolerance)**: the passage MUST NOT contain any of the letters A/B/C/D/E/F/G/H/I/J used as a building reference. NO "building A", "block C", "labelled D", "letter E" style. Enforce this by using orientation features instead.
  - **Bidirectional constraint**: every orientation feature word mentioned in the passage MUST exist as a text-labelled landmark on the map; and every text-labelled orientation feature landmark MUST be mentioned in the passage at least once.
For MCQ, put the CORRECT option first in each options list (frontend will shuffle). Each MCQ has EXACTLY 3 options (1 correct + 2 distractors).

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 2,
    "sectionType": "mixed",
    "title": "Section 2 - <topic>",
    "scenario": "{scenario_key}",
    "passage": "Full audio transcript. In the map section the speaker must describe locations using ONLY orientation feature words (reception, main road, car park, river ...) plus directions — NEVER letter names.",
    "subsections": [
        {{
            "type": "multiple_choice",
            "instructions": "Questions 1-5: Choose the correct letter, A, B or C.",
            "startId": 1,
            "endId": 5,
            "questions": [
                {{"id": 1, "question": "...", "options": ["CORRECT text first", "distractor 1", "distractor 2"], "explanation": "中文."}}
            ]
        }},
        {{
            "type": "map",
            "instructions": "Questions 6-10: Label the map. Which building (A-J) is each room in?",
            "startId": 6,
            "endId": 10,
            "options": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "map": {{
                "name": "Plan of [Site Name]",
                "width": 600,
                "height": 400,
                "landmarks": [
                    {{"id": "A", "label": "A", "x": 100, "y": 180, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "B", "label": "B", "x": 200, "y": 180, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "C", "label": "C", "x": 300, "y": 180, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "D", "label": "D", "x": 400, "y": 180, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "E", "label": "E", "x": 500, "y": 180, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "F", "label": "F", "x": 100, "y": 280, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "G", "label": "G", "x": 200, "y": 280, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "H", "label": "H", "x": 300, "y": 280, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "I", "label": "I", "x": 400, "y": 280, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "J", "label": "J", "x": 500, "y": 280, "shape": "rect", "w": 60, "h": 50}},
                    {{"id": "reception", "label": "RECEPTION", "x": 300, "y": 370, "shape": "rect", "w": 100, "h": 25}},
                    {{"id": "main-road", "label": "MAIN ROAD", "x": 300, "y": 50, "shape": "rect", "w": 500, "h": 18}},
                    {{"id": "car-park", "label": "CAR PARK", "x": 570, "y": 350, "shape": "rect", "w": 60, "h": 40}}
                ],
                "paths": [{{"points": [[300, 370], [300, 250]], "label": "Main Corridor"}}],
                "decorations": []
            }},
            "questions": [
                {{"id": 6, "question": "coffee room", "answer": "C", "explanation": "解析:passage 说 opposite the reception, along the main corridor — reception 位于图正下方,正对面即 C."}}
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
  - Questions 1-5: MULTIPLE CHOICE (EXACTLY 3 options each — authentic IELTS Listening is "A, B or C")
  - Questions 6-10: MATCHING (match items to options bank A-G)
CONTEXT: An educational conversation — tutorial, project meeting, or peer discussion. Speakers should express opinions and disagree politely.

For MCQ, correct option MUST be listed FIRST in options array (1 correct + 2 distractors that are genuinely discussed then rejected in the conversation). For Matching, provide 5 items + 7 options (A-G).

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
            "instructions": "Questions 1-5: Choose the correct letter, A, B or C.",
            "startId": 1,
            "endId": 5,
            "questions": [
                {{"id": 1, "question": "...", "options": ["CORRECT first", "d1", "d2"], "explanation": "中文."}}
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
WORD LIMIT: ONE WORD ONLY for each answer (authentic recent Cambridge convention for Part 4 — every answer is a single word).

Design the notes as structured study notes with subheadings and bullet points. 10 blanks numbered (1)-(10). Each answer must be a SINGLE word appearing VERBATIM in the transcript (concrete nouns work best: "factories", "whale", "beaches").

Output STRICTLY this JSON:
{{
    "type": "section",
    "sectionNum": 4,
    "sectionType": "note",
    "title": "Section 4 - <lecture topic>",
    "scenario": "{scenario_key}",
    "passage": "Full lecture transcript (600-800 words).",
    "note_intro": "Complete the notes below. Write ONE WORD ONLY for each answer.",
    "note_content": "<subject heading>\\n\\nBackground\\n• Origin: (1) _____\\n• First studied in (2) _____\\n\\nKey findings\\n• Main mechanism: (3) _____\\n• Contradicted earlier work on (4) _____\\n...",
    "questions": [
        {{"id": 1, "answers": ["<verbatim>"], "explanation": "中文原词定位."}}
    ]
}}
"""
)


# 长度对齐真题 (C9 tapescript 实测: S1=737, S2=603, S3=1043, S4=756 词)
LISTENING_SECTION_TEMPLATES = {
    1: (SKILL_LISTENING_SECTION1_TEMPLATE, 2, '550-750'),  # 双人对话
    2: (SKILL_LISTENING_SECTION2_TEMPLATE, 1, '550-750'),  # 独白 (含地图)
    3: (SKILL_LISTENING_SECTION3_TEMPLATE, 3, '700-900'),  # 学术讨论 (全卷最长)
    4: (SKILL_LISTENING_SECTION4_TEMPLATE, 1, '600-800'),  # 学术讲座
}
