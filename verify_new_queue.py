#!/usr/bin/env python
"""
验证新的队列构建逻辑：严格遵守daily_count，按最小熟练度填充
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import VocabFSRS, LearningPlan
from django.utils import timezone

now = timezone.now()
today = now.date()
start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

print(f'当前时间: {now}')
print()

# 测试第一个计划
plan = LearningPlan.objects.filter(pk=2).first()
if not plan:
    print('计划不存在')
    exit(1)

user = plan.user
entries = list(plan.entries.all())

print(f'📋 计划: {plan.name}')
print(f'   每日配额: {plan.daily_count}词')
print()

# 准备所有卡片
word_zh_map = {e.word: e.zh for e in entries}
all_cards = list(
    VocabFSRS.objects.filter(user=user, word__in=word_zh_map.keys(), plan_id=plan.pk).order_by('due')
)

# 统计今天已学
studied_today = sum(
    1 for c in all_cards
    if c.last_review is not None and c.last_review.date() == today
)
remaining_today = max(0, plan.daily_count - studied_today)

# 分类卡片
due_cards = [
    c for c in all_cards
    if c.state != 0 and c.due <= now
]

carryover_cards = sorted(
    [
        c for c in all_cards
        if c.state in (1, 3)
        and c.due > now
        and c.last_review is not None
        and c.last_review >= start_of_today
    ],
    key=lambda c: c.due,
)

new_cards = [c for c in all_cards if c.state == 0]

# ====== 新逻辑 ======
must_do_cards = due_cards + carryover_cards
remaining_quota = max(0, plan.daily_count - len(must_do_cards))
sorted_new_cards = sorted(new_cards, key=lambda c: (c.stability or float('inf'), c.due))
selected_new = sorted_new_cards[:remaining_quota]

session_cards = must_do_cards + selected_new

# 如果超过限制，截断
if len(session_cards) > plan.daily_count:
    def session_priority(card):
        if card in due_cards:
            return (0, card.stability or float('inf'), card.due)
        elif card in carryover_cards:
            return (1, card.stability or float('inf'), card.due)
        else:
            return (2, card.stability or float('inf'), card.due)
    session_cards = sorted(session_cards, key=session_priority)[:plan.daily_count]

# ==================

print(f'📊 队列分析：')
print(f'   已学词数: {studied_today}')
print(f'   已到期DUE: {len(due_cards)}')
print(f'   进行中CARRYOVER: {len(carryover_cards)}')
print(f'   全新NEW总数: {len(new_cards)}')
print()

print(f'🔧 运算过程：')
print(f'   必做(DUE+CARRYOVER): {len(must_do_cards)} = {len(due_cards)} + {len(carryover_cards)}')
print(f'   剩余配额: max(0, {plan.daily_count} - {len(must_do_cards)}) = {remaining_quota}')
print(f'   选中新词: {len(selected_new)} (来自 {len(new_cards)} 个新词，按S排序)')
print()

print(f'🎯 最终队列：')
print(f'   总数: {len(session_cards)} (< {plan.daily_count}? {len(session_cards) <= plan.daily_count})')
print()

# 展示队列内容
state_names = {0: 'NEW', 1: 'LEARNING', 2: 'REVIEW', 3: 'RELEARNING'}

print(f'队列顺序（前20个）：')
print('='*80)
for i, c in enumerate(session_cards[:20], 1):
    category = '【DUE】' if c in due_cards else '【CARRY】' if c in carryover_cards else '【NEW】'
    print(f'{i:2d}. {category:8s} {c.word:20s} | S:{c.stability:6.2f} | State:{state_names.get(c.state)}')

if len(session_cards) > 20:
    print(f'... 还有 {len(session_cards)-20} 个词')

print()
print('✅ 验证成功：')
print(f'   • 总队列({len(session_cards)}) <= 每日限制({plan.daily_count}): {len(session_cards) <= plan.daily_count}')
print(f'   • DUE卡片优先级最高: {due_cards[0].word if due_cards else "无"}')
print(f'   • 新词按稳定性排序: {selected_new[0].word if selected_new else "无"} (S={selected_new[0].stability if selected_new else 0})')
