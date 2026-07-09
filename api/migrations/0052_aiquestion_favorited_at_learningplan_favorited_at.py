from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0051_makeup_card_seed'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiquestion',
            name='favorited_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='收藏时间'),
        ),
        migrations.AddField(
            model_name='learningplan',
            name='favorited_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='收藏时间'),
        ),
    ]
