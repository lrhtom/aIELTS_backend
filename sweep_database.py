#!/usr/bin/env python
"""
数据库全面清扫工具
清理所有可能导致崩溃、不合法的数据
包括：重复数据、孤立数据、破损关系、无效状态等
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count
from api.models import (
    User, VocabFSRS, LearningPlan, LearningPlanEntry,
    Word, Notebook, NotebookWord, NotebookWordTag,
    VocabBook, WordBookMembership,
)

class DatabaseSweeper:
    """全面的数据库清扫工具"""
    
    def __init__(self):
        self.issues = []
        self.fixes = []
    
    def log_issue(self, category, count, description):
        """记录发现的问题"""
        self.issues.append({
            'category': category,
            'count': count,
            'description': description,
        })
    
    def log_fix(self, action, count):
        """记录执行的修复"""
        self.fixes.append({'action': action, 'count': count})
    
    # ──── 第1类：重复数据问题 ────
    
    def fix_duplicate_words_in_multiple_plans(self):
        """修复：同一单词在多个非零plan中重复"""
        print('【修复】同一单词在多个plan中的重复...')
        
        # 找出同时在多个非零plan中的单词
        problem_words = {}
        for card in VocabFSRS.objects.filter(plan_id__gt=0):
            key = (card.user_id, card.word)
            if key not in problem_words:
                problem_words[key] = []
            problem_words[key].append(card.plan_id)
        
        problem_words = {k: v for k, v in problem_words.items() if len(set(v)) > 1}
        
        if not problem_words:
            print('  ✓ 无重复数据')
            return 0
        
        fixed_count = 0
        
        for (user_id, word), plan_ids in problem_words.items():
            user = User.objects.get(id=user_id)
            unique_plan_ids = list(set(plan_ids))
            
            # 保留最小plan_id的卡片，删除其他
            cards_to_keep = VocabFSRS.objects.filter(
                user=user, word=word, plan_id__in=unique_plan_ids
            ).order_by('plan_id')
            
            keep_card = cards_to_keep.first()
            cards_to_delete = cards_to_keep.exclude(id=keep_card.id)
            
            delete_count = cards_to_delete.count()
            
            if delete_count > 0:
                # 转移last_review如果更新
                for card in cards_to_delete:
                    if card.last_review and (not keep_card.last_review or card.last_review > keep_card.last_review):
                        keep_card.last_review = card.last_review
                        keep_card.save(update_fields=['last_review'])
                
                cards_to_delete.delete()
                fixed_count += delete_count
        
        if fixed_count > 0:
            self.log_fix(f'删除了{fixed_count}张重复卡片（同一单词多plan）', fixed_count)
            print(f'  🗑️  删除了 {fixed_count} 张重复卡片')
        
        return fixed_count
    
    # ──── 第2类：孤立数据 ────
    
    def fix_orphaned_fsrs_cards(self):
        """修复：指向已删除用户/计划的FSRS卡片"""
        print('【修复】孤立的FSRS卡片...')
        
        user_ids = set(User.objects.values_list('id', flat=True))
        
        # 孤立用户卡片
        orphaned_user = VocabFSRS.objects.exclude(user_id__in=user_ids)
        orphaned_user_count = orphaned_user.count()
        
        if orphaned_user_count > 0:
            orphaned_user.delete()
            self.log_fix(f'删除了{orphaned_user_count}张孤立用户卡片', orphaned_user_count)
            print(f'  🗑️  删除了 {orphaned_user_count} 张孤立用户卡片')
        
        # 孤立计划卡片（plan_id > 0但计划已删除）
        plan_ids = set(LearningPlan.objects.values_list('id', flat=True))
        orphaned_plan = VocabFSRS.objects.filter(plan_id__gt=0).exclude(plan_id__in=plan_ids)
        orphaned_plan_count = orphaned_plan.count()
        
        if orphaned_plan_count > 0:
            orphaned_plan.delete()
            self.log_fix(f'删除了{orphaned_plan_count}张孤立计划卡片', orphaned_plan_count)
            print(f'  🗑️  删除了 {orphaned_plan_count} 张孤立计划卡片')
        
        return orphaned_user_count + orphaned_plan_count
    
    def fix_orphaned_plan_entries(self):
        """修复：指向已删除计划/单词的计划条目"""
        print('【修复】孤立的计划条目...')
        
        plan_ids = set(LearningPlan.objects.values_list('id', flat=True))
        word_strs = set(Word.objects.values_list('word', flat=True))
        
        orphaned = LearningPlanEntry.objects.filter(
            Q(plan_id__isnull=True) | ~Q(plan_id__in=plan_ids)
        )
        orphaned_count = orphaned.count()
        
        if orphaned_count > 0:
            orphaned.delete()
            self.log_fix(f'删除了{orphaned_count}条孤立计划条目', orphaned_count)
            print(f'  🗑️  删除了 {orphaned_count} 条孤立计划条目')
        
        return orphaned_count
    
    def fix_orphaned_notebook_entries(self):
        """修复：指向已删除笔记本/单词的笔记本条目"""
        print('【修复】孤立的笔记本条目...')
        
        notebook_ids = set(Notebook.objects.values_list('id', flat=True))
        word_ids = set(Word.objects.values_list('id', flat=True))
        
        orphaned = NotebookWord.objects.filter(
            Q(notebook_id__isnull=True, word_id__isnull=True) |
            (~Q(notebook_id__in=notebook_ids) | ~Q(word_id__in=word_ids))
        )
        orphaned_count = orphaned.count()
        
        if orphaned_count > 0:
            orphaned.delete()
            self.log_fix(f'删除了{orphaned_count}条孤立笔记本条目', orphaned_count)
            print(f'  🗑️  删除了 {orphaned_count} 条孤立笔记本条目')
        
        return orphaned_count
    
    # ──── 第3类：无效状态 ────
    
    def fix_invalid_fsrs_states(self):
        """修复：无效的FSRS卡片状态"""
        print('【修复】无效的FSRS状态...')
        
        invalid_states = VocabFSRS.objects.exclude(state__in=[0, 1, 2, 3])
        invalid_count = invalid_states.count()
        
        if invalid_count > 0:
            # 将无效状态重置为0（NEW）
            invalid_states.update(state=0, stability=0.0, difficulty=5.0)
            self.log_fix(f'修复了{invalid_count}张无效状态卡片', invalid_count)
            print(f'  ✏️  修复了 {invalid_count} 张无效状态卡片 → state=0')
        
        return invalid_count
    
    def fix_negative_values(self):
        """修复：FSRS字段的负值"""
        print('【修复】负值字段...')
        
        # 负数字段重置为0
        negative = VocabFSRS.objects.filter(
            Q(reps__lt=0) | Q(lapses__lt=0) | Q(elapsed_days__lt=0) | 
            Q(scheduled_days__lt=0) | Q(stability__lt=0) | Q(difficulty__lt=1)
        )
        
        fixed_count = 0
        for card in negative:
            changed = False
            if card.reps < 0:
                card.reps = 0
                changed = True
            if card.lapses < 0:
                card.lapses = 0
                changed = True
            if card.elapsed_days < 0:
                card.elapsed_days = 0
                changed = True
            if card.scheduled_days < 0:
                card.scheduled_days = 0
                changed = True
            if card.stability < 0:
                card.stability = 0.0
                changed = True
            if card.difficulty < 1:
                card.difficulty = 5.0
                changed = True
            
            if changed:
                card.save()
                fixed_count += 1
        
        if fixed_count > 0:
            self.log_fix(f'修复了{fixed_count}张负值卡片', fixed_count)
            print(f'  ✏️  修复了 {fixed_count} 张负值卡片')
        
        return fixed_count
    
    def fix_invalid_timestamps(self):
        """修复：无效的时间戳"""
        print('【修复】无效的时间戳...')
        
        now = timezone.now()
        fixed_count = 0
        
        # last_review在未来
        future_review = VocabFSRS.objects.filter(last_review__gt=now)
        if future_review.exists():
            future_review.update(last_review=now)
            fixed_count += future_review.count()
            print(f'  ✏️  修复了 {future_review.count()} 张未来时间的last_review')
        
        # due时间极其异常（超过10年）
        old_due = VocabFSRS.objects.filter(
            due__lt=now - timezone.timedelta(days=3650)
        )
        if old_due.exists():
            old_due.update(due=now)
            fixed_count += old_due.count()
            print(f'  ✏️  修复了 {old_due.count()} 张超期的due时间')
        
        if fixed_count > 0:
            self.log_fix(f'修复了{fixed_count}条异常时间戳', fixed_count)
        
        return fixed_count
    
    # ──── 第4类：破损的外键关系 ────
    
    def fix_invalid_mastery_levels(self):
        """修复：生词本掌握度不在0-5范围"""
        print('【修复】无效的掌握度等级...')
        
        invalid = NotebookWord.objects.exclude(
            mastery_level__in=[0, 1, 2, 3, 4, 5]
        )
        invalid_count = invalid.count()
        
        if invalid_count > 0:
            invalid.update(mastery_level=0)
            self.log_fix(f'修复了{invalid_count}条无效掌握度', invalid_count)
            print(f'  ✏️  修复了 {invalid_count} 条掌握度 → 0')
        
        return invalid_count
    
    def fix_invalid_plan_config(self):
        """修复：学习计划配置异常"""
        print('【修复】计划配置异常...')
        
        # daily_count不在1-500范围
        invalid = LearningPlan.objects.filter(
            Q(daily_count__lt=1) | Q(daily_count__gt=500)
        )
        invalid_count = invalid.count()
        
        if invalid_count > 0:
            for plan in invalid:
                if plan.daily_count < 1:
                    plan.daily_count = 1
                elif plan.daily_count > 500:
                    plan.daily_count = 50
                plan.save()
            
            self.log_fix(f'修复了{invalid_count}个计划配置', invalid_count)
            print(f'  ✏️  修复了 {invalid_count} 个计划配置')
        
        return invalid_count
    
    # ──── 第5类：数据不一致 ────
    
    def fix_empty_word_fields(self):
        """修复：空白单词字段"""
        print('【修复】空白单词字段...')
        
        # FSRS卡片word为空
        empty_word = VocabFSRS.objects.filter(
            Q(word__isnull=True) | Q(word__exact='')
        )
        empty_count = empty_word.count()
        
        if empty_count > 0:
            empty_word.delete()
            self.log_fix(f'删除了{empty_count}张空白word卡片', empty_count)
            print(f'  🗑️  删除了 {empty_count} 张空白word卡片')
        
        return empty_count
    
    def fix_word_case_inconsistency(self):
        """修复：单词大小写不一致问题"""
        print('【修复】单词大小写不一致...')
        
        # 统计大小写不一致的单词
        fixed_count = 0
        duplicates = (
            VocabFSRS.objects
            .values('user_id', 'word')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        
        for dup in duplicates:
            user_id = dup['user_id']
            word = dup['word']
            
            cards = list(VocabFSRS.objects.filter(user_id=user_id, word=word))
            
            if len(cards) > 1:
                # 保留最早的，删除其他
                keep_card = min(cards, key=lambda c: c.created_at)
                delete_cards = [c for c in cards if c.id != keep_card.id]
                
                for card in delete_cards:
                    if card.last_review and (not keep_card.last_review or card.last_review > keep_card.last_review):
                        keep_card.last_review = card.last_review
                        keep_card.save(update_fields=['last_review'])
                
                VocabFSRS.objects.filter(id__in=[c.id for c in delete_cards]).delete()
                fixed_count += len(delete_cards)
        
        if fixed_count > 0:
            self.log_fix(f'修复了{fixed_count}张大小写重复卡片', fixed_count)
            print(f'  🗑️  删除了 {fixed_count} 张大小写重复卡片')
        
        return fixed_count
    
    # ──── 主清扫函数 ────
    
    def run_full_sweep(self):
        """执行完整的数据库清扫"""
        print('\n' + '='*100)
        print('🧹 全面数据库清扫开始')
        print('='*100 + '\n')
        
        total_fixed = 0
        
        print('【第1章】重复数据')
        print('-'*100)
        total_fixed += self.fix_duplicate_words_in_multiple_plans()
        total_fixed += self.fix_word_case_inconsistency()
        
        print()
        print('【第2章】孤立数据')
        print('-'*100)
        total_fixed += self.fix_orphaned_fsrs_cards()
        total_fixed += self.fix_orphaned_plan_entries()
        total_fixed += self.fix_orphaned_notebook_entries()
        
        print()
        print('【第3章】无效状态')
        print('-'*100)
        total_fixed += self.fix_invalid_fsrs_states()
        total_fixed += self.fix_negative_values()
        total_fixed += self.fix_invalid_timestamps()
        
        print()
        print('【第4章】破损关系')
        print('-'*100)
        total_fixed += self.fix_invalid_mastery_levels()
        total_fixed += self.fix_invalid_plan_config()
        
        print()
        print('【第5章】数据一致性')
        print('-'*100)
        total_fixed += self.fix_empty_word_fields()
        
        self.print_summary(total_fixed)
    
    def print_summary(self, total_fixed):
        """打印清扫摘要"""
        print('\n' + '='*100)
        print('✨ 数据库清扫完成')
        print('='*100 + '\n')
        
        if total_fixed == 0:
            print('✅ 数据库已干净，无需修复')
        else:
            print(f'🎉 共清扫修复 {total_fixed} 条/张数据\n')
            
            print('修复清单：')
            for fix in self.fixes:
                print(f'  • {fix["action"]}: {fix["count"]}')
        
        print('\n' + '='*100)
        print('💪 数据库已强化，更加稳定可靠！')
        print('='*100 + '\n')


if __name__ == '__main__':
    with transaction.atomic():
        sweeper = DatabaseSweeper()
        sweeper.run_full_sweep()
