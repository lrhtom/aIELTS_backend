#!/usr/bin/env python
"""
验证新的最小间隔设置（1天）
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.fsrs_utils import fsrs_schedule
from django.utils import timezone

now = timezone.now()

print('🔄 验证修改后的间隔逻辑')
print('='*100)
print()

test_cases = [
    {
        'name': '新卡片，评分Again(1)',
        'card': {'state': 0, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None},
        'rating': 1,
    },
    {
        'name': '新卡片，评分Hard(2)',
        'card': {'state': 0, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None},
        'rating': 2,
    },
    {
        'name': '新卡片，评分Good(3)',
        'card': {'state': 0, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None},
        'rating': 3,
    },
    {
        'name': '新卡片，评分Easy(4)',
        'card': {'state': 0, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None},
        'rating': 4,
    },
    {
        'name': 'LEARNING卡片，评分Again(1)',
        'card': {'state': 1, 'stability': 1.0, 'difficulty': 5.0, 'reps': 1, 'lapses': 0, 'last_review': (now - timezone.timedelta(hours=2)).isoformat()},
        'rating': 1,
    },
    {
        'name': 'LEARNING卡片，评分Good(3)',
        'card': {'state': 1, 'stability': 1.0, 'difficulty': 5.0, 'reps': 1, 'lapses': 0, 'last_review': (now - timezone.timedelta(hours=2)).isoformat()},
        'rating': 3,
    },
    {
        'name': 'LEARNING卡片，评分Easy(4)',
        'card': {'state': 1, 'stability': 1.0, 'difficulty': 5.0, 'reps': 1, 'lapses': 0, 'last_review': (now - timezone.timedelta(hours=2)).isoformat()},
        'rating': 4,
    },
    {
        'name': 'RELEARNING卡片，评分Hard(2)',
        'card': {'state': 3, 'stability': 0.5, 'difficulty': 8.0, 'reps': 5, 'lapses': 1, 'last_review': (now - timezone.timedelta(hours=1)).isoformat()},
        'rating': 2,
    },
]

for i, test in enumerate(test_cases, 1):
    result = fsrs_schedule(test['card'], test['rating'], now)
    
    time_diff = result['due'] - now
    days = time_diff.days
    hours = round(time_diff.total_seconds() / 3600)
    minutes = round(time_diff.total_seconds() / 60)
    
    state_names = {0: 'NEW', 1: 'LEARNING', 2: 'REVIEW', 3: 'RELEARNING'}
    state_name = state_names.get(result['state'], '?')
    
    print(f'{i}. {test["name"]}')
    print(f'   原始状态: {state_names.get(test["card"]["state"])} | 评分: {test["rating"]}')
    print(f'   新状态: {state_name}')
    print(f'   计划间隔: {result["scheduled_days"]} 天')
    
    if days == 1 and hours == 24:
        print(f'   ✓ 下次复习: 1天后（{hours}小时）')
    elif days == 0 and minutes > 0:
        print(f'   ⚠️  下次复习: {minutes}分钟后（未来会改为1天）')
    else:
        print(f'   下次复习: {days}天 {hours%24}小时')
    
    print(f'   稳定性S: {result["stability"]:.4f} | 难度D: {result["difficulty"]:.4f}')
    print()

print('='*100)
print('📋 总结：')
print('='*100)
print('''
修改内容：
  NEW 状态：
    • rating=1 (Again)   : 1分钟 → 1天
    • rating=2 (Hard)    : 5分钟 → 1天
    • rating=3 (Good)    : 10分钟 → 1天
    • rating=4 (Easy)    : 直接进REVIEW（保持不变）

  LEARNING / RELEARNING 状态：
    • rating=1 (Again)   : 5分钟 → 1天
    • rating=2 (Hard)    : 10分钟 → 1天
    • rating=3 (Good)    : 10分钟 → 1天
    • rating=4 (Easy)    : 毕业进REVIEW（保持不变）

效果：
  ✅ 最小复习间隔从"几分钟"变成"1天"
  ✅ 用户无法在同一天快速重复单个卡片
  ✅ 强制用户更多分散式学习，符合FSRS长期记忆理论
  ✅ 简化了实时推送/通知逻辑（不再需要秒级计时）
''')
