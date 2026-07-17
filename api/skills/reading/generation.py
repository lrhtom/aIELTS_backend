"""
Reading Generation Skills — 阅读出题相关 AI 技能模板

覆盖 IELTS Academic Reading 官方 11 种题型 + 综合套题 (3 篇 passage)。

所有模板均使用 .format() 插值。共用参数:
    - difficulty        雅思 Band 目标 (6.0-8.5)
    - tone_instruction  语气指令 (含 absurd_mode)
    - vocab_instruction 目标词汇指令 (可为空串)
    - marker_rule       **word** 标注规则 (可为空串)
    - topic             题材 (来自 READING_TOPIC_POOL, 或 'random')
    - topic_instruction 派生自 topic 的具体指令

题型键 (READING_QUESTION_TYPES):
    - multiple_choice   4 选 1
    - true_false        True / False / Not Given (或 easy 二选一)
    - yes_no            Yes / No / Not Given (观点判断, 区别于 TFNG)
    - matching_headings 段落配标题 (需要 passage 分段 [A]-[G])
    - matching_info     信息在哪段
    - matching_features 分类归属 (人物 / 理论 / 类别)
    - matching_sentence 句子头尾配对
    - sentence_completion   句子填空 (from passage)
    - summary_completion    摘要段落填空
    - note_completion       笔记 / 表格 / 流程图填空
    - short_answer          简答题 (from passage, 词数限制)
"""

# ── 题材池 ─────────────────────────────────────────────
# 真雅思 Academic Reading 高频话题, 学术 quasi-academic 风格
READING_TOPIC_POOL = {
    'archaeology':        'Archaeology and ancient civilisations',
    'marine_biology':     'Marine biology and ocean ecosystems',
    'urban_planning':     'Urban planning and city development',
    'language':           'Language acquisition and linguistics',
    'climate':            'Climate change and environmental science',
    'trade_history':      'Ancient trade routes and economic history',
    'cognition':          'Cognitive science and human memory',
    'renewable_energy':   'Renewable energy technologies',
    'food_history':       'History of food and agriculture',
    'space':              'Space exploration and astronomy',
    'animal_behaviour':   'Animal behaviour and ethology',
    'architecture':       'Architecture history and building design',
    'social_psychology':  'Social psychology and group behaviour',
    'education':          'Education reform and pedagogy',
    'medicine_history':   'History of medicine and public health',
    'anthropology':       'Cultural anthropology and human societies',
    'geology':            'Geology and earth sciences',
    'transport':          'Transport innovation and mobility',
    'music_history':      'History of music and instruments',
    'psychology_work':    'Workplace psychology and productivity',
}

# 每种题型的题目数 (真雅思单题型 5 题为 practice unit; 综合模式用大数)
READING_QUESTION_COUNT_DEFAULT = 5

# 综合套题参数 — 真题分布 P1=13, P2=13, P3=14, 全卷 40 题
READING_FULL_PASSAGE_COUNT = 3
READING_FULL_QUESTIONS_BY_PASSAGE = {1: 13, 2: 13, 3: 14}

# ── 共用 preamble ─────────────────────────────────────
# 每个题型模板都用它开头 (通过 .format 传入)
READING_COMMON_PREAMBLE = """You are an IELTS Academic examiner writing authentic Cambridge-style reading material.

TARGET LEVEL: IELTS Band {difficulty}
TOPIC AREA: {topic_instruction}

Tone requirement:
{tone_instruction}

{vocab_instruction}
{marker_rule}

PASSAGE REQUIREMENTS:
- Length: 400-550 words (single-type practice mode).
- Style: quasi-academic — informative, third-person, evidence-based; NOT a textbook chapter, NOT a news article.
- Structure: {paragraph_rule}
- Register: neutral academic English matching Band {difficulty}. Use topic-specific vocabulary and hedged claims ("suggests", "may indicate").
- Do NOT invent scholarly references or fake author names. If citing research, use vague attribution like "recent studies", "a 2019 survey".
"""

