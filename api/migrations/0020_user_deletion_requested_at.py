from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_add_plan_id_to_vocabfsrs'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='deletion_requested_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='申请注销时间'),
        ),
    ]
