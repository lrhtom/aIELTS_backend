#!/usr/bin/env python
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import VocabFSRS
from django.utils import timezone

now = timezone.now()
print(f'当前时间: {now}')
print(f'当前服务器时区: UTC')
print()

# 查询下一个最近的 due 时间
next_cards = VocabFSRS.objects.filter(
    due__gt=now
).order_by('due')[:20]

if next_cards.exists():
    print('📅 接下来最近的20个要复习的单词:')
    print('=' * 100)
    
    for i, card in enumerate(next_cards, 1):
        time_diff = card.due - now
        hours = time_diff.total_seconds() / 3600
        days = time_diff.days
        
        if days > 0:
            time_str = f'{days}D {int((hours - days*24)):.1f}H'
        else:
            minutes = time_diff.total_seconds() / 60
            if minutes < 60:
                time_str = f'{int(minutes)}M'
            else:
                time_str = f'{hours:.1f}H'
        
        state_names = {0: 'NEW', 1: 'LEARNING', 2: 'REVIEW', 3: 'RELEARNING'}
        state_name = state_names.get(card.state, 'Unknown')
        
        print(f'{i:2d}. {card.word:20s} | {state_name:10s} | {time_str:12s} | S:{card.stability:6.2f} | D:{card.difficulty:5.2f} | Due: {card.due}')
    
    print()
    first_card = next_cards.first()
    time_diff = first_card.due - now
    hours = time_diff.total_seconds() / 3600
    days = time_diff.days
    
    print('🎯 ========== 最近的一张卡片 ==========')
    print(f'   英文单词:          {first_card.word}')
    print(f'   中文释义:          {first_card.zh}')
    print(f'   学习状态:          {state_names.get(first_card.state, "Unknown")}')
    print(f'   稳定性(S):         {first_card.stability:.2f}天')
    print(f'   难度(D):           {first_card.difficulty:.2f}')
    print(f'   已复习次数:        {first_card.reps}次')
    print(f'   遗忘次数:          {first_card.lapses}次')
    print(f'   下次复习时间:      {first_card.due} UTC')
    if days > 0:
        print(f'   ⏱️  还要等待:        {days}天 {int((hours - days*24)):.1f}小时')
    else:
        minutes = time_diff.total_seconds() / 60
        if minutes < 60:
            print(f'   ⏱️  还要等待:        {int(minutes)}分钟')
        else:
            print(f'   ⏱️  还要等待:        {hours:.1f}小时')
    print()
else:
    print('✓ 没有接下来的复习卡片（全部完成或还未安排）')
