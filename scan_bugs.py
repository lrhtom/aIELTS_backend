#!/usr/bin/env python
"""
扫描新的队列构建逻辑可能造成的 bugs
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

print('🔍 扫描新队列逻辑可能的 BUGS')
print('='*100)
print()

# 测试所有计划
plans = LearningPlan.objects.all()

for plan in plans:
    user = plan.user
    entries = list(plan.entries.all())
    if not entries:
        continue
    
    word_zh_map = {e.word: e.zh for e in entries}
    all_cards = list(
        VocabFSRS.objects.filter(user=user, word__in=word_zh_map.keys(), plan_id=plan.pk)
    )
    
    studied_today = sum(
        1 for c in all_cards
        if c.last_review is not None and c.last_review.date() == today
    )
    
    due_cards = [c for c in all_cards if c.state != 0 and c.due <= now]
    carryover_cards = [
        c for c in all_cards
        if c.state in (1, 3)
        and c.due > now
        and c.last_review is not None
        and c.last_review >= start_of_today
    ]
    new_cards = [c for c in all_cards if c.state == 0]
    
    must_do = due_cards + carryover_cards
    remaining_quota = max(0, plan.daily_count - len(must_do))
    selected_new = min(len(new_cards), remaining_quota) if remaining_quota > 0 else 0
    session_total = len(must_do) + selected_new
    
    # ===== 开始扫描 BUG =====
    bugs = []
    
    print(f'📌 计划: {plan.name} (daily_count={plan.daily_count})')
    print(f'   总卡片: {len(all_cards)} | due: {len(due_cards)} | carry: {len(carryover_cards)} | new: {len(new_cards)}')
    print()
    
    # BUG 1: CARRYOVER 被完全丢弃
    if len(carryover_cards) > 0 and len(due_cards) >= plan.daily_count:
        bugs.append({
            'id': 'BUG-1',
            'severity': '🔴 严重',
            'title': 'CARRYOVER 卡片完全丢弃',
            'detail': f'due卡片({len(due_cards)}) >= daily_count({plan.daily_count}), carryover({len(carryover_cards)})无位置',
            'impact': '今天答过的进行中卡片(5-10分钟要复习)会被完全丢弃，用户会觉得"我刚答的题消失了"',
            'severity_num': 1,
        })
    
    # BUG 2: LEARNING/RELEARNING 间隔破坏
    learning_cards_in_carryover = sum(1 for c in carryover_cards if c.state == 1)
    relearning_cards_in_carryover = sum(1 for c in carryover_cards if c.state == 3)
    if (learning_cards_in_carryover + relearning_cards_in_carryover) > 0 and remaining_quota <= 0:
        bugs.append({
            'id': 'BUG-2',
            'severity': '🔴 严重',
            'title': '短期学习卡片被延迟',
            'detail': f'LEARNING({learning_cards_in_carryover}) + RELEARNING({relearning_cards_in_carryover})卡片因无位置被延迟',
            'impact': '破坏FSRS时间精确性，5分钟/10分钟的间隔变成明天，学习连贯性被破坏',
            'severity_num': 1,
        })
    
    # BUG 3: 极端情况 - DUE太多导致新词无法学
    if remaining_quota < 5 and len(new_cards) > 100:
        bugs.append({
            'id': 'BUG-3',
            'severity': '🟠 中度',
            'title': '新词学习停滞',
            'detail': f'due卡片太多({len(due_cards)})，只剩{remaining_quota}配额给{len(new_cards)}个新词',
            'impact': '用户每天只能学习很少新词，学习进度被已过期卡片阻塞',
            'severity_num': 2,
        })
    
    # BUG 4: MUST_DO 超过 daily_count 时的截断
    if len(must_do) > plan.daily_count:
        exceed = len(must_do) - plan.daily_count
        bugs.append({
            'id': 'BUG-4',
            'severity': '🔴 严重',
            'title': '队列截断导致DUE卡片丢失',
            'detail': f'must_do({len(must_do)}) > daily_count({plan.daily_count})，超出{exceed}张会被截断',
            'impact': '低优先级的DUE卡片会被截断，可能永远无法复习',
            'severity_num': 1,
        })
    
    # BUG 5: 新词排序无效（都是 S=0）
    new_with_stability = sum(1 for c in new_cards if c.stability != 0)
    if len(new_cards) > 10 and new_with_stability < len(new_cards) * 0.1:
        bugs.append({
            'id': 'BUG-5',
            'severity': '🟡 轻度',
            'title': '新词排序逻辑无效',
            'detail': f'new卡片中{len(new_cards) - new_with_stability}个稳定性为0，按S排序毫无意义',
            'impact': '新词排序没有实际效果，应按due时间或随机排序',
            'severity_num': 3,
        })
    
    # BUG 6: 统计数字与实际不符
    if len(due_cards) > plan.daily_count:
        bugs.append({
            'id': 'BUG-6',
            'severity': '🟠 中度',
            'title': '前端统计显示误导',
            'detail': f'返回stats.due={len(due_cards)}，但session只包含{min(len(due_cards), plan.daily_count)}张',
            'impact': '用户看到"60张要复习"，但session只有"58张"，数字不匹配导致困惑',
            'severity_num': 2,
        })
    
    # 输出 BUG
    if bugs:
        bugs.sort(key=lambda b: b['severity_num'])
        print(f'⚠️  发现 {len(bugs)} 个 BUG：')
        print()
        for i, bug in enumerate(bugs, 1):
            print(f'{i}. {bug["severity"]} {bug["id"]}: {bug["title"]}')
            print(f'   详情: {bug["detail"]}')
            print(f'   影响: {bug["impact"]}')
            print()
    else:
        print(f'✅ 没有发现问题')
        print()

print()
print('='*100)
print('📋 总体分析：')
print('='*100)
print('''
新的队列逻辑存在的核心问题：

【最严重的三个问题】

1️⃣ CARRYOVER_CARDS 被丢弃
   问题：if len(due_cards) >= daily_count，carryover没有位置
   后果：今天答过(5-10分钟要复习)的卡片会消失，用户困惑
   原因：DUE和CARRYOVER都是"必做"，不能互相挤压

2️⃣ 时间精确性被破坏
   问题：LEARNING(5分钟) 和 RELEARNING(10分钟) 被延迟到明天
   后果：FSRS算法的间隔计算失效，卡片永远停留在LEARNING状态
   
3️⃣ MUST_DO 可能超过 daily_count
   问题：extreme case: due_cards(95) + carryover_cards(20) = 115 > daily_count(100)
   后果：需要截断，哪些DUE卡片被丢？优先级如何定？

【改进策略】

新的优先级应该是：
  1. CARRYOVER_CARDS（绝对优先，今天答过必须保留）
  2. DUE_CARDS（已到期，优先级次高）  
  3. NEW_CARDS（新词，可以受daily_count限制）

建议公式：
  session = carryover + due + new
  其中：
    carryover: 无限制（不能丢弃）
    due: 无限制（FSRS要求）
    new: 受限制（min(new_cards, daily_count - len(carryover) - len(due)))
''')
