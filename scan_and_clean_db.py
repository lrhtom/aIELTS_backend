#!/usr/bin/env python
"""
数据库异常数据扫描和清除工具
扫描并修复：孤立数据、无效引用、状态异常、时间戳异常等问题
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.utils import timezone
from django.db.models import Q, Count
from api.models import (
    User, VocabFSRS, LearningPlan, LearningPlanEntry,
    Word, Notebook, NotebookWord, NotebookWordTag,
    VocabBook, WordBookMembership,
    Feedback, AIPrompt
)

# ──────────────────────────────────────────────────────────────────────────────
# 扫描工具函数
# ──────────────────────────────────────────────────────────────────────────────

class DatabaseScanner:
    def __init__(self):
        self.issues = []
        self.fixes = []
        self.stats = {}
    
    def add_issue(self, category, count, details):
        """记录一个数据问题"""
        self.issues.append({
            'category': category,
            'count': count,
            'details': details,
        })
    
    def add_fix(self, category, count, action):
        """记录一个修复"""
        self.fixes.append({
            'category': category,
            'count': count,
            'action': action,
        })
    
    # ──── 第1组：孤立数据检测 ────
    
    def scan_orphaned_vocab_fsrs(self):
        """🔴 检测孤立的FSRS卡片（用户被删除）"""
        print('🔍 扫描孤立的FSRS卡片...', end=' ')
        
        user_ids = set(User.objects.values_list('id', flat=True))
        orphaned = VocabFSRS.objects.exclude(user_id__in=user_ids).count()
        
        if orphaned > 0:
            self.add_issue('孤立FSRS卡片', orphaned, 'FSRS卡片指向已删除的用户')
            print(f'⚠️  发现 {orphaned} 条孤立卡片')
        else:
            print('✓')
        
        return orphaned
    
    def scan_orphaned_learning_plan_entries(self):
        """🔴 检测孤立的学习计划条目（计划被删除）"""
        print('🔍 扫描孤立的计划条目...', end=' ')
        
        plan_ids = set(LearningPlan.objects.values_list('id', flat=True))
        orphaned = LearningPlanEntry.objects.exclude(plan_id__in=plan_ids).count()
        
        if orphaned > 0:
            self.add_issue('孤立计划条目', orphaned, '计划条目指向已删除的计划')
            print(f'⚠️  发现 {orphaned} 条孤立条目')
        else:
            print('✓')
        
        return orphaned
    
    def scan_orphaned_notebook_entries(self):
        """🔴 检测孤立的生词本条目（笔记本/单词被删除）"""
        print('🔍 扫描孤立的生词本条目...', end=' ')
        
        notebook_ids = set(Notebook.objects.values_list('id', flat=True))
        word_ids = set(Word.objects.values_list('id', flat=True))
        
        orphaned = NotebookWord.objects.exclude(
            Q(notebook_id__in=notebook_ids) & Q(word_id__in=word_ids)
        ).count()
        
        if orphaned > 0:
            self.add_issue('孤立生词本条目', orphaned, '生词本条目指向已删除的笔记本或单词')
            print(f'⚠️  发现 {orphaned} 条孤立条目')
        else:
            print('✓')
        
        return orphaned
    
    def scan_orphaned_notebook_tags(self):
        """🔴 检测孤立的生词本标签（条目被删除）"""
        print('🔍 扫描孤立的生词本标签...', end=' ')
        
        entry_ids = set(NotebookWord.objects.values_list('id', flat=True))
        orphaned = NotebookWordTag.objects.exclude(notebook_word_id__in=entry_ids).count()
        
        if orphaned > 0:
            self.add_issue('孤立生词本标签', orphaned, '标签指向已删除的条目')
            print(f'⚠️  发现 {orphaned} 条孤立标签')
        else:
            print('✓')
        
        return orphaned
    
    # ──── 第2组：FSRS状态异常检测 ────
    
    def scan_fsrs_invalid_states(self):
        """🔴 检测FSRS卡片状态异常（state不在0-3）"""
        print('🔍 扫描FSRS状态异常...', end=' ')
        
        invalid = VocabFSRS.objects.exclude(state__in=[0, 1, 2, 3]).count()
        
        if invalid > 0:
            self.add_issue('FSRS状态异常', invalid, 'state值不在0-3范围')
            print(f'⚠️  发现 {invalid} 条异常卡片')
        else:
            print('✓')
        
        return invalid
    
    def scan_fsrs_negative_values(self):
        """🔴 检测FSRS数值异常（不能为负）"""
        print('🔍 扫描FSRS负数值异常...', end=' ')
        
        negative_count = (
            VocabFSRS.objects
            .filter(Q(reps__lt=0) | Q(lapses__lt=0) | Q(elapsed_days__lt=0) | 
                    Q(scheduled_days__lt=0) | Q(stability__lt=0) | Q(difficulty__lt=0))
            .count()
        )
        
        if negative_count > 0:
            self.add_issue('FSRS负值异常', negative_count, '数值字段包含负数')
            print(f'⚠️  发现 {negative_count} 条异常卡片')
        else:
            print('✓')
        
        return negative_count
    
    def scan_fsrs_difficulty_range(self):
        """🟡 检测难度值异常（应在1-10）"""
        print('🔍 扫描FSRS难度值范围...', end=' ')
        
        out_of_range = VocabFSRS.objects.filter(
            Q(difficulty__lt=1) | Q(difficulty__gt=10)
        ).count()
        
        if out_of_range > 0:
            self.add_issue('FSRS难度异常', out_of_range, '难度值不在1-10范围')
            print(f'⚠️  发现 {out_of_range} 条异常卡片')
        else:
            print('✓')
        
        return out_of_range
    
    # ──── 第3组：时间戳异常检测 ────
    
    def scan_fsrs_invalid_timestamps(self):
        """🟡 检测FSRS时间戳异常（last_review > due, 未来时间等）"""
        print('🔍 扫描FSRS时间戳异常...', end=' ')
        
        now = timezone.now()
        issues = 0
        
        # last_review在未来
        future_review = VocabFSRS.objects.filter(last_review__gt=now).count()
        if future_review > 0:
            issues += future_review
            print(f'\n  ⚠️  future_review in {future_review}')
        
        # due在过去太久（超过1年）
        old_due = VocabFSRS.objects.filter(due__lt=now - timezone.timedelta(days=365)).count()
        if old_due > 0:
            issues += old_due
            print(f'  ⚠️  old_due in {old_due}')
        
        if issues > 0:
            self.add_issue('FSRS时间异常', issues, '时间戳包含异常值')
            print(f'⚠️  发现 {issues} 条异常')
        else:
            print('✓')
        
        return issues
    
    def scan_user_deletion_requests_old(self):
        """🟡 检测超过30天未处理的删除请求"""
        print('🔍 扫描过期的删除请求...', end=' ')
        
        threshold = timezone.now() - timezone.timedelta(days=30)
        old_requests = User.objects.filter(
            deletion_requested_at__isnull=False,
            deletion_requested_at__lt=threshold
        ).count()
        
        if old_requests > 0:
            self.add_issue('过期删除请求', old_requests, '超过30天未处理的用户删除请求')
            print(f'⚠️  发现 {old_requests} 个')
        else:
            print('✓')
        
        return old_requests
    
    # ──── 第4组：数据一致性检测 ────
    
    def scan_empty_word_entries(self):
        """🟡 检测空白单词条目"""
        print('🔍 扫描空白单词条目...', end=' ')
        
        empty_words = (
            VocabFSRS.objects.filter(word__isnull=True) |
            VocabFSRS.objects.filter(word__exact='')
        ).count()
        
        if empty_words > 0:
            self.add_issue('空白单词', empty_words, 'FSRS卡片的word字段为空')
            print(f'⚠️  发现 {empty_words} 条')
        else:
            print('✓')
        
        return empty_words
    
    def scan_duplicate_fsrs_entries(self):
        """🔴 检测FSRS重复条目（理论上不应该有，unique_together保护）"""
        print('🔍 扫描FSRS重复条目...', end=' ')
        
        duplicates = (
            VocabFSRS.objects
            .values('user_id', 'word', 'plan_id')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
            .count()
        )
        
        if duplicates > 0:
            self.add_issue('FSRS重复条目', duplicates, '相同(user,word,plan_id)的重复条目')
            print(f'⚠️  发现 {duplicates} 组重复')
        else:
            print('✓')
        
        return duplicates
    
    def scan_user_quota_anomalies(self):
        """🟡 检测用户配额异常（负数或超大值）"""
        print('🔍 扫描用户配额异常...', end=' ')
        
        anomalies = User.objects.filter(
            Q(daily_ai_quota__lt=0) | Q(daily_ai_quota__gt=1000000) |
            Q(at_balance__lt=0) | Q(at_balance__gt=10000000)
        ).count()
        
        if anomalies > 0:
            self.add_issue('用户配额异常', anomalies, '用户的quota或balance值异常')
            print(f'⚠️  发现 {anomalies} 个用户')
        else:
            print('✓')
        
        return anomalies
    
    # ──── 第5组：计划配置检测 ────
    
    def scan_learning_plan_config_anomalies(self):
        """🟡 检测学习计划配置异常"""
        print('🔍 扫描计划配置异常...', end=' ')
        
        anomalies = LearningPlan.objects.filter(
            Q(daily_count__lt=1) | Q(daily_count__gt=500)
        ).count()
        
        if anomalies > 0:
            self.add_issue('计划配置异常', anomalies, 'daily_count值不在1-500范围')
            print(f'⚠️  发现 {anomalies} 个计划')
        else:
            print('✓')
        
        return anomalies
    
    # ──── 主扫描函数 ────
    
    def run_full_scan(self):
        """执行完整扫描"""
        print('\n' + '='*100)
        print('📊 数据库异常扫描开始')
        print('='*100 + '\n')
        
        print('【第1组】孤立数据检测')
        print('-' * 100)
        self.scan_orphaned_vocab_fsrs()
        self.scan_orphaned_learning_plan_entries()
        self.scan_orphaned_notebook_entries()
        self.scan_orphaned_notebook_tags()
        
        print('\n【第2组】FSRS状态异常')
        print('-' * 100)
        self.scan_fsrs_invalid_states()
        self.scan_fsrs_negative_values()
        self.scan_fsrs_difficulty_range()
        
        print('\n【第3组】时间戳异常')
        print('-' * 100)
        self.scan_fsrs_invalid_timestamps()
        self.scan_user_deletion_requests_old()
        
        print('\n【第4组】数据一致性')
        print('-' * 100)
        self.scan_empty_word_entries()
        self.scan_duplicate_fsrs_entries()
        self.scan_user_quota_anomalies()
        
        print('\n【第5组】计划配置')
        print('-' * 100)
        self.scan_learning_plan_config_anomalies()
        
        self.print_summary()
    
    def print_summary(self):
        """打印扫描总结"""
        print('\n' + '='*100)
        print('📋 扫描结果总结')
        print('='*100)
        
        if not self.issues:
            print('✅ 数据库完整无缺，未发现任何异常！')
            return
        
        total_issues = sum(i['count'] for i in self.issues)
        print(f'\n🔴 发现 {len(self.issues)} 类异常，共 {total_issues} 条数据需要处理\n')
        
        for idx, issue in enumerate(self.issues, 1):
            print(f'{idx}. {issue["category"]}')
            print(f'   数量: {issue["count"]}条')
            print(f'   说明: {issue["details"]}')
            print()


# ──────────────────────────────────────────────────────────────────────────────
# 清除工具函数
# ──────────────────────────────────────────────────────────────────────────────

class DatabaseCleaner:
    def __init__(self):
        self.deleted_counts = {}
    
    def clean_orphaned_vocab_fsrs(self):
        """💥 删除孤立的FSRS卡片"""
        user_ids = set(User.objects.values_list('id', flat=True))
        orphaned = VocabFSRS.objects.exclude(user_id__in=user_ids)
        count = orphaned.count()
        
        if count > 0:
            orphaned.delete()
            print(f'🗑️  已删除 {count} 条孤立FSRS卡片')
            self.deleted_counts['orphaned_fsrs'] = count
    
    def clean_orphaned_learning_plan_entries(self):
        """💥 删除孤立的计划条目"""
        plan_ids = set(LearningPlan.objects.values_list('id', flat=True))
        orphaned = LearningPlanEntry.objects.exclude(plan_id__in=plan_ids)
        count = orphaned.count()
        
        if count > 0:
            orphaned.delete()
            print(f'🗑️  已删除 {count} 条孤立计划条目')
            self.deleted_counts['orphaned_entries'] = count
    
    def clean_orphaned_notebook_entries(self):
        """💥 删除孤立的生词本条目"""
        notebook_ids = set(Notebook.objects.values_list('id', flat=True))
        word_ids = set(Word.objects.values_list('id', flat=True))
        
        orphaned = NotebookWord.objects.exclude(
            Q(notebook_id__in=notebook_ids) & Q(word_id__in=word_ids)
        )
        count = orphaned.count()
        
        if count > 0:
            orphaned.delete()
            print(f'🗑️  已删除 {count} 条孤立生词本条目')
            self.deleted_counts['orphaned_notebook'] = count
    
    def clean_orphaned_notebook_tags(self):
        """💥 删除孤立的生词本标签"""
        entry_ids = set(NotebookWord.objects.values_list('id', flat=True))
        orphaned = NotebookWordTag.objects.exclude(notebook_word_id__in=entry_ids)
        count = orphaned.count()
        
        if count > 0:
            orphaned.delete()
            print(f'🗑️  已删除 {count} 条孤立生词本标签')
            self.deleted_counts['orphaned_tags'] = count
    
    def clean_fsrs_invalid_states(self):
        """💥 删除FSRS状态异常的卡片"""
        invalid = VocabFSRS.objects.exclude(state__in=[0, 1, 2, 3])
        count = invalid.count()
        
        if count > 0:
            invalid.delete()
            print(f'🗑️  已删除 {count} 条FSRS状态异常的卡片')
            self.deleted_counts['invalid_states'] = count
    
    def clean_fsrs_negative_values(self):
        """💥 删除FSRS数值异常的卡片"""
        invalid = VocabFSRS.objects.filter(
            Q(reps__lt=0) | Q(lapses__lt=0) | Q(elapsed_days__lt=0) | 
            Q(scheduled_days__lt=0) | Q(stability__lt=0) | Q(difficulty__lt=0)
        )
        count = invalid.count()
        
        if count > 0:
            invalid.delete()
            print(f'🗑️  已删除 {count} 条FSRS数值异常的卡片')
            self.deleted_counts['negative_values'] = count
    
    def clean_fsrs_difficulty_range(self):
        """💥 删除FSRS难度值异常的卡片"""
        invalid = VocabFSRS.objects.filter(
            Q(difficulty__lt=1) | Q(difficulty__gt=10)
        )
        count = invalid.count()
        
        if count > 0:
            invalid.delete()
            print(f'🗑️  已删除 {count} 条FSRS难度值异常的卡片')
            self.deleted_counts['difficulty_range'] = count
    
    def clean_empty_word_entries(self):
        """💥 删除空白单词条目"""
        empty = VocabFSRS.objects.filter(Q(word__isnull=True) | Q(word__exact=''))
        count = empty.count()
        
        if count > 0:
            empty.delete()
            print(f'🗑️  已删除 {count} 条空白单词条目')
            self.deleted_counts['empty_words'] = count
    
    def clean_fsrs_invalid_timestamps(self):
        """💥 删除FSRS时间戳异常的卡片"""
        now = timezone.now()
        
        # last_review在未来
        future = VocabFSRS.objects.filter(last_review__gt=now)
        future_count = future.count()
        if future_count > 0:
            future.delete()
            print(f'🗑️  已删除 {future_count} 条last_review在未来的卡片')
            self.deleted_counts['future_timestamps'] = future_count
        
        # due在过去超过1年的卡片（可能是bug导致的）
        old_due = VocabFSRS.objects.filter(due__lt=now - timezone.timedelta(days=365))
        old_count = old_due.count()
        if old_count > 0:
            # 先修复而不是删除
            old_due.update(due=now)
            print(f'✏️  已修复 {old_count} 条due时间过期的卡片（重置为现在）')
            self.deleted_counts['fixed_old_due'] = old_count
    
    def clean_user_quota_anomalies(self):
        """💥 修复用户配额异常"""
        # 负数改为0
        negative_quota = User.objects.filter(daily_ai_quota__lt=0)
        neg_count = negative_quota.count()
        if neg_count > 0:
            negative_quota.update(daily_ai_quota=0)
            print(f'✏️  已修复 {neg_count} 个用户的负数quota（重置为0）')
            self.deleted_counts['fixed_negative_quota'] = neg_count
        
        # 负数余额改为0
        negative_balance = User.objects.filter(at_balance__lt=0)
        neg_bal_count = negative_balance.count()
        if neg_bal_count > 0:
            negative_balance.update(at_balance=0)
            print(f'✏️  已修复 {neg_bal_count} 个用户的负数余额（重置为0）')
            self.deleted_counts['fixed_negative_balance'] = neg_bal_count
    
    def clean_learning_plan_anomalies(self):
        """💥 修复学习计划配置异常"""
        anomalies = LearningPlan.objects.filter(
            Q(daily_count__lt=1) | Q(daily_count__gt=500)
        )
        count = anomalies.count()
        
        if count > 0:
            # 小于1的改为1，大于500的改为50
            LearningPlan.objects.filter(daily_count__lt=1).update(daily_count=1)
            LearningPlan.objects.filter(daily_count__gt=500).update(daily_count=50)
            print(f'✏️  已修复 {count} 个计划的daily_count（重置为有效范围）')
            self.deleted_counts['fixed_plan_config'] = count
    
    def run_full_clean(self):
        """执行完整清除和修复"""
        print('\n' + '='*100)
        print('🧹 开始清除和修复异常数据')
        print('='*100 + '\n')
        
        self.clean_orphaned_vocab_fsrs()
        self.clean_orphaned_learning_plan_entries()
        self.clean_orphaned_notebook_entries()
        self.clean_orphaned_notebook_tags()
        
        self.clean_fsrs_invalid_states()
        self.clean_fsrs_negative_values()
        self.clean_fsrs_difficulty_range()
        
        self.clean_empty_word_entries()
        self.clean_fsrs_invalid_timestamps()
        self.clean_user_quota_anomalies()
        self.clean_learning_plan_anomalies()
        
        self.print_summary()
    
    def print_summary(self):
        """打印清除总结"""
        print('\n' + '='*100)
        print('✅ 清除和修复完成')
        print('='*100)
        
        if not self.deleted_counts:
            print('数据库已是清洁状态，无需处理。')
            return
        
        total = sum(self.deleted_counts.values())
        print(f'\n🎉 共处理 {total} 条数据：\n')
        
        for action, count in self.deleted_counts.items():
            print(f'  • {action}: {count}')
        
        print('\n✨ 数据库已清洁！')


# ──────────────────────────────────────────────────────────────────────────────
# 主程序
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    
    scanner = DatabaseScanner()
    scanner.run_full_scan()
    
    if scanner.issues:
        print('\n' + '='*100)
        response = input('🔧 是否立即清除和修复上述异常数据？(yes/no): ').strip().lower()
        print('='*100)
        
        if response in ('yes', 'y'):
            cleaner = DatabaseCleaner()
            cleaner.run_full_clean()
        else:
            print('\n⏭️  已取消清除操作，数据保持原样。')
    else:
        print('\n✅ 数据库状态良好，无需清除。')