# 段落规则：普通题型用连续段，特定题型 (headings / matching_info) 要求带 [A]-[G] 标签
_PARAGRAPH_RULE_PLAIN = "5-7 paragraphs, separated by blank lines. Do NOT prefix paragraphs with letters."
_PARAGRAPH_RULE_LABELLED = "EXACTLY 6 paragraphs, each starting on its own line with a label in square brackets on its own line: [A]\\n<paragraph text>\\n\\n[B]\\n<paragraph text>\\n\\n... up to [F]. The label MUST appear before the paragraph text."


# ── 1. Multiple Choice ────────────────────────────────
SKILL_READING_MCQ_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Multiple Choice (A/B/C/D)
Create EXACTLY 5 questions. For each:
- Stem: a complete question or unfinished statement testing detail comprehension, main idea, or inference.
- 4 options (A/B/C/D). ONE correct + 3 distractors.
- DISTRACTOR RULES: each of the 3 distractors must reference a concept, name, or number that ACTUALLY appears in the passage but is wrong because of ONE of:
  (a) wrong attribution (right fact, wrong paragraph/person)
  (b) partial truth misrepresented as full truth
  (c) quantity / time / polarity swap
  (d) plausible-sounding but not stated
- Do NOT invent facts absent from the passage for any option.
- Distribute correct answers across A/B/C/D — do not skew all to one letter.

Output STRICTLY this JSON (no markdown, no extra text):
{{
    "questionType": "multiple_choice",
    "title": "Passage Title",
    "passage": "Full passage text (400-550 words, plain paragraphs).",
    "topic": "{topic}",
    "questions": [
        {{"id": 1, "question": "Question stem", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "answer": "A", "explanation": "中文题解 + 原文定位 (第 X 段)."}}
    ]
}}
"""
)

# ── 2. True / False / Not Given ────────────────────────
SKILL_READING_TFNG_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: True / False / Not Given (FACT-based)
Create EXACTLY 5 statements about FACTS in the passage.
Allowed answers: {tfng_allowed}

CRITICAL SEMANTIC RULES:
- True: the statement AGREES with information given (may paraphrase, but the underlying fact matches).
- False: the statement DIRECTLY CONTRADICTS information given (the passage states the opposite).
- Not Given: the passage NEITHER confirms NOR contradicts — the reader cannot decide from the text alone. NOT the same as "not mentioned but consistent" — a NG statement must introduce information whose truth cannot be inferred.

Distribution: ensure at least one True, at least one False{ng_required}.
Order the 5 statements to follow the passage's flow (statement 1 evidence appears early, statement 5 evidence appears late).

Output STRICTLY this JSON:
{{
    "questionType": "true_false",
    "judgementMode": "{judgement_mode}",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "questions": [
        {{"id": 1, "question": "Statement to judge.", "options": {tfng_options_json}, "answer": "True", "explanation": "中文: 引用原文定位 + 判断理由."}}
    ]
}}
"""
)

# ── 3. Yes / No / Not Given (观点判断) ─────────────────
SKILL_READING_YNNG_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Yes / No / Not Given (OPINION / CLAIM-based)
The passage must express the WRITER'S OWN VIEWS or claims (use hedged language like "argues", "believes", "the author suggests"). Statements test whether they align with the writer's opinion.
Create EXACTLY 5 statements.
Allowed answers: Yes / No / Not Given

CRITICAL SEMANTIC RULES:
- Yes: the statement agrees with the WRITER'S VIEW.
- No: the statement contradicts the writer's view.
- Not Given: it is impossible to tell the writer's view on this specific claim.
Do NOT recycle TFNG-style factual statements — they must be about OPINIONS.

Distribution: include at least one Yes, one No, one Not Given.

