from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

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
    last_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="最后登录IP")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="信息最后更新时间")

    # 外观偏好
    bg_color = models.CharField(max_length=200, blank=True, null=True, verbose_name="背景颜色/渐变值")
    bg_image_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="背景图片URL")
    bg_blur = models.FloatField(default=2.0, verbose_name="背景模糊度(px)")

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

class Word(models.Model):
    """
    全局单词库：存储单词的原型及 AI 生成的元数据
    """
    word = models.CharField(max_length=100, unique=True, verbose_name="单词原文")
    phonetic = models.CharField(max_length=100, blank=True, null=True, verbose_name="音标")
    
    # definitions 存储结构示例: [{"pos": "n.", "meaning": "苹果"}, {"pos": "vt.", "meaning": "评价"}]
    definitions = models.JSONField(default=list, verbose_name="释义列表", help_text="包含词性与中文释义的 JSON 数组")
    
    # examples 存储结构示例: [{"en": "Sentence", "zh": "翻译"}]
    examples = models.JSONField(default=list, verbose_name="例句列表", help_text="包含中英对照例句的 JSON 数组")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收录时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "全局词库"
        verbose_name_plural = "全局词库"
        db_table = 'vocabulary_words'

    def __str__(self):
        return self.word

class Notebook(models.Model):
    """
    用户生词本（收藏夹）
    """
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
