"""Personal assistant / sidebar features: todos, shortcuts, creative workshop, markdown notes."""
from django.conf import settings
from django.db import models

from .user import User


class UserTodoItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='todos', verbose_name='用户')
    text = models.CharField(max_length=255, verbose_name='待办内容')
    done = models.BooleanField(default=False, verbose_name='是否完成')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'user_todo_items'
        verbose_name = '用户待办事项'
        verbose_name_plural = '用户待办事项'
        ordering = ['created_at']


class UserShortcut(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shortcuts', verbose_name='用户')
    title = models.CharField(max_length=100, verbose_name='标题')
    url = models.URLField(max_length=500, verbose_name='链接地址')
    open_in_new_tab = models.BooleanField(default=True, verbose_name='新标签页打开')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'user_shortcuts'
        verbose_name = '用户快捷访问'
        verbose_name_plural = '用户快捷访问'
        ordering = ['created_at']


class CreativeWorkshopPage(models.Model):
    """用户在创意工坊中生成的学习网页。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='creative_workshop_pages',
        verbose_name='用户',
    )
    title = models.CharField(max_length=120, verbose_name='网页标题')
    method_prompt = models.TextField(verbose_name='学习方法描述')
    generated_html = models.TextField(verbose_name='AI 生成网页源码')
    is_favorited = models.BooleanField(default=False, verbose_name='是否收藏')
    ai_provider = models.CharField(max_length=30, default='deepseek', verbose_name='生成模型提供商')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'creative_workshop_pages'
        verbose_name = '创意工坊网页'
        verbose_name_plural = '创意工坊网页'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'is_favorited', 'updated_at'], name='idx_cw_user_fav_updated'),
        ]

    def __str__(self):
        return f'{self.title} ({self.user.username})'


class MarkdownNote(models.Model):
    """User-owned markdown note with tags."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='markdown_notes',
        verbose_name='用户',
    )
    title = models.CharField(max_length=200, verbose_name='笔记标题')
    tags = models.JSONField(default=list, blank=True, verbose_name='标签列表')
    content = models.TextField(blank=True, default='', verbose_name='Markdown 内容')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'markdown_notes'
        verbose_name = 'Markdown 笔记'
        verbose_name_plural = 'Markdown 笔记列表'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'updated_at'], name='idx_mn_user_updated'),
        ]

    def __str__(self):
        return f'{self.title} ({self.user.username})'
