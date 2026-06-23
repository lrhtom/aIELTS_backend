"""Per-user daily aggregates: learning time + activity/check-in stats."""
from django.conf import settings
from django.db import models

from .user import User


class UserDailyLearningTime(models.Model):
    """Per-user daily accumulated learning time shared across all plans."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_learning_times',
        verbose_name='用户',
    )
    study_date = models.DateField(verbose_name='学习日期')
    total_seconds = models.PositiveIntegerField(default=0, verbose_name='学习时长(秒)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_daily_learning_time'
        verbose_name = '用户每日学习时长'
        verbose_name_plural = '用户每日学习时长'
        unique_together = ('user', 'study_date')
        indexes = [
            models.Index(fields=['user', 'study_date'], name='idx_udlt_user_date'),
        ]

    def __str__(self):
        return f'{self.user.username} {self.study_date} {self.total_seconds}s'


class UserDailyStats(models.Model):
    """Per-user per-day learning stats, check-in, and activity tracking."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField(verbose_name="日期")
    # Check-in
    is_checked_in = models.BooleanField(default=False, verbose_name="是否签到")
    checkin_bonus = models.PositiveIntegerField(default=0, verbose_name="签到奖励AT")
    checkin_count = models.PositiveIntegerField(default=0, verbose_name="累计签到次数")
    # Activity
    has_activity = models.BooleanField(default=False, verbose_name="是否有学习活动")
    practice_count = models.PositiveSmallIntegerField(default=0, verbose_name="练习次数")
    speaking_count = models.PositiveSmallIntegerField(default=0, verbose_name="口语练习次数")
    listening_count = models.PositiveSmallIntegerField(default=0, verbose_name="听力练习次数")
    reading_count = models.PositiveSmallIntegerField(default=0, verbose_name="阅读练习次数")
    writing_count = models.PositiveSmallIntegerField(default=0, verbose_name="写作练习次数")
    vocab_count = models.PositiveSmallIntegerField(default=0, verbose_name="词汇练习次数")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_daily_stats'
        verbose_name = '用户每日统计'
        verbose_name_plural = '用户每日统计列表'
        unique_together = [['user', 'date']]
        indexes = [
            models.Index(fields=['user', 'date'], name='idx_uds_user_date'),
        ]

    def __str__(self):
        return f'{self.user.username} — {self.date}'
