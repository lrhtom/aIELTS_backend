"""Convert any legacy `email = ''` rows into `email = NULL`.

Before registration was refactored to allow emailless users, an earlier
buggy code path INSERTed rows with `email = ''`. Under `UNIQUE(email)`, MySQL
allows exactly one such row — the *second* emailless registration then
crashes with `Duplicate entry '' for key 'user_profiles.email'`.

The healed state: NULL. MySQL's UNIQUE ignores NULL, so unlimited emailless
users are fine.
"""
from django.db import migrations


def heal_empty_emails(apps, schema_editor):
    User = apps.get_model('api', 'User')
    User.objects.filter(email='').update(email=None)


def reverse_noop(apps, schema_editor):
    # No safe way to reconstruct '' back — the empty string carries no signal.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0046_user_email_optional'),
    ]

    operations = [
        migrations.RunPython(heal_empty_emails, reverse_noop),
    ]
