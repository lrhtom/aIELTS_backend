from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_notebookword_custom_zh'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LearningPlan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='计划名称')),
                ('daily_count', models.IntegerField(default=20, verbose_name='每日学习词数')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='learning_plans', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': '学习计划',
                'verbose_name_plural': '学习计划',
                'db_table': 'vocab_learning_plans',
            },
        ),
        migrations.CreateModel(
            name='LearningPlanEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('word', models.CharField(max_length=200, verbose_name='单词')),
                ('zh', models.CharField(blank=True, max_length=500, verbose_name='中文释义')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='api.learningplan')),
            ],
            options={
                'verbose_name': '学习计划词条',
                'verbose_name_plural': '学习计划词条',
                'db_table': 'vocab_learning_plan_entries',
            },
        ),
        migrations.AlterUniqueTogether(
            name='learningplanentry',
            unique_together={('plan', 'word')},
        ),
    ]
