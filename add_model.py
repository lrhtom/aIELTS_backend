import os

model_code = """

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
"""

with open('e:/code/web/work/aIELTS/backend/api/models.py', 'a', encoding='utf-8') as f:
    f.write(model_code)
