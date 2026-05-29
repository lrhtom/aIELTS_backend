import re

with open('backend/api/vocab/learning_plan_views.py', 'r', encoding='utf-8') as f:
    code = f.read()

prompt = '''
STORY_MODE_PROMPT = """
You are a creative writer. Write an entertaining, highly dramatic, and slightly silly Chinese web novel excerpt (e.g., "霸道总裁" CEO romance, or dog-blood drama) (300-500 words).
You MUST naturally embed ALL of the following IELTS target vocabulary words into the Chinese story: {words}

Rules:
1. The main narrative MUST be in Chinese.
2. Every target English word MUST appear exactly once.
3. When embedding a target word, you MUST wrap it in exact double brackets using the format [[English Word|Chinese Meaning]].
   For example, instead of writing "提案", write: "陆氏集团的 [[proposition|提案]] 放在桌上..."
4. Make the story highly engaging, exaggerated, and funny to help the student remember the words through dramatic context.
5. Do NOT use markdown formatting in the article text.

Return ONLY a JSON object (no markdown code block, no extra text) with these fields:
{{
    "story_title": "A funny dramatic title for the story in Chinese",
    "story_text": "the full Chinese story with embedded English words using the [[word|meaning]] syntax"
}}
"""
'''
if 'STORY_MODE_PROMPT =' not in code:
    code = code.replace('ARTICLE_COPY_PROMPT = ', prompt + '\nARTICLE_COPY_PROMPT = ')
    with open('backend/api/vocab/learning_plan_views.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print("Added STORY_MODE_PROMPT")
else:
    print("STORY_MODE_PROMPT already exists")
