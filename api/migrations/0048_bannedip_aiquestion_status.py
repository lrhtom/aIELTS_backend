"""Add BannedIP table + async AIQuestion status/error_message.

- `banned_ips` table backs the admin IP blocklist (middleware rejects requests
  whose client IP is in this table).
- `AIQuestion.status` + `error_message` support the async generation flow:
  frontend clicks "generate" → row is inserted with status='generating' →
  background thread fills content_json + flips status to 'ready' / 'failed'.

Existing rows default to 'ready' so historic questions remain viewable.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0047_heal_empty_email_rows'),
    ]

    operations = [
        migrations.CreateModel(
            name='BannedIP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(unique=True, verbose_name='被封禁IP')),
                ('reason', models.CharField(blank=True, default='', max_length=200, verbose_name='封禁原因')),
                ('banned_at', models.DateTimeField(auto_now_add=True, verbose_name='封禁时间')),
                ('banned_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name='banned_ip_actions',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='操作管理员',
                )),
            ],
            options={
                'verbose_name': 'IP 封禁',
                'verbose_name_plural': 'IP 封禁列表',
                'db_table': 'banned_ips',
                'ordering': ['-banned_at'],
            },
        ),
        migrations.AddField(
            model_name='aiquestion',
            name='status',
            field=models.CharField(
                choices=[('generating', '生成中'), ('ready', '已完成'), ('failed', '生成失败')],
                default='ready',
                max_length=20,
                verbose_name='生成状态',
            ),
        ),
        migrations.AddField(
            model_name='aiquestion',
            name='error_message',
            field=models.TextField(blank=True, default='', verbose_name='失败原因'),
        ),
        migrations.AddIndex(
            model_name='aiquestion',
            index=models.Index(fields=['status', 'created_at'], name='idx_aiq_status_created'),
        ),
    ]