Output STRICTLY this JSON:
{{
    "questionType": "yes_no",
    "title": "Passage Title",
    "passage": "Full passage text — the writer's argumentative voice must be present.",
    "topic": "{topic}",
    "questions": [
        {{"id": 1, "question": "The writer believes ...", "options": {{"Yes": "Agrees with writer's view.", "No": "Contradicts writer's view.", "Not Given": "The writer's view on this is not stated."}}, "answer": "Yes", "explanation": "中文: 引用原文中作者立场 (第 X 段) + 判断理由."}}
    ]
}}
"""
)

# ── 4. Matching Headings ──────────────────────────────
SKILL_READING_MATCHING_HEADINGS_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Matching Headings — assign one heading from a bank to each paragraph.

MANDATORY: passage MUST be split into paragraphs [A] through [F] using the labelled format specified above.
Heading bank: provide EXACTLY 9 headings labelled i, ii, iii, iv, v, vi, vii, viii, ix. 6 will be correct (one per paragraph); 3 are distractors.
Each heading should be a short noun phrase (5-10 words) summarising the paragraph's main idea. Distractors must be plausible but reference sub-topics, incorrect scopes, or ideas from adjacent paragraphs.

Output STRICTLY this JSON:
{{
    "questionType": "matching_headings",
    "title": "Passage Title",
    "passage": "[A]\\nFirst paragraph text...\\n\\n[B]\\nSecond paragraph...\\n\\n[C]\\n...\\n\\n[D]\\n...\\n\\n[E]\\n...\\n\\n[F]\\n...",
    "topic": "{topic}",
    "headings_bank": {{
        "i": "First heading option",
        "ii": "Second heading option",
        "iii": "...",
        "iv": "...",
        "v": "...",
        "vi": "...",
        "vii": "...",
        "viii": "...",
        "ix": "..."
    }},
    "questions": [
        {{"id": 1, "paragraph": "A", "answer": "iii", "explanation": "中文: 段落 A 的主旨是 X, 对应 heading iii."}},
        {{"id": 2, "paragraph": "B", "answer": "v", "explanation": "..."}},
        {{"id": 3, "paragraph": "C", "answer": "i", "explanation": "..."}},
        {{"id": 4, "paragraph": "D", "answer": "vii", "explanation": "..."}},
        {{"id": 5, "paragraph": "E", "answer": "ii", "explanation": "..."}},
        {{"id": 6, "paragraph": "F", "answer": "viii", "explanation": "..."}}
    ]
}}
"""
)

# ── 5. Matching Information (信息在哪段) ───────────────
SKILL_READING_MATCHING_INFO_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Matching Information — for each statement, identify which paragraph (A-F) contains it.

MANDATORY: passage MUST use the labelled [A]-[F] paragraph format above.
Create EXACTLY 5 statements describing SPECIFIC pieces of information (examples, comparisons, reasons, definitions). Each statement's evidence sits in exactly one paragraph. Paragraphs may be used more than once OR not at all — this is authentic to the exam.

Statements should paraphrase rather than quote. Do NOT copy full sentences from the passage.

Output STRICTLY this JSON:
{{
    "questionType": "matching_info",
    "title": "Passage Title",
    "passage": "[A]\\n...\\n\\n[B]\\n...\\n\\n[C]\\n...\\n\\n[D]\\n...\\n\\n[E]\\n...\\n\\n[F]\\n...",
    "topic": "{topic}",
    "paragraph_labels": ["A", "B", "C", "D", "E", "F"],
    "questions": [
        {{"id": 1, "question": "a description of X's impact on Y", "answer": "C", "explanation": "中文: C 段提到 ..., 对应该说法."}},
        {{"id": 2, "question": "a comparison between two ...", "answer": "A", "explanation": "..."}},
        {{"id": 3, "question": "an explanation of why ...", "answer": "E", "explanation": "..."}},
        {{"id": 4, "question": "a reference to a specific ...", "answer": "B", "explanation": "..."}},
        {{"id": 5, "question": "an example of ...", "answer": "F", "explanation": "..."}}
    ]
}}
"""
)

# ── 6. Matching Features (分类归属) ────────────────────
SKILL_READING_MATCHING_FEATURES_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Matching Features — classify statements into 3-4 categories (people, theories, time periods, or places).

The passage must clearly discuss 3-4 distinct entities (e.g., three researchers with different views, or three historical periods, or three technologies). Assign each entity a label letter (A, B, C, D).
Create EXACTLY 5 statements. Each statement describes an attribute, claim, finding, or characteristic uniquely attributable to ONE entity. Some entities may be referenced more than once OR not at all.

Output STRICTLY this JSON:
{{
    "questionType": "matching_features",
    "title": "Passage Title",
    "passage": "Full passage — must clearly distinguish 3-4 entities (people/theories/etc).",
    "topic": "{topic}",
    "features_bank": {{
        "A": "First entity name (e.g., 'Dr Chen')",
        "B": "Second entity name",
        "C": "Third entity name",
        "D": "Fourth entity name (optional; omit if only 3 categories)"
    }},
    "questions": [
        {{"id": 1, "question": "argued that X causes Y", "answer": "B", "explanation": "中文: 该观点属于 B 实体, 原文第 X 段."}},
        {{"id": 2, "question": "published findings from a longitudinal study", "answer": "A", "explanation": "..."}},
        {{"id": 3, "question": "focused on ...", "answer": "C", "explanation": "..."}},
        {{"id": 4, "question": "criticised the assumption that ...", "answer": "A", "explanation": "..."}},
        {{"id": 5, "question": "was the first to propose ...", "answer": "B", "explanation": "..."}}
    ]
}}
"""
)

