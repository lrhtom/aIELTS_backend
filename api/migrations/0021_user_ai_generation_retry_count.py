from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_user_deletion_requested_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ai_generation_retry_count',
            field=models.IntegerField(default=0, help_text='当AI生成失败时自动重试的次数，范围0-10次。更多重试次数会增加AT币消耗。', verbose_name='AI生成重试次数(0-10)'),
        ),
    ]
