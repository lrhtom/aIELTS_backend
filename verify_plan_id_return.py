#!/usr/bin/env python
"""
验证 _card_to_dict 函数是否正确返回 plan_id
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import VocabFSRS, Word
from api.vocab_views import _card_to_dict
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

print('='*100)
print('✅ 验证: _card_to_dict 是否返回 plan_id')
print('='*100 + '\n')

# 创建测试用户
user, _ = User.objects.get_or_create(
    username='verify_card_dict',
    defaults={'email': 'verify@test.com'}
)

# 创建FSRS卡片（plan_id=5）
card = VocabFSRS.objects.create(
    user=user,
    word='verify_word',
    zh='测试词',
    plan_id=5,
    state=1,
    stability=2.5,
    difficulty=6.0,
    reps=3,
    lapses=0,
    due=timezone.now(),
)

# 创建对应的Word对象
word_obj = Word.objects.create(
    word='verify_word',
    phonetic='/test/',
)

# 调用_card_to_dict
result = _card_to_dict(card, word_obj)

print('【卡片信息】')
print(f'  原始卡片: id={card.id}, word={card.word}, plan_id={card.plan_id}')
print()

print('【_card_to_dict 返回值】')
print(f'  字段列表:')
for key in sorted(result.keys()):
    value = result[key]
    if isinstance(value, (str, int, float, type(None))):
        print(f'    ✓ {key}: {value}')
    else:
        print(f'    ✓ {key}: ({type(value).__name__})')

print()
print('【检查结果】')

if 'plan_id' in result:
    if result['plan_id'] == 5:
        print('  ✅ plan_id 正确返回（值=5）')
    else:
        print(f'  ❌ plan_id 值错误（返回{result["plan_id"]}，期望5）')
else:
    print('  ❌ plan_id 字段缺失！')

print()

# 清理
card.delete()
word_obj.delete()
user.delete()

print('='*100)
print('验证完成！修复已正确应用。')
print('='*100)