# ── 7. Matching Sentence Endings ───────────────────────
SKILL_READING_MATCHING_SENTENCE_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Matching Sentence Endings — complete each sentence beginning by choosing the correct ending from a bank.

Create EXACTLY 5 sentence BEGINNINGS reflecting facts from the passage. Provide EXACTLY 8 possible endings labelled A-H. 5 are correct (one per beginning); 3 are distractors.
Each ending should be a natural grammatical continuation. Endings must be SIMILAR IN LENGTH and structure so the answer isn't obvious from grammar alone.

Output STRICTLY this JSON:
{{
    "questionType": "matching_sentence",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "endings_bank": {{
        "A": "led to a decline in local biodiversity.",
        "B": "was later confirmed by independent researchers.",
        "C": "remains a subject of scientific debate.",
        "D": "produced results that contradicted earlier assumptions.",
        "E": "was abandoned due to cost overruns.",
        "F": "gained widespread public support.",
        "G": "required new legal frameworks.",
        "H": "encouraged similar projects overseas."
    }},
    "questions": [
        {{"id": 1, "question": "The 1998 pilot programme in Norway", "answer": "D", "explanation": "中文: 原文第 2 段说该计划的结果与预期相反."}},
        {{"id": 2, "question": "...", "answer": "F", "explanation": "..."}},
        {{"id": 3, "question": "...", "answer": "A", "explanation": "..."}},
        {{"id": 4, "question": "...", "answer": "G", "explanation": "..."}},
        {{"id": 5, "question": "...", "answer": "B", "explanation": "..."}}
    ]
}}
"""
)

# ── 8. Sentence Completion ────────────────────────────
SKILL_READING_SENTENCE_COMPLETION_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Sentence Completion — fill each blank with words FROM THE PASSAGE.

WORD LIMIT: {word_count_desc}.
Create EXACTLY 5 independent sentences summarising key facts. Each sentence contains exactly one "_____" blank. The answer for each blank MUST be a substring that appears VERBATIM in the passage (same wording, may be lowercase/uppercase). Do NOT paraphrase the answer.

Output STRICTLY this JSON:
{{
    "questionType": "sentence_completion",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "wordLimit": "{word_count_desc}",
    "questions": [
        {{"id": 1, "question": "The researchers found that _____ was the main cause of the decline.", "answers": ["habitat loss"], "explanation": "中文: 原文第 3 段原词 'habitat loss' 支撑."}},
        {{"id": 2, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 3, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 4, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 5, "question": "...", "answers": ["..."], "explanation": "..."}}
    ]
}}
"""
)

# ── 9. Summary Completion ─────────────────────────────
SKILL_READING_SUMMARY_COMPLETION_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Summary Completion — a paragraph-length summary of PART of the passage with 5 numbered blanks.

WORD LIMIT: {word_count_desc}.
SUMMARY: write a coherent 100-150 word summary paragraph that PARAPHRASES a specific section of the passage (usually paragraphs 2-4). Insert EXACTLY 5 numbered blanks marked as (1), (2), (3), (4), (5).
Each blank's answer MUST be a substring appearing VERBATIM in the ORIGINAL passage.
Provide a WORD BANK of 8 options labelled A-H (5 correct + 3 distractors). All bank options must be valid substrings from the passage.

