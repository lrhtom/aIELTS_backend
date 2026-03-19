#!/usr/bin/env python
"""
只扫描不清除 - 验证数据库状态
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.utils import timezone
from django.db.models import Q, Count
from api.models import (
    User, VocabFSRS, LearningPlan, LearningPlanEntry,
    Word, Notebook, NotebookWord, NotebookWordTag,
    VocabBook, WordBookMembership,
    Feedback, AIPrompt
)

print('\n' + '='*100)
print('📊 数据库状态检查')
print('='*100 + '\n')

# 基础统计
print('【基础数据量】')
print('-' * 100)
print(f'👤 用户总数: {User.objects.count()}')
print(f'📚 全局词库: {Word.objects.count()}')
print(f'📖 词书总数: {VocabBook.objects.count()}')
print(f'💾 FSRS卡片: {VocabFSRS.objects.count()}')
print(f'✏️  学习计划: {LearningPlan.objects.count()}')
print(f'📝 计划词条: {LearningPlanEntry.objects.count()}')
print(f'🗒️  生词本: {Notebook.objects.count()}')
print(f'📄 生词本条目: {NotebookWord.objects.count()}')
print()

# FSRS卡片状态分布
print('【FSRS卡片状态分布】')
print('-' * 100)
state_names = {0: 'NEW(新卡)', 1: 'LEARNING(学习中)', 2: 'REVIEW(复习)', 3: 'RELEARNING(重学)'}
for state in range(4):
    count = VocabFSRS.objects.filter(state=state).count()
    if count > 0:
        print(f'  {state_names[state]}: {count}')

# FSRS难度分布（检查是否有异常）
print('\n【FSRS难度值分布】')
print('-' * 100)
all_cards = VocabFSRS.objects.all()
valid_count = all_cards.filter(difficulty__gte=1, difficulty__lte=10).count()
invalid_count = all_cards.exclude(difficulty__gte=1, difficulty__lte=10).count()
print(f'  有效难度(1-10): {valid_count}')
print(f'  异常难度: {invalid_count}')

if invalid_count > 0:
    sample = all_cards.exclude(difficulty__gte=1, difficulty__lte=10).values('difficulty')[:5]
    print(f'  异常值示例: {[s["difficulty"] for s in sample]}')

# 学习计划统计
print('\n【学习计划统计】')
print('-' * 100)
plans = LearningPlan.objects.all()
anomalous_plans = plans.filter(Q(daily_count__lt=1) | Q(daily_count__gt=500))
print(f'  计划总数: {plans.count()}')
print(f'  配置异常: {anomalous_plans.count()}')

if anomalous_plans.count() > 0:
    for p in anomalous_plans:
        print(f'    - {p.name}: daily_count={p.daily_count}')

# 数据完整性检查
print('\n【数据完整性检查】')
print('-' * 100)
orphaned_fsrs = VocabFSRS.objects.exclude(user_id__in=User.objects.values_list('id', flat=True)).count()
orphaned_entries = LearningPlanEntry.objects.exclude(plan_id__in=LearningPlan.objects.values_list('id', flat=True)).count()

print(f'  孤立FSRS卡片: {orphaned_fsrs}')
print(f'  孤立计划条目: {orphaned_entries}')

# 数据库健康评分
print('\n【数据库健康评分】')
print('-' * 100)
health_score = 100
issues = []

if invalid_count > 0:
    health_score -= 10
    issues.append(f'⚠️  {invalid_count}条FSRS难度异常')

if anomalous_plans.count() > 0:
    health_score -= 5
    issues.append(f'⚠️  {anomalous_plans.count()}个计划配置异常')

if orphaned_fsrs + orphaned_entries > 0:
    health_score -= 10
    issues.append(f'⚠️  {orphaned_fsrs+orphaned_entries}条孤立数据')

if health_score == 100:
    print('🟢 数据库状态: 完美')
    print('✨ 没有发现任何异常数据')
else:
    print(f'🔴 数据库状态: 需要修复 (评分: {health_score}/100)')
    for issue in issues:
        print(f'   {issue}')

print('\n' + '='*100 + '\n')
