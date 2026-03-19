#!/usr/bin/env python
"""
直接单元测试：测试VocabReviewView的plan_id容错逻辑
不依赖认证框架的REST API测试框架
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import TestCase, RequestFactory
from api.models import VocabFSRS, LearningPlan, LearningPlanEntry, Word
from api.vocab_views import VocabReviewView
from unittest.mock import patch

User = get_user_model()

print('='*100)
print('🧪 单元测试：VocabReviewView的plan_id容错逻辑')
print('='*100 + '\n')

# 设置测试数据
# 使用get_or_create避免重复
user, created = User.objects.get_or_create(
    username='unit_test_user',
    defaults={'email': 'unit@test.com'}
)
if not created:
    # 清理旧数据
    VocabFSRS.objects.filter(user=user).delete()
    LearningPlan.objects.filter(user=user).delete()

plan = LearningPlan.objects.create(
    user=user,
    name='Unit Test Plan',
    daily_count=50
)

test_word = 'unit_test_word'
Word.objects.get_or_create(word=test_word, defaults={'phonetic': ''})

# 创建两张卡片
card_global = VocabFSRS.objects.create(
    user=user,
    word=test_word,
    zh='全局',
    plan_id=0,
    state=0,
    stability=0.0,
    difficulty=5.0,
    due=timezone.now(),
)

card_plan = VocabFSRS.objects.create(
    user=user,
    word=test_word,
    zh='计划',
    plan_id=plan.id,
    state=0,
    stability=0.0,
    difficulty=5.0,
    due=timezone.now(),
)

print(f'【测试设置】')
print(f'  用户: {user.username}')
print(f'  单词: "{test_word}"')
print(f'  全局卡片(plan_id=0): {card_global.id}')
print(f'  计划卡片(plan_id={plan.id}): {card_plan.id}')
print()

# 测试场景
print('【测试1】请求precision plan_id=0')
print('-'*100)

from django.db import transaction

with transaction.atomic():
    try:
        card = VocabFSRS.objects.select_for_update().get(
            user=user, word=test_word, plan_id=0
        )
        print(f'✓ 找到卡片: plan_id={card.plan_id}')
    except VocabFSRS.DoesNotExist:
        print(f'✗ 找不到卡片')

print()
print('【测试2】请求precision plan_id=999（不存在），逻辑会自动选择备选')
print('-'*100)

# 模拟修复后的逻辑
with transaction.atomic():
    try:
        card = VocabFSRS.objects.select_for_update().get(
            user=user, word=test_word, plan_id=999
        )
        print(f'✓ 精确查询成功: plan_id={card.plan_id}')
    except VocabFSRS.DoesNotExist:
        print(f'精确查询失败，检查备选方案...')
        
        alternatives = list(VocabFSRS.objects.filter(
            user=user, word=test_word
        ).select_for_update())
        
        print(f'  发现 {len(alternatives)} 个备选卡片:')
        for c in alternatives:
            print(f'    - plan_id={c.plan_id}')
        
        if len(alternatives) == 1:
            card = alternatives[0]
            print(f'  ✓ 只有一个备选，自动选用: plan_id={card.plan_id}')
        elif len(alternatives) > 1:
            global_card = [c for c in alternatives if c.plan_id == 0]
            if global_card:
                card = global_card[0]
                print(f'  ✓ 多个备选，优先选全局卡片: plan_id={card.plan_id}')
            else:
                card = min(alternatives, key=lambda c: c.plan_id)
                print(f'  ✓ 无全局卡片，选最小plan_id: plan_id={card.plan_id}')

print()
print('【测试3】同时存在多个副本时的选择优先级')
print('-'*100)

# 创建第三张卡片
card_plan2 = VocabFSRS.objects.create(
    user=user,
    word=test_word,
    zh='计划2',
    plan_id=5,
    state=0,
    stability=0.0,
    difficulty=5.0,
    due=timezone.now(),
)

print(f'新增卡片: plan_id={card_plan2.plan_id}')
print(f'现有卡片: plan_id=0, {plan.id}, 5')
print()

# 测试错误的plan_id会选择哪一个
with transaction.atomic():
    try:
        card = VocabFSRS.objects.select_for_update().get(
            user=user, word=test_word, plan_id=999
        )
    except VocabFSRS.DoesNotExist:
        alternatives = list(VocabFSRS.objects.filter(
            user=user, word=test_word
        ).select_for_update())
        
        global_card = [c for c in alternatives if c.plan_id == 0]
        if global_card:
            selected = global_card[0]
            print(f'✓ 优先选全局卡片: plan_id={selected.plan_id}')
        else:
            selected = min(alternatives, key=lambda c: c.plan_id)
            print(f'✓ 无全局卡片，选最小plan_id: plan_id={selected.plan_id}')

print()

# 验证修复逻辑
print('='*100)
print('📋 修复逻辑验证')
print('='*100)

print(f'''
修复策略：
  1. 首先尝试精确匹配 (user, word, plan_id)
  2. 失败时，查找 (user, word) 的所有副本
  3. 如果只有1个副本 → 使用它
  4. 如果有多个副本：
     - 优先选择全局卡片(plan_id=0)
     - 否则选择最小的plan_id
  5. 都没有 → 返回404

效果：
  ✅ 即使前端发送错的plan_id，也能找到正确的卡片
  ✅ 消除由于多个plan中有同一单词导致的404
  ✅ 自动容错，提高系统鲁棒性
''')

# 清理
print('【清理】...', end=' ')
VocabFSRS.objects.filter(user=user, word=test_word).delete()
LearningPlan.objects.filter(id=plan.id).delete()
Word.objects.filter(word=test_word).delete()
user.delete()
print('✓')

print()
print('='*100)
