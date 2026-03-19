#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import VocabFSRS, LearningPlan, LearningPlanEntry
from django.utils import timezone
from django.db.models import Count, Q

now = timezone.now()
today = now.date()
start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

print(f'当前时间: {now}')
print(f'今天日期: {today}')
print()

# 获取所有计划
plans = LearningPlan.objects.all().values_list('id', 'name', 'daily_count', 'user_id')

print('='*100)
print('📋 各计划的学习队列分析:')
print('='*100)

for plan_id, plan_name, daily_count, user_id in plans:
    print(f'\n✓ 计划: {plan_name} (ID={plan_id}) | 每日配额: {daily_count}词')
    print('-'*100)
    
    # 获取计划内所有词汇
    all_cards = list(VocabFSRS.objects.filter(
        plan_id=plan_id
    ))
    
    if not all_cards:
        print('  （暂无卡片）')
        continue
    
    total = len(all_cards)
    
    # 统计已学过的词数
    studied_today = sum(
        1 for c in all_cards
        if c.last_review is not None and c.last_review.date() == today
    )
    
    # 分类统计
    due_cards = [c for c in all_cards if c.state != 0 and c.due <= now]
    carryover_cards = [
        c for c in all_cards
        if c.state in (1, 3)
        and c.due > now
        and c.last_review is not None
        and c.last_review >= start_of_today
    ]
    new_cards = [c for c in all_cards if c.state == 0]
    pending_cards = [
        c for c in all_cards
        if c.state != 0
        and c.due > now
        and (c.last_review is None or c.last_review < start_of_today)
    ]
    
    session_total = len(due_cards) + len(carryover_cards) + min(len(new_cards), max(0, daily_count - studied_today))
    
    remaining_today = max(0, daily_count - studied_today)
    will_add_new = min(len(new_cards), remaining_today) if remaining_today > 0 else 0
    
    print(f'  📊 卡片分布:')
    print(f'     总卡片数:           {total}')
    print(f'     已到期(DUE):        {len(due_cards)}  ← ⚠️ 无限制（优先级1）')
    print(f'     进行中重复(CARRYOVER): {len(carryover_cards)}  ← ⚠️ 无限制（优先级2）')
    print(f'     全新卡片(NEW):      {len(new_cards)} (将添加 {will_add_new})')
    print(f'     等待复习(PENDING):  {len(pending_cards)}')
    
    print(f'\n  ⏱️  今日情况:')
    print(f'     每日学习目标:       {daily_count}词')
    print(f'     已学词数:          {studied_today}')
    print(f'     剩余配额:          {remaining_today}')
    
    print(f'\n  🎯 本次session队列:')
    print(f'     = DUE({len(due_cards)}) + CARRYOVER({len(carryover_cards)}) + NEW({will_add_new})')
    print(f'     = {session_total} 词')
    
    if session_total > daily_count:
        print(f'\n  ⚠️  ⚠️  ⚠️  WARNING: 队列词汇({session_total}) > 每日目标({daily_count})！')
        print(f'     超额: {session_total - daily_count} 词')
        print(f'     原因: DUE和CARRYOVER不受daily_count限制')
    else:
        print(f'\n  ✓ 队列词汇({session_total}) <= 每日目标({daily_count})')

print()
print('='*100)
print('📌 关键结论:')
print('='*100)
print('''
DUE_CARDS 和 CARRYOVER_CARDS 不受 daily_count 限制，原因：
  1. DUE_CARDS：已到期，必须立即复习（优先级最高）
  2. CARRYOVER_CARDS：今天内已经答过的，不能丢弃或怠慢

因此，完全可能出现"队列词汇 > 每日目标"的情况！

例如：
  - daily_count = 20
  - due_cards = 15 (昨天没复习)
  - carryover_cards = 10 (今天内答过，要立即重复)
  - new_cards = 5 (新词)
  → 总队列 = 15 + 10 + 5 = 30 词 > 20词目标！

这是正常的，因为已到期和进行中的卡片优先级更高。
''')