Output STRICTLY this JSON:
{{
    "questionType": "summary_completion",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "wordLimit": "{word_count_desc}",
    "summary_intro": "Complete the summary below using words from the box. Write the correct letter A-H.",
    "summary_text": "The team began with (1) _____ in 2018. Initial results showed (2) _____ across several sites. However, (3) _____ later became clear, leading to a revised methodology. By 2021, (4) _____ had become the standard approach, though (5) _____ remained a concern.",
    "word_bank": {{
        "A": "field surveys",
        "B": "unexpected patterns",
        "C": "sampling bias",
        "D": "aerial monitoring",
        "E": "budget constraints",
        "F": "high accuracy",
        "G": "public opposition",
        "H": "seasonal variation"
    }},
    "questions": [
        {{"id": 1, "answer": "A", "explanation": "中文: (1) 指起始方法, 原文第 2 段用 'field surveys'."}},
        {{"id": 2, "answer": "B", "explanation": "..."}},
        {{"id": 3, "answer": "C", "explanation": "..."}},
        {{"id": 4, "answer": "D", "explanation": "..."}},
        {{"id": 5, "answer": "E", "explanation": "..."}}
    ]
}}
"""
)

# ── 10. Note / Table / Flow-chart Completion ──────────
SKILL_READING_NOTE_COMPLETION_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Note Completion — a structured note layout summarising a process, timeline, or concept map, with 5 numbered blanks.

WORD LIMIT: {word_count_desc}.
Choose ONE of three layouts based on the passage content:
  - "notes"     : bulleted study-notes format (best for definitions / classifications)
  - "table"     : 2-column table (best for comparisons)
  - "flowchart" : sequential arrows (best for processes / timelines)

Write a "note_content" as clean plain text using markdown-lite conventions:
  - notes:      "• Topic\\n  ○ point 1\\n  ○ (1) _____\\n• Next topic\\n  ○ (2) _____"
  - table:      "| Column A | Column B |\\n| --- | --- |\\n| Row 1 | (1) _____ |\\n| Row 2 | (2) _____ |"
  - flowchart:  "Step 1: initial observation → Step 2: (1) _____ → Step 3: analysis → Step 4: (2) _____"

Each blank's answer MUST be a substring appearing VERBATIM in the passage. Answers must respect the word limit.

Output STRICTLY this JSON:
{{
    "questionType": "note_completion",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "wordLimit": "{word_count_desc}",
    "layout": "notes",
    "note_intro": "Complete the notes below. Write NO MORE THAN {word_count_desc_short} for each answer.",
    "note_content": "• Study aim\\n  ○ Investigate (1) _____ in urban areas\\n• Methodology\\n  ○ Data collected from (2) _____ over 6 months\\n  ○ Analysed using (3) _____\\n• Key findings\\n  ○ (4) _____ was the strongest predictor\\n  ○ Effect was reduced by (5) _____",
    "questions": [
        {{"id": 1, "answers": ["air quality"], "explanation": "中文: 原文第 1 段."}},
        {{"id": 2, "answers": ["42 sensors"], "explanation": "..."}},
        {{"id": 3, "answers": ["regression models"], "explanation": "..."}},
        {{"id": 4, "answers": ["traffic density"], "explanation": "..."}},
        {{"id": 5, "answers": ["green cover"], "explanation": "..."}}
    ]
}}
"""
)

# ── 11. Short-Answer Questions ────────────────────────
SKILL_READING_SHORT_ANSWER_TEMPLATE = (
    READING_COMMON_PREAMBLE +
    """
QUESTION TYPE: Short-Answer Questions — answer each question with words FROM THE PASSAGE.

WORD LIMIT: {word_count_desc}.
Create EXACTLY 5 wh-questions (What, Where, When, Who, Why, How, How many). Each expects a factual answer whose text appears VERBATIM in the passage.
Questions must NOT overlap in scope (spread across the passage). Do NOT ask "yes/no" questions.

Output STRICTLY this JSON:
{{
    "questionType": "short_answer",
    "title": "Passage Title",
    "passage": "Full passage text.",
    "topic": "{topic}",
    "wordLimit": "{word_count_desc}",
    "questions": [
        {{"id": 1, "question": "What did the researchers use to measure air quality?", "answers": ["portable sensors"], "explanation": "中文: 原文第 2 段."}},
        {{"id": 2, "question": "How many cities were included in the pilot study?", "answers": ["twelve", "12"], "explanation": "..."}},
        {{"id": 3, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 4, "question": "...", "answers": ["..."], "explanation": "..."}},
        {{"id": 5, "question": "...", "answers": ["..."], "explanation": "..."}}
    ]
}}
"""
)


