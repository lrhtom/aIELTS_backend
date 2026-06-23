"""User-facing feedback + AI prompt sharing."""
from django.db import models


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
