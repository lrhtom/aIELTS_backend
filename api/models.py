from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class User(AbstractUser):
    """
    全面定制化的用户模型
    """
    
    class MembershipTier(models.TextChoices):
        FREE = 'FREE', _('免费用户')
        PRO = 'PRO', _('专业会员')
        PREMIUM = 'PREMIUM', _('尊享会员')

    email = models.EmailField(_('email address'), unique=True, error_messages={
        'unique': _("A user with that email already exists."),
    })
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="手机号", unique=True)
    nickname = models.CharField(max_length=50, blank=True, verbose_name="用户昵称")
    avatar_url = models.URLField(max_length=500, blank=True, null=True, verbose_name="头像URL")
    avatar_file = models.CharField(max_length=255, blank=True, null=True, verbose_name="头像文件路径")
    
    target_score = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="目标分数(如: 7.5)")
    current_score = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="当前预估分数")
    exam_date = models.DateField(blank=True, null=True, verbose_name="预计考试时间")
    
    membership_tier = models.CharField(
        max_length=10, 
        choices=MembershipTier.choices, 
        default=MembershipTier.FREE, 
        verbose_name="会员等级"
    )
    vip_expires_at = models.DateTimeField(blank=True, null=True, verbose_name="会员过期时间")
    daily_ai_quota = models.IntegerField(default=20, verbose_name="每日剩余生成次数/Token")
    at_balance = models.IntegerField(default=10000, verbose_name="AT币余额")
    
    wechat_openid = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="微信OpenID")
    github_id = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="Github ID")

    # 用于限制单设备登录的 Token ID
    jwt_token_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="当前有效的 Token ID")

    is_email_verified = models.BooleanField(default=False, verbose_name="邮箱是否验证")
    is_banned = models.BooleanField(default=False, verbose_name="是否封号")
    deletion_requested_at = models.DateTimeField(blank=True, null=True, verbose_name="申请注销时间")
    last_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="最后登录IP")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="信息最后更新时间")

    # 外观偏好
    bg_color = models.CharField(max_length=200, blank=True, null=True, verbose_name="背景颜色/渐变值")
    bg_image_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="背景图片URL")
    bg_blur = models.FloatField(default=2.0, verbose_name="背景模糊度(px)")

    # AI生成相关设置
    ai_generation_retry_count = models.IntegerField(
        default=0, 
        verbose_name="AI生成重试次数(0-10)",
        help_text="当AI生成失败时自动重试的次数，范围0-10次。更多重试次数会增加AT币消耗。"
    )

    class Meta:
        verbose_name = "用户信息"
        verbose_name_plural = "用户信息列表"
        db_table = 'user_profiles'

    def __str__(self):
        return f"{self.username} ({self.get_membership_tier_display()})"

class AIPrompt(models.Model):
    username = models.CharField(max_length=150, verbose_name="用户名")
    title = models.CharField(max_length=200, verbose_name="提示词标题", default='')
    prompt_content = models.TextField(verbose_name="提示词内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    likes = models.ManyToManyField(
        'api.User',
        related_name='liked_prompts',
        verbose_name="点赞用户",
        blank=True
    )
    favorites = models.ManyToManyField(
        'api.User',
        related_name='favorited_prompts',
        verbose_name="收藏用户",
        blank=True
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AI 提示词"
        verbose_name_plural = "AI 提示词列表"

    def __str__(self):
        return f"{self.username} - {self.title or self.prompt_content[:30]}"

class Feedback(models.Model):
    username = models.CharField(max_length=150, verbose_name="用户名")
    title = models.CharField(max_length=255, verbose_name="反馈标题")
    content = models.TextField(blank=True, null=True, verbose_name="反馈内容")
    is_resolved = models.BooleanField(default=False, verbose_name="是否解决")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bug 反馈"
        verbose_name_plural = "Bug 反馈列表"

    def __str__(self):
        return f"{self.username} - {self.title}"

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

    # 语法标注（如 "noun, countable; often followed by 'of'"）
    grammar = models.CharField(max_length=500, blank=True, verbose_name='语法标注')

    # definitions 存储结构示例: [{"pos": "n.", "meaning": "苹果"}, {"pos": "vt.", "meaning": "评价"}]
    definitions = models.JSONField(default=list, verbose_name="释义列表", help_text="包含词性与中文释义的 JSON 数组")

    # examples 存储结构示例: [{"en": "Sentence", "zh": "翻译"}]
    examples = models.JSONField(default=list, verbose_name="例句列表", help_text="包含中英对照例句的 JSON 数组")

    # 所属词书（多对多，一个单词可属于多本词书）
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
    """
    笔记本与单词的关系表（包含用户个性化数据）
    """
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

    # FSRS Card 状态字段（完整映射 FSRS-4.5 Card 类型）
    due            = models.DateTimeField(default=timezone.now, verbose_name='下次复习时间')
    stability      = models.FloatField(default=0.0, verbose_name='稳定性 S')
    difficulty     = models.FloatField(default=0.0, verbose_name='难度 D')
    elapsed_days   = models.IntegerField(default=0, verbose_name='距上次复习天数')
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
        return f'{self.word} ({self.user.username}) plan={self.plan_id}'


class LearningPlan(models.Model):
    MAX_PER_USER = 3
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_plans')
    name        = models.CharField(max_length=50, verbose_name='计划名称')
    daily_count = models.IntegerField(default=20, verbose_name='每日学习词数')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

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
