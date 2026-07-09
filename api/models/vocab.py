"""Vocabulary: books, words, notebooks, FSRS cards, learning plans, cache tables, custom decks.

This is the biggest sub-module because the vocab system has many tightly-related tables.
Foreign keys cross file boundaries via the `settings.AUTH_USER_MODEL` string or direct class refs.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .user import User


# ──────────────────────────────────────────────────────────────────────────────
# Global word library
# ──────────────────────────────────────────────────────────────────────────────

class VocabBook(models.Model):
    """
    词书（如 IELTS 3000词、学术词汇表等）
    单词与词书是多对多关系：同一单词可收录于多本词书
    """
    name        = models.CharField(max_length=100, unique=True, verbose_name='词书名称')
    description = models.TextField(blank=True, verbose_name='词书简介')
    cover_image = models.URLField(max_length=500, blank=True, null=True, verbose_name='封面图片')
    word_count  = models.IntegerField(default=0, verbose_name='单词数量（缓存）')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '词书'
        verbose_name_plural = '词书列表'
        db_table = 'vocab_books'

    def __str__(self):
        return self.name


class Word(models.Model):
    """
    全局单词库：存储单词的原型及 AI 生成的元数据
    """
    word = models.CharField(max_length=100, unique=True, verbose_name="单词原文")
    phonetic = models.CharField(max_length=100, blank=True, null=True, verbose_name="音标")
    grammar = models.CharField(max_length=500, blank=True, verbose_name='语法标注')
    definitions = models.JSONField(default=list, verbose_name="释义列表", help_text="包含词性与中文释义的 JSON 数组")
    examples = models.JSONField(default=list, verbose_name="例句列表", help_text="包含中英对照例句的 JSON 数组")

    books = models.ManyToManyField(
        VocabBook,
        through='WordBookMembership',
        blank=True,
        related_name='words',
        verbose_name='所属词书',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收录时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "全局词库"
        verbose_name_plural = "全局词库"
        db_table = 'vocabulary_words'

    def __str__(self):
        return self.word


class WordBookMembership(models.Model):
    """
    单词与词书的多对多关联表
    记录单词在词书中的序号（方便按顺序导出/展示）
    """
    word  = models.ForeignKey(Word,      on_delete=models.CASCADE, related_name='book_memberships', verbose_name='单词')
    book  = models.ForeignKey(VocabBook, on_delete=models.CASCADE, related_name='memberships',      verbose_name='词书')
    order = models.IntegerField(default=0, verbose_name='在词书中的序号')

    class Meta:
        verbose_name = '词书收录'
        verbose_name_plural = '词书收录列表'
        db_table = 'vocab_word_book_membership'
        unique_together = ('word', 'book')
        indexes = [
            models.Index(fields=['book', 'order'], name='idx_wbm_book_order'),
        ]

    def __str__(self):
        return f'{self.word.word} → {self.book.name} #{self.order}'


# ──────────────────────────────────────────────────────────────────────────────
# Per-user notebooks
# ──────────────────────────────────────────────────────────────────────────────

class Notebook(models.Model):
    """
    用户生词本（收藏夹）
    """
    MAX_PER_USER = 10

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebooks', verbose_name="所属用户")
    title = models.CharField(max_length=100, verbose_name="生词本名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    is_public = models.BooleanField(default=False, verbose_name="是否公开")
    cover_color = models.CharField(max_length=50, default="indigo", verbose_name="封面颜色/主题")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "生词本"
        verbose_name_plural = "生词本列表"
        db_table = 'vocabulary_notebooks'

    def clean(self):
        from django.core.exceptions import ValidationError
        # 新建时才检查上限（排除当前对象本身）；管理员不受限制
        if not self.pk and not self.user.is_staff:
            count = Notebook.objects.filter(user=self.user).count()
            if count >= self.MAX_PER_USER:
                raise ValidationError(f'每位用户最多创建 {self.MAX_PER_USER} 本笔记本')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.user.username})"


class NotebookWord(models.Model):
    """笔记本与单词的关系表（包含用户个性化数据）"""
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='entries', verbose_name="所属生词本")
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name='in_notebooks', verbose_name="对应单词")

    mastery_level = models.IntegerField(default=0, verbose_name="掌握度 (0-5)")
    wrong_count = models.IntegerField(default=0, verbose_name="错误次数")
    custom_zh = models.CharField(max_length=500, blank=True, verbose_name="用户自定义中文释义")
    notes = models.TextField(blank=True, null=True, verbose_name="个人笔记")

    added_at = models.DateTimeField(auto_now_add=True, verbose_name="添加时间")
    last_reviewed = models.DateTimeField(blank=True, null=True, verbose_name="最后复习时间")

    class Meta:
        verbose_name = "词条记录"
        verbose_name_plural = "词条记录列表"
        db_table = 'vocabulary_notebook_words'
        unique_together = ('notebook', 'word')

    def __str__(self):
        return f"{self.word.word} in {self.notebook.title}"


class NotebookWordTag(models.Model):
    """
    用户为笔记本中的单词自定义的标签
    每个 NotebookWord 可挂多个标签，标签名区分大小写后 strip+lower 存储
    用途：搜索过滤（如只查看标有"重点"的单词）
    """
    notebook_word = models.ForeignKey(
        NotebookWord,
        on_delete=models.CASCADE,
        related_name='tags',
        verbose_name='词条',
    )
    name = models.CharField(max_length=50, verbose_name='标签名')

    class Meta:
        verbose_name = '词条标签'
        verbose_name_plural = '词条标签列表'
        db_table = 'vocab_notebook_word_tags'
        unique_together = ('notebook_word', 'name')
        indexes = [
            models.Index(fields=['notebook_word'], name='idx_nwtag_entry'),
            # 同一笔记本内按标签名查词：先在 Python 层过滤 notebook，再 join tags
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'#{self.name} on {self.notebook_word}'


# ──────────────────────────────────────────────────────────────────────────────
# FSRS spaced repetition state
# ──────────────────────────────────────────────────────────────────────────────

class VocabFSRS(models.Model):
    """
    每个用户在特定计划下的单词 FSRS 状态
    plan_id=0 → 全局卡片（VocabSync 流程）；>0 → 计划专属，彼此完全隔离
    state: 0=新卡  1=学习中  2=复习  3=重学
    """
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fsrs_cards', verbose_name='用户')
    word           = models.CharField(max_length=200, verbose_name='英文单词')
    plan_id        = models.IntegerField(default=0, verbose_name='所属计划ID（0=全局）')
    zh             = models.CharField(max_length=500, blank=True, verbose_name='中文释义')

    due            = models.DateTimeField(default=timezone.now, verbose_name='下次复习时间')
    stability      = models.FloatField(default=0.0, verbose_name='稳定性 S')
    difficulty     = models.FloatField(default=0.0, verbose_name='难度 D')
    elapsed_days   = models.FloatField(default=0.0, verbose_name='距上次复习天数')
    scheduled_days = models.IntegerField(default=0, verbose_name='计划间隔天数')
    reps           = models.IntegerField(default=0, verbose_name='总复习次数')
    lapses         = models.IntegerField(default=0, verbose_name='遗忘次数')
    state          = models.SmallIntegerField(default=0, verbose_name='卡片状态')
    last_review    = models.DateTimeField(null=True, blank=True, verbose_name='上次复习时间')

    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'FSRS 单词卡'
        verbose_name_plural = 'FSRS 单词卡'
        db_table = 'vocab_fsrs_cards'
        unique_together = ('user', 'word', 'plan_id')
        indexes = [
            models.Index(fields=['user', 'plan_id', 'due'], name='idx_vocab_fsrs_user_plan_due'),
        ]

    def save(self, *args, **kwargs):
        self.word = self.word.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.username} - {self.word} (state={self.state})'


# ──────────────────────────────────────────────────────────────────────────────
# Learning plans (per-user, max 3)
# ──────────────────────────────────────────────────────────────────────────────

class LearningPlan(models.Model):
    MAX_PER_USER = 3
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_plans')
    name        = models.CharField(max_length=50, verbose_name='计划名称')
    daily_count = models.IntegerField(default=20, verbose_name='每日学习词数')
    default_mode = models.CharField(max_length=20, default='flashcard', verbose_name='默认学习模式')
    complete_difficulty = models.CharField(max_length=10, default='hint', verbose_name='拼写难度')
    mastery_target = models.IntegerField(default=2, verbose_name='连续答对目标次数')
    copy_repetitions = models.PositiveSmallIntegerField(default=3, verbose_name='抄写模式每词次数')
    copy_review_days = models.PositiveIntegerField(default=2, verbose_name='抄写完成后复习间隔天数')
    article_review_days = models.PositiveIntegerField(default=7, verbose_name='文章抄写完成后复习间隔天数')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    favorited_at = models.DateTimeField(null=True, blank=True, verbose_name='收藏时间')

    class Meta:
        db_table = 'vocab_learning_plans'
        verbose_name = '学习计划'
        verbose_name_plural = '学习计划'

    def clean(self):
        from django.core.exceptions import ValidationError
        # 管理员不受计划数量限制
        if not self.pk and not self.user.is_staff:
            count = LearningPlan.objects.filter(user=self.user).count()
            if count >= self.MAX_PER_USER:
                raise ValidationError(f'每位用户最多创建 {self.MAX_PER_USER} 个学习计划。')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.user.username})'


class LearningPlanEntry(models.Model):
    plan     = models.ForeignKey(LearningPlan, on_delete=models.CASCADE, related_name='entries')
    word     = models.CharField(max_length=200, verbose_name='单词')
    zh       = models.CharField(max_length=500, blank=True, verbose_name='中文释义')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vocab_learning_plan_entries'
        unique_together = ('plan', 'word')
        verbose_name = '学习计划词条'
        verbose_name_plural = '学习计划词条'

    def save(self, *args, **kwargs):
        self.word = self.word.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.word} → {self.plan.name}'


# ──────────────────────────────────────────────────────────────────────────────
# Per-day AI-generated study caches
# ──────────────────────────────────────────────────────────────────────────────

class ArticleCopyCache(models.Model):
    """Per-user per-plan per-day AI-generated article for the article-copy study mode."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='article_copy_caches',
        verbose_name='用户',
    )
    plan = models.ForeignKey(
        LearningPlan,
        on_delete=models.CASCADE,
        related_name='article_copy_caches',
        verbose_name='学习计划',
    )
    date = models.DateField(verbose_name='学习日期')
    article_title = models.CharField(max_length=200, blank=True, verbose_name='文章标题')
    article_text = models.TextField(verbose_name='文章全文')
    article_translation = models.TextField(blank=True, default='', verbose_name='文章中文翻译')
    typed_text = models.TextField(blank=True, default='', verbose_name='用户已输入的内容')
    word_positions = models.JSONField(default=dict, verbose_name='目标词位置映射')
    ai_provider = models.CharField(max_length=30, default='deepseek', verbose_name='生成模型')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vocab_article_copy_cache'
        verbose_name = '文章抄写缓存'
        verbose_name_plural = '文章抄写缓存列表'
        unique_together = ('user', 'plan', 'date')
        indexes = [
            models.Index(fields=['user', 'plan', 'date'], name='idx_acc_user_plan_date'),
        ]

    def __str__(self):
        return f'{self.user.username} plan={self.plan_id} {self.date}'


