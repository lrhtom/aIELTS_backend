from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_user_jwt_token_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiprompt',
            name='title',
            field=models.CharField(default='', max_length=200, verbose_name='提示词标题'),
        ),
        migrations.AddField(
            model_name='aiprompt',
            name='likes',
            field=models.ManyToManyField(
                blank=True,
                related_name='liked_prompts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='点赞用户',
            ),
        ),
        migrations.AddField(
            model_name='aiprompt',
            name='favorites',
            field=models.ManyToManyField(
                blank=True,
                related_name='favorited_prompts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='收藏用户',
            ),
        ),
    ]
