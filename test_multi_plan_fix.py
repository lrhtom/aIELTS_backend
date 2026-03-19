#!/usr/bin/env python
"""
测试修复：同一单词在多个plan中时，review提交是否能成功
模拟实际问题场景：单词同时在全局(plan_id=0)和计划(plan_id=2)中
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from api.models import VocabFSRS, LearningPlan, LearningPlanEntry, Word
from rest_framework.test import APIRequestFactory
from api.vocab_views import VocabReviewView

User = get_user_model()

print('='*100)
print('🧪 测试：同一单词在多个plan中时的review处理')
print('='*100 + '\n')

# 设置
user = User.objects.create_user(
    username='multi_plan_test',
    email='multi@test.com',
    password='test123'
)

plan = LearningPlan.objects.create(
    user=user,
    name='Test Plan with Multi-Plan Words',
    daily_count=50
)

# 创建一个单词，同时在全局(plan_id=0)和计划(plan_id=plan.id)中
test_word = 'test_multi_plan_word'
Word.objects.get_or_create(word=test_word, defaults={'phonetic': ''})
LearningPlanEntry.objects.get_or_create(
    plan=plan, word=test_word, 
    defaults={'zh': '多计划测试词'}
)

# 创建两张卡片：一个全局，一个计划内
card_global = VocabFSRS.objects.create(
    user=user,
    word=test_word,
    zh='测试词(全局)',
    plan_id=0,
    state=0,
    stability=0.0,
    difficulty=5.0,
    due=timezone.now(),
)

card_plan = VocabFSRS.objects.create(
    user=user,
    word=test_word,
    zh='测试词(计划)',
    plan_id=plan.id,
    state=0,
    stability=0.0,
    difficulty=5.0,
    due=timezone.now(),
)

print(f'【测试设置】')
print(f'  用户: {user.username}')
print(f'  单词: "{test_word}"')
print(f'  全局卡片: plan_id=0')
print(f'  计划卡片: plan_id={plan.id}')
print()

# 测试场景
factory = APIRequestFactory()
view = VocabReviewView.as_view()

test_cases = [
    {
        'name': '场景1：请求plan_id=0（全局），应成功',
        'payload': {
            'word': test_word,
            'rating': 3,
            'client_last_review': None,
            'plan_id': 0,
        },
        'expect': 200,
    },
    {
        'name': f'场景2：请求plan_id={plan.id}（计划），应成功',
        'payload': {
            'word': test_word,
            'rating': 3,
            'client_last_review': None,
            'plan_id': plan.id,
        },
        'expect': 200,
    },
    {
        'name': '场景3：请求plan_id=999（不存在），但有备选方案，应使用备选',
        'payload': {
            'word': test_word,
            'rating': 3,
            'client_last_review': None,
            'plan_id': 999,  # 不存在的plan
        },
        'expect': 200,  # 应该使用备选方案而不是404
    },
]

print('【测试执行】')
print('-'*100)

results = []
for i, test in enumerate(test_cases, 1):
    print(f'{i}. {test["name"]}')
    
    request = factory.post('/api/vocab/review', test['payload'], format='json')
    request.user = user
    
    try:
        response = view(request)
        status_code = response.status_code
        
        if status_code == test['expect']:
            print(f'   ✅ PASS (status={status_code})')
            if status_code == 200:
                # 查看返回的plan_id
                returned_plan_id = response.data.get('card', {}).get('plan_id')
                print(f'      返回的plan_id: {returned_plan_id}')
            results.append(True)
        else:
            print(f'   ❌ FAIL (期望{test["expect"]}, 实际{status_code})')
            print(f'      响应: {response.data}')
            results.append(False)
    except Exception as e:
        print(f'   ❌ 异常: {e}')
        results.append(False)

print()

# 摘要
print('='*100)
print('📋 测试结果')
print('='*100)

passed = sum(results)
total = len(results)

if passed == total:
    print(f'✅ 全部通过 ({passed}/{total})')
    print('\n🎉 修复成功！同一单词在多个plan中时不再导致404')
else:
    print(f'❌ 部分失败 ({passed}/{total})')
    print('\n⚠️  修复不完整，还有问题需要解决')

# 清理
print('\n【清理测试数据】...', end=' ')
VocabFSRS.objects.filter(user=user, word=test_word).delete()
LearningPlanEntry.objects.filter(plan=plan, word=test_word).delete()
LearningPlan.objects.filter(id=plan.id).delete()
Word.objects.filter(word=test_word).delete()
user.delete()
print('✓')

print()
print('='*100)
