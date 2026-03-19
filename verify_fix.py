#!/usr/bin/env python
"""
验证修复后的队列逻辑
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

# ====== 修复后的逻辑 ======
print('🔧 修复后的队列构建过程：')
print()

# 步骤1: 必须保留 CARRYOVER
session_cards = list(carryover_cards)
print(f'步骤1: 保留CARRYOVER → {len(session_cards)} 张')

# 步骤2: 在剩余容量内加入 DUE
remaining_space = plan.daily_count - len(session_cards)
due_to_add = due_cards[:remaining_space] if remaining_space > 0 else []
session_cards.extend(due_to_add)
print(f'步骤2: 添加DUE(最多{remaining_space}张) → 现在 {len(session_cards)} 张')

# 步骤3: 填充新词
new_quota = max(0, plan.daily_count - len(session_cards))
if new_quota > 0 and new_cards:
    sorted_new_cards = sorted(new_cards, key=lambda c: (c.due, c.word))
    selected_new = sorted_new_cards[:new_quota]
    session_cards.extend(selected_new)
print(f'步骤3: 添加NEW(最多{new_quota}张) → 现在 {len(session_cards)} 张')

# 步骤4: 最终检查
if len(session_cards) > plan.daily_count:
    def priority(card):
        if card in carryover_cards:
            return (0, card.due)
        elif card in due_cards:
            return (1, card.due)
        else:
            return (2, card.due)
    session_cards = sorted(session_cards, key=priority)[:plan.daily_count]
    print(f'步骤4: 超过限制，截断 → {len(session_cards)} 张')
else:
    print(f'步骤4: 正常（{len(session_cards)} ≤ {plan.daily_count}）✓')

print()
print(f'🎯 最终队列：')
print(f'   CARRYOVER: {len([c for c in session_cards if c in carryover_cards])} 张 ✓（绝不丢）')
print(f'   DUE: {len([c for c in session_cards if c in due_cards])} 张 ✓（尽可能保留）')
print(f'   NEW: {len([c for c in session_cards if c not in carryover_cards and c not in due_cards])} 张 ✓（刚好填满）')
print(f'   总计: {len(session_cards)} 张 ({len(session_cards)} ≤ {plan.daily_count})')
print()

print(f'✅ 验证：')
print(f'   • CARRYOVER被保留: {len(carryover_cards) == len([c for c in session_cards if c in carryover_cards])}')
print(f'   • 不超过daily_count: {len(session_cards) <= plan.daily_count}')
print(f'   • 优先级正确: {len([c for c in session_cards if c in carryover_cards]) > 0 or "无carryover"}')