class StoryModeCache(models.Model):
    """Per-user per-plan per-day AI-generated story for the story click-to-learn mode."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='story_mode_caches',
        verbose_name='用户',
    )
    plan = models.ForeignKey(
        LearningPlan,
        on_delete=models.CASCADE,
        related_name='story_mode_caches',
        verbose_name='学习计划',
    )
    date = models.DateField(verbose_name='学习日期')
    story_title = models.CharField(max_length=200, blank=True, verbose_name='故事标题')
    story_text = models.TextField(verbose_name='故事全文')
    clicked_words = models.JSONField(default=list, verbose_name='已点击的单词列表')
    target_words = models.JSONField(default=list, verbose_name='目标单词列表')
    ai_provider = models.CharField(max_length=30, default='deepseek', verbose_name='生成模型')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vocab_story_mode_cache'
        verbose_name = '剧情模式缓存'
        verbose_name_plural = '剧情模式缓存列表'
        unique_together = ('user', 'plan', 'date')
        indexes = [
            models.Index(fields=['user', 'plan', 'date'], name='idx_smc_user_plan_date'),
        ]

    def __str__(self):
        return f'{self.user.username} plan={self.plan_id} {self.date}'


# ──────────────────────────────────────────────────────────────────────────────
# Custom memory decks (free-form flashcards)
# ──────────────────────────────────────────────────────────────────────────────

class CustomMemoryDeck(models.Model):
    """用户自定义记忆卡卡组。"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='custom_memory_decks',
        verbose_name='用户',
    )
    title = models.CharField(max_length=100, default='未命名记忆卡组', verbose_name='卡组名称')
    daily_count = models.IntegerField(default=20, verbose_name='每日学习卡片数')
    source_text = models.TextField(blank=True, default='', verbose_name='原始文本')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'custom_memory_decks'
        verbose_name = '自定义记忆卡组'
        verbose_name_plural = '自定义记忆卡组'

    def __str__(self):
        return f'{self.title} ({self.user.username})'


