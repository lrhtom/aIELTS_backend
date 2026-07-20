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


class SurveyResponse(models.Model):
    """雅思平台用户问卷调查提交记录。

    结构对齐前端问卷（3 大部分）：
    - Part A 人口统计（可选）：备考时长、目标分数（存原始 choice key）。
    - Part B 平台评价（1-5 李克特量表，必填）：8 项评分；0 表示未作答（历史/异常数据兜底）。
    - Part C 开放题（可选）：最有用之处 / 改进建议 / 其他评论。

    与 Feedback 一样允许同一用户多次提交（反馈会随使用时间变化），管理员看全部。
    """

    user = models.ForeignKey(
        'api.User', on_delete=models.CASCADE,
        related_name='survey_responses', verbose_name="用户",
    )
    username = models.CharField(max_length=150, verbose_name="用户名")

    # ── Part A — Demographics (optional) ──
    prep_duration = models.CharField(max_length=20, blank=True, default='', verbose_name="备考时长")
    target_band = models.CharField(max_length=20, blank=True, default='', verbose_name="目标分数")

    # ── Part B — Platform Evaluation (1-5; 0 = 未作答) ──
    q_all_skills = models.PositiveSmallIntegerField(default=0, verbose_name="四项技能练习有用")
    q_reading_relevant = models.PositiveSmallIntegerField(default=0, verbose_name="AI 阅读材料相关")
    q_listening_clear = models.PositiveSmallIntegerField(default=0, verbose_name="听力 TTS 清晰有用")
    q_speaking_anxiety = models.PositiveSmallIntegerField(default=0, verbose_name="口语练习缓解焦虑")
    q_writing_feedback = models.PositiveSmallIntegerField(default=0, verbose_name="写作反馈指出弱点")
    q_vocab_memory = models.PositiveSmallIntegerField(default=0, verbose_name="词汇复习助记忆")
    q_easy_navigate = models.PositiveSmallIntegerField(default=0, verbose_name="易于导航使用")
    q_recommend = models.PositiveSmallIntegerField(default=0, verbose_name="愿意推荐")

    # ── Part C — Open-ended (optional) ──
    most_useful = models.TextField(blank=True, default='', verbose_name="最有用之处")
    improvements = models.TextField(blank=True, default='', verbose_name="改进建议")
    other_comments = models.TextField(blank=True, default='', verbose_name="其他评论")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="提交时间")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "问卷调查"
        verbose_name_plural = "问卷调查列表"

    def __str__(self):
        return f"{self.username} - survey #{self.pk}"
