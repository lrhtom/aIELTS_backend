import sys

file_path = "e:/code/web/work/aIELTS/backend/api/skills/writing/ai_teacher.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

vocab_guide = '''
SKILL_TASK2_VOCAB_GUIDE = """
=== PREFERRED VOCABULARY & SENTENCE STRUCTURES (BAND 6.0-6.5) ===
CRITICAL INSTRUCTION: When generating sentences and the full essay, you MUST STRICTLY use the following sentence structures and vocabulary replacements. This is crucial for maintaining a safe Band 6.0-6.5 level while avoiding repetition. 

1. INTRODUCTION (Use one of these depending on the topic)
- Opinion: It is sometimes argued that... I disagree with this view, because...
- Phenomenon: There is a common phenomenon that... From my perspective, this trend may...
- Causes & Attitude: Currently, [phenomenon]. This is mainly due to... I perceive it as a positive/negative development, because...

2. BODY PARAGRAPHS - TOPIC SENTENCES
- Support: ...may serve as a strong incentive to promote..., thereby...
- Oppose: ...can impede/hinder..., because... are more likely to...
- Causes: This is mainly due to / largely because...
- Consequences: If..., ...may..., thereby confronting a higher risk of...

3. BODY PARAGRAPHS - EXPLANATIONS & LOGIC
- Cause & Effect: Since/As..., ... may...
- Hypothetical: If..., people are more likely to..., as...
- Contrast: Compared with..., ...can..., since...
- Progression: Moreover, ...that are able to... may directly...
- Concession: Although..., there is a wide disparity in...
- Surface vs Reality: Outwardly, ...appears to..., but a closer look reveals...
- Scope Emphasis: This is particularly true among... where...

4. EXAMPLES
- For example, ... by introducing..., considering that...
- For instance, ... can..., and thus...

5. CONCLUSION
- Restate Position: In conclusion, while [concession], I believe that [position], because [reason].
- Condition: In conclusion, ... only if... / ... can... only when...
- Critical: In conclusion, ... is not suitable for... considering that... may create a vicious circle of...

6. LOGICAL CONNECTORS (MUST REPLACE BASIC WORDS)
- DO NOT USE "because" -> USE: since, as, due to, owing to, considering that, given that
- DO NOT USE "so" -> USE: therefore, thus, thereby, consequently, as a result
- DO NOT USE "but" -> USE: however, although, while, whereas, nevertheless
- DO NOT USE "and" -> USE: moreover, furthermore, in addition, additionally
- DO NOT USE "for example" repeatedly -> USE: for instance, such as, particularly, notably
- DO NOT USE "cause" -> USE: lead to, result in, contribute to, give rise to, incur

7. HIGH-FREQUENCY VOCABULARY REPLACEMENTS (MUST USE)
- important -> vital, essential, crucial, significant, fundamental
- solve -> address, tackle, alleviate, mitigate, cope with, resolve
- think -> argue, believe, perceive, maintain, hold the view
- many -> numerous, a wide range of, various, diverse, a host of
- people -> individuals, citizens, the public, residents, the masses
- problem -> issue, challenge, obstacle, difficulty, concern
- good -> beneficial, positive, advantageous, favorable, desirable
- bad -> detrimental, adverse, harmful, negative, undesirable
- big -> considerable, substantial, enormous, significant
- give -> provide, offer, supply, endow...with
- use -> utilize, employ, leverage, make use of, take advantage of
- can -> be able to, be capable of, have the ability to
- help -> facilitate, promote, contribute to, be conducive to
- more and more -> increasingly, growing, rising, mounting
- be caused by -> stem from, arise from, be attributed to

8. TOPIC-SPECIFIC ARGUMENT VOCABULARY
- Agree/Disagree: agree with, support, advocate, be in favor of, endorse / disagree with, oppose, object to, be against, challenge / From my perspective, In my view, I am convinced that / impractical, unfeasible, unrealistic, unsustainable
- Causes & Solutions: the leading cause of, the root of, stem from / factor, element, contributor, driving force / measure, approach, strategy, initiative / authorities ought to, policymakers need to
- Advantages & Disadvantages: benefit, merit, positive aspect, strength, upside / drawback, demerit, negative aspect, weakness, downside / on the one hand... on the other hand... / ...outweigh...
- Discuss Both Views: Some people argue that... It is believed that... / However, others contend that... Opponents argue that... / In my opinion, both views have merit, but...

9. CRITICAL EXAM RULES
- EVERY sentence must use a complex structure (e.g., if / because / although / which / who).
- NEVER repeat the same keyword within the same paragraph; ALWAYS use synonyms.
"""
'''

content = content.replace('SKILL_AI_TEACHER_PART2_USER =', vocab_guide + '\n\nSKILL_AI_TEACHER_PART2_USER =')

content = content.replace(
    '    "bad_closing_en": "...", "bad_closing_zh": "..."\n  }\n}"""',
    '    "bad_closing_en": "...", "bad_closing_zh": "..."\n  }\n}""" + SKILL_TASK2_VOCAB_GUIDE'
)

content = content.replace(
    '    {"section_en": "Introduction", "section_zh": "引言段", "key_points_en": "...", "key_points_zh": "..."}\n  ]\n}"""',
    '    {"section_en": "Introduction", "section_zh": "引言段", "key_points_en": "...", "key_points_zh": "..."}\n  ]\n}""" + SKILL_TASK2_VOCAB_GUIDE'
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
