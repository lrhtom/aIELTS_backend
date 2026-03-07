from django.db import models

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