# ── 综合套题 (single passage inside a 3-passage test) ─
# 综合模式一次调 AI 只生成 1 篇 passage + ~13 题, 混合 2-3 种题型。
# 上层 view 会并发调 3 次生成 3 篇 passage 拼成完整测试。
SKILL_READING_FULL_PASSAGE_TEMPLATE = (
    READING_COMMON_PREAMBLE.replace(
        '- Length: 400-550 words (single-type practice mode).',
        '- Length: 800-1000 words (full-test passage {passage_num} of 3 — authentic Cambridge passages measure 850-1000 words).'
    ) +
    """
FULL-TEST PASSAGE {passage_num} of 3.
PASSAGE POSITION STYLE (authentic Cambridge difficulty gradient):
{passage_flavor}
QUESTION MIX: {question_mix_desc}
TOTAL QUESTIONS: {total_questions}

Generate a rich Cambridge-style passage suitable for supporting {total_questions} questions across the requested mix. If the mix includes 'matching_headings' or 'matching_info', you MUST use the labelled paragraph format ([A], [B], ...); otherwise use plain paragraphs.

For each sub-section in the mix, follow the corresponding schema and label questions with globally unique IDs 1-{total_questions} (do NOT restart numbering per sub-section).

HARD REQUIREMENTS (violating any of these makes the output unusable):
1. Every bank field required by a section type (headings_bank / features_bank / endings_bank / word_bank / paragraph_labels) MUST be present with REAL text values — never empty strings, never omitted, never placeholders.
2. For summary_completion and note_completion sections, the summary_text / note_content MUST embed one blank per question in the exact format "(1) _____", numbered LOCALLY starting from (1) within that section (regardless of the global question ids).
3. Keep each "explanation" under 25 words — the total output must stay compact enough to never be cut off.

Output STRICTLY this JSON:
{{
    "questionType": "full_passage",
    "passageNum": {passage_num},
    "title": "Passage Title",
    "passage": "Full passage (700-900 words).",
    "topic": "{topic}",
    "sections": [
        {{
            "questionType": "<one of the mix types>",
            "instructions": "Instructions to display (e.g., 'Questions 1-4: Choose the correct letter A-D.').",
            "startId": 1,
            "endId": 4,
            "payload": {{ "...": "REQUIRED type-specific fields, see SECTION SCHEMAS above" }},
            "questions": [
                {{"id": 1, "...": "type-specific fields for each question, see SECTION SCHEMAS above"}}
            ]
        }}
    ]
}}
"""
)


# ── 综合套题·两阶段生成 (2026-07-17) ─────────────────────────────────────────
# 单次调用要求 900 词文章 + 13 题 + 多套 bank 时，deepseek-v4-pro 的推理输出
# 会把响应顶破 max_tokens (finish_reason=length)，或者模型偷工减料把 bank 留空。
# 拆成两阶段：阶段一只生成文章（~1.5K token 输出），阶段二把文章作为输入只生成
# 题目 JSON（禁止回显文章），单次输出减半，两阶段各自独立重试。

SKILL_READING_FULL_PASSAGE_TEXT_TEMPLATE = (
    READING_COMMON_PREAMBLE.replace(
        '- Length: 400-550 words (single-type practice mode).',
        '- Length: 800-1000 words (full-test passage {passage_num} of 3 — authentic Cambridge passages measure 850-1000 words).'
    ) +
    """
FULL-TEST PASSAGE {passage_num} of 3 — PASSAGE TEXT ONLY. Questions are created in a separate step; do NOT write any questions.
PASSAGE POSITION STYLE (authentic Cambridge difficulty gradient):
{passage_flavor}

The passage must be rich and information-dense enough to later support {total_questions} questions of these types: {mix_type_names}.

Output STRICTLY this JSON:
{{
    "title": "Passage Title",
    "passage": "Full passage (800-1000 words)."
}}
"""
)

