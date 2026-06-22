import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0043_user_target_listening_user_target_reading_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('skill', models.CharField(choices=[('reading', '阅读'), ('listening', '听力'), ('writing', '写作')], max_length=20, verbose_name='技能类型')),
                ('subtype', models.CharField(blank=True, default='', max_length=50, verbose_name='子类型')),
                ('title', models.CharField(blank=True, default='', max_length=300, verbose_name='展示标题')),
                ('content_json', models.JSONField(default=dict, verbose_name='生成内容')),
                ('user_answer_json', models.JSONField(blank=True, null=True, verbose_name='用户作答')),
                ('ai_feedback_json', models.JSONField(blank=True, null=True, verbose_name='AI 反馈/评分')),
                ('answered_at', models.DateTimeField(blank=True, null=True, verbose_name='首次作答时间')),
                ('last_attempt_at', models.DateTimeField(blank=True, null=True, verbose_name='最近作答时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='生成时间')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_questions', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'verbose_name': 'AI 题库题目',
                'verbose_name_plural': 'AI 题库题目',
                'db_table': 'ai_questions',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', 'skill', '-created_at'], name='idx_aiq_user_skill_created')],
            },
        ),
    ]
