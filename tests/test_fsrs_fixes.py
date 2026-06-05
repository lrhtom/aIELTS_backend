#!/usr/bin/env python
"""
FSRS 修复验证测试脚本
验证 #2 elapsed_days 精度、#3 Relearning 对齐、#4 新评分策略对 difficulty 的影响
"""
import os, sys, math
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 添加 backend 目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import django
django.setup()

from datetime import datetime, timedelta, timezone
from api.fsrs_utils import fsrs_schedule, NEW, LEARNING, REVIEW, RELEARNING

print('=' * 80)
print('🧪 FSRS 修复验证测试')
print('=' * 80)

now = datetime.now(timezone.utc)
passed = 0
failed = 0

def check(desc: str, condition: bool, detail: str = ''):
    global passed, failed
    if condition:
        passed += 1
        print(f'  ✅ {desc}')
    else:
        failed += 1
        print(f'  ❌ {desc}')
    if detail:
        print(f'     → {detail}')


# ── Test 1: elapsed_days 返回浮点数 ──
print('\n【Test 1】elapsed_days 精度：间隔 < 1 天时不为 0')
card = {
    'state': REVIEW, 'stability': 10.0, 'difficulty': 5.0,
    'reps': 5, 'lapses': 0,
    'last_review': (now - timedelta(hours=6)).isoformat(),
}
result = fsrs_schedule(card, 3, now)
check(
    'elapsed_days 应约等于 0.25（6 小时）',
    0.2 < result['elapsed_days'] < 0.3,
    f"actual = {result['elapsed_days']}"
)
check(
    'elapsed_days 不是 0',
    result['elapsed_days'] != 0,
)


# ── Test 2: 新卡间隔仍为 1 天（保持 #1 不变）──
print('\n【Test 2】新卡间隔保持 1 天')
for rating in [1, 2, 3]:
    card = {'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None}
    result = fsrs_schedule(card, rating, now)
    expected_due = now + timedelta(days=1)
    diff_seconds = abs((result['due'] - expected_due).total_seconds())
    check(
        f'rating={rating} → due = 明天',
        diff_seconds < 5,
        f"due={result['due'].isoformat()}, sched_days={result['scheduled_days']}"
    )

card = {'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None}
result = fsrs_schedule(card, 4, now)
check(
    'rating=4 → 直接进入 REVIEW',
    result['state'] == REVIEW,
    f"state={result['state']}, sched_days={result['scheduled_days']}"
)


# ── Test 3: Review Again → Relearning，due = 5 分钟后 ──
print('\n【Test 3】Review Again → Relearning 5 分钟')
card = {
    'state': REVIEW, 'stability': 10.0, 'difficulty': 5.0,
    'reps': 3, 'lapses': 0,
    'last_review': (now - timedelta(days=3)).isoformat(),
}
result = fsrs_schedule(card, 1, now)
check(
    'state = RELEARNING(3)',
    result['state'] == RELEARNING,
)
expected_due = now + timedelta(minutes=5)
diff_seconds = abs((result['due'] - expected_due).total_seconds())
check(
    'due ≈ 5 分钟后',
    diff_seconds < 5,
    f"due={result['due'].isoformat()}"
)
check(
    'sched_days = 0',
    result['scheduled_days'] == 0,
)
check(
    'lapses + 1',
    result['lapses'] == 1,
)


# ── Test 4: 新评分策略验证——连续 Good(3) 不应推高 difficulty ──
print('\n【Test 4】4选1/写英文 新评分策略：Good(3) 不推高 difficulty')
card = {'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None}

# 模拟 4选1 模式：答对未毕业 → 提交 rating=3（Good）
# 旧策略提交 rating=1，导致 difficulty 飙升
r1 = fsrs_schedule(card, 3, now)
initial_difficulty = r1['difficulty']

# 第二次：基于第一次结果继续 Good
card2 = {
    'state': r1['state'], 'stability': r1['stability'], 'difficulty': r1['difficulty'],
    'reps': r1['reps'], 'lapses': r1['lapses'],
    'last_review': now.isoformat(),
}
r2 = fsrs_schedule(card2, 3, now + timedelta(days=1))

check(
    'Good(3) 评分 difficulty 不升高',
    r2['difficulty'] <= initial_difficulty + 0.5,
    f"first={initial_difficulty:.2f}, second={r2['difficulty']:.2f}"
)

# 对比旧策略（rating=1）
r1_old = fsrs_schedule({'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0, 'last_review': None}, 1, now)
card2_old = {
    'state': r1_old['state'], 'stability': r1_old['stability'], 'difficulty': r1_old['difficulty'],
    'reps': r1_old['reps'], 'lapses': r1_old['lapses'],
    'last_review': now.isoformat(),
}
r2_old = fsrs_schedule(card2_old, 1, now + timedelta(days=1))

check(
    '旧策略 Again(1) difficulty 显著更高',
    r2_old['difficulty'] > r2['difficulty'] + 0.5,
    f"Good策略={r2['difficulty']:.2f}, Again策略={r2_old['difficulty']:.2f}, 差={r2_old['difficulty'] - r2['difficulty']:.2f}"
)


# ── 总结 ──
print()
print('=' * 80)
total = passed + failed
print(f'总计：{total} 个测试，✅ {passed} 通过，❌ {failed} 失败')
if failed == 0:
    print('🎉 全部通过！')
else:
    print('⚠️ 存在失败的测试，请检查')
print('=' * 80)
