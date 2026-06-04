import sys
import re

file_path = "e:/code/web/work/aIELTS/backend/api/skills/writing/ai_teacher.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# First extract the vocab_guide from where it was injected
# It starts with 'SKILL_TASK2_VOCAB_GUIDE =' and ends right before 'SKILL_AI_TEACHER_PART2_USER'
match = re.search(r'(SKILL_TASK2_VOCAB_GUIDE = """[\s\S]*?""")', content)
if match:
    vocab_str = match.group(1)
    # Remove it from its current position
    content = content.replace(vocab_str, "")
    
    # Place it at the very top of the file
    content = vocab_str + "\n\n" + content.lstrip()
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed syntax order.")
else:
    print("Could not find SKILL_TASK2_VOCAB_GUIDE")
