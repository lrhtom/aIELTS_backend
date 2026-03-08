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
    
    wechat_openid = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="微信OpenID")
    github_id = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="Github ID")

    is_email_verified = models.BooleanField(default=False, verbose_name="邮箱是否验证")
    last_ip = models.GenericIPAddressField(blank=True, null=True, verbose_name="最后登录IP")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="信息最后更新时间")

    class Meta:
        verbose_name = "用户信息"
        verbose_name_plural = "用户信息列表"
        db_table = 'user_profiles'

    def __str__(self):
        return f"{self.username} ({self.get_membership_tier_display()})"

class AIPrompt(models.Model):
    username = models.CharField(max_length=150, verbose_name="用户名")
    prompt_content = models.TextField(verbose_name="提示词内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AI 提示词"
        verbose_name_plural = "AI 提示词列表"

    def __str__(self):
        return f"{self.username} - {self.prompt_content[:30]}"
