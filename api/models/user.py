"""User model — defines the custom user (extends AbstractUser).

`settings.AUTH_USER_MODEL = 'api.User'` resolves to this class.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    全面定制化的用户模型
    """

    class MembershipTier(models.TextChoices):
        FREE = 'FREE', _('免费用户')
        PRO = 'PRO', _('专业会员')
        PREMIUM = 'PREMIUM', _('尊享会员')

    # Email is optional. When provided, it stays unique across users.
    # When absent, the user can only log in via username. `unique=True + null=True`
    # keeps MySQL happy — multiple NULLs are allowed, only real values collide.
    email = models.EmailField(_('email address'), blank=True, null=True, unique=True, error_messages={
        'unique': _("A user with that email already exists."),
    })
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="手机号", unique=True)
    nickname = models.CharField(max_length=50, blank=True, verbose_name="用户昵称")
    # Stores a relative media key (e.g. "avatars/user_1_ab12.jpg"). Frontend
    # composes the full URL with VITE_MEDIA_BASE. Not a URLField because the
    # value is no longer a URL — kept the field name for API-contract stability.
    avatar_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="头像URL")
    avatar_file = models.CharField(max_length=255, blank=True, null=True, verbose_name="头像文件路径")

    target_score = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="目标分数(如: 7.5)")
    target_listening = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="听力目标分数")
    target_reading = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="阅读目标分数")
    target_writing = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="写作目标分数")
    target_speaking = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True, verbose_name="口语目标分数")

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
    # Polymorphic: holds either a relative media key ("bg_images/…") for
    # uploads, or an external http(s):// URL pasted by the user.
    bg_image_url = models.CharField(max_length=1000, blank=True, null=True, verbose_name="背景图片URL")
    bg_blur = models.FloatField(default=2.0, verbose_name="背景模糊度(px)")

    # AI生成相关设置
    ai_generation_retry_count = models.IntegerField(
        default=0,
        verbose_name="AI生成重试次数(0-10)",
        help_text="当AI生成失败时自动重试的次数，范围0-10次。更多重试次数会增加AT币消耗。"
    )

    # 跨端同步的偏好设置
    target_vocab_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="首选目标生词本")
    language_preference = models.CharField(max_length=10, default='zh', verbose_name="语言偏好(zh/en)")
    ai_provider = models.CharField(max_length=40, default='deepseek', verbose_name="默认AI提供商")
    vocab_complete_difficulty = models.CharField(max_length=10, default='hint', verbose_name='补全模式难度(easy/hint/hard)')

    class Meta:
        verbose_name = "用户信息"
        verbose_name_plural = "用户信息列表"
        db_table = 'user_profiles'

    def __str__(self):
        return f"{self.username} ({self.get_membership_tier_display()})"


class BannedIP(models.Model):
    """Admin-maintained IP blocklist. Middleware rejects any request whose
    client IP appears here (matches against a Redis-mirrored set when Redis is
    available, otherwise falls back to a DB query).
    """
    ip_address = models.GenericIPAddressField(unique=True, verbose_name="被封禁IP")
    reason = models.CharField(max_length=200, blank=True, default='', verbose_name="封禁原因")
    banned_at = models.DateTimeField(auto_now_add=True, verbose_name="封禁时间")
    banned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='banned_ip_actions', verbose_name="操作管理员"
    )

    class Meta:
        verbose_name = "IP 封禁"
        verbose_name_plural = "IP 封禁列表"
        db_table = 'banned_ips'
        ordering = ['-banned_at']

    def __str__(self):
        return f"{self.ip_address} ({self.reason or 'no reason'})"