SKILL_READING_FULL_QUESTIONS_TEMPLATE = """You are an expert IELTS Academic Reading question writer.
Difficulty: Band {difficulty}. {tone_instruction}

Below is the COMPLETE reading passage. Base every question strictly on it.
=== PASSAGE: {title} ===
{passage}
=== END OF PASSAGE ===

Create the question sections for this passage:
{question_mix_desc}

Label questions with globally unique IDs 1-{total_questions} across ALL sections (do NOT restart numbering per section).

HARD REQUIREMENTS (violating any of these makes the output unusable):
1. Every bank field required by a section type (headings_bank / features_bank / endings_bank / word_bank / paragraph_labels) MUST be present with REAL text values — never empty strings, never omitted.
2. For summary_completion and note_completion sections, the summary_text / note_content MUST embed one blank per question in the exact format "(1) _____", numbered LOCALLY starting from (1) within that section.
3. Keep each "explanation" under 25 words (Chinese is fine).
4. Do NOT re-output the passage anywhere in your response.

Output STRICTLY this JSON:
{{
    "sections": [
        {{
            "questionType": "<one of the requested types>",
            "instructions": "Instructions to display.",
            "startId": 1,
            "endId": 4,
            "payload": {{ "...": "REQUIRED type-specific fields, see SECTION SCHEMAS above" }},
            "questions": [
                {{"id": 1, "...": "type-specific fields, see SECTION SCHEMAS above"}}
            ]
        }}
    ]
}}
"""


# ── Full 模式各题型的 payload/questions 具体 schema ──────────────────────────
# 历史教训 (2026-07-17): full prompt 里只写 "type-specific fields" 这种模糊描述，
# 模型不知道 bank 字段的确切形状，经常留空 → 空 Categories / 空 Word bank 废卷。
# 这里给每个题型一段紧凑的具体 schema，_build_full_passage_prompt 按 mix 拼进 prompt。
READING_FULL_SECTION_SCHEMAS: dict = {
    'multiple_choice': (
        'payload: {} (empty). Each question: {"id": N, "question": "...", '
        '"options": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "A", "explanation": "..."}'
    ),
    'true_false': (
        'payload: {} (empty). Each question: {"id": N, "question": "statement about the passage", '
        '"answer": "True" | "False" | "Not Given", "explanation": "..."}'
    ),
    'yes_no': (
        'payload: {} (empty). Each question: {"id": N, "question": "claim about the writer\'s views", '
        '"answer": "Yes" | "No" | "Not Given", "explanation": "..."}'
    ),
    'matching_headings': (
        'payload: {"headings_bank": {"i": "heading text", "ii": "...", ..., "viii": "..."}} '
        '(2-3 MORE headings than paragraphs, all with real text). '
        'Each question: {"id": N, "paragraph": "A", "answer": "iii", "explanation": "..."}'
    ),
    'matching_info': (
        'payload: {"paragraph_labels": ["A", "B", "C", "D", "E", "F"]} (matching the labelled paragraphs). '
        'Each question: {"id": N, "question": "the information to locate", "answer": "C", "explanation": "..."}'
    ),
    'matching_features': (
        'payload: {"features_bank": {"A": "person/category name", "B": "...", "C": "...", "D": "..."}} '
        '(all values MUST be real names/categories from the passage). '
        'Each question: {"id": N, "question": "statement to match", "answer": "B", "explanation": "..."}'
    ),
    'matching_sentence': (
        'payload: {"endings_bank": {"A": "sentence ending", "B": "...", ...}} '
        '(2-3 MORE endings than questions, all real text). '
        'Each question: {"id": N, "question": "sentence beginning", "answer": "D", "explanation": "..."}'
    ),
    'summary_completion': (
        'payload: {"summary_intro": "Complete the summary using the list of words, A-H.", '
        '"summary_text": "A one-paragraph summary of part of the passage with blanks formatted EXACTLY like '
        '(1) _____ ... (2) _____, numbered locally from (1)", '
        '"word_bank": {"A": "word", "B": "word", ..., "H": "word"}} (3-4 MORE words than blanks). '
        'Each question: {"id": N, "answer": "C", "explanation": "..."} (answer = word_bank letter for blank N)'
    ),
    'note_completion': (
        'payload: {"note_intro": "Complete the notes below.", '
        '"note_content": "structured notes with blanks formatted EXACTLY like (1) _____, numbered locally from (1)", '
        '"wordLimit": "NO MORE THAN TWO WORDS FROM THE PASSAGE"}. '
        'Each question: {"id": N, "answers": ["exact word(s) from passage"], "explanation": "..."}'
    ),
    'sentence_completion': (
        'payload: {"wordLimit": "NO MORE THAN TWO WORDS FROM THE PASSAGE"}. '
        'Each question: {"id": N, "question": "sentence with a _____ gap", '
        '"answers": ["exact word(s) from passage"], "explanation": "..."}'
    ),
    'short_answer': (
        'payload: {"wordLimit": "NO MORE THAN THREE WORDS AND/OR A NUMBER"}. '
        'Each question: {"id": N, "question": "wh-question about the passage", '
        '"answers": ["exact answer from passage"], "explanation": "..."}'
    ),
}


