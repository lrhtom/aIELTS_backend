#!/usr/bin/env python
"""
验证数据库清扫后的状态
检查是否还有任何潜在问题
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import connection
from django.db.models import Q, Count, Min, Max
from api.models import VocabFSRS, User, LearningPlan, Word

def verify_database():
    """全面验证数据库状态"""
    print('\n' + '='*100)
    print('🔍 数据库清扫后验证')
    print('='*100 + '\n')
    
    # 1. FSRS卡片统计
    print('【FSRS卡片统计】')
    print('-'*100)
    total_cards = VocabFSRS.objects.count()
    print(f'  总卡片数: {total_cards}')
    
    # 按状态分布
    state_dist = {}
    for state in [0, 1, 2, 3]:
        count = VocabFSRS.objects.filter(state=state).count()
        state_names = {0: 'NEW', 1: 'LEARNING', 2: 'REVIEW', 3: 'RELEARNING'}
        state_dist[state] = count
        print(f'    {state_names[state]:10} (state={state}): {count:6} 张')
    
    # 2. 异常检测
    print('\n【异常检测】')
    print('-'*100)
    
    issues = []
    
    # 检查无效状态
    invalid_states = VocabFSRS.objects.exclude(state__in=[0, 1, 2, 3])
    if invalid_states.exists():
        issues.append(f'  ⚠️  {invalid_states.count()} 张无效状态卡片')
    
    # 检查难度值范围
    invalid_difficulty = VocabFSRS.objects.filter(
        Q(difficulty__lt=1) | Q(difficulty__gt=10)
    )
    if invalid_difficulty.exists():
        issues.append(f'  ⚠️  {invalid_difficulty.count()} 张无效难度值卡片')
    
    # 检查负值字段
    negative = VocabFSRS.objects.filter(
        Q(reps__lt=0) | Q(lapses__lt=0) | Q(stability__lt=0)
    )
    if negative.exists():
        issues.append(f'  ⚠️  {negative.count()} 张负值卡片')
    
    # 检查重复卡片（同user/word）
    duplicates = (
        VocabFSRS.objects
        .values('user_id', 'word')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
    )
    if duplicates.exists():
        dup_count = sum(d['count'] - 1 for d in duplicates)
        issues.append(f'  ⚠️  {dup_count} 张重复卡片 ({duplicates.count()} 组)')
    
    # 检查孤立卡片
    orphaned_user = VocabFSRS.objects.exclude(
        user_id__in=User.objects.values_list('id', flat=True)
    )
    if orphaned_user.exists():
        issues.append(f'  ⚠️  {orphaned_user.count()} 张孤立用户卡片')
    
    orphaned_plan = VocabFSRS.objects.filter(plan_id__gt=0).exclude(
        plan_id__in=LearningPlan.objects.values_list('id', flat=True)
    )
    if orphaned_plan.exists():
        issues.append(f'  ⚠️  {orphaned_plan.count()} 张孤立计划卡片')
    
    # 检查空单词
    empty_word = VocabFSRS.objects.filter(Q(word__isnull=True) | Q(word__exact=''))
    if empty_word.exists():
        issues.append(f'  ⚠️  {empty_word.count()} 张空白word卡片')
    
    if issues:
        for issue in issues:
            print(issue)
    else:
        print('  ✅ 无异常数据')
    
    # 3. 数值范围检查
    print('\n【数值范围检查】')
    print('-'*100)
    
    stats = VocabFSRS.objects.aggregate(
        min_difficulty=Min('difficulty'),
        max_difficulty=Max('difficulty'),
        min_stability=Min('stability'),
        max_stability=Max('stability'),
        min_reps=Min('reps'),
        max_reps=Max('reps'),
    )
    
    print(f'  Difficulty: [{stats["min_difficulty"]:.2f}, {stats["max_difficulty"]:.2f}] (有效范围: [1, 10])')
    print(f'  Stability:  [{stats["min_stability"]:.2f}, {stats["max_stability"]:.2f}] (有效范围: [0, ∞))')
    print(f'  Reps:       [{stats["min_reps"]}, {stats["max_reps"]}] (应为正整数)')
    
    # 4. 多计划单词分析
    print('\n【多计划单词分析】')
    print('-'*100)
    
    multi_plan = (
        VocabFSRS.objects
        .values('user_id', 'word')
        .annotate(plan_count=Count('plan_id', distinct=True))
        .filter(plan_count__gt=1)
    )
    
    multi_plan_count = multi_plan.count()
    if multi_plan_count > 0:
        print(f'  ⚠️  {multi_plan_count} 个单词存在于多个plan中')
        
        # 详细分布
        for item in list(multi_plan)[:5]:
            user_id = item['user_id']
            word = item['word']
            plans = list(
                VocabFSRS.objects.filter(
                    user_id=user_id, word=word
                ).values_list('plan_id', flat=True).distinct()
            )
            print(f'      "{word}" → plan_id={plans}')
        
        if multi_plan_count > 5:
            print(f'      ... 及其他 {multi_plan_count - 5} 个')
    else:
        print('  ✅ 所有单词均在单一plan中')
    
    # 5. 用户统计
    print('\n【用户统计】')
    print('-'*100)
    
    user_stats = (
        VocabFSRS.objects
        .values('user_id')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    print(f'  总用户数: {user_stats.count()}')
    for stat in list(user_stats)[:5]:
        user = User.objects.get(id=stat['user_id'])
        print(f'    {user.username:20} ({user.email}): {stat["count"]:5} 张卡片')
    
    # 6. 学习计划统计
    print('\n【学习计划统计】')
    print('-'*100)
    
    plans = LearningPlan.objects.all()
    print(f'  总计划数: {plans.count()}')
    for plan in plans[:5]:
        card_count = VocabFSRS.objects.filter(plan_id=plan.id).count()
        print(f'    {plan.name:30} (ID={plan.id}): {card_count:5} 张卡片')
    
    print('\n' + '='*100)
    print('✨ 数据库验证完成！')
    print('='*100 + '\n')


if __name__ == '__main__':
    verify_database()
