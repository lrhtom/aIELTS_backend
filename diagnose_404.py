#!/usr/bin/env python
"""
诊断脚本：追踪 404 问题的根本原因
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import VocabFSRS, LearningPlan, LearningPlanEntry, Word, User
from django.db.models import Q

print('='*100)
print('🔍 诊断: /api/vocab/review 404问题')
print('='*100 + '\n')

# 获取当前有数据的用户
user_count = User.objects.count()
if user_count == 0:
    print('❌ 数据库中没有用户，无法诊断')
    exit(1)

user = User.objects.first()
print(f'【用户信息】')
print(f'  用户: {user.username}')
print(f'  FSRS卡片总数: {VocabFSRS.objects.filter(user=user).count()}')
print()

# 检查FSRS卡片的plan_id分布
print('【FSRS卡片 plan_id 分布】')
print('-'*100)

cards_by_plan = {}
for card in VocabFSRS.objects.filter(user=user):
    plan_id = card.plan_id
    if plan_id not in cards_by_plan:
        cards_by_plan[plan_id] = []
    cards_by_plan[plan_id].append(card)

for plan_id in sorted(cards_by_plan.keys()):
    cards = cards_by_plan[plan_id]
    if plan_id == 0:
        print(f'  全局卡片 (plan_id=0): {len(cards)} 张')
    else:
        plan = LearningPlan.objects.filter(id=plan_id).first()
        if plan:
            print(f'  计划 "{plan.name}" (plan_id={plan_id}): {len(cards)} 张')
        else:
            print(f'  ⚠️  孤立计划 (plan_id={plan_id}): {len(cards)} 张 - 计划已删除！')
    
    # 显示前3张卡片
    for card in cards[:3]:
        print(f'    - {card.word} (state={card.state}, due={card.due.strftime("%Y-%m-%d %H:%M")})')

print()

# 检查前后端可能的问题
print('【潜在问题分析】')
print('-'*100)

# 问题1: 孤立的FSRS卡片（所属计划已删除）
orphaned = 0
for plan_id, cards in cards_by_plan.items():
    if plan_id > 0:
        if not LearningPlan.objects.filter(id=plan_id).exists():
            orphaned += len(cards)
            print(f'  ⚠️  发现 {len(cards)} 张孤立卡片 (plan_id={plan_id})')

if orphaned == 0:
    print(f'  ✅ 没有孤立卡片')

# 问题2: 同一单词在多个计划中
print()
word_plan_map = {}
for card in VocabFSRS.objects.filter(user=user):
    if card.word not in word_plan_map:
        word_plan_map[card.word] = []
    word_plan_map[card.word].append(card.plan_id)

multi_plan_words = {w: plans for w, plans in word_plan_map.items() if len(plans) > 1}
if multi_plan_words:
    print(f'  ⚠️  {len(multi_plan_words)} 个单词出现在多个计划中')
    for word, plans in list(multi_plan_words.items())[:3]:
        print(f'    - "{word}" 在 plan_id={plans}')
else:
    print(f'  ✅ 没有单词重复出现在多个计划')

print()

# 问题3: plan_id 字段返回情况
print('【字段返回检查】')
print('-'*100)

from api.vocab_views import _card_to_dict

sample_cards = list(VocabFSRS.objects.filter(user=user)[:3])
for card in sample_cards:
    word_obj = Word.objects.filter(word=card.word).first()
    result = _card_to_dict(card, word_obj)
    
    has_plan_id = 'plan_id' in result
    plan_id_value = result.get('plan_id', 'MISSING')
    
    status = '✅' if has_plan_id and plan_id_value == card.plan_id else '❌'
    print(f'  {status} {card.word:20} plan_id字段: {plan_id_value}')

print()

# 诊断建议
print('【诊断建议】')
print('-'*100)

issues = []

if orphaned > 0:
    issues.append(f'{orphaned}张孤立卡片 - 建议运行scan_and_clean_db.py清理')

if multi_plan_words:
    issues.append('同一单词在多个计划中 - 可能导致查询混乱')

if not issues:
    print('  目前未发现明显的数据问题')
else:
    print('  发现以下问题：')
    for i, issue in enumerate(issues, 1):
        print(f'    {i}. {issue}')

print()
print('【下一步诊断步骤】')
print('-'*100)
print('''
请提供以下信息以进一步诊断：

1. 404发生的场景
   - 是在"全局学习"还是"计划学习"中？
   - 分别提交几个单词后才出现404？

2. 浏览器console错误
   - 打开DevTools → Console标签
   - 提交review时是否有错误日志？

3. 服务器日志
   - 查看 python manage.py runserver 的输出
   - 记录发生404时前后的完整请求/响应

4. 测试命令（我可以运行）
   - 用户名、密码
   - 或者具体的学习计划ID
   - 让我准确复现404
''')

print('='*100)
