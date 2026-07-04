"""Practice-related records: speaking topic bank/history, writing service records, AI question bank."""
from django.conf import settings
from django.db import models

from .user import User


class SpeakingScenarioHistory(models.Model):
    """
    全局共享的口语场景生成历史，防止AI重复生成相同场景。
    """
    topic = models.CharField(max_length=500, verbose_name="场景主题")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="生成时间")

    class Meta:
        db_table = 'speaking_scenario_history'
        verbose_name = '口语随机场景历史'
        verbose_name_plural = '口语随机场景历史列表'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.topic[:50]} ({self.created_at})"


class SpeakingTopicBank(models.Model):
    """
    环球教育雅思口语题库（2025年9-12月）
    包含 Part 1、Part 2、Part 3 全部真题，AI 选题时优先选取 times_used 最少的题目。
    """
    part = models.SmallIntegerField(verbose_name="考试部分 (1/2/3)")
    category = models.CharField(max_length=100, verbose_name="大类标签")
    date = models.CharField(max_length=100, blank=True, verbose_name="日期批次")
    topic_en = models.CharField(max_length=300, blank=True, verbose_name="英文话题名")
    topic_zh = models.CharField(max_length=300, blank=True, verbose_name="中文话题名")
    questions_json = models.JSONField(default=list, verbose_name="问题列表（Part 1/3）")
    cue_card = models.TextField(blank=True, verbose_name="Cue Card 描述（Part 2）")
    bullet_points_json = models.JSONField(default=list, verbose_name="提示要点（Part 2）")
    times_used = models.IntegerField(default=0, verbose_name="已使用次数")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="入库时间")

    class Meta:
        db_table = 'speaking_topic_bank'
        verbose_name = '口语题库'
        verbose_name_plural = '口语题库列表'
        indexes = [
            models.Index(fields=['part', 'is_active', 'times_used'], name='idx_sp_bank_part_active_used'),
        ]

    def __str__(self):
        name = self.topic_en or self.topic_zh
        return f'[Part{self.part}] {name[:60]}'


class WritingServiceRecord(models.Model):
    SERVICE_CHOICES = [
        ('correction', '作文批改'),
        ('task1_teacher', '小作文老师'),
        ('task2_teacher', '大作文老师'),
        ('opinion_drill', '观点题特训'),
        ('typing_chat', '打字聊天'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='writing_records')
    service_type = models.CharField(max_length=50, choices=SERVICE_CHOICES, verbose_name='服务类型')
    title = models.CharField(max_length=255, verbose_name='记录标题')
    content = models.JSONField(verbose_name='生成内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'writing_service_records'
        verbose_name = '写作服务记录'
        verbose_name_plural = '写作服务记录'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.get_service_type_display()} - {self.title}'


class AIQuestion(models.Model):
    """AI 题库题目：listening / reading / writing 的生成产物 + 用户最近一次作答。"""

    SKILL_READING = 'reading'
    SKILL_LISTENING = 'listening'
    SKILL_WRITING = 'writing'
    SKILL_CHOICES = [
        (SKILL_READING, '阅读'),
        (SKILL_LISTENING, '听力'),
        (SKILL_WRITING, '写作'),
    ]

    STATUS_GENERATING = 'generating'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_GENERATING, '生成中'),
        (STATUS_READY, '已完成'),
        (STATUS_FAILED, '生成失败'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_questions',
        verbose_name='用户',
    )
    skill = models.CharField(max_length=20, choices=SKILL_CHOICES, verbose_name='技能类型')
    subtype = models.CharField(max_length=50, blank=True, default='', verbose_name='子类型')
    title = models.CharField(max_length=300, blank=True, default='', verbose_name='展示标题')
    content_json = models.JSONField(default=dict, verbose_name='生成内容')
    user_answer_json = models.JSONField(null=True, blank=True, verbose_name='用户作答')
    ai_feedback_json = models.JSONField(null=True, blank=True, verbose_name='AI 反馈/评分')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_READY,
        verbose_name='生成状态',
    )
    error_message = models.TextField(blank=True, default='', verbose_name='失败原因')
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name='首次作答时间')
    last_attempt_at = models.DateTimeField(null=True, blank=True, verbose_name='最近作答时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='生成时间')

    class Meta:
        db_table = 'ai_questions'
        verbose_name = 'AI 题库题目'
        verbose_name_plural = 'AI 题库题目'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'skill', '-created_at'], name='idx_aiq_user_skill_created'),
            models.Index(fields=['status', 'created_at'], name='idx_aiq_status_created'),
        ]

    def __str__(self):
        return f'[{self.skill}] {self.title or self.id} ({self.user.username})'