# ── 题型注册表 ─────────────────────────────────────────
# key = subtype 存到 AIQuestion; value = (template, needs_word_limit, needs_labelled_paragraphs)
READING_QUESTION_TYPES = {
    'multiple_choice':     (SKILL_READING_MCQ_TEMPLATE,               False, False),
    'true_false':          (SKILL_READING_TFNG_TEMPLATE,              False, False),
    'yes_no':              (SKILL_READING_YNNG_TEMPLATE,              False, False),
    'matching_headings':   (SKILL_READING_MATCHING_HEADINGS_TEMPLATE, False, True),
    'matching_info':       (SKILL_READING_MATCHING_INFO_TEMPLATE,     False, True),
    'matching_features':   (SKILL_READING_MATCHING_FEATURES_TEMPLATE, False, False),
    'matching_sentence':   (SKILL_READING_MATCHING_SENTENCE_TEMPLATE, False, False),
    'sentence_completion': (SKILL_READING_SENTENCE_COMPLETION_TEMPLATE, True, False),
    'summary_completion':  (SKILL_READING_SUMMARY_COMPLETION_TEMPLATE,  True, False),
    'note_completion':     (SKILL_READING_NOTE_COMPLETION_TEMPLATE,     True, False),
    'short_answer':        (SKILL_READING_SHORT_ANSWER_TEMPLATE,        True, False),
}


# ── 篇位风格 (真题难度递进: P1 事实 → P2 结构 → P3 观点) ──
READING_PASSAGE_FLAVOR = {
    1: (
        "Passage 1 (easiest): accessible, descriptive and FACTUAL — natural history, an invention, "
        "a place, a biography. Concrete details, dates and numbers throughout; NO authorial stance. "
        "A reader should be able to verify every statement against the text."
    ),
    2: (
        "Passage 2 (medium): discursive — presents several researchers' / stakeholders' perspectives "
        "on one topic, organised in clearly distinguishable paragraphs each with its own sub-focus "
        "(suits matching-type questions). Attribute views to named people or groups."
    ),
    3: (
        "Passage 3 (hardest): argumentative and more abstract — the WRITER'S OWN stance and hedged "
        "claims must be present throughout ('the author argues', concessions, counterarguments). "
        "Denser sentences and lower-frequency academic vocabulary than passages 1-2."
    ),
}


def get_paragraph_rule(needs_labelled: bool) -> str:
    return _PARAGRAPH_RULE_LABELLED if needs_labelled else _PARAGRAPH_RULE_PLAIN


def get_topic_instruction(topic_key: str) -> tuple[str, str]:
    """Return (topic_key_resolved, human_readable_instruction).

    'random' or unknown → pick nothing specific; let AI choose from the pool.
    """
    import random as _random
    if not topic_key or topic_key == 'random' or topic_key not in READING_TOPIC_POOL:
        # Pick one from the pool so we log a stable topic; don't leave AI unguided.
        topic_key = _random.choice(list(READING_TOPIC_POOL.keys()))
    return topic_key, READING_TOPIC_POOL[topic_key]