class CustomMemoryCard(models.Model):
    """自定义记忆卡，独立维护FSRS状态。"""
    deck = models.ForeignKey(
        CustomMemoryDeck,
        on_delete=models.CASCADE,
        related_name='cards',
        verbose_name='所属卡组',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='custom_memory_cards',
        verbose_name='用户',
    )
    front_text = models.TextField(verbose_name='正面内容')
    back_text = models.TextField(blank=True, default='', verbose_name='背面内容')
    order = models.PositiveIntegerField(default=0, verbose_name='卡片顺序')

    due = models.DateTimeField(default=timezone.now, verbose_name='下次复习时间')
    stability = models.FloatField(default=0.0, verbose_name='稳定性 S')
    difficulty = models.FloatField(default=0.0, verbose_name='难度 D')
    elapsed_days = models.FloatField(default=0.0, verbose_name='距上次复习天数')
    scheduled_days = models.IntegerField(default=0, verbose_name='计划间隔天数')
    reps = models.IntegerField(default=0, verbose_name='总复习次数')
    lapses = models.IntegerField(default=0, verbose_name='遗忘次数')
    state = models.SmallIntegerField(default=0, verbose_name='卡片状态')
    last_review = models.DateTimeField(null=True, blank=True, verbose_name='上次复习时间')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'custom_memory_cards'
        verbose_name = '自定义记忆卡'
        verbose_name_plural = '自定义记忆卡'
        unique_together = ('deck', 'order')
        indexes = [
            models.Index(fields=['user', 'deck', 'due'], name='idx_custom_card_user_deck_due'),
        ]

    def __str__(self):
        return f'Card#{self.order} {self.deck_id} ({self.user.username})'
