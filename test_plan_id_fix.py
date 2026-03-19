#!/usr/bin/env python
"""
测试 /api/vocab/review 端点的 plan_id 保持问题修复
验证：连续提交多个review，plan_id不会丢失导致404
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

import json
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.utils import timezone
from api.models import VocabFSRS, LearningPlan, LearningPlanEntry, Word

User = get_user_model()
client = APIClient()

print('='*100)
print('📝 测试: /api/vocab/review 的 plan_id 保持测试')
print('='*100)

# 1. 创建测试用户
print('\n【步骤1】创建测试用户...', end=' ')
test_user, created = User.objects.get_or_create(
    username='test_plan_id',
    defaults={'email': 'test_plan_id@test.com'}
)
test_user.set_password('password123')
test_user.save()
print(f'✓ (user_id={test_user.id})')

# 2. 创建测试计划
print('【步骤2】创建测试学习计划...', end=' ')
plan = LearningPlan.objects.create(
    user=test_user,
    name='Test Plan for Review',
    daily_count=50
)
print(f'✓ (plan_id={plan.id})')

# 3. 创建测试词汇
print('【步骤3】创建测试词汇...', end=' ')
test_words = [
    {'word': 'test_word_1', 'zh': '测试词1'},
    {'word': 'test_word_2', 'zh': '测试词2'},
    {'word': 'test_word_3', 'zh': '测试词3'},
]

for item in test_words:
    word_obj, _ = Word.objects.get_or_create(
        word=item['word'],
        defaults={'phonetic': ''}
    )
    LearningPlanEntry.objects.get_or_create(
        plan=plan,
        word=item['word'],
        defaults={'zh': item['zh']}
    )

print(f'✓ ({len(test_words)} words)')

# 4. 创建FSRS卡片
print('【步骤4】创建FSRS卡片...', end=' ')
cards = []
for item in test_words:
    card = VocabFSRS.objects.create(
        user=test_user,
        word=item['word'],
        zh=item['zh'],
        plan_id=plan.id,
        state=0,
        stability=0.0,
        difficulty=5.0,
        due=timezone.now(),
    )
    cards.append(card)
print(f'✓ ({len(cards)} cards)')

# 5. 生成JWT token
print('【步骤5】生成API认证token...', end=' ')
refresh = RefreshToken.for_user(test_user)
access_token = str(refresh.access_token)
client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
print('✓')

# 6. 测试连续review，检查plan_id是否保持
print('\n【步骤6】连续提交review测试...')
print('-'*100)

results = []
for i, card in enumerate(cards, 1):
    payload = {
        'word': card.word,
        'rating': 3,
        'client_last_review': None,
        'plan_id': plan.id,
    }
    
    print(f'  [{i}] 提交 word="{card.word}" plan_id={plan.id}...', end=' ')
    
    response = client.post(
        '/api/vocab/review',
        payload,
        format='json'
    )
    
    status_code = response.status_code
    result = {
        'iteration': i,
        'word': card.word,
        'sent_plan_id': plan.id,
        'status': status_code,
    }
    
    if status_code == 200:
        resp_data = response.data
        returned_card = resp_data.get('card', {})
        returned_plan_id = returned_card.get('plan_id')
        
        # 检查返回的plan_id是否正确
        if returned_plan_id == plan.id:
            result['returned_plan_id'] = returned_plan_id
            result['result'] = '✅ PASS'
            print(f'✓ (returned plan_id={returned_plan_id})')
        else:
            result['returned_plan_id'] = returned_plan_id
            result['result'] = f'❌ FAIL (返回plan_id={returned_plan_id})'
            print(f'❌ 返回plan_id={returned_plan_id}，期望{plan.id}')
    else:
        error_msg = response.data if hasattr(response, 'data') else str(response.content)
        result['result'] = f'❌ FAIL (status={status_code})'
        print(f'✗ {error_msg}')
    
    results.append(result)
    
    # 如果这次成功，用返回的卡片作为下次的输入
    if status_code == 200:
        returned_card = response.data.get('card', {})
        cards[i-1].last_review = returned_card.get('last_review')
        cards[i-1].plan_id = returned_card.get('plan_id', plan.id)

# 7. 汇总结果
print('\n' + '='*100)
print('📊 测试结果汇总')
print('='*100)

total = len(results)
passed = sum(1 for r in results if '✅' in r['result'])
failed = total - passed

print(f'\n总计: {total} 次请求')
print(f'✅ 通过: {passed}')
print(f'❌ 失败: {failed}')

if failed == 0:
    print('\n🎉 所有测试通过！plan_id 成功保持在圆形流程中。')
else:
    print(f'\n⚠️  有 {failed} 个测试失败：')
    for r in results:
        if '❌' in r['result']:
            print(f'  - [{r["iteration"]}] {r["word"]}: {r["result"]}')

# 8. 清理
print('\n【清理】...')
VocabFSRS.objects.filter(user=test_user, plan_id=plan.id).delete()
LearningPlanEntry.objects.filter(plan=plan).delete()
LearningPlan.objects.filter(id=plan.id).delete()
for item in test_words:
    Word.objects.filter(word=item['word']).delete()
User.objects.filter(id=test_user.id).delete()
print('✓ 测试数据已清理\n')

print('='*100)
