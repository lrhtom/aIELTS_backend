from django.db import migrations
from django.utils import timezone


def fill_last_login_for_existing_users(apps, schema_editor):
    User = apps.get_model('api', 'User')
    User.objects.filter(last_login__isnull=True).update(last_login=timezone.now())


def noop_reverse(apps, schema_editor):
    # Keep historical values on rollback.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_word_notebook_notebookword'),
    ]

    operations = [
        migrations.RunPython(fill_last_login_for_existing_users, noop_reverse),
    ]
